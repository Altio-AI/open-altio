"""Statistics for a group of reactions counted as one event, and on the cases received since a
day: a drug's ingredient against the group, on the cases the release's statistics count (rule
statistics-cases: kept, naming an ingredient of a suspect drug and a reaction), within the same
strata, scored by the build's own maths under the release's own fitted prior
(faers.statistics.scored.score_with), never fitted again. A case counts once for the group
however many of its reactions it names. Given one reaction and no day, the answer is that pair's
own statistics as the build worked them out (statistics_T).

    statistics(data, query)   `product` names the drug, `reaction` each reaction of the group
                              (repeated), `received_from` (yyyy-mm-dd) the window's first day

A window counts only the cases whose received day (rule received-day) is that day or later: they
are the whole table, their strata the same parts, the prior still the release's. A case with no
received day is in no window. Everything is counted on the explorer's database; the counted
cases in each stratum are counted once per release and window. No value from the query is put
into SQL text.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

import numpy as np

from open_altio import rulebook
from open_altio.faers.dates import received_day
from open_altio.faers.statistics.cases import RULE, explorer_counted, roles_sql, stratum_parts
from open_altio.faers.statistics.scored import SCORED, Cells, release_prior, score_with

from .answers import Problem
from .eventstats import ingredient_of, not_available
from .explore import Data, Query, value_of
from .statistics import given

DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
Stratum = tuple[str, ...]


def _since(query: Query) -> date | None:
    """The window's first day (`received_from`), or None for every counted case."""
    text = value_of(query, "received_from").strip()
    if not text:
        return None
    try:
        if not DAY.fullmatch(text):
            raise ValueError(text)
        return date.fromisoformat(text)
    except ValueError:
        raise Problem(400, "Write the received day as yyyy-mm-dd, such as 2026-03-12.") from None


def _parts() -> str:
    """The stratum's parts over the explorer's case table, in the rule's order, as s0, s1, ..."""
    known = stratum_parts("c")
    return ", ".join(f"{known[p]} AS s{i}" for i, p in enumerate(rulebook.value(RULE, "strata")))


def _stratum(row: dict[str, Any]) -> Stratum:
    return tuple(str(row[f"s{i}"]) for i in range(len(rulebook.value(RULE, "strata"))))


def _window(since: date | None) -> tuple[str, list[Any]]:
    """The window's condition over the explorer's case table, and its parameters."""
    if since is None:
        return "", []
    return f" AND c.{received_day()} >= ?::DATE", [since]


# The counted cases in each stratum.
STRATA = """
SELECT {parts}, count(*) AS n FROM explorer_case_T c
WHERE {counted}{window}
GROUP BY ALL ORDER BY ALL
"""

# In each stratum, the counted cases naming the ingredient (i), those naming any of FDA's texts
# the group counts (g), and those naming both, each case once.
CELLS = """
WITH i AS (
  SELECT DISTINCT case_id_T FROM explorer_ingredient_T
  WHERE ingredient_T = ? AND role_T IN ({roles})),
g AS (
  SELECT DISTINCT case_id_T FROM explorer_reac_term_T
  WHERE term_T IN (SELECT unnest(?::VARCHAR[]))),
k AS (
  SELECT {parts}, c.case_id_T IN (SELECT case_id_T FROM i) AS hi,
    c.case_id_T IN (SELECT case_id_T FROM g) AS hg
  FROM explorer_case_T c
  WHERE (c.case_id_T IN (SELECT case_id_T FROM i) OR c.case_id_T IN (SELECT case_id_T FROM g))
    AND {counted}{window})
SELECT * EXCLUDE (hi, hg), count(*) FILTER (WHERE hi) AS ingredient,
  count(*) FILTER (WHERE hg) AS reaction, count(*) FILTER (WHERE hi AND hg) AS cases
FROM k GROUP BY ALL
"""


def _strata(data: Data, since: date | None) -> dict[Stratum, int]:
    """The counted cases in each stratum, of the whole release or of the window, in the strata's
    order; counted once per release and window."""

    def make() -> dict[Stratum, int]:
        window, params = _window(since)
        sql = STRATA.format(parts=_parts(), counted=explorer_counted("c"), window=window)
        return {_stratum(r): r["n"] for r in data.rows(sql, params)}

    if since is None:
        return data.facts.once("group_statistics_strata", make)
    return data.facts.remember(f"group_statistics_strata|{since.isoformat()}", make)


def _cells(data: Data, drug: str, texts: list[str], since: date | None) -> list[dict[str, Any]]:
    """CELLS for the ingredient and FDA's texts the group counts."""
    window, params = _window(since)
    sql = CELLS.format(
        roles=roles_sql(), parts=_parts(), counted=explorer_counted("c"), window=window
    )
    return data.rows(sql, [drug, texts, *params])


def _plain(value: Any) -> Any:
    """A number as JSON gives it: a whole number as one, a value the table cannot give as None."""
    if isinstance(value, np.integer):
        return int(value)
    number = float(value)
    return None if math.isnan(number) else number


def statistics(data: Data, query: Query) -> dict[str, Any]:
    """The drug's ingredient (`product`) against the group (`reaction`, repeated), on every
    counted case or on those received since `received_from`: the cases naming both (`cases`),
    the ingredient's and the group's (`ingredient_cases`, `reaction_cases`), every case counted
    (`counted`), and each statistic of the release's, empty where the table cannot give it, with
    why where the release cannot (`not_available`)."""
    entry = given(data)
    if not entry["present"]:
        raise Problem(404, entry["reason"])
    drug = ingredient_of(data, query)
    keys = sorted({k for k in map(data.reactions.key, query.get("reaction", [])) if k})
    if not keys:
        raise Problem(400, "Name the group's reactions as reaction, one or more.")
    since = _since(query)
    totals = _strata(data, since)
    found = {_stratum(r): r for r in _cells(data, drug, data.reactions.texts(keys), since)}
    order = list(totals)
    cells = Cells(
        cases=np.array([sum(r["cases"] for r in found.values())]),
        ingredient=np.array([[found[s]["ingredient"] if s in found else 0 for s in order]]),
        reaction=np.array([[found[s]["reaction"] if s in found else 0 for s in order]]),
        strata=np.array([[totals[s] for s in order]]),
    )
    scores = score_with(release_prior(entry), cells)
    return {
        "ingredient": drug,
        "reactions": [data.pt_name(k) or k for k in keys],
        "received_from": since,
        "counted": sum(totals.values()),
        **{name: _plain(scores[name][0]) for name in SCORED},
        "not_available": not_available(entry),
    }


__all__ = ["statistics"]
