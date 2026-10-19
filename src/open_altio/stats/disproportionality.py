"""PRR, ROR, RRR and IC for many product and event pairs at once, from their tables of cases.

Each pair's table (CIOMS Working Group VIII), counted in cases:

                          the event    any other event
    the product               a              b
    any other product         c              d

N = a + b + c + d, and the count expected if the product and the event were independent is
expected = (a + b)(a + c) / N.

    PRR               = (a / (a + b)) / (c / (c + d))                 Evans, Waller and Davis 2001
    chi-square        = N (ad - bc)^2 / ((a+b)(c+d)(a+c)(b+d))        Pearson, one degree of freedom
    chi-square, Yates = N (max(|ad - bc| - N/2, 0))^2 / (same)
    ROR               = ad / bc, bounds exp(ln ROR -/+ z sqrt(1/a + 1/b + 1/c + 1/d))
                                                                   van Puijenbroek et al. 2002
    RRR               = a / expected                                  DuMouchel 1999
    IC                = log2((a + k) / (expected + k))                Noren, Hopstadius, Bate 2013
    IC025             = IC - c1 (a + k)^(-1/2) - c2 (a + k)^(-3/2)

z, k and (c1, c2) are rule values (rules/ror.md, rules/ic.md); each statistic's rule writes
its formula out with its source. Every function takes whole columns and returns whole columns,
so one call scores every pair of a release. A value the table cannot give honestly is NaN (an
empty cell in a table), never infinity: PRR without a comparator (c = 0), ROR with a zero cell,
a chi-square with an empty row or column. No correction is added to make them.

A statistic of disproportionate reporting is not a signal and not evidence of cause: it says
which pairs are reported together more than the rest of the data would lead one to expect.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from open_altio import rulebook

# The columns `measures` returns, in order.
COLUMNS = (
    "a",
    "b",
    "c",
    "d",
    "expected",
    "PRR",
    "chi_square",
    "chi_square_yates",
    "ROR",
    "ROR_lower",
    "ROR_upper",
    "RRR",
    "IC",
    "IC025",
)


def table(n: Any, n_product: Any, n_event: Any, total: Any) -> dict[str, np.ndarray]:
    """The four cells from what a count gives directly.

    n:         cases naming the product and the event (a)
    n_product: cases naming the product (a + b)
    n_event:   cases naming the event (a + c)
    total:     cases in the table (N)
    """
    a = _counts(n)
    n_prod, n_ev = _counts(n_product), _counts(n_event)
    whole = np.broadcast_to(_counts(total), a.shape)
    out = {"a": a, "b": n_prod - a, "c": n_ev - a, "d": whole - n_prod - n_ev + a}
    if any(np.any(v < 0) for v in out.values()):
        raise ValueError("the counts do not form a table: a cell would be negative")
    return out


def prr(a: Any, b: Any, c: Any, d: Any) -> dict[str, np.ndarray]:
    """PRR with its chi-square, without and with Yates' correction."""
    a, b, c, d = _cells(a, b, c, d)
    with np.errstate(divide="ignore", invalid="ignore"):
        value = (a / (a + b)) / (c / (c + d))
    value = np.where((c > 0) & (c + d > 0), value, np.nan)
    pearson, yates = _chi_squares(a, b, c, d)
    return {"PRR": value, "chi_square": pearson, "chi_square_yates": yates}


