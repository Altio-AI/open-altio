"""Whether a drug record's RxNorm code names the drug the record is counted under (rule
label-flags): the label follows the unit counted, `substance_T` of `drug_substance_T`.

    from open_altio.faers.labeldict.unit import Unit
    unit = Unit(coded_names)                          # every RxNorm name the release's codes carry
    unit.other_drug("valproic acid", "diazepam")      # True: the code names another drug

A code names another drug when the code and the counted ingredients share no ingredient, and
each counted ingredient is a drug RxNorm codes in this release: its name, through the reviewed
name pairs and the acid endings of rule rxnorm-ingredients, is the name of a code some record
carries, and it is no element named alone. One ingredient's name inside another's counts as
shared, so a code more precise than its counted group (insulin, insulin glargine) or a salt of
the counted ingredient (oxybate, oxybate sodium) names the same drug. A counted name RxNorm codes
nowhere in the release (a group such as "immunoglobulins, unspecified") cannot be compared, so
its record keeps its code, and so does a counted group name (rule label-flags'
`group_name_starts`: vitamin B6 is coded pyridoxine, factor VIII efmoroctocog alfa).
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable

from open_altio import rulebook

from ..rxnorm.match import read_pairs

RXNORM_RULE = "rxnorm-ingredients"
FLAGS_RULE = "label-flags"
SEPARATOR = ";"  # between the counted ingredients, as the drug names step writes them
SET_SEPARATOR = " / "  # between the ingredients of a multiple-ingredient code's name
_WORDS = re.compile(r"[a-z0-9]+")


class Unit:
    def __init__(self, coded_names: Iterable[str]) -> None:
        endings = dict(rulebook.value(RXNORM_RULE, "acid_endings"))
        self._endings = sorted(endings.items(), key=lambda e: -len(e[0]))  # longest first
        self._elements = {e.lower() for e in rulebook.value(RXNORM_RULE, "bare_elements")}
        self._pairs = read_pairs()
        self._groups = tuple(rulebook.value(FLAGS_RULE, "group_name_starts"))
        path = rulebook.data_root() / rulebook.value(FLAGS_RULE, "same_drug")
        with path.open(encoding="utf-8", newline="") as fh:
            self._same = {
                r["counted_name"].strip().lower(): r["rxnorm_name"] for r in csv.DictReader(fh)
            }
        self._coded = {self._words(n) for name in coded_names for n in name.split(SET_SEPARATOR)}

    def _words(self, name: str) -> tuple[str, ...]:
        key = name.strip().lower()
        for ending, written in self._endings:
            if key.endswith(ending):
                key = key[: -len(ending)] + written
                break
        return tuple(_WORDS.findall(key))

    @staticmethod
    def _within(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
        return bool(a) and any(b[i : i + len(a)] == a for i in range(len(b) - len(a) + 1))

    def _names(self, counted: str) -> set[tuple[str, ...]]:
        """A counted ingredient's names: its own, RxNorm's in the reviewed name pairs, and the
        other of a drug RxNorm names two ways."""
        key = counted.lower()
        return {
            self._words(n)
            for n in (counted, self._pairs.get(key, counted), self._same.get(key, counted))
        }

    def other_drug(self, substance: str, rxnorm_name: str) -> bool:
        counted = [n.strip() for n in substance.split(SEPARATOR) if n.strip()]
        names = [self._names(n) for n in counted]
        code = [self._words(n) for n in rxnorm_name.split(SET_SEPARATOR)]
        if any(self._within(a, b) or self._within(b, a) for ns in names for a in ns for b in code):
            return False
        if any(n.lower() in self._elements or n.lower().startswith(self._groups) for n in counted):
            return False
        return bool(names) and all(ns & self._coded for ns in names)


__all__ = ["Unit"]
