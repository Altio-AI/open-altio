"""The filters on a case's drug records and its report counted a second way, for recount.py: the
cases each keeps, read from the release's own tables apart from recordfilters.py.

    conditions(asked, values, ours, others, meddra)   each condition over case c

`ours` is the condition on a drug record (`d`, drug_latest_T, with its ingredients `s`,
drug_substance_T) that it is one the question counts, `others` that it is another drug's. A
field FDA writes once a record (time to onset, dechallenge, rechallenge) is the first record
giving it, by role in the order of rule explorer-drug-counts, then by FDA's drug sequence. An
indication counts under today's PT where `meddra` (MedDRA's licensed `indi_meddra_T` and
`meddra_pt`), else as FDA wrote it, whatever its capitals and spaces. Each value is a named
parameter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from open_altio.faers import not_given
from open_altio.faers.explorer_db import reaction_key
from open_altio.faers.meddra.terms import key_sql

from .drugs import roles
from .filters import NOT_GIVEN
from .recountquery import RECORD, Asked, days

if TYPE_CHECKING:
    from .recount import Values

CASE = "d.era_T, d.primaryid, d.quarter_T"  # a record's case
# the fields a drug record gives in words: each filter's parameter, FDA's field and its column
FIELDS = {
    "dose": ("dose_vbm", "d.dose_vbm"),
    "route": ("route", "d.route"),
    "dose_form": ("dose_form", "d.dose_form"),
    "lot": ("lot_num", "d.lot_num"),
}
# the filters that read the records the question counts
OURS = ("dose", "route", "dose_form", "lot", "indication", "onset", "dechal", "rechal")
RECORDS = "FROM drug_latest_T d JOIN drug_substance_T s ON " + " AND ".join(
    f"s.{k} = d.{k}" for k in RECORD
)
ONSET = " LEFT JOIN drug_onset_T o ON " + " AND ".join(f"o.{k} = d.{k}" for k in RECORD)
INDICATIONS = (
    " JOIN indi_latest_T i ON i.era_T = d.era_T AND i.primaryid = d.primaryid "
    "AND i.quarter_T = d.quarter_T AND i.indi_drug_seq = d.drug_seq"
)
TODAYS_PT = (
    " LEFT JOIN indi_meddra_T m ON m.indi_term_T = {key} LEFT JOIN meddra_pt p "
    "ON p.pt_code = m.pt_code_T"
)


def _in(cases: str) -> str:
    return f"(c.era_T, c.primaryid, c.quarter_T) IN ({cases})"


def _gives(whose: str, expr: str, joined: str = "") -> str:
    return f"SELECT {CASE} {RECORDS}{joined} WHERE {whose} AND {expr}"


def _any(whose: str, expr: str, chosen: tuple[str, ...], v: Values, joined: str = "") -> str:
    """One of the records holds `expr` among the chosen; with NOT_GIVEN, none gives it."""
    codes = [c for c in chosen if c != NOT_GIVEN]
    either = [_in(_gives(whose, v.among(expr, codes), joined))] if codes else []
    if NOT_GIVEN in chosen:
        either.append(f"NOT {_in(_gives(whose, f'{expr} IS NOT NULL', joined))}")
    return "(" + " OR ".join(either) + ")"


def _first(
    ours: str, expr: str, chosen: tuple[str, ...], match: str, v: Values, joined: str = ""
) -> str:
    """The first record giving `expr` holds a chosen value (`match`, over x); with NOT_GIVEN,
    none gives it."""
    either = []
    if any(c != NOT_GIVEN for c in chosen):
        order = ", ".join(v.one(r) for r in roles())
        first = (
            f"SELECT era_T, primaryid, quarter_T FROM (SELECT {CASE}, {expr} AS x "
            f"{RECORDS}{joined} WHERE {ours} AND {expr} IS NOT NULL QUALIFY row_number() OVER "
            f"(PARTITION BY {CASE} ORDER BY list_position([{order}], "
            "nullif(upper(trim(d.role_cod)), '')), try_cast(d.drug_seq AS BIGINT), d.drug_seq) "
            f"= 1) WHERE {match}"
        )
        either.append(_in(first))
    if NOT_GIVEN in chosen:
        either.append(f"NOT {_in(_gives(ours, f'{expr} IS NOT NULL', joined))}")
    return "(" + " OR ".join(either) + ")"


def _within(chosen: tuple[str, ...], v: Values) -> str:
    """SQL over x, days: within one of the chosen ranges, both ends included."""
    parts = []
    for low, high in (days(c) for c in chosen if c != NOT_GIVEN):  # type: ignore[misc]
        ends = [f"x >= CAST({v.one(str(low))} AS BIGINT)"] if low is not None else []
        ends += [f"x <= CAST({v.one(str(high))} AS BIGINT)"] if high is not None else []
        parts.append("(" + " AND ".join(ends) + ")")
    return " OR ".join(parts) or "FALSE"


def _code(field: str, column: str, **context: str) -> str:
    return f"upper(trim({not_given.given(field, column, **context)}))"


def _written(field: str, column: str) -> str:
    given = not_given.given(field, column)
    return f"upper(regexp_replace(trim({given}), '[[:space:]]+', ' ', 'g'))"


def conditions(asked: Asked, v: Values, ours: str, others: str, meddra: bool) -> list[str]:
    chosen, out = asked.records, []
    for name, (field, column) in FIELDS.items():
        if chosen[name]:
            out.append(_any(ours, _written(field, column), chosen[name], v))
    if chosen["indication"]:
        text = "trim(i.indi_pt)"
        key = reaction_key(text)
        joined = INDICATIONS
        if meddra:
            joined += TODAYS_PT.format(key=key_sql("indi_pt", text))
            key = f"coalesce(lower(p.pt_name), {key})"
        expr = f"CASE WHEN {not_given.given('indi_pt', 'i.indi_pt')} IS NOT NULL THEN {key} END"
        out.append(_any(ours, expr, chosen["indication"], v, joined))
    if chosen["onset"]:
        within = _within(chosen["onset"], v)
        out.append(_first(ours, "o.time_to_onset_T", chosen["onset"], within, v, ONSET))
    for name, expr in (
        ("dechal", _code("dechal", "d.dechal")),
        ("rechal", _code("rechal", "d.rechal", quarter="d.quarter_T")),
    ):
        if chosen[name]:
            codes = [c for c in chosen[name] if c != NOT_GIVEN]
            out.append(_first(ours, expr, chosen[name], v.among("x", codes), v))
    if chosen["other_drug"]:
        other = "lower(coalesce(s.substance_T, d.drugname_norm_T))"
        out.append(_any(others, other, chosen["other_drug"], v))
    if picked := chosen["report_type"]:
        rept = _code("rept_cod", "c.rept_cod")
        codes = [c for c in picked if c != NOT_GIVEN]
        either = [v.among(rept, codes)] if codes else []
        either += [f"{rept} IS NULL"] if NOT_GIVEN in picked else []
        out.append("(" + " OR ".join(either) + ")")
    if keys := chosen["other_reaction"]:
        matched = f"{v.among('r.text_T', keys)} OR {v.among('r.pt_T', keys)}"
        out.append(
            _in(f"SELECT r.era_T, r.primaryid, r.quarter_T FROM reac_keyed r WHERE {matched}")
        )
    return out


def counted_by(by: str, ours: str) -> str:
    """SQL: each value `ours` records give a field written in words, for a count by it, with the
    case's key, as its filter reads it."""
    field, column = FIELDS[by]
    expr = _written(field, column)
    return f"SELECT DISTINCT {CASE}, {expr} AS value {RECORDS} WHERE {ours} AND {expr} IS NOT NULL"


__all__ = ["FIELDS", "OURS", "conditions", "counted_by"]
