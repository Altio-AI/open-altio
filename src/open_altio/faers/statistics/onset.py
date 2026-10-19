"""Each pair's time to onset (rule time-to-onset), on the cases the statistics count (cases.py):
over the suspect drug records that give the pair's ingredient, in the counted cases that name its
reaction, the median of their `time_to_onset_T`, how many records have one, and how many have
none, by why (dates.ONSET_REASONS). A drug is a drug record, so a case naming the ingredient in
two records counts two drugs.

    columns = summary(con, counts)    # con holds cases.count's tables and drug_onset_T

The median is taken in numpy over the sorted values, not by DuckDB, whose median keeps every
value of every pair in memory at once.
"""

from __future__ import annotations

import duckdb
import numpy as np

from open_altio import rulebook

from ..dates import ONSET_REASONS, ONSET_TABLE
from ..reader import quoted
from .cases import Counts

RULE = "time-to-onset"
# The statistics' name for each column, the reasons in their order.
REASON_COLUMNS = tuple(f"no_onset_{reason}" for reason in ONSET_REASONS)
COLUMNS = ("onset_days", "onset_drugs", *REASON_COLUMNS)

# Each suspect drug record of a kept case, with its ingredient, its time to onset and why it has
# none.
DRUG_DAYS = f"""
CREATE TEMP TABLE drug_days AS
SELECT s.cid, s.iid, o.time_to_onset_T AS days, o.time_to_onset_reason_T AS reason
FROM suspect_drug s JOIN kept_case k USING (cid)
JOIN {ONSET_TABLE} o ON o.era_T = k.era_T AND o.primaryid = k.primaryid
  AND o.quarter_T = k.quarter_T AND o.drug_seq = s.drug_seq;
DROP TABLE suspect_drug
"""
VALUES = """
SELECT d.iid::INTEGER, r.eid::INTEGER, d.days::INTEGER
FROM drug_days d JOIN counted_reaction r USING (cid) WHERE d.days IS NOT NULL ORDER BY 1, 2, 3
"""
NONE = """
SELECT d.iid, r.eid, {counts} FROM drug_days d JOIN counted_reaction r USING (cid)
WHERE d.reason IS NOT NULL GROUP BY ALL
"""


def summary(con: duckdb.DuckDBPyConnection, counts: Counts) -> dict[str, np.ndarray]:
    """COLUMNS for each pair of `counts`, in its order: `onset_days` empty where no drug has a
    value; every column empty when the rule is switched off, since then no drug has one."""
    size = len(counts.pairs["n"])
    if not rulebook.is_on(RULE):
        return {name: np.ma.masked_all(size, dtype=np.int64) for name in COLUMNS}
    width = np.int64(len(counts.reactions))
    pairs = counts.pairs["product"] * width + counts.pairs["event"]
    con.execute(DRUG_DAYS)
    iid, eid, days = con.execute(VALUES).fetchnumpy().values()
    at = np.searchsorted(pairs, np.asarray(iid, dtype=np.int64) * width + eid)
    days = np.asarray(days, dtype=np.float64)
    first = np.flatnonzero(np.diff(at, prepend=-1))  # where each pair's run of values starts
    many = np.diff(np.r_[first, len(at)])
    median = np.full(size, np.nan)
    median[at[first]] = (days[first + (many - 1) // 2] + days[first + many // 2]) / 2
    drugs = np.zeros(size, dtype=np.int64)
    drugs[at[first]] = many
    out = {"onset_days": median, "onset_drugs": drugs}
    found = con.execute(
        NONE.format(
            counts=", ".join(
                f"count(*) FILTER (WHERE d.reason = {quoted(r)})" for r in ONSET_REASONS
            )
        )
    ).fetchnumpy()
    iid, eid, *per_reason = found.values()
    at = np.searchsorted(pairs, np.asarray(iid, dtype=np.int64) * width + eid)
    for name, n in zip(REASON_COLUMNS, per_reason, strict=True):
        out[name] = np.zeros(size, dtype=np.int64)
        out[name][at] = n
    con.execute("DROP TABLE drug_days")
    return out
