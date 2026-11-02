"""Quarter-end counts, worked out once by the build so the statistics can be read as they stood
at the end of every quarter without counting the release again: the cases the statistics count
(cases.py, rule statistics-cases), each placed in one quarter, counted by quarter and stratum.

    written, entry = build(staging, tables, memory_limit="6GB", threads=4)  # name -> table entry
    entry = add_quarters(release_dir)    # the same into a release built before the build did

    quarter_strata_T            qnum_T, the stratum's parts (age_band_T, sex_T, receipt_year_T),
                                cases_T: the counted cases placed in that quarter and stratum
    reaction_quarter_strata_T   reaction_T, named as statistics_T names it, then the same
                                columns: the counted cases naming the reaction
    reaction_quarter_strata_as_published_T    the reaction table counted by FDA's text, in a
                                release counted by current PT, for a viewer shown reactions as
                                FDA wrote them

A case is placed in the quarter of its received day (rule received-day, read through
dates.received_quarter), else, where that day is empty, in the quarter of its own file. Each
counted case is in one quarter, so summed over every quarter the tables give the statistics'
own margins, and running sums over qnum_T give them at each quarter's end. An ingredient's own
cells are small and are counted when asked. A release with MedDRA reads every reaction FDA wrote
to a PT (rule meddra-terms refuses a MedDRA file that leaves one out), so the cases counted are
the same by PT and by FDA's text, and one quarter_strata_T serves both.

The tables are Parquet only: the explorer's database holds no copy, so adding them to a built
release changes nothing else in its folder.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from ..dates import received_day, received_quarter
from ..meddra import licensed_dir
from ..reader import quoted, read_manifest, register_release, write_manifest
from . import cases
from .step import COUNTED, _connect, _held, _meddra, suffixed

QUARTERS = "quarter_strata_T"
REACTIONS = "reaction_quarter_strata_T"
AS_PUBLISHED = "reaction_quarter_strata_as_published_T"
TABLES = (QUARTERS, REACTIONS, AS_PUBLISHED)

# Each counted case's quarter, as yyyyq.
PLACED = """
CREATE TEMP TABLE case_quarter AS
SELECT k.cid, CAST({quarter} AS INTEGER) AS qnum
FROM kept_case k JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
WHERE k.cid IN (SELECT cid FROM counted_case)
"""

# The counted cases by quarter and stratum; then each reaction's, counted by stratum number
# first and given the stratum's parts after, so the join to them is over the counted rows.
SELECTS = {
    QUARTERS: """
SELECT q.qnum AS {qnum}, {parts}, count(*) AS {cases}
FROM counted_case c JOIN case_quarter q USING (cid)
GROUP BY ALL ORDER BY ALL""",
    REACTIONS: """
WITH n AS (
  SELECT r.eid, q.qnum, r.sid, count(*) AS n
  FROM counted_reaction r JOIN case_quarter q USING (cid) GROUP BY ALL),
s AS (SELECT DISTINCT sid, {plain} FROM counted_case)
SELECT x.name AS {reaction}, n.qnum AS {qnum}, {parts}, n.n AS {cases}
FROM n JOIN s USING (sid) JOIN reaction_id x USING (eid)
ORDER BY ALL""",
}


def place(con: duckdb.DuckDBPyConnection, by: str = "fda_text") -> list[str]:
    """The counted cases on `con` (cases.prepare), each with its quarter, as the temporary table
    case_quarter. Returns the stratum's parts."""
    parts = cases.prepare(con, by)
    con.execute(PLACED.format(quarter=received_quarter("c")))
    return parts


def select(table: str, parts: list[str]) -> str:
    """The SELECT of QUARTERS or REACTIONS over the tables `place` made, its columns named as the
    release names them."""
    source = "s" if table == REACTIONS else "c"
    return SELECTS[table].format(
        qnum=suffixed("qnum"),
        cases=suffixed("cases"),
        reaction=suffixed("reaction"),
        plain=", ".join(parts),
        parts=", ".join(f"{source}.{p} AS {suffixed(p)}" for p in parts),
    )


def _copy(con: duckdb.DuckDBPyConnection, release_dir: Path, name: str, sql: str) -> dict:
    """One table written into the release from `sql`, beside and renamed into place, so a
    release already built never shows half a table; and its manifest entry."""
    path = f"parquet/{name}.parquet"
    writing = release_dir / f"{path}.writing"
    con.execute(f"COPY ({sql}) TO {quoted(str(writing))} (FORMAT parquet, COMPRESSION zstd)")
    os.replace(writing, release_dir / path)
    return {
        "path": path,
        "kind": "derived",
        "rows": pq.ParquetFile(release_dir / path).metadata.num_rows,
        "bytes": (release_dir / path).stat().st_size,
    }


