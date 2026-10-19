---
rule: rrr
line: The cases that report an ingredient and a reaction together, divided by the number expected if the two had nothing to do with each other.
values:
  presets: []
  own:
    - {column: rrr, at_least: 2}
    - {column: cases, at_least: 3}
always_on: true
why_locked: The statistics take no case out of the release; the thresholds you read them against are set on the Statistics tab.
enforced_in:
  - src/open_altio/stats/disproportionality.py
  - tests/stats/test_disproportionality.py
  - tests/stats/test_screen.py
---
# RRR: cases against expected

How many cases report the ingredient and the reaction together, divided by how many would if the two had nothing to do with each other. An RRR of 3 means three times as many cases as expected.

**Formula**, on the table of cases drawn in `prr`:

    expected = (a + b)(a + c) / N,   N = a + b + c + d
    RRR = a / expected

This expected count is the crude one, over the whole table. EBGM's expected count is worked out within age band, sex and receipt year (`ebgm`), so a pair's RRR is seldom its cases over EBGM's expected count.

**When it is empty:** never, for a pair seen at least once.

**Presets:** none. RRR has no threshold in common use: on small counts it swings widely, which is what EBGM (`ebgm`) and IC (`ic`) shrink. A threshold of your own starts from `own`, RRR at least 2 in at least 3 cases, for you to change.

**Source:** the observed to expected ratio under independence that DuMouchel (1999) shrinks into EBGM: DuMouchel W. Bayesian data mining in large frequency tables, with an application to the FDA Spontaneous Reporting System. The American Statistician 1999;53(3):177-190.

**Not a signal:** see `prr`. Code: `src/open_altio/stats/disproportionality.py`.
