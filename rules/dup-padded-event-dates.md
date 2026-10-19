---
rule: dup-padded-event-dates
line: A date known only to its year is often written 1 January; in large look-alike groups from one company, such a date no longer makes cases match, so different patients stay apart.
values:
  min_group_size: 8
  full_date_length: 8
  padded_month_day: '0101'
  one_sender_only: true
settable:
  min_group_size:
    label: Applies to groups of at least (cases)
    minimum: 2
  one_sender_only:
    label: Only when one company sent every case
enforced_in:
  - src/open_altio/faers/duplicates.py
  - tests/faers/test_duplicates.py
  - tests/faers/test_user_rules.py
  - src/open_altio/faers/insights/cards/duplicates.py
  - tests/faers/insights/test_cards.py
---
# Placeholder dates don't merge patients

When only the year of an event is known, FAERS often records it as 1 January. In large groups of look-alike cases from one company, such a date says nothing, so we do not count it as a match. This keeps different patients from being merged into one.

In a group of the AEOLUS rule (`rules/dedup-default.md`) with `min_group_size` or more cases whose shared event date is padded, and whose cases were all sent by one company, the event date does not count as a match, so that rule sets nothing aside in the group. A date is padded when it is a full date (`full_date_length` characters) on 1 January (ending in `padded_month_day`), or shorter: a month or a year only. The 1st of any other month still counts. One company means every case has the same sender (`mfr_sndr`, trimmed and in capitals); a case with no sender counts as another sender. The cases can still be grouped by the manufacturer number (`rules/dup-manufacturer-number.md`). With `one_sender_only: false` the guard applies whoever sent the cases. Switched off, a padded date counts like any other.

`dup_padded_date_T` on `case_dup_T` marks the cases of the groups the guard leaves whole.

**Why:** notebook `notebooks/faers/04_duplicates`. A padded date matches every other case padded the same way, so one company's common drug and reaction pair from one year can form one large group of different patients, such as 36 lawyer reports all dated 1 January 2018. In groups of up to 7 cases the shared date falls on 1 January about 10% of the time, as in FAERS overall; from 8 cases it climbs (21% at 8, about half at 10 to 12, three quarters from 15). The 1st of other months does not climb with group size. When several companies send the same padded case, it is most often one published case that every maker reported, such as eight makers each reporting the same 53-year-old man with the same drugs and reactions: those are real duplicates and stay set aside. Of the 441 large padded groups in the 2026Q2 data, 68 (621 cases) came from two or more companies; the 373 from one company are mostly one sender's reports of one product over a few years. Event-date precision becomes a field in a later study of duplicate probability.
