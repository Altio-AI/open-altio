"""Expected counts within strata, for the pairs seen and for every cell never seen, and data
squashing (DuMouchel and Pregibon 2001), which merges cells the fit cannot tell apart.

A table here is any mapping of column name to values: a dict of lists, a pandas DataFrame, a
pyarrow table's `to_pydict()`. Keys may be any hashable values; integer ids are fastest.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from .model import check

Table = Mapping[str, ArrayLike]


def expected_counts(
    pairs: Table, product_strata: Table, event_strata: Table, strata: Table, chunk: int = 20_000
) -> dict[str, np.ndarray]:
    """N and E per pair, from counts of distinct cases.

    pairs:          product, event, n   (cases naming both, all strata together)
    product_strata: product, stratum, n (cases in the stratum naming the product)
    event_strata:   event, stratum, n   (cases in the stratum naming the event)
    strata:         stratum, n          (cases in the stratum)

    E sums over every stratum, including those where the pair itself was never seen. Returns
    the columns product, event, N and E.
    """
    pi, ei, a, b = _margins(pairs, product_strata, event_strata, strata)
    e = np.empty(len(pi))
    for lo in range(0, len(pi), chunk):
        hi = lo + chunk
        e[lo:hi] = np.einsum("ks,ks->k", a[pi[lo:hi]], b[ei[lo:hi]])
    if np.any(e <= 0):
        raise ValueError("a pair's product or event has no cases in any stratum")
    return {
        "product": _column(pairs, "product"),
        "event": _column(pairs, "event"),
        "N": np.asarray(pairs["n"], dtype=np.int64),
        "E": e,
    }


def unseen_cells(
    pairs: Table,
    product_strata: Table,
    event_strata: Table,
    strata: Table,
    bins_per_decade: float,
    block: int = 500,
) -> tuple[np.ndarray, np.ndarray]:
    """Every product and event cell never seen together, squashed: (mean E, weight) per bin.

    The table has a cell for each product and each event; those not in `pairs` have N = 0.
    Cells with E = 0 (no stratum holds both) are left out: the model gives them N = 0 for
    certain, so they add nothing to the likelihood. Same inputs as `expected_counts`; bins as
    `squash`.
    """
    pi, ei, a, b = _margins(pairs, product_strata, event_strata, strata)
    order = np.argsort(pi, kind="stable")
    pi, ei = pi[order], ei[order]
    totals: dict[int, list[float]] = {}
    for lo in range(0, a.shape[0], block):
        hi = min(lo + block, a.shape[0])
        cells = a[lo:hi] @ b.T
        seen = slice(*np.searchsorted(pi, [lo, hi]))
        cells[pi[seen] - lo, ei[seen]] = 0.0
        e = cells[cells > 0]
        bins, inverse = np.unique(
            np.floor(np.log10(e) * bins_per_decade).astype(np.int64), return_inverse=True
        )
        counts = np.bincount(inverse, minlength=len(bins))
        sums = np.bincount(inverse, weights=e, minlength=len(bins))
        for k, c, t in zip(bins.tolist(), counts.tolist(), sums.tolist(), strict=True):
            acc = totals.setdefault(k, [0.0, 0.0])
            acc[0] += c
            acc[1] += t
    w = np.array([v[0] for v in totals.values()])
    mean_e = np.array([v[1] for v in totals.values()]) / np.maximum(w, 1.0)
    return mean_e, w


def squash(
    n: ArrayLike, e: ArrayLike, bins_per_decade: float, w: ArrayLike | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Merge points with the same N and E in the same bin on the log scale.

    Returns (N, mean E, weight) per merged point; `w` weights the input points (1 each by
    default). A bin is 1/bins_per_decade of a factor of ten wide, so only expected counts within
    a few percent merge.
    """
    n_arr, e_arr = check(n, e)
    weights = np.ones(len(n_arr)) if w is None else np.asarray(w, dtype=float)
    b = np.floor(np.log10(e_arr) * bins_per_decade).astype(np.int64)
    uniq, inverse = np.unique(np.stack([n_arr, b], axis=1), axis=0, return_inverse=True)
    inverse = inverse.ravel()
    weight = np.bincount(inverse, weights=weights, minlength=len(uniq))
    mean_e = np.bincount(inverse, weights=weights * e_arr, minlength=len(uniq)) / weight
    return uniq[:, 0], mean_e, weight


def _margins(
    pairs: Table, product_strata: Table, event_strata: Table, strata: Table
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Each pair's product and event row, and the dense margins:
    a[product, s] = n(product, s) / n(s), b[event, s] = n(event, s)."""
    s_keys, s_n = _column(strata, "stratum"), np.asarray(strata["n"], dtype=float)
    s_index = {k: i for i, k in enumerate(s_keys.tolist())}
    if len(s_index) != len(s_keys) or np.any(s_n <= 0):
        raise ValueError("strata must list each stratum once with a positive count")
    pi, prod_index = _codes(_column(pairs, "product"), _column(product_strata, "product"))
    ei, event_index = _codes(_column(pairs, "event"), _column(event_strata, "event"))
    a = _dense(product_strata, "product", prod_index, s_index) / s_n
    b = _dense(event_strata, "event", event_index, s_index)
    return pi, ei, a, b


def _column(table: Table, name: str) -> np.ndarray:
    return np.asarray(table[name], dtype=object)


def _codes(pair_keys: np.ndarray, margin_keys: np.ndarray) -> tuple[np.ndarray, dict[Any, int]]:
    """Each pair's row in the margin table, and the margin keys' row numbers."""
    index = {k: i for i, k in enumerate(dict.fromkeys(margin_keys.tolist()))}
    try:
        codes = np.fromiter(
            (index[k] for k in pair_keys.tolist()), dtype=np.int64, count=len(pair_keys)
        )
    except KeyError as exc:
        raise ValueError(f"{exc.args[0]!r} is in a pair but has no stratum counts") from None
    return codes, index


def _dense(table: Table, key: str, index: dict[Any, int], s_index: dict[Any, int]) -> np.ndarray:
    out = np.zeros((len(index), len(s_index)))
    rows = np.fromiter((index[k] for k in _column(table, key).tolist()), dtype=np.int64)
    try:
        cols = np.fromiter((s_index[k] for k in _column(table, "stratum").tolist()), dtype=np.int64)
    except KeyError as exc:
        raise ValueError(f"stratum {exc.args[0]!r} is not in strata") from None
    np.add.at(out, (rows, cols), np.asarray(table["n"], dtype=float))
    return out
