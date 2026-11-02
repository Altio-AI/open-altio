"""A counted question as the second count reads it (recount.py): each parameter read from the
query string again, apart from filters.py and explore.py, and the drugs it names found on the
release's own tables.

    read(con, question)   an Asked: what the question asks, each value as the second count
                          uses it; `con` holds the release's tables
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

import duckdb

from open_altio.faers.explorer_db import drug_term, reaction_term
from open_altio.rulebook import is_on, value

from .drugs import default_roles, default_unit, roles
from .filters import (
    DEDUP_CHOICES,
    DIRECT,
    DIRECT_WORDS,
    ERA_T,
    FORM_MARK,
    NOT_GIVEN,
    ROLES,
    age_bands,
    default_dedup,
    default_eras,
    label_outcomes,
    nothing_ticked,
)

Question = dict[str, list[str]]
RECORD = ("era_T", "primaryid", "quarter_T", "drug_seq")  # a drug record's key
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
DAYS = re.compile(r"(\d*)-(\d*)")  # an onset's days, both ends included, either end open
CHALLENGES = ("Y", "N", "D")  # FDA's dechal and rechal codes that give one
WRITTEN = ("dose", "route", "dose_form", "lot")  # matched as written, in capitals


@dataclass(frozen=True)
class Drug:
    """One drug as a question counts it: its ingredients as the release names them, or None for
    FDA's spellings with no ingredient alone; in any product holding them or that product alone
    (`exact`), in `roles`, less the spellings `excluded`, plus the spellings with no ingredient
    `included`."""

    substance: str | None
    roles: tuple[str, ...]
    exact: bool = False
    excluded: tuple[str, ...] = ()
    included: tuple[str, ...] = ()


@dataclass(frozen=True)
class Asked:
    """What a question asks, each value as the second count uses it."""

    by: str
    eras: tuple[str, ...]  # era_T's values
    kept_only: bool  # probable duplicates set aside
    drug: str | None  # a drug name or active ingredient, as drugname_norm_T writes it
    drug_roles: tuple[str, ...]  # the role of the drug's record, alone or with `drug`
    reaction: str | None  # the one reaction, as its key: lower case, runs of spaces made one
    reactions: tuple[str, ...]  # the chosen reactions' keys, less those left out
    received: tuple[date | None, date | None]  # the first and last day a case is dated by
    event: tuple[date | None, date | None]  # the first and last day of the event
    fields: dict[str, tuple[str, ...]]  # each field filter's values: country, sex, age, reporter
    outcomes: tuple[str, ...]
    sender: str  # "" for none, DIRECT, NOT_GIVEN, or a spelling in capitals
    product: Drug | None
    drugs: tuple[Drug, ...]  # All cases' drugs, any one of them
    labels: tuple[str, ...] | None  # the label flags ticked; None when every one is
    # each filter on the drug records and the report, by its parameter: dose, route, dose_form,
    # lot, indication, onset, dechal, rechal, other_drug, report_type, other_reaction
    records: dict[str, tuple[str, ...]]


def days(text: str) -> tuple[int | None, int | None] | None:
    """An onset's first and last day, None for an open end; None for text that is no range."""
    found = DAYS.fullmatch(text)
    if not found or text == "-":
        return None
    low, high = (int(g) if g else None for g in found.groups())
    return None if low is not None and high is not None and low > high else (low, high)


def _given(question: Question, name: str) -> list[str]:
    return [v for v in (x.strip() for x in question.get(name, [])) if v]


def _first(question: Question, name: str) -> str:
    found = _given(question, name)
    return found[0] if found else ""


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _codes(question: Question, name: str) -> tuple[str, ...]:
    return _unique(v if v == NOT_GIVEN else v.upper() for v in _given(question, name))


def _day(question: Question, name: str) -> date | None:
    text = _first(question, name)
    if not DAY.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _eras(question: Question) -> tuple[str, ...]:
    if _given(question, "era"):
        named = [e for e in _codes(question, "era") if e in ERA_T]
    elif _given(question, FORM_MARK):  # a form with no era ticked
        named = []
    else:
        named = list(default_eras())
    return tuple(ERA_T[e] for e in named)


def _sender(question: Question) -> str:
    """The sender asked: the reports sent straight to FDA, chosen as such or typed as the words
    shown for them or, with rule company-names on, as FDA's own intake; none given; or a
    spelling."""
    sender = _first(question, "sender")
    direct = {DIRECT_WORDS.upper()}
    if is_on("company-names"):
        direct.add(str(value("company-names", "fda_sender")).strip().upper())
    if sender == DIRECT or sender.upper() in direct:
        return DIRECT
    return sender if sender == NOT_GIVEN else sender.upper()


def _labels(question: Question) -> tuple[str, ...] | None:
    given = _unique(_given(question, "label"))
    shown = set(label_outcomes())
    found = tuple(t for t in given if t != nothing_ticked() and t in shown)
    return None if not found and nothing_ticked() not in given else found