def _one_set(
    release_dir: Path,
    tables: dict[str, Any],
    meddra: tuple[str, dict[str, Any]] | None,
    names: dict[str, str],
    limits: tuple[str | None, int | None, str | None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Count and write the tables `names` gives (QUARTERS and REACTIONS -> the names they are
    written under), reactions by current PT with `meddra`, else by FDA's text. Returns each
    table's manifest entry and the set's entry."""
    started = time.monotonic()
    spill = release_dir / ".quarter_statistics.spill"
    con = _connect(limits[0], limits[1], spill, limits[2])
    by = "meddra_pt" if meddra else "fda_text"
    try:
        register_release(
            con,
            release_dir,
            tables={name: tables[name] for name in COUNTED},
            temporary=True,
            with_views=False,
        )
        if meddra:
            register_release(
                con, licensed_dir(release_dir), tables=meddra[1], temporary=True, with_views=False
            )
        parts = place(con, by)
        [(n_cases, n_reactions, n_quarters)] = con.execute(
            "SELECT (SELECT count(*) FROM counted_case), "
            "(SELECT count(DISTINCT eid) FROM counted_reaction), "
            "(SELECT count(DISTINCT qnum) FROM case_quarter)"
        ).fetchall()
        counted = round(time.monotonic() - started, 2)
        con.execute("SET preserve_insertion_order = true")  # COPY keeps the ORDER BY
        written = {
            name: _copy(con, release_dir, name, select(t, parts)) for t, name in names.items()
        }
    finally:
        con.close()
        shutil.rmtree(spill, ignore_errors=True)
    entry = {
        "reaction_key": by,
        **({"meddra_version": meddra[0]} if meddra else {}),
        "reaction_table": names[REACTIONS],
        "counted": {"cases": n_cases, "reactions": n_reactions, "quarters": n_quarters},
        "tables": {n: {"rows": w["rows"], "bytes": w["bytes"]} for n, w in written.items()},
        "seconds": {
            "count": counted,
            "write": round(time.monotonic() - started - counted, 2),
            "total": round(time.monotonic() - started, 2),
        },
    }
    return written, entry


def build(
    release_dir: Path,
    tables: dict[str, Any],
    *,
    memory_limit: str | None = None,
    threads: int | None = None,
    spill_limit: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write QUARTERS and REACTIONS into the release folder from the tables it holds, and, where
    it holds MedDRA, the reaction table again by FDA's text as AS_PUBLISHED. Returns each table's
    manifest entry by name (none when the release has no statistics) and the `quarter_statistics`
    entry, which holds the second set's as `as_published`."""
    if not all(t in tables for t in COUNTED):
        return {}, {
            "present": False,
            "reason": "The release has no drug ingredients to count (rule drug-names).",
        }
    started = time.monotonic()
    limits = (memory_limit, threads, spill_limit)
    meddra = _meddra(release_dir)
    own = {QUARTERS: QUARTERS, REACTIONS: REACTIONS}
    written, first = _one_set(release_dir, tables, meddra, own, limits)
    entry = {"present": True, "received_day": received_day(), "table": QUARTERS, **first}
    if meddra:
        more, entry["as_published"] = _one_set(
            release_dir, tables, None, {REACTIONS: AS_PUBLISHED}, limits
        )
        written |= more
    entry["seconds"]["total"] = round(time.monotonic() - started, 2)
    return written, entry


def add_quarters(release_dir: str | Path) -> dict[str, Any]:
    """Write the quarter-end counts into a release already built, by the build's own step
    (build): the tables and their manifest entries and the `quarter_statistics` entry, each
    replaced whole, and nothing else in the folder. Held to the explorer build's memory
    (rules/explorer-build-memory.md), as statistics.recount is. A second run writes the same
    again. Returns the entry; for a release without statistics, why it has none."""
    release_dir = Path(release_dir)
    manifest = read_manifest(release_dir)
    written, entry = build(release_dir, dict(manifest["tables"]), **_held())
    # a table a release no longer counts, once its MedDRA is gone, goes from the manifest
    kept = {k: v for k, v in manifest["tables"].items() if k not in TABLES}
    manifest["tables"] = kept | written
    manifest["quarter_statistics"] = entry
    write_manifest(release_dir, manifest)
    return entry
