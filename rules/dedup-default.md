---
rule: dedup-default
line: Cases with the same event date, age, sex, country, drugs and reactions count once, as in AEOLUS, a published clean-up of FAERS; a case missing any of these is never matched this way.
values:
  explorer_default: kept_only
  cross_case_method: AEOLUS (Banda et al. 2016) or the same manufacturer case number
settable:
  explorer_default:
    label: Probable duplicates when the explorer opens
    options:
      - [kept_only, Left out]
      - [all, Included]
enforced_in:
  - src/open_altio/faers/duplicates.py
  - src/open_altio/faers/funnel.py
  - tests/faers/test_duplicates.py
  - tests/faers/test_user_rules.py
  - src/open_altio/explorer/filters.py
  - tests/explorer/test_filters.py
  - src/open_altio/explorer/facts.py
  - tests/explorer/test_app.py
---
# Same patient, same event

The same event is sometimes reported as two separate cases, for example by two companies. When two cases match on the event date, the patient's age and sex, the country, the drugs and the reactions, we show one and set the other aside. Cases where any of these details is not given are never matched this way.

Two rules find probable duplicates, and a case is in a group when either rule puts it there:
- this one, the AEOLUS rule (Banda et al. 2016): the same event date, age, age unit, sex, country, set of drug names and set of reaction terms, none of them Not given;
- the same manufacturer case number from the same sender (`rules/dup-manufacturer-number.md`).

Groups that share a case are one group: if A matches B by one rule and B matches C by the other, A, B and C are one group. Each group shows one copy and sets the others aside (`rules/dup-shown-copy.md`). In large groups from one company a padded event date does not count as a match (`rules/dup-padded-event-dates.md`). Switched off, this rule groups no cases; the manufacturer number can still group them.

Empty fields are never compared. A case where any of these fields reads Not given (rule `not-given`: blank, says unknown or a filler, such as an age of 999), or whose sex is neither F nor M (`sex_T`, rule `sex-codes`: `NS`, `UNK`) or whose country is none (`country_T`, rule `country-not-given`: `COUNTRY NOT SPECIFIED`), is never grouped by this rule, though the manufacturer number can still group it. The release says how many cases this rule cannot check (`funnel.json`, `duplicates.not_compared_by_aeolus`, and the methods page). Matching on any version of a case, and a probability score over partial agreement, are for later releases.

Duplicates are flagged, never deleted. The release carries the kept set (`case_dedup_T`, `dup_kept_T` on `case_latest_T`) and its funnel step. The explorer's switch (Duplicates: kept cases only, or all cases with flagged duplicates included) starts on `explorer_default`, and the counts say how many probable duplicates were set aside.

**Why:** the deduplicated set is what Altio offers; the switch lets people check our work. Notebook `notebooks/faers/04_duplicates` measured the alternatives: the two rules find different duplicates and overlap little, while DiAna's rule, where an empty field matches an empty field, sets aside 16% of all cases in groups of up to thousands. Notebook `notebooks/faers/03_empty_fields` shows what empty fields leave the duplicate key.
