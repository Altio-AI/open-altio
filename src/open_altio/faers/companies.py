"""Put the company table in a release already built (rule company-names), with no rebuild.

    from open_altio.faers.companies import apply_company_table
    apply_company_table("releases/2026Q2")

    python -m open_altio.faers companies --release releases/2026Q2

`company_T` is worked out again from each row's own sender and report type, by the build's own
expression (derive.company), under the rules the release was built with: in the Parquet tables
that carry it and in the explorer database, with the sender table the explorer's Company filter
reads. A table whose company_T already is what the table gives is left as it is, so a second run
writes nothing. Each file is written beside and renamed into place: an explorer that has the old
database open goes on reading it until it restarts.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import duckdb

from open_altio import rulebook

from . import derive
from .explorer_db import EXPLORER_FILE, SENDERS, build_connection
from .reader import quoted, read_manifest, write_manifest
from .release import PARQUET_OPTIONS

# demo_T, and the two tables built from its rows (derive.demo_latest, derive.case_latest)
TABLES = ("demo_T", "demo_latest_T", "case_latest_T")
CASES = "explorer_case_T"
SENDER_TABLE = "explorer_sender_T"


def _given(row: str) -> str:
    """SQL: the company_T the table gives the row aliased `row`, joined to it as `m`."""
    return derive.company(f"{row}.mfr_sndr", f"{row}.rept_cod", "m.company")


def _joined(source: str, row: str) -> str:
    return f"{source} {row} LEFT JOIN {derive.COMPANY_TABLE} m ON m.fda_value = {row}.mfr_sndr"


def _differs(source: str, row: str = "r") -> str:
    """SQL: how many rows of `source` hold another company_T than the table gives."""
    return (
        f"SELECT count(*) FROM {_joined(source, row)} "
        f"WHERE {row}.company_T IS DISTINCT FROM {_given(row)}"
    )


def _rewrite(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    """The Parquet file again, its rows in the same order with company_T worked out again."""
    source = f"read_parquet({quoted(path.as_posix())}, file_row_number = true)"
    writing = path.with_name(f"{path.name}.writing")
    con.execute(
        f"COPY (SELECT r.* EXCLUDE (file_row_number) REPLACE ({_given('r')} AS company_T) "
        f"FROM {_joined(source, 'r')} ORDER BY r.file_row_number) "
        f"TO {quoted(str(writing))} ({PARQUET_OPTIONS})"
    )
    os.replace(writing, path)


def _explorer(release_dir: Path) -> int:
    """Put company_T in the explorer database and its sender table again, on a copy renamed over
    the old one. Returns the sender table's rows."""
    work = release_dir / ".explorer.companies"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    staged = work / EXPLORER_FILE
    shutil.copyfile(release_dir / EXPLORER_FILE, staged)
    con = build_connection(staged, spill=work / "spill")
    try:
        con.execute(derive.company_table())
        con.execute(
            f"UPDATE {CASES} SET company_T = n.company_T FROM ("
            f"SELECT c.case_id_T, {_given('c')} AS company_T FROM {_joined(CASES, 'c')}) n "
            f"WHERE {CASES}.case_id_T = n.case_id_T "
            f"AND {CASES}.company_T IS DISTINCT FROM n.company_T"
        )
        con.execute(f"DROP TABLE {SENDER_TABLE}")
        con.execute("CHECKPOINT")  # so the new sender table reuses the old one's room
        con.execute(SENDERS)
        rows = con.execute(f"SELECT count(*) FROM {SENDER_TABLE}").fetchall()[0][0]
        con.execute("CHECKPOINT")
    finally:
        con.close()
    return rows


def apply_company_table(release_dir: str | Path) -> dict:
    """Put the company table in a built release: company_T in each of TABLES and in the explorer
    database, as a build with the table writes it, with the manifest's sizes and the sender
    table's rows. Returns the rows changed per table and the seconds it took; nothing changed
    writes nothing."""
    started = time.monotonic()
    release_dir = Path(release_dir)
    manifest = read_manifest(release_dir)
    tables = manifest["tables"]
    spill = release_dir / ".companies.spill"
    built = rulebook.from_differences(manifest.get("user_rules") or {"off": [], "changed": []})
    changed: dict[str, int] = {}
    with rulebook.use_user_rules(built):
        con = build_connection(":memory:", spill=spill)
        try:
            con.execute("SET preserve_insertion_order = true")  # COPY keeps the ORDER BY
            con.execute(derive.company_table())
            for table in (t for t in TABLES if t in tables):
                path = release_dir / tables[table]["path"]
                source = f"read_parquet({quoted(path.as_posix())})"
                changed[table] = con.execute(_differs(source)).fetchall()[0][0]
                if changed[table]:
                    _rewrite(con, path)
            explorer = release_dir / EXPLORER_FILE
            if manifest.get("explorer") and explorer.exists():
                con.execute(f"ATTACH {quoted(str(explorer))} AS x (READ_ONLY)")
                changed[CASES] = con.execute(_differs(f"x.{CASES}", "c")).fetchall()[0][0]
                con.execute("DETACH x")
        finally:
            con.close()
            shutil.rmtree(spill, ignore_errors=True)
        senders = _explorer(release_dir) if changed.get(CASES) else None
    grown = 0
    for table in (t for t in TABLES if t in tables):
        size = (release_dir / tables[table]["path"]).stat().st_size
        grown += size - tables[table]["bytes"]
        tables[table]["bytes"] = size
    staged = release_dir / ".explorer.companies" / EXPLORER_FILE
    if senders is not None:
        entry = manifest["explorer"]
        entry["tables"][SENDER_TABLE]["rows"] = senders
        grown += staged.stat().st_size - entry["bytes"]
        entry["bytes"] = staged.stat().st_size
    if grown or senders is not None:
        manifest["release_bytes"] += grown
        write_manifest(release_dir, manifest)
    if senders is not None:
        os.replace(staged, release_dir / EXPLORER_FILE)
        shutil.rmtree(staged.parent)
    return {"changed": changed, "seconds": round(time.monotonic() - started, 1)}


__all__ = ["TABLES", "apply_company_table"]
