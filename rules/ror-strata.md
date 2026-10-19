---
rule: ror-strata
line: Each pair's odds ratio (ROR) is worked out again within each age band and each sex, so a link that comes only from who takes the drug shows up.
values:
  by: [age_band, sex]
always_on: true
why_locked: The statistics take no case out of the release; they are read on the Statistics tab and a pair's cases.
enforced_in:
  - src/open_altio/faers/statistics/strata.py
  - tests/faers/statistics/test_statistics_strata.py
---
# ROR by age band and by sex

The reporting odds ratio of an ingredient and a reaction, worked out again on the cases of one age band alone, and on the cases of one sex alone. If an ingredient looks linked to a reaction only because, say, older people take it and older people report the reaction more, the ratios within each age band show it.

For each part listed in `by`, and each of its values, the pair's table of cases (drawn in `prr`) is counted again on the cases with that value only, and its ROR and 95% interval are worked out on it exactly as `ror` says. The cases are the statistics' own (`statistics-cases`), with the same suspect ingredients and reactions. `age_band` is the case's age band (`age_band_T`, rule `age-bands`) and `sex` its sex (`sex_T`, rule `sex-codes`); a value that is not given is a group of its own, `unknown`. Each part is taken on its own: the age bands over both sexes, the sexes over every age band, never the two crossed.

`statistics_strata_T` holds one row for each pair and value where the pair has at least one case: the part (`by_T`), the value (`stratum_T`), the four counts the table is drawn from (`cases_T`, `ingredient_cases_T`, `reaction_cases_T` and `stratum_cases_T`) and `ror_T` with `ror_lower_T` and `ror_upper_T`. A value where the pair has no case is not written: its ROR is empty, as it is wherever a cell of the table is 0.

**Not a pooled ratio:** this gives one ROR per value. A single ratio adjusted for age and sex together (Mantel and Haenszel) is not worked out.

**Why:** within age and sex, differences in who reports cannot make a pair look linked (DuMouchel 1999); EBGM compares within them already (`statistics-cases`), and this shows the ROR the same way, a part at a time so each ratio stands on enough cases. The ROR is van Puijenbroek et al. (2002), as in `ror`.
