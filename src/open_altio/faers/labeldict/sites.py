"""A site phrase governing a list (rule label-dictionary): in "injection site reactions
(erythema and/or itching, pain or swelling)" each term is a reaction at the injection site, so it
codes to the site's own term ("Injection site pruritus"), else to the site's umbrella term
("Injection site reaction"), never to the plain term; a term with neither is kept off."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from open_altio import rulebook

from .scope import Verdict
from .terms import Hit, TermIndex
from .text import RULE, TextReader, Word

NO_SITE_TERM = Verdict(False, RULE, "site", "a site governs it and no term names it at that site")
_OPEN, _CLOSE = {"(", "["}, {")", "]"}


@dataclass(frozen=True)
class SiteLists:
    index: TermIndex
    sites: frozenset[str]  # the words a site phrase starts with: injection, infusion
    heads: frozenset[str]  # what may follow "site": reactions, events
    starts: tuple[tuple[str, ...], ...]  # what opens the governed list: "(", "including"
    ends: frozenset[str]  # what closes it outside brackets
    not_sites: frozenset[str]  # "administration site conditions" is a body-system class
    reach: int  # words between the phrase and a later "including"
    on: bool

    @classmethod
    def from_rules(cls, reader: TextReader, index: TermIndex) -> SiteLists:
        values: Mapping = rulebook.value(RULE, "site_lists")

        def keys(items: Sequence[str]) -> frozenset[str]:
            return frozenset(reader.key(w) for w in items)

        starts = (tuple(w.key for w in reader.words(p)) for p in values["starts"])
        return cls(
            index,
            keys(values["sites"]),
            keys(values["heads"]),
            tuple(sorted(starts, key=len, reverse=True)),
            keys(values["ends"]),
            keys(values["not_after"]),
            values["reach_words"],
            bool(values["read"]),
        )

    def recode(self, words: Sequence[Word], hits: Sequence[Hit]) -> tuple[list[Hit], set[int]]:
        """The hits with each one inside a governed list coded to its site's term, and the
        positions of those with no site term to code to."""
        out, off = list(hits), set[int]()
        if not self.on:
            return out, off
        keys = [w.key for w in words]
        for site, start, end in self._lists(keys, words):
            for n, hit in enumerate(hits):
                inside = start <= hit.first and hit.last <= end
                if not inside or "site" in hit.term.llt_name.lower():
                    continue
                named = tuple(keys[hit.first : hit.last])
                term = self.index.named((site, "site", *named)) or self.index.named(
                    (site, "site", "reaction")
                )
                if term is None:
                    off.add(n)
                else:
                    out[n] = replace(hit, term=term)
        return out, off

    def _lists(self, keys: list[str], words: Sequence[Word]) -> list[tuple[str, int, int]]:
        """(site word, first, last word position) of each list a site phrase governs."""
        found = []
        for i in range(len(keys) - 1):
            if keys[i] not in self.sites:
                continue
            j = i + 1
            while j + 1 < len(keys) and keys[j] == "/" and keys[j + 1] in self.sites:
                j += 2  # "injection/infusion site"
            if j >= len(keys) or keys[j] not in {"site", "sites"}:
                continue
            if keys[j + 1 : j + 2] and keys[j + 1] in self.not_sites:
                continue
            if keys[max(0, i - 2) : i] in (["disorders", "and"], ["conditions", "and"]):
                continue
            k = j + 1
            while k < len(keys) and keys[k] in self.heads:
                k += 1
            bracketed = keys[k : k + 1] == ["("] and keys[k + 2 : k + 3] == [")"]
            if bracketed and _abbreviation(words[k + 1].text):
                k += 3  # the phrase's abbreviation: "(ISRs)"
            span = self._governed(keys, k)
            if span is not None:
                found.append((keys[i], *span))
        return found

    def _governed(self, keys: list[str], k: int) -> tuple[int, int] | None:
        """The list opened at or a little after `k`, to its closing bracket, a stop or the
        end of the sentence."""
        for gap in range(self.reach + 1):
            at = k + gap
            if at >= len(keys) or (gap and keys[at - 1] in self.ends):
                return None
            for start in self.starts:
                if tuple(keys[at : at + len(start)]) == start:
                    first = at + len(start)
                    if start == ("(",):
                        return first, _closing(keys, first)
                    return first, self._stop(keys, first)
        return None

    def _stop(self, keys: list[str], first: int) -> int:
        depth = 0
        for i in range(first, len(keys)):
            if keys[i] in _OPEN:
                depth += 1
            elif keys[i] in _CLOSE:
                if depth == 0:
                    return i
                depth -= 1
            elif depth == 0 and keys[i] in self.ends:
                return i
        return len(keys)


def _abbreviation(text: str) -> bool:
    letters = text[:-1] if text.endswith("s") else text
    return len(letters) > 1 and letters.isupper()


def _closing(keys: list[str], first: int) -> int:
    depth = 0
    for i in range(first, len(keys)):
        if keys[i] in _OPEN:
            depth += 1
        elif keys[i] in _CLOSE:
            if depth == 0:
                return i
            depth -= 1
    return len(keys)
