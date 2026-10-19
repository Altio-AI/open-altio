# Change a rule

For anyone who wants a release built their own way: a rule switched off, or a value changed.

Every step Open Altio takes is a rule, and every data rule can be read, switched and changed without touching the code.

This page covers the switches on the methods page, the `rules.toml` file, building with it, and what the release records.

## On the methods page

Run the explorer on your own machine (`open-altio serve`) and open **Rules**. Each data rule has a switch. Opening a rule shows its values, which you can change there.

**WHO's drug classes** are a section of their own, with one switch in its head for their five rules. Switch it off and the release is rebuilt without the classes. The section stays, so you can switch them on again.

**Some rules are always on,** because the build cannot run without them or because later steps read them:

- **FDA's values kept as published.**
- **The latest version of each case.**
- **Which copy of a group of duplicates is shown.**
- **Not given.** It is always on, so every screen reads one empty state.
- **The rules that read a patient's sex, age, weight and age band.** They add a value beside FDA's own, which the later steps read.
- **The statistics' rules.** They take no case out. You set the thresholds you read them by on the Statistics tab.

**To rebuild,** change something and a bar says how many rules you changed and offers **Rebuild with your rules**.

- The rebuild runs in the background from the same FDA quarters, showing its progress. The explorer opens the new release when it is done.
- It never writes over the release the explorer has open, which Windows would refuse. The new release goes beside it, in a hidden folder (`.2026Q2.rebuilt`). The next `open-altio serve`, `demo` or `build` puts it back under the release's own name.
- From then on every page with counts says "Your rules: 2 off, 1 changed", with the list.

The hosted site at open.altioai.com shows the same page with Altio's standard, read only.

## In a rules file

Your choices are saved as `rules.toml` beside the release, in the folder that holds it. You can keep it, share it with a colleague and review it, and write or edit it yourself. It lists every data rule under its step, with Altio's standard values as comments and only your own choices written out:

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

- **Switch a rule off:** set `on = false`. The drug classes go on and off together, by `[atc-index]`.
- **Change a value:** remove the first `#` on its line and write your own.

Anything you leave untouched follows Altio's standard, including later updates to it. Only the values a rule offers can be set.

**Writing one by hand,** for example on a machine with no browser, where the switches on the methods page cannot be used: a file needs only what you change. Each rule is a section named for its rule file. [`rules/README.md`](https://github.com/Altio-AI/open-altio/blob/main/rules/README.md) lists every rule by name with what it does, and each rule file lists the values it lets you set under `settable`. This file switches off one rule, the one that reads `COUNTRY NOT SPECIFIED` and `A1` as no country, and leaves everything else at Altio's standard:

```toml
[country-not-given]
on = false
```

A file is refused before anything is built, with a plain message saying which, when it has:

- a rule or a value that does not exist;
- a value of the wrong kind;
- an always-on rule switched off.

## Build with it

```sh
open-altio build
```

Run `build` in the folder that holds your `rules.toml` and it picks the file up by itself, as the methods page's rebuild does. The release is written into that same folder, and `open-altio serve` run there opens it.

To keep Altio's standard release beside one built your way, give each its own folder: build in one with no `rules.toml`, and in another with yours. Both read FDA's files from the same data folder, so they are fetched once.

There is nothing to pass on the command line, by design: a folder with a `rules.toml` builds the same release each time.

## What the release records

A release built with your rules records how they differ from Altio's standard, in `manifest.json` and `methods.json`: which rules were off, and which values changed, from what to what.

- **The explorer says so** ("Your rules: 2 off, 1 changed", with the list).
- **The methods page** at `/methods` shows your values beside Altio's.
- **A release built without a `rules.toml`** records no differences.

## Propose a change for everyone

If your change would make Open Altio better for everyone, [propose it](https://github.com/Altio-AI/open-altio/issues/new?template=rule.yml) with the counts from your own build. What a rule change needs in a pull request is in [CONTRIBUTING.md](https://github.com/Altio-AI/open-altio/blob/main/CONTRIBUTING.md#how-a-rule-changes).

How a rule file is laid out: [Rule files](../reference/rules.md).
