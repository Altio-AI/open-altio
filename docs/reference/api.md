# The questions and their answers

For anyone building a product on Open Altio: every question a product may ask of a release, over HTTP or in its own process, and what each answers.

Contract version 1.0: these routes, their functions and their answers' keys are part of Open Altio's [written contract](contract.md).

## How to ask

Over HTTP, ask the explorer that `create_app(release_dir)` builds. Parameters are query string values, a list by repeating the name (`pt=headache&pt=nausea`). An answer is JSON; a refusal is `{"problem": "..."}` with its HTTP status, and 503 while no release can be read.

In your own process, ask the same function the route asks:

```python
from open_altio.explorer.access import LOCAL
from open_altio.explorer.questions import ask, open_release_data

data = open_release_data("releases/2026Q2", LOCAL)  # any finished release folder, read only
ask("GET /api/summary", data, {"product": ["valsartan"]})
```

- `open_release_data(folder, viewer)` reads one release folder, apart from the live one, so a product that keeps an earlier folder gets that release's own counts after a newer one is live. For the live release of an app, `explorer_of(app).data(viewer)` gives the same. Keep the data while you ask: it holds the release open and remembers what it has worked out.
- `ask(route, data, query)` answers what the route answers, under the rules the release was built with. The query is a dict of lists, as `urllib.parse.parse_qs` reads a query string; a route's path parameters go in it under their own names (`{"era": ["faers"], "key": ["9004004"]}`).
- `PUBLISHED` maps each route to its function. A route whose answer needs more than a release's data (who is asking, SQL, a file) has none, and is asked over HTTP only.

## What every answer holds

