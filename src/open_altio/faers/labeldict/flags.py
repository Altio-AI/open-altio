"""Whether each drug and reaction pair is on the drug's label (rules label-flags,
label-umbrella, label-treated-disease, label-not-a-medical-event and label-procedure).
Plain functions over plain inputs; join.py reads the pairs from a release's drug records."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from open_altio import rulebook

from ..meddra import term_key

RULE = "label-flags"
TREATED = "label-treated-disease"
UMBRELLA = "umbrella"  # the decider of an outcome the umbrella rule reached

FLAG_COLUMNS = (
    "rxcui",
    "route_families",
    "pt",
    "outcome",
    "expectedness",
    "section",
    "set_id",
    "label_date",
    "decided_by",
    "family_outcomes",
    "judged_on",
)
# who decided a label row, best first: a rule wins over a person, a person over a model
_DECIDERS = ("rule", "reviewer", "model suggestion")


@dataclass(frozen=True)
class Label:
    set_id: str
    label_date: date | None


@dataclass(frozen=True)
class Meddra:
    """What the comparison needs from the licensed part, as PT and HLT codes."""

    reaction_pt: Mapping[str, str | None]  # reaction text, as the explorer normalises it
    primary_hlt: Mapping[str, str]  # PT -> its primary HLT
    umbrella_hlt: Mapping[str, str]  # an umbrella PT -> the HLT it names
    severe: Collection[str]  # PTs named as a serious or severe form
    not_medical: Collection[str]  # PTs that name no medical event
    procedures: Collection[str]  # PTs that name a procedure
    catch_all: Collection[str] = frozenset()  # HLTs that never make a pair related
    same_meaning: Mapping[str, Collection[str]] = field(default_factory=dict)  # PT -> PTs it equals
    exact: Collection[str] = frozenset()  # real effects compared on the exact PT alone
    direction: Mapping[str, tuple[str, str]] = field(default_factory=dict)  # PT -> (up/down, stem)


@dataclass(frozen=True)
class Settings:
    """The values of rule label-flags the comparison reads, read once: a rule file is parsed
    on every read, and a release has millions of pairs."""

    expectedness: Mapping[str, str]
    decided_by: Mapping[str, str]
    closest_to_label: Sequence[str]
    unknown_family: str

    @classmethod
    def read(cls) -> Settings:
        keys = ("expectedness", "decided_by", "closest_to_label", "unknown_family")
        return cls(*(rulebook.value(RULE, k) for k in keys))


@dataclass
class _LabelPts:
    kept: dict[str, tuple[int, int, str]] = field(default_factory=dict)  # rank, order, section
    indicated: dict[str, int] = field(default_factory=dict)
    uncertain: set[str] = field(default_factory=set)
    hlts: dict[str, int] = field(default_factory=dict)  # primary HLT of a kept PT
    in_hlt: dict[str, set[str]] = field(default_factory=dict)  # the kept PTs of each such HLT
    umbrellas: dict[str, int] = field(default_factory=dict)  # HLT of a kept umbrella PT


def _rank(row: Mapping) -> int:
    return _DECIDERS.index(row["decided_by"]) if row["decided_by"] else len(_DECIDERS)


def _index(terms: Iterable[Mapping], meddra: Meddra) -> dict[str, _LabelPts]:
    """Per label: the PTs it keeps anywhere it is read (one sentence keeping a term off
    never cancels another that keeps it), the PTs its indications name, and the PTs only
    an uncertain phrase names."""
    order = {s: n for n, s in enumerate(rulebook.value(RULE, "section_order"))}
    indications = rulebook.value(TREATED, "indications_section")
    out: dict[str, _LabelPts] = {}
    for row in terms:
        pts = out.setdefault(row["set_id"], _LabelPts())
        pt, kept, section, rank = (
            row["pt_code"],
            row["kept"],
            row["section"],
            _rank(row),
        )
        if section == indications:
            if kept:
                pts.indicated[pt] = min(rank, pts.indicated.get(pt, rank))
        elif kept:
            best = (rank, order.get(section, len(order)), section)
            pts.kept[pt] = min(best, pts.kept.get(pt, best))
            for into, hlt in (
                (pts.hlts, meddra.primary_hlt.get(pt)),
                (pts.umbrellas, meddra.umbrella_hlt.get(pt)),
            ):
                if hlt is not None:
                    into[hlt] = min(rank, into.get(hlt, rank))
            if (hlt := meddra.primary_hlt.get(pt)) is not None:
                pts.in_hlt.setdefault(hlt, set()).add(pt)
        elif kept is None:
            pts.uncertain.add(pt)
    return out


def compare(
    pairs: Iterable[tuple[str | None, str, str]],
    *,
    labels: Mapping[tuple[str, str], Label],
    terms: Iterable[Mapping],
    meddra: Meddra,
) -> list[dict]:
    """One flag per (rxcui, route families, reaction text as FDA published it); see
    `Comparison`."""
    return list(Comparison(labels=labels, terms=terms, meddra=meddra).flags(pairs))


class Comparison:
    """The comparison of a release's pairs with its labels, set up once so millions of pairs
    stream through it. A pair is (rxcui, route families, reaction text as FDA published it):
    the record's RxNorm code (None without one), its candidate families sorted and joined
    with ";" (one when the form is certain, empty or `unknown_family` when nothing is known)
    and the reaction. `labels` gives the label read for each (rxcui, route family), one label
    serving several families where its routes span them; `terms` are the label_terms_T rows.

    A record is read on the labels of its own families when each has one, so every label
    whose families overlap the record's; otherwise, or when nothing is known, on every
    family's label. Several labels are resolved by `resolve`, never guessed; `judged_on`
    names the family label or labels that decided."""

    def __init__(
        self,
        *,
        labels: Mapping[tuple[str, str], Label],
        terms: Iterable[Mapping],
        meddra: Meddra,
    ) -> None:
        self.settings = Settings.read()
        self.judge = _Judge(terms, meddra, self.settings)
        self.labels = labels
        self.unknown = self.settings.unknown_family
        self.families: dict[str, list[str]] = {}
        for rxcui, family in sorted(labels):
            self.families.setdefault(rxcui, []).append(family)
        # one reaction of one drug is judged once per label, however many family sets ask
        self._seen: tuple[str | None, str] | None = None
        self._judged: dict[str, dict] = {}

    def flags(self, pairs: Iterable[tuple[str | None, str, str]]) -> Iterator[dict]:
        for rxcui, candidates, text in pairs:
            yield self.flag(rxcui, candidates, text)

    def flag(self, rxcui: str | None, candidates: str, text: str) -> dict:
        if self._seen != (rxcui, text):
            self._seen, self._judged = (rxcui, text), {}
        named = [f for f in candidates.split(";") if f and f != self.unknown]
        # a candidate family with no label counts as unknown, so every label is read
        own = rxcui is not None and all((rxcui, f) in self.labels for f in named)
        read = named if named and own else self.families.get(rxcui or "", [])
        if rxcui is None or not read:
            flag = self.judge(rxcui, candidates, text, None)
        elif read == named and len(read) == 1:
            flag = self._on(rxcui, read[0], text)
            flag["judged_on"] = read[0]
        else:
            flag = resolve({f: self._on(rxcui, f, text) for f in read}, self.settings)
        flag["route_families"] = candidates
        return {c: flag.get(c) for c in FLAG_COLUMNS}

    def _on(self, rxcui: str, family: str, text: str) -> dict:
        if family not in self._judged:
            self._judged[family] = self.judge(rxcui, family, text, self.labels[(rxcui, family)])
        return dict(self._judged[family])


def resolve(each: Mapping[str, dict], settings: Settings | None = None) -> dict:
    """One flag from the flags of every route family's label, keeping each family's
    outcome in `family_outcomes` and the families that decided in `judged_on`. When one
    family's label has the reaction on it and another's does not, `forms_differ` ("on the
    tablet label, not on the gel label"). Otherwise the outcome closest to the label: all
    agree on expectedness, so nothing is hidden by taking it."""
    settings = settings or Settings.read()
    flags = dict(sorted(each.items()))
    first = dict(next(iter(flags.values())))
    first["family_outcomes"] = "; ".join(f"{f}: {flag['outcome']}" for f, flag in flags.items())
    if len({flag["expectedness"] for flag in flags.values()}) > 1:
        first.update(
            outcome="forms_differ",
            expectedness=settings.expectedness["forms_differ"],
            decided_by=settings.decided_by[_DECIDERS[0]],
            set_id=None,
            label_date=None,
            section=None,
            judged_on="; ".join(flags),
        )
        return first
    closest = settings.closest_to_label
    best_outcome = min((f["outcome"] for f in flags.values()), key=closest.index)
    deciding = [f for f, flag in flags.items() if flag["outcome"] == best_outcome]
    best = dict(flags[deciding[0]])
    best["family_outcomes"] = first["family_outcomes"]
    best["judged_on"] = "; ".join(deciding)
    if len({flags[f]["set_id"] for f in deciding}) > 1:  # no one label to point to
        best.update(set_id=None, label_date=None, section=None)
    return best


class _Judge:
    """The flag of one reaction against one label, in the order rule label-flags gives."""

    def __init__(self, terms: Iterable[Mapping], meddra: Meddra, settings: Settings) -> None:
        self.named = settings.decided_by
        self.expectedness = settings.expectedness
        self.worse = [
            f" {w.lower().replace('-', ' ')} " for w in rulebook.value(TREATED, "worsening_words")
        ]
        self.by_label = _index(terms, meddra)
        self.meddra = meddra
        # each reaction text's PT, read once: the key's reading reads a rule file each time
        self._pt_of: dict[str, str | None] = {}

    def _pt(self, text: str) -> str | None:
        if text not in self._pt_of:
            term = term_key("pt", text)
            self._pt_of[text] = self.meddra.reaction_pt.get(term) if term else None
        return self._pt_of[text]

    def __call__(self, rxcui: str | None, family: str, text: str, label: Label | None) -> dict:
        flag = {
            "rxcui": rxcui,
            "route_families": family,
            "pt": text,
            "section": None,
            "set_id": label.set_id if label else None,
            "label_date": label.label_date if label else None,
        }
        pt = self._pt(text)
        # a worse form of the disease treated is compared like any other event
        plain = f" {' '.join(text.lower().replace('-', ' ').split())} "
        treatable = not any(w in plain for w in self.worse)
        pts = self.by_label.get(label.set_id, _LabelPts()) if label else None
        outcome, decider = _outcome(pt, pts, self.meddra, treatable, flag)
        flag["outcome"] = outcome
        flag["expectedness"] = self.expectedness[outcome]
        flag["decided_by"] = self.named[decider if isinstance(decider, str) else _DECIDERS[decider]]
        return flag


def _only_opposites(pt: str, neighbours: Iterable[str], direction: Mapping) -> bool:
    """Every kept PT of the group is the opposite direction of the same measure ("platelet
    count decreased" on the label, "platelet count increased" reported): it says nothing
    about the reported one."""
    mine = direction.get(pt)
    neighbours = [n for n in neighbours if n != pt]
    if not mine or not neighbours:
        return False
    return all(
        (other := direction.get(n)) is not None and other[1] == mine[1] and other[0] != mine[0]
        for n in neighbours
    )


def _outcome(
    pt: str | None, pts: _LabelPts | None, meddra: Meddra, treatable: bool, flag: dict
) -> tuple[str, int | str]:
    """The outcome and what decided it, in the order rule label-flags gives."""
    if pt is None:
        return "uncertain", 0
    if pt in meddra.procedures:
        return "procedure", 0
    if pt in meddra.not_medical:
        return "not_a_medical_event", 0
    if pts is None:
        return "no_label", 0
    if pt in meddra.exact:
        if pt in pts.kept:
            rank, _order, flag["section"] = pts.kept[pt]
            return "on_label", rank
        return "not_on_label", 0
    if treatable and pt in pts.indicated:
        return "treated_disease", pts.indicated[pt]
    if pt in pts.kept:
        rank, _order, flag["section"] = pts.kept[pt]
        return "on_label", rank
    twins = [t for t in meddra.same_meaning.get(pt, ()) if t in pts.kept]
    if twins:  # the label keeps the PT that means the same
        rank, _order, flag["section"] = min(pts.kept[t] for t in twins)
        return "on_label", rank
    hlt = meddra.primary_hlt.get(pt)
    if hlt in pts.umbrellas and pt not in meddra.severe:
        return "on_label", UMBRELLA
    if pt in pts.uncertain:
        return "uncertain", 0
    if (
        hlt in pts.hlts
        and hlt not in meddra.catch_all
        and not _only_opposites(pt, pts.in_hlt[hlt], meddra.direction)
    ):
        return "related", pts.hlts[hlt]
    return "not_on_label", 0
