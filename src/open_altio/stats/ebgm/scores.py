"""Each pair's posterior under a fitted prior: its weight on the first component, EBGM, and its
percentiles (EB05 and EB95 by default)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike
from scipy import special

from .model import FitError, Prior, check, log_nb, settings


def posterior_weight(prior: Prior, n: ArrayLike, e: ArrayLike) -> np.ndarray:
    """Q: the posterior probability that a pair's lambda comes from component 1."""
    n_arr, e_arr = check(n, e)
    lf1, _, _ = log_nb(n_arr.astype(float), prior.alpha1, prior.beta1, e_arr)
    lf2, _, _ = log_nb(n_arr.astype(float), prior.alpha2, prior.beta2, e_arr)
    return special.expit(np.log(prior.p) + lf1 - np.log1p(-prior.p) - lf2)


def ebgm(prior: Prior, n: ArrayLike, e: ArrayLike) -> np.ndarray:
    """The posterior geometric mean of lambda for each pair."""
    n_arr, e_arr = check(n, e)
    q = posterior_weight(prior, n_arr, e_arr)
    m1 = special.digamma(prior.alpha1 + n_arr) - np.log(prior.beta1 + e_arr)
    m2 = special.digamma(prior.alpha2 + n_arr) - np.log(prior.beta2 + e_arr)
    return np.exp(q * m1 + (1.0 - q) * m2)


def quantile(
    prior: Prior,
    n: ArrayLike,
    e: ArrayLike,
    prob: float,
    *,
    tol: float = 1e-10,
    max_iterations: int = 60,
) -> np.ndarray:
    """The `prob` percentile of each pair's posterior, by Newton's method kept inside a bracket.

    The answer lies between the two components' own percentiles, so the bracket always holds
    it; a step that would leave the bracket bisects it instead.
    """
    if not 0.0 < prob < 1.0:
        raise ValueError("prob must be between 0 and 1")
    n_arr, e_arr = check(n, e)
    q = posterior_weight(prior, n_arr, e_arr)
    a1, b1 = prior.alpha1 + n_arr, prior.beta1 + e_arr
    a2, b2 = prior.alpha2 + n_arr, prior.beta2 + e_arr
    x1, x2 = special.gammaincinv(a1, prob) / b1, special.gammaincinv(a2, prob) / b2
    lo, hi = np.minimum(x1, x2), np.maximum(x1, x2)
    x = np.clip(q * x1 + (1.0 - q) * x2, lo, hi)
    todo = np.flatnonzero(hi - lo > tol * hi)
    for _ in range(max_iterations):
        if todo.size == 0:
            break
        xi, qi = x[todo], q[todo]
        f = (
            qi * special.gammainc(a1[todo], b1[todo] * xi)
            + (1 - qi) * special.gammainc(a2[todo], b2[todo] * xi)
            - prob
        )
        lo[todo] = np.where(f < 0, xi, lo[todo])
        hi[todo] = np.where(f > 0, xi, hi[todo])
        dens = qi * _gamma_pdf(xi, a1[todo], b1[todo]) + (1 - qi) * _gamma_pdf(
            xi, a2[todo], b2[todo]
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            step = xi - f / dens
        inside = np.isfinite(step) & (step > lo[todo]) & (step < hi[todo])
        nxt = np.where(inside, step, np.sqrt(lo[todo] * hi[todo]))
        done = (np.abs(f) <= tol) | (hi[todo] - lo[todo] <= tol * hi[todo])
        x[todo] = np.where(done, xi, nxt)
        todo = todo[~done]
    if todo.size:
        raise FitError(f"the {prob} percentile did not converge for {todo.size} pair(s)", [])
    return x


def _gamma_pdf(x: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.exp(a * np.log(b) + (a - 1) * np.log(x) - b * x - special.gammaln(a))


def score(
    prior: Prior, n: ArrayLike, e: ArrayLike, quantiles: Sequence[float] | None = None
) -> dict[str, np.ndarray]:
    """EBGM and the rule's percentiles (EB05 and EB95) for each pair."""
    probs = settings()["quantiles"] if quantiles is None else quantiles
    out = {"EBGM": ebgm(prior, n, e)}
    for prob in probs:
        out[f"EB{round(prob * 100):02d}"] = quantile(prior, n, e, prob)
    return out
