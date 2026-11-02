"""Invented copies of EMA's two medical event list files, in the workbook layout EMA publishes
them in, with none of EMA's content: the terms are the invented MedDRA's (fakemeddra.py).

    write_dme(path, terms=DME_TERMS)           # a heading PTs, then a term to a row of column A
    write_ime(path, rows=IME_ROWS, version="29.1")   # MedDRA code, PT name; later sheet of drops
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

DME_TERMS = ["Renal failure", "Seizure", "Haemorrhage", "Invented term only EMA lists"]
IME_ROWS = [
    ("94000027", "Seizure"),
    ("94000022", "Renal failure acute"),
    ("94000002", "Nausea"),
    ("99999999", "Invented term the release's MedDRA lacks"),
]
EXCEL_DAY = 43997  # 2020-06-15 as a workbook counts days

_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _sheet(cells: dict[str, str | int], strings: list[str]) -> str:
    """A sheet of `cells` (a reference -> text or whole number), its text added to `strings`."""
    rows: dict[int, list[str]] = {}
    for ref, value in cells.items():
        row = int("".join(c for c in ref if c.isdigit()))
        if isinstance(value, int):
            rows.setdefault(row, []).append(f'<c r="{ref}"><v>{value}</v></c>')
        else:
            strings.append(value)
            rows.setdefault(row, []).append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
    data = "".join(f'<row r="{n}">{"".join(c)}</row>' for n, c in sorted(rows.items()))
    return f'<worksheet xmlns="{_NAMESPACE}"><sheetData>{data}</sheetData></worksheet>'


def _entry(name: str) -> zipfile.ZipInfo:
    return zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))


def _write(path: Path, *sheets: dict[str, str | int]) -> Path:
    """A workbook whose sheets hold the given cells."""
    strings: list[str] = []
    bodies = [_sheet(cells, strings) for cells in sheets]
    shared = "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
    with zipfile.ZipFile(path, "w") as book:
        # a fixed time in each entry, so the same cells always make the same file
        book.writestr(_entry("xl/sharedStrings.xml"), f'<sst xmlns="{_NAMESPACE}">{shared}</sst>')
        for n, body in enumerate(bodies, 1):
            book.writestr(_entry(f"xl/worksheets/sheet{n}.xml"), body)
    return path


def write_dme(path: Path, terms: list[str] = DME_TERMS) -> Path:
    cells: dict[str, str | int] = {
        "A5": EXCEL_DAY,
        "A10": "Designated Medical Event (DME) list",
        "A16": "PTs",
    }
    cells |= {f"A{17 + i}": term for i, term in enumerate(terms)}
    return _write(path, cells)


def write_ime(path: Path, rows: list[tuple[str, str]] = IME_ROWS, version: str = "29.1") -> Path:
    cells: dict[str, str | int] = {
        "A10": f"Important medical event terms list (MedDRA version {version})",
        "A12": "MedDRA Code",
        "B12": "PT Name",
    }
    for i, (code, name) in enumerate(rows):
        cells[f"A{13 + i}"] = code
        cells[f"B{13 + i}"] = name
    return _write(path, cells, {"A1": "94000001", "B1": "Headache"})  # a PT EMA dropped
