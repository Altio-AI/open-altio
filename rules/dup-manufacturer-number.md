---
rule: dup-manufacturer-number
line: "A report a company sent twice under its own case number counts once, unless the two disagree on sex or are years apart in age: then they are two patients."
values:
  clashing_sexes: [M, F]
  max_age_gap_years: 2
  country_code: '^[A-Z]{2}-'
settable:
  max_age_gap_years:
    label: Skip when the ages differ by more than (years)
    minimum: 0
  clashing_sexes:
    label: Skip when the cases disagree on sex
    options:
      - [[M, F], "Yes"]
      - [[], "No"]
enforced_in:
  - src/open_altio/faers/duplicates.py
  - tests/faers/test_duplicates.py
  - tests/faers/test_user_rules.py
  - src/open_altio/faers/insights/cards/duplicates.py
  - tests/faers/insights/test_cards.py
---
# Same company case number

Each company gives its reports its own case number. When one company sent two cases under the same number, it sent one report twice, so we show one and set the other aside. We skip the match when the cases disagree on sex or are years apart in age, because then the number was used for another patient.

Two cases are probable duplicates when they carry the same manufacturer case number (`mfr_num`) from the same sender (`mfr_sndr`), both compared trimmed and in capitals. A case with either field empty is never compared by this rule. It runs beside the AEOLUS rule (`rules/dedup-default.md`).

Two guards skip a whole number group, so one number reused for two patients never hides one of them:
- **Sex.** The group's cases disagree on sex: both values in `clashing_sexes` occur. Any other sex value counts as empty. With `clashing_sexes: []` sex is not compared.
- **Age.** Their ages, in years by their units (`age_years_T`), differ by more than `max_age_gap_years`. An empty age never triggers the guard.

**A missing country code still matches.** Companies often start the number with a two-letter country code and a hyphen (`country_code`, a regular expression on the number in capitals), as in `US-PFIZER INC-2008036041`. When one case has the number without the code (`PFIZER INC-2008036041`) and the same sender's cases carry it with exactly one code, the case without a code joins that number. Two different codes never match each other: `DE-` and `US-` before the same number are two cases. A number without a code that the sender also wrote with two different codes matches neither.

`dup_number_key_T` on `case_dup_T` holds the sender and number as compared. `dup_rule_T` names `manufacturer_number`, or `manufacturer_number_country_code` for a group joined by a missing code. Switched off, this rule groups no cases.

**Why:** notebook `notebooks/faers/04_duplicates`. The number finds duplicates the AEOLUS rule cannot see, because one of its fields is empty: most are follow-ups FDA filed as new cases, or a company sending the same report twice, mostly in AERS. The guards matter because a correction inside one case already reaches its latest version, so a sex or age clash between two cases sharing a number means two patients far more often than a corrected error: follow-ups switch sex between male and female in about 0.24% of versions, while 1.8% of number groups disagree on sex. A wrong guard leaves a duplicate visible; no guard would hide a different patient. Ignoring the country code in general was measured and rejected: it groups one company's local numbers from different countries, and in those groups sex differs in 23 to 28%.
