---
rule: pregnancy-cases
line: A pregnancy case is one that names a term of one MedDRA SMQ, so an event's pregnancy cases are counted by their terms.
placeholder: true
values:
  smq_key: pregnancy_smq
  scope: narrow
  sub_smqs: folded
enforced_in:
  - src/open_altio/faers/meddra/rulenames.py
  - src/open_altio/faers/labeldict/groups.py
  - src/open_altio/explorer/eventfacts.py
  - tests/explorer/test_eventfacts.py
  - tests/explorer/test_meddra.py
---
# The cases that concern pregnancy

FAERS has no field that says a case concerns a pregnancy, so Open Altio finds them by their events. An event's pregnancy count is its counted cases that also name any preferred term of one MedDRA SMQ.

- `smq_key`: the key of the SMQ in the groups file a person makes from their own MedDRA (`rules/label-groups.md`), kept beside the MedDRA version's tables because an SMQ's name is licensed. A release with no such SMQ, or one the version does not hold, never refuses a person's page: the count is empty (null), with the reason, and the build says so loudly (`rules/not-a-medical-event.md`).
- `scope`: `narrow` counts the SMQ's narrow terms, `broad` its narrow and broad terms.
- `sub_smqs`: `folded` adds the terms of the SMQ's own sub-SMQs.

There is no share for it, because no case "gives" a pregnancy the way it gives an age: the count is what the terms find, and it is likely an undercount. A release without a MedDRA version, or a viewer without MedDRA, is given the count as empty (null) with the reason, never 0.

**Not yet decided.** These values were chosen before their evidence. Notebook `notebooks/faers/15_event_facts` will decide them, by checking the undercount, and the adult hereditary conditions that its sub-SMQ on inherited conditions brings in.

**Why:** a drug taken in pregnancy can harm the baby, so a reviewer weighs how many of an event's cases are pregnancy cases. MedDRA's own SMQ is the standard list of those terms, and it is licensed, so only a viewer with MedDRA reads it.
