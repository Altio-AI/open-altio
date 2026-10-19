"""The two-gamma prior, the likelihood of counts under it, and the checks every function here
makes of the counts it is given (the model is in the package's docstring)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from scipy import special

from open_altio import rulebook

RULE = "ebgm"
PARAMS = ("alpha1", "beta1", "alpha2", "beta2", "p")


class FitError(Exception):
    """The hyperparameters could not be fitted, so no pair is scored. `starts` holds what each
    starting point reached, so the failure can be read."""

    def __init__(self, message: str, starts: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.starts = starts


@dataclass(frozen=True)
class Prior:
    """The two-gamma prior (shape, rate). Component 1 is the one with the larger mean."""

    alpha1: float
    beta1: float
    alpha2: float
    beta2: float
    p: float

    def as_dict(self) -> dict[str, float]:
        return {k: float(getattr(self, k)) for k in PARAMS}

    def canonical(self) -> Prior:
        """The same prior with its components in the agreed order, so two fits compare."""
        if self.alpha1 / self.beta1 >= self.alpha2 / self.beta2:
            return self
        return Prior(self.alpha2, self.beta2, self.alpha1, self.beta1, 1.0 - self.p)


@dataclass(frozen=True)
class Fit:
    prior: Prior
    neg_log_lik: float  # over the fitted points, conditioned on N >= min_count when it is above 0
    points: int  # squashed points fitted
    cells: float  # the cells those points stand for
    fit_on: str  # all_cells or seen_pairs
    min_count: int  # 0 when the cells never seen are in the fit
    starts: list[dict[str, Any]] = field(default_factory=list)


def settings() -> dict[str, Any]:
    """Every value of the model's rule (rules/ebgm.md)."""
    return dict(rulebook.rule(RULE).values)


def check(n: ArrayLike, e: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    """N as whole numbers and E as positive numbers, one each per pair; refused otherwise."""
    n_arr, e_arr = np.asarray(n), np.asarray(e, dtype=float)
    if n_arr.shape != e_arr.shape or n_arr.ndim != 1:
        raise ValueError("N and E must be one-dimensional and the same length")
    if np.any(~np.isfinite(e_arr)) or np.any(e_arr <= 0):
        raise ValueError("every E must be a positive number")
    if n_arr.size and (np.any(n_arr < 0) or np.any(np.asarray(n_arr, dtype=float) % 1 != 0)):
        raise ValueError("every N must be a whole number, zero or more")
    return n_arr.astype(np.int64), e_arr


def log_nb(
    n: np.ndarray, a: float, b: float, e: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """log f(n; a, b, E) and its derivatives in a and b."""
    log1p_e_b = np.log1p(e / b)
    lf = (
        special.gammaln(a + n)
        - special.gammaln(a)
        - special.gammaln(n + 1.0)
        - n * np.log1p(b / e)
        - a * log1p_e_b
    )
    da = special.digamma(a + n) - special.digamma(a) - log1p_e_b
    db = (a * e / b - n) / (e + b)
    return lf, da, db


def _log_mixture(n: np.ndarray, e: np.ndarray, prior: Prior) -> tuple[np.ndarray, np.ndarray]:
    """log m(n) and its gradient in (alpha1, beta1, alpha2, beta2, p), one row per point."""
    lf1, da1, db1 = log_nb(n, prior.alpha1, prior.beta1, e)
    lf2, da2, db2 = log_nb(n, prior.alpha2, prior.beta2, e)
    l1, l2 = np.log(prior.p) + lf1, np.log1p(-prior.p) + lf2
    lm = np.logaddexp(l1, l2)
    r1, r2 = np.exp(l1 - lm), np.exp(l2 - lm)
    dp = np.exp(lf1 - lm) - np.exp(lf2 - lm)
    return lm, np.stack([r1 * da1, r1 * db1, r2 * da2, r2 * db2, dp])


def _log1mexp(x: np.ndarray) -> np.ndarray:
    """log(1 - exp(x)) for x <= 0, accurate at both ends."""
    return np.where(x > -np.log(2.0), np.log(-np.expm1(x)), np.log1p(-np.exp(x)))


def neg_log_likelihood(
    prior: Prior,
    n: ArrayLike,
    e: ArrayLike,
    w: ArrayLike | None = None,
    min_count: int = 1,
) -> tuple[float, np.ndarray]:
    """The summed negative log-likelihood of the points, each conditioned on N >= min_count,
    and its gradient in (alpha1, beta1, alpha2, beta2, p)."""
    n_arr, e_arr = check(n, e)
    weights = np.ones(len(n_arr)) if w is None else np.asarray(w, dtype=float)
    if np.any(n_arr < min_count):
        raise ValueError(f"every N must be at least min_count={min_count}")
    ll, grad = _log_mixture(n_arr.astype(float), e_arr, prior)
    if min_count > 0:
        below = [
            _log_mixture(np.full(len(n_arr), float(k)), e_arr, prior) for k in range(min_count)
        ]
        log_below = np.logaddexp.reduce(np.stack([lm for lm, _ in below]), axis=0)
        log_rest = _log1mexp(np.minimum(log_below, 0.0))
        # d log(1 - T) = -dT / (1 - T), with dT = sum_k m(k) dlog m(k)
        d_below = sum(np.exp(lm - log_rest) * g for lm, g in below)
        ll = ll - log_rest
        grad = grad + d_below
    return float(-(weights * ll).sum()), -(grad * weights).sum(axis=1)
