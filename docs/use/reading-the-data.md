# FDA or Open Altio: reading the data

For anyone counting cases in Open Altio, or comparing it with another FAERS source.

This page says which values are FDA's and which are ours, how reports become cases, and what FAERS cannot tell you.

## Two labels

Every column is marked **FDA** or **Open Altio**, in the explorer, in downloads and on the methods page.

- **FDA** columns hold exactly what FDA published, as text: nothing trimmed, corrected or filled in. Their names are FDA's, in lower case. Where the legacy AERS files and the FAERS files spell the same column two ways (`isr` and `primaryid`, `gndr_cod` and `sex`), one name is used for both; the [data dictionary](../reference/data-dictionary.md#column-names) lists every such case.
- **Open Altio** columns, tables and views have names that end in `_T`. They are worked out from FDA's: dates as dates, ages in years, weights in kilograms, countries as ISO codes, the latest version of each case, the duplicate flags.

The explorer shows Open Altio's value, with a small "FDA: x" beside it when FDA's differs. A legacy AERS case shows its country as United States, with "FDA: UNITED STATES" beside it.

## From report versions to cases

FDA publishes report versions: each time a sender adds information to a case, a new version arrives. Open Altio counts cases.

1. **One latest version of each case.** The newest version FDA published, across AERS and FAERS. AERS and FAERS share one case numbering, so a case FDA carried from AERS into FAERS in 2012 counts once, as a FAERS case.
2. **Less the cases on FDA's deleted-case lists,** in both eras. They stay in `demo_T` and `demo_latest_T`, so you can still find them.
3. **Probable duplicates flagged.** Two cases are probable duplicates when either of these holds:
    - **The AEOLUS rule matches them:** the same event date, age, sex, country, drugs and reactions, every one of them filled in.
    - **They carry the same manufacturer case number** from the same sender.

    Each group shows one copy, the latest received, and sets the others aside. The group is dated by its earliest receipt (`group_first_dt_T`), which the received-date filters and sorting use. Nothing is deleted: the set-aside copies stay in the case table, each saying which copy is shown instead and why. One switch in the explorer shows them again.

Counts are always of cases, never of rows.

How each step works, why, and how many cases it moved on the release you are looking at is on [the methods page](../methods/index.md).

## What FAERS cannot tell you

- **Cause is not certain.** There is no certainty that a reported event was caused by the product. FDA does not require proof of a causal relationship before it accepts a report.
- **Detail can be thin.** Reports do not always hold enough detail to evaluate an event.
- **Not every event is reported.** FDA does not receive a report for every event that happens, and many things influence whether one is reported.
- **No population rates.** FAERS cannot tell you how often an event happens in the population.
- **Our work is ours.** Open Altio's deduplication and derived fields are our own work, and FDA has not reviewed or endorsed them.

## Opening a release yourself

A release is a folder of Parquet files any tool can read. The [data dictionary](../reference/data-dictionary.md) describes every table. From Python, with Open Altio installed:

```python
from open_altio.faers import open_release

con = open_release("<release folder>")  # DuckDB, with every table and view registered
con.sql("SELECT count(*) AS cases FROM case_dedup_T").show()
```

- **`case_dedup_T`** is the default view: the cases kept after flagging duplicates.
- **`case_latest_T`** holds every case, duplicates included, with their flags.
