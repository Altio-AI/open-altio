"""Read NLM's RxNorm Current Prescribable Content (rule rxnorm-ingredients).

    from open_altio.faers.rxnorm.rrf import read_rxnorm
    rx = read_rxnorm(folder)      # the folder NLM's zip unpacks to: its Readme and rrf/

NLM's files are never copied into the repository or a release. This module is
the one place that knows their layout: RXNCONSO.RRF names each concept, and
RXNREL.RRF relates them, one `|`-separated line each, with no header and no
quoting. Only RxNorm's own names that NLM does not suppress are read, of four
term types: ingredients (IN), precise ingredients such as salts (PIN),
multiple ingredients (MIN) and brand names (BN). Each is read as the set of
ingredients it stands for, so every name leads to IN codes.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from open_altio import rulebook

RULE = "rxnorm-ingredients"
INGREDIENT, SALT, SET, BRAND = "IN", "PIN", "MIN", "BN"
# When two concepts share a name, the one standing for an ingredient most directly wins
TYPES = (INGREDIENT, SALT, SET, BRAND)
OWN_SOURCE, NOT_SUPPRESSED = "RXNORM", "N"
# RXNCONSO.RRF columns: RXCUI, SAB, TTY, STR, SUPPRESS
CONSO = {"rxcui": 0, "source": 11, "tty": 12, "name": 14, "suppress": 16}
# RXNREL.RRF columns. A line says "RXCUI2 RELA RXCUI1": the line (a MIN, part_of, an IN)
# says the ingredient is part_of the multiple ingredient.
REL = {"rxcui1": 0, "rxcui2": 4, "rela": 7, "source": 10}
# For each term type but IN, the relation from an ingredient to a concept of that type
LINKS = {SALT: "has_form", SET: "part_of", BRAND: "has_tradename"}
# A brand's precise ingredient: (a PIN, has_precise_ingredient, a BN), the drug the brand sells
PRECISE = "has_precise_ingredient"
CONSO_FILE, REL_FILE = "rrf/RXNCONSO.RRF", "rrf/RXNREL.RRF"
README = re.compile(r"Readme_Full_Prescribe_([0-9]{8})\.txt", re.IGNORECASE)


class RxNormRefused(Exception):
    """The folder does not hold the RxNorm release the rule pins; the message says why."""


@dataclass(frozen=True)
class RxNorm:
    """One RxNorm release, as the matcher needs it."""

    release: str  # NLM's file date, as the rule pins it
    names: dict[str, tuple[str, str]]  # rxcui -> (name as RxNorm writes it, term type)
    by_name: dict[str, str]  # lower-case name -> rxcui
    ingredients: dict[str, frozenset[str]]  # rxcui -> the IN rxcuis it stands for
    sets: dict[frozenset[str], str]  # two or more IN rxcuis -> the MIN with exactly those
    brand_salts: dict[str, frozenset[str]]  # a BN's rxcui -> the PIN rxcuis it sells


def release_of(folder: Path) -> str:
    """The release date in the name of NLM's Readme, which ships at the zip's top."""
    found = sorted({m.group(1) for p in folder.iterdir() if (m := README.fullmatch(p.name))})
    if len(found) != 1:
        raise RxNormRefused(
            f"{folder} must hold NLM's Readme_Full_Prescribe_<date>.txt from one release; "
            f"found {', '.join(found) or 'none'}"
        )
    return found[0]


def _download() -> str:
    return str(rulebook.value(RULE, "download")).format(release=rulebook.value(RULE, "release"))


def _lines(path: Path) -> Iterator[list[str]]:
    if not path.is_file():
        raise RxNormRefused(
            f"{path} is missing: unpack NLM's zip ({_download()}) into the folder as it comes"
        )
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            yield line.rstrip("\n").split("|")


def read_rxnorm(folder: str | Path) -> RxNorm:
    """Read the release in `folder`. Refuses another release than the rule pins."""
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise RxNormRefused(f"{root} is not a folder")
    release, pinned = release_of(root), str(rulebook.value(RULE, "release"))
    if release != pinned:
        raise RxNormRefused(f"{root} holds the {release} release; rule {RULE} pins {pinned}")
    names: dict[str, tuple[str, str]] = {}
    for f in _lines(root / CONSO_FILE):
        if (
            f[CONSO["source"]] == OWN_SOURCE
            and f[CONSO["tty"]] in TYPES
            and f[CONSO["suppress"]] == NOT_SUPPRESSED
        ):
            names[f[CONSO["rxcui"]]] = (f[CONSO["name"]], f[CONSO["tty"]])
    links = {rela: tty for tty, rela in LINKS.items()}
    parts: dict[str, set[str]] = defaultdict(set)
    sold: dict[str, set[str]] = defaultdict(set)
    for f in _lines(root / REL_FILE):
        one, two = f[REL["rxcui1"]], f[REL["rxcui2"]]
        if f[REL["source"]] != OWN_SOURCE or one not in names or two not in names:
            continue
        tty = links.get(f[REL["rela"]])
        if tty and names[one][1] == tty and names[two][1] in (INGREDIENT, SALT):
            parts[one].add(two)
        elif f[REL["rela"]] == PRECISE and names[one][1] == SALT and names[two][1] == BRAND:
            sold[two].add(one)
    salts = {c: frozenset(parts[c]) for c, (_, tty) in names.items() if tty == SALT}
    ingredients: dict[str, frozenset[str]] = {}
    for rxcui, (_, tty) in names.items():
        if tty == INGREDIENT:
            ingredients[rxcui] = frozenset({rxcui})
        elif parts[rxcui]:
            # a multiple ingredient can list a salt as a part; it counts as the salt's ingredient
            ingredients[rxcui] = frozenset().union(
                *(salts.get(p) or frozenset({p}) for p in parts[rxcui])
            )
    by_name: dict[str, str] = {}
    for rxcui, (name, _) in sorted(names.items(), key=lambda kv: TYPES.index(kv[1][1])):
        by_name.setdefault(name.lower(), rxcui)
    sets = {
        ingredients[c]: c
        for c, (_, tty) in names.items()
        if tty == SET and len(ingredients.get(c, ())) > 1
    }
    brand_salts = {c: frozenset(p) for c, p in sold.items()}
    return RxNorm(release, names, by_name, ingredients, sets, brand_salts)


__all__ = ["CONSO_FILE", "REL_FILE", "RxNorm", "RxNormRefused", "read_rxnorm", "release_of"]