def _records(question: Question) -> dict[str, tuple[str, ...]]:
    """Each filter on the drug records and the report, its values as the second count matches
    them: words in capitals with runs of spaces made one, reactions and indications by their
    key, an other drug in lower case, codes in capitals; NOT_GIVEN kept where it is a choice."""

    def each(name: str, read: Callable[[str], str]) -> tuple[str, ...]:
        return _unique(v if v == NOT_GIVEN else read(v) for v in _given(question, name))

    found = {name: each(name, lambda v: " ".join(v.split()).upper()) for name in WRITTEN}
    found["indication"] = each("indication", lambda v: reaction_term(v) or v)
    reacs = each("other_reaction", lambda v: reaction_term(v) or v)
    found["other_reaction"] = tuple(r for r in reacs if r != NOT_GIVEN)
    found["onset"] = tuple(
        o for o in _unique(_given(question, "onset")) if o == NOT_GIVEN or days(o)
    )
    for name in ("dechal", "rechal"):
        found[name] = tuple(c for c in _codes(question, name) if c in (*CHALLENGES, NOT_GIVEN))
    found["other_drug"] = each("other_drug", lambda v: " ".join(v.split()).lower())
    found["report_type"] = _codes(question, "report_type")
    return found


def _roles(given: list[str]) -> tuple[str, ...]:
    """The roles a drug is counted in: those asked, in the rule's order, else the rule's own."""
    asked = {v.strip().upper() for v in given if v.strip()}
    return tuple(r for r in roles() if r in asked) if asked else default_roles()


def _named(
    con: duckdb.DuckDBPyConnection, name: str, in_roles: tuple[str, ...], exact: bool
) -> Drug:
    """The drug a name opens: an ingredient or combination the release names; else FDA's
    spelling with no ingredient; else the drug most of the name's drug rows were read to, by its
    drug name or its active ingredient; a name the release does not hold counts its spelling."""
    own = name.strip().lower()
    held = con.execute(
        "SELECT 1 FROM drug_ingredient_T WHERE ingredient_T = ? UNION ALL "
        "SELECT 1 FROM drug_substance_T WHERE substance_T = ? LIMIT 1",
        [own, own],
    ).fetchall()
    if held:
        return Drug(own, in_roles, exact)
    term = drug_term(name)
    key = ", ".join(RECORD)
    found = con.execute(
        f"""SELECT field, substance_T, count(*) AS n FROM (
          SELECT 'drugname' AS field, s.substance_T FROM drug_latest_T d
          JOIN drug_substance_T s USING ({key}) WHERE d.drugname_norm_T = ?
          UNION ALL
          SELECT 'prod_ai' AS field, s.substance_T FROM drug_latest_T d
          JOIN drug_substance_T s USING ({key}) WHERE d.prod_ai_norm_T = ?)
        GROUP BY 1, 2 ORDER BY 3 DESC, 2""",
        [term, term],
    ).fetchall()
    if any(f == "drugname" and s is None for f, s, _ in found):
        return Drug(None, in_roles, included=(str(term),))
    read = [s for _, s, _ in found if s is not None]
    if read:
        return Drug(read[0], in_roles, exact)
    return Drug(None, in_roles, included=(name.strip().upper(),))


def _product(con: duckdb.DuckDBPyConnection, question: Question) -> Drug | None:
    name = (question.get("product") or [""])[0].strip()
    if not name:
        return None
    unit = (question.get("unit") or [""])[0] or default_unit()
    drug = _named(con, name, _roles(question.get("prole", [])), unit == "exact")
    spelled = [s.strip().upper() for s in question.get("include", []) if s.strip()]
    if drug.substance is None:
        return Drug(None, drug.roles, included=_unique((*drug.included, *spelled)))
    excluded = sorted({s.strip().upper() for s in question.get("exclude", []) if s.strip()})
    return Drug(drug.substance, drug.roles, drug.exact, tuple(excluded), _unique(spelled))


def read(con: duckdb.DuckDBPyConnection, question: Question) -> Asked:
    """What `question` asks, read from its query string, its drugs found through `con`."""
    chosen = {k for k in map(reaction_term, question.get("pt", [])) if k}
    out = {k for k in map(reaction_term, question.get("pt_out", [])) if k}
    one = _first(question, "reaction")
    bands = {b["id"] for b in age_bands()} | {NOT_GIVEN}
    dedup = _first(question, "dedup")
    in_roles = _roles(question.get("drole", []))
    exact = default_unit() == "exact"
    named = sorted({d.strip() for d in question.get("dprod", []) if d.strip()})
    return Asked(
        by=(question.get("by") or [""])[0].strip(),
        eras=_eras(question),
        kept_only=(dedup if dedup in DEDUP_CHOICES else default_dedup()) == "kept_only",
        drug=drug_term(_first(question, "drug")) if _first(question, "drug") else None,
        drug_roles=tuple(r for r in _codes(question, "role") if r in ROLES),
        reaction=reaction_term(one) if one else None,
        reactions=tuple(sorted(chosen - out)),
        received=(_day(question, "received_from"), _day(question, "received_to")),
        event=(_day(question, "event_from"), _day(question, "event_to")),
        fields={
            "country": _unique(_given(question, "country")),
            "sex": _codes(question, "sex"),
            "age": tuple(a for a in _unique(_given(question, "age")) if a in bands),
            "reporter": _codes(question, "reporter"),
        },
        outcomes=_codes(question, "outcome"),
        sender=_sender(question),
        product=_product(con, question),
        drugs=tuple(_named(con, n, in_roles, exact) for n in named),
        labels=_labels(question),
        records=_records(question),
    )


__all__ = ["Asked", "Drug", "days", "read"]
