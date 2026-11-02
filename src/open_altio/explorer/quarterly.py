"""Each statistic as it stood at the end of every quarter, for a drug's events: how a pair's
numbers grew, when they passed a screen and stayed past it, and whether they are rising.

    series(data, query)    `product` names the drug: every event of its statistics, or one
                           group of reactions counted as one (`reaction`, repeated); optionally
                           screens (`screen`, repeated, each a JSON list of conditions) and the
                           statistic whose trend is read (`rising`); `by=event` places each
                           case by the date the reaction started (quarterplace.py)
    prior_quarter(data, query)   each event's EBGM and EB05 at the end of the quarter before the
                           newest, scored for that quarter end alone
    since(quarters, past)  the first quarter of the unbroken stretch of quarter ends, up to the
                           newest, at which a pair was past a screen; None when it is not past

At each quarter end the table of cases is the cases rule statistics-cases counts that were
received by then, each placed in the quarter of its received day (rule received-day), within
the same strata. Every case counted and each reaction's cases are running sums of the
release's quarter tables (faers.statistics.quarterly); the drug's own cases, and a group's, are
counted on the explorer's database, each case once. Each quarter end is scored with the
build's own maths under the release's own fitted prior (faers.statistics.scored.score_with),
never fitted again, so the newest quarter end is the pair's own statistics. A pair's series
starts at the first quarter end with a case of it and runs through every calendar quarter to
the release's newest. No value from the query is put into SQL text.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from open_altio import rulebook
from open_altio.faers.explorer_db import explorer_statistics
from open_altio.faers.statistics.cases import RULE, explorer_counted, roles_sql
from open_altio.faers.statistics.scored import Cells, release_prior, score_with
from open_altio.faers.statistics.step import suffixed
from open_altio.stats import ebgm, screen, trend

from .answers import Problem
from .eventstats import ingredient_of, not_available
from .explore import Data, Query, value_of
from .grouped import CELLS, Stratum, _parts
from .quarterplace import (
    by_of,
    dated,
    event_reaction_cases,
    event_totals,
    placed,
    quarter_index,
    running_totals,
    strata_of,
    undated,
)
from .statistics import given

# Each quarter end's statistics, after its quarter (qnum, yyyyq): those the usual screens read.
SERIES = ("cases", "ebgm", "eb05", "prr", "chi_square_yates", "ror", "ror_lower", "ic025")
COLUMNS = ("qnum", *SERIES)
BEFORE = (
    "This release was built before Open Altio counted its cases by quarter. Build it again to "
    "see its statistics at the end of every quarter."
)
# Scored together while the tables of the quarter ends waiting hold fewer cells than this, so a
# drug with thousands of events over a hundred quarters is held a slice at a time.
CELLS_AT_ONCE = 1 << 22


def _table(data: Data, name: str) -> str:
    """The path of one of the release's Parquet tables."""
    return str(Path(data.opened.folder) / data.opened.manifest["tables"][name]["path"])


def _reaction_table(data: Data) -> str:
    """The release's table of each reaction's cases by quarter and stratum that this viewer is
    given: by current PT where their reactions are named so, else by FDA's text."""
    entry = data.opened.manifest.get("quarter_statistics") or {"present": False, "reason": BEFORE}
    if not entry["present"]:
        raise Problem(404, entry["reason"])
    if data.reactions.version is None and entry["reaction_key"] != "fda_text":
        entry = entry.get("as_published") or {"reaction_table": None}
    if entry["reaction_table"] is None:
        raise Problem(404, BEFORE)
    return _table(data, entry["reaction_table"])


