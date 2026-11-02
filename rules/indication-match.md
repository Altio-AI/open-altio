---
rule: indication-match
line: For the condition the drug treats, the share of its cases whose reported indication is the event itself.
placeholder: true
values:
  reads: indi_pt_current_pt
  equals: event_pt
enforced_in:
  - src/open_altio/explorer/eventfacts.py
  - tests/explorer/test_eventfacts.py
---
# Whether the reported indication is the event

For an event marked as the condition the drug treats (rule `treated-condition`), the share of its counted cases that give an indication for the drug and whose indication is the event itself.

- `reads`: the indication FDA reported for the drug's record (`indi_pt`), read to today's preferred term in the MedDRA version the release holds.
- `equals`: what that term is compared with: the event's preferred term.

The share is of the cases whose record of the drug gives an indication, with the number giving one beside it. A case that gives none is in neither part. With no case giving an indication, the share is empty (null), never 0. An event not marked as the treated condition has no share. A release without a MedDRA version, or a viewer without MedDRA, is given it empty with the reason.

**Not yet decided.** Notebook `notebooks/faers/15_event_facts` will decide whether this is the right test.

**Why:** a drug given for the condition that is then reported as its event may be the disease showing itself, not harm the drug did. The reported indication is the report's own word for it.
