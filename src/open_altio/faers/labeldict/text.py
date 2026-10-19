"""Label text as sentences and words, read the way rule label-dictionary says."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from open_altio import rulebook

RULE = "label-dictionary"

# A word is letters and digits, hyphens inside it included, so "extra-pulmonary" is one
# word and never ends in "pulmonary". Every other visible character but an apostrophe is
# a mark, a word of its own, so a match cannot cross one unless the name holds it ("Mg++"
# never matches "mg").
_WORD = re.compile(r"[^\W_]+(?:[-\u2010\u2011][^\W_]+)*|[^\w\s'\u2019\-\u2010\u2011]")


def is_mark(key: str) -> bool:
    return not key[0].isalnum()


@dataclass(frozen=True)
class Word:
    text: str  # as written, accents dropped
    key: str  # what matching compares: lower case, one spelling
    start: int  # character span in the text as written
    end: int


def _folded(text: str) -> tuple[str, list[int]]:
    """The text without accents, and for each of its characters the position it
    came from, so a match can be shown as the label wrote it."""
    out: list[str] = []
    origin: list[int] = []
    for i, ch in enumerate(text):
        for part in unicodedata.normalize("NFKD", ch):
            if not unicodedata.combining(part):
                out.append(part)
                origin.append(i)
    origin.append(len(text))
    return "".join(out), origin


def all_capitals(name: str) -> bool:
    return any(c.isalpha() for c in name) and name == name.upper()


class TextReader:
    """Cuts label text into sentences and words. Built once per run, because the
    rule's values are read from its file."""

    def __init__(
        self,
        sentence_ends: Sequence[str],
        not_sentence_ends: Sequence[str],
        spellings: Sequence[Sequence[str]],
    ) -> None:
        self._end = re.compile("[" + re.escape("".join(sentence_ends)) + r"](?=\s)")
        self._not_ends = tuple(e.lower() for e in not_sentence_ends)
        self._spellings = tuple((a.lower(), b.lower()) for a, b in spellings)

    @classmethod
    def from_rules(cls) -> TextReader:
        return cls(
            rulebook.value(RULE, "sentence_ends"),
            rulebook.value(RULE, "not_sentence_ends"),
            rulebook.value(RULE, "spellings"),
        )

    def key(self, word: str) -> str:
        """British and US spellings meet, applied to label text and MedDRA names alike."""
        out = word.lower()
        for british, us in self._spellings:
            out = out.replace(british, us)
        return out

    def words(self, text: str) -> list[Word]:
        folded, origin = _folded(text)
        return [
            Word(
                m.group(0),
                self.key(m.group(0)),
                origin[m.start()],
                origin[m.end() - 1] + 1,
            )
            for m in _WORD.finditer(folded)
        ]

    def sentences(self, text: str) -> list[str]:
        out, start = [], 0
        for m in self._end.finditer(text):
            before = text[start : m.end()].lower()
            if any(_ends_with_word(before, n) for n in self._not_ends):
                continue
            out.append(text[start : m.end()])
            start = m.end()
        out.append(text[start:])
        return [s.strip() for s in out if s.strip()]


def _ends_with_word(text: str, tail: str) -> bool:
    return text.endswith(tail) and (len(text) == len(tail) or not text[-len(tail) - 1].isalnum())
