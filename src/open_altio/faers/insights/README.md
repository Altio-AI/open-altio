# Insights

The code that turns the notebooks' findings (`notebooks/faers/`) into the methods page's data. Every chart on the methods page is computed by a function here, so it is reproducible from code, and every insight card is tagged either "Changed our pipeline" (with the funnel step it links to and the rules it is the evidence for) or "Documented, not transformed".

```
src/open_altio/faers/insights/
  source.py             connect(): a release folder for the notebooks, its raw tables also as demo_all, drug_all, ...
  cards/__init__.py     CARDS (page order), compute_cards(con, ids=None)
  cards/publishing.py   the cards of notebooks 00, 01 and 90: how FDA publishes FAERS, what reporting changed
  cards/versions.py     the cards of notebook 02: case versions, and the gaps between AERS and FAERS
  cards/empty_fields.py the cards of notebook 03: empty fields, how FDA's files and senders write unknown
  cards/duplicates.py   the cards of notebook 04: duplicates
  cards/drug_names.py   the cards of notebook 05: drug names, plain about it when a release has none
  cards/meddra.py       the cards of notebook 06: MedDRA versions, plain about it when a release has none
  cards/demographics.py the cards of notebook 07: how FDA writes sex, age and country
  cards/dates_codes.py the cards of notebook 08: dates and codes
  cards/drug_classes.py the cards of notebook 09: WHO drug classes
  cards/rule_charts.py the charts of the rules no notebook measured, and each statistic's spread
  cards/common.py      what every card is made of: its query, chart, tag and the words for its numbers
  cards/notebook.py    the notebooks' shared chart look, plot_card() and write_cards()
  steps.yaml           step card text per funnel step id: exact rule, code file and anchor (title and line: rules/steps.yaml)
  limits.yaml          "What we do not do"
  lines.yaml           an opened card's Shows / Why it matters / What we did, filled where the page is served
  methods.py           build_methods(): methods.json for a release; validate()
  numbers.py           the numbers the methods story shows and every rule's version, added to a written release by write()
  methods.schema.json  the shape of methods.json (the methods page draws only from it)
```

## The notebooks

The notebooks live in `notebooks/faers/`; how to run them is in `notebooks/README.md`. Each notebook ends with a "Methods-page cards" section that calls the same card functions the release build calls: 00 computes the deleted-list and dechal/rechal cards, 01 the country card, 02 its three cards (on the release it reads as "after"), 03 its four empty-field cards, 04 its five cards, 05 its three drug-name cards, 06 its three MedDRA cards, 07 its three demographics cards, 08 its six dates and codes cards, 90 the sender names card.

## The cards

**What becomes a card.** A finding goes under "What we found" only if it passes all three tests:

1. It is about FDA's data, not our code or process. Our own slips go in the changelog.
2. It matters to someone using FAERS: it moves a count they would get, or would mislead them if they were not told, and its size makes it matter.
3. It is measured on the release, not a theory.

Each card is tagged "Changed our pipeline: step N" or "Documented, not transformed". A "Changed our pipeline" card also names the rules it is the evidence for (files in `rules/`), so the methods page shows it under them; `validate()` refuses a rule name with no file. Every step that removes cases has at least one card as its "Why this step" (`validate()` refuses a release without one); a step that removes nothing needs none. Options weighed and rejected, comparisons of methods and small technical fixes stay in the rule files, the notebooks and the step's exact rule.

