"""EMA's designated medical event (DME) and important medical event (IME) lists, read from the
files EMA publishes and written into a release as one table (rule medical-event-lists).

    read_dme(file)            -> (the PT names on the list, the date the file carries or None)
    read_ime_terms(file)      -> (its (MedDRA code, PT name) pairs, the MedDRA version or None)
    read_ime(file, pt_codes)  -> the codes on the list that are PTs of the version coded with
    written, entry = build(release_dir, dme=FILE, ime=FILE)   # table entries by name, the entry
    entry = add_medical_events(release_dir, dme=FILE, ime=FILE)   # into a release already built

    medical_events_T          list_T (dme or ime), pt_T: a PT name as MedDRA writes it

A list is read from a file the user names and is never committed. A list that was not given, or
could not be read, leaves the table without its rows and the manifest entry saying why, so a
page can tell a term that is not on a list from a list the release does not hold. The IME file
names its terms by code and by name. Where the release holds MedDRA, the codes that are PTs of
its version are kept and named as that version names them; without MedDRA the release marks by
the names the file gives. A file of codes alone needs the release's MedDRA to be read.
"""

from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Collection
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from open_altio import rulebook

from .meddra import licensed_dir, read_licensed_manifest
from .reader import read_manifest, write_manifest

RULE = "medical-event-lists"
TABLE = "medical_events_T"
ENTRY = "medical_events"

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_CODE = re.compile(r"\d{8}")
_VERSION = re.compile(r"MedDRA version (\d+\.\d+)")
_EXCEL_DAY_ZERO = date(1899, 12, 30)


class MedicalEventsRefused(ValueError):
    """A list file that cannot be read, in plain words."""


def _first_sheet(path: Path) -> list[tuple[str, str, bool]]:
    """Every cell of the workbook's first sheet as (reference, value, is text). EMA's files
    list the terms there; the IME file's later sheet holds the PTs it has dropped."""
    try:
        with zipfile.ZipFile(path) as book:
            shared = [
                "".join(t.text or "" for t in item.iter(f"{_MAIN}t"))
                for item in ET.fromstring(book.read("xl/sharedStrings.xml")).findall(f"{_MAIN}si")
            ]
            sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise MedicalEventsRefused(f"{path.name} is not a workbook EMA publishes") from exc
    cells = []
    for cell in sheet.iter(f"{_MAIN}c"):
        value = cell.find(f"{_MAIN}v")
        if value is None or value.text is None:
            continue
        text = cell.get("t") == "s"
        cells.append((cell.get("r") or "", shared[int(value.text)] if text else value.text, text))
    return cells


def _column(cells: list[tuple[str, str, bool]], letter: str) -> list[tuple[int, str, bool]]:
    found = []
    for ref, value, text in cells:
        match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
        if match and match.group(1) == letter:
            found.append((int(match.group(2)), value.strip(), text))
    return sorted(found)


def read_dme(path: str | Path) -> tuple[list[str], str | None]:
    """The PT names on EMA's DME list and the date its file carries (yyyy-mm-dd). The workbook
    (.xlsx) holds them in its first column under the heading "PTs"; a text file holds one name
    to a line."""
    path = Path(path).expanduser()
    day = None
    if path.suffix.lower() == ".xlsx":
        column = _column(_first_sheet(path), "A")
        for _, value, text in column:
            if not text and value.isdigit():
                day = (_EXCEL_DAY_ZERO + timedelta(days=int(value))).isoformat()
                break
        heading = next((row for row, value, text in column if text and value == "PTs"), None)
        if heading is None:
            raise MedicalEventsRefused(f"{path.name} has no column of PTs under a heading PTs")
        names = [value for row, value, text in column if row > heading and text and value]
    else:
        names = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    names = list(dict.fromkeys(n for n in names if n))
    if not names:
        raise MedicalEventsRefused(f"{path.name} names no terms")
    return names, day


def read_ime_terms(path: str | Path) -> tuple[list[tuple[str, str | None]], str | None]:
    """The (MedDRA code, PT name) pairs on EMA's IME list and the MedDRA version its file says it
    is for. A workbook gives each code its name from the next cell; a text file of codes gives
    the name None."""
    path = Path(path).expanduser()
    if path.suffix.lower() != ".xlsx":
        codes = [c for c in path.read_text(encoding="utf-8").split() if _CODE.fullmatch(c)]
        return [(c, None) for c in dict.fromkeys(codes)], None
    cells = _first_sheet(path)
    by_ref = {ref: value.strip() for ref, value, _ in cells}
    pairs = []
    for row, value, _ in _column(cells, "A"):
        if _CODE.fullmatch(value):
            pairs.append((value, by_ref.get(f"B{row}") or None))
    version = next((m.group(1) for _, v, _t in cells if (m := _VERSION.search(v))), None)
    return list(dict.fromkeys(pairs)), version


