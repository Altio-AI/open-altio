"""Match a drug record's names to its RxNorm ingredient code (rule rxnorm-ingredients).

    from open_altio.faers.rxnorm.match import Matcher
    matcher = Matcher(read_rxnorm(folder))
    matcher.drug_name("KLOR-CON")            # FDA's drug name, exactly
    matcher.prod_ai("POTASSIUM CHLORIDE")    # FDA's active ingredient, exactly, whole or by parts
    matcher.match("sacubitril;valsartan")    # the dictionary's ingredient
    # each gives Match(rxcui, rxnorm_name, tty, matched_by, reason)

A substance is one ingredient name, or a combination's names sorted and joined
with `;`, as the drug names step writes it (`substance_key`). Each name is
looked up three ways, and the first that finds it wins:

    exact        the name is an RxNorm name, ignoring case: an ingredient (IN), a salt or
                 other precise ingredient (PIN, read as its IN), a multiple ingredient
                 (MIN) or a brand (BN, read as its ingredients)
    name_pair    the reviewed list gives RxNorm's name for it (`acetaminophen` for `paracetamol`)
    spelling     it equals one RxNorm name once both drop the rule's ignored characters and
                 write an acid ending as the rule says (`alendronic acid`, `alendronate`)

A precise ingredient takes its ingredient's code only when it is a salt,
ester or form of that same drug: its name, less the rule's form words and
FDA's four-letter suffix, spells the ingredient's name, or the reviewed list
of names that keep their parent's code holds it. RxNorm also files distinct
drugs as precise ingredients of a parent (`trastuzumab deruxtecan` under
`trastuzumab`); those get no code, so they never take the parent's.

A name the dictionary writes as an element alone (`potassium` for potassium
chloride) gives no code when RxNorm reads it as one of the rule's bare
elements: RxNorm names each salt as an ingredient of its own, and the
dictionary does not say which salt it was. FDA's own drug name or active
ingredient naming the element still gives its code.

The substance's code is its one ingredient's IN, or the MIN whose ingredients
are exactly the set its names give. Nothing is guessed: a name close to an
RxNorm name but not equal to it finds nothing, and a spelling two RxNorm
ingredients share finds neither. A substance with no code says why.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from open_altio import rulebook

from ..drugnames.substances import PROD_AI_SEPARATOR
from .rrf import BRAND, INGREDIENT, RULE, SALT, SET, TYPES, RxNorm

SEPARATOR = ";"
PAIR_COLUMNS = ("dictionary_name", "rxnorm_name", "evidence")
PROD_AI_PAIR_COLUMNS = ("fda_name", "rxnorm_name", "evidence")
KEEP_COLUMNS = ("rxnorm_name", "reason")
# How a substance found its code, strongest first; a combination is as strong as its weakest name
BY_TYPE = {INGREDIENT: "ingredient", SALT: "salt", SET: "ingredient_set", BRAND: "brand"}
NAME_PAIR, SPELLING = "name_pair", "spelling"
STRENGTH = (*BY_TYPE.values(), NAME_PAIR, SPELLING)
# Every name has a code but RxNorm lists no product with exactly that set of ingredients
PARTS_ONLY = "parts_only"
NONE = "none"
# Why a substance has no code
NO_NAME = "no RxNorm name matches it"
DIFFERENT_PARENT = "RxNorm files it under a different parent drug"
NO_PRODUCT = "no US product has exactly these ingredients"
BARE_ELEMENT = "the ingredient names an element, not which of its salts"
_WORDS = re.compile(r"[\s,]+")

Found = tuple[frozenset[str], str]  # the IN rxcuis a name stands for, and how it was found


class PairsRefused(Exception):
    """The name pair list cannot be read as it stands; the message says why."""


@dataclass(frozen=True)
class Match:
    rxcui: str | None
    rxnorm_name: str | None
    tty: str | None  # IN or MIN
    matched_by: str
    reason: str | None = None  # why there is no code


def substance_key(text: str) -> str | None:
    """A substance as the drug names step writes it: lower case, a combination's
    names trimmed, sorted and joined with `;`."""
    names = sorted({n.strip().lower() for n in text.split(SEPARATOR)} - {""})
    return SEPARATOR.join(names) or None


def _rows(value: str, path: Path | None, columns: tuple[str, ...]) -> tuple[Path, list[dict]]:
    path = path or rulebook.data_root() / rulebook.value(RULE, value)
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != columns:
            raise PairsRefused(f"{path.name} must have the columns {', '.join(columns)}")
        return path, list(reader)


def _read_pairs(value: str, path: Path | None, columns: tuple[str, ...]) -> dict[str, str]:
    path, rows = _rows(value, path, columns)
    pairs: dict[str, str] = {}
    for row in rows:
        name = row[columns[0]].strip().lower()
        rxnorm = row[columns[1]].strip().lower()
        if pairs.get(name, rxnorm) != rxnorm:
            raise PairsRefused(f"{path.name} gives {name!r} two RxNorm names")
        pairs[name] = rxnorm
    return pairs


def read_pairs(path: Path | None = None) -> dict[str, str]:
    """The reviewed name pairs: the dictionary's name -> RxNorm's name, both lower case."""
    return _read_pairs("name_pairs", path, PAIR_COLUMNS)


def read_prod_ai_pairs(path: Path | None = None) -> dict[str, str]:
    """The reviewed names FDA's active ingredient writes differently from RxNorm:
    FDA's name -> RxNorm's name, both lower case."""
    return _read_pairs("prod_ai_pairs", path, PROD_AI_PAIR_COLUMNS)


def read_keeps(path: Path | None = None) -> set[str]:
    """The reviewed precise ingredients that keep their parent's code although their
    name does not spell it, as RxNorm names them without FDA's suffix, in lower case."""
    _, rows = _rows("keeps_parent_code", path, KEEP_COLUMNS)
    return {row["rxnorm_name"].strip().lower() for row in rows}


