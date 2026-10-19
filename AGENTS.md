# AGENTS.md

The guide for any agent (and any person) changing this repository. Read it before you start. A folder's README says what lives there and how to add one more; read it before working in that folder.

## What this is

Open Altio builds FAERS releases from FDA's quarterly files and lets one person explore them on their own machine. A release is a folder of Parquet tables, an explorer database, the funnel numbers, `methods.json` and a manifest. The hosted service at open.altioai.com runs the same explorer for approved people; its sign-in and people screens live in a private repository and plug in through the explorer's access hook.

## Setting it up for someone

When a person asks you to set Open Altio up so they can use it, not change it:

1. Install the command: `uv tool install open-altio` (or `pipx install open-altio`). From a clone, `uv sync --locked` and prefix each command with `uv run`.
2. Run `open-altio doctor` and tell them anything it says is short.
3. Run `open-altio demo`. It builds FDA's latest quarter in about 30 seconds and opens the explorer at `127.0.0.1`.
4. Only if they want all of FAERS: tell them it downloads about 3.5 GB and needs about 50 GB of free disk, then run `open-altio fetch`, `open-altio build` and `open-altio serve`.

The numbers each step needs are in `rules/machine-needs.md`; [the command reference](docs/reference/cli.md) lists every command.

## Layout

```
src/open_altio/
  faers/        load FDA's files, keep the latest version of each case, apply the deleted-case
                lists, flag duplicates, build a release; insights/ computes the methods data
  rulebook/     reads rules/ and the user's rules.toml; the only way code reads a rule value
  stats/        statistics over counts of cases from any source: EBGM, PRR, ROR, RRR, IC, screens
  explorer/     the data API and the local web app (ui/: small ES modules, no build step)
  cli/          the open-altio command
  testing/      invented FDA files and MedDRA releases, and the fixtures tests share
  paths.py      where the data folder is on each platform
  machine.py    memory facts, read the same way on every platform
rules/          one file per rule: values in front matter, then the rule in plain words
mappings/       reviewed cleaning data, such as legacy country names as ISO codes
notebooks/      the evidence behind each step, run against a release, committed with the outputs of that run (licensed MedDRA output cleared)
docs/           the MkDocs site, by reader
tests/          mirrors src/
scripts/        small tools run by hand, such as check.py (the gates every change passes)
```

Imports go one way: `cli` uses `explorer`, `faers` and `rulebook`; `explorer` uses `faers` and `rulebook`; `faers` uses `stats` and `rulebook`; `stats` uses `rulebook`. The explorer reads only finished release folders. Nothing in `src/open_altio` imports the hosted service, and a test fails if anything does. The explorer's access hook defaults to one local person who sees everything; keep it that way.

## Principles

- **Every number or policy is a rule.** It lives in a file in `rules/`, and code reads it with `open_altio.rulebook.value(rule, key)`. Never type a rule's value into code or tests; `tests/test_rules.py` fails if you do. A behaviour change and its rule file change in the same commit.
- **FDA's values stay verbatim.** Raw columns are loaded as text and never changed. Anything derived is a new column, table or view whose name ends in `_T`.
- **Duplicates are flagged, never deleted.** Every case stays in the case table; flags decide what the default view shows.
- **A change to which cases are kept is its own data release,** with a CHANGELOG entry and the before and after counts.
- **A release folder is the only hand-off.** Everything downstream reads it and nothing else.
- **Nothing licensed is committed:** no FDA zips, raw files, Parquet, DuckDB files, MedDRA files or WHO's ATC file. MedDRA and WHO files are read from a folder the user names; tests use invented fakes from `open_altio.testing`.
- **Keep asking how to do it more simply.** One way of doing each thing: one release reader, one audit writer, one home for MedDRA. No duplicated helpers.

## How we decide

Changes to how the data is cleaned, counted or shown are decided by Open Altio's maintainers, in the open, from evidence. Anyone can propose one; a maintainer decides it. Nothing that changes which cases are kept, or what a page says about them, ships on a contributor's judgement alone.

- **The path of a change.** Someone proposes it in an issue (Propose a rule change, or Data looks wrong). A notebook shows the evidence on a real release. A maintainer walks the notebook and decides each choice, and the decision is written on the issue. The rule file, code, test and docs then change together in one pull request, and a change to which cases are kept ships as its own data release with before and after counts. Until a maintainer has decided, a change is a proposal, however good it looks.
- **Evidence first.** A choice about the data (a new rule, a changed value, a new source) is made from a notebook in `notebooks/` run on a real release. The notebook shows the evidence as charts whose titles state what the data shows, sets out each choice with the numbers behind every option, and ships with its outputs. Accuracy comes before simplicity: make something simpler only if it stays exactly as accurate.
- **Count the way people read.** Counts on pages and in notebooks are over the cases a person sees, that is cases with `dup_kept_T` true, probable duplicates left out. Count cases, or distinct records by `era_T`, `primaryid`, `quarter_T` and `drug_seq`, never rows after a join: one record can have several rows. Join a case's drug and reaction rows on its own `quarter_T`.
- **Check every number twice.** Every number a person reads (on a page, in a chart, in a notebook) has a second, independent check, worked out apart from the code that makes the number (for example a separate query on the same release). The two must agree before the number ships; if they differ, find out which is right before changing either.
- **When unsure, do not hide.** Never call something known when it is not. A missing code, label or class shows as Not given (FDA gave nothing), Can't tell (more than one answer fits) or Not compared (there was nothing to compare against), and stays in view, because hiding it can hide a signal.
- **MedDRA is licensed.** Today's Preferred Term names may be shown to anyone. The hierarchy (system organ classes and the levels between), SMQs, lower level terms and every MedDRA code are shown only to a viewer with MedDRA: a verified subscriber on the hosted site, or a local copy given its own MedDRA files. A notebook output that shows them is cleared and replaced with a red note saying why.
- **Screens.** Use plain words a newcomer understands, and show no field that means nothing to its reader. Nothing moves when something opens, loads or changes. Use the app's own classes and look. Every chart has a plain title and a line saying how many of the cases it covers.
- **What "checked" means for a screen.** Two things, at every width the app is built for (today 320, 768, 1024 and 1440 pixels). An automated check drives the screen the way a person would and fails if anything scrolls sideways, overflows, overlaps or moves; a browser test is one way to do it. And someone actually looks at the screen at each width, beside the screens around it, before calling it done: a check that passes is not the same as a screen that looks right.
- **A new source** (another public database) takes the same shape as FAERS: its own steps and rule files, its own notebooks walked before its rules are switched on, its values kept verbatim with derived names ending in `_T`, and the same checks.

