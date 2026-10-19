# Rules

Every choice Open Altio makes about the data, and every limit of the explorer, is written here, one file per rule. The code reads its values from these files, so what a rule says and what the code does cannot drift apart.

## Reading a rule file

A rule file has two parts.

**The front-matter,** between the two `---` lines at the top, is what the code reads:

- `rule`: the rule's name, the file name without `.md`.
- `values`: its values. The text below names each one in `code style`.
- `enforced_in`: the code that applies the rule and the tests that check it, or `not yet built`.

A data rule, one that shapes the release, also has:

- `line`: one plain sentence, shown under its name on the methods page.
- `settable`: the values you may set for your own releases, each with a plain label (and, for a choice, its options).
- `always_on: true` and `why_locked`: for a rule the build cannot run without.

**The text.** The heading is the rule's name. The first paragraph says what it does and why, in plain words; the methods page shows it when the rule is opened. The paragraphs after it give the exact rule, and **Why** gives the evidence, usually a notebook in `notebooks/faers/` you can run yourself.

[`steps.yaml`](steps.yaml) lists the steps a release is built in and the data rules that act in each, in order.

## Changing a rule for your own releases

The data rules below are Altio's standard. To build releases your own way, open the methods page of your local explorer (`open-altio serve`), switch rules off or change their values, and rebuild. Your choices are saved as `rules.toml` beside the release; `open-altio build` reads the `rules.toml` in the folder it runs in. The file lists every data rule, with Altio's standard values as comments and only your own choices written out:

```toml
# Same manufacturer case number
# A company's report sent twice under one case number counts once.
[dup-manufacturer-number]
on = true
# Skip when the ages differ by more than (years)
max_age_gap_years = 5    # yours; Altio standard: 2
# Skip when the cases disagree on sex: ["M", "F"] (Yes) or [] (No)
# clashing_sexes = ["M", "F"]    # Altio standard; remove the first # to change
```

- `on = false` switches a rule off. WHO's drug classes have one switch for their five rules, `[atc-index]`: off, the release is built without them. Three rules are always on, because the build cannot run without them: FDA's values kept as published, the latest version of each case, and which copy of a group of duplicates is shown. Not given is always on, so every screen reads one empty state. The rules that read a patient's sex, age, weight and age band are always on too: they add a value beside FDA's own, which the later steps read. So are the statistics' rules: they take no case out, and the thresholds a pair is read against are set on the Statistics tab, not here.
- A value you leave alone, behind its `#`, follows Altio's standard, including later changes to it.
- Only the values a rule lists under `settable` can be set. The rest are part of how the rule works; to change one, propose a change to the rule.
- A file naming a rule or a value that does not exist, a value of the wrong kind, or an always-on rule switched off, is refused before anything is built, with the reason in plain words.

A release built with your rules records how they differ from the standard, under `user_rules` in its `manifest.json` and `methods.json`: the rules off, and each value changed, from what to what. The explorer shows it ("Your rules: 2 off, 1 changed", with the list). A release built without a rules file records none.

## Proposing a change to a rule

To change a rule for everyone, open an issue with the "Propose a rule change" form: what the rule should say, and the evidence, such as the counts from a release built with your own `rules.toml`. A rule changes in one pull request holding its file, the code that applies it and its test; a change to which cases are kept also adds a CHANGELOG entry with the counts before and after.

## For code

Code reads a value only through the rulebook, `rulebook.value("sql-limits", "timeout_seconds")`, and asks whether a data rule acts with `rulebook.is_on("deleted-cases")`. A build runs under a person's choices with `rulebook.use_user_rules(...)`. `tests/test_rules.py` fails when a file here is malformed or missing from the lists below, when it names code that does not exist or does not read it, or when code that reads a rule types in one of its distinctive values (a number of 100 or more, an email address) instead of reading it.

## Data rules, in the order the build applies them