def _totals(data: Data) -> tuple[np.ndarray, dict[Stratum, int], np.ndarray]:
    """Every quarter end of the release, oldest first, from the first quarter a counted case is
    placed in to the release's newest, each calendar quarter once; the strata, numbered; and
    every case counted in each stratum by each quarter end (quarters by strata). Worked out
    once per release."""

    def make() -> tuple[np.ndarray, dict[Stratum, int], np.ndarray]:
        entry = data.opened.manifest["quarter_statistics"]
        parts = [suffixed(p) for p in rulebook.value(RULE, "strata")]
        named = ", ".join(f"{p} AS s{i}" for i, p in enumerate(parts))
        found = data.rows(
            f"SELECT {suffixed('qnum')} AS q, {named}, {suffixed('cases')} AS n "
            "FROM read_parquet(?)",
            [_table(data, entry["table"])],
        )
        return running_totals(data, found)

    return data.facts.once("quarter_statistics_totals", make)


def _cells(data: Data, drug: str, texts: list[str], by: str) -> list[dict[str, Any]]:
    """grouped.CELLS by the quarter each case is placed in as well as its stratum: the drug's
    counted cases, those naming any of FDA's `texts`, and those naming both."""
    sql = CELLS.format(
        roles=roles_sql(),
        parts=f"{placed(by)} AS q, {_parts()}",
        counted=explorer_counted("c"),
        window=dated(by),
    )
    return data.rows(sql, [drug, texts])


def _events(data: Data, entry: dict[str, Any], drug: str) -> list[tuple[str, str]]:
    """Each event of the drug's statistics, as /api/events/statistics names it: as a page shows
    it and as the statistics key it."""
    by_pt = entry.get("reaction_key") == "meddra_pt"
    return [
        (
            r["reaction_T"] if by_pt else data.pt_name(r["reaction_T"]) or r["reaction_T"],
            r["reaction_T"],
        )
        for r in data.rows(
            f"SELECT reaction_T FROM {explorer_statistics(entry['table'])} WHERE ingredient_T = ? "
            "ORDER BY reaction_T",
            [drug],
        )
    ]


def _pair_cases(data: Data, drug: str, keys: list[str], t0: int, size: int, by: str) -> np.ndarray:
    """The drug's counted cases naming each event (`keys`, as the statistics key them), added in
    each quarter (events by quarters)."""
    reacs, params = data.reactions.keyed()
    found = data.rows(
        f"WITH i AS (SELECT c.case_id_T, {placed(by)} AS q FROM explorer_case_T c "
        f"WHERE {explorer_counted('c')}{dated(by)} AND c.case_id_T IN (SELECT case_id_T FROM "
        f"explorer_ingredient_T WHERE ingredient_T = ? AND role_T IN ({roles_sql()}))) "
        f"SELECT r.k, i.q, count(DISTINCT r.case_id_T) AS n FROM {reacs} r JOIN i USING "
        "(case_id_T) GROUP BY 1, 2",
        [drug, *params],
    )
    event = {k.lower(): j for j, k in enumerate(keys)}
    added = np.zeros((len(keys), size), dtype=np.int64)
    for r in found:
        added[event[r["k"]], quarter_index(r["q"]) - t0] += r["n"]
    return added


def _reaction_cases(
    data: Data, keys: list[str], columns: list[Stratum], t0: int
) -> tuple[np.ndarray, ...]:
    """Each event's cases (`keys`) added in each quarter within each of the drug's strata
    (`columns`), and in the rest of the strata together (the last column), from the release's
    table: event, quarter, column and cases, as four arrays."""
    parts = [suffixed(p) for p in rulebook.value(RULE, "strata")]
    reaction, qnum, cases = (suffixed(c) for c in ("reaction", "qnum", "cases"))
    held = ", ".join(f"unnest(?::VARCHAR[]) AS s{i}" for i in range(len(parts)))
    on = " AND ".join(f"r.{p} = s.s{i}" for i, p in enumerate(parts))
    sql = (
        f"WITH s AS (SELECT {held}, unnest(?::INTEGER[]) AS col), "
        "e AS (SELECT unnest(?::VARCHAR[]) AS k, unnest(?::INTEGER[]) AS j) "
        f"SELECT e.j, r.{qnum} AS q, coalesce(s.col, ?) AS col, sum(r.{cases})::BIGINT AS n "
        f"FROM read_parquet(?) r JOIN e ON r.{reaction} = e.k LEFT JOIN s ON {on} "
        "GROUP BY ALL ORDER BY q"
    )
    params = [
        *([s[i] for s in columns] for i in range(len(parts))),
        list(range(len(columns))),
        keys,
        list(range(len(keys))),
        len(columns),
        _reaction_table(data),
    ]
    cur = data.opened.cursor()
    try:
        got = cur.execute(sql, params).fetchnumpy()
    finally:
        cur.close()
    j, q, col, n = (np.asarray(got[c], dtype=np.int64) for c in ("j", "q", "col", "n"))
    return j, quarter_index(q) - t0, col, n


