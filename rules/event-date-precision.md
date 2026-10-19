---
rule: event-date-precision
line: FDA's old system, and FAERS since 2021, write an event date known only to its month as the 1st, and to its year as 1 January; we read such dates only that far, and work out no time to onset from them.
values:
  faers_from_quarter: 2021q3
  month_day: '01'
  year_month_day: '0101'
enforced_in:
  - src/open_altio/faers/dates.py
  - src/open_altio/faers/insights/cards/dates_codes.py
  - tests/faers/test_dates.py
---
# Dates on the 1st read as month or year

Legacy AERS, and FAERS since 2021, write an event date known only to its month as the 1st of that month, and one known only to its year as 1 January. Such a date cannot be told from a true 1st, so in those versions we read an event date on the 1st as known to the month, and on 1 January as known to the year. No time to onset is worked out from it. FDA's text is not changed.

In a case version from legacy AERS (`era_T` legacy), or from FAERS published in `faers_from_quarter` or later (`quarter_T`), a full event date (yyyymmdd) ending in `year_month_day` has `event_dt_prec_T` 4, and one ending in `month_day` has 6. `event_dt_T` holds a date only where `event_dt_prec_T` is 8, as it does for the partial dates FDA writes itself. FAERS versions published before `faers_from_quarter` are read as written. The duplicate rules compare FDA's own `event_dt`, so this rule changes no group and no kept case; padded dates there have their own rule (`rules/dup-padded-event-dates.md`). Switched off, every full event date is known to the day.

**Why:** notebook `notebooks/faers/08_dates_and_codes`, section 2. From 2021Q4 FDA publishes no partial event dates, and 42.6% of them fall on the 1st of a month, against 4.8 to 8.8% a quarter in FAERS from 2012Q4 to 2021Q1; legacy AERS has 32 to 50%. 2021Q3 is a mix of both. Therapy dates were not padded: they stay partial at the same rate throughout. In the 2026Q2 release, 2,033,522 cases of the default set have an event date this rule reads to the month or the year.