| Rule | What it does |
|---|---|
| [transformed-suffix-T](transformed-suffix-T.md) | FDA's values kept as published; everything we derive ends in `_T`. Always on |
| [not-given](not-given.md) | A value that is blank, says unknown or is a filler number reads Not given, FDA's own beside it. Always on |
| [overlong-lines](overlong-lines.md) | Two reports run together on one line are split back apart |
| [sex-codes](sex-codes.md) | A patient's sex is F or M, else not known. Always on |
| [age-in-years](age-in-years.md) | Ages read in years, exactly, from every unit; an age with no unit is in years; negative or over 122 is no age. Always on |
| [weight-in-kg](weight-in-kg.md) | Weights read in kilograms; no unit, an unknown unit, zero or over 635 kg is no weight. Always on |
| [age-bands](age-bands.md) | Each case's age band, the same for the explorer's filter and the statistics; a child given as 0 years goes by FDA's age group. Always on |
| [latest-version](latest-version.md) | Each case counts once, at its newest version, across AERS and FAERS. Always on |
| [deleted-cases](deleted-cases.md) | Cases FDA has withdrawn are taken out, in both eras |
| [dedup-default](dedup-default.md) | Cases with the same event date, age, sex, country, drugs and reactions count once (AEOLUS) |
| [dup-manufacturer-number](dup-manufacturer-number.md) | A company's report sent twice under one case number counts once, with a sex and an age guard |
| [dup-padded-event-dates](dup-padded-event-dates.md) | In large groups from one company, a 1 January date does not make cases match |
| [dup-shown-copy](dup-shown-copy.md) | Each group of duplicates shows the copy FDA received last, dated by its first receipt. Always on |
| [legacy-country](legacy-country.md) | Old country names are read as country codes |
| [country-not-given](country-not-given.md) | `COUNTRY NOT SPECIFIED` and `A1` are no country |
| [eu-member-state](eu-member-state.md) | A case naming only the EU takes its member state from an earlier version of the same case |
| [reaction-term-case](reaction-term-case.md) | Reactions match whatever their capital letters |
| [no-drug-or-reaction](no-drug-or-reaction.md) | Reports with no usable drug or reaction stay in view, marked |
| [company-names](company-names.md) | A company's spellings as a sender count under one company name; FDA's sender is kept |
| [drug-route](drug-route.md) | Each drug record gets the route families it could be in, from FDA's route, dose form and drug name; labels match on overlap |
| [event-date-precision](event-date-precision.md) | An event date FDA padded to the 1st is known only to its month, or to its year on 1 January |
| [date-limits](date-limits.md) | An event or therapy date after its own quarter, or long before the patient was born, gets no clean value |
| [time-to-onset](time-to-onset.md) | Days from a drug's first dose to the event, only from two dates known to the day |
| [therapy-duration](therapy-duration.md) | Each therapy's duration in days, from its two dates, else from FDA's duration and unit |
| [reporter-type](reporter-type.md) | FDA's reporter codes are read as the E2B(R3) reporter qualification, so OT and HP count as one |
| [drug-names](drug-names.md) | Each drug is read to its ingredients through the DiAna dictionary and our reviewed corrections; nothing is taken out |
| [rxnorm-ingredients](rxnorm-ingredients.md) | Each drug record carries the RxNorm code of its drug, from FDA's drug name first, then FDA's active ingredient, then its ingredient; a salt known only as its element gets none; nothing is guessed |
| [legacy-term-spelling](legacy-term-spelling.md) | Old terms written in capitals are shown in MedDRA's spelling, taken from FAERS's own text |
| [meddra-terms](meddra-terms.md) | With MedDRA, every reaction counts under its current PT for everyone; the text to PT link is shown to MedDRA subscribers. Always on |
| [statistics-cases](statistics-cases.md) | Every statistic counts the kept cases that name a suspect ingredient and a reaction. Always on |
| [ebgm](ebgm.md) | EBGM, EB05 and EB95, under a prior fitted on the release's own cases; default threshold EB05 at least 2, at least 3 cases. Always on |
| [prr](prr.md) | PRR with both chi-squares; Evans 2001: PRR at least 2, Yates chi-square at least 4, at least 3 cases. Always on |
| [ror](ror.md) | ROR with its 95% interval; lower bound above 1, at least 3 cases. Always on |
| [rrr](rrr.md) | RRR, cases over the crude expected count; no preset. Always on |
| [ic](ic.md) | IC with IC025, shrunk by a half case; IC025 above 0. Always on |
| [ror-strata](ror-strata.md) | Each pair's ROR within each age band and within each sex. Always on |
| [label-dictionary](label-dictionary.md) | Each FDA label is read once and the reactions it names are coded to MedDRA terms |
| [label-negation](label-negation.md) | A reaction the label says did not happen is not on the label |
| [label-population](label-population.md) | A condition that says who the patients are, or who must not take the drug, is not a reaction on the label |
| [label-table-rows](label-table-rows.md) | A reaction only the placebo or comparator group had in a label's table is not on the label |
| [label-umbrella](label-umbrella.md) | A label's umbrella term covers the milder reactions under it |
| [label-treated-disease](label-treated-disease.md) | A reported reaction that is the disease the drug treats is flagged as such |
| [label-not-a-medical-event](label-not-a-medical-event.md) | Reports of a drug not working, used wrongly or off label, or of exposure alone are not medical events |
| [label-procedure](label-procedure.md) | A reported term that names a procedure is flagged as a procedure |
| [label-flags](label-flags.md) | Each drug and reaction gets one flag: listed, possibly listed or not listed on its label, or not compared |
| [label-groups](label-groups.md) | The MedDRA groups the label rules read come from a file you make from your own MedDRA release |
| [label-source](label-source.md) | FDA's drug labels come from DailyMed's monthly release of prescription labels, keyed through RxNorm. Acts when a build is given a labels folder; switching off any of the three leaves labels out |
| [label-choice](label-choice.md) | Each ingredient or combination gets its originator's current label for each route family, with no default label. Acts when a build is given a labels folder; switching off any of the three leaves labels out |
| [label-sections](label-sections.md) | A label's safety sections and indications are read by their codes, as lines of text. Acts when a build is given a labels folder; switching off any of the three leaves labels out |
| [label-own-ingredients](label-own-ingredients.md) | A label DailyMed's mapping file leaves without an RxNorm code is keyed by the active ingredients it lists itself, where nothing else gives that ingredient a label. Acts when a build is given a labels folder |

