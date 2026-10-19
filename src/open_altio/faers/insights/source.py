"""Open a release folder for the insight notebooks.

    from open_altio.faers.insights.source import connect, release_folder
    con = connect(release_folder())       # $OPEN_ALTIO_RELEASE
    con = connect("releases/2026Q2")

Every table keeps its release name (`case_latest_T`, `demo_T`, `drug_latest_T`, ...), the
release's views are there too (`case_dedup_T`, ...), and each raw table FDA published is also
open as `<table>_all` (`demo_all`, `drug_all`, ...), the name the notebooks use for every row
FDA ever published, and `input_lines_T` holds the lines of FDA's files the load split back.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import duckdb

from open_altio.faers.reader import MANIFEST_FILE, read_manifest, register_release

RELEASE_ENV = "OPEN_ALTIO_RELEASE"
HOW_TO_GET_ONE = "build one with `open-altio demo` or `open-altio build`"


def release_folder(path: str | Path | None = None, setting: str = RELEASE_ENV) -> Path:
    """The release a notebook reads: `path` when given, else the folder the environment
    variable `setting` names. Raises FileNotFoundError, saying how to get a release, when
    neither names one."""
    given = path or os.environ.get(setting)
    if not given:
        raise FileNotFoundError(
            f"no release folder: set {setting}, or the variable for it in the "
            f"notebook's first code cell; {HOW_TO_GET_ONE}"
        )
    folder = Path(given).expanduser()
    if not (folder / MANIFEST_FILE).is_file():
        raise FileNotFoundError(
            f"{folder} is not a release folder (no {MANIFEST_FILE}); {HOW_TO_GET_ONE}"
        )
    return folder


def connect(release: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """An in-memory connection over a release folder's files (release_folder)."""
    folder = release_folder(release)
    con = duckdb.connect()
    _quiet(con)
    register_release(con, folder)
    manifest = read_manifest(folder)
    for table, entry in manifest["tables"].items():
        if entry["kind"] == "raw":
            con.execute(f'CREATE VIEW "{table}_all" AS SELECT * FROM "{table}"')
    _input_lines(con, manifest)
    return con


def _input_lines(con: duckdb.DuckDBPyConnection, manifest: dict) -> None:
    """The lines of FDA's files the load split back apart (rules/overlong-lines.md), from the
    manifest, as `input_lines_T`: one row per line, with the records it held."""
    lines = [
        (entry["quarter"], entry["table"], line["line"], line["records"])
        for entry in manifest.get("inputs", [])
        for line in entry.get("overlong_lines") or []
    ]
    con.execute(
        "CREATE TEMP TABLE input_lines_T "
        "(quarter_T VARCHAR, table_T VARCHAR, line_T BIGINT, records_T INTEGER)"
    )
    if lines:
        con.executemany("INSERT INTO input_lines_T VALUES (?, ?, ?, ?)", lines)


def _quiet(con: duckdb.DuckDBPyConnection) -> None:
    """No progress bar. Inside a Jupyter kernel DuckDB refuses to change the
    setting without ipywidgets; it draws no bar there anyway."""
    with contextlib.suppress(duckdb.InvalidInputException):
        con.execute("SET enable_progress_bar = false")
