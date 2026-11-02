---
rule: not-a-medical-event
line: A term about how a product was used, made or worked is marked as not a medical event.
placeholder: true
values:
  groups_key: event_facts_not_medical
  pts:
    - No adverse event
    - Drug ineffective
    - Product ineffective
    - Treatment failure
    - Therapeutic response decreased
    - Therapeutic product effect incomplete
    - Therapy non-responder
enforced_in:
  - src/open_altio/explorer/eventfacts.py
  - src/open_altio/faers/meddra/rulenames.py
  - tests/explorer/test_eventfacts.py
  - tests/explorer/test_meddra.py
  - tests/explorer/test_meddra_names_release.py
  - tests/faers/test_meddra_rule_names.py
---
# An event that is not a medical event

Some reported terms say how a product was used, made or worked, not what happened to the person. An event is marked not a medical event when its preferred term is on either of two lists, read from MedDRA's primary path for the term:

- `pts`: the public list of terms: no adverse event, and the terms on how a treatment worked.
- `groups_key`: the key of the licensed list in the groups file a person makes from their own MedDRA (`rules/label-groups.md`), kept beside the MedDRA version's tables and never in this repository. It lists the MedDRA groups, at any level, that hold terms about the product, how it was used or given, and personal and social matters. Procedures are among them.

Without that list, because the viewer has no MedDRA or the release's licensed part holds none, only the public list applies. A term on it is marked not a medical event, any other term is empty (null), never "is a medical event", and the reason says that only the public list was read.

A name that the MedDRA version does not hold never refuses a person's page: the mark is empty (null) for every event, with the reason naming this rule and the name, and every other fact still answers. So a list cannot quietly stop matching after a new MedDRA version. The build says so loudly and keeps the names in the licensed manifest (`rule_names_missing`), and `tests/explorer/test_meddra_names_release.py` fails on them over a real release.

**Not yet decided.** These lists were chosen before their evidence. Notebook `notebooks/faers/15_event_facts` will decide them, by reading the terms each list sets aside and the ones it keeps.

**Checked so far:** only that MedDRA 29.1 holds each name at the level this rule reads it. Whether the lists are the right ones is what the notebook will show; nothing here says so.

**Why:** a drug that did not work, or a product that was mislabeled, is not a harm the drug did. Marking these keeps a reviewer from weighing them as if it were.
