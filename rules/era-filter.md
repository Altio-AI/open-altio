---
rule: era-filter
values:
  default: [AERS, FAERS]
  quarters:
    AERS: [2004Q1, 2012Q3]
    FAERS: [2012Q4]
enforced_in:
  - src/open_altio/explorer/facts.py
  - src/open_altio/explorer/filters.py
  - tests/explorer/test_filters.py
---
# Era is and/or, not either/or

AERS (2004Q1 to 2012Q3) and FAERS (2012Q4 onward) are two checkboxes, both ticked by default, with a note under them: FDA changed systems, not the data's continuity.

`quarters` are the quarters FDA published each system's files in: AERS from its first to its last, FAERS from its first. The explorer's era choices, its charts' first year and its words for each era come from them.

**Why:** time is continuous; the date filter does the slicing.
