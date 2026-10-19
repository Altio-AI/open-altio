---
rule: ic
line: How much more often an ingredient and a reaction are reported together than expected, where 1 means twice as often, pulled toward no difference when cases are few.
values:
  shrinkage: 0.5
  ic025_coefficients: [3.3, 2.0]
  presets:
    - id: ic025-above-0
      label: IC025 above 0
      source: Noren, Hopstadius and Bate 2013
      default: true
      when:
        - {column: ic025, above: 0}
always_on: true
why_locked: The statistics take no case out of the release; the thresholds you read them against are set on the Statistics tab.
enforced_in:
  - src/open_altio/stats/disproportionality.py
  - tests/stats/test_disproportionality.py
  - tests/stats/test_screen.py
---
# IC: more than expected, in doublings

How many times more often the ingredient and the reaction are reported together than expected, on a doubling scale, pulled towards "no difference" when there are few cases. An IC of 1 means twice as many cases as expected, 2 means four times, and 0 means as expected. IC025 is the lower end of its 95% credibility interval: above 0 means more cases than expected even allowing for chance.

**Formula**, on the table of cases drawn in `prr`:

    expected = (a + b)(a + c) / N
    IC = log2((a + k) / (expected + k)),   k = shrinkage = 0.5
    IC025 = IC - 3.3 (a + k)^(-1/2) - 2 (a + k)^(-3/2)

The two numbers in IC025 are `ic025_coefficients`. Adding k to the observed and to the expected count is the shrinkage: it keeps a single case from giving a huge value. IC025 is a closed-form approximation of the 2.5% point of the gamma credibility interval; on every count from 1 to 10,000 it lies within 0.05 of the exact point, and below it, on the cautious side, from 2 cases on (`tests/stats/test_disproportionality.py`).

**When it is empty:** never, for a pair seen at least once.

**Presets** (`presets`; change any number on the Statistics tab, or set your own):
- **IC025 above 0** (the default), the threshold the WHO Uppsala Monitoring Centre's method reads.

**Source:** Noren GN, Hopstadius J, Bate A. Shrinkage observed-to-expected ratios for robust and transparent large-scale pattern discovery. Statistical Methods in Medical Research 2013;22(1):57-69. The IC itself: Bate A et al. A Bayesian neural network method for adverse drug reaction signal generation. European Journal of Clinical Pharmacology 1998;54:315-321. The closed form for IC025 is the one the DiAna package (Fusaroli et al. 2024) uses.

**Not a signal:** see `prr`. Code: `src/open_altio/stats/disproportionality.py`.
