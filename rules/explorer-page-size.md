---
rule: explorer-page-size
values:
  cases_per_page: 50
enforced_in:
  - src/open_altio/explorer/explore.py
  - tests/explorer/test_explore.py
---
# The explorer lists 50 cases a page

A page's Cases tab shows this many cases at a time, newest received first unless the person sorts it, with the next and previous pages a click away. The count line above it always covers every matching case.

**Why:** enough to scan on a laptop screen without the page getting slow; anyone who wants every row takes the filtered export.
