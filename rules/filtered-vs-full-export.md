---
rule: filtered-vs-full-export
values:
  filtered_filename_marker: FILTERED
  filtered_manifest: manifest.json
enforced_in:
  - src/open_altio/explorer/export.py
  - tests/explorer/test_export.py
  - tests/explorer/test_access.py
---
# A filtered export can never be mistaken for the full data

- Full release: on the Tables and SQL page, every table, a layer or one table as Parquet (original and `_T`), with sizes. A deduplicated view (`case_dedup_T` and the rest) has no file of its own: it comes as the tables it reads and `views.sql`, which makes it.
- Filtered export: the Export button in a page's toolbar beside Filters, for the cases the filters select. File name carries `FILTERED`; a `manifest.json` inside records filters, release and time.
- The two are never placed side by side.

**Why:** a subset taken for all of FAERS gives wrong counts, so a filtered file says what it is in its name and in the manifest it carries.
