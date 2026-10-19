# Data dictionary

For anyone querying a release: every file, table and column, and where each comes from.

This page lists the files in a release folder, then each table and its columns.

Columns are marked **FDA** or **Open Altio**:

- **FDA** columns are as FDA published them, as text.
- **Open Altio** columns are worked out by Open Altio. The name ends in `_T`.

Counts in the examples are from the 2026Q2 release.

## The release folder

```
2026Q2/                          named after the latest FDA quarter in it
  manifest.json                  what was built, from which FDA files, when, with which code
  funnel.json                    the count after each step
  methods.json                   the methods page's data: steps, rules, evidence, limits
  views.sql                      the deduplicated views, over the tables by name
  explorer.duckdb                the explorer's own database, built from the Parquet
  parquet/
    demo.parquet ... indi.parquet    FDA's tables, every column verbatim
    deleted.parquet                  FDA's deleted-case lists
    quarters_T.parquet ...           Open Altio's tables
    label_candidates_T.parquet ...   FDA drug labels, only when the build was given a labels folder
  licensed/                      MedDRA's part, only when you add your own MedDRA files
```

- **In Python,** `open_altio.faers.open_release(folder)` gives a DuckDB connection with every table and view registered.
- **In any other tool,** read the Parquet directly. To get the views, create a view per table over its Parquet file and run `views.sql`, which names tables, never paths.

## FDA's tables

One table per FDA file type, stacked across all quarters, every column as text exactly as FDA wrote it.

- **Empty fields** are empty (NULL).
- **Every other value** is kept as written, spaces included.
- **A column one era does not publish** is empty in that era's rows.

| Table | One row per | Holds |
|---|---|---|
| `demo` | report version | Dates, patient, reporter, sender and country |
| `drug` | drug on a report version | Name, active ingredient, role, route, dose, dechallenge and rechallenge |
| `reac` | reaction on a report version | The reaction as a MedDRA preferred term, as FDA published it |
| `outc` | outcome on a report version | The outcome code |
| `rpsr` | report source on a report version | Where the report came from |
| `ther` | therapy on a report version | Start and end dates and duration, per drug |
| `indi` | indication on a report version | What the drug was given for, as a MedDRA preferred term |
| `deleted` | line of a deleted-case list | `caseid` of a case FDA deleted |

Two Open Altio columns are added to every row:

| Column | What |
|---|---|
| `quarter_T` | The FDA quarter whose file held the row, `2004q1` to `2026q2`. On `deleted`, FDA's one-off whole-history list is `pre2019q1` |
| `era_T` | `legacy` (AERS layout, 2004Q1 to 2012Q3) or `faers` (2012Q4 on), read from the file's header. Not on `deleted` |

### Column names

FDA's names, in lower case, with these renames and no others, where the two eras spell the same column two ways:

| Table | FDA's name | Release name | Why |
|---|---|---|---|
| all | `isr` | `primaryid` | Legacy AERS keys report versions by ISR |
| all | `case` | `caseid` | Legacy AERS calls the case CASE |
| `demo` | `i_f_cod` | `i_f_code` | Legacy spelling |
| `demo` | `gndr_cod` | `sex` | Legacy and 2012Q4 to 2014Q2 spelling |
| `drug` | `lot_nbr` | `lot_num` | 2012Q4 spelling |
| `outc` | `outc_code` | `outc_cod` | 2012Q4 spelling |
| `ther` | `drug_seq` | `dsg_drug_seq` | Legacy THER calls it DRUG_SEQ |
| `indi` | `drug_seq` | `indi_drug_seq` | Legacy INDI calls it DRUG_SEQ |

The manifest records which renames each file needed (`inputs[].renamed`).

### FDA's columns

