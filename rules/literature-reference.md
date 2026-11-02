---
rule: literature-reference
line: A report cites an article when FDA's literature reference is given; a report from FDA's files before the field existed reads Not given, never no article cited.
values:
  first_quarter: 2014q3
enforced_in:
  - src/open_altio/faers/literature.py
  - src/open_altio/explorer/breakdowns/fields.py
  - src/open_altio/faers/insights/cards/rule_charts.py
  - tests/faers/test_explorer_db.py
  - tests/explorer/test_breakdowns.py
  - tests/faers/insights/rule_chart_checks.py
---
# Literature reference

An event's Literature line says whether each report cites a published article, from FDA's own literature reference field (`lit_ref`). FDA's files hold that field only from `first_quarter` on, so a report from an earlier file reads Not given: it could not say, which is not the same as citing no article.

- A report cites an article (`cites`) when its `lit_ref` is given, as rule `not-given` reads it.
- `first_quarter`: the first quarter of FDA's files with the field. A report whose latest version came in an earlier file reads Not given, whatever its `lit_ref` holds.
- From `first_quarter` on, a blank `lit_ref` (nothing, or only spaces) reads "No article cited" (`_none`): the field was there and the report left it empty, as a report that cites no article does. A `lit_ref` that only says unknown (`UNK`) reads Not given (rule `not-given`).
- A share of the Literature line counts only the reports that give it, so the reports from the earlier files lower its Given in share and never its shares.

FDA's `lit_ref` stays as published. The explorer's case table carries it (`explorer_case_T.lit_ref`); a release whose explorer database was built without it answers the Literature line Not available, with the reason, until its explorer database is built again.

**Why:** notebook `notebooks/faers/00_setup_and_inventory`, the share of each quarter's reports giving each of FDA's demographic fields: `lit_ref` is empty on every report in FDA's files up to 2014Q2, AERS and FAERS alike, and given on about 3% to 10% of the reports in each quarter's file from 2014Q3 on. Read as "No article cited", the earlier reports would show a rise in literature reports where FDA's files only gained a field.
