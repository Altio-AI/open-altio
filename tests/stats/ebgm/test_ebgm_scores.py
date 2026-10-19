"""Each pair's posterior (src/open_altio/stats/ebgm/scores.py), checked three ways: cases worked
by hand, properties any correct score must have, and the worked example printed in Canida and
Ihrie (2017), pages 506 to 508: the CAERS example's hyperparameters and the scores printed for
its first three pairs."""

from __future__ import annotations

import math

import numpy as np
import pytest

from open_altio import rulebook
from open_altio.stats import ebgm as g

EULER_GAMMA = 0.5772156649015329
# A prior shaped like a real one: a wide component with high mean, a narrow one near 1.


TYPICAL = g.Prior(alpha1=0.2, beta1=0.06, alpha2=1.4, beta2=1.8, p=0.1)


def one_gamma(alpha: float, beta: float) -> g.Prior:
    """Both components the same, so the prior is a single gamma."""
    return g.Prior(alpha, beta, alpha, beta, 0.5)


# ---------------------------------------------------------------- by hand


def test_ebgm_of_a_single_gamma_posterior_worked_by_hand():
    """Prior Gamma(1, 1), N = 1, E = 1: the posterior is Gamma(2, rate 2), whose
    geometric mean is exp(digamma(2)) / 2 = exp(1 - Euler's gamma) / 2."""
    got = g.ebgm(one_gamma(1.0, 1.0), [1], [1.0])[0]
    assert got == pytest.approx(math.exp(1 - EULER_GAMMA) / 2, rel=1e-12)


def test_posterior_weight_and_ebgm_of_a_mixture_worked_by_hand():
    """Prior 0.5 Gamma(1, 1) + 0.5 Gamma(1, 3), N = 1, E = 1.
    f1(1) = 1/2 * 1/2 = 1/4, f2(1) = 3/4 * 1/4 = 3/16, so Q = 4/7, and
    EBGM = exp(digamma(2)) * 2^-Q * 4^-(1-Q) = exp(1 - gamma) * 2^(-10/7)."""
    prior = g.Prior(1.0, 1.0, 1.0, 3.0, 0.5)
    assert g.posterior_weight(prior, [1], [1.0])[0] == pytest.approx(4 / 7, rel=1e-12)
    assert g.ebgm(prior, [1], [1.0])[0] == pytest.approx(
        math.exp(1 - EULER_GAMMA) * 2 ** (-10 / 7), rel=1e-12
    )


@pytest.mark.parametrize("prob", [0.05, 0.5, 0.95])
def test_percentile_of_a_single_gamma_posterior_solves_its_cdf(prob):
    """Posterior Gamma(2, rate 2) has CDF 1 - exp(-2x)(1 + 2x)."""
    x = g.quantile(one_gamma(1.0, 1.0), [1], [1.0], prob)[0]
    assert 1 - math.exp(-2 * x) * (1 + 2 * x) == pytest.approx(prob, abs=1e-10)


GRID_N = np.repeat(
    np.array([1, 2, 3, 5, 10, 30, 100, 1000]), 6
)  # rule-literal-ok: grid, not a rule value


GRID_E = np.tile(
    np.array([1e-4, 0.01, 0.3, 1.0, 10.0, 300.0]), 8
)  # rule-literal-ok: grid, not a rule value


def test_eb05_at_or_below_ebgm_at_or_below_eb95():
    s = g.score(TYPICAL, GRID_N, GRID_E, quantiles=[0.05, 0.95])
    assert np.all(s["EB05"] <= s["EBGM"]) and np.all(s["EBGM"] <= s["EB95"])
    assert np.all(s["EB05"] > 0)


def test_small_counts_are_shrunk_towards_one():
    """A pair seen once or twice with a tiny E has a huge N/E; EBGM pulls most of the way back."""
    n = np.array([1, 1, 1, 2])
    e = np.array([0.001, 0.01, 0.1, 0.001])
    got = g.ebgm(TYPICAL, n, e)
    assert np.all((got > 1) & (np.log(got) < 0.5 * np.log(n / e)))
    rare = g.ebgm(TYPICAL, [1], [50.0])[0]  # seen once where 50 were expected: N/E = 0.02
    assert 0.02 < rare < 1


def test_shrinkage_fades_as_n_grows_at_a_fixed_ratio():
    n = np.array([1, 3, 10, 30, 100, 1000, 10000])  # rule-literal-ok: counts, not rule values
    e = n / 5.0  # N/E = 5 throughout
    got = g.ebgm(TYPICAL, n, e)
    gap = np.abs(np.log(got / 5.0))
    assert np.all(np.diff(gap) < 0)
    assert got[-1] == pytest.approx(5.0, rel=0.01)


def test_score_reads_its_percentiles_from_the_rule():
    probs = rulebook.value("ebgm", "quantiles")
    s = g.score(TYPICAL, [3], [0.5])
    assert set(s) == {"EBGM"} | {f"EB{round(p * 100):02d}" for p in probs}


def test_scores_refuse_a_non_positive_expected_count():
    with pytest.raises(ValueError, match="positive"):
        g.ebgm(TYPICAL, [1, 2], [0.5, 0.0])


# ---------------------------------------------------------------- the paper's worked example
# Canida and Ihrie (2017), The R Journal 9(2), pages 506 to 508: the CAERS example's
# hyperparameters, and the scores printed for its first three pairs (two decimals).


CAERS_PRIOR = g.Prior(
    alpha1=3.25118662, beta1=0.39976698, alpha2=2.02696130, beta2=1.90893277, p=0.06539553
)


CAERS_E = [0.0360548272, 0.0038736591, 0.0002979738]


CAERS_PRINTED = {
    "EBGM": [2.23, 2.58, 2.63],
    "EB05": [0.49, 0.52, 0.52],
    "EB95": [13.85, 15.78, 16.02],
}


@pytest.mark.parametrize("column", sorted(CAERS_PRINTED))
def test_reproduces_the_printed_caers_example(column):
    s = g.score(CAERS_PRIOR, [1, 1, 1], CAERS_E, quantiles=[0.05, 0.95])
    assert s[column] == pytest.approx(CAERS_PRINTED[column], abs=0.005 + 1e-9)


def test_caers_example_10th_and_90th_percentiles():
    """The paper also prints QUANT_10 (0.67, 0.71, 0.72) and QUANT_90 (10.79, 12.62, 12.83).
    Ours agree to two decimals except the third QUANT_10, 0.714: the mixture's CDF there
    is 0.1000 and at 0.72 it is 0.1017, so the printed 0.72 looks like a coarse bisection."""
    s = g.score(CAERS_PRIOR, [1, 1, 1], CAERS_E, quantiles=[0.10, 0.90])
    assert s["EB10"] == pytest.approx([0.67, 0.71, 0.72], abs=0.01)
    assert s["EB90"] == pytest.approx([10.79, 12.62, 12.83], abs=0.005 + 1e-9)


# ---------------------------------------------------------------- fitting