| Column | Table | What |
|---|---|---|
| `primaryid` | all | Report number: the case number plus its version (ISR in AERS) |
| `caseid` | all | Case number, the same across a case's versions. Legacy child tables have none |
| `caseversion` | `demo` | The case's version: 1, 2, ... (empty in AERS) |
| `i_f_code` | `demo` | I for an initial report, F for a follow-up |
| `event_dt` | `demo` | When the event happened: yyyymmdd, yyyymm or yyyy, as FDA gave it |
| `mfr_dt` | `demo` | When the manufacturer first heard of it |
| `init_fda_dt` | `demo` | When FDA first received the case |
| `fda_dt` | `demo` | When FDA received this version |
| `rept_cod` | `demo` | Report type: EXP expedited (15-day), PER periodic, DIR direct from the public or a health professional, 5DAY a drug-device combination needing remedial action, 30DAY a device malfunction on a drug-device combination. Kept as FDA codes it; 30DAY and 5DAY are not counted as EXP |
| `auth_num` | `demo` | A regulator's own number for the case |
| `mfr_num` | `demo` | The manufacturer's own number for the case |
| `mfr_sndr` | `demo` | Who sent the report to FDA |
| `lit_ref` | `demo` | Literature reference |
| `age`, `age_cod` | `demo` | Age, and its unit: YR, MON, WK, DY, HR, DEC |
| `age_grp` | `demo` | Age group: N neonate, I infant, C child, T adolescent, A adult, E elderly |
| `sex` | `demo` | F, M, UNK, NS, or empty |
| `e_sub` | `demo` | Y when the report came in electronically |
| `wt`, `wt_cod` | `demo` | Weight, and its unit: KG, LBS, GMS |
| `rept_dt` | `demo` | When the report was sent |
| `to_mfr` | `demo` | Y when the reporter also told the manufacturer |
| `occp_cod` | `demo` | Who reported: MD physician, PH pharmacist, OT other health professional, LW lawyer, CN consumer. From 2020 FDA writes HP where it wrote OT; a few older cases say RN. Read as one type in `reporter_type_T` |
| `reporter_country` | `demo` | The reporter's country (a name in AERS, an ISO code in FAERS) |
| `occr_country` | `demo` | The country where the event happened (FAERS only) |
| `foll_seq`, `image`, `death_dt`, `confid` | `demo` | AERS only: follow-up number, FDA's image reference, date of death, confidential flag |
| `drug_seq` | `drug` | The drug's number on the report |
| `role_cod` | `drug` | PS primary suspect, SS secondary suspect, C concomitant, I interacting. Kept as FDA codes it; the explorer counts PS and SS unless you tick the others (rule `explorer-drug-counts`) |
| `drugname` | `drug` | The drug's name as reported |
| `prod_ai` | `drug` | The active ingredient as FDA coded it |
| `val_vbm` | `drug` | 1 when the name was checked against FDA's list, 2 when taken as written |
| `route` | `drug` | How it was given |
| `dose_vbm` | `drug` | The dose as written |
| `cum_dose_chr`, `cum_dose_unit` | `drug` | Cumulative dose and its unit |
| `dechal` | `drug` | Did the reaction stop when the drug stopped: Y, N, U unknown, D does not apply |
| `rechal` | `drug` | Did it come back when the drug restarted: Y, N, U unknown, D does not apply |
| `lot_num`, `exp_dt`, `nda_num` | `drug` | Lot number, expiry date, FDA application number |
| `dose_amt`, `dose_unit`, `dose_form`, `dose_freq` | `drug` | Dose amount, its unit, dose form, how often. FDA codes how often, for example QD daily, BID twice a day, QOW every other week, /wk per week; the case window names each code in FDA's words |
| `pt` | `reac` | The reaction: a MedDRA preferred term, as FDA published it |
| `drug_rec_act` | `reac` | A reaction that came back when the drug restarted |
| `outc_cod` | `outc` | DE death, LT life-threatening, HO hospitalisation, DS disability, CA congenital anomaly, RI required intervention, OT other serious |
| `rpsr_cod` | `rpsr` | Report source, for example HP health professional, CSM consumer, LIT literature, SDY study, FGN foreign |
| `dsg_drug_seq` | `ther` | The `drug_seq` this therapy belongs to |
| `start_dt`, `end_dt` | `ther` | Therapy start and end, as FDA gave them |
| `dur`, `dur_cod` | `ther` | Therapy duration and its unit |
| `indi_drug_seq` | `indi` | The `drug_seq` this indication belongs to |
| `indi_pt` | `indi` | What the drug was given for: a MedDRA preferred term |

FDA documents its own fields in the ASCII file description that comes with each quarterly file.

## Open Altio's tables

The steps, in order. Each table carries FDA's columns beside Open Altio's, so a reader needs no join to see both.

