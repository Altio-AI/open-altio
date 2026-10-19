# How we clean FAERS

For anyone checking how Open Altio turns FDA's files into the cases you see.

How we clean FAERS is Open Altio's methods page. This page says what it shows, lists the steps and their rules, and gives the background on drug classes and MedDRA.

The methods page is one page, served in two places from the same code:

- **[open.altioai.com/methods](https://open.altioai.com/methods)** is public, with no sign-in, for Altio's releases.
- **`/methods` in your own explorer** is for the release you built, with your own rules where they differ from Altio's.

Both read the `methods.json` every build writes, so the page always describes the release in front of you, with that release's own counts.

## What it shows

- **Today's line,** at the top: when the release was built, from which quarters and with whose rules, its MedDRA version and how to cite it. Then a guide to the three levels below and a box to find a rule.
- **Narrow:** from the report versions as FDA published them to the cases you see, each band as wide as what is left after its step.
- **Read one way:** dates, ages, reporters and empty fields, FDA's value above ours, so every count and filter means the same.
- **Answer:** four questions people bring (every report of a drug, whether a reaction is on its label, a class's cases, a reaction reported more than expected), each followed from cleaning to its answer.
- **Every rule in the box where it acts.**
    - **Closed,** a box says how many of its rules can be changed and how many are fixed.
    - **Opened,** it shows its finding, the rules you can change (each with what switching it off would change) and the fixed ones (each with why).
    - **A rule opens** to what it is set to, the findings behind it (the claim, how to read the chart, the chart, then what it shows, why it matters and what we did) and a foot with what it moved, the rule file and the code.
- **What Open Altio does not do yet,** at the foot.

Every number on the page is the release's own, from its `methods.json` and manifest.

In your own explorer:

- each rule you can change has its switch;
- its values are set in the open rule;
- the Rebuild bar appears as soon as anything changes.

[Changing a rule](../customise/rules.md) says how the release is then rebuilt with them. The old address `/rules` forwards to `/methods`.

## The steps

| Step | What happens | Rules |
|---|---|---|
| As FDA published | Every FDA file is loaded as text, verbatim. Nothing is corrected. A line holding two records is split back into them, and any other overlong line is recorded. Each patient's sex, age in years, weight in kilograms and age band are read beside FDA's values | [transformed-suffix-T](https://github.com/Altio-AI/open-altio/blob/main/rules/transformed-suffix-T.md), [overlong-lines](https://github.com/Altio-AI/open-altio/blob/main/rules/overlong-lines.md), [sex-codes](https://github.com/Altio-AI/open-altio/blob/main/rules/sex-codes.md), [age-in-years](https://github.com/Altio-AI/open-altio/blob/main/rules/age-in-years.md), [weight-in-kg](https://github.com/Altio-AI/open-altio/blob/main/rules/weight-in-kg.md), [age-bands](https://github.com/Altio-AI/open-altio/blob/main/rules/age-bands.md) |
| Latest version of each case | One version per case, the newest FDA published, across AERS and FAERS | [latest-version](https://github.com/Altio-AI/open-altio/blob/main/rules/latest-version.md) |
| FDA's deleted-case lists | Cases FDA lists as deleted leave the case set, in both eras | [deleted-cases](https://github.com/Altio-AI/open-altio/blob/main/rules/deleted-cases.md) |
| Probable duplicates | Two rules group the copies of one case. Each group shows its latest received copy and sets the others aside, flagged, never deleted | [dedup-default](https://github.com/Altio-AI/open-altio/blob/main/rules/dedup-default.md), [dup-manufacturer-number](https://github.com/Altio-AI/open-altio/blob/main/rules/dup-manufacturer-number.md), [dup-padded-event-dates](https://github.com/Altio-AI/open-altio/blob/main/rules/dup-padded-event-dates.md), [dup-shown-copy](https://github.com/Altio-AI/open-altio/blob/main/rules/dup-shown-copy.md), [legacy-country](https://github.com/Altio-AI/open-altio/blob/main/rules/legacy-country.md), [country-not-given](https://github.com/Altio-AI/open-altio/blob/main/rules/country-not-given.md), [eu-member-state](https://github.com/Altio-AI/open-altio/blob/main/rules/eu-member-state.md), [reaction-term-case](https://github.com/Altio-AI/open-altio/blob/main/rules/reaction-term-case.md) |
| Flags that hide nothing | Reports with no usable drug or reaction stay visible. Those with a serious outcome are flagged. A company's spellings as a sender count under one company name, FDA's sender kept beside it | [no-drug-or-reaction](https://github.com/Altio-AI/open-altio/blob/main/rules/no-drug-or-reaction.md), [company-names](https://github.com/Altio-AI/open-altio/blob/main/rules/company-names.md) |
| Dates | Each event and therapy date is read only as far as it is known and can be true. Time to onset and each therapy's duration are worked out from those dates. No case is removed | [event-date-precision](https://github.com/Altio-AI/open-altio/blob/main/rules/event-date-precision.md), [date-limits](https://github.com/Altio-AI/open-altio/blob/main/rules/date-limits.md), [time-to-onset](https://github.com/Altio-AI/open-altio/blob/main/rules/time-to-onset.md), [therapy-duration](https://github.com/Altio-AI/open-altio/blob/main/rules/therapy-duration.md) |
| Codes read one way | FDA's reporter codes are read as the E2B(R3) reporter qualification, so OT and HP count as one; FDA's codes stay beside them | [reporter-type](https://github.com/Altio-AI/open-altio/blob/main/rules/reporter-type.md) |
| Drug names | Each drug is read to its ingredients through the open DiAna dictionary and our reviewed corrections, so one medicine counts together whatever the spelling. No case is removed, and the page says how many drug records find no ingredient | [drug-names](https://github.com/Altio-AI/open-altio/blob/main/rules/drug-names.md) |
| RxNorm codes for drugs | Each drug record gets the RxNorm code of its drug, so it can be joined to FDA's labels: from FDA's drug name, else FDA's active ingredient, else the record's ingredient. A salt the record names only as its element (potassium for potassium chloride) gets none. No case is removed | [rxnorm-ingredients](https://github.com/Altio-AI/open-altio/blob/main/rules/rxnorm-ingredients.md) |
| Reaction terms in today's MedDRA | Old reaction and indication terms written in capitals are shown in MedDRA's spelling, taken from FAERS's own text. Where the release has MedDRA, every term FDA wrote is read to the preferred term it belongs to in the release's one MedDRA version, so each reaction is counted under today's term. No case is removed | [legacy-term-spelling](https://github.com/Altio-AI/open-altio/blob/main/rules/legacy-term-spelling.md), [meddra-terms](https://github.com/Altio-AI/open-altio/blob/main/rules/meddra-terms.md), [meddra-version](https://github.com/Altio-AI/open-altio/blob/main/rules/meddra-version.md) |
| Statistics | For every suspect ingredient and reaction, EBGM, PRR, ROR, RRR and IC, counted on one set of cases. No case is removed | [statistics-cases](https://github.com/Altio-AI/open-altio/blob/main/rules/statistics-cases.md), [ebgm](https://github.com/Altio-AI/open-altio/blob/main/rules/ebgm.md), [prr](https://github.com/Altio-AI/open-altio/blob/main/rules/prr.md), [ror](https://github.com/Altio-AI/open-altio/blob/main/rules/ror.md), [rrr](https://github.com/Altio-AI/open-altio/blob/main/rules/rrr.md), [ic](https://github.com/Altio-AI/open-altio/blob/main/rules/ic.md) |

Three pages here tell the background in prose:

- [Case versions across AERS and FAERS](case-versions.md)
- [Duplicates across cases](duplicates.md)
- [The statistics](statistics.md)

## Rerun the evidence

Every chart on the methods page is computed by code in `src/open_altio/faers/insights/`, from the release's own tables.

The notebooks in [`notebooks/faers/`](https://github.com/Altio-AI/open-altio/tree/main/notebooks) hold the full analyses behind each step:

| Notebook | Analysis |
|---|---|
| `00` | What FDA published |
| `01` | Volume over time |
| `02` | Case versions |
| `03` | Empty fields: which fields are empty and how FDA's files and senders write unknown (reads a release built from every quarter, and FDA's zips) |
| `04` | Duplicates |
| `05` | Drug names |
| `06` | MedDRA versions |
| `07` | Demographics and units: sex, age, weight and country |
| `08` | Dates and codes |
| `09` | Drug classes |
| `10` | Label flags: how far drug records reach an FDA label, what the flags say and how accurate they are (needs a release with the labels step run, and reads the licensed MedDRA part) |
| `11` | Drug route: how filled route and dose form are, and which labels each record matches (also reads the label step's tables) |
| `90` | Open questions |

Run them against a release you built, and they recompute every number from your own data. A notebook's first cell says what else it reads, and [`notebooks/README.md`](https://github.com/Altio-AI/open-altio/tree/main/notebooks) says how to run it.

## Drug classes

Drug classes come from WHO's ATC classification index, the 2026 edition, through a drug-to-class table in [`mappings/`](https://github.com/Altio-AI/open-altio/tree/main/mappings). For each ingredient it holds its ATC code, WHO's name for it, its level and the index year.

- **No WHO file needed.** The table is derived from WHO's index the way DiAna publishes its ATC table, so anyone building a release gets the classes without WHO's own file. WHO's file is not in the repository.
- **In the manifest.** A release that includes the classes lists them in its manifest, with the index year.
- **On the methods page** they are a section of their own, WHO drug classes: their five rules, one switch for all of them in your own copy, and their evidence.
- **Without the classes,** a release has no such section. On open.altioai.com it shows only while the classes are shown.

Cite the classes as: WHO Collaborating Centre for Drug Statistics Methodology, ATC classification index with DDDs 2026, Oslo, Norway.

## MedDRA

Reactions and indications are MedDRA preferred terms, shown exactly as FDA published them. MedDRA's own content is licensed by MSSO, and Open Altio never publishes it. That content is its codes, the hierarchy above the preferred term and the SMQs.

- **On your machine,** the explorer shows it only when you point it at MedDRA files you hold under your own subscription.
- **On open.altioai.com,** it is shown only to people whose MedDRA subscription has been verified with MSSO, and checked again as they use it.
