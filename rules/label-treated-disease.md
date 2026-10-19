---
rule: label-treated-disease
line: A reaction that is the disease the drug was given for is flagged as such, not judged against the label; a worse form, such as asthma-related death for an asthma drug, is judged.
values:
  indications_section: indications
  worsening_words:
  - exacerbation
  - exacerbations
  - exacerbated
  - aggravated
  - aggravation
  - worsening
  - worsened
  - progression
  - fulminant
  - crisis
  - related death
  - status
  risk_phrases:
  - risk of
  - risks of
  - because of
  - due to
  - caused by
  - experiencing
  - cannot tolerate
  risk_window_words: 4
  never_treated_words:
  - death
  not_indication_lines:
  - risk of
  - risks of
  - risk reduction
  - not indicated
  - limitations of use
  - has not been established
  - has not been shown
  - have not been shown
  - have not been established
  - not recommended
  - should not be used
  - antihypertensive drugs have
  - control of high blood pressure
  - lowering blood pressure
  - cardiovascular risk
  - a history of
  - has not been studied
  - have not been studied
  - has not been demonstrated
  - have not been demonstrated
  - failed to demonstrate
  - who cannot
  - cannot take
  - higher incidence
  - secondary causes
  - reserved for
  - maintain the effectiveness
  - exclude intracranial hemorrhage
  - published guidelines
  qualifier_phrases:
  - signs of inflammation
  - falling asleep
  - ovale infections
enforced_in:
- src/open_altio/faers/labeldict/coding.py
- src/open_altio/faers/labeldict/scope.py
- src/open_altio/faers/labeldict/flags.py
- tests/faers/test_label_coding.py
- tests/faers/test_label_flags.py
---
# The disease the drug treats

Reports often name the disease the drug was given for. We flag it as the disease the drug treats rather than judging it against the label. A worse form of the disease, such as status asthmaticus for an asthma drug, is judged against the label like any other reaction, because a drug can make its own disease worse.

A report often names the disease the drug was given for. When the reported term's current preferred term (PT) is named in the drug's own label in its indications section (`indications_section` in `label_sections_T`), the pair's outcome is `treated_disease` (shown as "Disease it treats"), decided before the label's safety sections are compared (`rules/label-flags.md`). Every disease the indications name counts, not only the first.

It applies only to the disease as the indications name it: the same PT. A reported term that names a worse, paradoxical or more severe form never gets `treated_disease`, even when it maps to the same PT; it is compared with the label like any other event. Such a term is either a different PT (status asthmaticus or asthma-related death for an asthma drug, pustular psoriasis for a drug indicated for plaque psoriasis) or holds one of `worsening_words`, read as whole words in any capitals, a hyphen read as a space ("Asthma-related death", "Psoriasis aggravated").

It is its own outcome, not "on the label" and not "not a drug reaction": a drug can worsen the disease it treats (deaths from asthma with a long-acting bronchodilator given for asthma, psoriasis with a TNF blocker given for psoriasis), so such reports stay findable as a flag of their own.

The indications section is coded like the safety sections (`rules/label-dictionary.md`), with one difference: it names the patients' disease on purpose, so the phrases of `rules/label-population.md` do not keep a term off there, and nothing in it is made uncertain or sent for review. Only negation keeps a term off ("not indicated for the treatment of type 1 diabetes"). A phrase the rules cannot read with certainty there (an everyday word such as "lead", a table row that does not line up with its header) is not taken as the disease treated: the pair is compared with the safety sections like any other, so nothing is set aside on a guess. A term the indications name never puts a PT on the label. A term listed after one of `risk_phrases`, within `risk_window_words` words ("Because of the risks of addiction, abuse, misuse, overdose, and death, reserve opioid analgesics", "to reduce the risk of cardiovascular death", "Because of the proarrhythmic effects of flecainide, its use should be reserved"), names an outcome the drug guards against, a harm it can do, a cause ("abnormal uterine bleeding due to hormonal imbalance": the imbalance is the cause, the bleeding the disease) or a patient's trouble with something ("patients experiencing nausea and vomiting with the first few doses"), not the disease it treats, and a term whose PT names one of `never_treated_words` (death) is never the disease treated: such reports are compared with the label like any other event. An indications sentence holding one of `not_indication_lines` names no disease treated at all, so none of its terms is set aside: a risk the drug lowers ("reduces the risk of cardiovascular death"), the opposite of an indication ("Limitations of Use: not indicated for ...", "safety and effectiveness has not been established"), a denied effect ("has not been shown to improve quality of life, fatigue, or patient well-being"), a history or a patient who cannot take something ("has not been studied in patients with a history of pancreatitis", "a higher incidence of angioedema"), the boilerplate that asks for antibiotics to be used only against proven bacterial infections, "exclude intracranial hemorrhage as the primary cause of stroke", and the paragraph FDA puts on blood-pressure drugs, its sentence that sends the reader to published guidelines too ("many antihypertensive drugs have additional approved indications and effects (e.g., on angina, heart failure, or diabetic kidney disease)", "Lowering blood pressure reduces the risk of fatal and nonfatal cardiovascular events, primarily strokes and myocardial infarctions"). A word that only qualifies the disease named, and is not the disease, is not taken as the disease treated: a phrase of `qualifier_phrases` ("objective signs of inflammation", "difficulty in falling asleep", "Plasmodium ovale infections") keeps the terms inside it off, while the disease the line names (the spondyloarthritis, the insomnia) still counts. A plain line that only names a disease ("Rheumatoid arthritis") still counts.

Examples:

| Indications say | Reported term | Outcome |
|---|---|---|
| "indicated for the treatment of adults with moderate-to-severe atopic dermatitis" | Dermatitis atopic | treated_disease |
| "not indicated for the treatment of type 1 diabetes" | Type 1 diabetes mellitus | compared as usual |
| "indicated for the maintenance treatment of asthma" | Asthma | treated_disease |
| "indicated for the maintenance treatment of asthma" | Asthma aggravated, or Status asthmaticus | compared as usual |

**Why:** a report of the disease treated is most often the disease itself, sometimes the drug failing, and sometimes the drug making it worse. None of these is answered by the label's list of reactions, so it is shown apart rather than counted as expected or unexpected. The evidence is in notebook `notebooks/faers/10_label_flags`, its closing section, which sets out what was decided and why.
