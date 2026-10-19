# Run the explorer on your machine

For anyone who wants Open Altio on their own laptop, for one person, with nothing to sign up for.

This page covers installing it, what is in the explorer, and how drugs, statistics, MedDRA, drug classes and label flags work in it.

## Install

With [uv](https://docs.astral.sh/uv/), the tool that installs Open Altio and the Python it needs. If you do not have uv yet, install it with one line, then open a new terminal so it is found.

On macOS or Linux:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows, in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then install Open Altio:

```sh
uv tool install open-altio
```

`pipx install open-altio` and `pip install open-altio` work too. You need Python 3.12 or later, on macOS, Linux or Windows. A container image is at `ghcr.io/altio-ai/open-altio`.

## First run

```sh
open-altio demo
```

`demo` downloads FDA's latest quarterly file (about 65 MB) and DiAna's drug dictionary. It builds a release from them (about 30 seconds, with about 3 GB of memory at its peak) and opens the explorer in your browser.

!!! note "The demo is one quarter"
    The demo release holds only FDA's latest quarter: about 415,000 cases for 2026Q2, against about 20 million in the full release. A case FDA last updated in an earlier quarter is not in it, and duplicates are found only within that quarter. For all of FAERS, [rebuild from FDA's files](../customise/rebuild.md).

Later, `open-altio serve` opens the explorer again on a release you have built. [The command reference](../reference/cli.md) lists every command.

## What is in it

Nothing about people: no accounts, no sign-in, no applications. The explorer listens only on `127.0.0.1`, so only your own machine can reach it. It sends no telemetry.

Everything about the data:

