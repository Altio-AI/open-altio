---
rule: explorer-label-words
values:
  words:
    not_on_label: Not listed
    forms_differ: Forms differ
    uncertain: Can't tell
    related: Possibly listed
    on_label: Listed
    procedure: Not compared
    treated_disease: Not compared
    not_a_medical_event: Not compared
    no_label: Not compared
  reasons:
    procedure: a procedure
    treated_disease: the disease it treats
    not_a_medical_event: not a medical event
    no_label: no label found
enforced_in:
  - src/open_altio/explorer/labels.py
  - src/open_altio/explorer/filters.py
  - tests/explorer/test_labels_api.py
  - tests/explorer/test_labels_page.py
  - src/open_altio/faers/insights/cards/rule_charts.py
---
# The words the screens give the label flags

The screens speak only of whether today's label lists a reaction. Every place a flag shows (the Statistics tab's Label column, the case window, Label status in the filters menu and on the strip, the tips, an export's list of filters and About the label flags) uses these words. Each flag keeps the meaning rules label-flags and explorer-label-flags give it; the data keep their codes (`outcome_T`), and no count changes.

- `words`: each flag's word. Listed, Not listed and Possibly listed say how the label stands to the reaction: a related term on the label (the same primary MedDRA group, rule label-flags) is Possibly listed. A flag's word never says "related", which a safety reviewer reads as cause. A phrase the rules could not settle reads Can't tell, as the drug classes say it.
- `reasons`: a flag with a reason was not compared with the label. It reads Not compared, with its reason in grey under it, the way an interval sits by its number: not a medical event, a procedure, the disease it treats, no label found. In a line of words, such as the strip or an export's list of filters, it reads "Not compared (a procedure)".
- **Forms differ** keeps its word in Label status, where it is ticked. On a reaction it is compared, and shows each form's answer in these words: "Listed on the by-mouth label, not listed on the skin label".
- **Another form's label.** A record read on another form's label is compared, and says which label decided: "Listed on the injected label; no by-mouth label".

**Why:** a flag says whether the label lists the reaction, never whether the drug caused it, so its words speak of listing alone. The outcomes that were never compared with the label read as one answer, Not compared, so they cannot be mistaken for a comparison's result, and each keeps its reason. The evidence is in notebook `notebooks/faers/10_label_flags`: the flags in these words (section 2) and one real label sentence for each (section 5).
