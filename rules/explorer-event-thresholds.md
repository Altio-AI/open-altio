---
rule: explorer-event-thresholds
line: A product's events open with each statistic's standard screen as its column's thresholds; a person changes every value in that column's head menu for the page they are on and nothing is kept.
values:
  threshold_step: 0.5
  trend_quarters: 8
  column_starts:
    - {column: newest, at_least: 3}
    - {column: ebgm, at_least: 2}
enforced_in:
  - src/open_altio/explorer/eventlist.py
  - src/open_altio/explorer/facts.py
  - src/open_altio/explorer/ui/eventmenus.js
  - src/open_altio/explorer/ui/eventcolumns.js
  - tests/explorer/test_events_table_page.py
---
# The thresholds a product's events open with

A product's Events tab answers one question: which events crossed the thresholds, in the newest quarter against the quarter before. The thresholds are filters: an event shows when it meets every one of the columns showing, all of a column's values together, and the rest are hidden, with a line at the table's foot saying how many.

**The values** are each statistic's own standard screen, from its rule: EB05 and its fewest cases (rule `ebgm`), PRR with its chi-square and fewest cases (rule `prr`), the ROR's lower bound and fewest cases (rule `ror`), IC025 (rule `ic`). No statistic's rule gives N or EBGM a value of their own, so `column_starts` does: N takes the standard screens' fewest cases, 3, in the newest quarter, and EBGM the number EB05's screen reads, 2. Each is in its column's head menu, every value of it, so a statistic with three values offers all three. What you see is what filters: a hidden column's values apply once Columns shows it, and every one showing narrows further.

`threshold_step` is what the arrow keys change a threshold by in the menu, a count of cases moving by one. `trend_quarters` is how many of the newest quarters the Trend column draws, each event's cases FDA first received in each.

**Nothing is kept.** The values come back on every visit. A person changes what they see on this page and no one else's, and changes no statistic and no count.

**Show every event takes every threshold off,** from any of those menus, so every event can always be reached, those with no value included, and each value's reset arrow puts it back.

**Why together:** a person reading a column's value as a filter expects each one set to narrow the list further, as every other narrowing on the table does.

**Why:** a signal review starts from a list a reader can go through, read against thresholds they can see. Keeping them per person would have two people on one page reading different lists without knowing it.
