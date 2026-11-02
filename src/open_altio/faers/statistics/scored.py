"""Every pair of the counted cases scored: EBGM under a prior fitted on the release's own
cases, and PRR, ROR, RRR and IC from each pair's table of cases. The maths is
open_altio.stats; this joins it to the counts and names the columns the release keeps.

    columns, about = score(counts)       # every pair, the prior fitted (the build's step)
    prior = release_prior(entry)         # the prior a built release was scored under
    scores = score_with(prior, cells)    # other tables of the same cases, under that prior

`score_with` scores tables the build did not, such as a group of reactions counted as one or the
cases received since a day, with the same maths and the release's own prior, never fitted again,
so its numbers stand beside the release's: a table it is given that the build scored too gets
that pair's own numbers."""

from __future__ import annotations

from dataclasses import dataclass
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
    product, event = counts.pairs["product"], counts.pairs["event"]
    n_product = _margin(counts.ingredient_strata, "product", len(counts.ingredients))[product]
    n_event = _margin(counts.reaction_strata, "event", len(counts.reactions))[event]
    maths = _maths(
        fitted.prior if fitted else None, counts.pairs["n"], n_product, n_event, counts.cases, ne
    )
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


def _maths(
    prior: ebgm.Prior | None,
    n: np.ndarray,
    n_product: np.ndarray,
    n_event: np.ndarray,
    total: Any,
    ne: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    """Every statistic, by the maths' names, of tables of cases (`n` naming both, `n_product`,
    `n_event`, `total`) with their expected counts within strata (`ne["E"]`): EBGM, EB05 and
    EB95 under `prior`, empty without one. The one place the build's scores and score_with's
    are worked out."""
    if prior is None:
        scores = {k: np.full(len(ne["E"]), np.nan) for k in ("EBGM", "EB05", "EB95")}
    else:
        scores = ebgm.score(prior, ne["N"], ne["E"])
    cells = dp.table(n, n_product, n_event, total)
    return {**dp.measures(**cells), **scores, "E": ne["E"]}


def release_prior(entry: dict[str, Any]) -> ebgm.Prior | None:
    """The prior a built release's statistics were scored under, as its manifest's statistics
    entry records it (`statistics`, or its `as_published` for the set counted by FDA's text);
    None where it did not fit, and the entry's `ebgm.reason` says why. Read, never fitted."""
    fitted = entry["ebgm"]
    return ebgm.Prior(**fitted["prior"]) if fitted.get("fitted") else None


@dataclass(frozen=True)
class Cells:
    """Tables of cases to score, one per row, each over strata of the same cases: the cases
    naming the ingredient and the reaction (`cases`, one number per row); and in each stratum
    (rows by strata, the strata in the same order in every row) the cases naming the ingredient
    (`ingredient`), those naming the reaction (`reaction`) and every case counted (`strata`).
    A group of reactions counted as one names its cases once each in `cases` and `reaction`."""

    cases: np.ndarray
    ingredient: np.ndarray
    reaction: np.ndarray
    strata: np.ndarray


# score_with's columns: those of COLUMNS a table gives, its two names aside; and of those, the
# ones worked out from the counts.
SCORED = tuple(name for name in COLUMNS if name not in ("ingredient", "reaction"))
MEASURES = tuple(n for n in SCORED if n not in ("cases", "ingredient_cases", "reaction_cases"))


def score_with(prior: ebgm.Prior | None, cells: Cells) -> dict[str, np.ndarray]:
    """Every column of SCORED for each row of `cells`, by the build's own maths (_maths): E
    summed over the strata, EBGM, EB05 and EB95 under `prior` (release_prior; empty without
    one), and PRR, chi-square, ROR, RRR and IC from the row's table. A row where no stratum
    holds both its ingredient and its reaction, as where either has no case, expects 0 cases
    and has every other statistic empty."""
    a = np.asarray(cells.cases, dtype=np.int64)
    ingredient, reaction, strata = (
        np.asarray(x, dtype=np.int64) for x in (cells.ingredient, cells.reaction, cells.strata)
    )
    n_product, n_event, total = ingredient.sum(axis=1), reaction.sum(axis=1), strata.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.where(strata > 0, ingredient / strata, 0.0)
    e = np.einsum("ks,ks->k", share, reaction.astype(float))
    out = {name: np.full(len(a), np.nan) for name in MEASURES}
    out |= {"cases": a, "ingredient_cases": n_product, "reaction_cases": n_event}
    held = e > 0
    if held.any():
        ne = {"N": a[held], "E": e[held]}
        maths = _maths(prior, a[held], n_product[held], n_event[held], total[held], ne)
        for name in MEASURES:
            out[name][held] = maths[str(COLUMNS[name])]
    out["expected"] = e
    return {name: out[name] for name in SCORED}
