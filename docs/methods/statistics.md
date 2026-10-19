# The statistics

For anyone reading the Statistics tab, or the `statistics_T` table, who wants to know how the numbers are made and how far to trust them.

Each statistic's formula, source and presets are its rule. This page says how they fit together.

## One set of cases

Every statistic counts the same cases ([statistics-cases](https://github.com/Altio-AI/open-altio/blob/main/rules/statistics-cases.md)): the cases the release keeps after duplicates that name at least one ingredient as primary or secondary suspect and at least one reaction.

- **Ingredients.** An ingredient counts in any product containing it, so a combination counts for each of its ingredients.
- **Once per pair.** Each case counts once for a pair, however often it names the drug or the reaction.
- **Side by side.** Because the five statistics share the cases, their numbers for one pair can be read side by side, and they join on ingredient and reaction.

How reactions are counted depends on MedDRA:

- **With MedDRA in the release,** each reaction is counted under the preferred term it belongs to in that MedDRA version today, and named by it, so an old or renamed term counts with its current one. The release also counts them by FDA's text, in `statistics_as_published_T` and `statistics_strata_as_published_T`, for anyone shown reactions as FDA wrote them.
- **Without MedDRA,** reactions are counted by FDA's text, matched whatever its capitals and spacing, and an old MedDRA term and its current one count apart.

The release's manifest says which way it counted (`reaction_key` under `statistics`).

## EBGM, fitted on each release

EBGM is DuMouchel's Gamma-Poisson Shrinker ([ebgm](https://github.com/Altio-AI/open-altio/blob/main/rules/ebgm.md)), written from the published papers: DuMouchel (1999), DuMouchel and Pregibon (2001) and the text and printed example of Canida and Ihrie (2017). No implementation's code was read.

**Expected count.** Each pair's expected count is worked out within age band, sex and year received. A drug reported mostly by older women, or mostly in one year, is compared with reports like its own.

**The fit.** Every build fits the prior on that release's own cases, over every ingredient and reaction cell including the ones never seen together. It records the fit in the manifest: the five hyperparameters, and what each of four starting points reached.

- **When it is used.** The fit is used only when at least two starts agree inside the parameter space. Otherwise the release carries no EBGM and says why, and the other statistics are unchanged.
- **The default threshold.** A prior fitted over every cell shrinks small counts less than one fitted on the pairs seen alone, so some pairs seen only twice reach EB05 2. The default threshold therefore asks for at least three cases beside EB05 at least 2.

**How the code is checked,** three ways:

- cases worked by hand;
- the worked example Canida and Ihrie print;
- tables drawn from the model itself, whose prior the fit recovers.

Run beside an earlier implementation on FAERS, it gave the same expected counts and, under the same prior, the same EBGM to twelve decimals. The two differ only in the prior they fit, because the other fits the pairs seen alone, which on FAERS has no maximum inside the parameter space.

## PRR, ROR, RRR and IC

These come straight from each pair's table of cases ([prr](https://github.com/Altio-AI/open-altio/blob/main/rules/prr.md), [ror](https://github.com/Altio-AI/open-altio/blob/main/rules/ror.md), [rrr](https://github.com/Altio-AI/open-altio/blob/main/rules/rrr.md), [ic](https://github.com/Altio-AI/open-altio/blob/main/rules/ic.md)), with no correction added.

- **Empty, never infinite.** A value the table cannot give is left empty.
- **Both chi-squares** are given beside PRR. The Evans preset reads the one with Yates' correction.
- **Crude expected count.** Their expected count is the crude one, over the whole table, so a pair's RRR is seldom its cases over EBGM's expected count.

## ROR by age band and by sex

Each pair's ROR is worked out again on the cases of one age band alone, and of one sex alone ([ror-strata](https://github.com/Altio-AI/open-altio/blob/main/rules/ror-strata.md)), a part at a time, never crossed.

- **Reading it.** Where the ratio is high overall but not within any age band, who reports, not the drug, may be the reason.
- **Where to see it.** Pressing a pair on the Statistics tab opens its cases, with these ratios under them.

## By drug class

Every statistic but the time to onset is worked out again with each drug's WHO class in place of its ingredient ([statistics-classes](https://github.com/Altio-AI/open-altio/blob/main/rules/statistics-classes.md)), on the same cases and reactions, at the therapeutic, pharmacological and chemical subgroup of the class.

- **A prior per level.** Each level gets its own EBGM prior, fitted on that level's cells alone, since a broader class holds its narrower ones.
- **Once per class.** A case counts once for a class however many of its drugs are in it.
- **Certain levels only.** A drug counts at every level its class is certain at. One whose report does not say which of its uses it was ("can't tell") counts at none.
- **Reading it.** On a drug's Statistics tab, its class's EB05 stands beside its own. When the two are close, the reaction is reported for the whole class. When the drug's is far higher, it stands out for the drug.

## Time to onset

Each pair's time to onset is the median over the ingredient's suspect drugs, in the pair's cases, that have one ([time-to-onset](https://github.com/Altio-AI/open-altio/blob/main/rules/time-to-onset.md)): from a first dose and an event date both known to the day.

Most drugs have none, and `statistics_T` says how many and why:

- the event date is padded or not exact;
- the first dose is not exact;
- the event came before it.

A median from a few drugs says little.

## Thresholds

Each statistic's common thresholds are presets on its rule. On the Statistics tab you may pick one, set your own numbers or use none.

!!! note
    Meeting a threshold is not a signal and not evidence that the drug caused the reaction. Spontaneous reports say what people chose to report, so a pair can stand out because of publicity, a lawsuit or how a company reports, and a real effect can hide in a reaction everyone reports.
