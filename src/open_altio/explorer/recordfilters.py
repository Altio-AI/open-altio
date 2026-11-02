"""The filters on what a case's drug records give for the drug a question counts, and on its
report: the SQL behind the filters filters.py reads as `dose`, `route`, `dose_form`, `lot`,
`indication`, `onset`, `dechal`, `rechal`, `other_drug`, `report_type` and `other_reaction`, and
the readings an event's breakdowns count by (breakdowns/fields.py), so a breakdown line's value
and its filter pick the same cases.

    where(filters, records, reactions)   the conditions over explorer_case_T c, and parameters
    Records.of(unit)                     the drug records a question counts, or every record
    indication_keyer(reactions)          FDA's indication text -> the key it counts under
    resolved(data, filters)              the filters with FDA's indication texts their keys read

The drug records a filter reads are the product's own, in the roles it is counted in
(`drugs.Unit.records`), the records the breakdowns read; a question with no product reads every
drug record of the case. A field FDA writes once a record (time to onset, dechallenge,
rechallenge) is that of the first record giving it, in the role order of rule
explorer-drug-counts and then by FDA's drug sequence. Another drug is a record in those roles
that is not the product's; with no product, any record. A value reads Not given as rule
not-given reads it; `_none` picks the cases that give none. No value is put into SQL text.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from open_altio.faers import not_given
from open_altio.faers.explorer_db import reaction_term
from open_altio.faers.meddra import term_key

from . import drugs
from .filters import NOT_GIVEN, Filters
from .recordfields import onset_span

if TYPE_CHECKING:
    from .drugs import Unit
    from .explore import Data
    from .reactions import Reactions

Job = tuple[str, list[Any]]
# another drug, by its ingredients as the release names them, else FDA's spelling
OTHER = "coalesce({d}.substance_T, {d}.drugname_norm_T)"
# the order the first record giving a field is taken in: by role, then by FDA's drug sequence
FIRST = "list_position(?::VARCHAR[], {d}.role_T), try_cast({d}.drug_seq AS BIGINT), {d}.drug_seq"
INDICATION = "trim({i}.indi_pt)"  # an indication as FDA wrote it, read to its key apart
# the fields a drug record gives in words: each filter's parameter, FDA's field and its column
WRITTEN = {
    "dose": ("dose_vbm", "d.dose_vbm"),
    "route": ("route", "d.route"),
    "dose_form": ("dose_form", "d.dose_form"),
    "lot": ("lot_num", "d.lot_num"),
}


def written(field: str, column: str) -> str:
    """SQL: a field FDA writes in words, in capitals with its runs of spaces made one; NULL where
    it reads Not given."""
    given = not_given.given(field, column)
    return f"upper(regexp_replace(trim({given}), '[[:space:]]+', ' ', 'g'))"


def code(field: str, column: str, **context: str) -> str:
    """SQL: a code of FDA's as written, trimmed and in capitals, or NULL where it reads Not
    given."""
    return f"upper(trim({not_given.given(field, column, **context)}))"


def indication_given(i: str = "i") -> str:
    return f"{not_given.given('indi_pt', f'{i}.indi_pt')} IS NOT NULL"


def indication_keyer(reactions: Reactions) -> Callable[[str], str]:
    """The key one of FDA's indication texts counts under: today's preferred term where
    reactions are counted by it, else the text whatever its capitals and spaces."""
    meddra = reactions.meddra
    read = meddra.read("indi_pt") if meddra else {}

    def key(text: str) -> str:
        found = read.get(term_key("indi_pt", text) or "")
        return found[0].lower() if found else reaction_term(text) or text

    return key


def resolved(data: Data, filters: Filters) -> Filters:
    """`filters` with FDA's indication texts its indications read to (`indication_texts`),
    each text of the release read once and kept."""
    keys = {k for k in filters.indications if k != NOT_GIVEN}
    if not keys:
        return filters
    key = indication_keyer(data.reactions)
    texts = data.facts.once(
        "indication_texts",
        lambda: [
            r["t"]
            for r in data.rows(
                f"SELECT DISTINCT {INDICATION.format(i='i')} AS t FROM explorer_indi_T i "
                f"WHERE {indication_given()}"
            )
        ],
    )
    return replace(filters, indication_texts=tuple(sorted(t for t in texts if key(t) in keys)))


@dataclass(frozen=True)
class Records:
    """The drug records a question counts (`ours`, a condition on explorer_drug_T d), the other
    drugs (`others`), and the cases they are within (`cases`, a query of case ids, or None for
    every case)."""

    ours: Job
    others: Job
    cases: Job | None = None

    @classmethod
    def of(cls, unit: Unit | None) -> Records:
        if unit is None:
            return cls(("TRUE", []), ("TRUE", []))
        ours, params = unit.records("d")
        marks = ", ".join("?" for _ in unit.roles)
        others = f"d.role_T IN ({marks}) AND NOT coalesce(({ours}), FALSE)"
        return cls((ours, params), (others, [*unit.roles, *params]), unit.cases())

    def select(self, whose: Job, joined: str = "", columns: str = "d.case_id_T") -> Job:
        """SQL: `SELECT columns FROM explorer_drug_T d ... WHERE` the records `whose` names, within
        the cases, ready for one more condition."""
        sql, params = whose
        within, more = ("", [])
        if self.cases:
            within, more = f"d.case_id_T IN ({self.cases[0]}) AND ", self.cases[1]
        return (
            f"SELECT {columns} FROM explorer_drug_T d{joined} WHERE {within}({sql}) AND ",
            [*more, *params],
        )


def _picked(gives: Job, expr: str, chosen: tuple[str, ...], match: Job | None = None) -> Job:
    """SQL over case c: one of `gives`'s records (a select ready for a condition) holds `expr`
    among the chosen values, or with NOT_GIVEN none gives it; `match` replaces the IN test."""
    sql, params = gives
    either, values = [], []
    codes = [v for v in chosen if v != NOT_GIVEN]
    if codes:
        test, more = match or (f"{expr} IN (SELECT unnest(?::VARCHAR[]))", [codes])
        either.append(f"c.case_id_T IN ({sql}{test})")
        values += [*params, *more]
    if NOT_GIVEN in chosen:
        either.append(f"c.case_id_T NOT IN ({sql}{expr} IS NOT NULL)")
        values += params
    return "(" + " OR ".join(either) + ")", values


def _first(records: Records, expr: str, chosen: tuple[str, ...], match: Job, joined: str) -> Job:
    """SQL over case c: the first of the product's records giving `expr` holds a chosen value
    (`match`, over `v`), or with NOT_GIVEN none gives it."""
    either, values = [], []
    if any(v != NOT_GIVEN for v in chosen):
        sql, params = records.select(records.ours, joined, f"d.case_id_T, {expr} AS v")
        first = (
            f"SELECT case_id_T FROM ({sql}{expr} IS NOT NULL QUALIFY row_number() OVER "
            f"(PARTITION BY d.case_id_T ORDER BY {FIRST.format(d='d')}) = 1) WHERE {match[0]}"
        )
        either.append(f"c.case_id_T IN ({first})")
        values += [*params, drugs.roles(), *match[1]]
    if NOT_GIVEN in chosen:
        sql, params = records.select(records.ours, joined)
        either.append(f"c.case_id_T NOT IN ({sql}{expr} IS NOT NULL)")
        values += params
    return "(" + " OR ".join(either) + ")", values


def _days(chosen: tuple[str, ...]) -> Job:
    """SQL over `v`, days: within one of the chosen ranges, both ends included."""
    parts: list[str] = []
    params: list[Any] = []
    for span in (c for c in chosen if c != NOT_GIVEN):
        low, high = onset_span(span)
        ends = [("v >= ?", low), ("v <= ?", high)]
        parts.append("(" + " AND ".join(sql for sql, end in ends if end is not None) + ")")
        params += [end for _, end in ends if end is not None]
    return " OR ".join(parts) or "FALSE", params


def where(filters: Filters, records: Records, reactions: Reactions) -> list[Job]:
    """The conditions over `explorer_case_T c` of the filters on drug records and the report."""
    out: list[Job] = []
    for chosen, (field, column) in (
        (filters.doses, WRITTEN["dose"]),
        (filters.routes, WRITTEN["route"]),
        (filters.dose_forms, WRITTEN["dose_form"]),
        (filters.lots, WRITTEN["lot"]),
    ):
        if chosen:
            out.append(_picked(records.select(records.ours), written(field, column), chosen))
    if filters.indications:
        joined = (
            " JOIN explorer_indi_T i ON i.case_id_T = d.case_id_T AND i.indi_drug_seq = d.drug_seq"
        )
        text = INDICATION.format(i="i")
        texts = list(filters.indication_texts or ())
        match = (f"{text} IN (SELECT unnest(?::VARCHAR[]))", [texts])
        given = f"CASE WHEN {indication_given()} THEN {text} END"
        out.append(_picked(records.select(records.ours, joined), given, filters.indications, match))
    if filters.onsets:
        out.append(_first(records, "d.time_to_onset_T", filters.onsets, _days(filters.onsets), ""))
    case_of = " JOIN explorer_case_T q USING (case_id_T)"  # the quarter rechal is read by
    for chosen, expr, joined in (
        (filters.dechals, code("dechal", "d.dechal"), ""),
        (filters.rechals, code("rechal", "d.rechal", quarter="q.quarter_T"), case_of),
    ):
        if chosen:
            codes = [c for c in chosen if c != NOT_GIVEN]
            match = ("v IN (SELECT unnest(?::VARCHAR[]))", [codes])
            out.append(_first(records, expr, chosen, match, joined))
    if filters.other_drugs:
        other = OTHER.format(d="d")
        named = [c.lower() for c in filters.other_drugs if c != NOT_GIVEN]
        match = (f"lower({other}) IN (SELECT unnest(?::VARCHAR[]))", [named])
        out.append(_picked(records.select(records.others), other, filters.other_drugs, match))
    if filters.report_types:
        rept = code("rept_cod", "c.rept_cod")
        codes = [c for c in filters.report_types if c != NOT_GIVEN]
        either = [f"{rept} IN (SELECT unnest(?::VARCHAR[]))"] if codes else []
        either += [f"{rept} IS NULL"] if NOT_GIVEN in filters.report_types else []
        out.append(("(" + " OR ".join(either) + ")", [codes] if codes else []))
    if filters.other_reactions:
        out.append(
            (
                "c.case_id_T IN (SELECT case_id_T FROM explorer_reac_term_T "
                "WHERE term_T IN (SELECT unnest(?::VARCHAR[])))",
                [reactions.texts(filters.other_reactions)],
            )
        )
    return out


__all__ = [
    "FIRST",
    "INDICATION",
    "OTHER",
    "Records",
    "WRITTEN",
    "code",
    "indication_given",
    "indication_keyer",
    "resolved",
    "where",
    "written",
]
