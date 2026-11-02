---
rule: trend-rising
line: A statistic is rising when its value at the newest quarter end is higher than it was a set number of quarter ends before.
placeholder: true
values:
  quarters_back: 4
  compare: higher
enforced_in:
  - src/open_altio/stats/trend.py
  - src/open_altio/explorer/quarterly.py
  - tests/stats/test_trend.py
  - tests/explorer/test_quarterly.py
---
# Rising

A statistic of a drug and an event is rising when its value at the end of the release's newest quarter is higher than it was a number of quarter ends before. It is read from the pair's statistics at the end of every quarter, each worked out on the cases received by then (rule `received-day`) and scored under the release's own prior, so a value is never fitted again.

- `quarters_back`: how many quarter ends before the newest the value is compared with. Every calendar quarter counts, including one in which no case was received.
- `compare`: how the newest value is compared with the earlier one. `higher` means strictly higher, so a value that stayed the same is not rising. It is the only choice today.
- The question names the statistic (`rising=eb05`, say). A pair that had no case at the earlier quarter end, or a value that is empty at either end, answers that it cannot tell (null), never that it is not rising.

Rising is not a signal and not evidence of cause; people judge what a pair means.

**Not yet decided.** These values were chosen before their evidence. Notebook `notebooks/faers/14_screens_over_time` will decide them, by comparing, for drug and event pairs regulators have acted on and pairs they have not, how often each choice of quarters and comparison calls a pair rising before the quarter the regulator acted, on years it was not tuned on.

**Why:** a pair whose numbers keep growing quarter after quarter tells a reader more than one that reached the same number long ago and stayed there. Reading the trend from the same series as the statistics keeps the two side by side.
