---
rule: explorer-field-notes
values:
  notes:
    - field: occp_cod
      from: 2025q3
      to: null
      note: >-
        From 2025Q3 FDA's files leave who reported blank for most company reports; consumers and other health
        professionals seem to vanish, which is not real.
    - field: route
      from: 2026q1
      to: null
      note: >-
        From 2026Q1 FDA's files give a real route far less often: 34% of drug rows in 2025Q4, 22% in 2026Q2.
    - field: dose_form
      from: 2026q1
      to: null
      note: >-
        From 2026Q1 FDA's files give a real dose form far less often: about 39% of drug rows in 2025Q4, about
        18% in 2026Q2.
    - field: dechal
      from: 2012q4
      to: 2016q2
      note: >-
        FDA coded dechallenge and rechallenge differently from 2012Q4 to 2016Q2: rechallenge D is a filler from
        2012Q4 to 2015Q3, dechallenge is filled on under 3% of drug rows in all those years, and both are nearly empty from
        2015Q4 to 2016Q2, so do not compare across these years.
    - field: rechal
      from: 2012q4
      to: 2016q2
      note: >-
        FDA coded dechallenge and rechallenge differently from 2012Q4 to 2016Q2: rechallenge D is a filler from
        2012Q4 to 2015Q3, dechallenge is filled on under 3% of drug rows in all those years, and both are nearly empty from
        2015Q4 to 2016Q2, so do not compare across these years.
enforced_in:
  - src/open_altio/explorer/facts.py
  - src/open_altio/faers/insights/cards/empty_fields.py
  - src/open_altio/explorer/ui/state.js
  - tests/explorer/test_page.py
---
# Fields whose FDA files changed

Some of FDA's fields changed in its own files from one quarter on, in ways that look like real change but are not. The explorer shows the field's note under its chart and beside its filter whenever the dates chosen take in those quarters.

Each of `notes` names the field (FDA's column), the first quarter of FDA's files it holds for (`from`) and the last (`to`, none while it lasts), and the sentence shown. With no received dates chosen, the note shows when the release holds any of those quarters.

**Why:** notebook `notebooks/faers/03_empty_fields`, sections 3 and 4: the breaks in these fields come from FDA's files, not from what people reported, and a chart that crosses them reads as a trend that is not there.