class Matcher:
    """Matches substances against one RxNorm release and the reviewed name pairs."""

    def __init__(
        self,
        rx: RxNorm,
        pairs: Mapping[str, str] | None = None,
        keeps: set[str] | None = None,
        prod_ai_pairs: Mapping[str, str] | None = None,
    ) -> None:
        self.rx = rx
        endings = dict(rulebook.value(RULE, "acid_endings"))
        self._endings = sorted(endings.items(), key=lambda e: -len(e[0]))  # longest first
        self._ignored = list(rulebook.value(RULE, "ignored_characters"))
        self._salt_words = set(rulebook.value(RULE, "form_words"))
        self._salt_endings = tuple(rulebook.value(RULE, "form_endings"))
        self._suffix = re.compile(rulebook.value(RULE, "biologic_suffix"))
        self._elements = {e.lower() for e in rulebook.value(RULE, "bare_elements")}
        pairs = read_pairs() if pairs is None else pairs
        self._keeps = read_keeps() if keeps is None else keeps
        fda = read_prod_ai_pairs() if prod_ai_pairs is None else prod_ai_pairs
        self._pairs = {n: rx.by_name[r] for n, r in pairs.items() if r in rx.by_name}
        self._fda_pairs = {n: rx.by_name[r] for n, r in fda.items() if r in rx.by_name}
        # a pair whose RxNorm name this release lacks codes nothing; the manifest lists it
        self.unused_pairs = sorted(
            n for n, r in [*pairs.items(), *fda.items()] if r not in rx.by_name
        )
        spelt: dict[str, list[str]] = defaultdict(list)
        for name, rxcui in sorted(rx.by_name.items(), key=lambda kv: self._rank(kv[1])):
            if rxcui in rx.ingredients:
                spelt[self.spelling(name)].append(rxcui)
        self._spelt = {
            key: found[0]
            for key, found in spelt.items()
            if len({rx.ingredients[c] for c in found}) == 1
        }

    def _rank(self, rxcui: str) -> int:
        return TYPES.index(self.rx.names[rxcui][1])

    def _ending(self, name: str) -> str:
        key = name.lower()
        for ending, written in self._endings:
            if key.endswith(ending):
                return key[: -len(ending)] + written
        return key

    def _squash(self, key: str) -> str:
        for character in self._ignored:
            key = key.replace(character, "")
        return key

    def spelling(self, name: str) -> str:
        return self._squash(self._ending(name))

    def bare(self, name: str) -> str:
        """A name less FDA's four-letter suffix and its salt and ester words (the rule's
        form words, and words with a form ending such as -ate), spelt. The acid ending is
        written first, so `lactic acid` is the salt word `lactate`."""
        words = _WORDS.split(self._ending(self._suffix.sub("", name.lower())))
        kept = (w for w in words if w and w not in self._salt_words)
        return self._squash(" ".join(w for w in kept if not w.endswith(self._salt_endings)))

    def _same_drug(self, rxcui: str) -> bool:
        """A precise ingredient is its ingredient's own drug when its name spells the
        ingredient's or the reviewed list keeps it; a brand, when every drug it sells is."""
        name, tty = self.rx.names[rxcui]
        if tty == BRAND:
            return all(self._same_drug(p) for p in self.rx.brand_salts.get(rxcui, ()))
        if tty != SALT or self._suffix.sub("", name.lower()) in self._keeps:
            return True
        return all(
            self.bare(name) == self.bare(self.rx.names[p][0]) for p in self.rx.ingredients[rxcui]
        )

    def _found(self, rxcui: str | None, how: str) -> Found | str | None:
        if rxcui not in self.rx.ingredients:
            return None
        if not self._same_drug(rxcui):
            return DIFFERENT_PARENT
        return self.rx.ingredients[rxcui], how or BY_TYPE[self.rx.names[rxcui][1]]

    def _bare(self, found: Found | str) -> bool:
        if isinstance(found, str) or len(found[0]) != 1:
            return False
        return self.rx.names[next(iter(found[0]))][0].lower() in self._elements

    def _name(self, name: str) -> Found | str:
        """What one of the dictionary's names stands for and how it was found, or why it has
        no code."""
        for rxcui, how in (
            (self.rx.by_name.get(name), ""),
            (self._pairs.get(name), NAME_PAIR),
            (self._spelt.get(self.spelling(name)), SPELLING),
        ):
            found = self._found(rxcui, how)
            if found is not None:
                return BARE_ELEMENT if self._bare(found) else found
        return NO_NAME

    def _exact(self, name: str) -> Found | str:
        found = self._found(self.rx.by_name.get(name.strip().lower()), "")
        return NO_NAME if found is None else found

    def drug_name(self, spelling: str) -> Match:
        """FDA's drug name, matched only as it is, to one RxNorm name ignoring case:
        no name pair and no spelling rule, since a drug name is not the dictionary's."""
        return self._code([self._exact(spelling)])

    def _fda_name(self, name: str) -> Found | str:
        """One of FDA's active ingredient names: exactly an RxNorm name, else RxNorm's name
        for it in the reviewed list of FDA's names (`dextrose` is `glucose`)."""
        found = self._exact(name)
        if found != NO_NAME:
            return found
        return self._found(self._fda_pairs.get(name.strip().lower()), NAME_PAIR) or NO_NAME

    def prod_ai(self, text: str) -> Match:
        """FDA's active ingredient, matched exactly: whole, else, for a combination FDA
        writes with its separator, every part. No spelling rule applies."""
        whole = self._code([self._fda_name(text)])
        if whole.rxcui is not None or PROD_AI_SEPARATOR not in text:
            return whole
        parts = sorted({p.strip().lower() for p in text.split(PROD_AI_SEPARATOR)} - {""})
        return self._code([self._fda_name(p) for p in parts] or [NO_NAME])

    def match(self, substance: str) -> Match:
        key = substance_key(substance)
        return self._code([self._name(n) for n in key.split(SEPARATOR)] if key else [NO_NAME])

    def _code(self, found: list[Found | str]) -> Match:
        refused = {f for f in found if isinstance(f, str)}
        if refused:
            order = (DIFFERENT_PARENT, BARE_ELEMENT, NO_NAME)
            return Match(None, None, None, NONE, min(refused, key=order.index))
        hits = [f for f in found if not isinstance(f, str)]
        ins = frozenset().union(*(ins for ins, _ in hits))
        how = [h for _, h in hits]
        if len(how) > 1:
            how = [BY_TYPE[SET] if h in (BY_TYPE[INGREDIENT], BY_TYPE[SALT]) else h for h in how]
        rxcui = next(iter(ins)) if len(ins) == 1 else self.rx.sets.get(ins)
        if rxcui is None:
            return Match(None, None, None, PARTS_ONLY, NO_PRODUCT)
        name, tty = self.rx.names[rxcui]
        return Match(rxcui, name, tty, max(how, key=STRENGTH.index))


__all__ = [
    "BARE_ELEMENT",
    "DIFFERENT_PARENT",
    "NONE",
    "NO_NAME",
    "NO_PRODUCT",
    "PAIR_COLUMNS",
    "PROD_AI_PAIR_COLUMNS",
    "PARTS_ONLY",
    "SEPARATOR",
    "STRENGTH",
    "Match",
    "Matcher",
    "PairsRefused",
    "read_keeps",
    "read_pairs",
    "read_prod_ai_pairs",
    "substance_key",
]
