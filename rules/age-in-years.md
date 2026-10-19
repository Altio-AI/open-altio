---
rule: age-in-years
line: Ages given in days, weeks, months or decades are read in years, exactly; an age with no unit is in years, and a negative age or one over 122 is no age.
values:
  units:
    DEC: [10, 1]
    YR: [1, 1]
    MON: [1, 12]
    WK: [7, 365.25]
    DY: [1, 365.25]
    HR: [1, 8766]
    MIN: [1, 525960]
    SEC: [1, 31557600]
  no_unit: YR
  max_years: 122
always_on: true
why_locked: The age bands, the statistics and the duplicate rules' age guard read the age it gives, and FDA's own age and unit stay beside it as published.
enforced_in:
  - src/open_altio/faers/derive.py
  - tests/faers/test_demographics.py
  - tests/faers/test_derive.py
---
# Ages read in years

A patient's age is read in years from FDA's `age` and its unit, `age_cod`, and kept exact, never rounded. An age with no unit is in years. A negative age, or one over 122 years, is no age. FDA's `age` and `age_cod` stay as published.

`age_years_T` is `age` times the first number of its unit in `units`, divided by the second: a decade is 10 years, a month a twelfth of a year, a week 7 days, a day a year over 365.25, then hours, minutes and seconds of such days. An age with no unit is read in `no_unit`. An age in a unit `units` does not hold, or over `max_years` once converted, is no age.

FDA's number is read as written, with spaces around it and with a leading or trailing decimal point: `.8` is 0.8 and `60.` is 60. Anything else, such as `4O`, is no number, and so is a negative number. The same reader reads weights (`weight-in-kg`).

**Why:** ages with no unit are spread like ages in years, and where another version of the same case gives the same number with a unit, that unit is `YR` 99.4% of the time. Rounding to whole years, as DiAna does, would move children of 18 to 23 months out of the bands under 2. Most negative ages are `-1`, and half of those cases carry a pregnancy, birth or newborn reaction: they mark exposure before birth, not an age. Above 122 years, the oldest age on record, every age is an error, such as years written as decades. The reader once took `.9` for no number, losing the weights of 1,800 cases, most of them newborns. All of it is in `notebooks/faers/07_demographics_units`, sections 2 to 4 and 6.
