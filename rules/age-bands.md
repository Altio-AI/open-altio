---
rule: age-bands
line: Each case falls in one age band, such as children 2 to 11, the same for the age filter and the statistics; a baby given as 0 years goes by the sender's own age group.
values:
  bands:
    - {id: "0-27d", label: "Under 28 days", from: [0, DY], to: [28, DY]}
    - {id: "28d-1", label: "28 days to under 2", from: [28, DY], to: [2, YR]}
    - {id: "under-1", label: "Under 1, exact age not given", from: null, to: null}
    - {id: "2-11", label: "2 to 11", from: [2, YR], to: [12, YR]}
    - {id: "12-17", label: "12 to 17", from: [12, YR], to: [18, YR]}
    - {id: "18-64", label: "18 to 64", from: [18, YR], to: [65, YR]}
    - {id: "65-74", label: "65 to 74", from: [65, YR], to: [75, YR]}
    - {id: "75-84", label: "75 to 84", from: [75, YR], to: [85, YR]}
    - {id: "85+", label: "85 and over", from: [85, YR], to: null}
  zero_age_units: [YR, DEC]
  zero_age_groups: {N: "0-27d", I: "28d-1"}
  zero_age_band: "under-1"
always_on: true
why_locked: It takes no case out, and the explorer's age filter and the statistics both read the band it gives.
enforced_in:
  - src/open_altio/faers/derive.py
  - src/open_altio/explorer/filters.py
  - src/open_altio/explorer/facts.py
  - src/open_altio/explorer/ui/state.js
  - tests/faers/test_demographics.py
  - tests/explorer/test_filters.py
  - tests/explorer/test_page.py
  - tests/explorer/test_case_page.py
---
# Age bands

Each case is placed in one age band from its age in years. A child given as 0 years, which cannot say whether it was a newborn, goes by the sender's own age group. The explorer's age filter and the statistics read the same band, `age_band_T`, worked out when the release is built.

A band holds the ages from `from` up to but not including `to`, each written as an age in one of FDA's units and read in years as `age-in-years` reads an age; the last band has no upper end. The exception is an age of exactly 0 in one of `zero_age_units`, or with no unit, which `age-in-years` reads as years: it goes by FDA's `age_grp` through `zero_age_groups` (`N`, neonate, is under 28 days; `I`, infant, is 28 days to under 2), and to `zero_age_band` otherwise. That band, with no range, holds only these cases. So the three youngest bands ticked together hold every case under 2. A case with no age in years has no band and reads Not given (rule `not-given`). Several bands can be ticked at once; the explorer's age menu says what the youngest three hold, and the case window shows each case's band beside its age. Since the bands are part of the release, changing them here needs a new release.

**Why:** the bands under 18 follow ICH E11: term newborns up to 27 days, infants and toddlers from 28 days to 23 months, children from 2 to 11, adolescents from 12 to 17. The older bands split the adults where FAERS reporting changes most. An age of 0 years says only "under 1": 11,499 cases are given that way (`notebooks/faers/07_demographics_units`, section 5), and FDA's `age_grp`, filled since 2014Q3, is the only thing that can place them more finely.
