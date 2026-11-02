---
rule: treated-condition
line: An event is the condition the drug treats when the drug's label flag for it says so.
placeholder: true
values:
  reads: label_flag
  outcome: treated_disease
enforced_in:
  - src/open_altio/explorer/eventfacts.py
  - tests/explorer/test_eventfacts.py
---
# The condition the drug treats

An event is likely the condition the drug is taken for when the label flag of the drug and the event (rule `label-treated-disease`) is `outcome`. The source of the answer is kept here, in `reads`, so the evidence notebook can weigh another source, the reported indication, against it.

- `reads`: where the answer comes from. `label_flag` is the drug's label flag for the event.
- `outcome`: the flag that means the event is the treated condition.

Where the answer cannot be given, it is empty (null) with the reason, never false: the release holds no labels, the drug has no label, the flag could not be settled because the drug's forms differ, or the event has no flag.

**Not yet decided.** Notebook `notebooks/faers/15_event_facts` will decide the source.

**Why:** a disease that the drug is given for is expected to appear in its reports, so it is no sign that the drug causes it.
