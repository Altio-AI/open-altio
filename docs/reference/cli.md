# The open-altio command

For anyone running Open Altio on their own machine: every command, what it does and what it needs.

Install it with `uv tool install open-altio` (or `pipx install open-altio`, or `pip install open-altio`). [Install](../use/explorer.md#install) says how to get uv.

Every command's `--help` gives a plain description, every option and a worked example. It is the full reference for options.

## open-altio

With no arguments, `open-altio` lists what you can do rather than its commands:

| To | Run |
|---|---|
| See the data | `open-altio demo` |
| Rebuild with all FDA data | `open-altio fetch`, then `open-altio build` |
| Change a rule | `open-altio serve`, then Rules |
| Something's wrong | `open-altio doctor` |

## demo

```sh
open-altio demo
```

Downloads FDA's latest quarterly file (about 65 MB, listed on [FDA's quarterly data extract page](https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html)) and DiAna's drug dictionary as `fetch` does. It builds a release from them (about 30 seconds and about 3 GB of memory at its peak; 2026Q2 holds about 415,000 cases) and opens the explorer in your browser.

- **`--no-open`** prints the explorer's address instead of opening it, for a machine with no browser.
- **`--port`** chooses the port, as for `serve`.
- **Run it again later** and it opens the same release without downloading or building again.

The demo release is one quarter only: see [the note on the demo](../use/explorer.md#first-run).

## fetch

```sh
open-altio fetch
```

Downloads every quarterly file FDA has published since 2004Q1 (90 quarters to 2026Q2, about 3.5 GB), with progress.

- **Stop it at any time;** run it again and it carries on where it stopped.
- **Each file is checked** against the size FDA's server gives and the checksums inside the zip, because FDA publishes no checksums.
- **DiAna's drug dictionary** (University of Bologna, CC BY 4.0) is downloaded too. The build reads each drug name to its ingredients through it. It is kept only when its checksum is the one [rule drug-names](https://github.com/Altio-AI/open-altio/blob/main/rules/drug-names.md) names.

## build

```sh
open-altio build
```

Builds a release from the files `fetch` downloaded, into the current folder.

- **Memory.** It is held to a memory limit by default so a laptop with 16 GB works, and spills to disk past it.
- **Your rules.** If the current folder holds a `rules.toml`, the build uses it and records how it differs from Altio's standard.
- **Drug ingredients.** Without DiAna's drug dictionary in the data folder, the release has no drug ingredients.

See [Rebuild from FDA's files](../customise/rebuild.md).

## serve

```sh
open-altio serve
```

Runs the explorer on `127.0.0.1`, so only your own machine can reach it. No sign-in, no telemetry. It opens the newest release in the current folder, else the demo's.

- **`--release`** names another release.
- **`--port`** names a port. If port 8000 is taken it uses the next free one.
- **`--meddra`** points it at the MedDRA release your organisation received from MSSO, unzipped. The release keeps what it needs, so you give it once.
- **`--rxnorm`, `--labels` and `--ime`** name the other files the release was built with, which the methods page's rebuild reads again, as it reads `--meddra` ([Rebuild it with your rules](../customise/rebuild.md#rebuild-it-with-your-rules)).

See [Run the explorer on your machine](../use/explorer.md). The explorer's methods page is where you switch rules and change their values.

## doctor

```sh
open-altio doctor
```

Checks:

- Python, memory and free disk;
- the explorer's port;
- the data folder with FDA's files, DiAna's drug dictionary and your releases;
- the versions installed and whether a newer `open-altio` is out;
- whether FDA can be reached.

It says in plain words what is wrong and how to fix it. When something needs fixing, it asks "Report this?". It changes nothing on your machine.

## report

```sh
open-altio report
```

Opens GitHub's new-issue page in your browser with the bug form filled in: what was run, the last error, your system and the versions. You add your own words and submit it.

- **Nothing is sent** until you submit it on GitHub, and the command never needs your GitHub login.
- **The address is printed too,** for a machine with no browser.
- **When any command crashes,** it offers to do this for you.

## Where the files go

FDA's files and the demo release live in one data folder, the platform's own place for an application's data:

| System | Data folder |
|---|---|
| macOS | `~/Library/Application Support/open-altio` |
| Linux | `~/.local/share/open-altio` (or `$XDG_DATA_HOME/open-altio`) |
| Windows | `%LOCALAPPDATA%\open-altio` |

Inside it:

- **`fda`** holds FDA's files.
- **`reference`** holds DiAna's drug dictionary.
- **`releases`** holds the demo release.
- The folder also keeps the last crash, for `open-altio report`, and any Improve this note still waiting to be sent.

`open-altio build` writes into the folder you run it in, beside your `rules.toml`. Three settings move things:

- `OPEN_ALTIO_DATA_DIR`: the whole data folder, for example to a bigger disk.
- `OPEN_ALTIO_FDA_DIR`: FDA's files only, if you keep them somewhere already.
- `OPEN_ALTIO_DIANA_DICTIONARY`: DiAna's drug dictionary, the file itself, if you keep it somewhere already.

## In a container

```sh
docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD:/data" ghcr.io/altio-ai/open-altio
```

Serves the newest release in the current folder at `http://127.0.0.1:8000`. Any command runs the same way, for example `... ghcr.io/altio-ai/open-altio demo --no-open`.

Inside the container the explorer listens on every address (the image sets `OPEN_ALTIO_HOST=0.0.0.0`), because the container's own `127.0.0.1` cannot be reached from outside it. Publishing the port on `127.0.0.1` as above keeps it reachable from your machine only.
