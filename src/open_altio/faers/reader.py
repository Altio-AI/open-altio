"""Open a release folder in DuckDB through its own files.

    from open_altio.faers import open_release, open_explorer
    con = open_release("releases/2026Q2")  # each table a view over its Parquet, then views.sql
    ex = open_explorer("releases/2026Q2")  # the explorer's database file, read only

Both read only what the release folder holds (src/open_altio/faers/README.md), so they
work on any copy of a release. Both go through `read_manifest`, which refuses a folder that is
not a finished release this version reads (`NotARelease`).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path

import duckdb

from . import formats

MANIFEST_FILE = "manifest.json"
EXPLORER_FILE = "explorer.duckdb"


class NotARelease(Exception):
    """A folder that is not a finished release this version of Open Altio reads, said in one
    plain line naming the folder."""

    def __init__(self, folder: Path, why: str) -> None:
        super().__init__(f"{folder.name} is not a release this Open Altio can read: {why}.")
        self.folder = folder


def read_manifest(release_dir: str | Path) -> dict:
    """The release's manifest, its format under today's name, or NotARelease. Every reader
    opens a release through this, so nothing is counted over an unfinished or unknown folder."""
    folder = Path(release_dir).resolve()
    path = folder / MANIFEST_FILE
    if not path.is_file():
        raise NotARelease(folder, f"it has no {MANIFEST_FILE}")
    manifest = formats.with_current_name(json.loads(path.read_text(encoding="utf-8")))
    if manifest.get("format") != formats.RELEASE:
        raise NotARelease(folder, f"its {MANIFEST_FILE} is not a release's")
    version = manifest.get("format_version")
    if version not in formats.READABLE_VERSIONS:
        raise NotARelease(
            folder, f"it is format version {version}, which this Open Altio does not read"
        )
    if version == 1:
        manifest.setdefault("source", formats.FAERS)
    if manifest.get("source") not in formats.SOURCES:
        raise NotARelease(folder, f"its source is {manifest.get('source')}, which it does not read")
    return manifest


def write_manifest(release_dir: str | Path, manifest: dict) -> None:
    """Write a release's manifest beside and rename it into place, so a reader never meets half
    of one."""
    path = Path(release_dir) / MANIFEST_FILE
    writing = path.with_name(f".{MANIFEST_FILE}.writing")
    writing.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.replace(writing, path)


def quoted(value: str) -> str:
    """`value` as an SQL string literal, for the places SQL takes no parameter (a file to read):
    each quote doubled, so nothing in it can end the string, and a NUL character, which would
    end the statement's text there, written as chr(0)."""
    return "'" + value.replace("'", "''").replace("\0", "' || chr(0) || '") + "'"


def sql_in(expr: str, values: Iterable[str]) -> str:
    """SQL: `expr IN (values)`, or false for no values, which SQL cannot write as an empty list."""
    listed = ", ".join(quoted(v) for v in values)
    return f"{expr} IN ({listed})" if listed else "false"


def register_release(
    con: duckdb.DuckDBPyConnection,
    release_dir: str | Path,
    *,
    tables: dict | None = None,
    temporary: bool = False,
    with_views: bool = True,
) -> None:
    """Create a view per release table over its Parquet file, then the
    release's own views (views.sql). `tables` is the manifest's `tables`
    entry, read from the folder when not given. Temporary views leave
    nothing behind in a database file."""
    release_dir = Path(release_dir).resolve()
    manifest = None
    if tables is None:
        manifest = read_manifest(release_dir)
        tables = manifest["tables"]
    kind = "TEMP VIEW" if temporary else "VIEW"
    for table, entry in tables.items():
        parquet = quoted(str(release_dir / entry["path"]))
        con.execute(f"CREATE {kind} {table} AS SELECT * FROM read_parquet({parquet})")
    if with_views:
        manifest = manifest or read_manifest(release_dir)
        sql = (release_dir / manifest["views"]["file"]).read_text(encoding="utf-8")
        if temporary:
            sql = sql.replace("CREATE VIEW ", "CREATE TEMP VIEW ")
        con.execute(sql)


def open_release(release_dir: str | Path) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection over the release: every table in
    manifest.json as a view of the same name over its Parquet, and the
    deduplicated views from views.sql."""
    con = duckdb.connect()
    register_release(con, release_dir)
    return con


def open_explorer(release_dir: str | Path) -> duckdb.DuckDBPyConnection:
    """The release's explorer database (explorer.duckdb), opened read only."""
    path = Path(release_dir) / EXPLORER_FILE
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} does not exist; build it with python -m open_altio.faers explorer "
            f"{release_dir}"
        )
    return duckdb.connect(str(path), read_only=True)
