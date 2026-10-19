"""Reading a release's label tables and its licensed MedDRA part, and naming columns,
for the label steps."""

from __future__ import annotations

from pathlib import Path

import duckdb

from open_altio import rulebook

from ..meddra import licensed_dir, read_licensed_manifest
from ..reader import read_manifest

SUFFIX_RULE = "transformed-suffix-T"
LABELS = "labels_T"
CANDIDATES = "label_candidates_T"
SECTIONS = "label_sections_T"


class LabelRefused(Exception):
    """The release lacks what the label step reads; the message says what."""


def col(name: str) -> str:
    """A label column as the release names it: every column we derive ends in the derived
    suffix (rule transformed-suffix-T), and the label's set ID is written as one word."""
    suffix = rulebook.value(SUFFIX_RULE, "derived_suffix")
    return ("setid" if name == "set_id" else name) + suffix


def require_suffix(table: str, columns: list[str]) -> None:
    suffix = rulebook.value(SUFFIX_RULE, "derived_suffix")
    wrong = [c for c in [table, *columns] if not c.endswith(suffix)]
    if wrong:
        raise LabelRefused(f"{table}: {', '.join(wrong)} must end in {suffix}")


def quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def connect() -> duckdb.DuckDBPyConnection:
    """A connection that draws no progress bar, which would land in the command's output."""
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    return con


def rows(sql: str, params: list | None = None) -> list[tuple]:
    con = connect()
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def has_table(release_dir: Path, table: str) -> bool:
    return table in read_manifest(release_dir)["tables"]


def public(release_dir: Path, table: str) -> str:
    tables = read_manifest(release_dir)["tables"]
    if table not in tables:
        raise LabelRefused(f"{release_dir} has no {table}; build the release with its labels")
    return f"read_parquet({quoted(str(release_dir / tables[table]['path']))})"


def held_version(release_dir: Path) -> tuple[dict, str, dict]:
    """The licensed manifest, the release's one MedDRA version and its entry: the labels are
    coded with the version the release's reactions were read to (rule meddra-version)."""
    manifest = read_licensed_manifest(release_dir) or {"meddra": {"versions": {}}}
    versions = manifest["meddra"]["versions"]
    if len(versions) != 1:
        raise LabelRefused(f"{release_dir} holds no MedDRA version; add one with the meddra step")
    ((version, entry),) = versions.items()
    return manifest, version, entry


def licensed(release_dir: Path, entry: dict, table: str) -> str:
    if table not in entry["tables"]:
        raise LabelRefused(f"MedDRA {entry['version']} in {release_dir} has no {table}")
    path = licensed_dir(release_dir) / entry["tables"][table]["path"]
    return f"read_parquet({quoted(str(path))})"
