"""How a WHO class name reads on a screen. WHO writes its levels 1 to 3 in capitals and levels 4
and 5 normally; a person sees the capitals in sentence case, keeping the abbreviations WHO itself
writes in capitals in its normally written names. Files, SQL and the Tables page keep WHO's text,
so only the explorer's answers for screens go through here."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .release import OpenRelease

_WORD = re.compile(r"[A-Za-z]+")


def abbreviations_in(names: Iterable[str]) -> frozenset[str]:
    """Every word of two or more letters that a normally written name writes in capitals."""
    return frozenset(
        w for n in names if n != n.upper() for w in _WORD.findall(n) if len(w) > 1 and w.isupper()
    )


def shown(name: str | None, abbreviations: frozenset[str]) -> str | None:
    """`name` for a screen: an all-capitals name in sentence case with its abbreviations in
    capitals; any other name as it is."""
    if not name or name != name.upper() or name == name.lower():
        return name

    def word(m: re.Match) -> str:
        w = m.group()
        return w if w in abbreviations else w.lower()

    text = _WORD.sub(word, name)
    first = _WORD.search(text)
    return (
        text
        if first is None
        else text[: first.start()] + text[first.start()].upper() + text[first.start() + 1 :]
    )


@lru_cache(maxsize=4)
def _of(opened: OpenRelease) -> frozenset[str]:
    rows = opened.rows("SELECT atc_name_T AS n FROM explorer_atc_class_T WHERE atc_level_T >= 4")
    return abbreviations_in(r["n"] for r in rows if r["n"])


def abbreviations(opened: OpenRelease) -> frozenset[str]:
    return _of(opened)
