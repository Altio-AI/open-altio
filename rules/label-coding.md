---
rule: label-coding
line: Where the fixed rules can't tell which reaction a label phrase names, an agent and then a reviewer answer one question; the rules, not they, set the flag.
values:
  question: Which MedDRA preferred term or terms does this phrase state as a reaction to this drug?
  stated: >-
    A phrase states a reaction when it says, in any section read (boxed warning, warnings and
    precautions, and adverse reactions including the list of reactions seen after approval),
    that the reaction happened with this drug or may happen with it. The
    words may differ from MedDRA's: a spelling, a synonym, a plural, a lab result written out,
    words spread across a list. A phrase that lists a reaction counts even when another sentence
    elsewhere on the label says there were no cases of it. Name every preferred term the phrase
    states, as MedDRA spells it, and nothing it does not state.
  stated_examples:
    - label: "Galactorrhea, amenorrhea, gynecomastia, and impotence have been reported in patients receiving prolactin-elevating compounds."
      pts: [Galactorrhoea, Amenorrhoea, Gynaecomastia, Erectile dysfunction]
    - label: "20% of subjects treated developed injection site reactions (erythema and/or itching, hemorrhage, pain or swelling)"
      pts: [Injection site reaction, Injection site erythema, Injection site pruritus, Injection site haemorrhage, Injection site pain, Injection site swelling]
    - label: "Elevations of serum ALT greater than 3 times the upper limit of normal"
      pts: [Alanine aminotransferase increased]
  none_reasons:
    states_no_reaction:
      name: States no reaction
      definition: The phrase names no reaction of its own. It is a heading, a table title, a table row such as a grade under a reaction named in the row above, the standard words about how clinical trials are run, advice on giving the drug or on what to measure, what the drug does not treat, contain or protect against, or words that point back to a reaction named in another sentence without naming it ("the latter", "these reactions"); that reaction is coded from the sentence that names it. A phrase that names a reaction, even in advice to watch for it, states that reaction.
      examples:
        - "Table 2: Adverse Reactions Reported in at Least 2% of Patients"
        - "Grade 4 | >10.0 × ULN | 1% | 2%"
        - "Because clinical trials are conducted under widely varying conditions, adverse reaction rates observed in the clinical trials of a drug cannot be directly compared."
        - "They do not treat viral infections (e.g., the common cold)."
        - "The latter usually is not reversible after androgens are discontinued."
    population:
      name: Population or who should not take it
      definition: The words describe who was studied, who should be tested first, or who should not take the drug.
      examples:
        - "Contraindicated in patients with a personal or family history of medullary thyroid carcinoma."
        - "Test patients for latent tuberculosis before starting treatment."
    did_not_happen:
      name: Did not happen
      definition: The phrase itself says the reaction was not seen or did not occur.
      examples:
        - "No cases of pancreatitis were reported in clinical trials."
        - "Hepatotoxicity was not observed."
    not_studied_or_unknown:
      name: Not studied or unknown
      definition: The phrase says the effect was not studied, or that it is not known whether the drug causes it, in all patients or in a group of them.
      examples:
        - "No carcinogenicity studies have been conducted with primaquine."
        - "Safety and effectiveness in pediatric patients have not been established."
    not_with_this_drug:
      name: Not with this drug
      definition: The phrase reports the reaction only with placebo or with another treatment, no more often than with placebo, or only in a patient no longer taking this drug.
      examples:
        - "Nasopharyngitis was reported in 4% of patients on placebo."
        - "There was no increase in syncope compared to placebo."
        - "One death occurred in a patient who had discontinued the drug seven weeks earlier."
    other:
      name: Other, with a note
      definition: None of the reasons above. The note says why; each one may point to a reason to add.
      examples:
        - "Adverse reactions reported in more than 5% of patients include such as"
  needs_note: [other]
  faers_line: FAERS reports are suspected events, not proven reactions; the flag only says whether today's label lists the event.
enforced_in:
  - src/open_altio/labelreview/coding.py
  - tests/labelreview/test_coding.py
---
# Label phrases the rules can't read

Fixed rules code most of each label's safety sections into MedDRA terms. What they leave uncertain is mostly phrases that read like reactions but match no term, and phrases where a rule's match may be wrong. For each one, an agent and then the reviewer answer one question, `question`: which MedDRA preferred terms the phrase states as a reaction to this drug. The answer is a list of preferred term names, or none.

`stated` says what counts as stating a reaction, with `stated_examples`. When a phrase states none, the answer gives one of `none_reasons`, each with a definition and examples; "other" needs a note (`needs_note`).

Nobody decides a flag here. The comparison rules turn each label's coded terms into the flags (on the label, related, not on the label, and the rest), the same way for coded phrases as for everything the fixed rules coded.

The examples use MedDRA preferred term names as FDA publishes them in FAERS, and label words as FDA publishes them. They carry no MedDRA codes, lower level terms or hierarchy, which are licensed (rule meddra-licensed-tier).

`faers_line` is said wherever the flags are explained.

**Why:** one plain question, answered the same way by a person and an agent, is easy to check item by item, and leaves every flag to rules anyone can read.
