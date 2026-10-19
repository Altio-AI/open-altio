---
rule: country-not-given
line: "FDA's words COUNTRY NOT SPECIFIED, and the code A1, are read as no country: the reporter's country is used instead, and cases no longer match as duplicates on these words."
values:
  not_countries: [COUNTRY NOT SPECIFIED, A1]
enforced_in:
  - src/open_altio/faers/derive.py
  - src/open_altio/explorer/facts.py
  - src/open_altio/faers/insights/cards/versions.py
  - tests/faers/test_demographics.py
  - tests/explorer/test_explore.py
  - tests/explorer/test_case_page.py
---
# 'Country not specified' read as none

`COUNTRY NOT SPECIFIED` is FDA's way of saying a case gives no country, and `A1` is not a country code. Both are read as no country, so the country falls back to the reporter's, and cases that share only these words no longer match on country as duplicates. FDA's text is not changed.

`country_T` is the occurrence country, else the reporter's country (`legacy-country`). A value in `not_countries`, in either column, counts as empty there: an occurrence country of `A1` falls back to the reporter's country, and a case whose countries are all in `not_countries` has no country. The duplicate rules compare `country_T`, so a case with no country is never matched on it by the first rule (`dedup-default`). The explorer never offers these values as a country in its filters or charts; the case window shows the country as not given, with FDA's text beside it. Switched off, these values are read as countries, as FDA wrote them, and still shown as not given.

**Why:** `COUNTRY NOT SPECIFIED` is FDA's text for no country in `reporter_country` (FDA's FAQ for the quarterly files, question 21); read as a country, it was the country of 12,622 cases, 294 of them flagged as probable duplicates. `A1` (182 cases) is in no list of country codes, and DiAna also reads it as no country (`notebooks/faers/07_demographics_units`, section 7).
