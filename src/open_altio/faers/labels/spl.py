"""Read one label in FDA's Structured Product Labeling (SPL) XML.

`read_facts` gives what choosing a label needs; `read_sections` flattens the
safety sections the label-sections rule names into lines of plain text.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

NS = "{urn:hl7-org:v3}"
_SPACES = re.compile(r"\s+")
# Text inside these is not the label's words: pictures, and the Highlights
# excerpt a full section repeats in short, which would count every warning twice.
_SKIPPED = {"renderMultiMedia", "excerpt"}
_BLOCKS = {"paragraph", "list", "table", "caption"}


def _tag(el: ET.Element) -> str:
    return el.tag.removeprefix(NS) if isinstance(el.tag, str) else ""


def _clean(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def _inline(el: ET.Element) -> str:
    """Every word under `el`, in order, as one line; a line break is a space."""
    parts = [el.text or ""]
    for child in el:
        tag = _tag(child)
        if tag not in _SKIPPED:
            parts.append(" " if tag == "br" else "")
            parts.append(_inline(child))
            parts.append(" " if tag in _BLOCKS or tag in {"item", "td", "th", "tr"} else "")
        parts.append(child.tail or "")
    return "".join(parts)


@dataclass(frozen=True)
class LabelFacts:
    set_id: str
    spl_version: int
    title: str
    effective_date: date | None
    document_type: str  # the LOINC code of the document, such as 34391-3
    # (FDA marketing category code, application id as written, such as NDA202155)
    approvals: tuple[tuple[str, str], ...] = field(default=())
    # FDA's names for the routes and forms of the products, such as ORAL and TABLET
    routes: tuple[str, ...] = field(default=())
    dosage_forms: tuple[str, ...] = field(default=())
    # whether its safety sections hold any words; some labels leave them empty
    # or file them as unclassified, and a label with none cannot be compared with
    safety_text: bool = True
    # each route with the active ingredient names (lower case) of the kit part
    # it is given for, or None for a route of the product itself
    route_parts: tuple[tuple[str, tuple[str, ...] | None], ...] = field(default=())
    # every active ingredient the label lists, kit parts' included, as its
    # substance's name and its active moiety's name (lower case; "" when none)
    actives: tuple[tuple[str, str], ...] = field(default=())


def _attr(root: ET.Element, path: str, name: str) -> str:
    el = root.find(path)
    return "" if el is None else el.get(name, "")


def _date(value: str) -> date | None:
    """SPL writes yyyymmdd, sometimes followed by a time."""
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return None


def _names(elements: list[ET.Element]) -> tuple[str, ...]:
    """Distinct display names, in label order."""
    names = (_clean(el.get("displayName", "")).upper() for el in elements)
    return tuple(dict.fromkeys(n for n in names if n))


def _forms(root: ET.Element) -> list[ET.Element]:
    """The form of each product the label covers. A kit's parts carry their
    own forms deeper down; the kit is one product, so only its own counts."""
    found = []
    for outer in root.iter(f"{NS}manufacturedProduct"):
        for inner in outer:
            if _tag(inner) in {"manufacturedProduct", "manufacturedMedicinalProduct"}:
                form = inner.find(f"{NS}formCode")
                if form is not None:
                    found.append(form)
    return found


def _route_parts(root: ET.Element) -> tuple[tuple[str, tuple[str, ...] | None], ...]:
    """Each route, with the active ingredients of the kit part it belongs to
    (an alcohol pad's isopropyl alcohol), or None outside any part."""
    found: list[tuple[str, tuple[str, ...] | None]] = []
    in_parts: set[int] = set()
    for part in root.iter(f"{NS}part"):
        actives = tuple(
            sorted(
                {
                    _clean(name.text or "").lower()
                    for ing in part.iter(f"{NS}ingredient")
                    if ing.get("classCode", "").startswith("ACT")
                    and (name := ing.find(f"{NS}ingredientSubstance/{NS}name")) is not None
                }
            )
        )
        for route in part.iter(f"{NS}routeCode"):
            in_parts.add(id(route))
            found.append((_clean(route.get("displayName", "")).upper(), actives))
    for route in root.iter(f"{NS}routeCode"):
        if id(route) not in in_parts:
            found.append((_clean(route.get("displayName", "")).upper(), None))
    return tuple(dict.fromkeys(r for r in found if r[0]))


def _actives(root: ET.Element) -> tuple[tuple[str, str], ...]:
    """Each active ingredient the label lists, once, as (substance, active moiety)."""
    found = []
    for ing in root.iter(f"{NS}ingredient"):
        substance = ing.find(f"{NS}ingredientSubstance")
        if not ing.get("classCode", "").startswith("ACT") or substance is None:
            continue
        name = substance.find(f"{NS}name")
        moiety = substance.find(f"{NS}activeMoiety/{NS}activeMoiety/{NS}name")
        found.append(
            (
                _clean(name.text or "").lower() if name is not None else "",
                _clean(moiety.text or "").lower() if moiety is not None else "",
            )
        )
    return tuple(dict.fromkeys(a for a in found if a[0] or a[1]))


def read_facts(root: ET.Element) -> LabelFacts:
    approvals = []
    for approval in root.iter(f"{NS}approval"):
        code = approval.find(f"{NS}code")
        ident = approval.find(f"{NS}id")
        approvals.append(
            (
                "" if code is None else code.get("code", ""),
                "" if ident is None else ident.get("extension", ""),
            )
        )
    title = root.find(f"{NS}title")
    version = _attr(root, f"{NS}versionNumber", "value")
    return LabelFacts(
        set_id=_attr(root, f"{NS}setId", "root").lower(),
        spl_version=int(version) if version.isdigit() else 0,
        title=_clean(_inline(title)) if title is not None else "",
        effective_date=_date(_attr(root, f"{NS}effectiveTime", "value")),
        document_type=_attr(root, f"{NS}code", "code"),
        approvals=tuple(dict.fromkeys(approvals)),
        routes=tuple(sorted(_names(list(root.iter(f"{NS}routeCode"))))),
        dosage_forms=_names(_forms(root)),
        route_parts=_route_parts(root),
        actives=_actives(root),
    )


def _holds_blocks(el: ET.Element) -> bool:
    return el.find(f".//{NS}table") is not None or el.find(f".//{NS}list") is not None


@dataclass(frozen=True)
class Line:
    section: str
    loinc: str
    ordinal: int
    is_table_row: bool
    text: str


class _Lines:
    """Collects a label's lines in order, numbering them as they come."""

    def __init__(self, separator: str) -> None:
        self.separator = separator
        self.lines: list[Line] = []

    def add(self, section: tuple[str, str], text: str, is_table_row: bool = False) -> None:
        # A row keeps an empty first cell, so splitting on the separator finds every cell.
        text = text if is_table_row else _clean(text)
        if text.replace(self.separator, "").strip():
            n = len(self.lines) + 1
            self.lines.append(Line(section[0], section[1], n, is_table_row, text))

    def table(self, section: tuple[str, str], table: ET.Element) -> None:
        """The caption, then the head, body and foot rows. SPL puts the foot
        (the footnotes) before the body, as HTML 4 did; read as a table is
        printed, the footnotes come last."""
        caption = table.find(f"{NS}caption")
        if caption is not None:
            self.add(section, _inline(caption))
        parts = {_tag(part): part for part in table if _tag(part) in {"thead", "tbody", "tfoot"}}
        rows = [r for part in ("thead", "tbody", "tfoot") if part in parts for r in parts[part]]
        rows += [r for r in table if _tag(r) == "tr"]  # a table with no head or body
        for row in rows:
            if _tag(row) == "tr":
                cells = [_clean(_inline(c)) for c in row if _tag(c) in {"td", "th"}]
                self.add(section, self.separator.join(cells), is_table_row=True)

    def blocks(self, section: tuple[str, str], el: ET.Element) -> None:
        """A section's <text>: paragraphs and list items one line each, a
        table one line per row; loose words between blocks are a line too."""
        loose = [el.text or ""]
        for child in el:
            tag = _tag(child)
            if tag in _SKIPPED:
                pass
            elif tag == "table":
                self.add(section, "".join(loose))
                loose = []
                self.table(section, child)
            elif tag == "list":
                self.add(section, "".join(loose))
                loose = []
                for item in child:
                    if _tag(item) == "caption":
                        self.add(section, _inline(item))
                    elif _tag(item) == "item" and _holds_blocks(item):
                        self.blocks(section, item)
                    elif _tag(item) == "item":  # its bullet or number and its words, one line
                        self.add(section, _inline(item))
            elif tag in {"paragraph", "caption"}:
                self.add(section, "".join(loose))
                loose = []
                if _holds_blocks(child):
                    self.blocks(section, child)
                else:
                    self.add(section, _inline(child))
            else:
                loose.append(_inline(child))
            loose.append(child.tail or "")
        self.add(section, "".join(loose))


def read_sections(root: ET.Element, wanted: dict[str, str], separator: str) -> list[Line]:
    """The lines of every wanted section, in label order. `wanted` maps a
    LOINC section code to its name. A subsection belongs to the nearest
    enclosing wanted section, so nothing is counted twice."""
    out = _Lines(separator)

    def walk(el: ET.Element, current: tuple[str, str] | None) -> None:
        for child in el:
            tag = _tag(child)
            if tag in _SKIPPED:
                continue
            if tag == "section":
                code = child.find(f"{NS}code")
                loinc = "" if code is None else code.get("code", "")
                here = (wanted[loinc], loinc) if loinc in wanted else current
                if here is not None:
                    title = child.find(f"{NS}title")
                    if title is not None:
                        out.add(here, _inline(title))
                    text = child.find(f"{NS}text")
                    if text is not None:
                        out.blocks(here, text)
                walk(child, here)
            elif tag in {"component", "structuredBody"}:
                walk(child, current)

    body = root.find(f"{NS}component/{NS}structuredBody")
    if body is not None:
        walk(body, None)
    return out.lines


def parse(xml: bytes) -> ET.Element:
    return ET.fromstring(xml)
