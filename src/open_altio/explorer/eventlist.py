"""A drug's events: every event the drug's counted cases name under the question, one row each,
each count of distinct cases (rules serious-outcomes, received-day); and a group of reactions
counted as one event, with the same figures, worked out by the same code.

    events(data, query)    `columns`, then `rows`: one row per event, most cases first
    group(data, query)     the figures of one group (`reaction`, repeated)

An event is the key the viewer counts reactions under (reactions.py): where the release holds
MedDRA, the current preferred term, so the cases FDA coded with an older name or a lower level
term of it count in its row. A group counts every case naming any of its reactions under one
key, so a case counts once however many of them it names, and a group of one reaction is that
event's row. The drug is the question's product, counted as its settings say
(explore.product_unit). Each drug is asked alone, so a case naming two drugs counts on the rows
of each. No value from the query is put into SQL text.
"""

from __future__ import annotations

from typing import Any

from open_altio.faers import medical_events
from open_altio.faers.dates import received_quarter
from open_altio.faers.explorer_db import reaction_term
from open_altio.rulebook import value

from . import labels
from .answers import Problem, cases_query
from .drugs import Unit
from .explore import Data, Query, Scope, scope

RULE = "serious-outcomes"
# what an event's row counts, and a group's
FIGURES = (
    "cases",
    "newest",
    "prior",
    "recent",
    "years",
    "busiest_year",
    "serious",
    "death",
    "life_threatening",
    "death_or_life_threatening",
)
COLUMNS = ("pt", *FIGURES, "label", "dme", "ime", "cases_query")
NO_DRUG = "A drug's events need a drug: name it as product."
NO_GROUP = "Name the group's reactions as reaction, one or more."
# why a column's value is null, where it is (Not available)
NO_FLAGS = "This release holds no label flags."
NO_INGREDIENT = "FDA's spelling with no ingredient is read against no label."
NO_REPORT = "No suspect report of the drug that the label flags read names this event."
NOT_HELD = {
    "dme": "This release holds no list of designated medical events.",
    "ime": "This release holds no list of important medical events.",
}
LISTS = ("dme", "ime")


def _quarter(name: str) -> tuple[int, str]:
    """A quarter as FDA's files name it (2026q2): its number as the counts place a case in it
    (20262), and as a page writes it (2026 Q2)."""
    year, n = int(name[:4]), int(name[-1])
    return year * 10 + n, f"{year} Q{n}"


def _counted(data: Data, asked: Scope, keyed: tuple[str, list[Any]]) -> list[dict[str, Any]]:
    """Under each key of `keyed` (a FROM item of case_id_T, k), its cases the question asks of,
    by the quarter each case is placed in (its received day's, else its own file's): a case is in
    one quarter, so the quarters' counts add up to the key's."""
    sql, params = asked.where()
    reacs, reac_params = keyed
    serious = list(value(RULE, "serious"))
    death, threatening = str(value(RULE, "death")), str(value(RULE, "life_threatening"))
    return data.rows(
        f"WITH cs AS (SELECT c.case_id_T, {received_quarter('c')} AS q, "
        "list_has_any(c.outcomes_T, ?::VARCHAR[]) AS serious, "
        "list_contains(c.outcomes_T, ?::VARCHAR) AS death, "
        "list_contains(c.outcomes_T, ?::VARCHAR) AS threatening "
        f"FROM explorer_case_T c WHERE {sql}) "
        "SELECT r.k, cs.q, count(DISTINCT r.case_id_T) AS n, "
        "count(DISTINCT r.case_id_T) FILTER (WHERE cs.serious) AS serious, "
        "count(DISTINCT r.case_id_T) FILTER (WHERE cs.death) AS death, "
        "count(DISTINCT r.case_id_T) FILTER (WHERE cs.threatening) AS threatening, "
        "count(DISTINCT r.case_id_T) FILTER (WHERE cs.death OR cs.threatening) AS either "
        f"FROM {reacs} r JOIN cs USING (case_id_T) GROUP BY 1, 2",
        [serious, death, threatening, *params, *reac_params],
    )


SUMS = ("n", "serious", "death", "threatening", "either")  # _counted's, summed over quarters


def _trend_quarters() -> int:
    return int(value("explorer-event-thresholds", "trend_quarters"))


def _tally() -> dict[str, Any]:
    recent = [0] * _trend_quarters()
    return dict.fromkeys(SUMS, 0) | {
        "newest": 0,
        "prior": 0,
        "recent": recent,
        "quarters": {},
        "years": {},
    }


