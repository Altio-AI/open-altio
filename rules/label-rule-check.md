---
rule: label-rule-check
values:
  sample_size: 100
  sample_seed: 1729
  decided_by: rule
  outcomes:
    on_label: On the label
    related: Related, the label names something nearby
    not_on_label: Not on the label
    treated_disease: Disease it treats
    procedure: Procedure
    not_a_medical_event: Not a medical event
    no_label: No label found
  confidence: 0.95
enforced_in:
  - src/open_altio/labelreview/rulecheck.py
  - tests/labelreview/test_rulecheck.py
---
# Hand check of rule-made flags

Fixed rules decide most label flags (`label_flags_T`). To say how often they are right, the reviewer checks a random sample of them by hand, on the review page's rule check.

- The sample is drawn once, from the flags whose `decided_by` is `decided_by` (the rules', not a person's or a model's), with `sample_seed` so anyone can draw the same sample again from the same table. It holds `sample_size` flags, shared as evenly as the table allows across `outcomes`, so each outcome gets its own error rate. Uncertain flags are left out: no rule decided them.
- For each flag the reviewer opens the label and marks the flag right, or wrong with the right outcome. Each check is written to the licensed decisions file with who made it and when.
- The page shows, for each outcome, how many flags were checked, how many were wrong, the error rate, and the range the true error rate likely lies in: a Wilson interval at `confidence`.

A wrong flag points at a fixed rule to change. The change is its own commit with its rule file and test, and the sample is not redrawn to hide it.

**Why:** publishing how often the fixed rules are wrong, with an honest range, lets a reader judge how far to trust a flag without checking every pair.
