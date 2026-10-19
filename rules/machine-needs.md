---
rule: machine-needs
values:
  demo_memory_gb: 4
  build_memory_gb: 12
  demo_disk_gb: 2
  build_disk_gb: 50
enforced_in:
  - src/open_altio/cli/doctor.py
  - src/open_altio/explorer/rebuild.py
  - tests/cli/test_doctor.py
  - tests/explorer/test_rebuild.py
---
# What a machine needs to run Open Altio

`open-altio doctor` checks this machine's memory and free disk against these numbers, and says in plain words when it falls short and what to do. The explorer's methods page says the same numbers before a rebuild with someone's rules, the demo's for a release of one quarter and a build of every quarter's otherwise, and does not start the rebuild when the disk that holds the release has less free room than that.

- `demo_memory_gb`: memory for `open-altio demo`, one quarter. The 2026Q2 demo build peaks at about 2.3 GB.
- `build_memory_gb`: memory for a build of every quarter. The build holds DuckDB to the limit in rule `explorer-build-memory` and peaks at about 9 GB, so a 16 GB laptop has room and an 8 GB one does not.
- `demo_disk_gb`: free disk for the demo: FDA's latest quarterly file and the release built from it.
- `build_disk_gb`: free disk for every quarter: FDA's files (about 3.5 GB), the release and the build's scratch space. Rebuilding all 90 quarters to 2026Q2 under rule `explorer-build-memory`, the build's working database and spill folder reached 38 GB while it was still working out the cases, and writing the release adds its 8 GB of Parquet before the working database goes, so a build needs at least 46 GB; 50 leaves a little room. The explorer database's own build needs less (about 24 GB with its spill).

**Why:** a build that runs out of memory or disk fails late and says little. Checking first says what is short and how to fix it.
