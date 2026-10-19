---
rule: explorer-build-memory
values:
  memory_limit_gb: 6
  threads: 4
  cases_per_part: 2000000
  spill_limit_gb: 20
enforced_in:
  - src/open_altio/faers/explorer_db.py
  - src/open_altio/explorer/rebuild.py
  - src/open_altio/faers/build.py
  - src/open_altio/faers/__main__.py
  - src/open_altio/faers/labeldict/flagbuild.py
  - src/open_altio/faers/meddra/licensed.py
  - src/open_altio/faers/statistics/step.py
  - tests/faers/test_explorer_db.py
  - tests/faers/test_build.py
  - tests/explorer/test_rebuild.py
---
# The explorer database builds within the service's box

Building `explorer.duckdb` (`src/open_altio/faers/explorer_db.py`) gives DuckDB at most `memory_limit_gb` of memory and `threads` worker threads. Past the limit DuckDB spills its sorts, joins and DISTINCTs to a folder inside the release's build folder, so the build gets slower, not bigger.

- `memory_limit_gb`: DuckDB's memory limit for the build, in GB.
- `threads`: DuckDB's worker threads for the build. Fewer threads hold fewer sort and hash buffers at once.
- `cases_per_part`: how many cases the explorer's case and child tables are written at a time.
- `spill_limit_gb`: the most the explorer database's build writes to its spill folder, in GB. A build that needs more stops and says so, rather than filling the disk.

**Why:** anyone should be able to build every quarter on a laptop with 16 GB of memory. Without a limit DuckDB takes up to 80% of the machine it runs on: on a 64 GB Mac the build peaked at 34 GB of resident memory. The whole process, Python included, must stay under 12 GB so the box keeps room for the service. With these values the same build peaked at 9.1 and 9.4 GB in two runs, in 3 to 5 minutes against 3.4 without them. DuckDB uses some memory outside its limit, so the limit sits about 3 GB below the target.

`open-altio build`, `open-altio demo` and the explorer's rebuild hold the whole release build to the same limit (`src/open_altio/faers/build.py`), so a laptop with 16 GB of memory builds every quarter, and so does adding MedDRA to a release already built (`src/open_altio/faers/meddra/licensed.py`), its statistics counted again included (`src/open_altio/faers/statistics/step.py`): on the 90 quarters to 2026Q2 that takes about seven minutes and peaks at 9.5 GB. Built this way on a Mac, all 90 quarters to 2026Q2 peaked at 8.6 GB and took 35 minutes, against about 13 minutes unlimited; the demo's one quarter peaks at 2.3 GB in about a minute, its statistics included. The statistics step counts on a connection of its own under the same limit and fits after closing it: over all 90 quarters it takes two to three minutes and peaks at 6.9 GB, below the rest of the build.

A peak here is the build's memory as the build records it (`peak_rss_bytes` in the manifest, `src/open_altio/machine.py`): on a Mac its physical footprint, as Activity Monitor shows it. macOS keeps counting memory a process has already given back as resident until something else needs it, so there resident memory adds each step's freed memory to the next step's: the same 90-quarter build peaked at 14.7 GB of resident memory while it never held more than 8.6 GB.

The label flags step holds its join of every suspect drug record with its case's reactions to the same limit.

DuckDB spills sorts, joins and DISTINCTs but not a `list()` aggregate's state, so the explorer lists each drug record's possible drug classes one quarter's cases at a time. Over all 90 quarters at once that list needed more than 18 GB and stopped the build; a quarter at a time, the classes tables take about a minute and the build stays under the limit.

The case table and the five child tables (drugs, reactions, outcomes, therapies, indications) are written `cases_per_part` cases at a time, in case order: each part's rows are joined and sorted alone, and the drug rows' ingredients and time to onset are read for the part's cases only, so neither memory nor spill grows with the release. Written whole, on all 90 quarters to 2026Q2, the case table spilled 13.4 GB and the drug table more than 20 GB, and a rebuild under this limit filled the disk. In parts of 2,000,000 cases the whole explorer database takes about ten minutes, its spill folder peaks at 8.6 GB (in the drug classes' tables, which are built a quarter at a time as below) and the build at 7.4 GB of memory. `spill_limit_gb` is more than twice that peak.

The limit changes only memory and time, never the file: the same tables, rows and values, stored in the same order. `scripts/compare_explorer_db.py` checks that against an earlier build.
