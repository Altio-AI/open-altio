# Changelog

Changes to the code, newest first. The code follows [semantic versioning](https://semver.org/). Data releases are named by FDA quarter (for example `2026Q2`); each one carries its own funnel numbers and changelog entry in its `methods.json`, shown on How we clean FAERS.

## 1.0.1 (2026-10-22)

DuckDB 2.0 support: four list filters now use DuckDB's `lambda` keyword, which DuckDB 2.0 requires. Every result is the same.

## 1.0.0 (2026-10-19)

The first public release.

### The pipeline

- Loads every quarterly file FDA has published since 2004Q1, legacy AERS and FAERS, exactly as published: every column as text, nothing trimmed or corrected. Column names are unified across the two eras, and only where FDA spelled the same column two ways.
- Keeps one latest version of each case across AERS and FAERS, so a case FDA carried from AERS into FAERS in 2012 counts once.
- Takes out the cases on FDA's deleted-case lists, in both eras.
- Flags probable duplicates by two rules: the AEOLUS rule (the same event date, age, sex, country, drugs and reactions, all filled in) and the same manufacturer case number from the same sender, with guards for a different sex or ages more than two years apart. In large groups from one company, a padded event date (1 January, or a month or year only) does not make cases match. The AEOLUS key never compares a value that reads Not given. Duplicates are flagged, never deleted. Each group shows its latest received copy, dated by the group's earliest receipt.
- Reads legacy country names as ISO codes and compares reaction terms in capitals, so duplicates can be found across the two eras.
- Reads each patient's sex as female or male, else not known; the age in years, exactly, from every unit FDA uses, an age with no unit in years and a negative age or one over 122 years as none; and the weight in kilograms, with none for no unit, zero or over 635 kg. Numbers written `.8` or `60.` are read.
- Places each case in one age band, the same for the explorer's filter and the statistics, splitting the under-2s at 28 days as ICH E11 does; a child given as 0 years goes by FDA's age group.
- Reads `COUNTRY NOT SPECIFIED` and `A1` as no country, and gives a case that names only the European Union the member state an earlier version of the same case named, without changing which cases are duplicates.
- One empty state, **Not given**, everywhere: a field that is blank, says unknown (sex `NS` or `UNK`, `COUNTRY NOT SPECIFIED`, dechallenge `U`, route `UNKNOWN`), holds a filler number (an age of 999, a weight of 0) or was not in FDA's file that quarter. Rechallenge `D` reads Not given in FDA's files from 2012Q4 to 2015Q3, and `to_mfr` on any report that is not direct. The lists are one rule, `rules/not-given.md`.
- Splits a line that holds two records back into them, and records any other overlong line in the manifest instead of cutting it short in silence.
- Keeps reports with no usable drug or reaction visible, and flags those with a serious outcome.
- Reads each drug name to its ingredients through the open DiAna dictionary, with FDA's own active-ingredient field where the name is not in it, so one medicine is counted together whatever the spelling. Combinations keep every ingredient. Our reviewed corrections to the dictionary sit beside it, each with its reason, and every record says where its ingredients came from. No case is removed.
- With a MedDRA release, reads every MedDRA term FDA wrote (reactions, reactions that came back when the drug was given again, and indications) to its current preferred term in that version, through MedDRA's history file for renamed terms, into the release's licensed part. A reaction that matches nothing refuses the MedDRA file as older than the data; indications that match nothing are counted and left as FDA wrote them. A release holds one MedDRA version, the newest when it is built, and reading it to another replaces the one it held.
- Gives each legacy reaction and indication, which AERS wrote in capitals, the spelling FAERS uses for the same term, so it can be shown as MedDRA writes it with FDA's capitals beside it. No MedDRA file is needed, and no case is removed.
- Writes everything it works out into columns and tables whose names end in `_T`, beside FDA's own.

### Companies

- Each case's `company_T` is the company its sender spelling names, in either era, from the reviewed list in `mappings/faers/senders/` (1,113 spellings in 475 companies), so `ELI LILLY AND CO` and `ELI LILLY AND COMPANY` count as Eli Lilly. FAERS's short names `DAIICHI`, `KYOWA` and `SWEDISH ORPHAN` count as Daiichi Sankyo, Kyowa Kirin and Swedish Orphan Biovitrum, since FAERS starts after each firm's merger; AERS names from before a merger stay apart.
- Any other sender is kept as written. A direct report, sent straight to FDA, has no company, nor does a sender that only says unknown or names no company (FDA's intake `FDA-CTU`, a regulator, a hospital, an ID number written as the name, or only generic words such as `PHARMACOVIGILANCE DEPARTMENT`).
- A company is never counted under its owner, nor under its earlier or later name, and a case counts under the sender of its latest version. FDA's `mfr_sndr` is unchanged, and the duplicate rules still compare it (`rules/company-names.md`).

### Statistics

- EBGM with EB05 and EB95, PRR, ROR, RRR and IC for every suspect ingredient and reaction a release's cases name together, EBGM's prior fitted on that release's own cases, on a Statistics tab with the common thresholds as presets you can change. With MedDRA, each reaction is counted under its current preferred term and named by it, also when MedDRA is added to a release already built; without, under FDA's text.
- A release with MedDRA also holds its statistics counted by FDA's text (`statistics_as_published_T`, `statistics_strata_as_published_T`), for a viewer without MedDRA's licensed part.
- Each pair's ROR within each age band and within each sex, in `statistics_strata_T` (rule `ror-strata`), with a sex or age that reads Not given in the unknown group.
- Each ingredient and reaction's time to onset: the median days over its suspect drugs that have one, how many have one, and how many have none by why (`time_to_onset_reason_T` on `drug_onset_T`).
- Statistics for each WHO drug class at ATC levels 2, 3 and 4, on the ingredient statistics' own cases, each level with its own EBGM prior (`rules/statistics-classes.md`). A case counts once for a class however many of its drugs are in it. On the Statistics tab, All cases' list can be by class at any of the three levels, and a drug's rows show its class's EB05 beside its own. `python -m open_altio.faers class-statistics --release <folder>` adds them to a release already built.

### Drug classes

- Each ingredient's WHO ATC class, from WHO's ATC classification index (2026) through a drug-to-class table in `mappings/`, so no WHO file is needed. A class a drug only could be is shown as such and left out of the class statistics.
- On How we clean FAERS, the drug classes are a section of their own: their rules in plain words, their evidence, and one switch for all of them in your own copy. Off, the release is rebuilt without the classes (`rules/atc-index.md`).
- The Drug class filter ticks a class above only when every class under it is ticked and no drug is classed at that class itself. A partly ticked class shows a dash, with a tip saying so.

### Label flags

- Labels come from DailyMed's monthly release of human prescription labels, keyed to each ingredient through DailyMed's RxNorm file and RxNorm's Current Prescribable Content, all from the U.S. National Library of Medicine; `python -m open_altio.faers labels-fetch` downloads them (`rules/label-source.md`).
- For each suspect drug and reaction, whether today's US prescription label on DailyMed lists the reaction, in the words of `rules/explorer-label-words.md`: Listed, Possibly listed, Not listed, Can't tell and Forms differ. A flag not compared with the label (not a medical event, a procedure, the disease it treats, no label found) reads Not compared with its reason (`rules/label-flags.md`).
- Each label is named by its product, its ingredients and its date (`rules/explorer-label-names.md`), and its link opens the version the flags were read from.
- Counting any product containing an ingredient, a drug's page judges every reaction against the ingredient's own label, by each ingredient's RxNorm code in `ingredient_rxnorm_T` (`rules/explorer-label-flags.md`).
- A label that names a group of reactions by one word, such as an injection site reaction, lists the mild reactions under it, but not a serious form: one on EMA's Important Medical Events list for the MedDRA version, when its file is given, or one whose name says it is severe (`rules/label-umbrella.md`).
- Beside a drug with no label found, Request this label opens Improve this with the request written.
- A procedure reads as unexpected in `label_flags_T.expectedness_T`, as Unexpected only counts it. Unexpected only quotes FDA's definition: not listed in the current labeling (21 CFR 314.80).
- `python -m open_altio.faers labels-refresh` keeps a release's labels current from DailyMed's daily update files, switching the new files in only when all are whole (`rules/label-refresh.md`). The screens and exports say which DailyMed day the labels are as of.

### The release

- A release folder holds Parquet tables, `explorer.duckdb`, `views.sql`, `funnel.json`, `methods.json` and `manifest.json`. How we clean FAERS draws from `methods.json`.
- On FDA's files from 2004Q1 to 2026Q2: 24,812,425 report versions as FDA published them; 20,692,690 cases at their latest version; 20,588,529 after FDA's deleted-case lists; 20,296,653 kept after flagging 291,876 probable duplicates.

### Rules

- Every number and policy is a file in `rules/`, read by the code, so the documentation and the behaviour cannot drift apart.
- Change the data rules for your own releases on How we clean FAERS in your own explorer: switch a rule off or set one of its values, then rebuild. Your choices are saved as a `rules.toml` beside the release, which `open-altio build` in that folder reads too, and the release records how it differs from Altio's standard. The three rules the build cannot run without are always on.

### The explorer

- Runs on your own machine for one person, on `127.0.0.1`, with no sign-in and no telemetry.
- Products, reactions, all cases and the case window; charts; Tables and SQL (read only); exports; settings; light and dark.
- Every column marked FDA or Open Altio, with FDA's value beside Open Altio's where they differ.
- Not given reads the same in the filters, the charts, the case window (with FDA's own value beside it) and the clean columns of exports. Each chart of a field that can be empty says how many of its cases give it ("Age given for 62% of these cases") and keeps Not given apart at the bottom.
- A note under a field's chart and beside its filter where FDA's own files changed how it is filled (who reported from 2025Q3; route and dose form from 2026Q1; dechallenge and rechallenge from 2012Q4 to 2016Q2), while the dates chosen take in those quarters (`rules/explorer-field-notes.md`).
- Sex is female, male or not given in every filter and count; the case window shows the age in years with its age band and the weight in kilograms beside FDA's values, and an impossible one as not given. `EU` is named "European Union, member state not given", and a member state taken from an earlier version of the case says so.
- Companies: a chart of the companies that sent the most cases, with the direct reports as one bar, Sent straight to FDA. The Company filter finds a company by its name or any of FDA's spellings of it. The case window shows the company with FDA's sender beside it, and exports carry `company_T` beside `mfr_sndr`.
- How we clean FAERS, at `/methods`: the journey from FDA's files to the cases you see, every rule with what it moved, and the evidence behind it. In your own explorer its switches and values change the rules, and it rebuilds the release with them in the background.
- MedDRA's hierarchy and SMQs when you point it at your own MedDRA files (`open-altio serve --meddra`).
- Where the release has MedDRA, reactions are counted and found by their current preferred term for everyone, in the Statistics tab, the charts and the reaction search, and the release's MedDRA version is named there and on How we clean FAERS. The case list shows FDA's text as written; an old term in capitals is shown in MedDRA's spelling with FDA's capitals beside it. Only a viewer with MedDRA's licensed part sees the current preferred term beside FDA's text, in the case list and the case window, for reactions, indications and the reaction that came back when the drug was given again. Downloads carry FDA's text only.
- Improve this: write a note, point at the part of the page it is about if you like, and send it to Altio, with no account and no confirm step. Only your words, the page, the part you pointed at and an email address, if you give one to hear back, are sent. A note that cannot go yet waits on your machine. A setting hides the button.

### The command

- `open-altio demo`, `fetch`, `build`, `serve`, `doctor` and `report`. With no arguments, `open-altio` lists what you can do.
- `fetch` and `demo` also download DiAna's drug dictionary (CC BY 4.0), kept only when its checksum is the one the rule names, so a release you build yourself reads drug names to ingredients too.
- Builds are held to a memory limit by default, so a laptop with 16 GB works.
- Runs on macOS, Linux and Windows with Python 3.12 or later.
- A container image, `ghcr.io/altio-ai/open-altio`, runs the explorer and every command.

### Evidence and docs

- Notebooks that measure each step on the release they read, committed with the outputs of a run (licensed MedDRA output cleared).
- The docs site: using it, customising it, contributing, and the reference for the command, the rules and every column.

### Final additions

- The Overview has a System organ class chart, and All cases a System organ class filter, for a viewer who may see MedDRA's licensed part. Nobody else sees them.
- The methods page's drug names line reads "993,421 FDA spellings read to 6,441 single ingredients and 9,095 combinations" on FAERS 2026Q2: ingredients and combinations are counted ignoring capitals (`lactobacillus SPP` and `lactobacillus spp` are one), where before it counted 6,442 ingredients and no combinations. `methods.json` gains `numbers.drug_names.combinations`; `python -m open_altio.faers methods --release <folder>` adds it to a release already built.
- FDA's FAERS name `BIOVITRUM` counts as Swedish Orphan Biovitrum (Sobi) too, as `SWEDISH ORPHAN` does: its cases are the same firm's drugs (Kineret, Orfadin) from 2015Q4 on. The AERS name `BIOVITRUM AB.`, from before the merger, stays apart. On FAERS 2026Q2, cases shown: Swedish Orphan Biovitrum 1,451 before and 16,665 after, Biovitrum 15,281 and 67 (`rules/company-names.md`). `python -m open_altio.faers companies --release <folder>` puts it in a release already built.
- FDA's FAERS names `DAIICHI`, `KYOWA` and `SWEDISH ORPHAN` count as Daiichi Sankyo, Kyowa Kirin and Swedish Orphan Biovitrum: FAERS starts in 2012, after each firm's merger, so they are today's firm under a short name (`rules/company-names.md`). AERS names from before a merger, such as `SANKYO PHARMA INC.`, stay apart. On FAERS 2026Q2, cases shown: Daiichi Sankyo 2,195 before and 39,721 after, Kyowa Kirin 1 and 14,430, Swedish Orphan Biovitrum 113 and 1,451. `python -m open_altio.faers companies --release <folder>` puts the company table in a release already built, its Parquet and its explorer database, with no rebuild.
- Statistics for each WHO drug class: EBGM, PRR, ROR, RRR and IC for each class and reaction at the therapeutic, pharmacological and chemical subgroup (ATC levels 2, 3 and 4), on the ingredient statistics' own cases, each level with its own EBGM prior (`rules/statistics-classes.md`). A case counts once for a class however many of its drugs are in it; a drug counts at every level its class is certain at, and a class it only could be is left out. They are part of the drug classes layer, in `atc_statistics_T` with each ingredient's classes in `atc_statistics_ingredients_T`, so a release without the classes has neither. A full build writes them, and `python -m open_altio.faers class-statistics --release R` adds them to a release already built, exactly as a build would. MedDRA added to a built release counts them again by its PTs, as it does the ingredients'. On the Statistics tab, All cases' list may be by class at any of the three levels, chosen in the menu beside Thresholds, and a drug's rows show its class's EB05 beside its own; neither shows where the classes are hidden or the release has none, nor to anyone shown reactions as FDA wrote them in a release with MedDRA, since the class statistics have no set counted by FDA's text.
- The label flags speak of listing only, in the words of `rules/explorer-label-words.md`: Listed, Possibly listed (was Related), Not listed, Can't tell (was Uncertain) and Forms differ, shown as each form's answer; a flag that was not compared with the label (not a medical event, a procedure, the disease it treats, no label found) reads Not compared with its reason. Each label read is named by its product, its ingredients and its date (`rules/explorer-label-names.md`). Data and counts are unchanged.
- The rules page shows WHO's drug classes as a section of their own: their four rules in plain words, their evidence, and one switch for all four in your own copy. Off, the release is rebuilt without the classes (`rules/atc-index.md`); the section stays so they can be switched on again. A release without the classes has no section, and on open.altioai.com it shows only while the WHO switch shows the classes.
- Each ingredient and reaction's statistics give its time to onset: the median days over its suspect drugs that have one, how many have one, and how many have none by why (a padded event date, an event date or first dose not known to the day, the event before the first dose). Each drug record's reason is `time_to_onset_reason_T` on `drug_onset_T`.
- The statistics' strata put a sex or an age that reads Not given in the unknown group.
- Company names: each case's `company_T` is the company its sender spelling names, in either era, in the reviewed list in `mappings/faers/senders/` (1,113 spellings in 475 companies, the largest AERS spellings and account codes included), so `ELI LILLY AND CO` and `ELI LILLY AND COMPANY` count as Eli Lilly; any other sender as written, and none on a direct report, sent straight to FDA (FAERS writes its sender as `FDA-CTU` or leaves it blank), or where the sender only says unknown or names no company (FDA's intake `FDA-CTU` on any report, a regulator, a hospital, a university press, an ID number written as the name, one character or only generic words such as `PHARMACOVIGILANCE DEPARTMENT`). A company is never counted under its owner, nor under its earlier or later name, and a case counts under the sender of its latest version. FDA's `mfr_sndr` is unchanged, and the duplicate rules still compare it (`rules/company-names.md`).
- The explorer charts the companies that sent the most cases, with the direct reports as one bar, Sent straight to FDA, saying how many cases name their sender. The Company filter finds a company by its name or any of FDA's spellings of it, and the direct reports by the words Sent straight to FDA or FDA's intake `FDA-CTU`. The case window shows the company with FDA's sender beside it, and exports carry `company_T` beside `mfr_sndr`.
- The AEOLUS duplicate key never compares a value that reads Not given, as it never compared a blank. On FDA's 2026Q2 file alone (the demo release, 422,458 cases): 280,446 cases had no key before, 280,462 after; 6,967 cases are set aside before and after.
- A release's labels are kept current between releases: `python -m open_altio.faers labels-refresh` reads DailyMed's daily update files since the day the labels are as of, chooses again only where a label changed, flags again where a label the flags read changed, and switches the new files in only when all are whole (`rules/label-refresh.md`); the hosted service runs it every night. The screens and exports say which DailyMed day the labels are as of, and each label's link opens the version the flags were read from.
- Label flags: a reported PT is Listed when the label keeps the PT a reviewed pair says means the same (Drug hypersensitivity and Hypersensitivity, Peripheral swelling and Oedema peripheral, Drug dependence and Dependence, Drug withdrawal syndrome and Withdrawal syndrome); seven coarse not-elsewhere-classified groups come off the catch-all list, so a close term on the label gives Possibly listed; Possibly listed from the opposite direction of the same measure alone is Not listed; an uncertain line with an unread negation or a patient's condition before the term, or the heading word Nervous, states nothing; Device expulsion, Drug resistance and Vaccination failure are compared with the label on the exact PT; Product used for unknown indication is not a medical event. On FAERS 2026Q2 the shown pairs move: 8,040 to Listed, 78,513 Not listed to Possibly listed, 6,291 Possibly listed to Not listed, 1,066 uncertain ones settled, 4,434 out of Not a medical event, 963 out of procedures.
- The case window reads in a reviewer's order: a one-line summary; what happened, each reaction with its label results and outcome; the drugs, suspects first, then those taken alongside, with therapy dates and time to onset under them; the patient beside the report.
- Each case says FDA does not publish the reporter's narrative in its public files, so a case shows only the coded fields.
- Where MedDRA's licensed part may be shown, each reaction in a case shows its primary system organ class, and the case list has a System organ class column.
- The count line's Include probable duplicates is a tick box; ticking it adds them and changes nothing else on the line.
- Statistics' thresholds name what the table shows: Rows shown, every drug and reaction or only those that pass a statistic's threshold.
- Home's release card says when the release was updated and that its reports are mostly postmarketing.
- A custom query is saved and run in one press, Save and run. On a hosted site saved queries live in the person's account and can be shared with their organisation; a local copy keeps them in the browser.
- Every menu that opens from a button stays with its button as the page scrolls.
- Every page ends the same distance from the bottom of the window as the side panel.
