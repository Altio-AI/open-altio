"""Which quarter a case is placed in, for each statistic at the end of every quarter
(quarterly.py). By the date FDA received it (`received`, rule received-day), the release's quarter
tables hold the running sums. By the date the reaction started (`event`, `event_dt_T`, FDA's full
dates only, as the event date filter reads it), nothing in the release is summed that way, so every
margin is counted here on the explorer's database, each case once; a case with no such date is at
no quarter end, and each event says how many of its cases that leaves out (`undated`). The
statistics' cases, strata and prior are the same either way. No value from the query is put into
SQL text.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from open_altio import rulebook
from open_altio.faers.dates import received_quarter
from open_altio.faers.statistics.cases import RULE, explorer_counted, roles_sql

from .answers import Problem
from .explore import Data, Query, value_of
from .grouped import Stratum, _parts

BY = ("received", "event")
EVENT_DAY = "c.event_dt_T"


def by_of(query: Query) -> str:
    """The date a quarter end counts by, as asked (`by`), FDA's receipt when not given."""
    by = value_of(query, "by", BY[0]).strip() or BY[0]
    if by not in BY:
        raise Problem(400, f"Count the statistics at each quarter end by {' or '.join(BY)}.")
    return by


def placed(by: str) -> str:
    """SQL: the quarter, yyyyq, a case of the explorer's case table `c` is placed in."""
    if by == "event":
        return f"year({EVENT_DAY}) * 10 + quarter({EVENT_DAY})"
    return received_quarter("c")


def dated(by: str) -> str:
    """SQL to add to a WHERE: only the cases that have a quarter by that date."""
    return f" AND {EVENT_DAY} IS NOT NULL" if by == "event" else ""


def quarter_index(qnum: Any) -> Any:
    """A quarter (yyyyq) as a count of quarters, so consecutive quarters are one apart."""
    return (qnum // 10) * 4 + qnum % 10 - 1


def strata_of(rows: list[dict[str, Any]]) -> list[Stratum]:
    """Each row's stratum, from its parts s0, s1, ... (grouped._parts), the rule read once."""
    size = len(rulebook.value(RULE, "strata"))
    return [tuple(str(r[f"s{i}"]) for i in range(size)) for r in rows]


def running_totals(
    data: Data, found: list[dict[str, Any]]
) -> tuple[np.ndarray, dict[Stratum, int], np.ndarray]:
    """From `found`, the cases added in each quarter (`q`) and stratum (`n`): every quarter end,
    oldest first, from the first quarter with a case to the release's newest, each calendar
    quarter once; the strata, numbered; and every case by each quarter end (quarters by strata)."""
    newest = data.opened.manifest["quarters"][-1]
    newest_q = int(newest[:4]) * 10 + int(newest[-1])
    last = max([newest_q, *(r["q"] for r in found)])
    first = min((r["q"] for r in found), default=newest_q)
    quarters = np.arange(quarter_index(first), quarter_index(last) + 1)
    strata = strata_of(found)
    numbered = {s: i for i, s in enumerate(sorted(set(strata)))}
    added = np.zeros((len(quarters), len(numbered)), dtype=np.int64)
    for r, stratum in zip(found, strata, strict=True):
        added[quarter_index(r["q"]) - quarters[0], numbered[stratum]] += r["n"]
    qnums = (quarters // 4) * 10 + quarters % 4 + 1
    return qnums, numbered, np.cumsum(added, axis=0)


def event_totals(data: Data) -> tuple[np.ndarray, dict[Stratum, int], np.ndarray]:
    """running_totals by the date the reaction started, worked out once per release."""

    def make() -> tuple[np.ndarray, dict[Stratum, int], np.ndarray]:
        found = data.rows(
            f"SELECT {placed('event')} AS q, {_parts()}, count(*) AS n FROM explorer_case_T c "
            f"WHERE {explorer_counted('c')}{dated('event')} GROUP BY ALL"
        )
        return running_totals(data, found)

    return data.facts.once("quarter_statistics_totals_by_event", make)


def event_reaction_cases(
    data: Data, keys: list[str], columns: list[Stratum], t0: int
) -> tuple[np.ndarray, ...]:
    """Each event's cases (`keys`) added in each quarter by the date the reaction started, within
    each of the drug's strata (`columns`) and in the rest together (the last column): event,
    quarter, column and cases, as four arrays in quarter order."""
    size = len(rulebook.value(RULE, "strata"))
    held = ", ".join(f"unnest(?::VARCHAR[]) AS s{i}" for i in range(size))
    on = " AND ".join(f"k.s{i} = s.s{i}" for i in range(size))
    reacs, reac_params = data.reactions.keyed()
    sql = (
        f"WITH s AS (SELECT {held}, unnest(?::INTEGER[]) AS col), "
        "e AS (SELECT unnest(?::VARCHAR[]) AS k, unnest(?::INTEGER[]) AS j), "
        f"r AS (SELECT DISTINCT case_id_T, e.j FROM {reacs} n JOIN e USING (k)), "
        f"k AS (SELECT c.case_id_T, {placed('event')} AS q, {_parts()} FROM explorer_case_T c "
        f"WHERE {explorer_counted('c')}{dated('event')}) "
        "SELECT r.j, k.q, coalesce(s.col, ?) AS col, count(*)::BIGINT AS n "
        f"FROM r JOIN k USING (case_id_T) LEFT JOIN s ON {on} GROUP BY ALL ORDER BY q"
    )
    params = [
        *([s[i] for s in columns] for i in range(size)),
        list(range(len(columns))),
        [k.lower() for k in keys],
        list(range(len(keys))),
        *reac_params,
        len(columns),
    ]
    cur = data.opened.cursor()
    try:
        got = cur.execute(sql, params).fetchnumpy()
    finally:
        cur.close()
    j, q, col, n = (np.asarray(got[c], dtype=np.int64) for c in ("j", "q", "col", "n"))
    return j, quarter_index(q) - t0, col, n


def undated(data: Data, drug: str, keys: list[str] | None) -> dict[str, int]:
    """The drug's counted cases with no date the reaction started, by each event's key lowered;
    with `keys` (a group's), all of them together under the key "".
    """
    reacs, params = data.reactions.keyed(keys)
    key = "''" if keys else "r.k"
    return {
        r["k"]: r["n"]
        for r in data.rows(
            f"SELECT {key} AS k, count(DISTINCT r.case_id_T) AS n FROM {reacs} r "
            "JOIN explorer_case_T c USING (case_id_T) "
            f"WHERE {explorer_counted('c')} AND {EVENT_DAY} IS NULL AND c.case_id_T IN "
            "(SELECT case_id_T FROM explorer_ingredient_T WHERE ingredient_T = ? "
            f"AND role_T IN ({roles_sql()})) GROUP BY 1",
            [*params, drug],
        )
    }


__all__ = [
    "BY",
    "by_of",
    "dated",
    "event_reaction_cases",
    "event_totals",
    "placed",
    "quarter_index",
    "running_totals",
    "strata_of",
    "undated",
]
