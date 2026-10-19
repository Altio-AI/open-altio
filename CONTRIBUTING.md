# Contributing

For anyone who wants to report something, propose a change or send a pull request: code, rules, mappings, notebooks or docs. Thank you for helping.

## In short

1. **Open an issue** with the form that fits.
2. **Wait for `status: ready`** before anything bigger than a small fix.
3. **Set up and run the checks** on your machine.
4. **Send one change per pull request,** with its rule file, its test and its docs.
5. **Answer the review.** A person owns every pull request, however it was written.

## Open an issue

Using the explorer? Press "Improve this" at the top right of any page instead. It sends your note straight to us.

Pick the form that fits on the [new issue page](https://github.com/Altio-AI/open-altio/issues/new/choose): report a bug, report wrong data, propose a rule change, suggest an idea, or improve the docs. If you ran the command, `open-altio report` opens the bug form with what you ran, the error and your system filled in.

- **We aim to reply within a week.** A maintainer replies on your issue with the next step: confirmed with a label, a question, or a no with the reason.
- **`status: ready` means go.** The issue has acceptance criteria an agent can check, and we agree on the approach.

## Contributions made with AI

Welcome, and openly. Use whatever tools help you.

- **A person owns each issue and each pull request.** You have read it, you have run it, and you answer the review.
- **Agents read [AGENTS.md](AGENTS.md).** It says how this repository is laid out and how an issue and a pull request are written here.

## Set up and run the checks

You need Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/Altio-AI/open-altio
cd open-altio
uv sync --locked --extra dev
uv run playwright install --only-shell chromium
uv run python scripts/check.py --all
```

| Command | What it runs |
|---|---|
| `uv run python scripts/check.py --all` | Everything a pull request must pass, as CI does: the text gates, `ruff check`, `ruff format --check`, `mypy src`, `mkdocs build --strict` and the fast test suite, the page tests in a headless browser included. |
| `uv run pytest -q -m slow` | The slow tests over the real FAERS quarters, once you have fetched them (`open-altio fetch`). |

## How a rule changes

Every number or policy Open Altio applies is a file in [`rules/`](rules/): its values at the top, then the rule in plain words, why, and the code and tests that enforce it. Code reads the values from the file, so the rule and the behaviour cannot drift apart.

A rule changes in one pull request that holds:

1. **The rule file:** its values, its plain words and its why.
2. **Its test:** one that fails before the change and passes after.
3. **The docs:** the page that describes the behaviour, if there is one.

If the change moves which cases are kept, add a CHANGELOG entry with the counts before and after on the same release; it ships as its own data release.

To try a rule change first, use the methods page of your own explorer (`open-altio serve`). It needs no code change at all.

## Other kinds of change

- **Code.** A test that fails before your change and passes after.
- **A mapping** in [`mappings/`](mappings/). Each row names its evidence and who reviewed it. See [mappings/README.md](mappings/README.md).
- **A notebook** in [`notebooks/`](notebooks/). Commit it with the outputs of a run on the release named in its first cell, with any licensed MedDRA output cleared (see [notebooks/README.md](notebooks/README.md)).
- **Docs** in [`docs/`](docs/). See the site as you write with `uv run mkdocs serve`. `scripts/check.py --all` builds it with `mkdocs build --strict`, which fails on a broken link.

## Ground rules for the data

- **FDA's values stay exactly as published.** Anything derived ends in `_T`.
- **Duplicates are flagged, never deleted.**
- **Nothing licensed is committed:** no FDA zips, raw files, Parquet, DuckDB files, MedDRA files or WHO's ATC file.

## Pull requests

Fill in the template, including the "I ran this" tick. Keep each pull request to one change. A maintainer reviews every one, and nothing is released automatically.

## Nothing to sign

There is no CLA and no DCO. What you contribute is licensed under Apache-2.0, as the [licence](LICENSE) says in section 5, and you keep your copyright.
