"""A drug's statistics with each of its events, for the whole release: each event's numbers as the
build worked them out once (statistics_T, counted as rule statistics-cases says), the columns a
drug's events table shows and the ones its thresholds read. No filter, window or setting of how
the drug is counted changes them, so a page asks once per drug.

    statistics_of(data, query)   `product` names the drug: its ingredient's events, as
                                 `columns` then `rows`
    ingredient_of(data, query)   the ingredient a drug's statistics are counted for; refused for
                                 a combination and for a name with no ingredient
    not_available(entry)         each statistic the release cannot give, with why

The answer's rows are columns of values, so a drug of thousands of events comes in one short
answer. No value from the query is put into SQL text.
"""

from __future__ import annotations

from typing import Any

from open_altio.faers.drugnames.dictionary import SEPARATOR
from open_altio.faers.explorer_db import explorer_statistics

from . import drugs, statistics
from .answers import Problem
from .explore import Data, Query, value_of

# Each event's statistics, as the Statistics tab names them: those a drug's events table shows,
# and those its thresholds read beside them (`cases`, the pair's own count over the whole release,
# and the chi-square with Yates' correction that PRR's threshold reads).
STATISTICS = (
    "cases",
    "expected",
    "ebgm",
    "eb05",
    "eb95",
    "prr",
    "chi_square_yates",
    "ror",
    "ror_lower",
    "ror_upper",
    "ic",
    "ic025",
    "onset_days",
)
# the statistics read under the release's fitted prior, which a release may not have
EBGM = ("ebgm", "eb05", "eb95")


def ingredient_of(data: Data, query: Query) -> str:
    """The ingredient whose statistics a drug (`product`) has: statistics are counted for each
    ingredient on its own, so a combination and FDA's spelling with no ingredient have none."""
    name = value_of(query, "product").strip()
    if not name:
        raise Problem(400, "Name the drug as product.")
    found = data.facts.name_of(name)
    if found is None:
        raise Problem(404, f"The release holds no drug named {name}.")
    kind, drug = found
    if kind != "ingredient":
        raise Problem(
            404, f"{drug} names no ingredient, and statistics are counted for each ingredient."
        )
    if SEPARATOR in drug:
        raise Problem(
            400,
            f"{drugs.title(drug)} is a combination: statistics are counted for each of its "
            "ingredients on its own.",
        )
    return drug


def not_available(entry: dict[str, Any]) -> dict[str, str]:
    """Each statistic the release's statistics leave empty for every pair, with the manifest's
    reason: EBGM, EB05 and EB95 where the prior did not fit."""
    fit = entry["ebgm"]
    return {} if fit.get("fitted") else dict.fromkeys(EBGM, fit.get("reason") or "")


def statistics_of(data: Data, query: Query) -> dict[str, Any]:
    """The drug's ingredient's statistics with each event it is counted with, from the release's
    own statistics: `pt` is the event as a page names it, `term` as a filter takes it."""
    entry = statistics.given(data)
    if not entry["present"]:
        raise Problem(404, entry["reason"])
    drug = ingredient_of(data, query)
    by_pt = entry.get("reaction_key") == "meddra_pt"  # a PT is named as MedDRA writes it
    got = data.rows(
        f"SELECT * FROM {explorer_statistics(entry['table'])} WHERE ingredient_T = ? "
        "ORDER BY reaction_T",
        [drug],
    )
    rows = [
        [
            r["reaction_T"] if by_pt else data.pt_name(r["reaction_T"]),
            r["reaction_T"],
            *(r[f"{name}_T"] for name in STATISTICS),
        ]
        for r in got
    ]
    return {
        "ingredient": drug,
        "columns": ["pt", "term", *STATISTICS],
        "rows": rows,
        "not_available": not_available(entry),
    }


__all__ = ["EBGM", "STATISTICS", "ingredient_of", "not_available", "statistics_of"]
