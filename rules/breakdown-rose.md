---
rule: breakdown-rose
line: A value of a breakdown line rose when its share is up by a set number of points from before to the window and the change is more than chance.
placeholder: true
values:
  points_at_least: 1
  chance_test: true
enforced_in:
  - src/open_altio/explorer/breakdowns/lines.py
  - tests/explorer/test_breakdowns.py
---
# What "rose" means

A value of an event's breakdown line rose when its share of the reports that give the field is up at least `points_at_least` points from before to the window, and its chance test passes (rule `chance-test`). Several lines show the value that rose (rule `breakdown-lines`), so a rise by chance never takes a line from a real one.

- `points_at_least`: how many points a share must be up, compared exactly, never after rounding.
- `chance_test`: `true` asks that the change also pass the chance test; `false` takes the rise in points alone.

A value whose share is Not given in either period, because no report there gives the field, has nothing to compare: it neither rose nor did not (`rose: null`). A value whose share is up but whose change fails the chance test did not rise (`rose: false`). For Time to onset the change is the median's, in days.

**Not yet decided.** These values were chosen before their evidence. Notebook `notebooks/faers/16_breakdowns` will decide them, by showing how often a value that rose by this rule is the one regulators acted on, on years it was not tuned on.

**Why:** a line that shows whichever value moved most would often show luck on an event with few reports. Asking a rise to pass the same chance test as everything else keeps a real change in view.
