---
rule: not-given
line: A blank, an 'unknown' or a filler number no one could mean, such as an age of 999, all read Not given, with FDA's own value beside it.
values:
  label: Not given
  unknown_words: [ASKED BUT UNKNOWN, NOT REPORTED, NOT AVAILABLE, NOT APPLICABLE, NOT SPECIFIED, NOT KNOWN,
                  UNSPECIFIED, UNKNOWN, UNKN, UNK, ASKU, NASK, N/A, 'NULL']
  glue_words: [FREQUENCY, FREQ, FORMULATION, ROUTE OF ADMINISTRATION]
  company_words: [MANUFACTURERS, MANUFACTURER, COMPANIES, COMPANY, MFR, LABELER, SPONSOR, DISTRIBUTOR, INC,
                  LLC, LTD, CORP]
  unknown_alone: [NA]
  fillers:
    nines: '9{3,}(\.0+)?'
    zero_or_nines: '(0+(\.0+)?|9{3,}(\.0+)?)'
    no_name: '([0-9[:punct:][:space:]]*|.)'
  fields:
    mfr_sndr: {words: true, glue: company_words, filler: no_name,
               codes: [CALIFORNIA DEPARTMENT OF PUBLIC HEALTH, DKMA - DANISH HEALTH AND MEDICINES AUTHORITY,
                       FOREIGN HEALTH AUTHORITY, 'PHARMAKOVIGILANCE, BFARM', SSM HEALTH ST. CLARE HOSPITAL,
                       DELL CHILDRENS HOSPITAL, "BMT LAB, KOSAIR CHILDREN'S HOSPITAL", UNIVERSITY OF CAPE TOWN PRESS,
                       SP, HERBAL PRODUCTS MANUFACTURER, COSMETIC MANUFACTURER, PHARMACOVIGILANCE,
                       PHARMACOVIGILANCE DEPARTMENT, DEPARTMENT PHARMACOVIGILANCE, US PHARMACOVIGILANCE,
                       GLOBAL PHARMACOVIGILANCE, INTERNATIONAL SAFETY + PHARMACOVIGILANCE, GLOBAL DRUG SAFETY,
                       GLOBAL CLINICAL SAFETY, GLOBAL VIGILANCE, GLOBAL REGULATORY AFFAIRS, 'PHARMACEUTICALS, INC.']}
    to_mfr: {only_report_types: [DIR]}
    auth_num: {words: true}
    mfr_num: {words: true}
    lit_ref: {words: true}
    age: {words: true, filler: nines}
    age_cod: {words: true}
    wt: {words: true, filler: zero_or_nines}
    wt_cod: {words: true}
    drugname: {no_drug_names: true, words: true}
    prod_ai: {no_drug_names: true, words: true}
    route: {words: true}
    dose_vbm: {words: true}
    cum_dose_chr: {words: true, filler: zero_or_nines}
    cum_dose_unit: {words: true}
    dechal: {codes: [U]}
    rechal: {codes: [U], codes_in_quarters: {codes: [D], from: 2012q4, to: 2015q3}}
    lot_num: {words: true}
    exp_dt: {words: true}
    nda_num: {words: true, filler: zero_or_nines}
    dose_amt: {words: true, filler: zero_or_nines}
    dose_unit: {words: true}
    dose_form: {words: true}
    dose_freq: {words: true, filler: nines}
    dur: {words: true, filler: nines}
    dur_cod: {words: true}
    indi_pt: {codes: [PRODUCT USED FOR UNKNOWN INDICATION, DRUG USE FOR UNKNOWN INDICATION]}
always_on: true
why_locked: Every screen, download and statistic reads one empty state, and FDA's own value is always kept beside it.
enforced_in:
  - src/open_altio/faers/not_given.py
  - src/open_altio/faers/derive.py
  - src/open_altio/faers/duplicates.py
  - src/open_altio/explorer/explore.py
  - src/open_altio/explorer/filters.py
  - src/open_altio/explorer/ui/charts.js
  - src/open_altio/explorer/ui/casedialog.js
  - tests/explorer/test_page.py
  - tests/faers/test_not_given.py
  - tests/faers/test_duplicates.py
  - tests/explorer/test_explore.py
  - tests/faers/statistics/test_statistics_cases.py
