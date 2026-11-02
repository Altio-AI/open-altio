"""A counted question (/api/count): the cases a question asks for, counted by one field (rule
counted-question), each value with the case list's question for exactly its cases
(answers.cases_query), so the cases behind any number can be listed.

    count(data, query)   the filters, a product as explore.product_unit reads it, and `by`

It answers the question exactly as asked (`question`), in plain words (`described`), the field
counted by (`by`), `counts` as [[value, cases, cases_query]], the question's cases (`total`),
each count checked by a second, separate count (`check`, recount.py), and that count as one
query to run in Tables and SQL (`sql`), or null with the reason in `why`.
A value is the one its field's filter takes, `_none` for Not given, so that filter picks its
cases. A case with no day it is dated by, or naming no reaction, counts in a row of its own whose
value and cases_query are null, as no filter picks it. No value from the query is put into SQL
text the explorer runs; `sql` holds each as a quoted constant, for a person to run.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from open_altio.faers.dates import received_day
from open_altio.rulebook import value

from . import recordfilters, recount
from .answers import Problem, cases_query
from .described import described
from .explore import Data, Query, Scope, days_query, scope, value_of
from .filters import CASE_FIELDS, NOT_GIVEN, OUTCOMES_GIVEN

RULE = "counted-question"
# each count by time: its value's SQL over the day a case is dated by (rule received-day)
TIMES = {
    "year": "year(c.{day})",
    "quarter": "strftime(c.{day}, '%Y') || 'q' || quarter(c.{day})",
    "month": "strftime(c.{day}, '%Y-%m')",
}
OUTCOME_FILTERED = (
    "A case can give several outcomes, so a count by outcome takes no outcome filter: "
    "leave it out, or count by another field."
)
# why there is no query to run behind the counts
LICENSED = (
    "The query behind these counts reads today's preferred terms from MedDRA's licensed part, "
    "which is not open to you here."
)
RECORD_FILTERED = (
    "A case's drug records can give several values of a field, so a count by {by} takes no {by} "
    "filter: leave it out, or count by another field."
)
NOT_COUNTED_AGAIN = "These counts are not counted a second way, so there is no query behind them."


def choices() -> list[str]:
    """What a question may count by (rule counted-question)."""
    return list(value(RULE, "by"))


def _days(by: str, found: Any) -> tuple[date, date]:
    """The first and last day of a year (2026), a quarter (2026q2) or a month (2026-04)."""
    if by == "year":
        return date(found, 1, 1), date(found, 12, 31)
    year = int(found[:4])
    first = (int(found[-1]) - 1) * 3 + 1 if by == "quarter" else int(found[5:])
    last = first + 2 if by == "quarter" else first
    return date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1])


def _rows(data: Data, query: Query, asked: Scope, by: str) -> list[list[Any]]:
    """[value, cases, cases_query] for each value the question's cases give `by`."""
    sql, params = asked.where()
    if by in TIMES:
        found = data.rows(
            f"SELECT {TIMES[by].format(day=received_day())} AS k, count(*) AS n "
            f"FROM explorer_case_T c WHERE {sql} GROUP BY 1",
            params,
        )
        dated = sorted(r["k"] for r in found if r["k"] is not None)
        n = {r["k"]: r["n"] for r in found}
        rows = [[k, n[k], days_query(*_days(by, k), asked.filters, query, "by")] for k in dated]
        return rows + ([[None, n[None], None]] if None in n else [])
    if by == "event":
        reacs, reac_params = data.reactions.keyed()
        found = data.rows(
            f"SELECT r.k, count(DISTINCT r.case_id_T) AS n FROM {reacs} r WHERE r.case_id_T IN "
            f"(SELECT c.case_id_T FROM explorer_case_T c WHERE {sql}) GROUP BY 1",
            reac_params + params,
        )
        named = [
            [data.pt_name(r["k"]), r["n"], cases_query(query, "by", event=[r["k"]])] for r in found
        ]
        none = data.rows(
            f"SELECT count(*) AS n FROM explorer_case_T c WHERE {sql} "
            f"AND c.case_id_T NOT IN (SELECT r.case_id_T FROM {reacs} r)",
            params + reac_params,
        )[0]["n"]
        return _by_cases(named) + ([[None, none, None]] if none else [])
    if by in recordfilters.WRITTEN:
        return _record_rows(data, query, asked, by)
    if by == "outcome":
        if asked.filters.outcomes:
            raise Problem(400, OUTCOME_FILTERED)
        found = data.rows(
            f"SELECT o AS k, count(DISTINCT id) AS n FROM (SELECT c.case_id_T AS id, "
            f"unnest({OUTCOMES_GIVEN}) AS o FROM explorer_case_T c WHERE {sql}) GROUP BY 1",
            params,
        )
    else:
        found = data.rows(
            f"SELECT coalesce({CASE_FIELDS[by]}, '{NOT_GIVEN}') AS k, count(*) AS n "
            f"FROM explorer_case_T c WHERE {sql} GROUP BY 1",
            params,
        )
    return _by_cases([[r["k"], r["n"], cases_query(query, "by", **{by: [r["k"]]})] for r in found])


