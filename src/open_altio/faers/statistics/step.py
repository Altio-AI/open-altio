"""The statistics step of the build: the release's own cases counted (cases.py), every pair
scored (scored.py) with its time to onset (onset.py), and its ROR by age band and by sex
(strata.py), written into the release as two tables, `statistics_T` and `statistics_strata_T`,
with what the manifest says about them under `statistics`.

    written, entry = build(staging, tables, memory_limit="6GB", threads=4)  # name -> table entry
    written, entry = build_classes(staging, tables)  # the same for each WHO class (classes.py)
    entry = recount(release_dir)    # a built release counted again by the MedDRA it now holds
    entry = add_as_published(release_dir)   # the set by FDA's text, into one built before it
    entry = add_classes(release_dir)    # the class statistics written into a built release

It runs after the release's Parquet is written, on a connection of its own over those files,
which it closes before the fit, so the fit's memory never adds to the counting's. Where the
release holds MedDRA, it reads the licensed mapping too and counts each reaction under its
current preferred term (rule statistics-cases); the table then names PTs, never a code, and the
same two tables are written again by FDA's text (`AS_PUBLISHED`), for a viewer the explorer
shows reactions as FDA wrote them. MedDRA added to a release already built
(meddra.build_licensed) counts it again the same way, so its Statistics tab names reactions as
its search and charts do. The class statistics are written by a step of their own, which a full
build runs after this one and `add_classes` runs over a release already built: one function, so
the two write the same tables.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from open_altio import rulebook

from ..dates import ONSET_TABLE
from ..drugnames.substances import INGREDIENTS
from ..explorer_db import CLASS_STATISTICS_TABLES, STATISTICS_TABLES, replace_statistics
from ..meddra import licensed_dir, read_licensed_manifest
from ..reader import EXPLORER_FILE, read_manifest, register_release, write_manifest
from . import cases, classes, onset, scored, strata

TABLE = "statistics_T"
STRATA_TABLE = strata.TABLE
# The two again, counted by FDA's text in a release that holds MedDRA, for a viewer shown
# reactions as FDA wrote them; a release without MedDRA counts by FDA's text already.
AS_PUBLISHED = {
    TABLE: "statistics_as_published_T",
    STRATA_TABLE: "statistics_strata_as_published_T",
}
# The statistics' name for each column of statistics_T: the scores, then the time to onset.
COLUMNS = (*scored.COLUMNS, *onset.COLUMNS)
COUNTED = ("case_latest_T", "drug_latest_T", "reac_latest_T", INGREDIENTS)
NEEDS = (*COUNTED, ONSET_TABLE)
MEDDRA_NEEDS = ("reac_meddra_T", "meddra_pt")


def by_current_pt(manifest: dict[str, Any]) -> tuple[str, ...]:
    """The release's statistics tables counted by current PT, which a viewer shown reactions as
    FDA wrote them is not given: they are given the AS_PUBLISHED ones instead. The class
    statistics have no second set, so such a viewer is given none of them."""
    entry = manifest.get("statistics") or {}
    by_class = manifest.get("class_statistics") or {}
    own = (entry["table"], entry["ror_strata"]["table"]) if _by_pt(entry) else ()
    return own + (tuple(by_class["tables"]) if _by_pt(by_class) else ())


def _by_pt(entry: dict[str, Any]) -> bool:
    return bool(entry.get("present")) and entry.get("reaction_key") == "meddra_pt"


def suffixed(name: str) -> str:
    """A column's name in the release (rule transformed-suffix-T)."""
    return name + rulebook.value("transformed-suffix-T", "derived_suffix")


def _column(values: np.ndarray | pa.Array) -> pa.Array:
    if isinstance(values, pa.Array):  # built as Arrow already
        return values
    if isinstance(values, np.ma.MaskedArray):  # a column the rules leave empty
        return pa.array(values.data, mask=np.ma.getmaskarray(values))
    if values.dtype.kind == "f":
        return pa.array(values, mask=np.isnan(values))  # a value the table cannot give is empty
    if values.dtype.kind in "iu":
        return pa.array(values)
    return pa.array(values.tolist(), type=pa.string())


def _connect(
    memory_limit: str | None, threads: int | None, spill: Path, spill_limit: str | None = None
) -> duckdb.DuckDBPyConnection:
    config: dict[str, Any] = {"temp_directory": str(spill)}
    if memory_limit:
        config["memory_limit"] = memory_limit
    if threads:
        config["threads"] = int(threads)
    if spill_limit:
        config["max_temp_directory_size"] = spill_limit
    con = duckdb.connect(config=config)
    con.execute("SET enable_progress_bar = false")
    con.execute("SET preserve_insertion_order = false")  # every count is ordered where it matters
    return con


