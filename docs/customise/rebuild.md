# Rebuild from FDA's files

For anyone who wants all of FAERS on their own machine, or wants to check Open Altio's work from FDA's files up.

This page takes you from FDA's files to a release on your machine, then to rebuilding it with your rules and checking it against Altio's.

## Fetch the files

```sh
open-altio fetch
```

`fetch` downloads:

- **Every quarterly file FDA has published since 2004Q1,** the legacy AERS files and the FAERS files: 90 quarters to 2026Q2, about 3.5 GB. Expect it to take about an hour. It shows its progress and can be stopped at any time. Run it again and it carries on where it stopped.
- **DiAna's drug dictionary** (University of Bologna, CC BY 4.0), through which the build reads each drug name to its ingredients ([`rules/drug-names.md`](https://github.com/Altio-AI/open-altio/blob/main/rules/drug-names.md)). The file is kept only when its checksum is the one the rule names. A release built without it has no drug ingredients.

`fetch` keeps the files in Open Altio's data folder ([Where the files go](../reference/cli.md#where-the-files-go)), and `build` reads them from there. If you move that folder with `OPEN_ALTIO_DATA_DIR`, set it the same way for both.

## Build a release

```sh
open-altio build
```

`build` turns the files `fetch` downloaded into a release folder named after the latest quarter, for example `2026Q2`, inside the folder you run it in. A full build takes about an hour. If the folder you run it in holds a `rules.toml`, the build uses it (see [Change a rule](rules.md)).

What the build needs:

- **Memory.** The build is held to a memory limit by default (DuckDB at 6 GB and 4 threads, from [`rules/explorer-build-memory.md`](https://github.com/Altio-AI/open-altio/blob/main/rules/explorer-build-memory.md)). The build as a whole peaks at about 8 to 9 GB, so a laptop with 16 GB of memory works. Past the limit it spills to disk and takes longer rather than failing.
- **Disk.** Leave about 50 GB free for FDA's files, the release and the build's scratch space ([`rules/machine-needs.md`](https://github.com/Altio-AI/open-altio/blob/main/rules/machine-needs.md)).

`open-altio doctor` checks both before you start.

A build never leaves a half-written release. It writes into a hidden folder beside the release and moves it into place only when everything is written.

## Explore it

```sh
open-altio serve
```

Run it in the folder you ran `build` in: it opens the newest release there. [Run the explorer on your machine](../use/explorer.md) says what is in it.

## Rebuild it with your rules

The explorer's methods page rebuilds the release with your rules ([Change a rule](rules.md)).

It builds from FDA's files and from every other file the release was built with, so the rebuilt release holds what a first build with those files and your rules would. Start the explorer with each one the release holds:

| The release holds | Start the explorer with |
|---|---|
| MedDRA, in its licensed part | `--meddra <folder>`: MedDRA's English release, unzipped |
| RxNorm's drug codes | `--rxnorm <folder>`: NLM's RxNorm files, unzipped. Without it, the folder `OPEN_ALTIO_RXNORM_DIR` names, else `rxnorm/` in Open Altio's data folder, as `build` reads them |
| FDA's labels | `--labels <folder>`: the folder `python -m open_altio.faers labels-fetch` filled |
| Label flags read with EMA's Important Medical Events | `--ime <file>`: EMA's file for the release's MedDRA version |

```sh
open-altio serve --meddra ~/meddra/MedDRA_29_1_English --labels ~/labels --ime ~/meddra/ime_29_1.xlsx
```

When the release's reactions were flagged on FDA's labels, the rebuild runs the labels step again under your rules. It uses the groups file and the reviewed codings the release keeps in its licensed part ([Make the groups file](label-groups.md)).

If a file the release needs is not given, the rebuild does not start. It says which file to give, rather than build a release without that layer.

Before you start it, the methods page shows:

- **What a rebuild of your release needs:** free disk and memory, the numbers `open-altio doctor` checks ([`rules/machine-needs.md`](https://github.com/Altio-AI/open-altio/blob/main/rules/machine-needs.md)).
- **What your computer has,** beside them.

If the disk that holds the release has less free room than that, the rebuild does not start and says so. If a rebuild stops, the methods page says in plain words what happened and what to do, and the release you had open stays as it was.

## Keep its labels current

FDA's labels change every day. Between releases, bring a release's labels up to date from DailyMed's daily update files, without building FAERS again:

```sh
python -m open_altio.faers labels-refresh --release 2026Q2 --labels ~/labels --ime ~/meddra/ime_29_1.xlsx
```

It:

- fetches each day's file since the day the release's labels are as of, into the labels folder;
- chooses a label again only where one changed;
- flags the reactions again when a label the flags read changed.

Give `--ime` when the release's flags read EMA's file.

Everything is built beside the release and switched in only when whole, so a refresh that fails leaves the release as it was and says why. Run it once a day to keep the flags on today's labels. The explorer shows the day the labels are as of. Rule [label-refresh](https://github.com/Altio-AI/open-altio/blob/main/rules/label-refresh.md) says exactly what it does.

## Check it against Altio's

- `funnel.json` in the release holds the count after each step. Compare it with the counts on [the methods page](https://open.altioai.com/methods) for the same quarter. Built from the same FDA files with Altio's rules, they are the same.
- `manifest.json` records every FDA file read, with its checksum, and an `inputs_hash` over all of them, so two builds can show they started from the same files.
- The [data dictionary](../reference/data-dictionary.md) describes every table and column the build writes.

## Rerun the evidence

The notebooks in [`notebooks/`](https://github.com/Altio-AI/open-altio/tree/main/notebooks) measure each step on a release. Point them at yours and they recompute every chart on the methods page from your own build. `notebooks/README.md` says how to run them.

## Licence

A release you build yourself is yours. FDA's data is in the public domain. If your release uses others' work, such as the DiAna drug dictionary (CC BY 4.0) or WHO's ATC classes, credit it as [NOTICE](https://github.com/Altio-AI/open-altio/blob/main/NOTICE) says.
