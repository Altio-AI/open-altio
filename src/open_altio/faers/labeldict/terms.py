"""Find current MedDRA LLT names in a sentence, longest first (rule label-dictionary)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from open_altio import rulebook

from .text import RULE, TextReader, Word, all_capitals

_END = ""  # no word has an empty key, so this marks where a name ends


@dataclass(frozen=True)
class Term:
    llt_code: str
    llt_name: str
    pt_code: str
    pt_name: str


@dataclass(frozen=True)
class Hit:
    term: Term
    first: int  # word positions in the sentence, last not included
    last: int


def plural(key: str) -> str:
    if key.endswith(("s", "x", "z", "ch", "sh")):
        return key + "es"
    if key.endswith("y") and len(key) > 1 and key[-2] not in "aeiou":
        return key[:-1] + "ies"
    return key + "s"


class TermIndex:
    """Every current LLT name as a tree of words, so one pass over a sentence finds
    the longest name starting at each word. Each name is also stored in its other
    forms (a plural last word, a lab result in prose order), after every name as
    MedDRA writes it, so a name as written always wins over another name's form."""

    def __init__(
        self,
        terms: Iterable[Term],
        reader: TextReader,
        *,
        capitals_match_capitals: bool,
        shortest_name: int,
        plural_last_word: bool,
        prose_order: Mapping[str, Sequence[str]],
    ) -> None:
        self._root: dict = {}
        self._reader = reader
        # the PT's own LLT first, then the lowest code: the first name stored at a node wins
        ordered = sorted(terms, key=lambda t: (t.llt_code != t.pt_code, int(t.llt_code)))
        other_forms: list[tuple[tuple[str, ...], Term]] = []
        prose_firsts = {reader.key(last): firsts for last, firsts in prose_order.items()}
        for term in ordered:
            name = reader.words(term.llt_name)
            if sum(c.isalnum() for c in term.llt_name) < shortest_name:
                continue
            keys = tuple(w.key for w in name)
            if capitals_match_capitals and all_capitals(term.llt_name):
                self._store(keys, term, tuple(w.text for w in name))
                continue
            self._store(keys, term, None)
            forms = [keys]
            for first in prose_firsts.get(keys[-1], ()) if len(keys) > 1 else ():
                forms.append(tuple(w.key for w in reader.words(first)) + keys[:-1])
            if plural_last_word:
                forms += [form[:-1] + (plural(form[-1]),) for form in forms]
            forms = forms[1:]  # the name as written is stored already
            other_forms += [(form, term) for form in forms]
        for form, term in other_forms:
            self._store(form, term, None)

    @classmethod
    def from_rules(cls, terms: Iterable[Term], reader: TextReader) -> TermIndex:
        return cls(
            terms,
            reader,
            capitals_match_capitals=rulebook.value(RULE, "capitals_match_capitals"),
            shortest_name=rulebook.value(RULE, "shortest_name"),
            plural_last_word=rulebook.value(RULE, "plural_last_word"),
            prose_order=rulebook.value(RULE, "prose_order"),
        )

    def _store(self, keys: tuple[str, ...], term: Term, exact: tuple[str, ...] | None) -> None:
        node = self._root
        for key in keys:
            node = node.setdefault(key, {})
        node.setdefault(_END, []).append((term, exact))

    def named(self, keys: Sequence[str]) -> Term | None:
        """The term a name (or one of its other forms) is, as keys, or None."""
        node: dict | None = self._root
        for key in keys:
            node = node.get(key) if node is not None else None
        found = node.get(_END, ()) if node is not None else ()
        return next((term for term, exact in found if exact is None), None)

    def hits(self, sentence: Sequence[Word]) -> list[Hit]:
        found: list[Hit] = []
        i, n = 0, len(sentence)
        while i < n:
            best = self._longest(sentence, i)
            if best is None:
                i += 1
                continue
            found.append(best)
            i = best.last
        return found

    def _longest(self, sentence: Sequence[Word], i: int) -> Hit | None:
        node: dict | None = self._root
        j, best = i, None
        while j < len(sentence) and node is not None:
            node = node.get(sentence[j].key)
            if node is None:
                break
            j += 1
            for term, exact in node.get(_END, ()):
                if exact is None or tuple(w.text for w in sentence[i:j]) == exact:
                    best = Hit(term, i, j)
                    break
        return best


class Headings:
    """MedDRA's body-system class names, in singular or plural, where a label uses
    them as headings (a table's group headings): a term inside one is a heading,
    not a reaction."""

    def __init__(self, names: Iterable[str], reader: TextReader) -> None:
        self._by_first: dict[str, list[tuple[str, ...]]] = {}
        for name in names:
            keys = tuple(_singular(w.key) for w in reader.words(name))
            if keys:
                self._by_first.setdefault(keys[0], []).append(keys)

    def spans(self, sentence: Sequence[Word]) -> list[tuple[int, int]]:
        keys = [_singular(w.key) for w in sentence]
        found = []
        for i, key in enumerate(keys):
            for name in self._by_first.get(key, ()):
                if tuple(keys[i : i + len(name)]) == name:
                    found.append((i, i + len(name)))
        return found


def _singular(key: str) -> str:
    return key[:-1] if len(key) > 3 and key.endswith("s") else key
