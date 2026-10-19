---
rule: sql-result-download
values:
  max_rows: 2000000
enforced_in:
  - src/open_altio/explorer/sql_files.py
  - tests/explorer/test_downloads.py
---
# A SQL result downloads whole up to 2,000,000 rows

On the Tables and SQL page, a query's whole result downloads as Parquet or CSV, not just the page shown. Up to `max_rows` rows it comes as one file. Past that it is refused, and the person is pointed to the table downloads on the same page, to run the query on their own machine.

CSV also stops at Excel's limit (rule `export-csv-row-cap`), counted the same way: the result's rows plus the header line. Between that and `max_rows` a result comes as Parquet only.

The download runs the query again under rule `sql-limits`: the same timeout, memory limit and one query at a time per person. It is handed to the access hook with its SQL text and format, so a host can log it; the explorer on its own keeps nothing.

**Why:** a SQL result is written on the service's own small box and sent from it, while the table downloads come straight from the object store. 2,000,000 rows is about twice what Excel opens, so Parquet still takes results CSV cannot; on the widest table it is a file of about 100 MB written in seconds. A result larger than that is most of a table, and the table itself is the better download.
