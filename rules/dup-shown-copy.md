---
rule: dup-shown-copy
line: Each group of duplicates shows the copy FDA received last, as it usually says the most, dated by when FDA first heard of the event; the other copies point to it.
always_on: true
why_locked: Each group of duplicates has to show one copy.
values:
  shown_copy: latest_received
  set_aside_line: 'Set aside: probable duplicate of case {shown_case}, received later and shown instead.'
  rule_lines:
    aeolus: Same event date, age, sex, country, drugs and reactions.
    manufacturer_number: Same manufacturer case number from the same sender.
    manufacturer_number_country_code: Same manufacturer case number from the same sender, one copy without its country code.
  shown_line: 'Also reported as {other_cases}, first received {first_received}.'
settable:
  shown_copy:
    label: The copy each group shows
    options:
      - [latest_received, Received last]
      - [earliest_received, Received first]
enforced_in:
  - src/open_altio/faers/duplicates.py
  - tests/faers/test_duplicates.py
  - tests/faers/test_user_rules.py
  - src/open_altio/explorer/explore.py
  - src/open_altio/explorer/ui/casedialog.js
  - tests/explorer/test_explore.py
---
# Which copy of a duplicate is shown

When cases are grouped as one event, we show the copy FDA received last, because it usually carries the most information. The group is dated by when FDA first heard of the event, so timelines stay right. The other copies stay in the data, each pointing to the one shown.

In each group of probable duplicates (`rules/dedup-default.md`) one copy is shown (`dup_kept_T`) and the others are set aside. With `shown_copy: latest_received` the shown copy is the one FDA received last: the latest `first_fda_dt_T`, then the highest `caseid`, then FAERS before AERS, then the highest `case_key_T`. The same order holds for every rule, so no rule can hide the copy another rule shows. With `earliest_received` it is the copy received first.

The group is dated by its earliest receipt: `group_first_dt_T` is the earliest `first_fda_dt_T` of any case in the group, and equals the case's own `first_fda_dt_T` for a case in no group. Received-date filters, sorting and exports use it, so an event keeps its original timing while users see the fullest copy. The case's own `first_fda_dt_T` is unchanged.

Every copy says why. A set-aside copy carries `dup_shown_case_T` (the shown copy) and `dup_rule_T` (the rules that grouped it), from which `open_altio.faers.duplicates.reason_lines` writes `set_aside_line` and one of `rule_lines` per rule. The shown copy carries `dup_other_cases_T` (the copies set aside, earliest received first) for `shown_line`, with the month and year of `group_first_dt_T`. The explorer sends these lines with each case (`/api/case`, as `reasons`) and the case dialog shows them, each case number in them a link to that copy, and dates a copy in a group twice: `First received (any copy)` for the group, beside the copy's own first receipt.

The shown case can change between releases when a newer copy arrives. The older copy stays in the data, flagged, and points to the newer one: opened from a bookmark or an export, by its case number in the address (`?case=`), it says it is set aside and links to the copy shown now.

**Why:** notebook `notebooks/faers/04_duplicates`. In groups found by the manufacturer number the latest copy usually carries more: more reactions in 31% of groups (the earliest in 12%), more patient fields filled in 23% (2%). In AEOLUS groups the copies agree on the matched fields by construction. This mirrors FAERS itself: the latest version of a case is shown, dated by its first receipt.
