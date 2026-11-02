---
rule: chance-test
line: A change in a share between two periods counts as more than chance when its p-value is under alpha, by Fisher's exact test on a small table and the chi-square test on a large one.
placeholder: true
values:
  sides: two
  alpha: 0.05
  fisher_up_to: 20000
  days: mann_whitney
enforced_in:
  - src/open_altio/stats/chance.py
  - tests/stats/test_chance.py
---
# More than chance

A share can differ between two periods by luck alone. This rule says how a change in a share is tested, so that the same two counts always give the same answer.

A table has four counts: in the earlier period, the reports with the value and those without; in the later period, the reports with the value and those without.

- `sides`: `two` tests for a difference in either direction. It is the only choice today.
- `alpha`: the change is more than chance when its p-value is under this number.
- `fisher_up_to`: a table holding at most this many reports is tested with Fisher's exact test; a larger one with the chi-square test (the two-proportion z test), which is quick on a large table.
- `days`: how two sets of days are compared, such as the days to onset in each period. `mann_whitney` is the Mann-Whitney rank test, the only choice today.

A table with an empty row or column has no change to test: its p-value is 1. An empty set of days cannot be compared: the answer is empty, never a pass or a fail.

A pass is not a signal and not evidence of cause; people judge what a change means.

**Not yet decided.** These values were chosen before their evidence. Notebook `notebooks/faers/16_breakdowns` will decide them, by showing on a real release how often the two tests differ near the limit, and how often a change that passes also holds in the next period.

**Why:** with many reports a small, steady change is certain to differ from zero, and with few reports a large change may be luck. Testing every change the same way keeps the two apart.