def _scored(
    prior: ebgm.Prior | None,
    totals: np.ndarray,
    ingredient: np.ndarray,
    cases: np.ndarray,
    added: tuple[np.ndarray, ...],
    only: int | None = None,
) -> dict[str, np.ndarray]:
    """Every statistic of SERIES at each quarter end (events by quarters, empty before an
    event's first case), from the running cases counted and the drug's (`totals`,
    `ingredient`: quarters by columns), each event's running cases with the drug (`cases`),
    and each event's cases added in each quarter and column (`added`: event, quarter, column,
    cases, in quarter order). The quarter ends are scored in slices of CELLS_AT_ONCE; with
    `only`, that one quarter end alone, every other left empty."""
    events, quarters = cases.shape
    out = {name: np.full((events, quarters), np.nan) for name in SERIES}
    running = np.zeros((events, totals.shape[1]), dtype=np.int64)
    j, t, col, n = added
    bounds = np.searchsorted(t, np.arange(quarters + 1))
    waiting: list[tuple[int, np.ndarray, np.ndarray]] = []  # quarter, events with a case, theirs
    for q in range(quarters):
        now = slice(bounds[q], bounds[q + 1])
        np.add.at(running, (j[now], col[now]), n[now])
        alive = np.flatnonzero(cases[:, q] > 0) if only in (None, q) else np.empty(0, dtype=int)
        if alive.size:
            waiting.append((q, alive, running[alive]))
        if waiting and (q == quarters - 1 or sum(r.size for *_, r in waiting) >= CELLS_AT_ONCE):
            at = np.concatenate([np.full(a.size, w) for w, a, _ in waiting])
            rows = np.concatenate([a for _, a, _ in waiting])
            scores = score_with(
                prior,
                Cells(
                    cases=cases[rows, at],
                    ingredient=ingredient[at],
                    reaction=np.vstack([r for *_, r in waiting]),
                    strata=totals[at],
                ),
            )
            for name in SERIES:
                out[name][rows, at] = scores[name]
            waiting = []
    return out


def _screens(query: Query) -> list[list[tuple[str, str, float]]]:
    """The screens asked (`screen`, repeated), each a JSON list of conditions, checked."""
    such = json.dumps(screen.start("EBGM"))
    form = f"Write each screen as a JSON list of conditions, such as {such}."
    out = []
    for text in query.get("screen", []):
        try:
            when = json.loads(text)
        except ValueError:
            raise Problem(400, form) from None
        if not isinstance(when, list) or not when or not all(isinstance(c, dict) for c in when):
            raise Problem(400, form)
        try:
            out.append(screen.check(when, SERIES))
        except screen.ScreenError as exc:
            raise Problem(400, str(exc)) from None
    return out


def _rising(query: Query) -> str | None:
    column = value_of(query, "rising").strip()
    if column and column not in SERIES:
        raise Problem(400, f"Rising reads one of {', '.join(SERIES)}, not {column}.")
    return column or None


def since(quarters: Sequence[int], past: Sequence[bool]) -> int | None:
    """Walking back from the newest quarter end while the pair is past, the first quarter of
    that unbroken stretch; None when it is not past at the newest. An earlier stretch that fell
    back is not read."""
    found = None
    for quarter, held in zip(reversed(quarters), reversed(past), strict=True):
        if not held:
            break
        found = quarter
    return found


