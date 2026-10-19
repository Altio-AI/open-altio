---
rule: label-population
line: "'Contraindicated in patients with renal failure' says who must not take the drug, not a reaction it causes, so renal failure is not put on the label."
values:
  phrases:
  - contraindicated in patients with
  - patients with a history of
  - with a history of
  - history of
  - in patients with
  - patients with
  - in patients who have
  - patients who have
  - patients who are
  - in women with
  - in children with
  - in the presence of
  - in presence of
  - tested for
  - testing for
  - screening for
  - screened for
  - tested negative for
  - tested positive for
  - indicated for
  - newly diagnosed
  - diagnosed with
  - pre-existing
  - preexisting
  - excluded for
  - background risk of
  people_words:
  - patients
  - patient
  - subjects
  - adults
  - children
  - women
  - men
  - infants
  - neonates
  - population
  - populations
  window_words: 4
  bare_comma_items: uncertain
  trial_exclusion:
  - trial excluded
  - trials excluded
  - study excluded
  - studies excluded
  - excluded patients
  - excluded subjects
  - were excluded from
  - was excluded from
  - were excluded
  - exclusion criteria
  - must be excluded
  risk_starts:
  - patients with
  - those with
  - people with
  - subjects with
  risk_ends:
  - are at greater risk
  - are at increased risk
  - are at higher risk
  - are at an increased risk
  - are at a greater risk
  - may be at increased risk
  - may be at greater risk
  - have an increased risk
  population_sections:
  - contraindications
  unstated_context:
    phrases: [patients with, history of, disease, including, known, in patients]
    chars: 60
settable:
  window_words:
    label: Words allowed between the phrase and the condition
    minimum: 0
enforced_in:
- src/open_altio/faers/labeldict/scope.py
- tests/faers/test_label_coding.py
---
# Who the patients are

Labels name conditions to say who is at risk or who must not take the drug: "contraindicated in patients with renal failure". Such a condition is not a reaction the drug causes, so it does not put that reaction on the label. Everything in the contraindications section is read this way.

A hit is kept off the label (`kept` false, `rule` naming this file) when it names who the patients are, not what happened to them: one of `phrases` is followed, within `window_words` words, by the term, and by every term listed with it (`rules/label-dictionary.md` says how a list is read). The longest phrase wins, so "contraindicated in patients with" is read once.

A term followed straight away by one of `people_words` describes the people too ("hypertensive patients", "diabetic women") and is kept off.

The phrases also cover tests and indications, which name a condition looked for or treated, not one caused: "tested for latent tuberculosis", "indicated for multiple myeloma", "newly diagnosed multiple myeloma". So do a condition the patient already had ("pre-existing low white blood cell count"), a trial's exclusions ("excluded for abnormal left ventricular ejection fraction") and the background risk every pregnancy carries ("the background risk of major birth defects and miscarriage"). "Treatment of" is not among them, because in a safety section it more often names a reaction being managed ("for the treatment of anaphylaxis").

A clause about a trial's exclusions or screening (one of `trial_exclusion`: "The trial excluded patients with active pneumonitis", "Patients were excluded from the study if they had symptomatic hypotension"), up to a semicolon or the end of the sentence, names who was left out, so every term in it is kept off. So is a risk factor: a term between one of `risk_starts` and one of `risk_ends` ("Patients with high tumor burden or renal impairment are at greater risk for tumor lysis syndrome" keeps renal impairment off and the tumour lysis syndrome on).

A term after a bare comma, with no "and" or "or" later in the list, is uncertain (`bare_comma_items`): "in patients with renal failure, hyperkalaemia may occur" starts a new clause, while "in patients with renal failure, heart failure or stroke" goes on listing.

Every hit in one of `population_sections` is kept off as a population: the contraindications section names who must not take the drug ("severe hepatic impairment"). It never puts a term on the label and leaves nothing uncertain. When it also names a real reaction ("hypersensitivity to the drug"), the label states it elsewhere and it is kept from there; if not, the event shows as not on the label or related, so nothing is hidden.

**A condition before a term no phrase reads.** A line that is still uncertain, with one of `unstated_context`'s `phrases` within `chars` characters before the term, states nothing and is kept off, unless the sentence holds a word of `unstated_unless` in rule label-negation ("patients with a history of deep thrombophlebitis" is a patient's condition; "reported in patients with" is a reaction list).

Examples:

| Sentence | Term | Kept |
|---|---|---|
| "Contraindicated in patients with renal failure." | renal failure | off |
| "Patients with a history of renal failure or hepatitis should be monitored." | both | off |
| "Monitor patients with severe renal failure." | renal failure | off: "severe" is within the window |
| "Patients with psoriasis developed hepatitis." | psoriasis | off |
| "Patients with psoriasis developed hepatitis." | hepatitis | kept: "developed" is not a term, so the list stops |
| "In patients with renal failure, nausea may occur." | nausea | uncertain: a bare comma |
| "4 CONTRAINDICATIONS Severe hepatic impairment" | hepatic impairment | off: the contraindications |
| "occurred in 2.6% of hypertensive patients" | hypertensive | off: followed by "patients" |
| "Patients should be tested for latent tuberculosis." | latent tuberculosis | off: a test |

**Why:** labels name conditions to say who is at risk or who must not take the drug. Such a condition is not a reaction the drug causes, so a report of it is not expected because the label names it. The evidence is in notebook `notebooks/faers/10_label_flags`: the accuracy checks (section 7) and its closing section, which sets out what was decided.
