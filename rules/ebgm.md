---
rule: ebgm
line: How many times more often an ingredient and a reaction are reported together than expected, with small counts pulled toward the usual, so two or three cases cannot look alarming alone.
values:
  fit_on: all_cells
  min_count: 1
  squash_bins_per_decade: 50
  starts:
    - {alpha1: 0.2, beta1: 0.1, alpha2: 2.0, beta2: 4.0, p: 0.3333}
    - {alpha1: 0.2, beta1: 0.06, alpha2: 1.4, beta2: 1.8, p: 0.1}
    - {alpha1: 0.1, beta1: 0.1, alpha2: 10.0, beta2: 10.0, p: 0.2}
    - {alpha1: 0.5, beta1: 0.5, alpha2: 5.0, beta2: 5.0, p: 0.5}
  gradient_tolerance: 1.0e-6
  max_iterations: 250
  agreeing_starts: 2
  agreement_tolerance: 0.01
  parameter_range: [1.0e-4, 1.0e+4]
  weight_range: [1.0e-4, 0.9999]
  quantiles: [0.05, 0.95]
  presets:
    - id: eb05-2-three-cases
      label: EB05 at least 2, at least 3 cases
      source: Szarfman, Machado and O'Neill 2002, with the three cases of Evans, Waller and Davis 2001
      default: true
      when:
        - {column: eb05, at_least: 2}
        - {column: cases, at_least: 3}
    - id: eb05-2
      label: EB05 at least 2
      source: Szarfman, Machado and O'Neill 2002
      when:
        - {column: eb05, at_least: 2}
always_on: true
why_locked: The statistics take no case out of the release; the thresholds you read them against are set on the Statistics tab.
enforced_in:
  - src/open_altio/stats/ebgm/model.py
  - src/open_altio/faers/statistics/scored.py
  - tests/stats/ebgm/test_ebgm_model.py
  - tests/stats/ebgm/test_ebgm_fit.py
  - tests/stats/ebgm/test_ebgm_scores.py
  - tests/stats/test_screen.py
---
# EBGM: more often than expected

EBGM is how many times more often an ingredient and a reaction are reported together than expected, with small counts pulled towards the ratio typical of the whole release, so that two or three cases cannot make a pair look alarming on their own. EB05 and EB95 bound it: there is a 90% chance the true ratio lies between them, and an EB05 of 2 means at least twice as many cases as expected, allowing for chance. It is DuMouchel's Gamma-Poisson Shrinker, written from the papers (`src/open_altio/stats/ebgm/`).

N is the cases naming both (`statistics-cases`). E, the expected count, is worked out within strata of age band, sex and receipt year and summed: in each stratum, the cases naming the ingredient times the cases naming the reaction, over the cases in the stratum. The ratio N/E of every pair is assumed drawn from one prior, a mixture of two gamma distributions; the prior is fitted to the release, and each pair's EBGM is the geometric mean of its ratio given its N and E. A pair with many cases keeps nearly its own ratio; a pair with few is pulled towards the prior.

**Presets** (`presets`; change any number on the Statistics tab, or set your own):
- **EB05 at least 2, at least 3 cases** (the default): the threshold Szarfman, Machado and O'Neill (2002) describe for FDA's screening of its spontaneous reports, with the floor of three cases Evans, Waller and Davis (2001) put beside PRR.
- **EB05 at least 2**: the threshold alone.

A statistic of disproportionate reporting is not a signal and not evidence of cause (`prr`).

## Settings

- **`fit_on`**: `all_cells` fits the prior over every ingredient and reaction cell, the ones never seen (N = 0) included, as DuMouchel (1999) does. `seen_pairs` fits only pairs seen at least `min_count` times, each pair's likelihood conditioned on that, as DuMouchel and Pregibon (2001) do to save time.
- **`min_count`**: used only with `seen_pairs`. 1 means pairs never seen are left out.
- **`squash_bins_per_decade`**: before the fit, cells with the same N whose expected counts fall in the same bin are merged into one weighted point at the bin's mean E. Bins are this many to a factor of ten in E, so 50 merges only expected counts within about 5% of each other. Scores are always computed per pair, never on merged points.
- **`starts`**: the fit runs from each of these starting points, the ones Canida and Ihrie (2017) print.
- **`gradient_tolerance`**, **`max_iterations`**: a start has converged when the largest gradient of the mean negative log-likelihood, on the log scale of the parameters, is below the tolerance.
- **`parameter_range`**, **`weight_range`**: a converged fit with a shape or rate outside the range, or a mixing weight outside its range, is on the edge of the parameter space and does not count.
- **`agreeing_starts`**, **`agreement_tolerance`**: the best converged fit is used only when at least this many converged starts, itself included, agree with it to within this relative difference on every hyperparameter. Otherwise the release carries no EBGM, and its manifest says why and what each start reached.
- **`quantiles`**: the posterior percentiles given beside EBGM (EB05 and EB95).

Every release fits its own prior on its own cases; the manifest records the five hyperparameters, what each start reached and the counts the fit ran over (`statistics` in `manifest.json`).

**Why `all_cells`:** on FAERS (ingredients by reaction, about four million pairs seen) the `seen_pairs` fit has no maximum inside the parameter space: from every start, one component's shape runs to zero, where the truncated negative binomial becomes a log-series. Counted with its hundreds of millions of cells never seen, the table fits cleanly and every start agrees. Squashed, the cells never seen are a few hundred points, so the speed reason for leaving them out does not apply. Fitted this way, the prior puts some weight on a wide component, so it shrinks small counts less than a `seen_pairs` fit would: on the full release to 2026Q2, 4.1% of the pairs seen only twice reach EB05 2 (23,066 of 564,723). The default threshold asks for at least three cases beside it, so those pairs do not crowd the list; 505,571 of the 4,009,745 pairs pass it.

**Why the rest:** the model has no closed-form fit, and a numerical optimiser can stop at a local optimum or on the edge of the space. Several starts that must agree turn a silent bad fit into a reported failure. Squashing makes the fit take seconds over millions of pairs with no visible change in the scores.

**Sources:** DuMouchel W. Bayesian data mining in large frequency tables, with an application to the FDA Spontaneous Reporting System. The American Statistician 1999;53(3):177-190. DuMouchel W, Pregibon D. Empirical Bayes screening for multi-item associations. Proc. KDD 2001:67-76. Canida T, Ihrie J. openEBGM: an R implementation of the Gamma-Poisson Shrinker data mining model. The R Journal 2017;9(2):499-519 (its text and printed example only). Szarfman A, Machado SG, O'Neill RT. Use of screening algorithms and computer systems to efficiently signal higher-than-expected combinations of drugs and events in the US FDA's spontaneous reports database. Drug Safety 2002;25(6):381-392.
