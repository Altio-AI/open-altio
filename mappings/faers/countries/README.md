# Legacy AERS country names as ISO codes

For anyone checking how a legacy case's country is compared with a FAERS case's.

Legacy AERS (2004Q1 to 2012Q3) writes `reporter_country` as a name in capitals, for example `UNITED STATES`. FAERS (2012Q4 onward) writes the ISO 3166-1 two-letter code, `US`. FDA's own FAQ for the quarterly files says it moved to ISO 3166-1 codes and that "users may need to update their legacy data to the latest codes". `accepted.csv` does that for every name legacy AERS ever used: 208 names, read by the release build into `country_T` (`rules/legacy-country.md`). The raw `reporter_country` is never changed.

## The file

| Column | What |
|---|---|
| `fda_value` | The name exactly as legacy AERS wrote it, case and punctuation included |
| `iso2` | The two-letter code FAERS uses for the same country |
| `evidence` | Why: an ISO 3166-1 name, an earlier ISO 3166-1 name, or a code ISO keeps reserved |

## How it was checked

- 176 names are ISO 3166-1 names as written (the ISO list as published by DataHub's `country-list`, also bundled in AEOLUS's `faersdbstats`).
- The other 32 are earlier ISO 3166-1 names or names without their accents (`BOSNIA AND HERZEGOWINA`, `CROATIA (local name: Hrvatska)`, `REUNION`), each looked up by hand. AEOLUS lists the same 32 hand-added names; ours differ in two: `European Union` is `EU` and `FRANCE, METROPOLITAN` is `FX`, the codes FAERS itself uses.
- FDA carried 82,342 AERS cases into FAERS in 2012 under the same case number. Of the 81,604 with a legacy country, 77,772 have a named country on their FAERS version, and for 98.3% of them it is the code this file gives; the other 3,832 say `COUNTRY NOT SPECIFIED`. Notebook `notebooks/faers/02_case_versions` shows the check.
- Two codes never appear in FAERS: `CS` (Serbia and Montenegro, 35 legacy cases) and `SJ` (one case). Those cases can match other legacy cases but never a FAERS case.

## Review

Reviewed row by row with the evidence in notebook `notebooks/faers/02_case_versions`, including `European Union` as `EU` and `FRANCE, METROPOLITAN` as `FX`. `SERBIA AND MONTENEGRO` stays `CS`: its 35 cases were received from 2006 to 2011, 31 of them after the country split in June 2006, and reading them as Serbia would be a guess. A later change to any row is its own reviewed change with its evidence.

## ISO 3166-1 codes

`iso-codes.csv` lists the 249 officially assigned ISO 3166-1 two-letter codes, one row each (`iso2`, with its `evidence`). Rule `eu-member-state` reads it: a case that names only the European Union (`EU`) takes the country of an earlier version of the same case only when that version gives one of these codes, so a retired code (`YU`, `AN`), a user-assigned one (`XK`, `XI`) or `A1` is never taken. The list is ISO's own, as published on its online browsing platform; `EU` is not on it, since ISO only reserves it. Notebook `notebooks/faers/07_demographics_units` uses the same list.
