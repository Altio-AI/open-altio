"""The explorer's filters: read from a URL query string, written back to one,
turned into parameterised SQL over the release's explorer database, and
described in plain words for a page or an export manifest.

    from open_altio.explorer.filters import parse
    filters = parse(parse_qs(query_string))   # name -> its values, as urllib reads them
    clause = filters.where()                  # Clause(sql, params) over explorer_case_T c
    filters.query()                           # "drug=aspirin&sex=F", shareable
    filters.manifest()                        # {"query", "filters", "described"}

Query parameters (each list parameter may repeat; a value that is not one of the choices, or
not a date, is left out):

    drug            drug name or active ingredient (normalised as drugname_norm_T)
    role            PS, SS, C, I: the matching drug's role (alone: any drug in that role)
    reaction        reaction term (PT), case-blind
    received_from, received_to   yyyy-mm-dd, on group_first_dt_T (FDA's first receipt of any
                                 copy of the case, rule dup-shown-copy)
    event_from, event_to         yyyy-mm-dd, on event_dt_T (full dates only)
    country         country_T (occurrence, else reporter; a legacy name as its ISO code);
                    _none = not given (rule not-given)
    sex             sex_T, F or M (rule sex-codes); _none = not given (rule not-given)
    age             age_band_T, a band id from rule age-bands; _none = not given
    outcome         FDA's outc_cod; _none = no outcome row
    reporter        reporter_type_T, the E2B(R3) reporter qualification of FDA's occp_cod
                    (rule reporter-type); _none = not given
    sender          company_T: a company, or any of FDA's spellings of it, case-blind
                    (rule company-names); _direct = sent straight to FDA (a direct report),
                    as are those words or FDA's own intake typed;
                    _none = not given (rule not-given)
    era             AERS, FAERS (rule era-filter). Absent means the rule's
                    default unless `f` is present: `f` marks a submitted form,
                    where an absent era means none was ticked.
    dedup           kept_only or all (rule dedup-default)
    label           a product's Label status: the label flags ticked (rule explorer-label-flags);
                    absent means every tick on, `none` none of them. explore.scope resolves the
                    ticks into the cases they keep (label_cases), never written to the address.

No user value is ever put into SQL text: every value is a parameter.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from datetime import date
from typing import Any
from urllib.parse import urlencode

from open_altio.faers import not_given
from open_altio.faers.derive import direct_report
from open_altio.faers.explorer_db import drug_term, reaction_term, sender_key
from open_altio.rulebook import is_on, value

NOT_GIVEN = "_none"
DIRECT = "_direct"  # the sender of a report sent straight to FDA, by no company
DIRECT_WORDS = "Sent straight to FDA"
FORM_MARK = "f"

ERA_T = {"AERS": "legacy", "FAERS": "faers"}  # rule era-filter names -> era_T
ERA_LABEL = {"AERS": "AERS (2004Q1 to 2012Q3)", "FAERS": "FAERS (2012Q4 onward)"}
DEDUP_CHOICES = {
    "kept_only": "Kept cases only (probable duplicates set aside)",
    "all": "All cases, flagged duplicates included",
}

# FDA's code lists (FAERS README), and the E2B(R3) reporter qualification (rule reporter-type);
# codes are shown as written, with these words beside.
ROLES = {"PS": "Primary suspect", "SS": "Secondary suspect", "C": "Concomitant", "I": "Interacting"}
OUTCOMES = {
    "DE": "Death",
    "LT": "Life-threatening",
    "HO": "Hospitalization",
    "DS": "Disability",
    "CA": "Congenital anomaly",
    "RI": "Required intervention",
    "OT": "Other serious",
}
REPORTERS = {
    "1": "Physician",
    "2": "Pharmacist",
    "3": "Other health professional",
    "4": "Lawyer",
    "5": "Consumer or other non health professional",
}
SEXES = {"F": "Female", "M": "Male"}
LABEL_WORDS = "explorer-label-words"  # the label flags' words, as the page says them too

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def default_eras() -> tuple[str, ...]:
    return tuple(value("era-filter", "default"))


def default_dedup() -> str:
    return value("dedup-default", "explorer_default")


def age_bands() -> list[dict]:
    return list(value("age-bands", "bands"))


def not_given_label() -> str:
    return not_given.label()


def label_outcomes() -> list[str]:
    return list(value("explorer-label-flags", "outcomes"))


def label_words() -> dict[str, str]:
    """Each label flag as a line of words says it (rule explorer-label-words): a flag that was
    not compared with the label with its reason, "Not compared (a procedure)"."""
    words, reasons = value(LABEL_WORDS, "words"), value(LABEL_WORDS, "reasons")
    return {k: f"{w} ({reasons[k]})" if k in reasons else w for k, w in words.items()}


def nothing_ticked() -> str:
    return value("explorer-label-flags", "nothing_ticked")


@dataclass(frozen=True)
class Clause:
    sql: str
    params: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class Filters:
    drug: str = ""
    roles: tuple[str, ...] = ()
    reaction: str = ""
    received_from: date | None = None
    received_to: date | None = None
    event_from: date | None = None
    event_to: date | None = None
    countries: tuple[str, ...] = ()
    sexes: tuple[str, ...] = ()
    ages: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    reporters: tuple[str, ...] = ()
    sender: str = ""
    eras: tuple[str, ...] | None = None  # None: the rule's default
    dedup: str = ""  # "": the rule's default
    labels: tuple[str, ...] | None = None  # None: every label flag ticked
    label_cases: tuple[int, ...] | None = None  # the cases `labels` keeps, set by explore.scope

    # defaults resolved through the rules ---------------------------------------

    @property
    def era_list(self) -> tuple[str, ...]:
        return default_eras() if self.eras is None else self.eras

    @property
    def dedup_choice(self) -> str:
        return self.dedup or default_dedup()

    @property
    def kept_only(self) -> bool:
        return self.dedup_choice == "kept_only"

    @property
    def direct(self) -> bool:
        """The sender asked is the reports sent straight to FDA: chosen as such, or typed as the
        words the explorer shows for them or, with rule company-names on, as FDA's own intake,
        the sender FAERS writes on most of them."""
        typed = {sender_key(DIRECT_WORDS)}
        if is_on("company-names"):
            typed.add(sender_key(value("company-names", "fda_sender")))
        return self.sender == DIRECT or sender_key(self.sender) in typed

    # SQL ---------------------------------------------------------------------

    def where(self) -> Clause:
        """The WHERE condition over `explorer_case_T c`."""
        parts: list[str] = []
        params: list[Any] = []

        def add(sql: str, *values: Any) -> None:
            parts.append(sql)
            params.extend(values)

        eras = [ERA_T[e] for e in self.era_list if e in ERA_T]
        if eras:
            add(f"c.era_T IN ({_marks(eras)})", *eras)
        else:
            add("FALSE")
        if self.kept_only:
            add("c.dup_kept_T")
        term = drug_term(self.drug) if self.drug else None
        if term or self.roles:
            sub, sub_params = ["TRUE"], []
            if term:
                sub.append("term_T = ?")
                sub_params.append(term)
            if self.roles:
                sub.append(f"role_T IN ({_marks(self.roles)})")
                sub_params += list(self.roles)
            matching = " AND ".join(sub)
            add(
                f"c.case_id_T IN (SELECT case_id_T FROM explorer_drug_term_T WHERE {matching})",
                *sub_params,
            )
        reac = reaction_term(self.reaction) if self.reaction else None
        if reac:
            add(
                "c.case_id_T IN (SELECT case_id_T FROM explorer_reac_term_T WHERE term_T = ?)", reac
            )
        for column, low, high in (
            ("c.group_first_dt_T", self.received_from, self.received_to),
            ("c.event_dt_T", self.event_from, self.event_to),
        ):
            if low:
                add(f"{column} >= ?", low)
            if high:
                add(f"{column} <= ?", high)
        for column, chosen in (
            ("c.country_T", self.countries),
            ("c.sex_T", self.sexes),
            ("c.age_band_T", self.ages),
            ("c.reporter_type_T", self.reporters),
        ):
            if chosen:
                add(*_in_or_null(column, chosen))
        if self.outcomes:
            codes = [o for o in self.outcomes if o != NOT_GIVEN]
            alternatives, values = [], []
            if codes:
                alternatives.append("list_has_any(c.outcomes_T, ?::VARCHAR[])")
                values.append(codes)
            if NOT_GIVEN in self.outcomes:
                alternatives.append("len(c.outcomes_T) = 0")
            add("(" + " OR ".join(alternatives) + ")", *values)
        sender = sender_key(self.sender) if self.sender else None
        if self.direct:
            add(direct_report("c.rept_cod"))
        elif self.sender == NOT_GIVEN:
            add(f"c.company_T IS NULL AND NOT {direct_report('c.rept_cod')}")
        elif sender:
            add(
                "c.company_T IN (SELECT company_T FROM explorer_sender_T WHERE spelling_T = ?)",
                sender,
            )
        if self.label_cases is not None:
            add("c.case_id_T IN (SELECT unnest(?::BIGINT[]))", list(self.label_cases))
        return Clause(" AND ".join(parts), params)

    # the URL ---------------------------------------------------------------------

    def params(self) -> list[tuple[str, str]]:
        """(name, value) pairs for a query string; defaults are left out."""
        out: list[tuple[str, str]] = []
        if self.drug:
            out.append(("drug", self.drug))
        out += [("role", r) for r in self.roles]
        if self.reaction:
            out.append(("reaction", self.reaction))
        for name in ("received_from", "received_to", "event_from", "event_to"):
            day = getattr(self, name)
            if day:
                out.append((name, day.isoformat()))
        for name, chosen in (
            ("country", self.countries),
            ("sex", self.sexes),
            ("age", self.ages),
            ("outcome", self.outcomes),
            ("reporter", self.reporters),
        ):
            out += [(name, v) for v in chosen]
        if self.sender:
            out.append(("sender", self.sender))
        if self.eras is not None and tuple(self.eras) != default_eras():
            out.append((FORM_MARK, "1"))
            out += [("era", e) for e in self.eras]
        if self.dedup and self.dedup != default_dedup():
            out.append(("dedup", self.dedup))
        if self.labels is not None:
            out += [("label", t) for t in self.labels] or [("label", nothing_ticked())]
        return out

    def query(self) -> str:
        """The query string for these filters."""
        return urlencode(self.params())

    @property
    def is_default(self) -> bool:
        return not self.params()

    # plain words -------------------------------------------------------------

    def described(self) -> list[tuple[str, str]]:
        """(label, plain words) for every filter in force, then era and deduplication."""
        out: list[tuple[str, str]] = []
        if self.drug:
            out.append(("Drug name or active ingredient", drug_term(self.drug) or self.drug))
        if self.roles:
            out.append(("Drug role", ", ".join(f"{r} ({ROLES[r]})" for r in self.roles)))
        if self.reaction:
            out.append(("Reaction term", self.reaction.strip()))
        for label, low, high in (
            ("Received", self.received_from, self.received_to),
            ("Event date", self.event_from, self.event_to),
        ):
            if low or high:
                out.append((label, _range_words(low, high)))
        bands = {b["id"]: b["label"] for b in age_bands()}
        for label, chosen, words in (
            ("Country", self.countries, {}),
            ("Sex", self.sexes, SEXES),
            ("Age", self.ages, bands),
            ("Outcome", self.outcomes, OUTCOMES),
            ("Reporter type", self.reporters, REPORTERS),
        ):
            if chosen:
                out.append((label, ", ".join(_code_words(c, words) for c in chosen)))
        if self.sender:
            sender = self.sender.strip()
            out.append(("Company", DIRECT_WORDS if self.direct else _code_words(sender, {})))
        if self.labels is not None:
            words = label_words()
            ticked = ", ".join(words[t] for t in self.labels)
            out.append(("Label status", ticked or "None ticked"))
        eras = self.era_list
        out.append(("Era", " and ".join(ERA_LABEL[e] for e in eras) if eras else "None ticked"))
        out.append(("Deduplication", DEDUP_CHOICES[self.dedup_choice]))
        return out

    def manifest(self) -> dict:
        """What a filtered export records about the filters (rule filtered-vs-full-export)."""
        machine: dict[str, Any] = {}
        for f in fields(self):
            if f.name == "label_cases":
                continue  # the cases themselves; `labels` says what kept them
            v = getattr(self, f.name)
            if isinstance(v, date):
                v = v.isoformat()
            elif isinstance(v, tuple):
                v = list(v)
            machine[f.name] = v
        machine["eras"] = list(self.era_list)
        machine["dedup"] = self.dedup_choice
        return {
            "query": self.query(),
            "filters": machine,
            "described": [f"{k}: {v}" for k, v in self.described()],
        }

    def with_(self, **changes: Any) -> Filters:
        return replace(self, **changes)


def _marks(values: Iterable[Any]) -> str:
    return ", ".join("?" for _ in values)


def _in_or_null(column: str, chosen: tuple[str, ...]) -> tuple:
    codes = [c for c in chosen if c != NOT_GIVEN]
    alternatives, values = [], []
    if codes:
        alternatives.append(f"{column} IN ({_marks(codes)})")
        values += codes
    if NOT_GIVEN in chosen:
        alternatives.append(f"{column} IS NULL")
    return ("(" + " OR ".join(alternatives) + ")", *values)


def _code_words(code: str, words: Mapping[str, str]) -> str:
    if code == NOT_GIVEN:
        return not_given_label()
    return f"{code} ({words[code]})" if code in words else (words.get(code) or code)


def _range_words(low: date | None, high: date | None) -> str:
    """A date range in words; at least one end is given."""
    if low and high:
        return f"{low.isoformat()} to {high.isoformat()}"
    return f"from {low.isoformat()}" if low else f"up to {high}"


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def parse(query: Mapping[str, Sequence[str]]) -> Filters:
    """Filters from a query string as urllib's parse_qs reads it: each name with its values."""

    def given(name: str) -> list[str]:
        return [v for v in (x.strip() for x in query.get(name, [])) if v]

    def one(name: str) -> str:
        values = given(name)
        return values[0] if values else ""

    def day(name: str) -> date | None:
        text = one(name)
        if not _DATE.fullmatch(text):
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    def codes(name: str, allowed: Iterable[str] | None = None) -> tuple[str, ...]:
        chosen = _unique(v if v == NOT_GIVEN else v.upper() for v in given(name))
        return chosen if allowed is None else tuple(c for c in chosen if c in allowed)

    if given("era"):
        eras: tuple[str, ...] | None = codes("era", ERA_T)
    elif given(FORM_MARK):
        eras = ()
    else:
        eras = None
    bands = {b["id"] for b in age_bands()} | {NOT_GIVEN}
    ticked = given("label")
    labels: tuple[str, ...] | None = _unique(t for t in ticked if t in label_outcomes())
    if not labels and nothing_ticked() not in ticked:
        labels = None  # every tick on
    dedup = one("dedup")
    return Filters(
        drug=one("drug"),
        roles=codes("role", ROLES),
        reaction=one("reaction"),
        received_from=day("received_from"),
        received_to=day("received_to"),
        event_from=day("event_from"),
        event_to=day("event_to"),
        countries=_unique(given("country")),
        sexes=codes("sex"),
        ages=tuple(a for a in _unique(given("age")) if a in bands),
        outcomes=codes("outcome"),
        reporters=codes("reporter"),
        sender=one("sender"),
        eras=eras,
        dedup=dedup if dedup in DEDUP_CHOICES else "",
        labels=labels,
    )


__all__ = [
    "DEDUP_CHOICES",
    "ERA_LABEL",
    "ERA_T",
    "FORM_MARK",
    "label_words",
    "NOT_GIVEN",
    "OUTCOMES",
    "REPORTERS",
    "ROLES",
    "SEXES",
    "Clause",
    "Filters",
    "age_bands",
    "default_dedup",
    "default_eras",
    "label_outcomes",
    "nothing_ticked",
    "parse",
]
