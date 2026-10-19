"""PRR, ROR, RRR and IC (src/open_altio/stats/disproportionality.py), checked three ways:
small tables worked by hand, a reference table with every figure worked out, and a second
implementation's output on the same fifteen tables (reference_tables.json): ten tables of real
ingredient and reaction pairs from FAERS (counts only), the reference table, the hand table
below, and three tables a measure cannot be given for."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy import special

from open_altio import rulebook
from open_altio.stats import disproportionality as dp

REFERENCE = json.loads(
    (Path(__file__).parent / "reference_tables.json").read_text(encoding="utf-8")
)


def one(**columns):
    return {k: float(np.asarray(v).ravel()[0]) for k, v in columns.items()}


# ---------------------------------------------------------------- worked by hand
# a = 10, b = 90, c = 40, d = 860, N = 1000.
#   PRR = (10/100) / (40/900) = 0.1 / (2/45) = 9/4
#   ad - bc = 8600 - 3600 = 5000; margins (a+b)(c+d)(a+c)(b+d) = 100 * 900 * 50 * 950 = 4.275e9
#   chi-square = 1000 * 5000^2 / 4.275e9 = 1000/171;  Yates: 1000 * (5000 - 500)^2 / 4.275e9 = 90/19
#   ROR = 8600 / 3600 = 43/18; se^2 = 1/10 + 1/90 + 1/40 + 1/860
#   expected = 100 * 50 / 1000 = 5; RRR = 10/5 = 2
#   IC = log2(10.5 / 5.5) = log2(21/11); IC025 = IC - 3.3 / sqrt(10.5) - 2 / 10.5^1.5
HAND = (10, 90, 40, 860)


def test_prr_and_both_chi_squares_worked_by_hand():
    got = one(**dp.prr(*HAND))
    assert got["PRR"] == pytest.approx(9 / 4, rel=1e-12)
    assert got["chi_square"] == pytest.approx(1000 / 171, rel=1e-12)
    assert got["chi_square_yates"] == pytest.approx(90 / 19, rel=1e-12)


def test_chi_squares_equal_the_sum_over_the_four_cells():
    """Expected cells 5, 95, 45, 855; every |O - E| = 5."""
    expected_cells = (5, 95, 45, 855)
    pearson = sum(5**2 / e for e in expected_cells)
    yates = sum(4.5**2 / e for e in expected_cells)
    got = one(**dp.prr(*HAND))
    assert got["chi_square"] == pytest.approx(pearson, rel=1e-12)
    assert got["chi_square_yates"] == pytest.approx(yates, rel=1e-12)


def test_ror_and_its_interval_worked_by_hand():
    se = math.sqrt(1 / 10 + 1 / 90 + 1 / 40 + 1 / 860)
    z = rulebook.value("ror", "z")
    got = one(**dp.ror(*HAND))
    assert got["ROR"] == pytest.approx(43 / 18, rel=1e-12)
    assert got["ROR_lower"] == pytest.approx(43 / 18 * math.exp(-z * se), rel=1e-12)
    assert got["ROR_upper"] == pytest.approx(43 / 18 * math.exp(z * se), rel=1e-12)


def test_rrr_worked_by_hand():
    got = one(**dp.rrr(*HAND))
    assert got["expected"] == pytest.approx(5.0, rel=1e-12)
    assert got["RRR"] == pytest.approx(2.0, rel=1e-12)


def test_ic_and_ic025_worked_by_hand():
    ic = math.log2(21 / 11)
    got = one(**dp.ic(*HAND))
    assert got["IC"] == pytest.approx(ic, rel=1e-12)
    assert got["IC025"] == pytest.approx(ic - 3.3 / math.sqrt(10.5) - 2 / 10.5**1.5, rel=1e-12)


def test_table_from_the_counts_a_source_gives():
    """a = 10 cases with both, 100 with the product, 50 with the event, 1000 in all."""
    cells = dp.table([10], [100], [50], 1000)
    assert {k: int(v[0]) for k, v in cells.items()} == dict(zip("abcd", HAND, strict=False))


def test_measures_gives_every_column_and_whole_number_cells():
    out = dp.measures(*([x] for x in HAND))
    assert tuple(out) == dp.COLUMNS
    assert out["a"].dtype.kind == "i" and int(out["d"][0]) == 860
    assert float(out["PRR"][0]) == pytest.approx(9 / 4)


# ---------------------------------------------------------------- a reference table
# a = 10, b = 90, c = 100, d = 9800, each figure worked to four decimals or more.
def test_every_figure_of_the_reference_table():
    got = one(**dp.measures([10], [90], [100], [9800]))
    assert got["PRR"] == pytest.approx(9.9)
    assert got["chi_square"] == pytest.approx(73.5455, abs=5e-4)
    assert got["chi_square_yates"] == pytest.approx(65.5141, abs=5e-4)
    assert got["ROR"] == pytest.approx(98000 / 9000)
    assert got["ROR_lower"] == pytest.approx(5.5033, abs=5e-4)
    assert got["ROR_upper"] == pytest.approx(21.5447, abs=5e-4)
    assert got["expected"] == pytest.approx(1.1) and got["RRR"] == pytest.approx(10 / 1.1)
    assert got["IC"] == pytest.approx(2.714246, abs=1e-6)
    assert got["IC025"] == pytest.approx(1.637061, abs=1e-6)


# ---------------------------------------------------------------- a second implementation
COMPARED = (
    "PRR",
    "chi_square",
    "chi_square_yates",
    "ROR",
    "ROR_lower",
    "ROR_upper",
    "expected",
    "RRR",
    "IC",
    "IC025",
)


@pytest.mark.parametrize(
    "row", REFERENCE["tables"], ids=lambda r: f"{r['a']}-{r['b']}-{r['c']}-{r['d']}"
)
def test_same_numbers_as_a_second_implementation_on_the_same_table(row):
    """Where it gives no value (None), ours is empty (NaN); elsewhere they agree. One
    difference: when c = 0 it withholds the chi-square with the PRR; the chi-square is still
    defined there (every row and column has cases), so it is given."""
    got = one(**dp.measures([row["a"]], [row["b"]], [row["c"]], [row["d"]]))
    for col in COMPARED:
        if row[col] is None and col.startswith("chi_square") and row["c"] == 0:
            assert math.isfinite(got[col]), col
        elif row[col] is None:
            assert math.isnan(got[col]), col
        else:
            assert got[col] == pytest.approx(row[col], rel=1e-9), col


def test_the_reference_tables_include_real_pairs_and_refusals():
    rows = REFERENCE["tables"]
    assert len(rows) == 15
    assert any(r["PRR"] is None for r in rows) and any(r["ROR"] is None for r in rows)


# ---------------------------------------------------------------- empty, never infinite
def test_no_comparator_leaves_prr_and_ror_empty():
    out = one(**dp.measures([5], [95], [0], [9900]))
    assert math.isnan(out["PRR"]) and math.isnan(out["ROR"]) and math.isnan(out["ROR_lower"])
    assert (
        math.isfinite(out["chi_square"]) and math.isfinite(out["IC"]) and math.isfinite(out["RRR"])
    )


def test_a_zero_cell_leaves_ror_empty_and_nothing_is_infinite():
    out = dp.measures([5, 3, 1], [0, 7, 2], [100, 2, 3], [9895, 0, 4])
    assert np.isnan(out["ROR"][:2]).all() and np.isfinite(out["ROR"][2])
    for col in COMPARED:
        assert not np.isinf(out[col]).any(), col


def test_ror_takes_a_stratum_where_the_product_has_no_case():
    out = dp.ror([0], [0], [4], [40])
    assert math.isnan(out["ROR"][0])


@pytest.mark.parametrize(
    "cells",
    [
        ([-1], [10], [10], [100]),
        ([1.5], [10], [10], [100]),
        ([0], [0], [10], [100]),
        ([0], [10], [0], [100]),
    ],
)
def test_refused_tables(cells):
    with pytest.raises(ValueError):
        dp.measures(*cells)


def test_a_table_with_a_negative_cell_is_refused():
    with pytest.raises(ValueError, match="negative"):
        dp.table([10], [5], [50], 1000)


# ---------------------------------------------------------------- columns at once
def test_columns_at_once_equal_one_table_at_a_time():
    rng = np.random.default_rng(7)
    a, b, c, d = (rng.integers(1, 50, 40) for _ in range(4))
    whole = dp.measures(a, b, c, d)
    for i in range(40):
        single = dp.measures([a[i]], [b[i]], [c[i]], [d[i]])
        for col in dp.COLUMNS:
            assert whole[col][i] == pytest.approx(single[col][0], rel=1e-12, nan_ok=True), col


def test_large_tables_keep_the_chi_square_exact():
    """FAERS-sized cells: the closed form equals the cell sum computed in exact fractions."""
    from fractions import Fraction

    a, b, c, d = 1291, 36813, 6281, 15856661
    n = a + b + c + d
    rows, cols = (a + b, c + d), (a + c, b + d)
    exact = sum(
        Fraction((o * n - r * k) ** 2, n * r * k)
        for o, r, k in (
            (a, rows[0], cols[0]),
            (b, rows[0], cols[1]),
            (c, rows[1], cols[0]),
            (d, rows[1], cols[1]),
        )
    )
    assert float(dp.prr([a], [b], [c], [d])["chi_square"][0]) == pytest.approx(
        float(exact), rel=1e-12
    )


# ---------------------------------------------------------------- the IC025 closed form
def test_ic025_closed_form_is_within_a_twentieth_of_the_exact_gamma_point():
    """The claim in rules/ic.md: on every count from 1 to 10,000 the closed form lies within 0.05
    (log2 scale) of the 2.5% point of the Gamma(a + 0.5, rate expected + 0.5) posterior, and below
    it from 2 cases on. The difference does not depend on the expected count."""
    a = np.arange(1, 10_001)
    k = rulebook.value("ic", "shrinkage")
    b, c, d = np.full(a.shape, 10**6), np.full(a.shape, 10**6), np.full(a.shape, 10**8)
    exact = np.log2(special.gammaincinv(a + k, 0.025) / (dp.expected(a, b, c, d) + k))
    gap = dp.ic(a, b, c, d)["IC025"] - exact
    assert np.abs(gap).max() < 0.05
    assert (gap[1:] < 0).all()