| Card id | Finding | Tag |
|---|---|---|
| `carried_cases_counted_twice` | AERS cases FDA carried into FAERS had a latest version in each era | Changed our pipeline: `latest_versions`, for `latest-version` |
| `deleted_lists_unpublished` | FDA's deleted-case lists name far more case ids than ever reached a published file, AERS or FAERS | Changed our pipeline: `after_deleted_lists`, for `deleted-cases` |
| `deleted_lists_name_aers_cases` | The lists also name AERS cases, half of them direct reports sent electronically in 2011 | Changed our pipeline: `after_deleted_lists`, for `deleted-cases` |
| `eras_write_countries_and_terms_differently` | AERS writes country names and capital terms, FAERS codes and mixed case, so duplicates never matched across eras | Changed our pipeline: `kept_after_duplicates`, for `legacy-country`, `reaction-term-case` |
| `same_event_several_cases` | One event reaches FAERS as two or more cases, from a second company, a direct report or one company under two numbers; the later copy more often lists more reactions | Changed our pipeline: `kept_after_duplicates`, for `dedup-default` |
| `one_case_two_numbers` | Companies sent some cases twice under two FDA case numbers, mostly before 2012; some numbers cover different patients | Changed our pipeline: `kept_after_duplicates`, for `dup-manufacturer-number` |
| `padded_dates_join_different_patients` | Padded or partial event dates make large one-company groups look like one patient | Changed our pipeline: `kept_after_duplicates`, for `dup-padded-event-dates` |
| `event_dates_padded` | Since 2021Q3 FDA writes an event date known only to its month as the 1st, as legacy AERS did | Changed our pipeline: `dates`, for `event-date-precision` |
| `padding_puts_reactions_before_drug` | Padded event dates make reactions look as if they came before the drug | Changed our pipeline: `dates`, for `time-to-onset` |
| `occupation_code_changes` | FDA renamed the other health professional code from OT to HP in 2020 | Changed our pipeline: `codes`, for `reporter-type` |
| `one_medicine_many_spellings` | One medicine is written hundreds of ways; a search for its brand misses its other names and every biosimilar | Changed our pipeline: `drug_names`, for `drug-names` |
| `background_drugs_counted_every_role` | Counted in every role, a medicine patients take alongside the suspect one has many times its suspect cases | Changed our pipeline: `drug_names`, for `drug-names` |
| `brand_changes_ingredient` | A brand can change ingredient: Zantac was ranitidine, Zantac 360 is famotidine | Changed our pipeline: `drug_names`, for `drug-names` |
| `unknown_written_two_ways` | A missing route is written blank or UNKNOWN, and FDA's 2026 files turned UNKNOWN into blank | Changed our pipeline: `report_versions`, for `not-given` |
| `to_mfr_filler_on_company_reports` | to_mfr means something only on direct reports; on company reports it is a filler N in 2014Q1 to 2015Q3 | Changed our pipeline: `report_versions`, for `not-given` |
| `who_reported_lost_on_company_reports` | From 2025Q3 FDA's files stop saying who reported on company reports; direct reports keep it | Changed our pipeline: `report_versions`, for `not-given`, `explorer-field-notes` |
| `completeness_depends_on_sender` | How many of age, sex and event date a case gives depends on the company that sent it | Changed our pipeline: `report_versions`, for `not-given` |
| `rechal_filler` | Rechallenge filled in with D 2012Q4 to 2015Q3, dechallenge near empty | Changed our pipeline: `report_versions`, for `not-given` |
| `older_meddra_terms_missed` | Older reports carry reaction terms MedDRA has since demoted or renamed, which a search on today's term misses | Changed our pipeline: `meddra_terms`, for `meddra-terms` |
| `quarterly_files_keep_their_meddra_version` | Each quarterly file keeps the MedDRA version FDA built it in, so older quarters hold more old terms | Changed our pipeline: `meddra_terms`, for `meddra-version`, `meddra-terms` |
| `sender_names_unstable` | Sender names standardised, then split across two spellings from 2024Q4 | Documented |
| `rept_cod_combination_products` | 30-day reports are device malfunctions on combination products, not expedited reports | Documented |
| `no_outcome_not_non_serious` | A case with no outcome is not non-serious: some expedited reports give none | Documented |
| `drug_seq_repeated` | From 2024Q4 one drug can fill several rows under one drug sequence number | Documented |
| `country_empty_rising` | Country of the event empty more often since 2022 | Documented |
| `european_union_for_member_state` | Since 2025Q3 about one case in ten names the European Union, not a member state; an earlier version gives the state back for about one in seven | Documented |
| `sex_not_specified_for_empty` | NS written where the sex was empty, 2013Q1 to 2014Q2 | Documented |
| `ages_without_a_unit` | Ages with no unit, and why they are in years | Documented |
| `duplicate_check_needs_fields` | Most cases leave blank a field that duplicate matching needs, a rising share | Documented |
| `no_adverse_event_serious_outcome` | Reports of "no adverse event" that record a death or a hospitalisation | Documented |
| `unknown_indication_placeholder` | A third of indication rows give no reason for the drug | Documented |
| `aspirin_dose_tells_the_use` | Most aspirin reports that state a dose give the low dose of a blood thinner, not a painkiller's | Documented: the evidence for `atc-class-choice`, whose drug classes are a layer, not a funnel step |
| `two_use_drug_use_not_said` | FAERS ever more often does not say which use a drug WHO codes for two uses had | Documented: the evidence for `atc-class-choice`, whose drug classes are a layer, not a funnel step |

A card is tagged "Changed our pipeline" only when a funnel step acts on it. A new step that acts on a documented finding (sender names, say) changes that card's tag to the step's id in the same change.

A chart may carry the question it answers (`question`, shown above it) and a `note` labelling the x value that matters.

