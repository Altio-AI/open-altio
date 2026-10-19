# Pipeline

For anyone changing how a release is built. Builds a release of Open Altio from FDA's quarterly files: every FDA value loaded verbatim as text, everything we derive in tables and columns ending in `_T`, written as Parquet with the funnel numbers and a manifest.

A person builds one with `open-altio build`, from the FDA files `open-altio fetch` downloaded (`faers/build.py` holds that build to the memory rule). The pipeline's own command takes any folders, for hosts and scripts:

```sh
python -m open_altio.faers build --input zips --out releases                   # -> releases/2026Q2/
python -m open_altio.faers build --input raw --out releases --quarter 2019Q1  # an earlier release
```

```python
from open_altio.faers import build_release

# -> the release folder
path = build_release(input_dir, out_dir, quarter=None, overwrite=False, user_rules=None)
```

`build_release` raises `SourceError` when the input is not what FDA publishes (a missing file, a quarter given twice, a column FDA never published) and `ReleaseError` when the release would break a rule, already exists, or a person's own rules would not build (see [Your own rules](#your-own-rules)). The command line prints `refused: ...` and exits 2 in both cases.

## Modules

| Module | Job |
|---|---|
| `sources.py` | Find FDA's quarters in an input folder, as zips or extracted folders |
| `load.py` | Load FDA's text files into the build database, every value verbatim |
| `schema.py` | FDA's columns per table, the one renaming across eras, and the check of the `_T` suffix |
| `derive.py` | The `_T` tables: typed columns, the latest version of each case, the deleted cases, the child rows, the views |
| `dates.py` | Dates read as far as they are known and can be true, time to onset and therapy duration |
| `duplicates.py` | The duplicate step, and the reason lines a case shows |
| `drugnames/` | The drug-name step: each drug record's ingredients from the DiAna dictionary |
| `atc/` | The drug classes layer: WHO's ATC class for each drug record, after the drug-name step, and the builder of our class table |
| `funnel.py` | The funnel numbers, `funnel.json` |
| `release.py` | The build: staging folder, checks before writing, Parquet, manifest |
| `explorer_db.py` | The explorer's database, `explorer.duckdb` |
| `reader.py` | Open a release folder in DuckDB, and quote values for SQL |
| `build.py` | The build `open-altio build`, `demo` and the explorer's rebuild share |
| `fda.py` | Which quarters FDA has published, and downloading them |
| `formats.py` | The format each JSON document of a release names itself by |
| `meddra/` | The licensed MedDRA part of a release |
| `insights/` | The methods page's data, `methods.json` (its own README) |
| `__main__.py` | `python -m open_altio.faers` |

## Input

A folder holding FDA's quarterly zips as downloaded (`aers_ascii_2004q1.zip` ... `faers_ascii_2026q2.zip`), extracted quarter folders (`2004q1/`, `faers_ascii_2026q2/`, ...), or a mix for different quarters. The quarter is read from the zip or folder name. Inside a quarter, files are found by name at any depth and case-blind, because FDA's layout moved over the years:

| What | Names seen |
|---|---|
| Case tables | `ascii/DEMO04Q1.TXT`, `ascii/demo12q4.txt`, `ascii/DEMO18Q1_new.txt`, `ASCII/DEMO26Q2.txt` (and the same for DRUG, REAC, OUTC, RPSR, THER, INDI) |
| Deleted-case lists | `deleted/ADR19Q1DeletedCases.txt`, `Deleted/21Q1DeletedCases.txt`, `Deleted/DELETE26Q2.txt` |
| FDA's one-off whole-history list | `deleted/AllDeletedCases.txt` (shipped in 2019Q1) |

STAT, SIZE, PDF and Word files are ignored. Zips are read member by member into a scratch folder that is removed as the build goes.

### How files are read

