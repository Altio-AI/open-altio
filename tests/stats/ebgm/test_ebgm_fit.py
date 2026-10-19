"""The prior's fit (src/open_altio/stats/ebgm/fit.py) on tables drawn from the model itself: it
finds the prior they were drawn from, and reports a table it cannot fit instead of scoring it."""

from __future__ import annotations

import numpy as np
import pytest

from open_altio import rulebook
from open_altio.stats import ebgm as g


def simulate(prior: g.Prior, cells: int, seed: int):
    """A table drawn from the model itself: the pairs seen (N, E), and the E of the cells never
    seen."""
    rng = np.random.default_rng(seed)
    e = 10 ** rng.uniform(-2, 1, cells)
    first = rng.random(cells) < prior.p
    lam = np.where(
        first,
        rng.gamma(prior.alpha1, 1 / prior.beta1, cells),
        rng.gamma(prior.alpha2, 1 / prior.beta2, cells),
    )
    n = rng.poisson(lam * e)
    return n[n >= 1], e[n >= 1], e[n == 0]


TRUE = g.Prior(alpha1=2.0, beta1=0.5, alpha2=5.0, beta2=5.0, p=0.1)


@pytest.fixture(scope="module")
def simulated():
    return simulate(TRUE, cells=200_000, seed=7)


def fit_all_cells(seen_n, seen_e, unseen_e, **config):
    return g.fit_prior(
        seen_n,
        seen_e,
        unseen_e,
        np.ones(len(unseen_e)),
        config={**g.settings(), **config, "fit_on": "all_cells"},
    )


def fit_seen_pairs(seen_n, seen_e, **config):
    return g.fit_prior(seen_n, seen_e, config={**g.settings(), "fit_on": "seen_pairs", **config})


def assert_recovers(fit, seen_n, seen_e):
    assert fit.prior.p == pytest.approx(TRUE.p, abs=0.03)
    assert fit.prior.alpha2 / fit.prior.beta2 == pytest.approx(1.0, rel=0.05)
    assert fit.prior.alpha1 / fit.prior.beta1 == pytest.approx(4.0, rel=0.15)
    assert g.ebgm(fit.prior, seen_n, seen_e) == pytest.approx(
        g.ebgm(TRUE, seen_n, seen_e), rel=0.05
    )
    assert all(s["converged"] and s["inside"] and s["agrees_with_best"] for s in fit.starts)


def test_fit_over_all_cells_recovers_the_prior_a_table_was_drawn_from(simulated):
    seen_n, seen_e, unseen_e = simulated
    fit = fit_all_cells(seen_n, seen_e, unseen_e)
    assert fit.fit_on == "all_cells" and fit.min_count == 0
    assert fit.cells == len(seen_n) + len(unseen_e) and fit.points < fit.cells
    assert_recovers(fit, seen_n, seen_e)


def test_fit_over_seen_pairs_conditioned_recovers_it_too(simulated):
    seen_n, seen_e, _ = simulated
    fit = fit_seen_pairs(seen_n, seen_e)
    assert fit.min_count == rulebook.value("ebgm", "min_count") and fit.cells == len(seen_n)
    assert_recovers(fit, seen_n, seen_e)


def test_the_rule_chooses_what_the_fit_runs_on(simulated):
    seen_n, seen_e, unseen_e = simulated
    fit_on = rulebook.value("ebgm", "fit_on")
    if fit_on == "all_cells":
        with pytest.raises(ValueError, match="unseen cells"):
            g.fit_prior(seen_n, seen_e)
    else:
        with pytest.raises(ValueError, match="do not pass"):
            g.fit_prior(seen_n, seen_e, unseen_e, np.ones(len(unseen_e)))


def test_squashing_barely_moves_the_fit(simulated):
    seen_n, seen_e, unseen_e = simulated
    squashed = fit_all_cells(seen_n, seen_e, unseen_e).prior.as_dict()
    unsquashed = fit_all_cells(seen_n, seen_e, unseen_e, squash_bins_per_decade=1e9).prior.as_dict()
    assert squashed == pytest.approx(unsquashed, rel=0.01)


def test_ignoring_the_unseen_cells_biases_the_fit(simulated):
    """Fitting the seen pairs as though zero counts could not happen inflates the high component."""
    seen_n, seen_e, _ = simulated
    naive = fit_seen_pairs(seen_n, seen_e, min_count=0).prior
    assert abs(naive.p - TRUE.p) > 0.03


def test_a_table_the_model_cannot_fit_is_reported_not_scored():
    """Every pair seen once where one was expected: the best prior is on the edge of the space."""
    with pytest.raises(g.FitError, match="converged") as caught:
        fit_seen_pairs(np.ones(1000, dtype=int), np.ones(1000))  # rule-literal-ok: table size
    assert len(caught.value.starts) == len(rulebook.value("ebgm", "starts"))
    assert not any(s["inside"] for s in caught.value.starts)


def test_starts_that_do_not_agree_are_reported(simulated):
    seen_n, seen_e, unseen_e = simulated
    with pytest.raises(g.FitError, match="agree"):
        fit_all_cells(seen_n, seen_e, unseen_e, agreement_tolerance=0.0)