---
# Empty fields read Not given

A field can be empty in four ways: it is blank, it says unknown (`UNK`, `UNKNOWN MANUFACTURER`), it holds a number no one could mean (a weight of 0, an age of 999), or FDA's file had no such column that quarter. All four read **Not given**, the one empty state every screen, download and statistic shows. FDA's own value is never changed and is shown beside it.

Sex and country are read by their own rules, and only there: a sex other than female or male (`sex-codes`, so `NS` and `UNK`) and FDA's words for no country (`country-not-given`, so `COUNTRY NOT SPECIFIED`) leave `sex_T` and `country_T` empty, and an empty `sex_T` or `country_T` reads Not given, with FDA's value beside.

A value reads `label` when it is blank (nothing, or only spaces), or when its field is listed under `fields` and the value is one the field's entry names. Values are compared trimmed and in capitals:

- `codes`: the codes or terms that mean unknown in that field.
- `words: true`: free text made only of `unknown_words`, with `glue_words`, spaces and punctuation between them (`UNK` and `FREQUENCY UNKNOWN` are, `DOSE UNKNOWN` is not), or a value that is only one of `unknown_alone`. `glue` names the list of glue words a field takes instead: a sender made only of unknown words and `company_words` (`UNKNOWN MANUFACTURER`) is no company. `GENERIC` is no unknown word: `GENERICS [UK] LTD` is a company.
- For the sender, `codes` are the names that are no company: a regulator, a hospital, a university press, `SP`, or only generic words such as `HERBAL PRODUCTS MANUFACTURER` and `PHARMACOVIGILANCE DEPARTMENT`. Its `filler` is a sender with no letter in it, such as an ID number written as the name (`039976196:01`), or of one character.
- `no_drug_names: true`: a drug name in the list rule `no-drug-or-reaction` keeps (`unusable_drug_names`).
- `filler`: a value that cannot be real, as the named pattern in `fillers`: a run of three or more 9s, a zero, or for the sender `no_name`.
- `codes_in_quarters`: these codes read Not given only in FDA's files from `from` to `to`.
- `only_report_types`: the field is read only on these report types (`rept_cod`); on any other report it reads Not given.

Kept as real values, on purpose: dechallenge and rechallenge `D` (does not apply) outside the quarters above, and an age of 0 (a newborn).

Where it shows: the explorer's filters and charts, where each chart also says how many of its cases give the field, reactions counting a case with a reaction row, ingredient and WHO class (which Open Altio works out) saying "found", and outcomes saying "A serious outcome given", since FDA writes outcome rows only for serious outcomes and a case with none is not missing a field; the case window, with FDA's value beside; the clean columns of the explorer's downloads (`sex_T`, `age_years_T`, `wt_kg_T`, `country_T`), which their own rules (`sex-codes`, `age-in-years`, `weight-in-kg`, `country-not-given`) leave empty where no value is given; the statistics' strata, where a sex or age band not given is one unknown group (rule `statistics-cases`); and the duplicate key, which never compares a Not given value and reads sex as `sex_T` (rule `dedup-default`). The release's own tables keep FDA's columns as published.

**Why:** notebook `notebooks/faers/03_empty_fields`. Senders differ in whether they write blank or `UNKNOWN` for the same thing, and FDA's own files moved route from `UNKNOWN` to blank in 2026Q2, so telling them apart would show habits, not information. Rechallenge `D` from 2012Q4 to 2015Q3 sits on about 76% of drug rows, against well under 10% in other quarters; when such a case is sent again from 2015Q4 on, the same drug's rechallenge is blank in 96% of them and `D` in almost none, so the sender never said it. Before 2012Q4, `D` is a real and common answer. `to_mfr` asks whether a reporter who wrote to FDA also told the company, so it means something only on direct reports; on company reports it is blank in almost every quarter and a filler `N` in 2014Q1 to 2015Q3.
