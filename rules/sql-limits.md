---
rule: sql-limits
values:
  timeout_seconds: 30
  memory_limit_gb: 4
  concurrent_queries_per_user: 1
  access: read_only
  threads: 2
  rows_shown: 300
enforced_in:
  - src/open_altio/explorer/sql.py
  - src/open_altio/explorer/tables.py
  - src/open_altio/explorer/api.py
  - tests/explorer/test_sql.py
  - tests/explorer/test_api.py
  - tests/explorer/test_downloads.py
---
# SQL is read-only DuckDB with hard limits

**Why:** the whole service runs on one small box; anyone hitting the limits should take the full release.

**How it is enforced:** SQL on the Tables and SQL page (`POST /api/sql`) queries the live release's own tables (a view per Parquet file in `manifest.json`) and its deduplicated views (`views.sql`), through a DuckDB catalog opened read only. DuckDB is locked down after the views are made: external access off except reading the release's Parquet files, extensions never installed or loaded, configuration locked. Only a single `SELECT` statement runs; anything else is refused before it reaches DuckDB.

- `timeout_seconds`: a query still running after this is interrupted. The SQL box says so, with this number.
- `memory_limit_gb`: DuckDB's memory limit for all SQL queries together (one box), with `threads` worker threads.
- `concurrent_queries_per_user`: a second query from the same person while one runs is refused.
- `rows_shown`: the rows one page of results holds. The answer says how many rows the whole query gives, and the person pages through them; counting them and fetching the page share one `timeout_seconds`. The full answer is for the downloads.

`threads` and `rows_shown` are the sizes the box takes; change them here.
