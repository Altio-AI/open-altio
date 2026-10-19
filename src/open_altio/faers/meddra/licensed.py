"""Build the licensed MedDRA part of a release: its one MedDRA version, in a folder of its own
with its own manifest, beside the public part and never in it.

A release holds one MedDRA version, the newest held when it is built, and everything in it uses
that version (rule meddra-version). A release build given a MedDRA folder reads FDA's terms to it
in its own database and writes this part with the rest of the release (`source`, `map_licensed`,
`write_licensed`); `build_licensed` does the same for a release already built, and counts its
statistics again by the new version's PTs, as a build with it would. Writing another version
replaces the one held. Rebuilding the public release replaces the whole folder, so give
the build the MedDRA folder, or run this step again afterwards. A host that keeps versions
itself, each unpacked as `<held>/<version>/MedAscii/`, gives a release build the newest of them
(`newest_held`), or reads a built release to it with `add_held`.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NamedTuple

import duckdb

from open_altio import rulebook

from .. import formats
from ..reader import MANIFEST_FILE, quoted, read_manifest
from ..sources import sha256
from .files import (
    FILES,
    RELEASE_FILE,
    SUBDIR,
    VERBATIM_TABLES,
    MeddraRefused,
    ascii_folder,
    read_release_file,
    read_table,
)
from .terms import MAPPING_TABLES, map_terms, stopping
from .versions import newest, release_date

LICENSED_DIR = "licensed"
LICENSED_MANIFEST = "manifest.json"
MEDDRA_DIR = "meddra"
LICENSED_FORMAT = formats.LICENSED
DERIVED_TABLES = MAPPING_TABLES
LICENSED_TABLES = VERBATIM_TABLES + DERIVED_TABLES
# Files a person wrote into the version's folder for the label step: reviewed codings of label
# phrases and the MedDRA groups the label rules read. Writing the same version again keeps them.
LABEL_CODINGS_FILE = "label_codings_frozen.jsonl"
LABEL_GROUPS_FILE = "label_groups.json"
# The label review's record of that work (src/open_altio/labelreview), so a rebuild loses no
# decision: its batches, the agent's suggestions, the reviewer's decisions, the blind redo and
# the hand check of rule-made flags.
LABEL_REVIEW_FILES = {
    "batches": "label_batches.jsonl",
    "suggestions": "label_suggestions.jsonl",
    "decisions": "label_decisions.jsonl",
    "redo_set": "label_redo_set.json",
    "redo_answers": "label_redo_answers.jsonl",
    "rule_check": "label_rule_check.json",
}
KEPT_ON_REBUILD = (LABEL_CODINGS_FILE, LABEL_GROUPS_FILE, *LABEL_REVIEW_FILES.values())


class Source(NamedTuple):
    """A MedDRA ASCII release, checked: its MedAscii folder, version and language."""

    folder: Path
    version: str
    language: str


def licensed_dir(release_dir: str | Path) -> Path:
    return Path(release_dir) / LICENSED_DIR


def read_licensed_manifest(release_dir: str | Path) -> dict | None:
    path = licensed_dir(release_dir) / LICENSED_MANIFEST
    if not path.is_file():
        return None
    return formats.with_current_name(json.loads(path.read_text(encoding="utf-8")))


def older_part(entry: dict) -> bool:
    """Whether a version's licensed part was written by an older Open Altio: without the terms
    report or the text to PT tables (DERIVED_TABLES). The explorer serves the release without it,
    and adding the same version again writes it anew."""
    return "terms" not in entry or any(t not in entry.get("tables", {}) for t in DERIVED_TABLES)


def older_words(version: str) -> str:
    """What the explorer and the doctor say of a release whose MedDRA part is an older one."""
    return (
        f"MedDRA {version} was added to this release by an older version of Open Altio, so the "
        "explorer shows the release without MedDRA. To add it again, run open-altio serve "
        f"--meddra <folder>, with the folder of MedDRA {version} you unzipped."
    )


def source(meddra_dir: str | Path) -> Source:
    """The MedDRA release in `meddra_dir` (it or its MedAscii/), once every file FILES reads
    is there and it is in the rule's language. Raises MeddraRefused otherwise."""
    where = ascii_folder(meddra_dir)
    missing = [n for n in FILES if not (where / n).is_file()]
    if missing:
        raise MeddraRefused(f"not in {where}: {', '.join(missing)}")
    version, language = read_release_file(where)
    wanted = rulebook.value("meddra-version", "language")
    if language.lower() != str(wanted).lower():
        raise MeddraRefused(
            f"MedDRA {version} is in {language}; the tier serves {wanted} only "
            "(rule meddra-version)"
        )
    return Source(where, version, language)


def load(con: duckdb.DuckDBPyConnection, where: Path) -> None:
    """MedDRA's files, as the tables FILES names, in `con`."""
    for name, (table, *_spec) in FILES.items():
        con.register(f"_{table}", read_table(where, name))
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _{table}")
        con.unregister(f"_{table}")