def _meddra(release_dir: Path) -> tuple[str, dict[str, Any]] | None:
    """The release's MedDRA version and the licensed tables the count reads, or None."""
    manifest = read_licensed_manifest(release_dir)
    if not manifest or not manifest["meddra"]["versions"]:
        return None
    [(version, entry)] = manifest["meddra"]["versions"].items()  # one (rule meddra-version)
    return version, {name: entry["tables"][name] for name in MEDDRA_NEEDS}


def _held() -> dict[str, Any]:
    """The explorer build's memory, threads and spill (rules/explorer-build-memory.md), for a
    step a host runs over a built release beside the explorer."""
    rule = "explorer-build-memory"
    return {
        "memory_limit": f"{rulebook.value(rule, 'memory_limit_gb')}GB",
        "threads": int(rulebook.value(rule, "threads")),
        "spill_limit": f"{rulebook.value(rule, 'spill_limit_gb')}GB",
    }


def _write(
    release_dir: Path, name: str, columns: dict[str, Any], kind: str = "derived"
) -> dict[str, Any]:
    """One table into the release, its columns named with the derived suffix, and its manifest
    entry. Written beside and renamed into place, so a release already built never shows half
    a table."""
    path = f"parquet/{name}.parquet"
    arrow = pa.table({suffixed(k): _column(v) for k, v in columns.items()})
    writing = release_dir / f"{path}.writing"
    pq.write_table(arrow, writing, compression="zstd")
    os.replace(writing, release_dir / path)
    return {
        "path": path,
        "kind": kind,
        "rows": arrow.num_rows,
        "bytes": (release_dir / path).stat().st_size,
    }