A new card: a function in the `cards/` module of its notebook, returning the card dictionary (see `cards/__init__.py`), added to `CARDS`, and a call in its notebook. Cards read only derived `_T` tables, so they run on a release and on the release build's own connection; the MedDRA cards also read the licensed mapping tables, which the connection holds only when the release is built with MedDRA (or a notebook read MedDRA's files), and without them say so, with no data. A card whose table or column is missing shows no data (with a `MissingDataWarning`) rather than stopping the build.

## methods.json

Every release carries `methods.json`, named in its manifest under `methods` and written by `src/open_altio/faers/release.py` through `open_altio.faers.insights.methods.build_methods`. It holds:

- `release`, and `code` (repository, package version, and the git commit every code link points at: `OPEN_ALTIO_CODE_REF`, else the checked-out commit, else `v<version>`)
- `funnel`: the steps of `funnel.json` with their counts per era, and the deleted-list totals
- `steps`: one card per funnel step in order: number, title and sentence (from `rules/steps.yaml`), before and after counts, removed, the exact rule, a GitHub link to the line implementing it, and the ids of the insights that motivated it (taken from the insight tags)
- `insights`: the cards above, computed on the release's own data, each with its tag and label
- `limits`: what we do not do, filled with `numbers` and the funnel's duplicate counts whenever the numbers are written (`numbers.write`, which the label step runs again once it has flagged the release), so every count in them is over the cases the release shows; a limit that `needs` a part of the release appears only when the numbers have it
- `classes`: the drug classes layer, as the manifest records it: whether the release carries it, the index year and WHO's citation to show wherever a class is shown, and the cases it covers, or why it is absent
- `changelog`: a placeholder entry, written when a person publishes the release
- `user_rules`: how the rules the release was built with differ from Altio's standard (`off`, and `changed` with each value's standard and the one used); both empty for a release built without a `rules.toml`
- `numbers`: the numbers the methods story shows that the rest of the release does not carry (`numbers.py`), counted over the cases the release shows and their drug and reaction rows: event dates as written and as read, ages by unit and in years, reporter codes and the types they read to, routes that read Not given and their families, reaction texts, and, where the release has them, drug names read to ingredients and combinations, counted ignoring capitals (spellings per ingredient, the suspect cases one spelling finds against its ingredient, and the drug records whose name finds none), RxNorm codes of suspect rows and records, the suspect records by the fate each met on the way to a label (once the label step has flagged them), WHO classes (how each row's class was chosen, and suspect cases per main group) and the pairs meeting each statistic's default screen. No words: the page's words are read where it is served. The numbers that need MedDRA's files (the MedDRA terms the reactions read to, and the cases on a term MedDRA has since replaced) are in the licensed manifest instead, under the version's `numbers`. The build adds `numbers` and `rule_versions` last, from the tables the release holds (`numbers.write`); `python -m open_altio.faers methods --release DIR` does the same on a release already built, and MedDRA added later (`build_licensed`) counts them again
- `rule_versions`: every rule by name, with a short hash of its file's front-matter values and its text and its values as the release was built with them, so the next release can say which rules are new or changed

The build refuses a release when a funnel step has no entry in `steps.yaml`, when a step's code anchor is no longer in its file, when a "Changed our pipeline" tag names a step that is not in the funnel, or when any text has an em dash. A new funnel step therefore adds its entry to `steps.yaml` in the same change. The full shape is `methods.schema.json`.

**Every rule has a chart.** Each card carries `rules`, the rules it is a chart for (`RULES_OF` in `cards/__init__.py`), so a rule finds its cards and a card can serve several; every rule of `rules/steps.yaml` has at least one (`tests/faers/insights/test_rule_charts.py`). A rule no notebook measured gets the simplest true chart of what it did in the release (`cards/rule_charts.py`), and a statistic its spread over the release's pairs. Like `numbers`, it counts over the cases the release shows and their drug and therapy records; a card about FDA's columns and lines, the labels read or the label flags' pairs counts those. Such a card keeps the numbers its words quote in `numbers`; its opened lines are in `lines.yaml` and the rules page fills them when it is served (`methods.card_lines`), so they can be reworded without a rebuild. A card that needs MedDRA's licensed files (`LICENSED`) goes in the licensed part, under its version's `insights`, never in the public methods.json.

**Cards without a rebuild.** `python -m open_altio.faers methods --release <folder>` computes the cards again on a built release's own tables (`methods.refresh_cards`), writing them into its methods.json and licensed part, and then adds the numbers (`numbers.write`). The release build and an added MedDRA version end the same way, and the label flags with the cards, so the command writes what a full build writes.