- **Drugs and reactions,** each with its cases, charts and counts. A drug is found by its ingredient or any name it is reported under; [how a drug counts](#how-a-drug-counts) is below.
- **Pinned products.** The pin beside a drug Home finds, or on the drug's page, keeps it in the side panel, in the order you drag them. Press the pin again, or Unpin in the row's menu, to let it go. Pins are kept in this browser. Home lists the drugs you opened lately.
- **How current it is.** Every page says once, top right, the latest FDA quarter the release holds ("FDA data through 2026Q2").
- **All cases,** with filters (drugs, drug classes, reactions, system organ class, dates, sex, age, outcome, reporter, country, company, era) and the switch that shows probable duplicates again.
- **Companies,** [listed in the company-names rule](https://github.com/Altio-AI/open-altio/blob/main/rules/company-names.md).
    - The company that sent each report is shown, with each of FDA's spellings of one company counted under its name (`ELI LILLY AND CO` and `ELI LILLY AND COMPANY` are Eli Lilly).
    - A chart shows the companies that sent the most cases. Reports sent straight to FDA by no company are one bar, Sent straight to FDA.
    - The Company filter finds a company by its name or any of FDA's spellings.
    - The case window shows FDA's sender under it, and exports beside it.
- **The case window** shows one case with every value. See [the case window](#the-case-window) below.
- **Not given.** See [not given](#not-given) below.
- **FDA system** is the system of each case's latest version. The cases FDA carried from AERS into FAERS count as FAERS cases, though many were first received before. The Received by FDA filter finds the cases first reported before FAERS.
- **Statistics,** on a product's page and on All cases: EBGM with EB05 and EB95, PRR, ROR, RRR and IC for each ingredient and reaction, worked out once for the release ([below](#statistics)).
- **Label flags,** when the release holds them: whether today's US prescription label of each suspect drug lists a reaction ([see below](#label-flags)).
- **Tables and SQL.** Every table of the release, with its columns marked FDA or Open Altio, read-only SQL, and downloads.
- **Exports** of what your filters show.
- **How we clean FAERS,** the methods page, at `/methods`: the journey from FDA's files to the cases you see, every rule with what it moved, and the evidence. Switch a rule or set a value there, then rebuild the release with your rules. Afterwards every page with counts says "Your rules" and lists how they differ from Altio's standard.
- **Settings,** and a light and a dark look.

### The case window

It shows one case, every value, with FDA's under Open Altio's where they differ and a link to the rule that changed it under that. It also shows what each drug was used for as the report says, and why a case was set aside as a duplicate, each case it names a link to that copy.

It reads in the order a safety reviewer reads a case:

1. **A line about the case.**
2. **What happened:** each reaction with its label results under it, then the outcomes and the event date.
3. **The drugs:** the suspects first, then those taken alongside them, with each drug's therapy dates and time to onset under them.
4. **The patient.**
5. **The report,** last, with its probable duplicates.

A copy in a group of duplicates shows when any copy was first received beside when this one was.

Each drug shows:

- its role as FDA codes it (its name on hover);
- its ingredients, with FDA's active ingredient under them and where they came from: the DiAna dictionary, DiAna through FDA's active-ingredient field, or an Open Altio correction;
- its WHO class where the release carries the classes;
- its dose, with how often in words;
- whether the reaction abated when it was stopped and came back when it was restarted.

The therapy table:

- names each drug as it was reported (with its number where two share a name);
- gives each therapy's start and end as far as they are known, its duration in days, and each drug's time to onset (the first dose is day 1), or why it has none, each with FDA's own under it.

While the window is open the address names the case. A bookmark, or a case number from an export put in the address as `?case=`, opens it again. A copy set aside since says so and links to the copy shown now.

### Not given

A field that is blank, says unknown (sex `NS`, `COUNTRY NOT SPECIFIED`) or holds a filler number (an age of 999) reads Not given in:

- the filters;
- the charts;
- the case window, where FDA's own value is shown under it;
- the clean columns of exports.

How it shows:

- **In charts.** Each chart says how many of its cases give its field ("Countries given for 98% of these cases") and keeps Not given apart at the bottom.
- **Found values.** Where Open Altio works the value out, the line says found: "Ingredient found" for a case with a suspect drug of a known ingredient, "WHO class found" for one with a class chosen or a could-be class.
- **Outcomes are not such a field.** FDA writes an outcome only when it is serious, so the line reads "A serious outcome given for 40% of these cases" and a case with none reads No outcome given.
- **Field notes.** Where FDA's own files changed how a field is filled, a note sits under its chart and beside its filter.

The lists are [the not-given rule](https://github.com/Altio-AI/open-altio/blob/main/rules/not-given.md), with [sex-codes](https://github.com/Altio-AI/open-altio/blob/main/rules/sex-codes.md) and [country-not-given](https://github.com/Altio-AI/open-altio/blob/main/rules/country-not-given.md) for sex and country, and [the explorer-field-notes rule](https://github.com/Altio-AI/open-altio/blob/main/rules/explorer-field-notes.md).

## How a drug counts

A drug's page counts it by its ingredient, as the open [DiAna dictionary](https://osf.io/zqu89/) and our reviewed corrections read FDA's drug names, so one medicine counts together however it was spelled. A combination such as sacubitril and valsartan is a drug of its own too.

- **Its spellings.** The title says how many of FDA's spellings the page counts. Click it to see each spelling with its cases, all ticked. Untick one to leave it out. Type to find a spelling, and FDA's spellings that carry no ingredient, which you can tick to count with the drug. The strip under the toolbar says what you changed.
- **Any product containing it, or the exact product.** By default valsartan's page counts every product containing valsartan, Entresto included. "Exact product" counts valsartan alone. On Entresto's page, "Exact product" counts sacubitril and valsartan together and nothing more.
- **Roles.** FDA codes how each drug was involved in a report: PS primary suspect, SS secondary suspect, I interacting, C concomitant (taken alongside).
    - PS and SS are ticked when a page opens.
    - Tick I or C to count them too. The strip under the toolbar shows the roles counted until you set them back.
    - Hover a code for its name. The codes are FDA's, never merged or changed.

The Drugs filter on All cases works the same way: choose ingredients or FDA's spellings with no ingredient, and tick the roles.

- **Exports** name the drug as it was counted.
- **Older links.** A link to a product page from an earlier version, which named FDA's active ingredient (`/product/ADALIMUMAB`), opens the page of the drug that name is read to.
- **Defaults.** They are [the explorer-drug-counts rule](https://github.com/Altio-AI/open-altio/blob/main/rules/explorer-drug-counts.md).

## Statistics

The Statistics tab lists ingredient and reaction pairs with how much more often they are reported together than expected.

- **The same cases.** Every statistic counts the cases the release keeps that name the ingredient as primary or secondary suspect, in any product containing it, and a reaction.
- **Reactions.** Where the release has MedDRA, each reaction is counted and named under its preferred term today. Otherwise it is counted under FDA's text.
- **Worked out once.** The build works them out once for the whole release, so the filters do not change them, nor do a drug page's products and roles.
- **Combinations.** A combination's tab links to each of its ingredients'.

The columns and controls:


- **EBGM** is how many times more often than expected, with small counts pulled towards the ratio usual in the release. **EB05** and **EB95** bound it.
- **Exp. count,** the expected count, is the cases expected if the two were unrelated, worked out within age band, sex and year received.
- **Beside them** stand **PRR** with its two chi-squares (**Chi²**, and **Yates** with Yates' correction), **ROR** with its 95% interval under it, and **RRR** and **IC** with IC025 under it. A head's tip gives its full name.
- **Onset** is the median time from the first dose, day 1, to the reaction, in days, over the ingredient's suspect drugs in the pair's cases that give both dates to the day. In grey, how many drugs that is of all of them. Its tip says why the others have none.
- **Width.** The table fits a laptop's screen. On a narrower one it scrolls sideways inside its frame with its first column held in view, as the case list and the other wide tables do.
- **Sorting.** Press a column title to sort by it: highest first (a name A to Z), then lowest first, then back to the table's own order, EB05 highest first. The case list's titles sort the same way, back to newest first.
- **Thresholds** sets the thresholds. Each statistic offers the common ones as presets, or your own numbers, or none.
    - The presets are EB05 at least 2 with at least 3 cases, Evans 2001 for PRR, a lower ROR bound above 1, and IC025 above 0.
    - A number that passes its statistic's threshold is marked.
    - One threshold narrows the list: by default EBGM's.
    - Your choices stay in this browser.
- **By class,** where the release holds WHO's drug classes. The button beside Thresholds on All cases' tab lists class and reaction pairs instead of ingredient and reaction pairs, at one level of the class: Therapeutic, Pharmacological or Chemical subgroup. The columns and thresholds are the same, without Onset. A row opens every case's Cases tab filtered to the class and the reaction.
- **Class EB05,** on a drug's tab, is its class's EB05 with the same reaction, beside the drug's own, at the level **Class level** chooses. Its tip names the class.
    - When the two are close, the reaction is reported for the whole class. When the drug's is far higher, it stands out for the drug.
    - Where the classes are not shown, neither is.
    - Neither is shown to anyone shown reactions as FDA wrote them in a release with MedDRA, because the class statistics are counted only by today's MedDRA terms.
- **A row** opens the pair's cases. Under them is the pair's **ROR by age band and by sex**: the ROR worked out again on the cases of each age band alone and of each sex alone, every group listed, empty where its table has a cell of 0.
- **How these are worked out** opens the rules behind each statistic.

!!! note
    A statistic of disproportionate reporting is not a signal and not evidence that the drug caused the reaction. It says which pairs are reported together more often than the rest of the release would lead you to expect.

## MedDRA, with your own files

MedDRA's hierarchy above the preferred term and its SMQs are MedDRA's licensed content. If your organisation subscribes, point the explorer at the MedDRA release you received from MSSO (the English release, unzipped). The hierarchy, the SMQs and SMQ filters then appear.

- **SMQs.** A chosen SMQ opens to its preferred terms, all ticked. Untick one to leave it out, and the SMQ shows a dash, partly ticked.
- **Your own queries (CMQs)** work the same way, with or without MedDRA.
- **Preferred terms.** Every reaction, indication and reaction that came back when the drug was given again is counted and found by its current preferred term. A search for Seizure also finds the cases FDA wrote as Convulsion, and a search takes any lower level term too.
- **The case list** shows that preferred term beside FDA's text and each case under it, with the MedDRA version.
- **Statistics.** Adding MedDRA to a release already built counts its statistics again by preferred term.
- **Downloads and exports** carry FDA's text only.
- **Your files stay on your machine.** `open-altio serve --help` shows how.

Without MedDRA files, reactions show and count as FDA published them, by preferred term text. An old term AERS wrote in capitals is shown in MedDRA's spelling, taken from FAERS's own text, with FDA's capitals beside it.

## System organ classes

Where you may see MedDRA's licensed part, the Overview has a System organ class chart and All cases has a System organ class filter. Each reaction counts in the primary system organ class of the current preferred term it reads to, so a case with reactions in two classes counts in both. A bar filters to the cases with any reaction in that class. The chart says for how many cases a class was found.

## WHO drug classes

When a release includes WHO's drug classes (ATC), All cases has a Drug class filter. Where the classes come from is on [the methods page](../methods/index.md#drug-classes). Each drug in a report has one class, the most exact one the report allows. When its codes have different uses and the report does not say which (no dose or route that decides), its class is the broader one its codes share, or "can't tell".

- **The filter.** Type a class, a code or a substance, or open the main groups down to the class you want. The classes tick as a tree:
    - Ticking a class ticks every class under it.
    - Unticking one of those leaves only it out, so each class above it shows a dash, partly ticked.
    - Ticking the last unticked one under a class ticks that class whole again, unless drugs are classed at that class itself (a report naming only an ACE inhibitor is classed at C09A). The classes under it leave those out, so it keeps its dash.
    - A case counts when a drug in a ticked role is in a ticked class. PS and SS are ticked, as in the Drugs filter.
    - A drug known only by a broader class counts when that class is ticked.
- **Could be.** One tick adds the drugs that could be in the chosen class, because the report does not say which of their classes they were given as. The number beside it is the cases it adds.
- **The breakdown.** All cases' Overview counts cases by the classes one level under the class chosen, or by the main groups. Drugs that could be in several of them are one bar of their own, "Could be several", so no drug counts twice.
- **Each drug's class** shows beside it in the case list, marked "broader" when it is a broader class. The case window shows, for each drug, its class, what else it could be, and how the class was chosen, with a link to the rule.

How the classes are written and cited:

- **Capitals.** WHO writes the names of its first three levels in capitals. The pages show them in normal capitals (Cardiovascular system), keeping abbreviations such as ACE in capitals. Files, SQL and the Tables page keep WHO's exact text.
- **Citation.** Wherever classes show, one short line names WHO's index and its year. It opens WHO's full citation on the methods page. Every export with classes, and every Parquet SQL result where the classes can be read, carries the full citation.
- **Without the classes,** a release works as before, with no filter.
- **On open.altioai.com** one switch shows or hides the classes everywhere at once.

## Label flags

FAERS reports are suspected events, not proven reactions. The flag only says whether today's label lists the event.

When the release holds the label tables, each suspect drug and reaction carries a flag that says only whether the label lists the reaction:

| Flag | Means |
|---|---|
| Listed | The label lists the reaction (with its section). |
| Possibly listed | The label names a related term. |
| Not listed | The label does not list it. |
| Forms differ | The labels of the drug's forms disagree, shown as each form's answer: "Listed on the by-mouth label, not listed on the skin label". |
| Can't tell | It could not be decided. |
| Not compared | The reaction was not compared with the label, with its reason under it: not a medical event, a procedure, the disease it treats, or no label found. |

Point at a flag for how it was decided and the label it was read on, named by its product, its ingredients and its date (a label's forms are named only where the drug has different labels for different forms).

Which label a flag is read on:

- **Another form's label.** Where none of the forms the report could be has a label of its own, or the report does not say the form, the flag is read on another form's label and says which ("Listed on the injected label; no by-mouth label").
- **No RxNorm code.** A drug record with no RxNorm code shows Not compared, no label found.
- **Trial products.** A trial product (a study drug, a placebo or a blinded drug) has no flag.
- **Any product containing an ingredient,** as a drug's page opens and as its Statistics tab always counts. Every reaction is judged against the ingredient's own label: valsartan's page reads its reports of Entresto on valsartan's label. An ingredient with no label of its own shows Not compared, no label found for the products that hold it with others, while its reports of the ingredient alone keep their own label.
- **The product alone, and a combination's page.** The flags are those of exactly that product's reports, each read on its own label.
- **More than one label.** Where reports were read on more than one label that agree, the flag names the drug's own label first, then the newest, then the lower set ID, so the same release always names the same label.

- **The case window** shows, under each reaction, one line per suspect drug with its flag, and links each drug's label on DailyMed.
- **Label status,** in a drug's filters menu, keeps the cases with at least one reaction whose flag for the drug is ticked. Every flag is ticked from the start, so the list opens on its true total. **Unexpected only** ticks Not listed, Possibly listed, Forms differ, Can't tell, and Not compared for no label found and for a procedure, in one click. It combines with every other filter.
- **On a drug's Statistics tab,** the Label column after Reaction gives each pair's flag, and sorting by it puts Not listed first. Filters holds Label status, which narrows the pairs the same way. It also holds Only reactions that pass the cutoffs, which is the Thresholds menu's choice between every pair and the pairs that pass a threshold.
- **About the label flags,** linked beside them, says what each flag means and how each was decided.

How the screens show them is [rule explorer-label-flags](https://github.com/Altio-AI/open-altio/blob/main/rules/explorer-label-flags.md). A release without the tables shows no flags.

## Improve this

Every page has an Improve this button. Write what was confusing, slow or missing, point at the part of the page you mean if you like, and click send. There is no preview and no confirm step. Under the box it says what is sent: "We send only your words, the page you're on, the part you pointed at and your email if you give one. Nothing else."

- **Where it goes.** Notes go straight to Altio's improvements board, marked as coming from a local copy.
- **The email is optional.** Give one only if you want to hear back, and Altio writes to it once someone has looked at your note. Nothing else is ever sent to it.
- **How it is sent.** Your browser sends the note itself, so it goes through the same connection as any page you open.
- **Offline.** A note that cannot go yet, because you are offline or Altio does not answer, waits on your computer and is sent when you are back online or next open the explorer. The dialog says so.
- **Turn it off.** Settings, Improve this, Hide turns the button off in that browser.

[The improve-this rule](https://github.com/Altio-AI/open-altio/blob/main/rules/improve-this.md) lists exactly what a note holds and where it is kept.

## When something goes wrong

```sh
open-altio doctor
```

`doctor` checks Python, memory, disk, ports, the release folder and versions, and says in plain words what is wrong and how to fix it. When it cannot fix something, or any command crashes, it asks whether to report it.

`open-altio report` opens a GitHub issue with what you ran, the error, your system and versions filled in. You add your words and submit it in your browser. The command never needs your GitHub login.
