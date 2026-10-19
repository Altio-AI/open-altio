---
rule: therapy-duration
line: Days from the start and end dates when both are known to the day, else from the duration FDA wrote; left empty when longer than the patient could have been treated.
values:
  unit_days: {YR: 365.25, MON: 30.4375, WK: 7, DAY: 1}
  units_a_day: {HR: 24, MIN: 1440, SEC: 86400}
  age_margin_years: 1
  max_years_unknown_age: 50
settable:
  max_years_unknown_age:
    label: Longest therapy where the age is not known (years)
    minimum: 1
enforced_in:
  - src/open_altio/faers/dates.py
  - tests/faers/test_dates.py
---
# How long a drug was taken

How long each drug was given. We work it out in days for each therapy line, from its start and end dates when both are known to the day and possible, else from the duration and unit FDA wrote, and leave it empty when it is longer than the patient could have been treated. A missing start or end date is never filled in from a duration.

`dur_days_T` on `ther_latest_T` is `end_dt_T` less `start_dt_T` plus one, when both dates are known to the day, inside the limits (`rules/date-limits.md`) and the end is not before the start. Otherwise it is FDA's `dur`, where it is a number, times the days in its unit `dur_cod`: `unit_days` for a year, month, week or day, and one over `units_a_day` for an hour, minute or second. Another unit gives none. It is empty when longer than the patient's age plus `age_margin_years` years, where the age is known (`age_years_T` 0 or more), else longer than `max_years_unknown_age` years, a year being the `unit_days` of YR. Switched off, it is empty.

**Why:** notebook `notebooks/faers/08_dates_and_codes`, section 4. E2B(R3) says the duration is usually computed from the start and end dates and is sent when the dates are not exact (G.k.4.r.6), so the dates come first. DiAna does the same and drops durations over 50 years, but it also fills a missing start or end date from the other date and the duration; we do not, since a date made that way would look like one the reporter gave.
