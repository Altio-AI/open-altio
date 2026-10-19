"""The likelihood of the Gamma-Poisson Shrinker (src/open_altio/stats/ebgm/model.py), worked by hand
and checked against finite differences."""

from __future__ import annotations

import math

import numpy as np
import pytest

from open_altio.stats import ebgm as g

EULER_GAMMA = 0.5772156649015329
# A prior shaped like a real one: a wide component with high mean, a narrow one near 1.


TYPICAL = g.Prior(alpha1=0.2, beta1=0.06, alpha2=1.4, beta2=1.8, p=0.1)


def one_gamma(alpha: float, beta: float) -> g.Prior:
    """Both components the same, so the prior is a single gamma."""
    return g.Prior(alpha, beta, alpha, beta, 0.5)


# ---------------------------------------------------------------- by hand


def test_marginal_is_the_negative_binomial_worked_by_hand():
    """With shape 1 the marginal is geometric: f(n) = b/(b+E) * (E/(b+E))^n.
    b = 2, E = 1, n = 2: (2/3)(1/3)^2 = 2/27."""
    nll, _ = g.neg_log_likelihood(one_gamma(1.0, 2.0), [2], [1.0], min_count=0)
    assert nll == pytest.approx(-math.log(2 / 27), rel=1e-12)


def test_likelihood_is_conditioned_on_n_at_least_min_count():
    """P(N = 2 | N >= 1) = f(2) / (1 - f(0)) = (2/27) / (1 - 2/3) = 2/9."""
    nll, _ = g.neg_log_likelihood(one_gamma(1.0, 2.0), [2], [1.0], min_count=1)
    assert nll == pytest.approx(-math.log(2 / 9), rel=1e-12)


def test_conditioned_probabilities_sum_to_one():
    prior, e = TYPICAL, 0.7
    n = np.arange(1, 4000)
    total = sum(math.exp(-g.neg_log_likelihood(prior, [k], [e], min_count=1)[0]) for k in n[:60])
    tail = np.exp(
        -np.array([g.neg_log_likelihood(prior, [k], [e], min_count=1)[0] for k in n[60:]])
    )
    assert total + tail.sum() == pytest.approx(1.0, abs=1e-6)


def test_gradient_matches_finite_differences():
    rng = np.random.default_rng(3)
    n, e, w = rng.integers(1, 30, 64), rng.uniform(0.01, 8, 64), rng.uniform(1, 4, 64)
    prior = g.Prior(0.4, 0.2, 2.0, 1.5, 0.3)
    _, grad = g.neg_log_likelihood(prior, n, e, w, min_count=1)
    for i, key in enumerate(g.PARAMS):
        h = 1e-6 * getattr(prior, key)
        up = g.neg_log_likelihood(
            g.Prior(**{**prior.as_dict(), key: getattr(prior, key) + h}), n, e, w, 1
        )[0]
        down = g.neg_log_likelihood(
            g.Prior(**{**prior.as_dict(), key: getattr(prior, key) - h}), n, e, w, 1
        )[0]
        assert grad[i] == pytest.approx((up - down) / (2 * h), rel=1e-5)


# ---------------------------------------------------------------- properties
