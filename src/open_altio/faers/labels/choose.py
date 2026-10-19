"""Choose one label per ingredient and route family (rule label-choice)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from open_altio import rulebook

from ..route import RouteTables, families
from .spl import LabelFacts

RULE = "label-choice"
OTHER = "other"
# How a label found its RxNorm key (label_candidates_T.keyed_by_T): DailyMed's mapping
# file, or the label's own active ingredients (rule label-own-ingredients)
MAPPING_FILE, OWN_INGREDIENTS = "mapping_file", "label_ingredients"


@dataclass(frozen=True)
class Policy:
    """The rule's values, read once: the loader reads the file on every call."""

    categories: dict[str, str]  # FDA's marketing category code -> NDA, BLA, ANDA
    order: list[list[str]]
    recent_from: date
    kit_form: str
    routes: RouteTables  # the shared route table (rule drug-route): a route's families
    no_family: str  # the key of a label whose routes give no family (rule drug-route's unknown)
    accessories: frozenset[str]  # ingredients of a kit's accessory parts, lower case
    # each route name's families, read once from the shared table
    _by_route: dict[str, frozenset[str]] = field(default_factory=dict, compare=False)

    @classmethod
    def read(cls) -> Policy:
        return cls(
            rulebook.value(RULE, "marketing_categories"),
            rulebook.value(RULE, "application_order"),
            rulebook.value(RULE, "recent_from"),
            rulebook.value(RULE, "kit_form"),
            RouteTables.read(),
            families()[-1],  # the route families, then the unknown one
            frozenset(n.lower() for n in rulebook.value(RULE, "not_counted_beside_others")),
        )

    def routes_of(self, facts: LabelFacts) -> tuple[str, ...]:
        """The routes the label's drugs are given by. A kit part holding only
        accessories (an alcohol or iodine pad, placebo tablets, a part with no
        active ingredient) adds no route, and neither does the kit's own route
        list where it repeats such a part's, unless the label has no other."""

        def accessory(actives: tuple[str, ...]) -> bool:
            return all(a in self.accessories for a in actives)

        parts = [(r, a) for r, a in facts.route_parts if a is not None]
        aside = {r for r, a in parts if accessory(a)} - {r for r, a in parts if not accessory(a)}
        counted = {r for r, a in facts.route_parts if r not in aside}
        return tuple(sorted(counted)) or facts.routes

    def families_of(self, facts: LabelFacts) -> set[str]:
        """Every route family the label's routes could be in, read from the shared route
        table as FAERS's records are. A label whose routes give none, a route the table
        lacks or no route at all, is kept under `no_family`, so it is read only where a
        record's own families have no label of theirs."""
        return set(self.routes.label_families(self.routes_of(facts))) or {self.no_family}

    def _route_families(self, route: str) -> frozenset[str]:
        if route not in self._by_route:
            self._by_route[route] = self.routes.label_families([route])
        return self._by_route[route]

    def reach(self, facts: LabelFacts, family: str) -> int:
        """How closely the label's own routes name `family`: the fewest families of any
        of its routes that allow it. 1 when a route is that family alone (INTRAVENOUS for
        injected), more when the family is reached only through a broad route
        (OPHTHALMIC, the eye or an injection into it). 0 under `no_family`."""
        if family == self.no_family:
            return 0
        return min(
            len(f) for r in self.routes_of(facts) if family in (f := self._route_families(r))
        )

    def unplaced(self, facts: LabelFacts) -> list[str]:
        """The label's routes the shared route table does not hold, as a label or a FAERS
        route word; they are listed for the table's review and give no family here."""
        return [
            r
            for r in self.routes_of(facts)
            if self.routes.families("label", r) is None and self.routes.families("route", r) is None
        ]

    def is_kit(self, facts: LabelFacts) -> bool:
        """Every product the label covers is a kit; a starter pack beside
        tablets does not make a tablet label a kit."""
        return bool(facts.dosage_forms) and all(f == self.kit_form for f in facts.dosage_forms)

    def rank(self, name: str) -> int:
        return next((i for i, group in enumerate(self.order) if name in group), len(self.order))


