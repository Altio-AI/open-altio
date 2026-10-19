---
rule: legacy-country
line: FDA's old system wrote countries as names, such as UNITED STATES, and the new one as codes, such as US; we read the names as codes, so filters and duplicate checks work across both.
values:
  mapping: mappings/faers/countries/accepted.csv
  # codes that name no country of today: the name shown, and the note beside it
  noted_codes:
    CS:
      name: Serbia and Montenegro
      note: >-
        A country from 2003 to 2006, since split into Serbia and Montenegro; the report does not say which.
        Before 1993 CS was Czechoslovakia's code, but here it never means Czechoslovakia.
    YU:
      name: Yugoslavia
      note: A country until 2003, when it was renamed Serbia and Montenegro; reports still use its code.
    AN:
      name: Netherlands Antilles
      note: >-
        Dissolved in 2010 into Curaçao, Sint Maarten and the Caribbean Netherlands; reports still use its
        code.
    EU:
      name: European Union, member state not given
      note: Not a country. The report says only that it came from the European Union.
    FX:
      name: Metropolitan France
      note: France in Europe, without its overseas regions, a code taken out of use in 1997.
enforced_in:
  - src/open_altio/faers/derive.py
  - src/open_altio/faers/release.py
  - src/open_altio/explorer/facts.py
  - tests/explorer/test_api.py
  - tests/explorer/test_case_page.py
  - tests/faers/test_eras.py
  - tests/faers/test_user_rules.py
  - tests/explorer/test_filters.py
---
# Old country names read as codes

FDA's old system wrote countries as names, such as UNITED STATES; the new one writes codes, such as US. We read the old names as codes, so country filters and duplicate matching work across both systems. FDA's own text is not changed.

Legacy AERS writes the reporter's country as a name (`UNITED STATES`); FAERS writes the ISO 3166-1 code (`US`). `country_T` is the occurrence country, else the reporter country, with a legacy name read through the reviewed mapping in `mapping`. The duplicate key and the explorer's country filter use `country_T`, so a legacy case and a FAERS case from the same country can match. The raw columns are never changed. A legacy country name the mapping does not hold stops the build, with the name in the refusal. Switched off, `country_T` holds a legacy name as FDA wrote it.

`SERBIA AND MONTENEGRO` stays `CS`, the code of the country it names, although FAERS never uses it: its 35 cases were received from 2006 to 2011, mostly after the country split, and reading them as Serbia would be a guess.

The explorer names each country beside its code, with FDA's own value beside it. The codes in `noted_codes` name no country of today, so each is shown with its name and a short note: `CS` is never shown bare, since it was Czechoslovakia's code before it was Serbia and Montenegro's. `EU` is named "European Union, member state not given"; where the member state comes from an earlier version of the case, the case window says so (`eu-member-state`). FDA's words for no country are shown as not given, with FDA's text beside (`country-not-given`).

**Why:** compared as raw text, no duplicate group could span the two eras, and a country filter found only one era's cases. FDA's own FAQ tells users to update legacy data to ISO 3166-1 codes. Notebook `notebooks/faers/02_case_versions` counts the two eras' country spellings and the cases they split.