def ror(a: Any, b: Any, c: Any, d: Any, z: float | None = None) -> dict[str, np.ndarray]:
    """ROR with its confidence interval on the log scale; NaN where any cell is 0.

    The one measure that also takes a table with no case for its product or event (a stratum
    the product never reached): a zero cell leaves it empty."""
    a, b, c, d = _cells(a, b, c, d, margins=False)
    z = float(rulebook.value("ror", "z")) if z is None else float(z)
    filled = (a > 0) & (b > 0) & (c > 0) & (d > 0)
    nan = np.full(a.shape, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_ror = np.log(a) + np.log(d) - np.log(b) - np.log(c)
        se = np.sqrt(1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d)
        return {
            "ROR": np.where(filled, np.exp(log_ror), nan),
            "ROR_lower": np.where(filled, np.exp(log_ror - z * se), nan),
            "ROR_upper": np.where(filled, np.exp(log_ror + z * se), nan),
        }


def expected(a: Any, b: Any, c: Any, d: Any) -> np.ndarray:
    """Cases expected with the product and the event if they were unrelated: (a + b)(a + c) / N."""
    a, b, c, d = _cells(a, b, c, d)
    return (a + b) * (a + c) / (a + b + c + d)


def rrr(a: Any, b: Any, c: Any, d: Any) -> dict[str, np.ndarray]:
    """Observed over expected, and the expected count."""
    e = expected(a, b, c, d)
    with np.errstate(divide="ignore", invalid="ignore"):
        return {"expected": e, "RRR": np.asarray(a, dtype=float) / e}


def ic(a: Any, b: Any, c: Any, d: Any) -> dict[str, np.ndarray]:
    """The information component in its shrinkage form, and IC025."""
    k = float(rulebook.value("ic", "shrinkage"))
    c1, c2 = (float(x) for x in rulebook.value("ic", "ic025_coefficients"))
    e = expected(a, b, c, d)
    shrunk = np.asarray(a, dtype=float) + k
    value = np.log2(shrunk / (e + k))
    return {"IC": value, "IC025": value - c1 * shrunk**-0.5 - c2 * shrunk**-1.5}


def measures(a: Any, b: Any, c: Any, d: Any) -> dict[str, np.ndarray]:
    """Every column of COLUMNS for each table: the cells (whole numbers), then PRR, ROR, RRR
    and IC."""
    counts = np.broadcast_arrays(*(_counts(x) for x in (a, b, c, d)))
    fa, fb, fc, fd = _cells(a, b, c, d)
    out = dict(zip("abcd", counts, strict=True))
    for part in (rrr(fa, fb, fc, fd), prr(fa, fb, fc, fd), ror(fa, fb, fc, fd), ic(fa, fb, fc, fd)):
        out.update(part)
    return {k: out[k] for k in COLUMNS}


def _chi_squares(
    a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    n = a + b + c + d
    margins = (a + b) * (c + d) * (a + c) * (b + d)
    gap = np.abs(a * d - b * c)  # exact: every product is below 2^53 for tables of real size
    with np.errstate(divide="ignore", invalid="ignore"):
        pearson = n * gap**2 / margins
        yates = n * np.maximum(gap - n / 2.0, 0.0) ** 2 / margins
    empty = margins <= 0
    return np.where(empty, np.nan, pearson), np.where(empty, np.nan, yates)


def _counts(values: Any) -> np.ndarray:
    arr = np.asarray(values)
    floats = arr.astype(float)
    if arr.size and (not np.all(np.isfinite(floats)) or np.any(floats % 1 != 0)):
        raise ValueError("counts must be whole numbers")
    return arr.astype(np.int64)


def _cells(
    a: Any, b: Any, c: Any, d: Any, margins: bool = True
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The four cells as floats of one shape; refused when a count is not a whole number of
    zero or more, or (with `margins`) when the product or the event has no case (a + b = 0 or
    a + c = 0)."""
    cells = np.broadcast_arrays(*(_counts(x) for x in (a, b, c, d)))
    if any(np.any(x < 0) for x in cells):
        raise ValueError("a cell is negative; a count of cases cannot be")
    fa, fb, fc, fd = (x.astype(float) for x in cells)
    if margins and (np.any(fa + fb == 0) or np.any(fa + fc == 0)):
        raise ValueError("a table has no case for its product (a + b = 0) or its event (a + c = 0)")
    return fa, fb, fc, fd
