"""Every pair of the counted cases scored: EBGM under a prior fitted on the release's own
cases, and PRR, ROR, RRR and IC from each pair's table of cases. The maths is
open_altio.stats; this joins it to the counts and names the columns the release keeps."""

from __future__ import annotations

from typing import Any

import numpy as np

from open_altio.stats import disproportionality as dp
from open_altio.stats import ebgm

from .cases import Counts

# The statistics' own name for each column the table keeps (its name in the release adds the
# derived suffix), and the column of the maths it comes from.
COLUMNS = {
    "ingredient": None,
    "reaction": None,
    "cases": "a",
    "ingredient_cases": None,
    "reaction_cases": None,
    "expected": "E",
    "ebgm": "EBGM",
    "eb05": "EB05",
    "eb95": "EB95",
    "prr": "PRR",
    "chi_square": "chi_square",
    "chi_square_yates": "chi_square_yates",
    "ror": "ROR",
    "ror_lower": "ROR_lower",
    "ror_upper": "ROR_upper",
    "rrr": "RRR",
    "ic": "IC",
    "ic025": "IC025",
}
EBGM_COLUMNS = ("ebgm", "eb05", "eb95")


def _margin(table: dict[str, np.ndarray], key: str, size: int) -> np.ndarray:
    """Cases per ingredient (or reaction) over every stratum: each case is in one stratum."""
    return np.bincount(table[key], weights=table["n"], minlength=size).astype(np.int64)


def fit(counts: Counts, ne: dict[str, np.ndarray]) -> tuple[ebgm.Fit | None, dict[str, Any]]:
    """The prior fitted on the counted cases, and what the manifest says about it; no fit, and
    why, when the starts do not agree inside the parameter space."""
    model = ebgm.settings()
    strata = {"stratum": counts.strata["stratum"], "n": counts.strata["n"]}
    unseen: tuple[Any, Any] = (None, None)
    if model["fit_on"] == "all_cells":
        unseen = ebgm.unseen_cells(
            counts.pairs,
            counts.ingredient_strata,
            counts.reaction_strata,
            strata,
            model["squash_bins_per_decade"],
        )
    try:
        fitted = ebgm.fit_prior(ne["N"], ne["E"], *unseen)
    except ebgm.FitError as exc:
        return None, {"fitted": False, "reason": str(exc), "starts": exc.starts}
    return fitted, {
        "fitted": True,
        "prior": fitted.prior.as_dict(),
        "component_order": "component 1 has the larger prior mean, alpha1 / beta1",
        "fit_on": fitted.fit_on,
        "min_count": fitted.min_count,
        "cells_never_seen": float(unseen[1].sum()) if unseen[1] is not None else 0.0,
        "cells_fitted": fitted.cells,
        "points_fitted": fitted.points,
        "neg_log_lik": fitted.neg_log_lik,
        "starts": fitted.starts,
    }


def score(counts: Counts) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Every column of COLUMNS for every pair seen, ordered by ingredient then reaction, and
    what the manifest says about the EBGM fit."""
    strata = {"stratum": counts.strata["stratum"], "n": counts.strata["n"]}
    ne = ebgm.expected_counts(
        counts.pairs, counts.ingredient_strata, counts.reaction_strata, strata
    )
    fitted, about = fit(counts, ne)
    if fitted is None:
        scores = {k: np.full(len(ne["N"]), np.nan) for k in ("EBGM", "EB05", "EB95")}
    else:
        scores = ebgm.score(fitted.prior, ne["N"], ne["E"])
    product, event = counts.pairs["product"], counts.pairs["event"]
    n_product = _margin(counts.ingredient_strata, "product", len(counts.ingredients))[product]
    n_event = _margin(counts.reaction_strata, "event", len(counts.reactions))[event]
    cells = dp.table(counts.pairs["n"], n_product, n_event, counts.cases)
    maths: dict[str, np.ndarray] = {**dp.measures(**cells), **scores, "E": ne["E"]}
    out = {
        "ingredient": counts.ingredients[product],
        "reaction": counts.reactions[event],
        "ingredient_cases": n_product,
        "reaction_cases": n_event,
    }
    for name, source in COLUMNS.items():
        if source is not None:
            out[name] = maths[source]
    return {name: out[name] for name in COLUMNS}, about