def _record_rows(data: Data, query: Query, asked: Scope, by: str) -> list[list[Any]]:
    """Each value the question's counted drug records give `by`, as its filter reads it, each case
    once under each; `_none` for a case whose records give none."""
    if query.get(by):
        raise Problem(400, RECORD_FILTERED.format(by=by))
    sql, params = asked.where()
    expr = recordfilters.written(*recordfilters.WRITTEN[by])
    records = recordfilters.Records.of(asked.product)
    giving, more = records.select(records.ours, columns=f"d.case_id_T, {expr} AS k")
    found = data.rows(
        f"SELECT k, count(DISTINCT case_id_T) AS n FROM ({giving}{expr} IS NOT NULL) "
        f"WHERE case_id_T IN (SELECT c.case_id_T FROM explorer_case_T c WHERE {sql}) GROUP BY 1",
        more + params,
    )
    gives, more = records.select(records.ours)
    none = data.rows(
        f"SELECT count(*) AS n FROM explorer_case_T c WHERE {sql} "
        f"AND c.case_id_T NOT IN ({gives}{expr} IS NOT NULL)",
        params + more,
    )[0]["n"]
    rows = [(r["k"], r["n"]) for r in found] + ([(NOT_GIVEN, none)] if none else [])
    return _by_cases([[k, n, cases_query(query, "by", **{by: [k]})] for k, n in rows])


def _by_cases(rows: list[list[Any]]) -> list[list[Any]]:
    """Most cases first, then by value: one order, so the same question answers the same."""
    return sorted(rows, key=lambda r: (-r[1], str(r[0])))


def _query(data: Data, second: recount.Recount | None) -> dict[str, Any]:
    """The second count as a query to run (`sql`), or null with why: no second count, or one
    reading MedDRA's licensed part for a viewer who may not see it."""
    if second is None:
        return {"sql": None, "why": {"sql": NOT_COUNTED_AGAIN}}
    if second.statement.licensed and data.meddra is None:
        return {"sql": None, "why": {"sql": LICENSED}}
    return {"sql": recount.sql_of(second.statement), "why": {}}


def count(data: Data, query: Query) -> dict[str, Any]:
    """The question's cases counted by `by`, each value with its cases' question, checked by a
    second count, and that count as a query; 400 naming the choices for a `by` that is not one
    of them."""
    by = value_of(query, "by").strip()
    if by not in choices():
        raise Problem(400, f"Count by one of: {', '.join(choices())}.")
    asked = scope(data, query)
    sql, params = asked.where()
    total = data.rows(f"SELECT count(*) AS n FROM explorer_case_T c WHERE {sql}", params)[0]["n"]
    first = {
        "question": {name: list(query[name]) for name in sorted(query)},
        "described": [f"Counted by: {by}", *described(data, query, asked)],
        "by": by,
        "counts": _rows(data, query, asked, by),
        "total": total,
    }
    unread = recount.unread(query)
    second = None if unread else recount.recount(data.opened, query, data.reactions.version)
    return first | {"check": recount.check(first, second, unread)} | _query(data, second)


__all__ = ["choices", "count"]