def _older_than_the_data(version: str, report: dict) -> str:
    parts, total = [], 0
    for column in stopping(report):
        unmapped = report["columns"][column]["unmapped"]
        first, last = (q.upper() for q in unmapped["quarters"])
        total += unmapped["texts"]
        parts.append(
            f"{unmapped['texts']:,} {'text' if unmapped['texts'] == 1 else 'texts'} in {column} "
            f"({unmapped['rows']:,} rows, {first} to {last})"
        )
    return (
        f"{' and '.join(parts)} {'is' if total == 1 else 'are'} no name in MedDRA {version} or "
        "in its history file: the MedDRA file is older than this release's data. Use the "
        "newest MedDRA version."
    )


def map_licensed(con: duckdb.DuckDBPyConnection, meddra: Source) -> dict:
    """Load `meddra` into `con`, which holds FDA's reac and indi tables, and read FDA's terms to
    it (terms.map_terms). Returns the report. Raises MeddraRefused when a reaction text matches
    nothing: the MedDRA file is older than the data (rule meddra-version)."""
    load(con, meddra.folder)
    report = map_terms(con, meddra.version)
    if stopping(report):
        raise MeddraRefused(_older_than_the_data(meddra.version, report))
    return report


def write_licensed(
    con: duckdb.DuckDBPyConnection,
    release_dir: Path,
    release: str,
    meddra: Source,
    report: dict,
    *,
    released: date | None = None,
) -> dict:
    """Write the licensed tables `con` holds (map_licensed) into release_dir/licensed/ as the
    release's one MedDRA version, replacing any other it held (rule meddra-version), and record
    it in the licensed manifest. Returns that version's entry."""
    released = released or release_date(meddra.version)
    root = licensed_dir(release_dir)
    manifest = read_licensed_manifest(release_dir) or {
        "format": LICENSED_FORMAT,
        "release": release,
        "meddra": {"versions": {}},
    }
    rel_dir = f"{MEDDRA_DIR}/{meddra.version}"
    target = root / rel_dir
    staging = root / MEDDRA_DIR / f".{meddra.version}.building"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    tables = {}
    try:
        for table in LICENSED_TABLES:
            path = staging / f"{table}.parquet"
            con.execute(f"COPY {table} TO {quoted(str(path))} (FORMAT parquet, COMPRESSION zstd)")
            tables[table] = {
                "path": f"{rel_dir}/{table}.parquet",
                "kind": "derived" if table in DERIVED_TABLES else "meddra",
                "rows": con.execute(f"SELECT count(*) FROM {table}").fetchall()[0][0],
                "bytes": path.stat().st_size,
            }
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if target.exists():
        for name in KEPT_ON_REBUILD:
            if (target / name).is_file():
                os.replace(target / name, staging / name)
        shutil.rmtree(target)
    os.replace(staging, target)
    for other in manifest["meddra"]["versions"]:
        if other != meddra.version:
            shutil.rmtree(root / MEDDRA_DIR / other, ignore_errors=True)
    entry = {
        "version": meddra.version,
        "language": meddra.language,
        "released": released.isoformat(),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_files": {n: sha256(meddra.folder / n) for n in FILES},
        "tables": tables,
        "terms": report,
    }
    manifest["meddra"]["versions"] = {meddra.version: entry}
    write_licensed_manifest(release_dir, manifest)
    return entry


def write_licensed_manifest(release_dir: str | Path, manifest: dict) -> None:
    path = licensed_dir(release_dir) / LICENSED_MANIFEST
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def keep_person_files(old_release: str | Path, new_release: str | Path) -> list[str]:
    """Copy the files a person wrote into the old release's MedDRA version folder (the label
    step's groups, the reviewed codings and the label review's record) into the new release
    built with the same version, as writing the same version again keeps them. Returns their
    names; none when the new release holds another version or none."""
    held = (read_licensed_manifest(old_release) or {"meddra": {"versions": {}}})["meddra"]
    built = (read_licensed_manifest(new_release) or {"meddra": {"versions": {}}})["meddra"]
    kept: list[str] = []
    for version in set(held["versions"]) & set(built["versions"]):
        was, now = (licensed_dir(r) / MEDDRA_DIR / version for r in (old_release, new_release))
        for name in KEPT_ON_REBUILD:
            if (was / name).is_file():
                shutil.copyfile(was / name, now / name)
                kept.append(name)
    return kept


