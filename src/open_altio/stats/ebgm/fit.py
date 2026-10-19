"""The prior fitted by maximum likelihood from every starting point the rule lists, and
accepted only when enough of them agree inside the parameter space."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from scipy import optimize, special

from .expected import squash
from .model import PARAMS, Fit, FitError, Prior, check, neg_log_likelihood, settings


def _to_x(prior: Prior) -> np.ndarray:
    return np.array(
        [
            np.log(prior.alpha1),
            np.log(prior.beta1),
            np.log(prior.alpha2),
            np.log(prior.beta2),
            special.logit(prior.p),
        ]
    )


def _from_x(x: np.ndarray) -> Prior:
    a1, b1, a2, b2 = (float(v) for v in np.exp(x[:4]))
    return Prior(a1, b1, a2, b2, float(special.expit(x[4])))


def _points(
    n: np.ndarray,
    e: np.ndarray,
    unseen_e: ArrayLike | None,
    unseen_w: ArrayLike | None,
    cfg: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """The squashed points the fit runs over, and the min_count they are conditioned on."""
    bins = cfg["squash_bins_per_decade"]
    if cfg["fit_on"] == "all_cells":
        if unseen_e is None or unseen_w is None:
            raise ValueError("fit_on all_cells needs the unseen cells (unseen_cells)")
        sn, se, sw = squash(n, e, bins)
        unseen = np.asarray(unseen_e, dtype=float)
        un, ue, uw = squash(np.zeros(len(unseen), dtype=np.int64), unseen, bins, unseen_w)
        return np.r_[sn, un], np.r_[se, ue], np.r_[sw, uw], 0
    if cfg["fit_on"] == "seen_pairs":
        if unseen_e is not None:
            raise ValueError("fit_on seen_pairs leaves unseen cells out; do not pass them")
        min_count = int(cfg["min_count"])
        keep = n >= min_count
        return (*squash(n[keep], e[keep], bins), min_count)
    raise ValueError(f"fit_on must be all_cells or seen_pairs, not {cfg['fit_on']!r}")


def fit_prior(
    n: ArrayLike,
    e: ArrayLike,
    unseen_e: ArrayLike | None = None,
    unseen_w: ArrayLike | None = None,
    *,
    config: Mapping[str, Any] | None = None,
) -> Fit:
    """Fit the prior by maximum likelihood from every starting point in the rule.

    The rule's `fit_on` says over what:
    - `all_cells` (DuMouchel 1999): the pairs seen, and every cell never seen, given as
      `unseen_e` and `unseen_w` (from `unseen_cells`), with N = 0.
    - `seen_pairs` (DuMouchel and Pregibon 2001): only pairs with N >= `min_count`, each pair's
      likelihood conditioned on N >= `min_count`.
    Points are squashed first. Raises FitError when too few starts converge to the same answer
    inside the parameter space.
    """
    cfg = settings() if config is None else dict(config)
    n_arr, e_arr = check(n, e)
    sn, se, sw, min_count = _points(n_arr, e_arr, unseen_e, unseen_w, cfg)
    if len(sn) == 0:
        raise FitError("no pairs to fit", [])
    total = sw.sum()

    def objective(x: np.ndarray) -> tuple[float, np.ndarray]:
        prior = _from_x(x)
        value, grad = neg_log_likelihood(prior, sn, se, sw, min_count)
        to_x = np.array(
            [prior.alpha1, prior.beta1, prior.alpha2, prior.beta2, prior.p * (1.0 - prior.p)]
        )
        return value / total, grad * to_x / total

    lo, hi = cfg["parameter_range"]
    wlo, whi = cfg["weight_range"]
    gtol = float(cfg["gradient_tolerance"])
    starts = []
    for start in cfg["starts"]:
        x0 = _to_x(Prior(**{k: float(start[k]) for k in PARAMS}))
        with np.errstate(all="ignore"):
            res = optimize.minimize(
                objective,
                x0,
                jac=True,
                method="BFGS",
                options={"gtol": gtol, "maxiter": int(cfg["max_iterations"])},
            )
            value, grad = objective(res.x)
        prior = _from_x(res.x).canonical()
        finite = bool(np.isfinite(value) and np.all(np.isfinite(grad)))
        shapes = (prior.alpha1, prior.beta1, prior.alpha2, prior.beta2)
        starts.append(
            {
                "start": {k: float(start[k]) for k in PARAMS},
                "estimate": prior.as_dict(),
                "neg_log_lik": value * total,
                "max_gradient": float(np.max(np.abs(grad))),
                "iterations": int(res.nit),
                "converged": finite and float(np.max(np.abs(grad))) <= gtol,
                "inside": all(lo <= v <= hi for v in shapes) and wlo <= prior.p <= whi,
                "message": str(res.message),
            }
        )
    good = [s for s in starts if s["converged"] and s["inside"]]
    if not good:
        raise FitError("no starting point converged inside the parameter space", starts)
    best = min(good, key=lambda s: s["neg_log_lik"])
    tol = float(cfg["agreement_tolerance"])
    agree = [
        s
        for s in good
        if all(
            abs(s["estimate"][k] - best["estimate"][k]) <= tol * abs(best["estimate"][k])
            for k in PARAMS
        )
    ]
    for s in starts:
        s["agrees_with_best"] = s in agree
    if len(agree) < int(cfg["agreeing_starts"]):
        raise FitError(
            f"only {len(agree)} converged start(s) agree with the best fit; "
            f"{cfg['agreeing_starts']} needed",
            starts,
        )
    return Fit(
        prior=Prior(**best["estimate"]),
        neg_log_lik=best["neg_log_lik"],
        points=len(sn),
        cells=float(sw.sum()),
        fit_on=cfg["fit_on"],
        min_count=min_count,
        starts=starts,
    )
