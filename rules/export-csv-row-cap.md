---
rule: export-csv-row-cap
values:
  csv_row_cap: 1048576
enforced_in:
  - src/open_altio/explorer/export.py
  - src/open_altio/explorer/sql_files.py
  - src/open_altio/explorer/downloads.py
  - tests/explorer/test_export.py
  - tests/explorer/test_downloads.py
---
# CSV exports stop at Excel's row limit

A filtered export above 1,048,576 rows is offered as Parquet only. Rows are counted per CSV file, header included, as Excel counts them: the export holds cases, their drugs and their reactions, and CSV is offered only while the largest of the three fits.

A SQL result's download (rule `sql-result-download`) is one file and stops at the same number of lines, header included; past it the result comes as Parquet.

**Why:** a CSV bigger than Excel can open helps nobody and costs the server; anyone that large should take Parquet or the full release.
