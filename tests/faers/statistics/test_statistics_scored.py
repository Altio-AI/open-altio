"""Scoring tables the build did not (scored.py): score_with scores each row by the build's own maths
under the prior it is given, a row with no table expects no case and gives no statistic, and
release_prior reads the prior a built release was scored under, never fitting one."""

from __future__ import annotations

import numpy as np
import pytest

from open_altio.faers import read_manifest
from open_altio.faers.statistics.scored import (
    COLUMNS,
    MEASURES,
    SCORED,
    Cells,
    release_prior,
    score_with,
)
from open_altio.stats import disproportionality as dp
from open_altio.stats import ebgm

PRIOR = ebgm.Prior(alpha1=2.0, beta1=1.0, alpha2=0.5, beta2=0.4, p=0.2)
# two tables over three strata: 6 of 40, 10 of 70 and 4 of 90 cases name the ingredient
CELLS = Cells(
    cases=np.array([5, 0]),
    ingredient=np.array([[6, 10, 4], [6, 10, 4]]),
    reaction=np.array([[8, 3, 12], [2, 0, 5]]),
    strata=np.array([[40, 70, 90], [40, 70, 90]]),
)


def by_hand(row: int, prior: ebgm.Prior | None) -> dict[str, float]:
    """One row's statistics worked out from the formulas: E over the strata, then the maths of
    open_altio.stats on the row's two by two table."""
    i, r, n = CELLS.ingredient[row], CELLS.reaction[row], CELLS.strata[row]
    a = int(CELLS.cases[row])
    e = float(sum(i[s] * r[s] / n[s] for s in range(len(n))))
    table = dp.table([a], [int(i.sum())], [int(r.sum())], int(n.sum()))
    maths = dp.measures(**table) | {"E": np.array([e])}
    if prior is not None:
        maths |= ebgm.score(prior, [a], [e])
    out = {"cases": a, "ingredient_cases": int(i.sum()), "reaction_cases": int(r.sum())}
    for name in MEASURES:
        source = str(COLUMNS[name])
        out[name] = float(maths[source][0]) if source in maths else float("nan")
    return out


def test_each_row_is_scored_by_the_builds_maths_under_the_prior_given():
    got = score_with(PRIOR, CELLS)
    assert list(got) == list(SCORED)
    for row in (0, 1):
        want = by_hand(row, PRIOR)
        for name in SCORED:
            assert got[name][row] == pytest.approx(want[name], rel=1e-12, nan_ok=True), name


def test_a_row_of_no_cases_with_the_event_still_has_its_expected_count_and_ebgm():
    got = score_with(PRIOR, CELLS)
    assert got["cases"][1] == 0 and got["expected"][1] > 0
    assert got["ebgm"][1] < 1 and np.isnan(got["ror"][1])  # a zero cell leaves ROR empty


def test_without_a_prior_ebgm_eb05_and_eb95_are_empty_and_the_rest_are_given():
    got = score_with(None, CELLS)
    with_prior = score_with(PRIOR, CELLS)
    for name in MEASURES:
        if name in ("ebgm", "eb05", "eb95"):
            assert np.isnan(got[name]).all(), name
        else:
            assert np.array_equal(got[name], with_prior[name], equal_nan=True), name


def test_a_row_whose_ingredient_or_event_has_no_case_expects_none_and_gives_no_statistic():
    empty = Cells(
        cases=np.array([0, 0]),
        ingredient=np.array([[0, 0, 0], [3, 0, 0]]),
        reaction=np.array([[2, 1, 0], [0, 4, 0]]),
        strata=np.array([[10, 10, 0], [10, 10, 0]]),
    )
    got = score_with(PRIOR, empty)
    assert list(got["expected"]) == [0.0, 0.0]
    assert list(got["ingredient_cases"]) == [0, 3] and list(got["reaction_cases"]) == [3, 4]
    for name in MEASURES:
        if name != "expected":
            assert np.isnan(got[name]).all(), name


def test_the_prior_is_the_one_the_release_records_and_is_never_fitted(stats_release, monkeypatch):
    def no_fit(*args, **kwargs):
        raise AssertionError("release_prior fitted a prior")

    monkeypatch.setattr(ebgm, "fit_prior", no_fit)
    entry = read_manifest(stats_release)["statistics"]
    assert entry["ebgm"]["fitted"]
    assert release_prior(entry) == ebgm.Prior(**entry["ebgm"]["prior"])


def test_a_release_whose_prior_did_not_fit_has_none(release):
    entry = read_manifest(release)["statistics"]
    assert not entry["ebgm"]["fitted"] and entry["ebgm"]["reason"]
    assert release_prior(entry) is None
