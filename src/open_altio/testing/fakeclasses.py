"""An invented drug classes layer on a built release, for the explorer's tests: the three
`atc_*_T` tables the release step writes (src/open_altio/faers/README.md), with every name
made up and every substance code in a fourth level WHO does not use (`ZZ`, `ZY`).

    add_classes(folder)      the layer on the fake release's drug records, with the statistics of
                             its classes, the explorer database rebuilt; returns the manifest's
                             `classes` entry
    add_classes(folder, GROUP_CLASS)
                             the same, with a class above one class only that holds records of
                             its own
    remove_classes(folder)   the release as one built without the layer

Each substance of the fake quarters gets one way a class is chosen:

    acetylsalicylic acid   can't tell: B01ZZ01 (platelets) or N02ZZ01 (pain)
    warfarin               only one code, B01ZY01
    digoxin                only one code, C01ZZ01
    ibuprofen              a shared class, M01ZZ (level 4): M01ZZ01 or M01ZZ51
    omeprazole             only one code, A02ZZ01
    metformin              only one code, A10ZZ01

With GROUP_CLASS, as WHO's C09A (ACE inhibitors) holds C09AA alone and FAERS reports naming only
"an ACE inhibitor" are classed at C09A itself:

    valsartan              only one code, C09ZZ01
    adalimumab             a group's class, C09Z (level 3), whose one class under it is C09ZZ
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from open_altio.faers import build_explorer_db, read_manifest
from open_altio.faers.explorer_db import CLASS_LAYER
from open_altio.faers.reader import MANIFEST_FILE, quoted
from open_altio.faers.statistics import add_classes as add_class_statistics
from open_altio.faers.statistics import record_classes

YEAR = 2026
CITATION = "Invented classes for tests; not WHO's."
# (code, level, name)
INDEX = [
    ("A", 1, "INVENTED DIGESTION MEDICINES"),
    ("A02", 2, "INVENTED ACID MEDICINES"),
    ("A02Z", 3, "INVENTED ULCER MEDICINES"),
    ("A02ZZ", 4, "Invented pump inhibitors"),
    ("A02ZZ01", 5, "omeprazole"),
    ("A10", 2, "INVENTED SUGAR MEDICINES"),
    ("A10Z", 3, "INVENTED GLUCOSE LOWERING MEDICINES"),
    ("A10ZZ", 4, "Invented biguanides"),
    ("A10ZZ01", 5, "metformin"),
    ("B", 1, "INVENTED BLOOD MEDICINES"),
    ("B01", 2, "INVENTED CLOT MEDICINES"),
    ("B01Z", 3, "INVENTED ANTITHROMBOTIC AGENTS"),
    ("B01ZY", 4, "Invented vitamin antagonists"),
    ("B01ZY01", 5, "warfarin"),
    ("B01ZZ", 4, "Invented platelet inhibitors"),
    ("B01ZZ01", 5, "acetylsalicylic acid"),
    ("C", 1, "INVENTED HEART MEDICINES"),
    ("C01", 2, "INVENTED HEART BEAT MEDICINES"),
    ("C01Z", 3, "INVENTED ACE GLYCOSIDES"),
    ("C01ZZ", 4, "Invented ACE digitalis glycosides"),
    ("C01ZZ01", 5, "digoxin"),
    ("M", 1, "INVENTED MUSCLE MEDICINES"),
    ("M01", 2, "INVENTED INFLAMMATION MEDICINES"),
    ("M01Z", 3, "INVENTED ANTIINFLAMMATORY AGENTS"),
    ("M01ZZ", 4, "Invented propionic acids"),
    ("M01ZZ01", 5, "ibuprofen"),
    ("M01ZZ51", 5, "ibuprofen, combinations"),
    ("N", 1, "INVENTED NERVE MEDICINES"),
    ("N02", 2, "INVENTED PAIN MEDICINES"),
    ("N02Z", 3, "INVENTED ANALGESICS"),
    ("N02ZZ", 4, "Invented salicylic acids"),
    ("N02ZZ01", 5, "acetylsalicylic acid"),
]
# substance -> (its class, how it was chosen, its possible codes)
CHOSEN = {
    "acetylsalicylic acid": (None, "cannot_tell", ["B01ZZ01", "N02ZZ01"]),
    "warfarin": ("B01ZY01", "only_code", ["B01ZY01"]),
    "digoxin": ("C01ZZ01", "only_code", ["C01ZZ01"]),
    "ibuprofen": ("M01ZZ", "shared_class", ["M01ZZ01", "M01ZZ51"]),
    "omeprazole": ("A02ZZ01", "only_code", ["A02ZZ01"]),
    "metformin": ("A10ZZ01", "only_code", ["A10ZZ01"]),
}
# (more index rows, more substances' classes), for add_classes
GROUP_CLASS = (
    [
        ("C09", 2, "INVENTED PRESSURE MEDICINES"),
        ("C09Z", 3, "INVENTED PRESSURE AGENTS"),
        ("C09ZZ", 4, "Invented angiotensin blockers"),
        ("C09ZZ01", 5, "valsartan"),
    ],
    {
        "valsartan": ("C09ZZ01", "only_code", ["C09ZZ01"]),
        "adalimumab": ("C09Z", "group_class", ["C09Z"]),
    },
)
_KEY = "era_T, primaryid, quarter_T, drug_seq"


def _write(con: duckdb.DuckDBPyConnection, folder: Path, table: str) -> dict:
    path = f"parquet/{table}.parquet"
    con.execute(f"COPY {table} TO {quoted(str(folder / path))} (FORMAT parquet)")
    [(rows,)] = con.execute(f"SELECT count(*) FROM {table}").fetchall()
    return {"path": path, "kind": "classes", "rows": rows, "bytes": (folder / path).stat().st_size}


def _save(folder: Path, manifest: dict) -> None:
    (folder / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def add_classes(folder: Path, more: tuple[list, dict] = ([], {})) -> dict:
    """Write the invented layer, and `more` of it (GROUP_CLASS), into the release at `folder` and
    rebuild its explorer database."""
    manifest = read_manifest(folder)
    substances = quoted(str(folder / manifest["tables"]["drug_substance_T"]["path"]))
    index, chosen = INDEX + more[0], CHOSEN | more[1]
    level = {code: lvl for code, lvl, _ in index}
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE atc_index_T (atc_code_T VARCHAR, atc_level_T INTEGER, atc_name_T VARCHAR, "
        "atc_index_year_T INTEGER)"
    )
    con.executemany("INSERT INTO atc_index_T VALUES (?, ?, ?, ?)", [(*r, YEAR) for r in index])
    con.execute(
        "CREATE TABLE chosen_T (substance_T VARCHAR, atc_code_T VARCHAR, atc_level_T INTEGER, "
        "atc_chosen_by_T VARCHAR, codes_T VARCHAR[])"
    )
    con.executemany(
        "INSERT INTO chosen_T VALUES (?, ?, ?, ?, ?)",
        [(s, c, level.get(c) if c else None, by, codes) for s, (c, by, codes) in chosen.items()],
    )
    con.execute(
        f"CREATE TABLE records_T AS SELECT {_KEY}, substance_T FROM read_parquet({substances})"
    )
    con.execute(
        f"""CREATE TABLE atc_drug_T AS
            SELECT {_KEY}, c.atc_code_T, c.atc_level_T, {YEAR} AS atc_index_year_T,
                   c.atc_chosen_by_T, len(c.codes_T) AS atc_possible_codes_T,
                   'substance' AS atc_matched_on_T
            FROM records_T JOIN chosen_T c USING (substance_T)"""
    )
    con.execute(
        f"""CREATE TABLE atc_drug_codes_T AS
            SELECT {_KEY}, substance_T AS atc_ingredient_T, p.code_T AS atc_code_T,
                   i.atc_level_T, {YEAR} AS atc_index_year_T,
                   p.code_T IS NOT DISTINCT FROM c.atc_code_T AS atc_chosen_T
            FROM records_T JOIN chosen_T c USING (substance_T),
                 unnest(c.codes_T) AS p(code_T)
            JOIN atc_index_T i ON i.atc_code_T = p.code_T"""
    )
    for table in CLASS_LAYER:
        manifest["tables"][table] = _write(con, folder, table)
    con.close()
    manifest["classes"] = {
        "present": True,
        "source": "Invented for tests",
        "index_year": YEAR,
        "citation": CITATION,
        "prefix": "atc_",
        "tables": list(CLASS_LAYER),
    }
    _save(folder, manifest)
    build_explorer_db(folder)
    add_class_statistics(folder)
    return read_manifest(folder)["classes"]


def remove_classes(folder: Path) -> None:
    """The release at `folder` as one built without the layer, its explorer database rebuilt."""
    manifest = read_manifest(folder)
    for table in CLASS_LAYER:
        manifest["tables"].pop(table, None)
    manifest["classes"] = {"present": False, "source": "Invented for tests", "reason": "none"}
    record_classes(manifest, {}, {"present": False, "reason": "none"})
    _save(folder, manifest)
    build_explorer_db(folder)


__all__ = ["CHOSEN", "CITATION", "GROUP_CLASS", "INDEX", "YEAR", "add_classes", "remove_classes"]
