---
rule: overlong-lines
line: In three of FDA's 2011 drug files, a missing line break joined two drug records on one line; we put it back so the second drug is not lost.
values: {}
enforced_in:
  - src/open_altio/faers/load.py
  - tests/faers/test_load.py
---
# Missing line breaks put back

In a few of FDA's files two reports run together on one line, because a line break is missing. We split them back into two, so the second report is not lost. No value changes; only the missing line break is put back.

A line in an FDA file with more fields than its header is never cut short in silence. When it holds two or more whole records one after the other, it is split back into those records. Any other such line keeps its first fields, as FDA's columns line up, and the text past the last column is written into the manifest. Every such line is listed in the manifest under `inputs[].overlong_lines`. Switched off, a run-on line keeps only its first record, and the rest of it is written into the manifest like any other long line.

**Why:** FDA's 2011Q2, 2011Q3 and 2011Q4 DRUG files each hold one run-on line. Read as one record, the second drug of each case is lost without a trace. Notebook `notebooks/faers/02_case_versions` counts the run-on lines and the drugs they lose.
