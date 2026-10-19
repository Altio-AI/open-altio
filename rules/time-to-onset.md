---
rule: time-to-onset
line: Days from a drug's first dose to the reaction, counted only from two dates known to the day and possible, so a placeholder or impossible date never gives a wrong number.
values:
  first_dose_day: 1
enforced_in:
  - src/open_altio/faers/dates.py
  - src/open_altio/faers/statistics/onset.py
  - tests/faers/test_dates.py
  - tests/faers/statistics/test_statistics_onset.py
---
# Time to onset

How long after a drug was started the reaction began. We count it in days for each drug record, only from an event date and a therapy start date both known to the day and both possible, so a padded or impossible date never gives a wrong number.

`time_to_onset_T` on `drug_onset_T`, one row per drug record (`era_T`, `primaryid`, `quarter_T`, `drug_seq`), is the event date (`event_dt_T`) less the drug's earliest therapy start known to the day (`start_dt_T` of its therapy lines, where `dsg_drug_seq` is the `drug_seq`), plus `first_dose_day`: the day of the first dose is day 1, as E2B(R3) counts it (G.k.9.i.3.1). FDA writes one row per regimen, and since 2024Q4 can repeat a `drug_seq` across rows, so the earliest start of the record is taken however many rows it has. It is empty when the event date is not known to the day (`rules/event-date-precision.md`), when either date is outside the limits (`rules/date-limits.md`), and when the result is less than `first_dose_day`: the event came before the first dose. It is empty too when another therapy line of the record has a start known only to its month or year, inside the limits, that could be on or before the earliest full start (its yyyymm or yyyy is not after that date's): the first dose may be earlier than the date counted from. Switched off, it is empty.

Where it is empty, `time_to_onset_reason_T` says why, the first of these that holds: `padded_event_date`, the event date is on the 1st and read as known only to its month or year (`rules/event-date-precision.md`); `event_date_not_exact`, the event date is not known to the day for another reason (not given, partial, no such day, or outside the limits); `first_dose_not_exact`, no therapy start of the record is known to the day, or a partial start could be earlier; `event_before_first_dose`. Switched off, it is empty too.

**For each ingredient and reaction** (`statistics_T`), on the cases the statistics count (`statistics-cases`): the drugs are the suspect drug records that give the ingredient, in the cases that name the reaction. `onset_drugs_T` counts those with a time to onset and `onset_days_T` is the median of their values (the middle value, or the mean of the two middle values); each `no_onset_<reason>_T` counts those without one, by `time_to_onset_reason_T`. A drug with no value never adds to the median. A case naming the ingredient in two drug records gives two drugs.

**Why:** notebook `notebooks/faers/08_dates_and_codes`, section 3. Where the event date may be padded, 42% of therapy rows have the event before the drug's start, against 15% where it is not, because a reaction in March written as 1 January lands before a drug started in February. DiAna drops values of 0 or less only for events before 2013, which misses every padded date published since 2021 and keeps padded dates that give a positive but wrong value.
