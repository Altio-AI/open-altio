"""The filtered export: a person downloads exactly the cases their filters
select, in a zip that cannot be mistaken for the full release (rule
filtered-vs-full-export).

`write_export` writes it for the cases a WHERE over `explorer_case_T c`
selects (the filters of explore.py, product and reactions included). The zip
is named `FILTERED_<release>_<yyyymmddThhmmssZ>.zip` and holds one folder of
the same name with:

    cases.<csv|parquet>       one row per selected case (explorer_case_T,
                              FDA's columns verbatim plus the derived _T ones;
                              in CSV, the lists outcomes_T, dup_rule_T and
                              dup_other_cases_T are joined with ';'), newest
                              first by group_first_dt_T (rule dup-shown-copy)
    drugs.<csv|parquet>       every drug row of those cases (explorer_drug_T), with the
                              ingredients each was read to (substance_T)
    reactions.<csv|parquet>   every reaction row of those cases (explorer_reac_T)
    manifest.json             filters, release (and the day its labels are as of, when it
                              holds them: rule label-refresh), export time, row counts, format,
                              a note that this is a filtered extract, and the
                              terms the caller names (a hosted service's licence)

Child rows carry era_T, case_key_T and primaryid to join back to cases.

Rows and the CSV cap (rule export-csv-row-cap): the cap is on lines in any
one CSV file, header included, because that is what Excel counts. CSV is
offered only while the largest of the three files (cases, drugs or
reactions) fits; above that only Parquet is (`csv_fits`). The page asks the
counts first, and the export counts again before it writes. A SQL result
downloaded whole (sql_files.py) comes in the same formats under the same cap.

The files are written by DuckDB COPY into a temporary folder and zipped
there; the zip is streamed from disk and the folder removed after the
response, so a large export never sits in memory.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from open_altio.faers.labels.build import as_of as labels_as_of
from open_altio.faers.reader import quoted
from open_altio.rulebook import value

from .release import OpenRelease

FORMATS = ("csv", "parquet")  # every file the data leaves the explorer as

# What each file holds: (file stem, SELECT list over the selected cases c and the child d).
_CASE_DROP = "case_id_T"
# list columns, joined with ';' in CSV
_CASE_LISTS = ("outcomes_T", "dup_rule_T", "dup_other_cases_T")
_CHILD_KEYS = "c.era_T, c.case_key_T, c.primaryid"
_CHILDREN = {
    "drugs": ("explorer_drug_T", "case_id_T, drugname_norm_T, prod_ai_norm_T, role_T"),
    "reactions": ("explorer_reac_T", "case_id_T"),
}
# Each drug record's one class, WHO's name for it, its level and how it was chosen, where the
# export carries WHO's drug classes.
_CLASS_COLUMNS = ", a.atc_code_T, k.atc_name_T, a.atc_level_T, a.atc_chosen_by_T"
_CLASS_JOINS = (
    " LEFT JOIN explorer_atc_drug_T a ON a.case_id_T = d.case_id_T AND a.drug_seq = d.drug_seq"
    " LEFT JOIN explorer_atc_class_T k ON k.atc_code_T = a.atc_code_T"
)


def csv_row_cap() -> int:
    """The most lines (header included) one CSV file may have."""
    return int(value("export-csv-row-cap", "csv_row_cap"))


def marker() -> str:
    return str(value("filtered-vs-full-export", "filtered_filename_marker"))


def manifest_name() -> str:
    return str(value("filtered-vs-full-export", "filtered_manifest"))


def csv_fits(rows: int) -> bool:
    """True when a CSV file of this many rows fits the cap with its header line."""
    return rows + 1 <= csv_row_cap()


def selection(where_sql: str) -> str:
    """The selected cases, for a WHERE over explorer_case_T c."""
    return f"SELECT c.* FROM explorer_case_T c WHERE {where_sql}"


def _write(
    opened: OpenRelease, sel: str, params: list[Any], fmt: str, folder: Path, classes: bool
) -> dict[str, int]:
    """COPY the selection's tables into `folder`, each drug with its class when `classes`;
    returns rows per file."""
    options = "(FORMAT csv, HEADER)" if fmt == "csv" else "(FORMAT parquet)"
    case_cols = f"* EXCLUDE ({_CASE_DROP})"
    if fmt == "csv":
        case_cols += (
            " REPLACE (" + ", ".join(f"array_to_string({c}, ';') AS {c}" for c in _CASE_LISTS) + ")"
        )
    queries = {
        "cases": (
            f"SELECT {case_cols} FROM ({sel}) ORDER BY group_first_dt_T DESC NULLS LAST, case_id_T"
        ),
    }
    for stem, (table, drop) in _CHILDREN.items():
        extra, joins = (_CLASS_COLUMNS, _CLASS_JOINS) if classes and stem == "drugs" else ("", "")
        queries[stem] = (
            f"SELECT {_CHILD_KEYS}, d.* EXCLUDE ({drop}){extra} FROM ({sel}) c "
            f"JOIN {table} d USING (case_id_T){joins} ORDER BY c.case_id_T"
        )
    rows: dict[str, int] = {}
    cur = opened.cursor()
    try:
        for stem, query in queries.items():
            target = folder / f"{stem}.{fmt}"
            rows[stem] = cur.execute(
                f"COPY ({query}) TO {quoted(str(target))} {options}", params
            ).fetchall()[0][0]
    finally:
        cur.close()
    return rows


@dataclass(frozen=True)
class Written:
    """A filtered export on disk: the zip, the scratch folder to remove after
    sending it, its name and the rows of each file."""

    work: Path
    archive: Path
    rows: dict[str, int]


def write_export(
    opened: OpenRelease,
    sel: str,
    params: list[Any],
    fmt: str,
    at: datetime,
    filters: dict[str, Any],
    terms: dict[str, Any],
    classes: dict[str, Any] | None = None,
) -> Written:
    """Write the zip of a filtered export of the cases `sel` selects, with
    `filters` (query, filters, described) and `terms` in its manifest.json;
    with each drug's class, and WHO's citation in the manifest, when `classes`
    names the release's index year and citation."""
    name = f"{marker()}_{opened.name}_{at.strftime('%Y%m%dT%H%M%SZ')}"
    work = Path(tempfile.mkdtemp(prefix="open-altio-export-"))
    try:
        folder = work / name
        folder.mkdir()
        rows = _write(opened, sel, params, fmt, folder, classes is not None)
        manifest = {
            "kind": "filtered export",
            "note": (
                f"This is a {marker()} extract: only the cases selected by the filters below, "
                f"not the full release {opened.name}."
            ),
            "release": opened.name,
            **({"labels_as_of": day} if (day := labels_as_of(opened.manifest)) else {}),
            "exported_at": at.isoformat(),
            "format": fmt,
            "rows": rows,
            "files": {stem: f"{stem}.{fmt}" for stem in rows},
            **({"classes": classes} if classes else {}),
            **filters,
            **terms,
        }
        (folder / manifest_name()).write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8"
        )
        archive = work / f"{name}.zip"
        compression = zipfile.ZIP_DEFLATED if fmt == "csv" else zipfile.ZIP_STORED
        with zipfile.ZipFile(archive, "w", compression=compression, allowZip64=True) as z:
            for path in sorted(folder.iterdir()):
                z.write(path, f"{name}/{path.name}")
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return Written(work, archive, rows)


def send(written: Written) -> FileResponse:
    """The zip as a download; its scratch folder goes once it is sent."""
    return FileResponse(
        written.archive,
        media_type="application/zip",
        filename=written.archive.name,
        background=BackgroundTask(shutil.rmtree, written.work, ignore_errors=True),
    )
