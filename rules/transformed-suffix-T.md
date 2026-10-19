---
rule: transformed-suffix-T
line: Every value stays exactly as FDA wrote it; anything we work out, such as an age in years, is added beside it, so you can always tell FDA's data from ours.
always_on: true
why_locked: FDA's own values are never changed.
values:
  derived_suffix: "_T"
enforced_in:
  - src/open_altio/faers/schema.py
  - src/open_altio/faers/labeldict/release_io.py
  - tests/faers/test_label_build.py
  - src/open_altio/faers/release.py
  - tests/faers/test_release.py
  - src/open_altio/faers/explorer_db.py
  - tests/faers/test_explorer_db.py
  - src/open_altio/faers/statistics/step.py
---
# FDA's values never changed

Every value FDA published is kept exactly as FDA wrote it. Anything Open Altio works out, such as a date read as a date or an age in years, is added beside it, never in its place. So you can always tell FDA's data from ours.

Every FDA column is loaded verbatim as text. Anything we compute (typed dates, ages in years, duplicate flags, normalised names) is a new column, view or table whose name ends in `derived_suffix`. The build refuses a release in which a derived table, view or column does not.

In a wholly derived table every column ends in `_T` too, values copied from another source included: the label tables (`label_candidates_T`, `label_sections_T`, rules label-choice and label-sections) hold DailyMed's and RxNorm's values, so a label's set ID is `setid_T`.

**Why:** anyone can tell what FDA published from what we did to it, and trace any number back to the raw file.