def _before(quarter: int) -> int:
    """The calendar quarter before one numbered as the counts place a case in it (20262)."""
    return quarter - 1 if quarter % 10 > 1 else (quarter // 10 - 1) * 10 + 4


def _tallied(data: Data, asked: Scope, keyed: tuple[str, list[Any]]) -> dict[str, dict]:
    """Each key's counts over the whole question, its cases in the release's newest quarters
    (`recent`, oldest first, rule explorer-event-thresholds), and by year."""
    newest, _ = _quarter(data.opened.manifest["quarters"][-1])
    prior = _before(newest)
    wanted = [newest]
    while len(wanted) < _trend_quarters():
        wanted.insert(0, _before(wanted[0]))
    found: dict[str, dict[str, Any]] = {}
    for r in _counted(data, asked, keyed):
        tally = found.setdefault(r["k"], _tally())
        for name in SUMS:
            tally[name] += r[name]
        tally["newest"] += r["n"] if r["q"] == newest else 0
        tally["prior"] += r["n"] if r["q"] == prior else 0
        tally["quarters"][r["q"]] = tally["quarters"].get(r["q"], 0) + r["n"]
        year = r["q"] // 10
        tally["years"][year] = tally["years"].get(year, 0) + r["n"]
    for tally in found.values():
        tally["recent"] = [tally["quarters"].get(q, 0) for q in wanted]
    return found


def _figures(tally: dict[str, Any]) -> list[Any]:
    """A key's FIGURES, in their order: its cases, those placed in the release's newest quarter
    and in the one before it, its cases in each of the newest quarters, its cases by year with
    its busiest year (the earliest of those tied, None with no case), and its serious, fatal,
    life-threatening and fatal or life-threatening cases."""
    years = sorted(tally["years"].items())
    busiest = min(years, key=lambda y: (-y[1], y[0]))[0] if years else None
    counts = [tally[n] for n in SUMS[1:]]  # serious, death, threatening, either
    return [
        tally["n"],
        tally["newest"],
        tally["prior"],
        tally["recent"],
        [list(y) for y in years],
        busiest,
        *counts,
    ]


def _flags(data: Data, product: Unit) -> tuple[dict[str, dict] | None, str]:
    """Each event's label flag for the drug, and why an event has none; None, and why, where no
    event can have one."""
    if not labels.held(data.opened):
        return None, NO_FLAGS
    if product.substance is None:
        return None, NO_INGREDIENT
    return labels.event_flags(data, product.substance, product.exact), NO_REPORT


def _lists(data: Data) -> tuple[dict[str, set[str]], dict[str, str]]:
    """The events on each of EMA's lists the release holds, as the keys events are counted
    under, and why each list it does not hold is missing."""
    entry = data.opened.manifest.get(medical_events.ENTRY) or {}
    held = {n: v for n, v in (entry.get("lists") or {}).items() if v.get("present")}
    why = {
        n: (entry.get("lists") or {}).get(n, {}).get("reason") or NOT_HELD[n]
        for n in LISTS
        if n not in held
    }
    if not held:
        return {}, why
    table = data.opened.folder / data.opened.manifest["tables"][medical_events.TABLE]["path"]
    found: dict[str, set[str]] = {n: set() for n in held}
    for r in data.rows("SELECT list_T, pt_T FROM read_parquet(?)", [str(table)]):
        if r["list_T"] in found:
            found[r["list_T"]].add(reaction_term(r["pt_T"]) or "")
    return found, why


def _label(flag: dict | None) -> dict | None:
    """The label answer for an event: the flag, the DailyMed set ID and version of the label it
    was read on, and each route family's answer where the families differ."""
    if flag is None:
        return None
    read = flag.get("label") or {}
    return {
        "answer": flag["outcome"],
        "setid": flag["setid"],
        "spl_version": read.get("version"),
        "forms": flag["families"],
    }


def events(data: Data, query: Query) -> dict[str, Any]:
    """Every event the product's counted cases name under the question's filters, most cases
    first, then by name: its FIGURES, its label answer, whether EMA lists it as a designated
    (`dme`) or important (`ime`) medical event (null, never false, where the release holds no
    such list) and the /api/cases question that lists its cases (`cases_query`).
    `not_available` gives, for each column with a null value, why."""
    asked = scope(data, query)
    if asked.product is None:
        raise Problem(400, NO_DRUG)
    found = _tallied(data, asked, data.reactions.keyed())
    flags, no_flag = _flags(data, asked.product)
    listed, missing = _lists(data)
    rows = []
    for k, tally in found.items():
        label = _label(flags.get(k)) if flags is not None else None
        if label is None:
            missing["label"] = no_flag
        rows.append(
            [
                data.pt_name(k) or k,
                *_figures(tally),
                label,
                *(k in listed[n] if n in listed else None for n in LISTS),
                cases_query(query, event=[k]),
            ]
        )
    rows.sort(key=lambda r: (-r[1], r[0].lower(), r[0]))
    return {
        "columns": list(COLUMNS),
        "rows": rows,
        "newest_quarter": _quarter(data.opened.manifest["quarters"][-1])[1],
        "not_available": dict(sorted(missing.items())),
    }


def group(data: Data, query: Query) -> dict[str, Any]:
    """The group of reactions (`reaction`, repeated) counted as one event of the product, or of a
    drug class (`atc`), under the question's filters: the FIGURES an event's row has, each case
    counted once however many of the group's reactions it names, the group's reactions as the
    release names them, and the /api/cases question that lists its cases (`cases_query`)."""
    # the reactions here are the group, not the one-reaction filter
    asked = scope(data, {k: v for k, v in query.items() if k != "reaction"})
    if asked.product is None and not query.get("atc"):
        raise Problem(400, NO_DRUG)
    keys = sorted({k for k in map(data.reactions.key, query.get("reaction", [])) if k})
    if not keys:
        raise Problem(400, NO_GROUP)
    reacs, params = data.reactions.keyed(keys)
    found = _tallied(data, asked, (f"(SELECT case_id_T, '' AS k FROM {reacs})", params))
    return {
        "reactions": [data.pt_name(k) or k for k in keys],
        **dict(zip(FIGURES, _figures(found.get("", _tally())), strict=True)),
        "newest_quarter": _quarter(data.opened.manifest["quarters"][-1])[1],
        # the group is its reactions, not the one-reaction filter
        "cases_query": cases_query(query, "reaction", event=keys),
    }


__all__ = ["COLUMNS", "FIGURES", "events", "group"]
