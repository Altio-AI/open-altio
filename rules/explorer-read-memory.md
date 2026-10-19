---
rule: explorer-read-memory
values:
  memory_limit_gb: 6
  warm_after_quiet_seconds: 2
enforced_in:
  - src/open_altio/explorer/release.py
  - src/open_altio/explorer/context.py
  - src/open_altio/explorer/meddra.py
  - tests/explorer/test_live_release.py
---
# The explorer reads within the service's box

The explorer reads the live release, and its licensed MedDRA part, through DuckDB held to at most `memory_limit_gb` of memory (`src/open_altio/explorer/release.py`). Past the limit DuckDB spills its sorts, joins and DISTINCTs to a temporary folder of its own, so a big question gets slower, not bigger.

- `memory_limit_gb`: DuckDB's memory limit for the explorer's reads, in GB, for every page's questions together; the licensed MedDRA part has the same limit of its own.
- `warm_after_quiet_seconds`: as a release opens, the explorer works out in the background what the search boxes read under no filter (the drugs, the reactions' cases, FDA's spellings with no ingredient, each drug class's cases), so a person's first search answers at once. It starts each part only after this many seconds in which no page asked anything, so the warming never slows a page being read.

**Why:** without a limit DuckDB takes up to 80% of the machine it runs on and keeps what it has read cached up to that. On a 64 GB Mac, over all 90 quarters to 2026Q2 with label flags and MedDRA 29.1, the first open of the Statistics tabs of dupilumab, sertraline, valsartan and sacubitril with valsartan took the explorer to a peak of 16 GB (35 GB with the records' route families), and its footprint stayed there. At 6 GB the same four opened in 2 to 5 seconds each and the explorer peaked at 5.7 GB. At 4 GB the All cases overview ran out of memory when its questions were asked side by side; at 6 GB the ten heaviest first questions asked at once all answered, with a peak of 7.6 GB. The explorer must fit beside the build (rule explorer-build-memory) and SQL (rule sql-limits) on the service's box, and on a 16 GB laptop.

A peak here is the process's physical footprint, as Activity Monitor shows it. The limit changes only memory and time, never an answer.
