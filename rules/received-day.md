---
rule: received-day
line: Every count by quarter, year or window dates a case by the first time FDA received any copy of it.
placeholder: true
values:
  column: group_first_dt_T
enforced_in:
  - src/open_altio/faers/dates.py
  - src/open_altio/faers/statistics/quarterly.py
  - src/open_altio/explorer/eventlist.py
  - src/open_altio/explorer/filters.py
  - src/open_altio/explorer/grouped.py
  - src/open_altio/explorer/quarterly.py
  - tests/explorer/test_eventlist.py
  - tests/explorer/test_grouped.py
  - tests/explorer/test_quarterly.py
  - tests/faers/statistics/test_statistics_quarterly.py
  - tests/faers/test_dates.py
---
# The day a case is dated by

Every count by quarter, year or window dates a case by one day, read from the column `column` names, so changing this one value dates all of them again. Today that day is the first time FDA received any copy of the case: `group_first_dt_T`, the earliest first receipt in the case's group of probable duplicates (rule `dup-shown-copy`), or the case's own first receipt when it is in no group.

- `column`: a column of the case table (`case_latest_T`, and `explorer_case_T` in the explorer's database) that the release derives, so its name ends in `_T`. `open_altio.faers.dates.received_day()` refuses any other. FDA's own `init_fda_dt` and `fda_dt` are never changed.
- A case whose day is empty is placed in the quarter of the file that holds it, `quarter_T`.
- A window that starts on a day, such as the statistics of the cases received since a day, holds no case whose day is empty.

**Not yet decided.** This value was chosen before its evidence. Notebook `notebooks/faers/13_received_day` will decide it, by comparing the counts each candidate day gives, quarter by quarter, for drug and event pairs regulators have acted on. The aim is the day FDA first received a version of the case naming the event under today's preferred term, so that a later recoding of a term does not make an old event look new. That day needs a new column for each case and event (`event_first_received_T`), built only once the notebook has decided it. A change of this value ships as its own data release, with the counts by quarter before and after on the same release.

**Why:** a case FDA received again, as a new version or from another sender, is the same event. Dating it by its first copy keeps an old event from counting as new in the quarter a later copy arrived.
