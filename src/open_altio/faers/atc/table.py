"""Build our drug-to-class table from WHO's index (rule atc-index).

    python -m open_altio.faers atc-table        # reads $OPEN_ALTIO_WHO_DIR, writes the rule's table

    from open_altio.faers.atc.table import build_table
    summary = build_table(who_dir)

The table is keyed by the substance a drug record names: one ingredient in
lower case, or a combination's ingredients sorted and joined with `;`
(`sacubitril;valsartan`). Each row gives one WHO code for it, WHO's name for
that code exactly as WHO wrote it, its level and the index year. Rows with no
ingredient name the classes above the substances' codes, so every level of a
code carries WHO's name.

A substance code joins WHO's own name for it, in lower case, and every
spelling the reviewed bridges give that name (rule atc-spelling-bridges). A
combination code joins the set of its parts when WHO's name lists them ("valsartan
and sacubitril", "metformin, sitagliptin and dapagliflozin") and every part is
a substance WHO codes or a bridged word; each part stands for its own name and
its bridged spellings. A bridge on a combination's whole name joins that code to
the substance or ingredient set the bridge names ("buprenorphine, combinations"
for `buprenorphine;naloxone`), and a bridge on a class's name joins that class
to an ingredient set WHO classes only by the class ("calcium, combinations with
vitamin D and/or other drugs" for `calcium;vitamin d, unspecified`). A
combination WHO names by a class it has no bridge for ("metformin and
sulfonylureas") or as "combinations", with no bridge on its whole name, names no
ingredient set, so it is left out and listed in the summary.

The classes of the reviewed group words (rule atc-group-classes) are written
too, so the layer finds WHO's name for each.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import os
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from open_altio import rulebook

from ..rxnorm.match import SEPARATOR, substance_key
from .whofile import CODE, index_file, level, read_index

COLUMNS = ("ingredient", "atc_code", "who_name", "level", "index_year")
BRIDGE_COLUMNS = ("who_name", "substance", "evidence")
GROUP_COLUMNS = ("substance", "atc_code", "reason")
GROUP_LEVELS = (2, 3, 4)  # never level 1, which names only a body system
SUBSTANCE_LEVEL = 5
# How WHO lists a combination's parts: "a and b", "a, b and c". A comma alone
# qualifies one substance ("fibrinogen, human").
_AND = re.compile(r"\sand\s")
_PARTS = re.compile(r",\s*|\s+and\s+")
_GROUP = re.compile(r"\bcombinations?\b|\bexcl\.|\bincl\.|\bvarious\b")
# a WHO name that names a product of several ingredients, for the layer's SQL too
COMBINATION_NAME = f"{_AND.pattern}|{_GROUP.pattern}"
_YEAR = re.compile(r"\b(?:19|20)[0-9]{2}\b")


class TableRefused(Exception):
    """The class table cannot be built from this input; the message says why."""


def repo_path(rule: str, key: str) -> Path:
    return rulebook.data_root() / rulebook.value(rule, key)


def _substance(path: Path, text: str) -> str:
    """A mapping row's substance, or set of ingredients, keyed as the drug names step writes
    it and the RxNorm step reads it (`substance_key`), so a class joins the records RxNorm
    codes by the same ingredient. A row with none is refused."""
    key = substance_key(text)
    if key is None:
        raise TableRefused(f"{path.name} has a row with no substance")
    return key


def read_bridges(path: Path | None = None) -> dict[str, list[str]]:
    """WHO's word (lower case) -> the substance spellings, or ingredient sets, it also stands
    for."""
    path = path or repo_path("atc-spelling-bridges", "mapping")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != BRIDGE_COLUMNS:
            raise TableRefused(f"{path.name} must have the columns {', '.join(BRIDGE_COLUMNS)}")
        bridges = defaultdict(list)
        for row in reader:
            bridges[row["who_name"].strip().lower()].append(_substance(path, row["substance"]))
    return dict(bridges)


def read_groups(path: Path | None = None) -> dict[str, str]:
    """A group word (or ingredient set) -> the one WHO class it is given (rule
    atc-group-classes). Refuses a word listed twice or a code of another level."""
    path = path or repo_path("atc-group-classes", "mapping")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != GROUP_COLUMNS:
            raise TableRefused(f"{path.name} must have the columns {', '.join(GROUP_COLUMNS)}")
        groups: dict[str, str] = {}
        for row in reader:
            word, code = _substance(path, row["substance"]), row["atc_code"].strip()
            if word in groups:
                raise TableRefused(f"{path.name} lists {word!r} twice")
            if not (CODE.fullmatch(code) and level(code) in GROUP_LEVELS):
                raise TableRefused(
                    f"{path.name}: {code!r} for {word!r} is not a class of level 2 to 4"
                )
            groups[word] = code
    return groups


def _is_combination(name: str) -> bool:
    return bool(_AND.search(name) or _GROUP.search(name))


def table_rows(
    index: list[tuple[str, str]],
    bridges: dict[str, list[str]],
    year: int,
    group_codes: Iterable[str] = (),
) -> tuple[list[dict], list[str]]:
    """The table's rows, sorted, and the combination codes left out because
    their names list no set of coded substances."""
    names = dict(index)
    coded = {
        n.lower()
        for c, n in index
        if level(c) == SUBSTANCE_LEVEL and not _is_combination(n.lower())
    }

    def spellings(part: str) -> list[str]:
        return ([part] if part in coded else []) + bridges.get(part, [])

    # WHO names some classes like the one class below them (A12A "CALCIUM", A12AA "Calcium"); a
    # bridge on such a name stands for the deeper one, which lists the products
    deepest: dict[str, str] = {}
    for c, n in index:
        if level(c) != SUBSTANCE_LEVEL and len(c) > len(deepest.get(n.lower(), "")):
            deepest[n.lower()] = c

    rows: list[dict] = []
    left_out: list[str] = []
    used: set[str] = set()

    def add(code: str, ingredients: set[str]) -> None:
        rows.extend(
            {
                "ingredient": s,
                "atc_code": code,
                "who_name": names[code],
                "level": level(code),
                "index_year": year,
            }
            for s in ingredients
        )
        used.update(code[:n] for n in (1, 3, 4, 5) if n <= len(code))

    for code, name in index:
        lowered = name.lower()
        if level(code) != SUBSTANCE_LEVEL:
            # a class stands only for an ingredient set WHO classes by it; a single word that is a
            # class's name ("diuretics") is a part of combination names
            classed = {s for s in bridges.get(lowered, []) if SEPARATOR in s}
            if classed and deepest[lowered] == code:
                add(code, classed)
            continue
        whole = set(bridges.get(lowered, [])) if _is_combination(lowered) else set()
        parts = (
            [p.strip() for p in _PARTS.split(lowered)] if _is_combination(lowered) else [lowered]
        )
        options = [spellings(p) for p in parts]
        sets = (
            set()
            if _GROUP.search(lowered) or not all(options)
            else {
                key
                for choice in itertools.product(*options)
                if (key := substance_key(SEPARATOR.join(choice)))
            }
        )
        if not sets | whole:
            left_out.append(code)
            continue
        add(code, sets | whole)
    used.update(c[:n] for c in group_codes for n in (1, 3, 4, 5) if n <= len(c))
    missing = sorted(c for c in used if c not in names)
    if missing:
        raise TableRefused(f"WHO's index names no class for {', '.join(missing)}")
    rows += [
        {
            "ingredient": "",
            "atc_code": c,
            "who_name": names[c],
            "level": level(c),
            "index_year": year,
        }
        for c in used
    ]
    rows.sort(key=lambda r: (r["ingredient"], r["atc_code"]))
    return rows, left_out


def write_table(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(f".{path.name}.writing")
    with scratch.open("w", encoding="utf-8", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        out.writeheader()
        out.writerows(rows)
    os.replace(scratch, path)


def build_table(
    who_dir: str | Path,
    out: str | Path | None = None,
    *,
    bridges: Path | None = None,
    groups: Path | None = None,
) -> dict:
    """Read WHO's index in `who_dir`, write the class table (by default the
    file rule atc-index names) and return what was written. Refuses a file
    whose name gives another year than the rule's index year."""
    year = int(rulebook.value("atc-index", "index_year"))
    source = index_file(who_dir)
    other = sorted({int(y) for y in _YEAR.findall(source.name)} - {year})
    if other:
        raise TableRefused(
            f"{source.name} looks like the {other[0]} index; rule atc-index pins {year}"
        )
    path = Path(out) if out else repo_path("atc-index", "table")
    rows, left_out = table_rows(
        read_index(who_dir), read_bridges(bridges), year, read_groups(groups).values()
    )
    write_table(rows, path)
    ingredients = {r["ingredient"] for r in rows if r["ingredient"]}
    return {
        "table": str(path),
        "index_year": year,
        "source": {"file": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "rows": len(rows),
        "substances": sum(SEPARATOR not in i for i in ingredients),
        "ingredient_sets": sum(SEPARATOR in i for i in ingredients),
        "combination_codes_left_out": left_out,
    }


__all__ = [
    "BRIDGE_COLUMNS",
    "COLUMNS",
    "COMBINATION_NAME",
    "GROUP_COLUMNS",
    "SEPARATOR",
    "TableRefused",
    "build_table",
    "read_bridges",
    "read_groups",
    "repo_path",
    "table_rows",
    "write_table",
]
