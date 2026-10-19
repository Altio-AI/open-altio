---
rule: eu-member-state
line: Since 2025Q3 about one case in ten names only the European Union; where an earlier version of the same case names the member state, we show it, and say where it came from.
values:
  code: EU
  iso_codes: mappings/faers/countries/iso-codes.csv
enforced_in:
  - src/open_altio/faers/derive.py
  - src/open_altio/faers/duplicates.py
  - src/open_altio/explorer/ui/casedialog.js
  - tests/faers/test_demographics.py
  - tests/explorer/test_case_page.py
---
# European Union cases

Since 2025Q3 about one case in ten names the European Union, not the member state, as its country, follow-ups of older cases included. Where an earlier version of the same case, as FDA published it, names a country, we use that country and say where it came from. The duplicate rules still compare the country as published, so this never splits a group of duplicates.

When `country_T` is `code` (after `legacy-country` and `country-not-given`), it becomes the occurrence country of an earlier published FAERS version of the same case number (`caseid`) whose occurrence country is an ISO 3166-1 code other than `code` (the 249 officially assigned codes, `iso_codes`); with several, the latest of them. Versions are ordered as `latest-version` orders them. `country_source_T` says where the country came from: `as published` for the case's own version, `earlier version` for one taken from an earlier version, and empty when there is no country. A case with no such version keeps `EU`, which the explorer names "European Union, member state not given" (`legacy-country`'s `noted_codes`), and the case window says when the country came from an earlier version. The duplicate rules compare `code`, as published, for every case whose country was taken this way. Switched off, `country_T` stays `EU`.

**Why:** 166,184 cases name `EU` as their country, nearly all of them published since 2025Q3, when the member state disappeared from European reports, and 96% of them begin their manufacturer case number with `EU-`. For about one in seven, an earlier version of the same case still names the country, nearly always a member state. That is FDA's own value for the same case. Reading the country from the company's case number would be a guess (`notebooks/faers/07_demographics_units`, section 7).