@dataclass(frozen=True)
class Candidate:
    rxcui: str
    ingredient: str
    facts: LabelFacts
    application: str  # NDA, BLA, ANDA or other
    number: int | None  # the application number, when the label gives one
    application_id: str = ""  # as FDA writes it, such as NDA020001
    keyed_by: str = MAPPING_FILE


@dataclass(frozen=True)
class Choice:
    candidate: Candidate
    family: str  # the route family the label is chosen for
    chosen_because: str


def application(facts: LabelFacts, policy: Policy) -> tuple[str, int | None, str]:
    """The label's best marketing category in the rule's order, and the
    lowest application number given under it, as a number and as written."""
    found = [(policy.categories.get(c, OTHER), i) for c, i in facts.approvals] or [(OTHER, "")]
    best = min(policy.rank(name) for name, _ in found)
    name = next(n for n, _ in found if policy.rank(n) == best)
    numbered = sorted(
        (int(m.group()), ident)
        for n, ident in found
        if policy.rank(n) == best and (m := re.search(r"\d+", ident))
    )
    if not numbered:
        return name, None, ""
    number, ident = numbered[0]
    return name, number, ident


def _applications(facts: LabelFacts, policy: Policy) -> set[str]:
    """The NDA, BLA and ANDA numbers the label's products are marketed under."""
    return {i for code, i in facts.approvals if code in policy.categories and i}


def _kits_aside(group: list[Candidate], policy: Policy) -> set[str]:
    """Set IDs of the kits in `group` that bundle a product whose own label,
    not a kit, is also in `group`: a pharmacy's kit, whose own label loses to
    that product's. An originator sold only as kits has no such label."""
    plain: set[str] = set()
    for c in group:
        if not policy.is_kit(c.facts):
            plain |= _applications(c.facts, policy)
    return {
        c.facts.set_id
        for c in group
        if policy.is_kit(c.facts) and _applications(c.facts, policy) & plain
    }


def _order(c: Candidate, policy: Policy, kits_aside: set[str], family: str) -> tuple:
    """The rule's steps as one sort key, smallest first."""
    when = c.facts.effective_date or date.min
    return (
        policy.reach(c.facts, family),
        not c.facts.safety_text,
        c.facts.set_id in kits_aside,
        when < policy.recent_from,
        policy.rank(c.application),
        c.number if c.number is not None else float("inf"),
        -when.toordinal(),
        c.facts.set_id,
    )


_STEPS = (
    "its route is closest to {family}",
    "the only label whose safety sections hold text",
    "a kit's product has its own label",
    "the only label from {recent} on",
    "{app} before {other}",
    "lowest application number",
    "newest of the labels under this application",
    "first set ID of labels with the same date",
)


def _rank(group: list[Candidate], policy: Policy, family: str) -> tuple[Candidate, str]:
    """The winner of one family's group, and the step that decided it."""
    aside = _kits_aside(group, policy)
    ranked = sorted(group, key=lambda c: _order(c, policy, aside, family))
    winner = ranked[0]
    head = winner.application_id or winner.application
    if len(ranked) == 1:
        return winner, f"{head}: the only label"
    key = _order(winner, policy, aside, family)
    runner_up = _order(ranked[1], policy, aside, family)
    step = next(i for i in range(len(key)) if key[i] != runner_up[i])
    reason = _STEPS[step].format(
        family=family,
        recent=policy.recent_from.year,
        app=winner.application,
        other=ranked[1].application,
    )
    return winner, f"{head}: {reason}; {len(ranked)} labels"


def choose(candidates: list[Candidate], policy: Policy | None = None) -> list[Choice]:
    """One label per ingredient (or combination) and route family."""
    policy = policy or Policy.read()
    by_key: dict[str, list[Candidate]] = defaultdict(list)
    for c in candidates:
        by_key[c.rxcui].append(c)
    out = []
    for rxcui in sorted(by_key):
        group = by_key[rxcui]
        families = {c.facts.set_id: policy.families_of(c.facts) for c in group}
        for family in sorted(set().union(*families.values())):
            winner, because = _rank(
                [c for c in group if family in families[c.facts.set_id]], policy, family
            )
            out.append(Choice(winner, family, because))
    return out