## Code

- Python 3.12, standard library first, typed. `ruff` (line length 100) and `mypy src` are clean.
- Small files with one job: a Python module stays under about 400 lines, a JS module under about 500.
- Comments say why, never what. No module docstring that lists endpoints. No defensive code for cases that cannot happen.
- Use the simplest standard words in code: sign-in page, audit events, dialogs, messages, clicks. Screen text is product copy; change it only when an issue asks.
- No process history in code, rules, tests or docs: no issue numbers, names of people, review rounds or dates. That history lives in the issue tracker and the CHANGELOG.
- Plain English in every message a person reads, short sentences, no em dashes.

## Checks

Set up once, with [uv](https://docs.astral.sh/uv/). The versions come from `uv.lock`, the browser the page tests draw in included:

```sh
uv sync --locked --extra dev
uv run playwright install --only-shell chromium
```

Before every commit:

```sh
uv run python scripts/check.py --all
```

That runs the text gates (no process history, private references, old names or em dashes), the code gates (no link made, no file path typed with a separator), `ruff check`, `ruff format --check`, `mypy src`, `mkdocs build --strict` and the fast test suite. `uv run python scripts/check.py` alone runs only the text and code gates, in a second. CI runs exactly these commands on Linux, macOS and Windows, with `OPEN_ALTIO_REQUIRE_BROWSER=1` so that a page test fails rather than skips when the browser is missing; set it yourself to be sure the pages were drawn. Tests over the real FAERS quarters are marked `slow`: `uv run pytest -q -m slow`.

Tests mirror `src/`. Shared helpers live in fixtures (`tests/conftest.py`) and fakes in `open_altio.testing`. A test names what it proves and checks both what the code does and what it refuses. Prefer a behaviour check to asserting a literal string of CSS or HTML.

## Issues

Every issue starts from one of the forms in `.github/ISSUE_TEMPLATE/`: report a bug, report wrong data, propose a rule change, suggest an idea, improve the docs. Keep the form's shape when you write one:

1. **In your own words:** what you saw or want, in a few sentences.
2. **The facts an agent needs:** the command or page, the release, the rule file, what you expected and why.
3. **Acceptance criteria:** a list of checks an agent can run and see pass or fail ("a test shows ...", "`open-altio build` on the demo release prints ..."). An issue with these gets the `status: ready` label.
4. **The output of `open-altio doctor` or `open-altio report`,** for anything that ran.

Report only what you have seen happen. If an agent drafted the issue for you, read it before you submit it: you own it.

## Pull requests

- One change per pull request, on its own branch. The title says what changed, in plain words.
- Fill in the template. The "I ran this" tick is required: you ran the checks and the change itself, on your machine.
- A behaviour change carries its rule file, its test and the docs page that describes it, in the same pull request.
- A change to which cases are kept also carries a CHANGELOG entry with the counts before and after on the same release.
- A person owns every pull request, however it was written, and answers the review.
- Commit messages: one line saying what changed, then why if it is not obvious. When an agent wrote the change, add a `Co-Authored-By:` line for it.

## Docs

The site is built from `docs/` with MkDocs Material (`mkdocs.yml` at the root): Use, Customise, Contribute, Reference, Methods. `uv run mkdocs serve` shows it as you write; `mkdocs build --strict` is one of the checks above. The docs workflow builds it alone with `uv sync --locked --extra docs` and `uv run mkdocs build --strict`.

- The first line of each page says who it is for.
- One fact, one place. Link instead of repeating; the methods page and the rule files are the home of every method.
- Plain English, short sentences, no em dashes.
- A page nobody needs is deleted. Fewer, better pages.

## Releases

A maintainer releases. The version goes into `pyproject.toml` and `CITATION.cff`, with its CHANGELOG entry, and a tag `v<version>` is pushed. The release workflow then runs the checks above, refuses a tag that does not name the version in `pyproject.toml`, builds the wheel and sdist with `uv build`, publishes them to PyPI by trusted publishing and pushes the container image to `ghcr.io/altio-ai/open-altio`.
