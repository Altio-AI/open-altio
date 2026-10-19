---
rule: no-drug-or-reaction
line: Reports that name no usable drug, or say only 'no adverse event', stay in view, and those that still record a death, a hospital stay or another serious outcome are marked.
values:
  unusable_drug_names: [UNKNOWN, UNKNOWN DRUG, UNKNOWN MEDICATION, UNKNOWN MEDICATIONS, UNSPECIFIED MEDICATION,
                        UNSPECIFIED MEDICATIONS, UNSPECIFIED INGREDIENT, 'DRUG, UNSPECIFIED', '[THERAPY UNSPECIFIED]',
                        THERAPY UNSPECIFIED, NO DRUG NAME, NO MEDICATION, NONE, N/A]
  no_event_terms: [NO ADVERSE EVENT, NO ADVERSE EFFECT, NO ADVERSE DRUG EFFECT, NO ADVERSE REACTION,
                   NO ADVERSE DRUG REACTION]
  serious_outcome_codes: [DE, LT, HO, DS, CA, RI, OT]
settable:
  unusable_drug_names:
    label: Drug names that count as no drug
  no_event_terms:
    label: Reactions that count as no reaction
enforced_in:
  - src/open_altio/faers/duplicates.py
  - src/open_altio/faers/not_given.py
  - tests/faers/test_duplicates.py
  - tests/faers/test_user_rules.py
  - src/open_altio/faers/insights/cards/duplicates.py
  - tests/faers/insights/test_cards.py
  - src/open_altio/explorer/ui/casedialog.js
  - src/open_altio/explorer/ui/cases.js
---
# No usable drug or reaction

Some reports name no usable drug or say only "no adverse event". We keep them in view rather than removing them, and mark the ones that still record a death, a hospital stay or another serious outcome.

A report has no usable drug when it has no drug name or only names in `unusable_drug_names` (normalised drug names). It has no usable reaction when it has no reaction term or only terms in `no_event_terms` (compared in capitals). Such a report is not set aside for it and never hidden: `no_drug_or_reaction_T` marks it. It is matched for duplicates like any other case.

When it also carries one of `serious_outcome_codes` in OUTC (death, life-threatening, hospitalisation, disability, congenital anomaly, required intervention, other serious), `serious_no_drug_or_reaction_T` marks it, and the explorer flags it in the case list and the case window as "No usable drug or reaction recorded, serious outcome reported", linked to this rule. Switched off, no report is marked.

**Why:** notebook `notebooks/faers/04_duplicates`. These reports are almost all "no adverse event" reports. DiAna removes them, but they are not empty: they carry indications and outcome codes, including deaths and hospitalisations.