def _event(
    j: int,
    qnums: np.ndarray,
    cases: np.ndarray,
    scores: dict[str, np.ndarray],
    screens: list[list[tuple[str, str, float]]],
    rising: tuple[str, int, str] | None,
) -> dict[str, Any]:
    """One event's series from its first case, and, as asked, whether it was past a screen at
    each quarter end and since when, and whether it is rising (`rising`: the statistic, the
    quarter ends back and the comparison of rule trend-rising)."""
    held = np.flatnonzero(cases[j] > 0)
    first = int(held[0]) if held.size else len(qnums)
    values = {name: scores[name][j, first:].tolist() for name in SERIES[1:]}
    values = {name: [None if math.isnan(v) else v for v in got] for name, got in values.items()}
    columns = [qnums[first:].tolist(), cases[j, first:].tolist(), *values.values()]
    rows: list[list[Any]] = [list(row) for row in zip(*columns, strict=True)]
    out: dict[str, Any] = {"series": rows}
    if screens:
        past = [
            any(screen.meets(s, dict(zip(SERIES, row[1:], strict=True))) for s in screens)
            for row in rows
        ]
        out |= {"past": past, "since": since(columns[0], past)}
    if rising:
        column, back, compare = rising
        by_name = {"cases": columns[1], **values}
        out["rising"] = trend.risen(by_name, column, back, compare=compare)
    return out


def _group(
    rows: list[dict[str, Any]], column: dict[Stratum, int], t0: int, size: int
) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
    """A group's cases with the drug added in each quarter (one event by quarters), and the
    group's own cases added in each quarter and column, in quarter order, from _cells."""
    pairs = np.zeros((1, size), dtype=np.int64)
    named = [r for r in rows if r["reaction"]]
    for r in named:
        pairs[0, quarter_index(r["q"]) - t0] += r["cases"]
    added = tuple(
        np.asarray(a, dtype=np.int64)
        for a in (
            [0] * len(named),
            [quarter_index(r["q"]) - t0 for r in named],
            [column.get(stratum, len(column)) for stratum in strata_of(named)],
            [r["reaction"] for r in named],
        )
    )
    order = np.argsort(added[1], kind="stable")
    return pairs, tuple(a[order] for a in added)


@dataclass(frozen=True)
class _Worked:
    """What every screen and trend of one question reads: the quarter ends, each event as named,
    its running cases and its statistics at each quarter end, and what `by=event` leaves out."""

    qnums: np.ndarray
    named: list[tuple[str | None, str | None]]
    cases: np.ndarray
    scores: dict[str, np.ndarray]
    left_out: dict[str, int] | None


def _work_out(
    data: Data,
    entry: dict[str, Any],
    drug: str,
    keys: list[str] | None,
    by: str,
    back: int | None = None,
) -> _Worked:
    """The series of the drug's every event, or of the group `keys` counted as one; with `back`,
    the statistics of only the quarter end that many before the newest."""
    qnums, numbered, totals = event_totals(data) if by == "event" else _totals(data)
    t0, size = int(quarter_index(qnums[0])), len(qnums)
    found = _cells(data, drug, data.reactions.texts(keys) if keys else [], by)
    # the columns are the drug's strata, and one more for every other stratum together, where
    # the drug has no case, so E is the same and each margin still counts every case
    strata = strata_of(found)
    columns = sorted({s for r, s in zip(found, strata, strict=True) if r["ingredient"]})
    column = {s: i for i, s in enumerate(columns)}
    rest = [i for s, i in numbered.items() if s not in column]
    every = np.column_stack([totals[:, [numbered[s] for s in columns]], totals[:, rest].sum(1)])
    drug_cases = np.zeros((size, len(columns) + 1), dtype=np.int64)
    for r, stratum in zip(found, strata, strict=True):
        if r["ingredient"]:
            drug_cases[quarter_index(r["q"]) - t0, column[stratum]] += r["ingredient"]
    if keys:
        named: list[tuple[str | None, str | None]] = [(None, None)]
        pairs, added = _group(found, column, t0, size)
    else:
        events = _events(data, entry, drug)
        named = list(events)
        terms = [term for _, term in events]
        pairs = _pair_cases(data, drug, terms, t0, size, by)
        read = event_reaction_cases if by == "event" else _reaction_cases
        added = read(data, terms, columns, t0)
    cases = np.cumsum(pairs, axis=1)
    only = None if back is None else size - 1 - back
    scores = _scored(release_prior(entry), every, np.cumsum(drug_cases, axis=0), cases, added, only)
    left_out = undated(data, drug, keys) if by == "event" else None
    return _Worked(qnums, named, cases, scores, left_out)


