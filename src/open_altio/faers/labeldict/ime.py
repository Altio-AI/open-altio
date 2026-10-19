"""EMA's Important Medical Events list, read from the file EMA publishes for each MedDRA
version (rule label-umbrella). It is read from a folder the user names, like MedDRA's
own files, and never committed."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Collection
from pathlib import Path

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_CODE = re.compile(r"\d{8}")


def _first_sheet_cells(path: Path) -> list[str]:
    """Every cell value of the workbook's first sheet: EMA's file lists the terms there
    and the PTs it has dropped on a later sheet."""
    with zipfile.ZipFile(path) as book:
        shared = [
            "".join(t.text or "" for t in item.iter(f"{_MAIN}t"))
            for item in ET.fromstring(book.read("xl/sharedStrings.xml")).findall(f"{_MAIN}si")
        ]
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    cells = []
    for cell in sheet.iter(f"{_MAIN}c"):
        value = cell.find(f"{_MAIN}v")
        if value is not None and value.text is not None:
            cells.append(shared[int(value.text)] if cell.get("t") == "s" else value.text)
    return cells


def read_ime(path: str | Path, pt_codes: Collection[str]) -> set[str]:
    """The PT codes on the list: EMA's workbook (.xlsx), or a text file of codes. Only
    codes that are PTs of the version coded with count."""
    path = Path(path).expanduser()
    if path.suffix.lower() == ".xlsx":
        cells = _first_sheet_cells(path)
    else:
        cells = path.read_text(encoding="utf-8").split()
    found = {c.strip() for c in cells if _CODE.fullmatch(c.strip())}
    return found & set(pt_codes)