def _one_set(
    release_dir: Path,
    tables: dict[str, Any],
    meddra: tuple[str, dict[str, Any]] | None,
    names: dict[str, str],
    memory_limit: str | None,
    threads: int | None,
    spill_limit: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Count, score and write one set of the two tables, named by `names` (TABLE and
    STRATA_TABLE -> the names they are written under), by current PT with `meddra`, else by
    FDA's text. Returns each table's manifest entry and the set's entry."""
    seconds: dict[str, float] = {}
    started = time.monotonic()
    spill = release_dir / ".statistics.spill"
    con = _connect(memory_limit, threads, spill, spill_limit)
    by = "meddra_pt" if meddra else "fda_text"
    try:
        needed = {name: tables[name] for name in NEEDS}
        register_release(con, release_dir, tables=needed, temporary=True, with_views=False)
        if meddra:
            register_release(
                con, licensed_dir(release_dir), tables=meddra[1], temporary=True, with_views=False
            )
        counts = cases.count(con, by)
        seconds["count"] = round(time.monotonic() - started, 2)
        lap = time.monotonic()
        onsets = onset.summary(con, counts)
        seconds["onset"] = round(time.monotonic() - lap, 2)
        lap = time.monotonic()
        found = strata.count(con, counts)
    finally:
        con.close()
        shutil.rmtree(spill, ignore_errors=True)
    # each table is written before the next is worked out, so their memory never adds up
    table, strata_table = names[TABLE], names[STRATA_TABLE]
    written = {strata_table: _write(release_dir, strata_table, strata.table(counts, found))}
    del found
    seconds["strata"] = round(time.monotonic() - lap, 2)
    lap = time.monotonic()
    columns, about = scored.score(counts)
    seconds["fit_and_score"] = round(time.monotonic() - lap, 2)
    lap = time.monotonic()
    written[table] = _write(release_dir, table, columns | onsets)
    seconds["write"] = round(time.monotonic() - lap, 2)
    seconds["total"] = round(time.monotonic() - started, 2)
    entry = {
        "present": True,
        "table": table,
        "reaction_key": by,
        **({"meddra_version": meddra[0]} if meddra else {}),
        "counted": {
            "cases": counts.cases,
            "ingredients": int(np.unique(counts.pairs["product"]).size),
            "reactions": int(np.unique(counts.pairs["event"]).size),
            "strata": len(counts.strata["n"]),
            "pairs": written[table]["rows"],
        },
        "ebgm": about,
        "ror_strata": {"table": strata_table, "by": strata.parts()},
        "seconds": seconds,
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
    """Write `parquet/statistics_T.parquet` and `parquet/statistics_strata_T.parquet` into the
    release folder from the tables it holds; where it holds MedDRA, counted by current PT, and
    the same two again by FDA's text under the names AS_PUBLISHED gives them, as a release
    without MedDRA counts them, for a viewer shown reactions as FDA wrote them. Returns each
    table's manifest entry by name (none when there are no statistics) and the `statistics`
    entry, which holds the second set's as `as_published`."""
    missing = [t for t in NEEDS if t not in tables]
    if missing:
        return {}, {
            "present": False,
            "reason": "The release has no drug ingredients to count (rule drug-names).",
        }
    meddra = _meddra(release_dir)
    own = {TABLE: TABLE, STRATA_TABLE: STRATA_TABLE}
    held = (memory_limit, threads, spill_limit)
    written, entry = _one_set(release_dir, tables, meddra, own, *held)
    if meddra:
        more, entry["as_published"] = as_published(
            release_dir, tables, memory_limit=memory_limit, threads=threads, spill_limit=spill_limit
        )
        written |= more
    return written, entry


def as_published(
    release_dir: Path,
    tables: dict[str, Any],
    *,
    memory_limit: str | None = None,
    threads: int | None = None,
    spill_limit: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The two tables counted by FDA's text under the names AS_PUBLISHED gives them, in a
    release that holds MedDRA: each table's manifest entry, and the set's entry. The build takes
    this step, and `add_as_published` takes it on a release built before it did."""
    return _one_set(release_dir, tables, None, AS_PUBLISHED, memory_limit, threads, spill_limit)


def recount(release_dir: str | Path) -> dict[str, Any] | None:
    """Count a built release's statistics again by the MedDRA version its licensed part holds
    now, as a build given that version does: `statistics_T`, `statistics_strata_T`, the
    manifest's `statistics` entry and the explorer database's copies, each replaced whole, and
    the class statistics too where the release has them (add_classes). Held
    to the explorer build's memory (rules/explorer-build-memory.md), since a host runs it beside
    the explorer. Returns the new entry; None, with nothing changed, for a release that has no
    statistics."""
    release_dir = Path(release_dir)
    manifest = read_manifest(release_dir)
    if not (manifest.get("statistics") or {}).get("present"):
        return None
    tables = dict(manifest["tables"])
    written, entry = build(release_dir, tables, **_held())
    if not written:
        return None
    # a second set the release no longer counts, once its MedDRA is gone, goes from the manifest
    for name in AS_PUBLISHED.values():
        tables.pop(name, None)
    manifest["tables"] = tables | written
    manifest["statistics"] = entry
    _finish(release_dir, manifest, STATISTICS_TABLES)
    if (manifest.get("class_statistics") or {}).get("present"):
        add_classes(release_dir)  # counted by the same reactions as the ingredients
    return entry


def add_as_published(release_dir: str | Path) -> dict[str, Any] | None:
    """Write into a built release that counted its statistics by current PT the same two tables
    counted by FDA's text, by the step its build now takes (`as_published`): the tables, their
    manifest entries, the statistics entry's `as_published` and the explorer database's copies.
    The rest of the release is left as it is. Each file is written beside and renamed into
    place, so a reader meets the old or the new, and a second run writes the same again. Held
    to the explorer build's memory, as `recount` is. Returns the set's entry; None, with
    nothing changed, for a release that counted by FDA's text, or has no statistics."""
    release_dir = Path(release_dir)
    manifest = read_manifest(release_dir)
    entry = manifest.get("statistics") or {}
    if not entry.get("present") or entry.get("reaction_key") != "meddra_pt":
        return None
    tables = dict(manifest["tables"])
    written, second = as_published(release_dir, tables, **_held())
    manifest["tables"] = tables | written
    manifest["statistics"] = entry | {"as_published": second}
    _finish(release_dir, manifest, STATISTICS_TABLES)
    return second


def _finish(release_dir: Path, manifest: dict[str, Any], explorer: dict[str, Any]) -> None:
    """The manifest with new statistics, and the explorer database's copies of `explorer`'s
    tables (STATISTICS_TABLES or CLASS_STATISTICS_TABLES) where it has one."""
    if (release_dir / EXPLORER_FILE).is_file():
        replace_statistics(release_dir, manifest, explorer)
    else:
        write_manifest(release_dir, manifest)


# The class table's columns: the ingredient table's scores with the class in the ingredient's
# place, and the level it is a class at.
CLASS_NAMES = {"ingredient": "class", "ingredient_cases": "class_cases"}
CLASS_COLUMNS = (
    "class",
    "level",
    *(CLASS_NAMES.get(c, c) for c in scored.COLUMNS if c != "ingredient"),
)


def build_classes(
    release_dir: Path,
    tables: dict[str, Any],
    *,
    memory_limit: str | None = None,
    threads: int | None = None,
    spill_limit: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write the class statistics (rule statistics-classes), `parquet/atc_statistics_T.parquet`
    and `parquet/atc_statistics_ingredients_T.parquet`, into the release folder from the tables
    it holds. Returns each table's manifest entry by name (none when the release has no classes
    or no ingredients) and the `class_statistics` entry."""
    if not all(t in tables for t in classes.needs()):
        return {}, {"present": False, "reason": "The release has no drug classes (rule atc-index)."}
    if not all(t in tables for t in COUNTED):
        return {}, {
            "present": False,
            "reason": "The release has no drug ingredients to count (rule drug-names).",
        }
    started = time.monotonic()
    spill = release_dir / ".statistics.spill"
    con = _connect(memory_limit, threads, spill, spill_limit)
    meddra = _meddra(release_dir)
    by = "meddra_pt" if meddra else "fda_text"
    try:
        needed = {name: tables[name] for name in (*COUNTED, *classes.needs())}
        register_release(con, release_dir, tables=needed, temporary=True, with_views=False)
        if meddra:
            register_release(
                con, licensed_dir(release_dir), tables=meddra[1], temporary=True, with_views=False
            )
        counts = cases.count(con, by)
        classes.prepare(con)
        found = {v["level"]: classes.at_level(con, counts, v["level"]) for v in classes.levels()}
    finally:
        con.close()
        shutil.rmtree(spill, ignore_errors=True)
    counted = round(time.monotonic() - started, 2)
    parts, links, levels = [], [], []
    for about in classes.levels():
        level_counts, level_links, with_class = found.pop(about["level"])
        columns, fit = scored.score(level_counts)
        rows = len(columns["reaction"])
        parts.append(
            {CLASS_NAMES.get(k, k): v for k, v in columns.items()}
            | {"level": np.full(rows, about["level"], dtype=np.int64)}
        )
        links.append(level_links)
        levels.append(
            about
            | {
                "classes": int(np.unique(level_counts.pairs["product"]).size),
                "cases": with_class,
                "pairs": rows,
                "ebgm": fit,
            }
        )
    lap = time.monotonic()
    linked = {k: np.concatenate([p[k] for p in links]) for k in classes.LINK_COLUMNS}
    by_ingredient = np.lexsort((linked["class"], linked["level"], linked["ingredient"]))
    linked = {k: v[by_ingredient] for k, v in linked.items()}  # stored as the explorer reads it
    written = {
        classes.TABLE: _write(
            release_dir,
            classes.TABLE,
            {k: np.concatenate([p[k] for p in parts]) for k in CLASS_COLUMNS},
            "classes",
        ),
        classes.INGREDIENTS_TABLE: _write(
            release_dir, classes.INGREDIENTS_TABLE, linked, "classes"
        ),
    }
    entry = {
        "present": True,
        "tables": list(written),
        "reaction_key": by,
        **({"meddra_version": meddra[0]} if meddra else {}),
        "could_be": classes.could_be(),
        "counted": {"cases": counts.cases, "pairs": written[classes.TABLE]["rows"]},
        "levels": levels,
        "seconds": {
            "count": counted,
            "fit_and_score": round(lap - started - counted, 2),
            "write": round(time.monotonic() - lap, 2),
            "total": round(time.monotonic() - started, 2),
        },
    }
    return written, entry


def record_classes(
    manifest: dict[str, Any], written: dict[str, Any], entry: dict[str, Any]
) -> None:
    """Put the class statistics' tables and entry into a release's manifest, in place of any it
    held. The tables join the classes layer's own, so whatever hides the classes hides them."""
    kept = {k: v for k, v in manifest["tables"].items() if k not in classes.TABLES}
    manifest["tables"] = kept | written
    layer = manifest.get("classes") or {}
    if layer.get("present"):
        layer["tables"] = [t for t in layer["tables"] if t not in classes.TABLES] + list(written)
    manifest["class_statistics"] = entry


def add_classes(release_dir: str | Path) -> dict[str, Any]:
    """The class statistics written into a release already built, as a full build writes them
    (build_classes): the two tables, the manifest's entries and the explorer database's copies,
    each replaced whole. Held to the explorer build's memory, as recount is. Returns the entry;
    for a release without classes or ingredients, why it has none."""
    release_dir = Path(release_dir)
    manifest = read_manifest(release_dir)
    written, entry = build_classes(release_dir, dict(manifest["tables"]), **_held())
    record_classes(manifest, written, entry)
    _finish(release_dir, manifest, CLASS_STATISTICS_TABLES)
    return entry