def series(data: Data, query: Query) -> dict[str, Any]:
    """The drug's ingredient (`product`) with each event of its statistics, or with one group
    of reactions counted as one (`reaction`, repeated): each event's statistics at the end of
    every quarter from its first case (`series`, rows of `columns`); with screens, whether it
    was past any one of them, each judged whole, at each quarter end (`past`) and since when
    (`since`); with `rising`, whether that statistic is rising (rule trend-rising); with
    `by=event`, each case placed by the date the reaction started and each event's `undated`.
    `not_available` gives why EBGM, EB05 and EB95 are empty where the release's prior did not
    fit. Questions differing only in their screens or `rising` share one working out, so a
    page's questions side by side count the series once, not each."""
    entry = given(data)
    if not entry["present"]:
        raise Problem(404, entry["reason"])
    _reaction_table(data)
    drug = ingredient_of(data, query)
    screens, rising, by = _screens(query), _rising(query), by_of(query)
    keys = None
    group = None
    if "reaction" in query:
        keys = sorted({k for k in map(data.reactions.key, query["reaction"]) if k})
        if not keys:
            raise Problem(400, "Name the group's reactions as reaction, one or more.")
        group = [data.pt_name(k) or k for k in keys]
    worked = data.facts.recent(
        "|".join(["quarters", data.reactions.version or "-", by, drug, *(keys or [])]),
        lambda: _work_out(data, entry, drug, keys, by),
    )
    back = int(rulebook.value(trend.RULE, "quarters_back"))
    trend_asked = (rising, back, str(rulebook.value(trend.RULE, "compare"))) if rising else None

    def event_of(j: int, pt: str | None, term: str | None) -> dict[str, Any]:
        out = _event(j, worked.qnums, worked.cases, worked.scores, screens, trend_asked)
        out = {"pt": pt, "term": term, **out}
        left = worked.left_out
        return out if left is None else out | {"undated": left.get((term or "").lower(), 0)}

    return {
        "ingredient": drug,
        "reactions": group,
        "by": by,
        "columns": list(COLUMNS),
        "events": [event_of(j, pt, term) for j, (pt, term) in enumerate(worked.named)],
        "rising": {"column": rising, "quarters_back": back} if rising else None,
        "not_available": not_available(entry),
    }


def prior_quarter(data: Data, query: Query) -> dict[str, Any]:
    """Each event of the drug's (`product`) statistics, with its EBGM and EB05 at the end of the
    quarter before the release's newest, scored as `series` scores it but for that quarter end
    alone: empty for an event with no case by then, and no rows for a release of one quarter."""
    entry = given(data)
    if not entry["present"]:
        raise Problem(404, entry["reason"])
    _reaction_table(data)
    drug = ingredient_of(data, query)
    worked = data.facts.recent(
        "|".join(["prior quarter", data.reactions.version or "-", drug]),
        lambda: _work_out(data, entry, drug, None, "received", back=1),
    )
    end = len(worked.qnums) - 2

    def number(name: str, j: int) -> float | None:
        v = float(worked.scores[name][j, end])
        return None if math.isnan(v) else v

    return {
        "ingredient": drug,
        "quarter": int(worked.qnums[end]) if end >= 0 else None,
        "columns": ["pt", "term", "ebgm", "eb05"],
        "rows": [
            [pt, term, number("ebgm", j), number("eb05", j)]
            for j, (pt, term) in enumerate(worked.named)
        ]
        if end >= 0
        else [],
        "not_available": not_available(entry),
    }


__all__ = ["COLUMNS", "SERIES", "prior_quarter", "series", "since"]