| Table | What it is |
|---|---|
| `quarters_T` | One row per quarter: `quarter_T`, `era_T`, `qnum_T` (the quarter as a sortable number, yyyyq) |
| `demo_T` | Every report version, nothing removed: FDA's `demo` columns plus the typed columns below |
| `demo_latest_T` | One row per case across AERS and FAERS: the highest `caseversion_T`, then the latest `fda_dt`, then the latest quarter, then the highest `primaryid`. A case FDA carried from AERS into FAERS keeps its FAERS version. A legacy row with no CASE is its own case |
| `deleted_cases_T` | Each `caseid` on any of FDA's deleted-case lists, once: `first_listed_quarter_T`, `n_listings_T`, `in_all_history_list_T` |
| `case_latest_T` | The case table: `demo_latest_T` less the cases on a deleted-case list, in both eras, with the duplicate columns below. Every case stays here, duplicates included |
| `drug_latest_T` ... `indi_latest_T` | The rows of `drug`, `reac`, `outc`, `rpsr`, `ther` and `indi` that belong to a case in `case_latest_T` |
| `drug_route_T` | One row per drug record (`era_T`, `primaryid`, `quarter_T`, `drug_seq`) of `drug_latest_T`: its cleaned route, below |
| `case_dup_T` | One row per case in `case_latest_T`: the keys each duplicate rule compares, and the group it puts the case in |
| `drug_onset_T` | One row per drug record of `drug_latest_T` (`era_T`, `primaryid`, `quarter_T`, `drug_seq`): its `time_to_onset_T`, and `time_to_onset_reason_T` where it has none |
| `drug_substance_T` | One row per drug record of `drug_latest_T` (`era_T`, `primaryid`, `quarter_T`, `drug_seq`): its ingredients and where they came from. Since 2024Q4 FDA writes some drug records on one row per dose; they share one row here |
| `drug_ingredient_T` | One row per drug record and ingredient, keyed the same way |
| `statistics_T` | One row per suspect ingredient and reaction named together in at least one counted case: EBGM, PRR, ROR, RRR, IC and the time to onset (below). Absent from a release built without the drug ingredients |
| `statistics_strata_T` | One row per pair of `statistics_T` and value of an age band or a sex where the pair has a case: its ROR within that value (below). Absent where `statistics_T` is |
| `statistics_as_published_T`, `statistics_strata_as_published_T` | The same two tables counted by FDA's text, as in a release without MedDRA, for anyone shown reactions as FDA wrote them. Only in a release with MedDRA |
| `atc_index_T`, `atc_drug_T`, `atc_drug_codes_T` | WHO's drug classes, when the release includes them ([below](#who-drug-classes)) |
| `atc_statistics_T`, `atc_statistics_ingredients_T` | The statistics of each WHO class and reaction, at each class level, and each ingredient's classes, when the release includes the classes and the drug ingredients ([below](#statistics-of-each-class)) |

### Typed columns

On `demo_T`, and carried into `demo_latest_T` and `case_latest_T`:

| Column | What |
|---|---|
| `fda_dt_T`, `init_fda_dt_T`, `rept_dt_T`, `mfr_dt_T`, `death_dt_T` | The date as a date, only where FDA gave a full, valid yyyymmdd. A year or a year and month alone, or an impossible day, is empty |
| `<date>_prec_T` | How many digits FDA gave for that date: 8, 6 or 4; empty when it was empty or another length |
| `event_dt_T`, `event_dt_prec_T` | The event date as a date, only where it is known to the day and can be true, and how much of it is known: 8 the day, 6 the month, 4 the year. A full date FDA padded to the 1st is known to the month, or to the year on 1 January ([event-date-precision](https://github.com/Altio-AI/open-altio/blob/main/rules/event-date-precision.md)); a date after its quarter or older than any patient has neither ([date-limits](https://github.com/Altio-AI/open-altio/blob/main/rules/date-limits.md)) |
| `first_fda_dt_T` | When FDA first received the case: `init_fda_dt`, else `fda_dt` (AERS has no `init_fda_dt`) |
| `init_year_T`, `fda_year_T` | The years of `first_fda_dt_T` and `fda_dt` |
| `caseversion_T` | `caseversion` as a number; empty in AERS |
| `sex_T` | The patient's sex, F or M; empty for every other code, such as NS or UNK ([sex-codes](https://github.com/Altio-AI/open-altio/blob/main/rules/sex-codes.md)) |
| `age_years_T` | Age in years, exact, from `age` and `age_cod`: DEC times 10, YR as is, MON over 12, a week as 7 days, DY over 365.25, then hours, minutes and seconds. An age with no unit is in years. Empty for another unit, a value that is not a number, a negative age or one over 122 years ([age-in-years](https://github.com/Altio-AI/open-altio/blob/main/rules/age-in-years.md)) |
| `age_band_T` | The age band the explorer's filter and the statistics read. An age of exactly 0 years goes by `age_grp`. Empty when no age is given ([age-bands](https://github.com/Altio-AI/open-altio/blob/main/rules/age-bands.md)) |
| `wt_kg_T` | Weight in kilograms, from `wt` and `wt_cod`: KG or KGS as is, LBS times 0.45359237, GMS over 1,000. Empty with no unit or another unit, at zero or over 635 kg ([weight-in-kg](https://github.com/Altio-AI/open-altio/blob/main/rules/weight-in-kg.md)) |
| `case_key_T` | The case's key: `caseid`, or `ISR:` and the `primaryid` for a legacy report with no CASE |
| `country_T` | Where the event happened, else the reporter's country, as an ISO 3166-1 code. A legacy country name (`UNITED STATES`) is read as its code (`US`) through the reviewed list in [`mappings/faers/countries/`](https://github.com/Altio-AI/open-altio/tree/main/mappings/faers/countries). `COUNTRY NOT SPECIFIED` and `A1` are no country. A case that names only the European Union (`EU`) takes the country of an earlier version of the same case where one gives it |
| `country_source_T` | Where `country_T` came from: `as published`, or `earlier version` when an `EU` case took its country from an earlier version; empty with no country |
| `company_T` | The company that sent the report: a sender spelling, in either era, read as its company's name through the reviewed list in [`mappings/faers/senders/`](https://github.com/Altio-AI/open-altio/tree/main/mappings/faers/senders) (`ELI LILLY AND CO` and `ELI LILLY AND COMPANY` are `Eli Lilly`), else `mfr_sndr` trimmed, as written. Empty on a direct report (`rept_cod` DIR), sent straight to FDA by no company, and where the sender names no company: blank, only saying unknown, FDA's own intake `FDA-CTU`, a regulator, a hospital, an ID number or only generic words ([rule company-names](https://github.com/Altio-AI/open-altio/blob/main/rules/company-names.md)) |
| `reporter_type_T` | Who reported, as the ICH E2B(R3) reporter qualification of `occp_cod`: 1 physician (MD), 2 pharmacist (PH), 3 other health professional (OT, HP or RN), 4 lawyer (LW), 5 consumer or other non health professional (CN); empty for any other code. Read through the reviewed list in [`mappings/faers/reporter_types/`](https://github.com/Altio-AI/open-altio/tree/main/mappings/faers/reporter_types) ([reporter-type](https://github.com/Altio-AI/open-altio/blob/main/rules/reporter-type.md)) |

On the child tables:

| Column | Table | What |
|---|---|---|
| `drugname_norm_T`, `prod_ai_norm_T` | `drug_latest_T` | The name in capitals, spaces collapsed and trimmed, trailing periods removed |
| `pt_norm_T` | `reac_latest_T` | `pt` in capitals, so a legacy term (`DRUG INEFFECTIVE`) equals the FAERS spelling (`Drug ineffective`) |
| `pt_spelling_T`, `indi_pt_spelling_T` | `reac_latest_T`, `indi_latest_T` | The term to show: on a legacy row, the spelling FAERS uses for the same term (`DRUG INEFFECTIVE` is `Drug ineffective`), else `pt` or `indi_pt` as FDA wrote it. Taken from FAERS's own text, with no MedDRA file |
| `start_dt_T`, `end_dt_T`, `start_dt_prec_T`, `end_dt_prec_T` | `ther_latest_T` | The therapy dates as dates, where FDA gave a full, valid yyyymmdd, and how many digits it gave: 8, 6 or 4. A date after its quarter, or long before the patient was born, has neither ([date-limits](https://github.com/Altio-AI/open-altio/blob/main/rules/date-limits.md)) |
| `dur_days_T` | `ther_latest_T` | The therapy's duration in days: from its two dates, else from `dur` and `dur_cod`; empty when longer than the patient could have been treated ([therapy-duration](https://github.com/Altio-AI/open-altio/blob/main/rules/therapy-duration.md)) |
| `time_to_onset_T` | `drug_onset_T` | Days from the drug's first dose, counted as day 1, to the event, from two dates known to the day; empty when the event came first ([time-to-onset](https://github.com/Altio-AI/open-altio/blob/main/rules/time-to-onset.md)) |
| `time_to_onset_reason_T` | `drug_onset_T` | Why a drug has no time to onset: `padded_event_date`, `event_date_not_exact`, `first_dose_not_exact` or `event_before_first_dose`; empty where it has one ([time-to-onset](https://github.com/Altio-AI/open-altio/blob/main/rules/time-to-onset.md)) |
| `route_T` | `drug_route_T` | FDA's route as an ICH E2B route code (`048` Oral); `065` when the record's rows give different routes; empty when FDA gave none |
| `route_source_T` | `drug_route_T` | Which of FDA's fields said something about the route on any row, joined with `+` (`route+dose_form`); `disagree` when they contradict each other on a row; `none` |
| `route_family_T` | `drug_route_T` | The route family when there is exactly one: `by_mouth`, `under_tongue`, `injected`, `inhaled`, `nasal`, `rectal`, `vaginal`, `transdermal`, `skin`, `eye`, `ear`, `other`; else `unknown` |
| `route_families_T` | `drug_route_T` | Every family the record could be in, sorted and joined with `;`: on each row, those its route, dose form and drug name all allow, or, when they contradict each other, any of them names; then every family one of its rows could be in, a row being one dosage regimen; empty when nothing is known. The methods page explains it |

### Duplicate columns

Two rules find probable duplicates: the AEOLUS rule and the same manufacturer case number from the same sender. Groups that share a case are one group. The methods page explains both, with their guards.

| Column | On | What |
|---|---|---|
| `dup_key_T` | `case_dup_T` | What the AEOLUS rule compares, joined with a vertical bar: event date, age, age unit, sex, country, the set of drug names, the set of reaction terms. Empty when any part reads Not given (blank, says unknown or a filler, [rule not-given](https://github.com/Altio-AI/open-altio/blob/main/rules/not-given.md)), and then that rule never compares the case |
| `dup_number_key_T` | `case_dup_T` | The sender and manufacturer case number as the second rule compares them. Empty when either is empty |
| `dup_padded_date_T` | `case_dup_T` | True for the cases of a large one-sender group left whole because its shared event date is padded (1 January, or a month or year only) |
| `dup_group_T` | `case_dup_T`, `case_latest_T` | A number shared by every case of one group; empty for a case in no group |
| `probable_duplicate_T` | `case_dup_T`, `case_latest_T` | True for every case in a group, the shown one included |
| `dup_kept_T` | `case_dup_T`, `case_latest_T` | False only for the copies a group sets aside. The shown copy and every case in no group are kept |
| `group_first_dt_T` | `case_dup_T`, `case_latest_T` | The earliest `first_fda_dt_T` in the case's group, or the case's own when it is in no group. Received-date filters and sorting use it |
| `dup_rule_T` | `case_dup_T`, `case_latest_T` | Which rules put the case in its group: `aeolus`, `manufacturer_number`, `manufacturer_number_country_code` |
| `dup_shown_case_T` | `case_dup_T`, `case_latest_T` | The `case_key_T` of the group's shown copy, on every case of the group |
| `dup_other_cases_T` | `case_dup_T`, `case_latest_T` | On the shown copy only: the `case_key_T` of the copies set aside, earliest received first |
| `no_drug_or_reaction_T` | `case_dup_T`, `case_latest_T` | The report has no usable drug or no usable reaction. Never hidden for it |
| `serious_no_drug_or_reaction_T` | `case_dup_T`, `case_latest_T` | As above, and the report has a serious outcome code |

### Drug ingredient columns

Each drug name is read to its ingredients through the open DiAna dictionary, with FDA's `prod_ai` where the name is not in it, and our reviewed corrections.

- **The rule** is `rules/drug-names.md`.
- **The corrections** are in `mappings/faers/drug_names/`.
- **Without the dictionary,** a release built without it has neither table.

The explorer counts a drug by these columns. On a product page and in the Drugs filter, a drug is an ingredient or a combination as `substance_T` names it, counted in any product containing it unless you choose the exact product (rule `explorer-drug-counts`). Its database carries `substance_T` on each drug row, and `explorer_ingredient_T` and `explorer_no_ingredient_T` to find them fast.

| Column | On | What |
|---|---|---|
| `substance_T` | `drug_substance_T` | The ingredients in lower case, as international names without their salts; a combination's sorted and joined with `;` (`sacubitril;valsartan`). Empty where none was found |
| `substance_source_T` | `drug_substance_T` | Where they came from: `diana_name` (DiAna, by the drug name), `diana_prod_ai` (DiAna, by FDA's `prod_ai`), `correction` (our reviewed correction changed DiAna's answer) or `none` |
| `diana_trial_T` | `drug_substance_T` | True when DiAna marks the record a trial product: a named study drug, placebo or a blinded drug. The label flags give such a record none. Unreliable from 2021 on |
| `ingredient_T` | `drug_ingredient_T` | One ingredient of the record |

### Statistics columns

- **Counted on** the cases rule `statistics-cases` names: the kept cases that name a suspect ingredient and a reaction.
- **Each statistic's formula, source and presets** are its rule (`ebgm`, `prr`, `ror`, `rrr`, `ic`).
- **An empty value** is one the table cannot give, never infinity.

| Column | What |
|---|---|
| `ingredient_T`, `reaction_T` | The ingredient, as `drug_ingredient_T` names it, and the reaction: in a release with MedDRA, its current preferred term as MedDRA writes it; without, FDA's text in lower case with runs of spaces as one, as the explorer matches it. The manifest's `statistics` entry says which (`reaction_key`) |
| `cases_T` | Cases naming both (a) |
| `ingredient_cases_T`, `reaction_cases_T` | Cases naming the ingredient (a + b), and the reaction (a + c) |
| `expected_T` | Cases expected within age band, sex and year received, summed over them (EBGM's E) |
| `ebgm_T`, `eb05_T`, `eb95_T` | EBGM and its 5th and 95th percentiles; empty when the prior could not be fitted |
| `prr_T`, `chi_square_T`, `chi_square_yates_T` | PRR, and its chi-square without and with Yates' correction |
| `ror_T`, `ror_lower_T`, `ror_upper_T` | ROR and its 95% interval |
| `rrr_T` | Cases over the crude expected count, (a + b)(a + c) / N |
| `ic_T`, `ic025_T` | The information component and the lower end of its 95% interval |
| `onset_days_T`, `onset_drugs_T` | The median time to onset, in days, over the pair's suspect drugs that have one (`time_to_onset_T`), and how many have one; the median is empty where none has ([time-to-onset](https://github.com/Altio-AI/open-altio/blob/main/rules/time-to-onset.md)) |
| `no_onset_padded_event_date_T`, `no_onset_event_date_not_exact_T`, `no_onset_first_dose_not_exact_T`, `no_onset_event_before_first_dose_T` | The pair's suspect drugs with no time to onset, by why (`time_to_onset_reason_T`) |

On `statistics_strata_T`, rule [ror-strata](https://github.com/Altio-AI/open-altio/blob/main/rules/ror-strata.md): `ingredient_T` and `reaction_T` as above; `by_T`, the part (`age_band` or `sex`); `stratum_T`, its value (an age band's id, `F`, `M`, or `unknown`); `cases_T`, `ingredient_cases_T`, `reaction_cases_T` and `stratum_cases_T`, the cases within that value naming both, the ingredient, the reaction, and any of them (a, a + b, a + c and N); `ror_T`, `ror_lower_T`, `ror_upper_T`, the ROR within that value and its 95% interval.

### The deduplicated views

`views.sql` defines the release's default view:

| View | What |
|---|---|
| `case_dedup_T` | `case_latest_T` where `dup_kept_T` is true: the cases you see by default |
| `drug_dedup_T` ... `indi_dedup_T` | The child rows of a case in `case_dedup_T` |

They are views, not more Parquet. The kept cases are most of the case table, and copies would nearly double the release.

## funnel.json

The count after each step, per era and in total, and what each step removed:

| Step | Table or view | Cases in 2026Q2 |
|---|---|---|
| `report_versions` | `demo` | 24,812,425 |
| `latest_versions` | `demo_latest_T` | 20,692,690 |
| `after_deleted_lists` | `case_latest_T` | 20,588,529 |
| `kept_after_duplicates` | `case_dedup_T` | 20,296,653 |
| `dates` | `case_dedup_T` | 20,296,653: no case removed; each event and therapy date read as far as it is known and can be true |
| `codes` | `case_dedup_T` | 20,296,653: no case removed; each reporter code read as its E2B(R3) type |
| `drug_names` | `case_dedup_T` | 20,296,653: no case removed; there when the release carries the drug ingredients |

`duplicates` adds what the duplicate step could and could not do: how many cases the AEOLUS rule cannot check because a field it needs is empty, how many each rule set aside, and the padded-date groups left whole.

## manifest.json

| Key | What |
|---|---|
| `format`, `format_version` | `open-altio-release`, and its version |
| `release`, `quarters` | The release's name and every quarter in it |
| `built_at`, `build_seconds` | When it was built (UTC) and how long it took |
| `peak_rss_bytes` | The build's peak memory, in bytes |
| `release_bytes` | Its size on disk, every file but the manifest |
| `code_version`, `duckdb_version` | The versions that built it |
| `inputs_hash` | One checksum over every FDA file read, so two builds can show they started from the same files |
| `inputs[]` | Per FDA file read: table, quarter, path, checksum, size, encoding, era, rows, rejected lines, renames, and any overlong lines with what was done with them |
| `tables`, `views` | Per table its path, kind (`raw`, `derived`, or `classes` for WHO's drug classes) and rows; per view its rows |
| `funnel`, `methods`, `explorer` | The files above |
| `drug_names` | The DiAna dictionary read (its address, date, size and checksum), each correction with the dictionary entries it changed, and drug records by where their ingredients came from; or why the release has none |
| `classes` | WHO's drug classes: the ATC index year, WHO's citation, the class table and the group classes read (path and checksum of each), the class tables, and the cases with a coded drug, with a class, with a shared class and with a drug it cannot tell; or why the release has none |
| `class_statistics` | What the statistics of each class counted: the cases (the ingredient statistics' own), the pairs, and for each level its name, its classes, the counted cases naming one of them, its pairs and its own EBGM fit; the reaction key, whether a record also counted under the classes it could be (`could_be`), the two tables and how long it took; or why the release has none |
| `statistics` | What the statistics counted (cases, ingredients, reactions, strata, pairs), the reaction key they counted by (`reaction_key`: `meddra_pt` with its `meddra_version`, or `fda_text`), EBGM's fit (its five hyperparameters, what each starting point reached, or why it did not fit), the table and parts of the ROR by stratum (`ror_strata`) and how long each part took; or why the release has none |
| `labels` | What the labels step read and chose, or that it was skipped; the DailyMed day the labels are as of (`as_of`), the daily files applied since the build (`daily_files`), and what each refresh changed (`refreshes`, rule label-refresh) |
| `user_rules` | How the rules it was built with differ from Altio's standard: the rules off, and each value changed, from what to what. Empty for Altio's standard (see [Change a rule](../customise/rules.md)) |

## methods.json

The data the methods page draws: each step with its counts, its rule and a link to the code that applies it; the evidence cards, computed on the release's own data; what Open Altio does not do; and the release's changelog entry. Its shape is `methods.schema.json` in `src/open_altio/faers/insights/`.

## explorer.duckdb

The explorer's own database, built last from the Parquet the build has just written. It holds:

- the case table with the columns the filters use;
- the child rows;
- term tables sorted by term, so a drug or reaction filter reads only the rows it needs.

It holds nothing the Parquet does not. Query the Parquet, not this file: its layout serves the explorer and may change between versions.

## Drug labels

Present when the release was built with a labels folder (`--labels`). FDA's current prescription labels from DailyMed, keyed by RxNorm ingredient: for each ingredient, or combination of ingredients, the originator's label for each route family, and the text of their safety sections and indications. How a label is chosen and read is in the rule files [label-source](https://github.com/Altio-AI/open-altio/blob/main/rules/label-source.md), [label-choice](https://github.com/Altio-AI/open-altio/blob/main/rules/label-choice.md) and [label-sections](https://github.com/Altio-AI/open-altio/blob/main/rules/label-sections.md), and a label DailyMed's mapping file misses in [label-own-ingredients](https://github.com/Altio-AI/open-altio/blob/main/rules/label-own-ingredients.md). Every column is Open Altio's and ends in `_T`, values copied from DailyMed and RxNorm included.

| Table | One row per | Columns |
|---|---|---|
| `label_candidates_T` | ingredient and route family | `rxcui_T` (RxNorm ingredient or combination code), `ingredient_T`, `route_family_T` (a family of rule drug-route's shared route table: by_mouth, under_tongue, injected, inhaled, nasal, rectal, vaginal, transdermal, skin, eye, ear, other; unknown for a label whose routes give none), `setid_T` (the label on DailyMed), `spl_version_T`, `title_T`, `effective_date_T`, `application_T` (NDA, BLA, ANDA or other), `routes_T`, `dosage_form_T`, `chosen_because_T`, `forms_differ_T`, `keyed_by_T` (`mapping_file`: through DailyMed's mapping file; `label_ingredients`: through the label's own active ingredients, rule [label-own-ingredients](https://github.com/Altio-AI/open-altio/blob/main/rules/label-own-ingredients.md)) |
| `label_sections_T` | line of a label's text | `setid_T`, `section_T` (boxed_warning, warnings_and_precautions, warnings, precautions, adverse_reactions, contraindications, indications), `loinc_T`, `ordinal_T` (order in the label), `is_table_row_T`, `text_T` (a table row's cells joined by `" \| "`) |

## MedDRA's part

`licensed/` holds MedDRA content and appears only when the release was built with MedDRA files, or you add your own to it. It holds MedDRA's files as you received them, and FDA's MedDRA terms read to that MedDRA version (`rules/meddra-terms.md`).

It is kept apart from `parquet/`, never listed in `manifest.json` and never in `explorer.duckdb`, so a release can be shared without it.

| Table | One row per | Holds |
|---|---|---|
| `reac_meddra_T` | distinct text of `pt`, keyed `reac_term_T` | `pt_code_T`, the text's current PT; `llt_code_T`, its term; `matched_as_T`: `pt`, `llt` (a lower level term) or `former_name` (an old name, from MedDRA's history file), empty when nothing matches; `pt_current_T`, true when the text is a PT of this version |
| `drug_rec_act_meddra_T` | distinct text of `drug_rec_act`, keyed `drug_rec_act_term_T` | The same columns. FDA writes an apostrophe here as `^`; it is read as one |
| `indi_meddra_T` | distinct text of `indi_pt`, keyed `indi_term_T` | The same columns |
| `meddra_term_T` | name of the version | Every PT, lower level term and old name, normalised, with its code and PT |

The key is FDA's text in lower case with runs of spaces made one, as the explorer compares reactions. `licensed/manifest.json` says, per column, how many texts only the history file places and how many match nothing, and which quarters fit no single MedDRA version.

When the release has FDA labels, the labels step (`python -m open_altio.faers labels`) also writes each label coded into MedDRA terms there, beside the MedDRA version it used: `label_terms_T` (each term a label names, in which section and sentence, and whether the rules keep it on the label) and `label_uncertain.jsonl` (what the rules could not settle, for a person to decide). The rules are `label-dictionary`, `label-negation`, `label-population` and `label-table-rows`.

## label_flags_T

`label_other_drug_T`, beside it, lists each suspect drug record whose RxNorm code names another drug than the ingredient it is counted under: its key, the code (`rxcui_T`, `rxnorm_name_T`, `matched_by_T`) and the counted ingredient (`substance_T`). Such a record is flagged as one with no RxNorm code, and the screens show it as Not compared, no label found (rule [label-flags](https://github.com/Altio-AI/open-altio/blob/main/rules/label-flags.md)).

One row per drug (`rxcui_T`, empty for a drug record with no RxNorm code), the record's route families (`route_families_T`: the families its form could be, joined with ";", from by_mouth, under_tongue, injected, inhaled, nasal, rectal, vaginal, transdermal, skin, eye, ear and other; empty when nothing is known) and reaction (`pt_T`, as FDA published it): `outcome_T` says whether the reaction is on the label (`on_label`, `related`, `not_on_label`), differs between the labels of the drug's forms (`forms_differ`, with each family's outcome in `family_outcomes_T`), is the disease the drug treats (`treated_disease`), is not a medical event (`not_a_medical_event`), is a procedure (`procedure`), has no label to compare (`no_label`), or could not be settled (`uncertain`); `expectedness_T` reads it as `expected` (`on_label`), `unexpected` (`related`, `not_on_label`, `forms_differ`, `uncertain`, `no_label` and `procedure`: what the explorer's Unexpected only keeps) or `set_aside` (`treated_disease`, `not_a_medical_event`). `judged_on_T` names the family label or labels that decided, which differs from the record's families when one of them has no label of its own ("on the injection label; no label for tablets"). `setid_T` and `label_date_T` say which label was read, `section_T` where it names the reaction, and `decided_by_T` how the outcome was reached (`rule`, `rule: umbrella`, `model_reviewed`, `model_suggested`). It holds no MedDRA code or group, so it is public. A suspect drug record (PS or SS) finds its row by its RxNorm code in `drug_rxnorm_T`, its route families in `drug_route_T` and the reaction; a trial product has none. Each record also has a row for each ingredient it is counted under, by that ingredient's own code in `ingredient_rxnorm_T` (one row per ingredient: `ingredient_T`, `rxcui_T`, `rxnorm_name_T`, `tty_T`, `no_code_reason_T`), so a combination's reactions are judged against each ingredient's own label too; a page counting any product containing the ingredient reads those. The manifest's `label_flags` entry counts the suspect records and their cases by how far each got: a trial product, no RxNorm code, no label, a label. The outcomes are defined in rule `label-flags`.

## WHO drug classes

When a release includes WHO's drug classes (ATC), its manifest lists the class tables and the ATC index year under `classes`. Where the classes come from is on [the methods page](../methods/index.md#drug-classes).

- **Three tables of their own,** read from the ingredients in `drug_substance_T`.
- **No other table changes** with them, and a release built without the drug ingredients has none.
- **One class per drug record** is chosen by the rule `atc-class-choice`.
- **Count classes in cases, not rows.**

| Table | One row per | Holds |
|---|---|---|
| `atc_index_T` | ATC code in the class table, at every level | `atc_code_T`, `atc_level_T` (1 to 5), `atc_name_T` (WHO's name, as WHO writes it), `atc_index_year_T` |
| `atc_drug_T` | Drug record with at least one ATC code, from its ingredients, FDA's own words on it or its group word, keyed as `drug_substance_T` | Its one class and how it was chosen (below) |
| `atc_drug_codes_T` | Possible code of each record in `atc_drug_T` | `atc_ingredient_T` (the ingredient, or the combination, the code is for), `atc_code_T`, `atc_level_T`, `atc_index_year_T`, `atc_chosen_T` |

| Column | On | What |
|---|---|---|
| `atc_code_T` | `atc_drug_T` | The record's class: a code of level 5; for `shared_class` the class of level 4, 3 or 2 its codes share (the codes its stated route fits, when two or more do; else all its possible codes); for `group_class` its group word's class, of level 4, 3 or 2; WHO's class for a combination WHO codes only by its class. Empty when it cannot tell |
| `atc_level_T` | both | The code's level, 1 to 5 |
| `atc_chosen_by_T` | `atc_drug_T` | `only_code` (it has one possible code), `dose`, `route`, `indication`, `shared_class`, `group_class` (the record names only a group of drugs, rule `atc-group-classes`) or `cannot_tell` |
| `atc_possible_codes_T` | `atc_drug_T` | How many possible codes it has; each is a row of `atc_drug_codes_T` |
| `atc_matched_on_T` | `atc_drug_T` | Where its codes came from (rule `atc-index`). From its ingredients: `substance` (one ingredient), `ingredient_set` (WHO's code for the whole combination) or `each_ingredient` (a combination WHO has no code for, split into its ingredients; always `cannot_tell`). When they have no code, from FDA's own words: `drug_name`, `active_ingredient`, `active_ingredient_set` or `each_active_ingredient` (FDA's active ingredients split, always `cannot_tell`) |
| `atc_chosen_T` | `atc_drug_codes_T` | True for the code that is the record's class; false for every code of a record with a shared class or one it cannot tell |

### Statistics of each class

Rule [statistics-classes](https://github.com/Altio-AI/open-altio/blob/main/rules/statistics-classes.md): the statistics of each ingredient worked out again with each drug's WHO class in place of its ingredient, on the same cases, at each level the rule names (the therapeutic, pharmacological and chemical subgroups), each level with its own EBGM prior. Both tables are part of the drug classes layer, listed under `classes` in the manifest: a release without the classes has neither. `python -m open_altio.faers class-statistics --release R` adds them to a release already built.

| Table | One row per | Holds |
|---|---|---|
| `atc_statistics_T` | Level, class and reaction named together in at least one counted case | `level_T` (the ATC level), `class_T` (the class's ATC code at that level; its name is in `atc_index_T`), `reaction_T`, `cases_T`, `class_cases_T` (cases naming the class), and every other column of `statistics_T` from `reaction_cases_T` to `ic025_T`, worked out the same way. No time to onset |
| `atc_statistics_ingredients_T` | Ingredient, level and class | `ingredient_T`, `level_T`, `class_T`, `cases_T`: the counted cases in which a record of the ingredient counted under the class |
