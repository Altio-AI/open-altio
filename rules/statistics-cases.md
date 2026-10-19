---
rule: statistics-cases
line: Every statistic counts one set of cases, those kept that name an ingredient of a suspected drug and a reaction, so a pair's numbers can be read side by side.
values:
  product_roles: [PS, SS]
  strata: [age_band, sex, receipt_year]
  unknown: unknown
always_on: true
why_locked: The statistics take no case out of the release; the thresholds you read them against are set on the Statistics tab.
enforced_in:
  - src/open_altio/faers/statistics/cases.py
  - src/open_altio/faers/statistics/step.py
  - src/open_altio/faers/meddra/licensed.py
  - src/open_altio/explorer/statistics.py
  - tests/faers/statistics/test_statistics_cases.py
  - tests/faers/statistics/test_statistics_meddra.py
---
# The cases the statistics count

Every statistic counts one set of cases: the cases the release keeps that name at least one suspect ingredient and at least one reaction. EBGM, PRR, ROR, RRR and IC all count it, and so do each pair's time to onset (`time-to-onset`) and its ROR by age band and by sex (`ror-strata`), so their numbers for one ingredient and reaction stand side by side.

- **Cases**: the cases the release keeps after duplicates (`dup_kept_T`, rule `dedup-default`), each counted once. A case counts only if it names an ingredient and a reaction below. These cases are the whole table: the total N, the comparator cell c and the cell d are counted over them and no others.
- **Ingredient**: each ingredient of every drug the case names as primary or secondary suspect (`product_roles`, FDA's `role_cod`), from `drug_ingredient_T` (rule `drug-names`). A combination counts for each of its ingredients, so valsartan's cases include those naming Entresto: "any product containing" the ingredient. Interacting and concomitant drugs do not count. A release built without the drug names has no statistics.
- **Reaction**: where the release holds MedDRA (rule `meddra-version`), the current preferred term FDA's text is read to in that version (rule `meddra-terms`), named as MedDRA writes it, so an old term, a renamed one or a lower level term counts with its PT. Without MedDRA, the text as FDA wrote it, matched whatever its capitals and spacing, as the explorer's reaction search matches it, and an old MedDRA term and its current term count apart. The manifest's `statistics` entry says which a release used: `reaction_key` is `meddra_pt`, with its `meddra_version`, or `fda_text`. MedDRA added to a release already built counts its statistics again by its PTs, as a build with MedDRA does. The statistics name PTs only: never a MedDRA code, a lower level term or which of FDA's texts went to which PT, which stay in the release's licensed part. A release with MedDRA also holds the same two tables counted by FDA's text, as a release without MedDRA counts them: `statistics_as_published_T` and `statistics_strata_as_published_T` (the entry's `as_published`), for a viewer the host shows reactions as FDA wrote them (rule meddra-terms), who is given those and never the ones counted by PT.
- **Counting**: distinct cases. A case that names an ingredient twice, or a reaction twice, counts once for that pair.
- **Strata**, within which EBGM's expected counts are worked out: every combination of the listed parts. `age_band` is the case's age band, `age_band_T` (`age-bands`), the one the explorer's age filter reads; `sex` is `sex_T`, female or male (`sex-codes`); `receipt_year` is `init_year_T`, the year FDA first received the case. A value that is not given (rule `not-given`) is a group of its own, named `unknown`.

**Why:** distinct cases, not drug or reaction rows, so one long report does not weigh more than a short one. The table holds only cases that could have been counted for an ingredient: a case with none would sit in c and d but never in a or b, and pull every ratio down. Suspect drugs only, because counted in every role a medicine many people take alongside the suspect one becomes a frequent suspect itself (`notebooks/faers/05_drug_names`). Comparing within age, sex and year keeps differences in who reports, and when, from looking like a drug and reaction association (DuMouchel 1999). Counting under the current PT keeps one reaction from being split across the names MedDRA gave it over the years, or across the lower level terms FDA's older quarters hold (`notebooks/faers/06_meddra_versions`).
