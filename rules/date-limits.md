---
rule: date-limits
line: An event or therapy date after the file that holds it, or long before the patient was born, gets no clean date, so no time is worked out from it.
values:
  max_age_years: 122
  before_birth_years: 1
settable:
  max_age_years:
    label: Oldest a patient can be (years)
    minimum: 1
  before_birth_years:
    label: How long before birth a therapy date may be (years)
    minimum: 0
enforced_in:
  - src/open_altio/faers/dates.py
  - tests/faers/test_dates.py
---
# Dates that cannot be true

A date later than the file that holds it, or long before the patient was born, cannot be true, and a time worked out from it would be wrong. We check the dates times are worked out from, the event date and each therapy's start and end, and a date outside these limits gets no clean value. FDA's text is not changed.

The ceiling: a date may not be after the last day of the quarter its case version was published in (`quarter_T`). A partial date is compared at its own precision, so 202607 is after 2026Q2 and 202606 is not. The floor of a therapy date (`start_dt`, `end_dt`): its year may not be more than `before_birth_years` before the patient's birth year, where the age is known (`age_years_T` 0 or more). The birth year is the event year, else the year FDA first received the case (`init_year_T`), less the age, rounded down. Where the age is not known, the year may not be more than `max_age_years` before the year FDA first received the case. An event date has only that second floor, since the age is the age at the event. A date outside the limits has an empty `_T` and an empty `_prec_T`, with FDA's text beside them. The report, receipt, manufacturer and expiry dates are not checked. Switched off, every date is read as written.

**Why:** notebook `notebooks/faers/08_dates_and_codes`, section 1. FAERS dates are well formed, but some cannot be true: a year before 1901 is a typing slip (1012 for 2012) or a placeholder, and a date after the quarter that published it is in the future of its own file. E2B(R3) says a date cannot refer to the future. DiAna drops every date before 1985, which removes true therapy dates such as decades of thyroid or anticonvulsant treatment, so the floor follows the patient instead; 122 years is the longest human life on record. In the full 2026Q2 release the limits catch 546 event dates (97 under the floor, 449 over the ceiling), 10,481 therapy start dates (9,107 of them before birth, 7,917 of those from 1985 on, where DiAna's floor does not look) and 3,152 end dates.