def report_lines(version: str, report: dict) -> list[str]:
    """The build's log lines for FDA's terms read to MedDRA `version` (map_licensed's report)."""
    lines = []
    for column, got in report["columns"].items():
        unmapped = got["unmapped"]
        lines.append(
            f"MedDRA {version}, {column}: {got['texts']:,} distinct texts, "
            f"{got['former_names']:,} placed through the history file, "
            f"{unmapped['texts']:,} matching nothing ({unmapped['rows']:,} rows)"
        )
    off = [
        f"{q['quarter'].upper()} (nearest {q['nearest']}, {q['rows_off']:,} rows off)"
        for q in report["quarters_fitting_no_version"]
    ]
    lines.append(
        f"MedDRA {version}: quarters fitting no single version: {', '.join(off) or 'none'}"
    )
    return lines


def build_licensed(
    release_dir: str | Path,
    meddra_dir: str | Path,
    *,
    released: date | None = None,
    overwrite: bool = False,
) -> dict:
    """Read a built release to one MedDRA version, in its licensed part, replacing any other
    version it held, and record it in the licensed manifest; then count its statistics again
    by that version's current PTs (statistics.recount) and the methods' numbers (numbers.write).
    Returns the version's entry.

    Raises MeddraRefused when the folder is not a release, MedDRA's files are missing or
    malformed, the release is not in the rule's language, a reaction text matches nothing in
    it (the file is older than the data), or the version is already held (pass overwrite=True
    to replace it)."""
    release_dir = Path(release_dir).expanduser()
    if not (release_dir / MANIFEST_FILE).is_file():
        raise MeddraRefused(f"{release_dir} is not a release folder (no {MANIFEST_FILE})")
    public = read_manifest(release_dir)
    meddra = source(meddra_dir)
    licensed = read_licensed_manifest(release_dir) or {"meddra": {"versions": {}}}
    if meddra.version in licensed["meddra"]["versions"] and not overwrite:
        raise MeddraRefused(
            f"MedDRA {meddra.version} is already in {licensed_dir(release_dir)}; "
            "pass overwrite=True to replace it"
        )
    spill = licensed_dir(release_dir) / ".spill"
    con = duckdb.connect()
    try:
        # held to the build's memory, since the service runs this step beside the explorer
        memory = rulebook.value("explorer-build-memory", "memory_limit_gb")
        con.execute(f"SET memory_limit = '{memory}GB'")
        con.execute(f"SET threads = {int(rulebook.value('explorer-build-memory', 'threads'))}")
        con.execute(f"SET temp_directory = {quoted(str(spill))}")
        con.execute("SET enable_progress_bar = false")
        # views, not tables: the texts are read straight from the Parquet, in a fraction of the
        # memory
        for table in ("reac", "indi"):
            path = quoted(str(release_dir / public["tables"][table]["path"]))
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet({path})")
        report = map_licensed(con, meddra)
        entry = write_licensed(
            con, release_dir, public["release"], meddra, report, released=released
        )
    finally:
        con.close()
        shutil.rmtree(spill, ignore_errors=True)
    # imported here, not above: the statistics step and the methods' numbers read the licensed
    # part this module writes
    from ..insights import numbers
    from ..statistics import recount

    recount(release_dir)
    from ..insights.methods import refresh_cards

    refresh_cards(  # the cards that count with MedDRA, and the recounted statistics'
        release_dir,
        memory_limit=f"{rulebook.value('explorer-build-memory', 'memory_limit_gb')}GB",
        threads=int(rulebook.value("explorer-build-memory", "threads")),
    )
    numbers.write(
        release_dir,
        memory_limit=f"{rulebook.value('explorer-build-memory', 'memory_limit_gb')}GB",
        threads=int(rulebook.value("explorer-build-memory", "threads")),
    )
    return entry


def held_versions(held_root: str | Path) -> dict[str, Path]:
    """version -> its folder, for each MedDRA release kept in `held_root` as
    `<version>/MedAscii/`. Folders starting with a dot are work in progress."""
    root = Path(held_root).expanduser()
    found: dict[str, Path] = {}
    if not root.is_dir():
        return found
    for folder in sorted(root.iterdir()):
        if folder.name.startswith(".") or not (folder / SUBDIR / RELEASE_FILE).is_file():
            continue
        version, _language = read_release_file(folder / SUBDIR)
        found[version] = folder
    return found


def newest_held(held_root: str | Path) -> Path | None:
    """The folder of the newest version kept in `held_root`, or None when none is: the version a
    release build takes up (rule meddra-version)."""
    held = held_versions(held_root)
    version = newest(held)
    return held[version] if version else None


def add_held(release_dir: str | Path, held_root: str | Path) -> list[str]:
    """Read a built release to the newest version held (rule meddra-version), unless it holds
    it already from the same files. Returns the version built, or none."""
    held = held_versions(held_root)
    version = newest(held)
    if version is None:
        return []
    licensed = read_licensed_manifest(release_dir) or {"meddra": {"versions": {}}}
    have = licensed["meddra"]["versions"].get(version, {})
    where = ascii_folder(held[version])
    if not older_part(have) and have.get("source_files") == {n: sha256(where / n) for n in FILES}:
        return []
    build_licensed(release_dir, held[version], overwrite=True)
    return [version]