- **The release it was counted on.** Every answer that is a JSON object, but who is asking (`/api/me`), holds `counted_on`: the release's name (`release`), its `source`, and its `first_quarter` and `last_quarter`.
- **The same answer to the same question.** Every list is in a fixed order (by its count, most first, then by its name), and no answer reads the clock or chance, so the same question on the same release answers the same, byte for byte. Two values say when something happened rather than what the release holds: how long a SQL query ran (`seconds`) and the moment a file was made, in its name and its manifest.
- **The cases behind each count.** Each count of a drug's events, a group of reactions, the Overview, an event's breakdowns and a counted question carries `cases_query`: the query string that lists exactly its cases in [`/api/cases`](#get-apicases), under the same question, filters and window.
- **The keys listed below.** Each list is the keys of the answer to the question the contract test asks on the invented release (`ASKED` in `open_altio.testing.contract`, recorded in `tests/contract/snapshots/api.json`). Some keys come only with what that question asks, such as a product, MedDRA or the label flags. A list answer lists its items' keys.

The rules page (`/api/rules`) and the notes outbox (`/api/notes/outbox`) are the explorer's own and may change in any release, as may anything else not on this page.

## The filters

Every question that asks "the filters" takes the explorer's filters, the same as a page's address:

| Parameter | What it chooses |
|---|---|
| `product`, `prole`, `unit`, `include`, `exclude` | The drug whose page this is, counted as its settings say ([A product](#a-product)) |
| `dprod`, `drole` | All cases' drug filter: drugs or FDA's spellings with no ingredient, and the roles counted |
| `pt`, `pt_out`, `smq`, `soc` | Reactions (any spelling of a preferred term), a term left out, an SMQ (`code:narrow` or `code:broad`) and a system organ class; SMQs and classes only for a viewer with MedDRA |
| `atc`, `atc_out`, `arole`, `could` | WHO's drug classes, where the release carries them and the viewer may see them |
| `label` | A product's Label status, where the release holds the label flags |
| `received_from`, `received_to`, `event_from`, `event_to` | Days, `yyyy-mm-dd`: when FDA received the case, and when the event began |
| `sex`, `age`, `country`, `outcome`, `reporter`, `sender`, `era` | The case's own fields, as the filters name their values |
| `dose`, `route`, `dose_form`, `lot`, `indication`, `onset`, `dechal`, `rechal`, `other_drug` | What the drug records a question counts give: the product's own, in the roles it is counted in, or every record with no product. Words as written, whatever their capitals and spaces; `indication` by today's preferred term where reactions are counted by it, else FDA's text; `onset` days from the first dose, `2-7`, either end open (`91-`); `dechal` and `rechal` FDA's codes `Y`, `N`, `D`, the first record giving one; `other_drug` another drug in those roles, by its ingredients or FDA's spelling. `_none` keeps the cases that give none |
| `report_type`, `other_reaction` | FDA's report type (`EXP`, `PER`, `DIR`, ...), and a reaction the case names too |
| `dedup` | `kept_only` (probable duplicates left out) or `all` |

## A product

Every question that counts one drug names it by these six settings, and only by them (`explore.product_unit`), so every drug the release names is counted the same way. Each one left out takes its default, Open Altio's standard count.

| Parameter | What it chooses | Left out |
|---|---|---|
| `product` | The drug: an ingredient or a combination as the release names it (`valsartan`, `sacubitril;valsartan`), or FDA's spelling with no ingredient (`VALSARTAN TEVA`). Any other of FDA's names opens the drug it is read to; a name the release does not hold counts no case | No drug: every case |
| `prole` | The roles a case names the drug in, FDA's codes `PS`, `SS`, `I` and `C`, repeated | `PS` and `SS` ([rule explorer-drug-counts](https://github.com/Altio-AI/open-altio/blob/main/rules/explorer-drug-counts.md)) |
| `unit` | `any` (any product containing it) or `exact` (that product alone) | `any` (the same rule) |
| `include` | FDA's spellings with no ingredient counted with the drug, repeated | None |
| `exclude` | The drug's spellings left out, repeated | None |
| `dedup` | `kept_only` (probable duplicates left out) or `all` | `kept_only` ([rule dedup-default](https://github.com/Altio-AI/open-altio/blob/main/rules/dedup-default.md)) |

A `prole`, `unit` or `dedup` that is not one of its choices is refused with 400 and one plain line saying the choices.

## The published questions

### `GET /api/me`

Who is asking and what they may use: MedDRA's and WHO's tiers, SQL, the filtered export, the statistics and SQL's time limit. A host's access hook may add keys of its own.

- Function: none: asked over HTTP only.
- Asks: nothing.
- Answers: `exports`, `sql`, `sql_seconds`, `statistics`, `tiers`.

### `GET /api/release`

What the release holds and how its pages name things: its quarters and eras, its cases with probable duplicates and without, the age bands and countries, the drugs and reactions as it counts them, WHO's classes, the label flags, and a MedDRA part an older Open Altio added.

- Function: `api.release_info`.
- Asks: nothing.
- Answers: `ages`, `all_cases`, `built_at`, `by_era`, `cases`, `class_statistics`, `classes`, `counted_on`, `countries`, `dedup`, `drugs`, `eras`, `event_thresholds`, `field_notes`, `labels`, `lists`, `meddra_older`, `quarters`, `reactions`, `refreshed`, `release`, `set_aside`.

### `GET /api/products`

Drugs found by their name or a spelling they are reported under, and FDA's spellings with no ingredient, each with its cases.

- Function: `search.products`.
- Asks: `q`, what was typed.
- Answers: `counted_on`, `drugs`, `q`, `unmapped`.

### `GET /api/product`

What a product page opens for a name: its drug with its ingredients, or FDA's spelling with no ingredient, with its cases. Not found (404) for a name the release does not hold.

- Function: `api.product_named`.
- Asks: `product`.
- Answers: `about`, `cases`, `counted_on`, `ingredients`, `kind`, `name`, `reported`, `spellings`, `title`.

### `GET /api/spellings`

The spellings a product page counts, each with its cases, those left out and those added, and `settings`: the cases each setting of the product finds with the others as passed, `unit` (`any`, `exact`), `roles` (each role alone) and `dedup` (`kept_only`, `all`).

- Function: `search.spellings`.
- Asks: `product` and the filters; `q` narrows the list as a person types.
- Answers: `counted_on`, `excluded`, `included`, `q`, `settings`, `spellings`, `total`, `unmapped`.

### `GET /api/summary`

The count line and every chart of the Overview: cases by year, sex, age, country, reporter, sender, outcome, seriousness and era, the drugs and reactions, each chart counted under every other filter.

- Function: `explore.summary`.
- Asks: the filters.
- Answers: `age`, `all_cases`, `by_era`, `cases`, `cases_query`, `counted_on`, `country`, `era`, `given`, `kept_only`, `outcome`, `reactions`, `reporter`, `sender`, `serious`, `set_aside`, `sex`, `soc`, `spellings`, `years`.
- `cases_query` lists the cases of `cases`. Each bar of a chart is `[value, cases, cases_query]` (a drug's `[drug, cases, title, cases_query]`), its question the Overview's with the bar's value as that chart's filter: a year's, the days of that year the question takes in. A year's is null for the cases with no full date, which no filter picks.

### `GET /api/timeline`

Cases by the period FDA first received them, or with `by=event` by the period the event began.

- Function: `explore.timeline`.
- Asks: the filters; `grain` (`year`, `month`, `week` or `day`); `by` (`received`, the default, or `event`).
- Answers: `counted_on`, `grain`, `rows`, `undated`.
- `rows` is `[period, cases]` for each period with cases, its first day as `yyyy-mm-dd`, in time order. By `event` a case is placed by its event date as the `event_from` and `event_to` filters read it, FDA's full dates only, so every case it places is one those filters can pick; `undated` counts the cases it cannot place. Refused (400) for a `by` that is neither.

### `GET /api/events`

A drug's events: one row per event its counted cases name under the filters, by today's preferred term where the release holds MedDRA, most cases first, then by name. Every count is of distinct cases, and a share is its count over `cases`.

- Function: `eventlist.events`.
- Asks: [a product](#a-product), which it needs (400 without), and the filters.
- Answers: `columns`, `counted_on`, `newest_quarter`, `not_available`, `rows`.
- `columns` names each value of a row in `rows`: `pt`, the event; `cases`; `newest`, its cases placed in the release's newest quarter (`newest_quarter`, written `2026 Q2`) by the day a case is dated by ([rule received-day](https://github.com/Altio-AI/open-altio/blob/main/rules/received-day.md)); `prior`, those in the quarter before it; `recent`, those in each of the newest quarters, oldest first ([rule explorer-event-thresholds](https://github.com/Altio-AI/open-altio/blob/main/rules/explorer-event-thresholds.md)); `years`, `[[year, cases]]` for each year with cases, adding up to `cases`; `busiest_year`, the year with the most, the earliest of those tied; `serious`, `death` and `life_threatening`, its cases with an outcome code of each ([rule serious-outcomes](https://github.com/Altio-AI/open-altio/blob/main/rules/serious-outcomes.md)), a case with no outcome in none; `death_or_life_threatening`, its cases that ended in death or were life-threatening, each once, so never more than `death` and `life_threatening` together and never fewer than either; `label`, `{answer, setid, spl_version, forms}`: the label flag ([rule explorer-label-flags](https://github.com/Altio-AI/open-altio/blob/main/rules/explorer-label-flags.md)), the DailyMed set ID and version of the label it was read on, and each route family's answer where they differ, with `no_label` for a drug with no label; `dme` and `ime`, the event on EMA's lists; `cases_query`, the question that lists its `cases`.
- `not_available` gives, for each column with a null value, why: a release without the label flags or the lists, or FDA's spelling with no ingredient, which is read against no label.

### `GET /api/events/group`

A group of reactions counted as one event of a drug or of a drug class, such as an SMQ's preferred terms or any list of them: the figures a row of [a drug's events](#get-apievents) has, worked out by the same code, under the drug's settings and the filters. A case counts once however many of the group's reactions it names, so a group of one reaction is that event's row, figure for figure. A group the drug's cases never name counts no case.

- Function: `eventlist.group`.
- Asks: [a product](#a-product) or a drug class (`atc`, with `atc_out` and `arole`), one of which it needs (400 without), `reaction` (repeated, any spelling of a preferred term: the group, 400 without), and the filters.
- Answers: `busiest_year`, `cases`, `cases_query`, `counted_on`, `death`, `death_or_life_threatening`, `life_threatening`, `newest`, `newest_quarter`, `prior`, `recent`, `reactions`, `serious`, `years`.
- `reactions` names the group's reactions as the release names them, in alphabetical order; `cases_query` is the question that lists its `cases`; the other keys are the columns of a drug's events of the same names, `busiest_year` null when the group has no case.

### `GET /api/cases`

One page of the matching cases, each with its drugs and reactions. With a count's `cases_query` it lists exactly that count's cases.

- Function: `caselist.cases`.
- Asks: the filters; `page`, `sort`; `event` (repeated, any spelling of a preferred term): only the cases naming any of them, counted as one event as [a drug's events](#get-apievents) count it. With `period` (`before` or `window`) the question is [an event's breakdowns](#get-apibreakdowns), with its event as `event`: the cases counted in that period; with `field`, a line's field, those that give it (for Duplicates, every case, kept or set aside); with `value`, those that give that value, read the way the line counted it. `case_number`: the first digits of a case number, only the cases whose number starts with them (anything but digits is ignored). `detail=columns`, with [a product](#a-product): more of each case about the drug.
- Answers: `cases`, `counted_on`, `meddra_version`, `page`, `size`, `total`.
- `total` is every case the question lists, over all its pages. Each case gives its day, age, sex, weight (`wt_kg_T`), country, who reported it (`reporter_type_T`), the report's type and company (`rept_cod`, `company_T`, `direct_T` for a report sent straight to FDA), its outcomes, its duplicate flags with its group's shown copy (`dup_shown_case_T`) and, on the shown copy, the copies set aside (`dup_other_cases_T`), its drugs (`[name, ingredients, role, class]`) and its reactions as FDA wrote them.
- `sort` is `newest` (the default) or `oldest` by the day a case is dated by, or one of `case`, `event`, `age`, `sex`, `weight`, `reporter`, `serious` and, with a product, `onset`, `role`, `dechal`, `drugs`, `indication`, `start`, `stop`; each sorts its first way (highest case number, newest event, oldest, female, heaviest, health professionals, most serious by [rule serious-outcomes](https://github.com/Altio-AI/open-altio/blob/main/rules/serious-outcomes.md)'s order, longest onset, primary suspect, positive dechallenge, most suspect drugs, what it was taken for A to Z, newest therapy start or stop) and, ending `-asc` (`onset-asc`), the other. A case that gives no value comes last both ways; ties go newest first. Any other `sort` is newest first.
- With `detail=columns` each case has `columns_T`, null without a product: the drug's own records the page counts, first by FDA's role order and then its drug sequence, read as [an event's breakdowns](#get-apibreakdowns) read them. `role`, `onset` (days, the first dose day 1; `onset_why` the reason when none, rule time-to-onset), `dechal` and `rechal` (FDA's code) are those of its first record that gives one; `dose`, `route`, `dose_form`, `lot` and `indication` list every value its records give, as written; `start` and `stop` are `[day, digits FDA gave]`, the earliest start and the latest stop of its therapy rows. A value that reads Not given ([rule not-given](https://github.com/Altio-AI/open-altio/blob/main/rules/not-given.md)) is null or left out. `suspects` lists `[name, role, its own]`, the drug's own records first, then the case's other drugs in the roles the page counts; `other_reaction` the case's reactions besides the event's (its `event` and chosen reactions), by name.
- Refused (400) for a `field` or `value` without `period`, a period that is not `before` or `window`, no event, a field that is not a line of rule `breakdown-lines`, a line the release or this viewer cannot give (with the reason), and a value that no case of the question gives the line's field.

### `GET /api/count`

A question's cases counted by one field: distinct cases for each value the field gives, each with the question that lists exactly its cases, as [rule counted-question](https://github.com/Altio-AI/open-altio/blob/main/rules/counted-question.md) says. Refused (400), with the choices named, for a `by` that is not one of the rule's, and for a count by outcome, route, dose form or lot under that field's own filter, since a case can give several.

- Function: `counted.count`.
- Asks: `by` (`year`, `quarter`, `month`, `event`, `outcome`, `sex`, `age`, `country`, `reporter`, `route`, `dose_form` or `lot`), [a product](#a-product), which it may leave out to count every case, and the filters.
- Answers: `by`, `check`, `counted_on`, `counts`, `described`, `question`, `sql`, `total`, `why`.
- `question` is the query exactly as asked, each name with its values; `described` says it in plain words, the way a filtered export's manifest does, with a line for each filter value left out because it is not one of its choices or not a day. `total` is the question's cases. Each item of `counts` is `[value, cases, cases_query]`: the value as its field's filter takes it (`_none` for Not given), a year, quarter or month as `2026`, `2026q2` or `2026-04`, an event by its name; `cases_query` lists exactly its cases in [`/api/cases`](#get-apicases). A case with no day it is dated by, or naming no reaction, counts in a row whose value and `cases_query` are null, as no filter picks it. Times are in time order; the other values by their cases, most first, then by value, with a null row last. A case counts once under each event, outcome, route, dose form or lot it gives, so those counts can add up to more than `total`.
- `check` is every count made a second way, apart from the first: the question read again from its query string, and counted on the release's own Parquet tables (`case_dedup_T` or `case_latest_T`, `drug_latest_T`, `drug_substance_T`, `drug_ingredient_T`, `reac_latest_T`, `outc_latest_T`, the label flags' tables, and for today's preferred terms MedDRA's licensed `reac_meddra_T` and `meddra_pt`), never the explorer's database (`recount.recount`). It holds `counts` (`[value, cases]`), `total`, `agrees` (true only when every value's cases and the total are the same both ways), `differences` (`[value, first, second]` for each value counted differently, 0 where one count has no such value) and `unread`. A question naming anything the second count does not read (`recount.READS`: today MedDRA's SMQs and system organ classes, WHO's classes, or any other name) is not counted again: `unread` names it, and `counts`, `total`, `agrees` and `differences` are null, never agreeing.
- `sql` is that second count as one query (`recount.sql_of`), each value written in as a constant (text in single quotes, each quote doubled, so no value can change the query; a day as a `DATE`). It runs as it stands in [Tables and SQL](#post-apisql), and on the release downloaded, to `check`'s `counts`, row for row and in the same order, so anyone can see how each number was counted and count it again. It reads MedDRA's licensed tables only for a count by event or a question choosing reactions, where reactions are counted by today's preferred term. `sql` is null, never a query that cannot run, with the reason in `why` (`{"sql": ...}`; `{}` when there is a query): for a viewer who may not see MedDRA's licensed part when the query would read it, and for a question not counted again.

### `GET /api/case/{era}/{key}`

One case with every row the release holds for it, why a probable duplicate is shown or set aside, and its group. Not found (404) for a case the release does not hold.

- Function: `api.case_asked`.
- Asks: `era` (`faers` or `legacy`) and `key`, in the address.
- Answers: `age`, `age_band_T`, `age_cod`, `age_years_T`, `case_id_T`, `case_key_T`, `caseid`, `caseversion`, `classes`, `company_T`, `counted_on`, `country_T`, `country_source_T`, `direct_T`, `drug`, `dup_group_T`, `dup_kept_T`, `dup_other_cases_T`, `dup_rule_T`, `dup_shown_case_T`, `era_T`, `event_dt`, `event_dt_T`, `event_dt_prec_T`, `fda_dt`, `first_fda_dt_T`, `group`, `group_first_dt_T`, `i_f_code`, `indi`, `init_fda_dt`, `lit_ref`, `meddra_version`, `mfr_sndr`, `no_drug_or_reaction_T`, `not_given_T`, `occp_cod`, `occr_country`, `outc`, `outcomes_T`, `primaryid`, `probable_duplicate_T`, `quarter_T`, `reac`, `reasons`, `reporter_country`, `reporter_type_T`, `rept_cod`, `serious_no_drug_or_reaction_T`, `sex`, `sex_T`, `ther`, `wt`, `wt_cod`, `wt_kg_T`.

### `GET /api/terms`

Reactions found by what was typed, with their cases; with MedDRA, lower level terms and SMQs too.

Lower level terms and SMQs are for a viewer who may see MedDRA's licensed part. Asked for with `meddra=1` by a viewer without it, the answer holds none and `why_no_licensed` says why (null otherwise).

- Function: `search.term_search`.
- Asks: `q`; `kind`; `meddra=1` for MedDRA's licensed part; the filters.
- Answers: `counted_on`, `kind`, `llts`, `q`, `smqs`, `terms`, `totals`, `why_no_licensed`.

### `GET /api/smq`

An SMQ's preferred terms, narrow first, each with its cases. Only for a viewer who may see MedDRA's licensed part (403 otherwise).

- Function: `search.smq_terms`.
- Asks: `code`; `scope` (`narrow` or `broad`, the default, which holds both); the filters. Child SMQs are folded in.
- Answers: `code`, `counted_on`, `n_terms`, `name`, `terms`.

### `GET /api/termcounts`

Cases for each chosen preferred term.

- Function: `search.term_counts`.
- Asks: `pt` (repeated) and the filters.
- Answers: `counted_on`, `terms`.

### `GET /api/drugs`

Drugs found by what was typed for the All cases drug filter, with their cases in the roles counted.

- Function: `search.drug_search`.
- Asks: `q`, `drole` and the filters.
- Answers: `counted_on`, `drugs`, `q`, `unmapped`.

### `GET /api/classes`

WHO's drug classes the class filter offers, each with its cases. Only where the release carries the classes and the viewer may see them.

- Function: `api.class_listing`.
- Asks: `q`, `parent` and the filters.
- Answers: `chosen`, `citation`, `classes`, `could`, `counted_on`, `index_year`, `left_out`, `parent`, `q`.

### `GET /api/exportsize`

The rows in each file a filtered export would hold: cases, drugs and reactions.

- Function: `explore.export_size`.
- Asks: the filters.
- Answers: `cases`, `counted_on`, `drugs`, `reactions`.

### `GET /api/statistics/about`

Whether the release holds statistics and why not, what was counted, the EBGM fit, and each statistic in plain words.

- Function: `statistics.about`.
- Asks: nothing.
- Answers: `cases_rule`, `classes`, `counted`, `counted_on`, `ebgm`, `meddra_version`, `present`, `reaction_key`, `shown`, `statistics`.

### `GET /api/statistics`

One page of drug and reaction pairs with EBGM, PRR, ROR, RRR and IC.

- Function: `statistics.pairs`.
- Asks: `ingredient` or `class` and `level`, `find`, `pass` (a screen), `sort`, `dir`, `offset`.
- Answers: `class`, `counted_on`, `ingredient`, `label`, `matched`, `offset`, `rows`.

### `GET /api/statistics/strata`

One pair's ROR within each value of each part of a case. Not found (404) for a pair the statistics do not name.

- Function: `statistics.strata`.
- Asks: `ingredient` and `reaction`.
- Answers: `cases`, `counted_on`, `ingredient`, `parts`, `reaction`, `term`.

### `GET /api/statistics/group`

A drug's ingredient against a group of reactions counted as one event, on all the cases the statistics count or on those FDA received since a day: the group's table of cases and every statistic `GET /api/statistics` gives, scored under the release's own fitted prior. A case counts once however many of the group's reactions it names. Given one reaction and no day, the answer is that pair's own statistics. A value the table cannot give is null; where the release's prior did not fit, `not_available` gives the reason EBGM, EB05 and EB95 are null. Refused (400) for a combination, which has statistics only for each ingredient.

- Function: `grouped.statistics`.
- Asks: `product`, `reaction` (repeated), `received_from` (`yyyy-mm-dd`, optional). The filters are not read.
- Answers: `cases`, `chi_square`, `chi_square_yates`, `counted`, `counted_on`, `eb05`, `eb95`, `ebgm`, `expected`, `ic`, `ic025`, `ingredient`, `ingredient_cases`, `not_available`, `prr`, `reaction_cases`, `reactions`, `received_from`, `ror`, `ror_lower`, `ror_upper`, `rrr`.

### `GET /api/statistics/quarters`

A drug's statistics as they stood at the end of every quarter, for each event of its statistics or for one group of reactions counted as one event: at each quarter end, the cases received by then (rule `received-day`), scored under the release's own fitted prior, never fitted again, so the newest quarter end is the pair's own statistics. Each event's `series` starts at the first quarter end with a case of the pair and holds every calendar quarter from there to the release's newest, one row of `columns` each: the quarter (`qnum`, as `20262` for 2026q2), then `cases`, `ebgm`, `eb05`, `prr`, `chi_square_yates`, `ror`, `ror_lower` and `ic025`. A value the table cannot give is null. Given screens, each event also says whether it met any one of them at each quarter end (`past`, every condition of a screen holding, an empty value meeting none) and the first quarter of the unbroken stretch that reaches the newest (`since`, null when it is not past at the newest). Given `rising`, each event says whether that statistic at the newest quarter end is higher than it was the number of quarter ends before that rule `trend-rising` gives (`rising`, null where either value is empty or the pair is newer than that, never false). For a group, its one event has no `pt` or `term` and `reactions` names it. Given `by=event`, each case is placed by the date the reaction started (`event_dt_T`, FDA's full dates only) rather than the day FDA received it: every margin of the table is then the cases dated by each quarter end, the series can start before FDA's first file and the newest quarter end is no longer the pair's own statistics; a case with no such date is at no quarter end, and each event says how many of its cases that leaves out (`undated`). The cases counted, the strata and the prior are the same. `by` says which date was counted by. Refused (400) for a combination, a screen that cannot be read or that names a statistic the series does not give, a `rising` that is not one of its statistics, and a `by` that is neither; not found (404) for a release built before the counts by quarter.

- Function: `quarterly.series`.
- Asks: `product`, `reaction` (repeated, optional: one group), `screen` (repeated, optional: each a JSON list of conditions, as `[{"column": "eb05", "at_least": 2}, {"column": "cases", "at_least": 3}]`), `rising` (optional: one of the statistics), `by` (optional: `received`, the default, or `event`). The filters are not read.
- Answers: `by`, `columns`, `counted_on`, `events`, `ingredient`, `not_available`, `reactions`, `rising`.

### `GET /api/events/statistics`

A drug's statistics with each of its events, for the whole release, as the build worked them out: the columns a drug's events table shows and its thresholds read, as `columns` then `rows`. No filter, window or setting of how the drug is counted changes them. Refused (400) for a combination, and not found (404) for FDA's spelling with no ingredient.

- Function: `eventstats.statistics_of`.
- Asks: `product`. The filters are not read.
- Answers: `columns`, `counted_on`, `ingredient`, `not_available`, `rows`.

### `GET /api/events/prior-quarter`

Each event of a drug's statistics with its EBGM and EB05 at the end of the quarter before the release's newest, scored as `GET /api/statistics/quarters` scores it, but for that one quarter end, so it comes in seconds. Empty for an event with no case by then; no rows for a release of one quarter. Refused as `GET /api/events/statistics` is.

- Function: `quarterly.prior_quarter`.
- Asks: `product`. The filters are not read.
- Answers: `columns`, `counted_on`, `ingredient`, `not_available`, `quarter`, `rows`.

### `GET /api/events/facts`

The plain facts about a product's cases for each of its events, from the release and the rules `age-groups`, `pregnancy-cases`, `not-a-medical-event`, `treated-condition` and `indication-match`: the shares of the cases giving an age that are older or children, against the product's own; the cases naming a pregnancy term; whether the term is a medical event at all; whether the label says the event is the condition the product treats; and for such an event, the share whose reported indication is the event. A fact the release cannot give is null, with a plain reason beside it under `why`, never 0 or false. The pregnancy, medical event and indication facts come from MedDRA's licensed part and are null, with the reason, for a viewer without MedDRA. Refused (400) for no product, or when a rule names an age band, an SMQ or a term the release's MedDRA version does not hold.

A fact the release cannot give is null, with the reason in the event's `why`. `not_medical` reads a public list of terms and a licensed list of MedDRA groups: without the licensed list, because the viewer has no MedDRA or the release holds none, only a term on the public list is marked, any other is null, and `why` says so. A name the MedDRA version does not hold makes only that fact null, naming the rule; it never refuses the question.

- Function: `eventfacts.facts`.
- Asks: `product`, `unit`, `event` (repeated; the most reported events when none) and the filters.
- Answers: `counted_on`, `drug`, `events`, `product`.

### `GET /api/breakdowns`

A drug and event pair's cases broken down one field at a time, in the order of rule `breakdown-lines`: for each field, each value's cases and its share among only the reports that give the field, in the window and before it, the change in points, and how many of the reports give the field (rule `breakdown-lines` says what each field reads; rule `rechallenge-correction` how dechallenge and rechallenge are read). The cases are the ones `/api/events` counts for the event under the same settings and filters, each counted once however many of the group's reactions it names, and placed in a period by the day a case is dated by (rule `received-day`). The window is `received_from` to `received_to`, by default the release's newest quarters (`default_window_quarters`) to its end; before it is `before_from` to `before_to`, by default every day before the window. A question that names its window by the day the event began (`event_from`, `event_to`) and no received day places each case by its full event date instead, as the event date filter reads it; a case with none is in neither period.

Each line has its `field`, `name` and `group`; for each period (`before`, `window`) its `cases`, the reports that give the field (`given`) and their share (`given_share`; null for Pregnancy, which FAERS has no field for); and its `values`. Each value has `value` (FDA's code, a band id, a number of days, `cites` for a report that cites an article, `serious` for a report with any serious outcome (rule `serious-outcomes`), once however many it gives, or `_none` for no serious outcome given, no other drug and no article cited), `name` where the page cannot name it from a code (an indication, an other drug), its `cases` and `share` in each period, `change`, the p-value of its chance test (`p`, rule `chance-test`) and whether it rose (`rose`, rule `breakdown-rose`). A share is null, never 0, in a period where no report gives the field, and so are the change, `p` and `rose`. Each line also gives the value it shows (`shown`, chosen by the field's `pick` in rule `breakdown-lines`): the `pick`, the `value` (a value of the field, or the name of those it gathers: `children`, `older`, `health_professionals`, `lawyers`, a strength such as `100 mg`), the line's `values` it counts, each case once, its `cases` and `share` in each period (for Time to onset, `cases` and the median `days`), `change` (for Time to onset, in days), `p` and `rose`; `shown` is null where the line shows nothing. `alarm` says whether the shown value's change reaches the points and its chance test passes (rule `breakdown-alarm`), null where there is nothing to compare. Each line names the filter that picks its values' cases (`filter`, a parameter of [the filters](#the-filters): `outcome`, `age`, `sex`, `indication`, `onset`, `dechal`, `rechal`, `prole`, `dose`, `other_drug`, `reporter`, `country` or `report_type`), each of its values a value of that filter, `serious` aside (the codes of rule `serious-outcomes`), and Drug role's `prole` picking by the roles the product is counted in; `filter` is null for Pregnancy, Literature, Key details and Duplicates. Time to onset also gives its days in rule `breakdown-lines`' `onset_bands` (`bands`): each band's `value` (its `onset` filter value, `2-7`), `name`, `cases` and `share` in each period, `change`, `p` and `rose`. A line the release or this viewer cannot give has no values and is named under `not_available` with the reason: Pregnancy without MedDRA's licensed part, and Literature where the release's explorer database was built without FDA's literature reference. On the Literature line, a report from FDA's files before they held the field does not give it, so it is never counted as `_none` (rule `literature-reference`). Refused (400) for no product, no event, a day not written yyyy-mm-dd, a period that ends before it starts, a before that does not end before the window starts, `points` that is not a positive number, `fall` that is not 0 or 1, a `strength` that cannot be read or strengths in different measures (rule `dose-strength` says what each unit measures, in its `measures`), or a rule the breakdowns cannot read.

- Function: `breakdowns.breakdowns`.
- Asks: `product`, `unit`, `prole`, `include`, `exclude`, `dedup`, `reaction` (repeated), `received_from`, `received_to` (or `event_from`, `event_to`), `before_from`, `before_to`, `points` (optional: the alarm's points, else rule `breakdown-alarm`'s), `fall` (optional: 1 counts a fall as a rise does, 0 counts rises only; else the rule's `fall_counts`), `strength` (repeated, optional: the product's strengths, such as `40 mg`, rule `dose-strength`) and the filters. `points`, `fall` and `strength` change only the values shown and the alarms, never a count.
- Answers: `before`, `cases`, `cases_query`, `counted_on`, `groups`, `lines`, `not_available`, `product`, `reactions`, `window`.
- Each count carries the question that lists its cases: `cases_query` for `cases` in each period; in each line's period, `cases_query` for its `cases` and `given_query` for `given` (null where `given` is); and in each value's and each band's period, `cases_query`.

### `GET /api/labels/product`

The labels a product's reports are read against, and each of its reactions' flag; nothing where the release holds no label flags.

- Function: `api.label_product`.
- Asks: `product`, `unit` and the filters.
- Answers: `counted_on`, `labels`, `reactions`.

### `GET /api/labels/cases`

A product's cases under each Label status.

- Function: `api.label_counts`.
- Asks: `product`, `unit` and the filters.
- Answers: `cases`, `counted_on`.

### `GET /api/labels/query`

A group of reactions read against a drug's label: each reaction reported with the drug, with its flag, how many the label lists, and how many of the group were never reported with the drug (`not_compared`, named in `never_reported`). Nothing where the release holds no label flags.

- Function: `labelquery.label_query`.
- Asks: `product`, `unit`, `reaction` (repeated) and the filters.
- Answers: `counted_on`, `drug`, `listed`, `never_reported`, `not_compared`, `reactions`.

### `GET /api/labels/case/{era}/{key}`

One case's suspect drugs, each with its flag for each reaction and its label.

- Function: `api.label_case`.
- Asks: `era` and `key`, in the address.
- Answers: `counted_on`, `drugs`.

### `GET /api/schema`

Every table and view of the release a viewer may query with SQL, with its columns, rows and size: a list. MedDRA's licensed tables, which a viewer who may see them can query too, are not listed.

- Function: none: asked over HTTP only.
- Asks: nothing.
- Answers: `bytes`, `columns`, `group`, `name`, `rows`, `view`.

### `GET /api/manifest`

The release's manifest as the Tables page shows it: its quarters, size, funnel, tables and views.

- Function: none: asked over HTTP only.
- Asks: nothing.
- Answers: `built_at`, `counted_on`, `funnel`, `quarters`, `release`, `release_bytes`, `tables`, `views`.

### `POST /api/sql`

One page of a read-only SQL query's result, and how long it ran (`seconds`). It queries the release's tables and views and, for a viewer who may see MedDRA's licensed part, the tables of its MedDRA version too (such as `reac_meddra_T` and `meddra_pt`), within [rule sql-limits](https://github.com/Altio-AI/open-altio/blob/main/rules/sql-limits.md). Only one `SELECT` runs; any statement that would change the release is refused (400) and nothing is written.

- Function: none: asked over HTTP only.
- Asks: a JSON body: `sql` and `page`.
- Answers: `columns`, `counted_on`, `page`, `rows`, `seconds`, `size`, `total`.

### `GET /api/downloads`

Where the release's whole tables are, and the limits of a CSV file and a SQL result's download.

- Function: `downloads.tables_here`.
- Asks: nothing.
- Answers: `counted_on`, `csv_row_cap`, `on`, `release`, `sql_download_rows`, `why`.

### `GET /api/export`

A filtered export: a zip of the matching cases, their drugs and their reactions, with a manifest of the question it answers.

- Function: none: asked over HTTP only.
- Asks: the filters and `format` (`csv` or `parquet`).
- Answers: a file.

### `POST /api/sql/download`

A SQL query's whole result as a file.

- Function: none: asked over HTTP only.
- Asks: a JSON body: `sql` and `format`.
- Answers: a file.
