"""DuMouchel's Gamma-Poisson Shrinker: EBGM, EB05 and EB95 for pairs of items.

    ne = expected_counts(pairs, product_strata, event_strata, strata)   # N and E per pair seen
    unseen = unseen_cells(pairs, product_strata, event_strata, strata,
                          settings()["squash_bins_per_decade"])        # every cell never seen
    fit = fit_prior(ne["N"], ne["E"], *unseen)                         # FitError if it cannot
    scores = score(fit.prior, ne["N"], ne["E"])                        # EBGM, EB05, EB95

For each pair of items (here an ingredient and a reaction) N is the number of cases naming
both, and E the number expected if the two were independent within strata of the cases:

    E = sum over strata s of  n(product, s) * n(event, s) / n(s)

The model (DuMouchel 1999):

    N | lambda  ~  Poisson(lambda * E)
    lambda      ~  P Gamma(alpha1, beta1) + (1 - P) Gamma(alpha2, beta2)     (shape, rate)

so N is a mixture of two negative binomials,

    f(n; a, b, E) = Gamma(a + n) / (Gamma(a) n!) * (E / (E + b))^n * (b / (E + b))^a,

and given N = n, lambda is again a two-gamma mixture, with shapes a_i + n, rates b_i + E, and
weight on the first component

    Q = P f(n; alpha1, beta1, E) / (P f(n; alpha1, beta1, E) + (1 - P) f(n; alpha2, beta2, E)).

The scores read that posterior:

    EBGM = exp(E[log lambda | N = n])
         = exp(Q (digamma(alpha1 + n) - log(beta1 + E))
               + (1 - Q) (digamma(alpha2 + n) - log(beta2 + E)))
    EB05, EB95 = its 5th and 95th percentiles, solved numerically.

The five hyperparameters are fitted by maximum likelihood. The rule's `fit_on` says over what:

- `all_cells` (DuMouchel 1999): every cell of the product by event table, the cells never seen
  (N = 0) included. Their E comes from the same margins (`unseen_cells`).
- `seen_pairs` (DuMouchel and Pregibon 2001): only pairs seen at least `min_count` times, each
  pair's likelihood conditioned on that:

      P(N = n | N >= n*) = m(n) / (1 - sum_{k < n*} m(k)),   m = P f1 + (1 - P) f2.

  On FAERS this has no maximum inside the parameter space: the likelihood keeps rising as one
  component's shape goes to zero (the truncated negative binomial tends to a log-series).

Over millions of cells the fit is made fast by data squashing (DuMouchel and Pregibon 2001):
cells with the same N and nearly the same E are merged into one point at their mean E,
weighted by how many were merged. Scores are always computed per pair. The fit runs from
several starting points and is accepted only when enough of them converge, inside the parameter
space, to the same answer (`FitError` otherwise). Every setting is read from `rules/ebgm.md`.

Sources (papers only; no implementation's code was read):
- DuMouchel W. (1999). Bayesian data mining in large frequency tables, with an application to
  the FDA Spontaneous Reporting System. The American Statistician 53(3):177-190. The model, the
  negative binomial marginal, the posterior, EBGM and the stratified expected count, worked from
  its equations as Canida and Ihrie (2017) and the review below restate them.
- DuMouchel W., Pregibon D. (2001). Empirical Bayes screening for multi-item associations. Proc.
  KDD 2001, 67-76. Leaving out small counts with an adjusted likelihood, and data squashing, as
  Canida and Ihrie (2017) describe them. The conditioning above is the exact conditional
  probability under the model, derived here.
- Canida T., Ihrie J. (2017). openEBGM: An R Implementation of the Gamma-Poisson Shrinker Data
  Mining Model. The R Journal 9(2):499-519. The paper's text and printed output only: the model
  summary, the description of squashing, the starting points, and the worked example the tests
  reproduce.
- Tan Y. et al. (2026). A Review of Statistical Methods for Spontaneous Reporting System Data
  Mining. arXiv:2604.18898, section 2.3.2. Its printed negative binomial has the two exponents
  swapped; the form above is derived from the Poisson and the gamma.
- U.S. FDA. Data Mining at FDA (white paper): EB05 and EB95 as the lower and upper 90% limits
  of EBGM.
"""

from .expected import expected_counts, squash, unseen_cells
from .fit import fit_prior
from .model import PARAMS, RULE, Fit, FitError, Prior, neg_log_likelihood, settings
from .scores import ebgm, posterior_weight, quantile, score

__all__ = [
    "PARAMS",
    "RULE",
    "Fit",
    "FitError",
    "Prior",
    "ebgm",
    "expected_counts",
    "fit_prior",
    "neg_log_likelihood",
    "posterior_weight",
    "quantile",
    "score",
    "settings",
    "squash",
    "unseen_cells",
]