def read_ime(path: str | Path, pt_codes: Collection[str]) -> set[str]:
    """The PT codes on the list: EMA's workbook (.xlsx), or a text file of codes. Only
    codes that are PTs of the version coded with count."""
    pairs, _ = read_ime_terms(path)
    return {code for code, _name in pairs} & set(pt_codes)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _held_pts(release_dir: Path) -> tuple[str, dict[str, str]] | None:
    """The release's MedDRA version and its PTs by code, or None without MedDRA."""
    manifest = read_licensed_manifest(release_dir)
    if not manifest or not manifest["meddra"]["versions"]:
        return None
    [(version, entry)] = manifest["meddra"]["versions"].items()  # one (rule meddra-version)
    table = licensed_dir(release_dir) / entry["tables"]["meddra_pt"]["path"]
    got = pq.read_table(table, columns=["pt_code", "pt_name"]).to_pydict()
    return version, dict(zip(got["pt_code"], got["pt_name"], strict=True))


def _dme(path: Path) -> tuple[list[str], dict[str, Any]]:
    names, day = read_dme(path)
    return names, {"present": True, "sha256": _sha256(path), "date": day, "terms": len(names)}


def _ime(path: Path, held: tuple[str, dict[str, str]] | None) -> tuple[list[str], dict[str, Any]]:
    pairs, version = read_ime_terms(path)
    if not pairs:
        raise MedicalEventsRefused(f"{path.name} names no MedDRA codes")
    entry: dict[str, Any] = {"present": True, "sha256": _sha256(path), "meddra_version": version}
    if held is not None:
        pts = held[1]
        names = sorted({pts[code] for code, _ in pairs if code in pts})
        entry |= {"named_by": "meddra", "release_meddra_version": held[0]}
        entry["not_pts_of_release_version"] = sum(1 for code, _ in pairs if code not in pts)
    else:
        if any(name is None for _, name in pairs):
            raise MedicalEventsRefused(
                f"{path.name} gives codes alone, and the release holds no MedDRA to read them"
            )
        names = sorted({str(name) for _, name in pairs})
        entry["named_by"] = "file"
    entry["terms"] = len(names)
    return names, entry


def build(
    release_dir: str | Path, dme: str | Path | None = None, ime: str | Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write `medical_events_T` into the release folder from the list files given. Returns its
    manifest table entry by name and the `medical_events` entry: per list the file's checksum
    and its date (DME) or MedDRA version (IME), or why the list is not held."""
    release_dir = Path(release_dir)
    held = _held_pts(release_dir)
    lists: dict[str, dict[str, Any]] = {}
    rows: list[tuple[str, str]] = []
    for name, given, read in (
        ("dme", dme, _dme),
        ("ime", ime, lambda p: _ime(p, held)),
    ):
        if given is None:
            lists[name] = {"present": False, "reason": f"No {name.upper()} file was given."}
            continue
        path = Path(given).expanduser()
        try:
            terms, entry = read(path)
        except (MedicalEventsRefused, OSError, UnicodeDecodeError) as exc:
            lists[name] = {
                "present": False,
                "reason": f"The {name.upper()} file was not read: {exc}",
            }
            continue
        lists[name] = entry
        rows += [(name, term) for term in terms]
    rows.sort()
    table = pa.table(
        {
            f"list{_suffix()}": pa.array([r[0] for r in rows], pa.string()),
            f"pt{_suffix()}": pa.array([r[1] for r in rows], pa.string()),
        }
    )
    where = f"parquet/{TABLE}.parquet"
    writing = release_dir / f"{where}.writing"
    pq.write_table(table, writing, compression="zstd")
    os.replace(writing, release_dir / where)
    written = {
        TABLE: {
            "path": where,
            "kind": "derived",
            "rows": len(rows),
            "bytes": (release_dir / where).stat().st_size,
        }
    }
    entry = {"present": any(v["present"] for v in lists.values()), "table": TABLE, "lists": lists}
    return written, entry


def _suffix() -> str:
    return str(rulebook.value("transformed-suffix-T", "derived_suffix"))


def add_medical_events(
    release_dir: str | Path, dme: str | Path | None = None, ime: str | Path | None = None
) -> dict[str, Any]:
    """Write the lists into a release already built, by the build's own step (build): the
    table and the `medical_events` manifest entry, each replaced whole, and nothing else in the
    folder. A second run with the same files writes the same again. Returns the entry."""
    release_dir = Path(release_dir)
    manifest = read_manifest(release_dir)
    written, entry = build(release_dir, dme, ime)
    manifest["tables"] = manifest["tables"] | written
    manifest[ENTRY] = entry
    write_manifest(release_dir, manifest)
    return entry


__all__ = [
    "ENTRY",
    "RULE",
    "TABLE",
    "MedicalEventsRefused",
    "add_medical_events",
    "build",
    "read_dme",
    "read_ime",
    "read_ime_terms",
]
