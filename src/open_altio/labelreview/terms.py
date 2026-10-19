"""MedDRA's preferred terms, from the release's licensed part, as the label step reads them.

A coding names the preferred terms of one MedDRA version: the version folder the review
folder is (`licensed/meddra/<version>/`, where the label step writes its items and reads the
frozen codings), or else the one the release is built with, the
newest it holds (rule meddra-version). Every term an agent or the reviewer names is checked
against it, so a misspelt or retired term never reaches a flag.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from open_altio.faers.meddra import MEDDRA_DIR, licensed_dir, newest, read_licensed_manifest

from .store import Refused

PT_TABLE = "meddra_pt"


def find_release(start: Path) -> Path | None:
    """The release a licensed folder sits in: the nearest folder above with a licensed manifest."""
    for folder in (start, *start.parents):
        if read_licensed_manifest(folder) is not None:
            return folder
    return None


def current_pts(release: Path | None, start: Path) -> dict[str, str]:
    """Each preferred term of the version, by its name in lower case, spelt as MedDRA spells it."""
    release = release or find_release(start)
    if release is None:
        raise Refused(
            f"No release with MedDRA's licensed part holds {start}. Name one with --release."
        )
    manifest = read_licensed_manifest(release) or {"meddra": {"versions": {}}}
    versions = manifest["meddra"]["versions"]
    if start.parent.name == MEDDRA_DIR and start.name not in versions:
        raise Refused(
            f"{release} holds MedDRA {', '.join(versions) or 'none'}, not {start.name}. "
            "A coding names the preferred terms of the version the release is built with."
        )
    version = start.name if start.name in versions else newest(versions)
    if version is None or PT_TABLE not in versions[version]["tables"]:
        raise Refused(f"{release} holds no MedDRA version for {start}.")
    path = licensed_dir(release) / versions[version]["tables"][PT_TABLE]["path"]
    with duckdb.connect() as con:
        rows = con.execute("SELECT pt_name FROM read_parquet(?)", [str(path)]).fetchall()
    return {name.casefold(): name for (name,) in rows}


def check_pts(names: list[str], known: dict[str, str]) -> tuple[list[str], list[str]]:
    """The names spelt as MedDRA spells them, without repeats, and the names that are not PTs."""
    spelt: list[str] = []
    unknown: list[str] = []
    for name in names:
        found = known.get(" ".join(name.split()).casefold())
        if found is None:
            unknown.append(name)
        elif found not in spelt:
            spelt.append(found)
    return spelt, unknown
