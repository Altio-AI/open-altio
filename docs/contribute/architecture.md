# How the code fits together

For developers: the parts, which way data flows, and where a change belongs.

This page shows the flow from FDA's files to a release, the parts of the code, the rules that hold everywhere, and where each kind of change goes.

```
FDA's quarterly files (fis.fda.gov)
   │  open-altio fetch
   ▼
faers/            load verbatim as text; latest version of each case; deleted-case lists;
   │              duplicate flags; every derived name ends in _T
   │  rulebook/   every value the steps use, from rules/ and your rules.toml
   ▼
a release folder  Parquet, explorer.duckdb, funnel.json, methods.json, manifest.json
   │
   ├──> explorer/   the data API and the local web app, on 127.0.0.1; the methods page at /methods
   ├──> notebooks/  the evidence behind each step, rerun on the release
   └──> anything    Parquet and DuckDB, read by any tool
```

## The parts

```text
open-altio/
├── src/open_altio/
│   ├── faers/          FDA files to a release
│   ├── rulebook/       reads every rule value
│   ├── explorer/       data API and web app
│   ├── cli/            the open-altio command
│   ├── stats/          statistics over case counts
│   ├── labelreview/    review of uncertain label lines
│   ├── testing/        invented data for tests
│   ├── machine.py      machine memory facts
│   └── paths.py        where files live
├── rules/              one file per rule
├── mappings/           reviewed cleaning tables
├── notebooks/          evidence behind each step
├── docs/               this documentation site
├── scripts/            checks and maintenance helpers
├── tests/              the test suite
├── .github/            checks, releases, issue forms
├── README.md           start here
├── AGENTS.md           how agents work here
├── CLAUDE.md           points to AGENTS.md
├── CONTRIBUTING.md     how to contribute
├── CHANGELOG.md        what changed, by version
├── SECURITY.md         reporting a security problem
├── LICENSE             Apache-2.0
├── NOTICE              credits and third-party notices
├── CITATION.cff        how to cite
├── pyproject.toml      the package
├── uv.lock             pinned dependency versions
├── mkdocs.yml          the docs site
└── Dockerfile          the container image
```

## What holds everywhere

- **A release folder is the only hand-off.** The explorer and the notebooks read a release and nothing else, so any copy of a release works anywhere.
- **Raw is never changed.** FDA's columns stay as published; derived columns and tables end in `_T`.
- **Policy is data.** Numbers and policies live in `rules/` and are read through `open_altio.rulebook`. A test fails if a value is typed into code.
- **Cleaning decisions are data.** Reviewed mappings live in `mappings/`; code applies them.
- **Imports go one way.** `cli` runs the `explorer`, and both use `faers` and `rulebook`; nothing in `faers` knows about the explorer.

## The explorer's access hook

The explorer's app takes an access hook that answers two questions: who is viewing, and what may they see (MedDRA's licensed content, WHO's classes, SQL, exports).

- **The default** is one local person who sees everything the release and their own MedDRA files hold.
- **The hosted service** at open.altioai.com runs the same explorer with its own hook, which adds sign-in, approval and the MedDRA check. That code lives in a separate, private repository.
- **Nothing in `src/open_altio` imports it,** and a test fails if anything does.

## Where a change belongs

- **A new pipeline step:** a step in `faers/`, its rule file in `rules/`, its entry in the funnel and its step text for the methods page, its evidence in a notebook. A step that changes which cases are kept ships as its own data release.
- **A new rule value:** the rule file's front matter, read with `rulebook.value`.
- **A new filter or screen:** the explorer's data API and its UI module, with the rule it applies.
- **A new command:** a module in `cli/`, with a plain `--help` and a worked example.