`$`-delimited, no quoting or escaping, every column as text, short rows padded with empty values, UTF-8 or (where a file is not valid UTF-8) Latin-1. An empty field is NULL; every other value is kept exactly as FDA wrote it, spaces included. Legacy AERS data rows end in a stray `$` the header lacks; that empty trailing field is dropped. A UTF-8 byte order mark (2012Q4 DRUG) and spaces around header names (2012Q4 DEMO's ` rept_dt`) are ignored. A header naming a column the release schema does not have stops the build with the file and column named, so a new FDA column is never dropped silently.

The header line sets the columns; they are never guessed from the rows. A line with more fields than its header is never cut short in silence (`rules/overlong-lines.md`). When it holds whole records one after the other, it is split back into them: FDA's 2011Q2, 2011Q3 and 2011Q4 DRUG files each have one line where a drug record runs on into the next with no line break, and read as one record the second drug would be lost. Any other long line keeps its first fields, as FDA's columns line up, and the text past the last column goes into the manifest: 2012Q1 DEMO has one line with a `$` inside `mfr_num`, so that case's later values sit one column to the right. Each such line is listed under `inputs[].overlong_lines` (`line`, `fields`, `records`, and `dropped` for a line not split), and `overflow_values` counts the non-empty values dropped.

### Column names: the one unification across eras

Raw columns keep FDA's names, lower-cased, with these renames and no others (`src/open_altio/faers/schema.py:COLUMN_UNIFICATION`):

| Table | FDA's name | Release name | Why |
|---|---|---|---|
| all | `isr` | `primaryid` | Legacy AERS keys report versions by ISR |
| all | `case` | `caseid` | Legacy AERS calls the case CASE |
| demo | `i_f_cod` | `i_f_code` | Legacy spelling |
| demo | `gndr_cod` | `sex` | Legacy and 2012Q4 to 2014Q2 spelling |
| drug | `lot_nbr` | `lot_num` | 2012Q4 spelling |
| outc | `outc_code` | `outc_cod` | 2012Q4 spelling |
| ther | `drug_seq` | `dsg_drug_seq` | Legacy THER calls it DRUG_SEQ |
| indi | `drug_seq` | `indi_drug_seq` | Legacy INDI calls it DRUG_SEQ |

Each raw table holds the union of both eras' columns (`src/open_altio/faers/schema.py:RAW_COLUMNS`); a column one era or quarter does not publish is NULL there. Legacy child tables carry no `caseid`. Which renames each file needed is in the manifest (`inputs[].renamed`).

## The release folder

```
releases/2026Q2/                  named by the latest FDA quarter in the input
  manifest.json                   what was built, from what, when
  funnel.json                     the numbers per cleaning step
  views.sql                       the deduplicated views, over the tables by name
  methods.json                    the methods page's data (src/open_altio/faers/insights/README.md)
  explorer.duckdb                 the explorer's database, built from the Parquet (below)
  parquet/
    demo.parquet ... indi.parquet raw tables: FDA's columns verbatim + quarter_T, era_T
    deleted.parquet               raw: every deleted-case list line, caseid + quarter_T
    quarters_T.parquet            derived tables (below)
    demo_T.parquet
    demo_latest_T.parquet
    deleted_cases_T.parquet
    case_latest_T.parquet
    drug_latest_T.parquet ... indi_latest_T.parquet
    case_dup_T.parquet
    atc_index_T.parquet ...       the drug classes layer, when the release carries it (below)
    statistics_T.parquet          EBGM, PRR, ROR, RRR, IC and time to onset per suspect ingredient and reaction
    statistics_strata_T.parquet   each pair's ROR within each age band and each sex (below)
    atc_statistics_T.parquet      the same statistics per WHO class and reaction, with the classes (below)
    atc_statistics_ingredients_T.parquet   each ingredient's classes, for the class statistics
    drug_rxnorm_T.parquet         each drug record's RxNorm code, when built with --rxnorm (below)
    ingredient_rxnorm_T.parquet   each ingredient's own RxNorm code, built with it
    label_candidates_T.parquet    FDA drug labels, only when the build is given a labels folder (below)
    label_sections_T.parquet
  licensed/                       licensed MedDRA part, added by `python -m open_altio.faers meddra` or the service (below)
```

The build writes into a hidden `.<release>.building/` folder beside it and renames it into place only when everything is written, so a failed build never leaves a partial release. An existing release is replaced only with `overwrite=True` (`--overwrite`).

### Provenance columns

| Column | Values |
|---|---|
| `quarter_T` | The FDA quarter whose file held the row, `2004q1` ... `2026q2`. On `deleted`, FDA's whole-history list is `pre2019q1`. |
| `era_T` | `legacy` (AERS layout, 2004Q1 to 2012Q3) or `faers` (2012Q4 onward), read from the file's header (ISR means legacy). Not on `deleted`. |

### Derived tables (`_T`)

The steps, in order (`src/open_altio/faers/derive.py`):

| Table | What it is |
|---|---|
| `quarters_T` | One row per quarter: `quarter_T`, `era_T`, `qnum_T` (yyyyq, sortable) |
| `demo_T` | Every report version (nothing removed), all raw `demo` columns plus the typed columns below |
| `demo_latest_T` | One row per case, across AERS and FAERS (`rules/latest-version.md`): highest `caseversion_T`, then latest `fda_dt`, then latest quarter (a primaryid can be re-published), then highest `primaryid`. `fda_dt` and `primaryid` compare as FDA's text. Legacy has no caseversion, so a case FDA carried from AERS into FAERS (same case number, versions counting on) keeps its FAERS version, and an AERS-only case is ordered from `fda_dt` on. A legacy row with no CASE is its own case. |
| `deleted_cases_T` | Each caseid on any deleted-case list, once: `first_listed_quarter_T`, `n_listings_T`, `in_all_history_list_T` |
| `case_latest_T` | The analysis grain: `demo_latest_T` less the cases on a deleted-case list, in both eras (`rules/deleted-cases.md`): AERS and FAERS share one case numbering, so a listed number in the AERS range is an AERS case (`notebooks/faers/02_case_versions`, section 5). A legacy report with no CASE number is never matched to a list. |
| `<child>_latest_T` | Rows of drug, reac, outc, rpsr, ther and indi belonging to a case in `case_latest_T`, joined on (`era_T`, `primaryid`, `quarter_T`), so a re-published primaryid's rows from another quarter do not come along. `drug_latest_T` adds `drugname_norm_T` and `prod_ai_norm_T`; `reac_latest_T` adds `pt_norm_T` and `pt_spelling_T`; `indi_latest_T` adds `indi_pt_spelling_T`; `ther_latest_T` adds `start_dt_T`, `end_dt_T`, their `_prec_T` (`rules/date-limits.md`) and `dur_days_T` (`rules/therapy-duration.md`), read against the case by `dates.py`. |
| `case_dup_T` | One row per case in `case_latest_T`: the cross-case duplicate flags (below). `case_latest_T` then gains the flag columns. |
| `drug_onset_T` | One row per drug record of `drug_latest_T` (`era_T`, `primaryid`, `quarter_T`, `drug_seq`): `time_to_onset_T`, and `time_to_onset_reason_T` where it has none, by `dates.py` (`rules/time-to-onset.md`). |
| `drug_substance_T`, `drug_ingredient_T` | The ingredients of each drug record, built after the derive steps by `src/open_altio/faers/drugnames/` when the build is given the DiAna dictionary (below). |
| `statistics_T`, `statistics_strata_T` | One row per suspect ingredient and reaction named together: EBGM, EB05, EB95, PRR, ROR, RRR, IC and the time to onset; and one per pair and value of an age band or a sex where the pair has a case, with its ROR there. Built after the Parquet is written by `src/open_altio/faers/statistics/` (below). |
| `atc_statistics_T`, `atc_statistics_ingredients_T` | The statistics of each WHO class and reaction at each class level, and each ingredient's classes, written by `statistics/` after the ingredient statistics when the release carries the classes layer, as part of that layer (below). |

Typed columns on `demo_T` (and carried into `demo_latest_T` and `case_latest_T`):

| Column | Rule |
|---|---|
| `<date>_T` for `fda_dt`, `init_fda_dt`, `rept_dt`, `mfr_dt`, `event_dt`, `death_dt` | A DATE only where FDA gave a full, valid yyyymmdd; a year or year-month alone, or an impossible day, is NULL |
| `<date>_prec_T` | Digits FDA gave: 8, 6 or 4; NULL when empty or another length |
| `event_dt_T`, `event_dt_prec_T` | As above, read further by `dates.py`: a full date padded to the 1st is known to the month (6) or, on 1 January, the year (4) (`rules/event-date-precision.md`), and a date outside the limits has neither (`rules/date-limits.md`) |
| `first_fda_dt_T`, `init_year_T`, `fda_year_T` | `init_fda_dt`, falling back to `fda_dt` (legacy has no init_fda_dt), and the years |
| `caseversion_T` | `caseversion` as an integer; NULL in legacy |
| `sex_T` | `sex` trimmed and in capitals when it is F or M; NULL for every other code (`rules/sex-codes.md`) |
| `age_years_T` | `age` in years by `age_cod`, exact: DEC x10, YR, MON /12, WK x7/365.25, DY /365.25, HR /8766, MIN, SEC; no unit is YR; NULL for another unit, a value that is not a number, a negative one or over 122 years (`rules/age-in-years.md`). A number may have a leading or trailing point (`.8`, `60.`) and spaces around it |
| `age_band_T` | The case's age band id, from `age_years_T`; an age of exactly 0 YR or DEC (or 0 with no unit) by `age_grp` (N, I, else the band for under 1 with no exact age); NULL with no age (`rules/age-bands.md`) |
| `wt_kg_T` | `wt` in kg by `wt_cod`: KG or KGS, LBS x0.45359237, GMS /1000; NULL with no unit or another unit, at zero or over 635 kg (`rules/weight-in-kg.md`) |
| `case_key_T` | `caseid`, or `ISR:<primaryid>` where a legacy row has no CASE |
| `country_T` | `occr_country`, else `reporter_country`; a legacy name (`UNITED STATES`) read as its ISO 3166-1 code (`US`) through `mappings/faers/countries/accepted.csv` (`rules/legacy-country.md`). A legacy name the mapping lacks stops the build. `COUNTRY NOT SPECIFIED` and `A1` count as empty (`rules/country-not-given.md`). An `EU` case takes the occurrence country of its latest earlier FAERS version that gives an ISO code (`rules/eu-member-state.md`) |
| `country_source_T` | Where `country_T` came from: `as published`, or `earlier version` for an `EU` case's member state; NULL with no country |
| `company_T` | A `mfr_sndr`, in either era, read as its company's name through `mappings/faers/senders/accepted.csv` (`rules/company-names.md`), else `mfr_sndr` trimmed; NULL on a direct report (`rept_cod` DIR, whose sender FAERS writes as `FDA-CTU` or blank), where the sender is FDA's own intake `FDA-CTU` on any report, and where the sender reads Not given (`rules/not-given.md`: blank, only unknown, or naming no company, such as a regulator or an ID number). The duplicate rules compare `mfr_sndr`, never `company_T`. `python -m open_altio.faers companies --release <folder>` puts a changed mapping in a release already built, here and in the explorer database |
| `reporter_type_T` | `occp_cod` as the ICH E2B(R3) reporter qualification, 1 to 5, through `mappings/faers/reporter_types/accepted.csv` (`rules/reporter-type.md`); empty for a code the mapping does not hold |
| `qnum_T` | The quarter as yyyyq |
| `drugname_norm_T`, `prod_ai_norm_T` | Upper case, whitespace collapsed and trimmed, trailing periods removed, empty as NULL |
| `pt_norm_T` (on `reac_latest_T`) | `pt` in upper case, so a legacy term (`DRUG INEFFECTIVE`) equals FAERS's MedDRA spelling (`Drug ineffective`) (`rules/reaction-term-case.md`) |
| `pt_spelling_T`, `indi_pt_spelling_T` (on `reac_latest_T`, `indi_latest_T`) | On a legacy row, the spelling FAERS uses for the same term, compared without capitals (`DRUG INEFFECTIVE` is shown `Drug ineffective`); FDA's text elsewhere (`rules/legacy-term-spelling.md`, `open_altio.faers.spelling`) |

### Probable duplicates across cases

Two rules (`rules/dedup-default.md`), each making its own groups; groups that share a case are then one group. The first is AEOLUS (Banda et al. 2016): two cases in `case_latest_T` are probable duplicates when all of these agree, compared as FDA's text except where said:

- `event_dt` (as written, so a partial date matches only the same partial date)
- `age` and `age_cod`
- `sex`
- country: `country_T` (`occr_country`, else `reporter_country`, a legacy name read as its ISO code, FDA's words for no country as none), as the case's own version gives it: an `EU` case whose member state came from an earlier version is compared as `EU`, so taking it never splits a group
- the set of `drugname_norm_T` over the case's `drug_latest_T` rows (distinct, so order and repeats do not matter)
- the set of `pt_norm_T` over the case's `reac_latest_T` rows: `pt` in upper case, because legacy AERS writes reaction terms in capitals and FAERS in MedDRA's mixed case (`rules/reaction-term-case.md`)

A case with a null in any of these (no drug or reaction rows counts as null) is never compared by this rule. Matching runs across eras. Legacy AERS publishes no occurrence country, so a legacy case matches on its reporter country, read as its ISO code so it can match a FAERS case, and legacy quarters in the 2004Q1 layout, which publish no country at all, are never compared. In a group of `min_group_size` or more (`rules/dup-padded-event-dates.md`) whose shared event date is 1 January, or a month or year only, and whose cases all come from one sender (`mfr_sndr` trimmed and in capitals; a blank sender counts as another), the date does not count as a match, so the rule sets nothing aside in that group.

The second is the same manufacturer case number from the same sender (`rules/dup-manufacturer-number.md`): `mfr_num` and `mfr_sndr`, trimmed and in capitals. A number without its leading two-letter country code (`US-`) matches the coded number when the sender wrote it with exactly one code; two different codes never match. A number group is skipped when its cases include both M and F, or their `age_years_T` differ by more than `max_age_gap_years`.

Linking: every case starts with its own label, and each step gives every case the lowest label in either of its two groups, until no label changes (`duplicates.link_groups`). Cases with one label are one group: if A matches B by one rule and B matches C by the other, A, B and C are one group. Each group shows one copy (`rules/dup-shown-copy.md`), by Altio's standard the latest received (`first_fda_dt_T`, which is `init_fda_dt` falling back to `fda_dt`), then the highest `caseid` compared as text, then FAERS before legacy, then the highest `case_key_T`. The same order holds for both rules. The group is dated by its earliest receipt, `group_first_dt_T`, which the explorer's received-date filters and sorting and the filtered export use.

| Column | On | What |
|---|---|---|
| `dup_key_T` | `case_dup_T` | The AEOLUS fields joined with `\|`, NULL when any is null |
| `dup_number_key_T` | `case_dup_T` | The sender and number as the second rule compares them (`SENDER\|NUMBER`, a number without its code written with the one code the sender uses); NULL when either is empty |
| `dup_padded_date_T` | `case_dup_T` | True for the cases of an AEOLUS group from one sender left whole because its shared event date is padded |
| `dup_group_T` | `case_dup_T`, `case_latest_T` | A number shared by every case of one linked group; NULL for a case in no group |
| `probable_duplicate_T` | `case_dup_T`, `case_latest_T` | True for every member of a group, the shown one included |
| `dup_kept_T` | `case_dup_T`, `case_latest_T` | False only for the copies a group sets aside; the shown copy and every case in no group are kept |
| `group_first_dt_T` | `case_dup_T`, `case_latest_T` | The earliest `first_fda_dt_T` of the case's group; the case's own `first_fda_dt_T` when it is in no group |
| `dup_rule_T` | `case_dup_T`, `case_latest_T` | The rules that put the case in its group, a list of `aeolus`, `manufacturer_number`, `manufacturer_number_country_code` (the number matched through a missing country code); NULL for a case in no group |
| `dup_shown_case_T` | `case_dup_T`, `case_latest_T` | The `case_key_T` of the group's shown copy, on every member; NULL for a case in no group |
| `dup_other_cases_T` | `case_dup_T`, `case_latest_T` | On the shown copy only: the `case_key_T` of the copies set aside, earliest received first |
| `no_drug_or_reaction_T` | `case_dup_T`, `case_latest_T` | No usable drug or no usable reaction (`rules/no-drug-or-reaction.md`): never hidden for it |
| `serious_no_drug_or_reaction_T` | `case_dup_T`, `case_latest_T` | `no_drug_or_reaction_T` and one of the rule's `serious_outcome_codes` in OUTC |

`open_altio.faers.duplicates.reason_lines(case)` writes the reason lines from these columns and the rule's sentences: on a set-aside copy, "Set aside: probable duplicate of case N, received later and shown instead." and one line per rule; on the shown copy, "Also reported as cases X and Y, first received <month year>."

Nothing is deleted: every case stays in `case_latest_T` and its child tables. `case_dup_T` holds every duplicate column for every case; the flags are also copied onto `case_latest_T`, so the explorer filters one table with no join.

### The deduplicated views (`views.sql`)

The default view of the release:

| View | What |
|---|---|
| `case_dedup_T` | `case_latest_T WHERE dup_kept_T` |
| `<child>_dedup_T` | `<child>_latest_T` rows of a case in `case_dedup_T`, on (`era_T`, `primaryid`, `quarter_T`) |

They are views, not more Parquet: the kept set is most of the grain, and copying the child tables would nearly double the release. `views.sql` names tables, never paths. To open a release in DuckDB, create a view per entry of `manifest.json` `tables` (`CREATE VIEW case_latest_T AS SELECT * FROM read_parquet('<release>/parquet/case_latest_T.parquet')`), then run `views.sql`. For the explorer: the dedup switch is `WHERE dup_kept_T` on `case_latest_T` (on: kept cases only; off: drop the predicate); filters on drugs or reactions join the child `_latest_T` tables to the filtered cases on (`era_T`, `primaryid`, `quarter_T`). The manifest lists the views and their row counts under `views`.

The build refuses to write a release in which a derived table or view, or a column that is not FDA's, lacks the `_T` suffix (`rules/transformed-suffix-T.md`).

### Checks a caller adds

`build_release(..., checks=(...))` runs a caller's own checks before the build's: each reads the build's database before a byte of the release is written and raises `ReleaseError` to refuse it, and the staging folder is removed, so a refused build leaves nothing in the output folder. A host that publishes releases adds its own policy this way; `python -m open_altio.faers build` passes a caller's own through `main(checks=...)`.

### Your own rules

`build_release(..., user_rules=...)` builds under a person's own choices: data rules switched off and values changed (`rules/README.md`). The command line, and `open-altio build`, read them from the `rules.toml` in the folder they run in, through `open_altio.rulebook.load_user_rules`. The build refuses choices `rulebook.check_user_rules` finds a problem with before anything is written, runs every step under them (`rulebook.use_user_rules`: `value` gives the person's value, `is_on` says whether a rule acts), and records how they differ from Altio's standard under `user_rules` in `manifest.json` and `methods.json`. Values the person leaves alone follow the standard. A build without a `rules.toml` follows Altio's standard throughout.

### Opening a release

```python
from open_altio.faers import open_explorer, open_release

con = open_release("releases/2026Q2")  # a view per manifest table over its Parquet, then views.sql
ex = open_explorer("releases/2026Q2")  # explorer.duckdb, read only
```

`register_release(con, release_dir, temporary=False, with_views=True)` does the same on a connection you already hold.

### explorer.duckdb

The explorer queries this one file (`src/open_altio/faers/explorer_db.py`). The build writes it last, from the Parquet it has just written; `python -m open_altio.faers explorer releases/2026Q2` rebuilds it for an existing release and records it in the manifest. It is laid out for case-level filters over all 20 million cases on one small box: the case table holds the filters' columns, and drug and reaction filters read term tables sorted by term, so DuckDB's per-row-group min/max (zone maps) skip everything but the matching term before joining to cases by an integer id. No ART indexes: sorting does the work without holding an index in memory.

The build holds DuckDB to the memory and threads in `rules/explorer-build-memory.md` and spills to disk past them, so it fits on the service's box. `scripts/compare_explorer_db.py OLD NEW` checks that two builds hold the same tables, rows and values, in the same storage order.

| Table | Rows | Columns |
|---|---|---|
| `explorer_release_T` | one | `release_T`, `built_at_T` |
| `explorer_case_T` | one per case in `case_latest_T` (duplicates included, flagged), stored in `case_id_T` order | `case_id_T` (1.. in `era_T`, `case_key_T` order), `era_T`, `case_key_T`, `caseid`, `primaryid`, `quarter_T`, `caseversion`, `i_f_code`, `rept_cod`, `first_fda_dt_T` (received), `init_fda_dt`, `fda_dt`, `event_dt`, `event_dt_T`, `event_dt_prec_T`, `age`, `age_cod`, `age_years_T`, `sex`, `wt`, `wt_cod`, `wt_kg_T`, `occr_country`, `reporter_country`, `country_T` (the release's: occurrence, else reporter, a legacy name as its code), `occp_cod`, `reporter_type_T`, `mfr_sndr`, `company_T` (the release's: the sender's company, `rules/company-names.md`), `dup_kept_T`, `probable_duplicate_T`, `dup_group_T`, `group_first_dt_T` (the received date filters and sorting use), `dup_rule_T`, `dup_shown_case_T`, `dup_other_cases_T`, `no_drug_or_reaction_T`, `serious_no_drug_or_reaction_T`, `outcomes_T` (the case's distinct `outc_cod`, sorted) |
| `explorer_drug_T`, `explorer_reac_T`, `explorer_outc_T`, `explorer_ther_T`, `explorer_indi_T` | the child `_latest_T` rows, sorted by `case_id_T` then sequence | `case_id_T` and FDA's columns verbatim (case keys dropped); drug adds `drugname_norm_T`, `prod_ai_norm_T`, `role_T` (upper case, trimmed `role_cod`) and `substance_T` (the ingredients `drug_substance_T` read it to; empty without the drug-name step) |
| `explorer_sender_T` | distinct (spelling, company): each sender spelling and each company name with the `company_T` it names, sorted by spelling | `spelling_T` (`mfr_sndr` or `company_T` in upper case, trimmed), `company_T` |
| `explorer_drug_term_T` | distinct (term, role, case), sorted by term | `term_T` (`drugname_norm_T` or `prod_ai_norm_T`), `role_T`, `case_id_T` |
| `explorer_reac_term_T` | distinct (term, case), sorted by term | `term_T` (`pt` lower case, whitespace collapsed), `case_id_T` |
| `explorer_ingredient_T` | distinct (ingredient, combination, spelling, role, case), sorted by ingredient | `ingredient_T`, `substance_T`, `spelling_T` (`drugname_norm_T`), `role_T`, `case_id_T` |
| `explorer_no_ingredient_T` | distinct (spelling, role, case) of the drugs with no ingredient, sorted by spelling | `spelling_T`, `role_T`, `case_id_T` |
| `explorer_drug_name_T` | each of FDA's names with each set of ingredients its drugs were read to, sorted by name | `name_T`, `field_T` (`drugname` or `prod_ai`), `substance_T` (empty: none), `rows_T` |

`open_altio.faers.explorer_db.drug_term`, `reaction_term` and `sender_key` normalise what a user types the same way. The manifest's `explorer` entry records the file, its bytes and each table's rows.

### funnel.json

```json
{
  "release": "2026Q2",
  "eras": {"legacy": "AERS, 2004Q1 to 2012Q3", "faers": "FAERS, 2012Q4 onward"},
  "steps": [
    {"id": "report_versions",     "table": "demo",          "label": "...", "count": {"legacy": n, "faers": n, "total": n}},
    {"id": "latest_versions",     "table": "demo_latest_T", "label": "...", "count": {...}, "removed": {...}},
    {"id": "after_deleted_lists", "table": "case_latest_T", "label": "...", "count": {...}, "removed": {...}},
    {"id": "kept_after_duplicates", "table": "case_dedup_T", "label": "...", "count": {...}, "removed": {...}}
  ],
  "deleted_lists": {"caseids_listed": n, "listings": n},
  "duplicates": {"cases": n, "not_compared_by_aeolus": n, "set_aside": n,
                 "set_aside_by_rule": {"aeolus": n, "manufacturer_number": n},
                 "padded_date_groups": {"groups": n, "cases": n}}
}
```

`steps` is ordered; each count is the row count of the step's table (or view) per `era_T`, and `removed` is the drop from the step before. `kept_after_duplicates` counts `case_dedup_T`: the cases the duplicate flag keeps, which is the release's default view; the steps after it (`dates`, `codes`, and `drug_names` and `meddra_terms` when the release has them) count the same cases and remove none. A new step is one entry appended to `src/open_altio/faers/funnel.py:FUNNEL_STEPS`.

`duplicates` says what the duplicate step could and could not do: `not_compared_by_aeolus` counts the cases the AEOLUS rule cannot check because a field it needs reads Not given (rules/not-given.md), which the methods page states; `set_aside_by_rule` counts the cases set aside that each rule grouped (a case both rules grouped counts under both); `padded_date_groups` counts the AEOLUS groups left whole because of a padded event date, and their cases.

### manifest.json

| Key | What |
|---|---|
| `format`, `format_version` | `open-altio-release`, 1 (a release built under the project's earlier format names reads the same: `src/open_altio/faers/formats.py`) |
| `release`, `quarters` | The release name and every quarter in it |
| `built_at`, `build_seconds` | UTC build time (ISO 8601) and wall time |
| `release_bytes` | Size of the release on disk: every file in it but `manifest.json` |
| `peak_rss_bytes` | Peak memory of the build process (DuckDB runs in it): its peak resident memory, or on macOS its peak physical footprint, since macOS keeps counting memory already given back as resident (`src/open_altio/machine.py`) |
| `code_version`, `duckdb_version` | Package and engine versions |
| `inputs_hash` | sha256 over the sorted (table, quarter_T, file sha256) triples: the data cut; the same quarters from zips or folders give the same hash |
| `inputs[]` | Per FDA file read: table, quarter, source path, sha256, bytes, encoding, era, rows, rejected lines, overflow values, renames, overlong lines (see [How files are read](#how-files-are-read)) |
| `tables` | Per table: `path`, `kind` (`raw` or `derived`), `rows`, `bytes` |
| `views` | `file` (`views.sql`) and, per view, its `rows` |
| `funnel` | `funnel.json` |
| `methods` | `methods.json` |
| `classes` | The drug classes layer: `present`, and either its `index_year`, WHO's `citation`, the class `table` it read (path and sha256), the table `prefix`, its `tables` and the `cases` they cover, or the `reason` it is absent (below) |
| `rxnorm` | The RxNorm release `drug_rxnorm_T` was built from: `release` (NLM's file date), `source`, `download`, per file its `sha256` and `bytes`, the table's counts, `ingredients` (`ingredient_rxnorm_T`'s ingredients and how many have a code), and `suspect_records`: the suspect drug records (rule label-flags' roles) and how many have a code, over every case, probable duplicates included; or `present: false` and the `reason` (below) |
| `explorer` | `file` (`explorer.duckdb`), `bytes`, and per table its `rows` |
| `user_rules` | How the rules the release was built with differ from Altio's standard: `off` (data rules switched off) and `changed` (`rule`, `key`, `standard`, `value`); both empty for a release built without a `rules.toml`. `methods.json` carries the same |
| `statistics` | The statistics step: what it counted and by which reaction key, EBGM's fit (the prior, every start) and its seconds, or the `reason` there are none (see [The statistics](#the-statistics-statistics_t)) |
| `class_statistics` | The class statistics: what they counted, each level's classes, pairs and EBGM fit, the reaction key and its seconds, or the `reason` there are none (see [The statistics](#the-statistics-statistics_t-statistics_strata_t)) |
| `drug_names` | The drug-name step: `present`, the dictionary read, its corrections, records by source and the unmapped share, or the `reason` it is absent (see [The drug ingredients](#the-drug-ingredients-drug_substance_t-drug_ingredient_t)) |
| `labels` | What the labels step read and chose (`src/open_altio/faers/labels/README.md`), or `{"skipped": "no labels folder given"}` |

### The drug ingredients (`drug_substance_T`, `drug_ingredient_T`)

```sh
python -m open_altio.faers build --input zips --out releases --diana reference/DiAna_dictionary.csv
```

Each drug record of `drug_latest_T` (`era_T`, `primaryid`, `quarter_T`, `drug_seq`) gets its ingredients from the DiAna dictionary (`rules/drug-names.md`, `src/open_altio/faers/drugnames/`). `open-altio build` (`open_altio.faers.build`) reads the dictionary from `reference/DiAna_dictionary.csv` in Open Altio's data folder, or from the file `OPEN_ALTIO_DIANA_DICTIONARY` names, and builds without drug ingredients when there is none; it never downloads unasked. `python -m open_altio.faers build --diana FILE` downloads it from DiAna's OSF project to `FILE` first when the file is missing. Either way a file whose SHA-256 is not the one the rule pins is refused. Our reviewed corrections are `mappings/faers/drug_names/`. Since 2024Q4 FDA writes some drug records on one row per dose; the rows of a record share its name and `prod_ai` and give one row here, and every count the step reports is of records, never rows.

| Table | One row per | Columns |
|---|---|---|
| `drug_substance_T` | drug record | the record's key, `substance_T` (ingredients sorted and joined with `;`, NULL when none), `substance_source_T` (`diana_name`, `diana_prod_ai`, `correction`, `none`), `diana_trial_T` |
| `drug_ingredient_T` | drug record and ingredient | the record's key, `ingredient_T` |

The manifest's `drug_names` records the file read (address, date, bytes, SHA-256), each correction with the dictionary keys it changed (`unused_corrections` lists those that changed none, so one DiAna has fixed is seen and dropped), and the records by source. A release built without the file, or with the rule switched off in `rules.toml`, has neither table, no `drug_names` funnel step and no unmapped-share limit on the methods page, and its `drug_names` entry says why.

### The drug classes layer (`atc_*_T`)

WHO's ATC classes for each drug record (rules `atc-index`, `atc-class-choice`, `atc-spelling-bridges`, `atc-group-classes`; `src/open_altio/faers/atc/`). They are a layer of their own: three tables whose names start with `atc_`, of `kind` `classes` in the manifest's `tables`, and listed again under the manifest's `classes` with the index year and WHO's citation, so a reader can leave out or hide the whole layer by that one list. No core table gains a class column, and every count and view of the core release is the same with the layer or without it. The four rules have one switch, rule `atc-index` (its step in `rules/steps.yaml`): off in a person's rules, the release is built without the layer.

The layer joins our drug-to-class table, `mappings/faers/atc/classes.csv`, built once a year from WHO's index by `python -m open_altio.faers atc-table` (`mappings/faers/atc/README.md`), to the substance each drug record names. That substance is `substance_T` of the drug-name step's `drug_substance_T` (see [The drug ingredients](#the-drug-ingredients-drug_substance_t-drug_ingredient_t)), so the layer is built right after that step. A release built without the drug ingredients, or without the class table, carries no classes, and its manifest says why.

| Table | Rows | Columns |
|---|---|---|
| `atc_index_T` | one per code the table holds, at every level | `atc_code_T`, `atc_level_T` (1 to 5), `atc_name_T` (WHO's name, as WHO writes it), `atc_index_year_T` |
| `atc_drug_T` | one per drug record whose substance has a code | the record's key, `atc_code_T` (its one class: a code of level 5, or for `shared_class` the class of level 4, 3 or 2 its codes share: those its one route group fits when two or more do, else all its possible codes; NULL when it cannot tell), `atc_level_T` (that class's level), `atc_index_year_T`, `atc_chosen_by_T` (`only_code`, `dose`, `route`, `indication`, `shared_class`, `group_class` or `cannot_tell`), `atc_possible_codes_T` (how many codes it had), `atc_matched_on_T` (`substance`, `ingredient_set` for a combination's own code, `each_ingredient` for a combination WHO has no code for, split, whose class is always `cannot_tell`; for a record whose ingredients have no code, FDA's words: `drug_name`, `active_ingredient`, `active_ingredient_set`, `each_active_ingredient`) |
| `atc_drug_codes_T` | one per possible code of each such record | the record's key, `atc_ingredient_T` (the substance or set the code is for), `atc_code_T`, `atc_level_T`, `atc_index_year_T`, `atc_chosen_T` (the code is the record's one class; false for every code of a record given a shared class) |

A record is looked up by its substance; one whose substance has no code, or that has none, by FDA's drug name and then its active ingredient, each as a whole name and never in part; else its group word's class (`group_class`). A combination's whole ingredient set is looked up first and gets WHO's combination code; only a combination with none is split into its ingredients, and a split combination's class is always `cannot_tell`. The class is chosen by the record's dose, then its route, from the rows of the record, then the indication the report gives for it; a record neither decides, unless it is a split combination, gets the class its codes share, at level 4, 3 or 2 (the codes its one route group fits when two or more do, else all its possible codes), or is `cannot_tell` (rule `atc-class-choice`). A report saying eye or ear takes the eye or ear code before WHO's code for both, and a single ingredient never takes a code under a class WHO reserves for mixes. The manifest's `classes.cases` counts cases of `case_latest_T`, never rows: those with a coded drug, those with at least one drug given a class (a shared class included), those with a drug given a shared class, and those with a drug it cannot tell. `methods.json` carries the same entry under `classes`, with WHO's citation for the page to show wherever it shows a class. `notebooks/faers/09_drug_classes` measures the layer on a real release.

### The statistics (`statistics_T`, `statistics_strata_T`)

After the release's Parquet is written, the build counts its cases for the statistics on a DuckDB connection of its own, held to the same memory limit, then fits and scores them in `open_altio.stats` and writes `statistics_T` with each pair's time to onset (`statistics/onset.py`, `rules/time-to-onset.md`), and `statistics_strata_T`, each pair's ROR within each age band and each sex (`statistics/strata.py`, `rules/ror-strata.md`). Every statistic counts one set of cases (`rules/statistics-cases.md`): the kept cases naming a suspect ingredient (`drug_ingredient_T`, primary or secondary suspect) and a reaction. What a reaction is lives in one place, `REACTION_NAMES` in `statistics/cases.py`: where the release's licensed part holds MedDRA, the step reads its `reac_meddra_T` and `meddra_pt` and counts each reaction under its current PT, named by its PT name; without MedDRA, a reaction is FDA's text as the explorer matches it. The `statistics` entry's `reaction_key` (`meddra_pt` with `meddra_version`, or `fda_text`) says which. `statistics_T` names PTs only, never a code, a lower level term or the text to PT link. MedDRA added to a release already built (`build_licensed`, `open-altio serve --meddra`, a host's upload) counts them again by its PTs (`statistics.recount`), as a build with MedDRA does: both tables and the explorer's copies are replaced whole, the database renamed over the old one so an explorer that has it open reads the new one at its next request. EBGM's prior is fitted on the release's own cases every build (`rules/ebgm.md`); when it does not fit, the EBGM columns are empty and the manifest says why. A release without the drug ingredients has no statistics. The explorer copies the tables into `explorer.duckdb` as `explorer_statistics_T` and `explorer_statistics_strata_T`, sorted by ingredient and reaction.

Then, where the release carries the drug classes layer, it counts the same cases again with each suspect drug record's WHO class in place of its ingredients, at each level rule `statistics-classes` names, fits a prior for each level and writes `atc_statistics_T` and `atc_statistics_ingredients_T` (`statistics/classes.py`), listed with the layer's tables under `classes`. The same function adds them to a release already built, with the explorer database's copies, as a full build writes them:

```sh
python -m open_altio.faers class-statistics --release releases/2026Q2
```

### Drug labels (`label_candidates_T`, `label_sections_T`)

```sh
python -m open_altio.faers labels-fetch --into ~/faers-labels
python -m open_altio.faers build --input ~/faers-zips --out releases --labels ~/faers-labels
```

Given a labels folder, the build adds FDA's current prescription labels: for each RxNorm ingredient or combination, the originator's label per route family, with their safety sections and indications as lines of text (rules label-source, label-choice, label-sections). Without one it prints `labels: skipped, no labels folder given`. The tables, their columns and the manifest's `labels` entry are in `src/open_altio/faers/labels/README.md`. Between releases `python -m open_altio.faers labels-refresh --release releases/2026Q2 --labels ~/faers-labels` brings them up to date from DailyMed's daily update files, and flags again where a label changed, without building FAERS again (rule label-refresh).

### The licensed MedDRA part (`licensed/`)

MedDRA codes, the LLT to PT mapping, everything above PT and SMQs are MSSO's licensed content: the explorer shows them only to a viewer its access hook allows (`src/open_altio/explorer/access.py`). They are built by a separate step into a separate folder of the release, never into `parquet/`, never listed in `manifest.json` and never in `explorer.duckdb`; a test checks that no public table or column names the hierarchy.

```sh
python -m open_altio.faers meddra --release releases/2026Q2 --meddra ~/Downloads/MedDRA_29_1_English_v2
```

```
releases/2026Q2/licensed/
  manifest.json                   format open-altio-licensed; the one MedDRA version held:
                                  language, released, built_at, source file sha256s,
                                  tables, and terms: per column, the texts, those placed through
                                  the history file and those matching nothing; the quarters
                                  fitting no single MedDRA version
  meddra/29.1/
    meddra_soc.parquet ... meddra_history.parquet   MedDRA's ASCII files verbatim as text
    meddra_term_T.parquet         every PT, lower level term and former name, normalised, with
                                  its code, PT and currency
    reac_meddra_T.parquet         per distinct text of pt, drug_rec_act and indi_pt in this
    drug_rec_act_meddra_T.parquet   release: pt_code_T, llt_code_T, matched_as_T (pt, llt,
    indi_meddra_T.parquet           former_name), llt_current_T, pt_current_T
```

The three columns are read to MedDRA's terms by one piece of code, `meddra/terms.py` (rule `meddra-terms`): a PT first, then a lower level term, then a name MedDRA used before renaming the term, from its history file. A reaction text that matches nothing refuses the step, because it means the MedDRA file is older than the data; indications and `drug_rec_act` texts that match nothing are counted and left as FDA wrote them. `pt_current_T` flags text that is not a PT of that MedDRA version. FDA's text is public, but which code it maps to, and whether it is still current, is MedDRA content that changes with the licensed version, so the mapping lives here and not in the public `_T` tables.

A release build given a MedDRA folder (`build_release(..., meddra_dir=...)`, or `python -m open_altio.faers build --meddra`) reads the terms in its own database, so the methods page's MedDRA cards count with them, and writes this part with the rest of the release. The methods page's rebuild is such a build: it gives the build the files the explorer was started with (`open-altio serve --meddra --rxnorm --labels --ime`, as `open_altio.faers.build.Inputs`), runs the labels step again when the release's reactions were flagged, keeping the files a person wrote into the version's folder, and refuses without a file for a layer the release holds rather than lose it. The step above reads a release already built. A release holds one MedDRA version, the newest held when it is built, and everything in it uses that one (`rules/meddra-version.md`): running the step with another version replaces the one held, and a new version waits until just before the next data build. The release date comes from MedDRA's numbering (x.0 on 1 March, x.1 on 1 September) unless `--released` says otherwise. Only English releases are accepted. Rebuilding the public release with `--overwrite` replaces the whole folder, and each new FAERS release needs the step again, because the mapping tables are keyed by that release's text. A host that keeps versions itself gives each release build the newest of them (`open_altio.faers.meddra.newest_held`), or reads a built release to it with `add_held`; `--held <folder>` does that from the command line. The licensed part is never offered as a public download or to SQL.

### The label dictionary

`python -m open_altio.faers labels --release releases/2026Q2` codes the release's FDA labels into MedDRA terms with the release's one MedDRA version, into the licensed part (`licensed/meddra/<version>/label_terms_T.parquet` and `label_uncertain.jsonl`), then flags each suspect drug's reactions into the public `label_flags_T`. See `src/open_altio/faers/labeldict/README.md`.
### RxNorm codes for drug records (`rxnorm/`)

`drug_rxnorm_T` gives each drug record, beside its ingredient (`substance_T` of `drug_substance_T`), its RxNorm ingredient code (IN) or multiple-ingredient code (MIN), and says how it was found or why it has none (`rules/rxnorm-ingredients.md`). FDA's drug name comes first, matched exactly to one RxNorm name, so a brand gives its precise ingredient (`LANTUS`: insulin glargine) while the record is still counted under the dictionary's ingredient (insulin). FDA's active ingredient (`prod_ai`) comes second, matched the same way, whole or every `\`-joined part, with the short reviewed list of FDA's names RxNorm writes otherwise (`mappings/faers/rxnorm/prod_ai_pairs.csv`: dextrose is glucose), so `KCL` with FDA's `POTASSIUM CHLORIDE` is coded potassium chloride and DIANEAL takes its own combination code. Only a record whose two FDA fields give no code falls back to the ingredient, through the reviewed name pairs in `mappings/faers/rxnorm/`; an ingredient that is an element alone (the dictionary's `potassium` for a potassium salt) gives none there. It is built with the release from NLM's RxNorm Current Prescribable Content, of the release the rule pins, read from the folder its zip unpacks to; the files are never kept in the repository:

```sh
python -m open_altio.faers build --input zips --out releases --rxnorm <folder>
```

```python
from open_altio.faers.rxnorm.match import Matcher
from open_altio.faers.rxnorm.rrf import read_rxnorm

m = Matcher(read_rxnorm(folder))
m.drug_name("LANTUS")  # Match(rxcui, rxnorm_name, tty, matched_by, reason)
m.prod_ai("POTASSIUM CHLORIDE")  # FDA's active ingredient, exactly
m.match("sacubitril;valsartan")  # an ingredient, as the drug names step writes it
```

| Column | What |
|---|---|
| `era_T`, `primaryid`, `quarter_T`, `drug_seq` | The drug record, keyed as `drug_substance_T` |
| `rxcui_T` | Its RxNorm code; NULL where it has none |
| `rxnorm_name_T` | RxNorm's name for the code, as RxNorm writes it |
| `tty_T` | `IN` or `MIN` |
| `matched_by_T` | `drug_name` (FDA's drug name is an RxNorm name), `prod_ai` (FDA's active ingredient is), `substance` (found from the record's ingredient) or `none` |
| `no_code_reason_T` | Why it has no code: no RxNorm name matches it, RxNorm files it under a different parent drug, the ingredient names an element and not which of its salts, or no US product has exactly these ingredients; NULL where it has one |

`ingredient_rxnorm_T` has one row per ingredient a record is counted under (`ingredient_T`, `substance_T` split at `;`), with the code that ingredient's own reading gives it (`Matcher.match`): `rxcui_T`, `rxnorm_name_T`, `tty_T` and `no_code_reason_T`, as above. The label flags read each ingredient's own label by it, for the pages that count any product containing the ingredient (`rules/label-flags.md`).

`open-altio build` reads NLM's files from `rxnorm/` in Open Altio's data folder, or the folder `OPEN_ALTIO_RXNORM_DIR` names (`--rxnorm` for `python -m open_altio.faers build`). Without them, with the rule switched off, or before the drug names step writes `drug_substance_T`, the release has no `drug_rxnorm_T` and the manifest's `rxnorm` entry says why. A folder holding another RxNorm release than the rule pins refuses the build.

### Where a change goes

- Another duplicate rule: a new release with its own changelog entry; the rules are `DUP_MEMBERS_T` (each rule's groups and guards) and `CASE_DUP_T` (the linked groups and the shown copy) in `src/open_altio/faers/duplicates.py`, the views `view_statements()` in `derive.py`.
- Another refusal: a check added to `src/open_altio/faers/release.py:checks_before_write`, which runs before anything is written (the legacy-country and suffix checks are there), or a caller's own through `build_release(checks=...)`.
- Methods page JSON: `methods.json`, built by `open_altio.faers.insights.methods.build_methods` from the funnel, `src/open_altio/faers/insights/steps.yaml` and the insight cards. A new funnel step needs its step card in `src/open_altio/faers/insights/steps.yaml` or the build is refused.
- The real build over all quarters: `build_release("zips", ...)`; see [Parity](#parity-with-counts-made-apart-from-this-code) and [A full build](#a-full-build).

## Parity with counts made apart from this code

`tests/faers/test_parity.py` (marked `slow`, skipped by the normal suite) checks a release built from FDA's 90 quarters, 2004Q1 to 2026Q2, against counts made apart from this code. An earlier, independent build of the same pipeline in Postgres gave these, and the release matched every step exactly:

| Step | Legacy | FAERS | Total |
|---|---|---|---|
| `report_versions` | 4,276,201 | 20,536,224 | 24,812,425 |
| `latest_versions` | 3,091,168 | 17,683,864 | 20,775,032 |
| `after_deleted_lists` | 3,091,168 | 17,585,777 | 20,676,945 |
| `kept_after_duplicates` | 3,079,299 | 17,306,099 | 20,385,398 |

The deleted lists hold 237,032 listings of 229,234 caseids.

The rules of notebook `02_case_versions` change three steps on purpose, so the test expects the Postgres counts less these differences, each counted in the notebook from the release before the change:

| Step | Legacy | FAERS | Total | Why |
|---|---|---|---|---|
| `latest_versions` | 3,008,826 | 17,683,864 | 20,692,690 | 82,342 AERS copies of cases FDA carried into FAERS no longer count as cases of their own (`rules/latest-version.md`) |
| `after_deleted_lists` | 3,002,752 | 17,585,777 | 20,588,529 | the same 82,342, including 230 whose FAERS version FDA deleted; and 6,074 more legacy cases on FDA's deleted lists (`rules/deleted-cases.md`) |
| `kept_after_duplicates` | 2,991,409 | 17,305,224 | 20,296,633 | the same; legacy countries read as codes set 11 more cases aside (`rules/legacy-country.md`), reaction terms compared in capitals 941 more (`rules/reaction-term-case.md`); of the 6,074 legacy deleted cases, 54 were already set aside, and 40 cases they had set aside as duplicates are kept again (25 legacy, 15 FAERS), so 5,980 fewer are kept |

The rules of notebook `04_duplicates` change the last step on purpose, counted in the notebook from a release with notebook 02's rules, apart from the release code:

| Step | Total | Why |
|---|---|---|
| `kept_after_duplicates` | 20,296,653 | groups of 8 or more from one company whose shared event date is padded set nothing aside, so 4,324 more are kept (`rules/dup-padded-event-dates.md`); the manufacturer number with its guards sets 3,939 more aside, and a number without its country code 365 more (`rules/dup-manufacturer-number.md`). The shown copy moves to the latest received in every group (`rules/dup-shown-copy.md`), which moves cases between eras but not the total |

Run over the tables of a release with notebook 02's rules, the release code sets aside the same 291,876 cases in the same 189,576 groups as the notebook. A release built with the rules of both notebooks switched off (the `rules.toml` in notebook 02's introduction) gives the Postgres counts themselves.

```sh
OPEN_ALTIO_ZIPS=zips OPEN_ALTIO_RELEASES=releases \
  uv run pytest -m slow tests/faers/test_parity.py          # builds a release, then checks it
OPEN_ALTIO_REAL_RELEASE=releases/2026Q2 \
  uv run pytest -m slow tests/faers/test_parity.py          # checks an existing release
```

`OPEN_ALTIO_BEFORE` names a release built with those rules off, to check it gives the Postgres counts; `OPEN_ALTIO_MEMORY_LIMIT` (default `6GB`) is passed to DuckDB. The test skips unless it is told which release to check or build.

## A full build

The build over all 90 quarters is held to two measures:

- **Memory.** The duplicate key's drug and reaction sets (`string_agg(DISTINCT ... ORDER BY ...)` per case) are built one quarter at a time into scratch tables (`src/open_altio/faers/duplicates.py:DUP_SETS`), a few hundred MB each, then dropped, because DuckDB keeps an ordered aggregate's state in memory: over all quarters at once they need more than a 16 GB limit. `build_release(memory_limit=..., temp_directory=...)` and `--memory-limit`, `--temp-directory` set DuckDB's limit and spill folder. DuckDB overshoots its limit: with 16 GB set the process peaked at 23 GB, so leave headroom.
- **Size.** Derived tables come out of their joins in no row order, so every table is written sorted by quarter, then primaryid or case (`src/open_altio/faers/release.py:WRITE_ORDER`), with zstd at level 9. That halves `demo_latest_T` and `case_latest_T` (to 488 and 513 MB) and lets a reader skip row groups by quarter. No value or count changes.

On a Mac with 10 cores and 64 GB (DuckDB 1.5.6), unlimited, the build takes about 12 minutes, of which loading the zips takes about 5, and writes a release of 5.35 GB: 2.04 GB of raw tables, `case_dup_T` 262 MB. The rest of the size is by design: derived tables carry the raw columns so a reader needs no join (`drug_latest_T` alone is 1 GB, as `drug` is), and the deduplicated set is views, not copies. Held to the build memory rule, as `open-altio build` holds it, the same build takes longer and fits a 16 GB laptop (`rules/explorer-build-memory.md`).
