---
rule: breakdown-alarm
line: A breakdown line is an alarm when the value it shows moved by a set number of points from before to the window and the change is more than chance.
placeholder: true
values:
  points: 10
  fall_counts: true
enforced_in:
  - src/open_altio/explorer/breakdowns/lines.py
  - tests/explorer/test_breakdowns.py
---
# The alarm on a breakdown line

An event's breakdown line is an alarm when the change of the value it shows (rule `breakdown-lines`) reaches `points` and its chance test passes (rule `chance-test`). A question may give its own `points`, such as a product's own setting; this rule gives the one default.

- `points`: how far the shown value's share must move, in points, compared exactly. For Time to onset, whose change is the median's, it is in days. A question's `points` must be a positive number, and anything else is refused, naming it.
- `fall_counts`: `true` counts a fall of that size as a rise does. A question's `fall=1` counts falls, and `fall=0` counts rises only.

A line whose shown value has a share Not given in either period, or that shows no value, has nothing to compare and is never an alarm (`alarm: null`). An alarm is not a signal and not evidence of cause; people judge what a change means.

**Not yet decided.** These values were chosen before their evidence. Notebook `notebooks/faers/16_breakdowns` will decide them, by showing how many alarms each choice raises on the events regulators acted on and on those they did not, on years it was not tuned on.

**Why:** a change of a few points on many reports is certain to pass a chance test and still matter little. Asking for a change of a set size as well keeps the alarm for changes a person would weigh.