## Drug classes

WHO's ATC class for each drug record, built after the drug-name step as a layer of tables of its own, with the statistics of each class. It takes no case out and changes no other table. The five rules have one switch, atc-index's: off, the release is built without the classes; none of the other four is switched alone.

| Rule | What it says |
|---|---|
| [atc-index](atc-index.md) | Drug classes are WHO's ATC codes and names from one index year for every quarter, read from our table by substance, else by FDA's own words, as a layer of their own; counted in cases |
| [atc-spelling-bridges](atc-spelling-bridges.md) | A reviewed list joins WHO's words to the substance dictionary's spellings |
| [atc-group-classes](atc-group-classes.md) | A group word the dictionary writes for many products gets WHO's class for the group, marked as a group class |
| [atc-class-choice](atc-class-choice.md) | One WHO class per drug record, chosen by its dose, route or indication, else the broadest class its possible codes share, or "can't tell"; every possible class kept |
| [statistics-classes](statistics-classes.md) | EBGM, PRR, ROR, RRR and IC for each WHO class and reaction at levels 2, 3 and 4, each level with its own EBGM prior, on the ingredient statistics' cases |

## Limits of the explorer and the command

These set how the explorer, the commands and MedDRA's licensed part behave, and how a release's labels are kept current, not how a release is built; a rules file does not change them.

| Rule | What it says |
|---|---|
| [era-filter](era-filter.md) | Era is and/or, not either/or |
| [explorer-build-memory](explorer-build-memory.md) | The explorer database builds within the service's box |
| [explorer-read-memory](explorer-read-memory.md) | The explorer reads within the service's box |
| [explorer-drug-counts](explorer-drug-counts.md) | A drug counts by its ingredient, in any product containing it, as primary or secondary suspect; each role a tick box |
| [explorer-field-notes](explorer-field-notes.md) | A note under a field's chart and beside its filter where FDA's own files changed |
| [explorer-label-flags](explorer-label-flags.md) | How the screens show the label flags: every flag from the start, Unexpected only one click |
| [explorer-label-names](explorer-label-names.md) | A label is named by its product, its ingredients and its date; its forms only where the drug's labels differ by form |
| [explorer-label-words](explorer-label-words.md) | The flags speak of listing only: Listed, Possibly listed, Not listed, Can't tell, or Not compared with its reason |
| [explorer-lists](explorer-lists.md) | How long the explorer's searches and short lists are |
| [explorer-page-size](explorer-page-size.md) | The explorer lists 50 cases a page |
| [export-csv-row-cap](export-csv-row-cap.md) | CSV exports stop at Excel's row limit |
| [filtered-vs-full-export](filtered-vs-full-export.md) | A filtered export can never be mistaken for the full data |
| [label-refresh](label-refresh.md) | Between releases, a release's labels are brought up to date from DailyMed's daily update files, choosing again only where a label changed, and switched in only when whole |
| [improve-this](improve-this.md) | Improve this sends only the note, from the browser, to Altio's improvements board; a note that cannot go yet waits on this machine |
| [machine-needs](machine-needs.md) | The memory and free disk `open-altio doctor` checks for |
| [meddra-version](meddra-version.md) | One MedDRA version per release, the newest when it is built |
| [sql-limits](sql-limits.md) | SQL is read-only DuckDB with hard limits |
| [sql-result-download](sql-result-download.md) | A SQL result downloads whole up to 2,000,000 rows |

## The label review

These set how the label phrases the fixed rules leave uncertain are coded by an agent and checked by one reviewer, and how the fixed rules' own accuracy is measured. They shape no release by themselves: the comparison rules read the frozen codings.

| Rule | What it says |
|---|---|
| [label-agent](label-agent.md) | Any agent codes what the label rules leave uncertain, file in and file out, with retries; terms are checked against MedDRA; a blank or refused item counts as a disagreement |
| [label-coding](label-coding.md) | One coding question for each uncertain label phrase: the MedDRA preferred terms it states as a reaction, or a reason for none |
| [label-review](label-review.md) | One reviewer codes uncertain label phrases in batches of 100, then 100 more each time, picked as a mix; patterns, the blind redo and freezing |
| [label-review-gates](label-review-gates.md) | A bigger batch starts only when every item is decided, "other" is under 1% and the agent named the same terms on every item |
| [label-rule-check](label-rule-check.md) | A seeded random sample of rule-decided flags is checked by hand, to publish each outcome's error rate with a Wilson range |
