"""How the screens name a label (rule explorer-label-names): its product, read from the label's
title, its ingredients and, only where the labels read for a page differ by form, its forms.
The page puts the words together (ui/labels.js, labelName); this gives it the parts.

    product(title, ingredients)        the brand the title names, or None
    parts(rows)                        setid -> {setid, version, date, product, ingredients, forms}
    named(opened, setids)              the same, read from the release's label_candidates_T
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from open_altio.rulebook import value

if TYPE_CHECKING:
    from .release import OpenRelease

RULE = "explorer-label-names"
CANDIDATES = "label_candidates_T"
RXNORM_JOIN = " / "  # how RxNorm's name of a combination joins its ingredients
_LETTERS = re.compile(r"[^\W\d_]+")
_PARTS = re.compile(r"([-/])")  # a word's parts, each written on its own: Zomig-ZMT


def _in_capitals(word: str) -> bool:
    return any(c.isupper() for c in word) and not any(c.islower() for c in word)


def _words(text: str) -> list[tuple[str, bool]]:
    """`text`'s words, each with whether it ends the sentence or the phrase (a full stop, not
    one inside an abbreviation such as I.V., or a comma), with the trademark marks taken out:
    a sign wherever it stands, a mark of letters only where it is a word of its own."""
    marks = value(RULE, "marks")
    for mark in marks:
        if not mark.isalpha():
            text = text.replace(mark, " ")
    out: list[tuple[str, bool]] = []
    for word in text.split():
        ends = word[-1] in ".,;:" and not (word[-1] == "." and "." in word[:-1])
        word = word.rstrip(".,;:") if ends else word
        if word in marks:
            if ends and out:
                out[-1] = (out[-1][0], True)
            continue
        out.append((word, ends))
    return out


def _cased(name: list[str]) -> str:
    """A brand written in capitals, in title case: a short word after the first keeps its
    capitals (HCT), a small word is written small."""
    short, small = value(RULE, "capitals_up_to"), set(value(RULE, "small_words"))
    out: list[str] = []
    for i, word in enumerate(name):
        if i and word.lower() in small:
            out.append(word.lower())
            continue
        parts = _PARTS.split(word)
        out.append(
            "".join(
                p
                if _PARTS.fullmatch(p) or (i or j) and len("".join(_LETTERS.findall(p))) <= short
                else p.capitalize()
                for j, p in enumerate(parts)
            )
        )
    return " ".join(out)


def product(title: str | None, ingredients: str) -> str | None:
    """The product the label's title names after the Highlights' sentence, in title case; None
    for a title without it, a name not in capitals, or a generic's name, which shares a word
    with the label's ingredients (RxNorm's names, joined with " / ")."""
    text = " ".join((title or "").split())
    at = text.lower().find(value(RULE, "product_from").lower())
    if at < 0:
        return None
    name: list[str] = []
    for word, ends in _words(text[at + len(value(RULE, "product_from")) :]):
        if not word or not _in_capitals(word):
            break
        name.append(word)
        if ends:
            break
    half = len(name) // 2
    if name and len(name) % 2 == 0 and name[:half] == name[half:]:
        name = name[:half]  # a title that writes the name twice
    letters = value(RULE, "shared_word_letters")
    own = {w.lower() for w in _LETTERS.findall(ingredients) if len(w) >= letters}
    if not name or own & {w.lower() for w in _LETTERS.findall(" ".join(name))}:
        return None
    return _cased(name)


def parts(rows: Iterable[tuple]) -> dict[str, dict]:
    """The labels read for one page, each by its set ID with the parts its name is made of and
    the version the flags were read from, from their rows of label_candidates_T: (setid, rxcui,
    ingredient, title, effective date, version, the route families it was chosen for). Forms are
    named only when two of the labels have one RxNorm code: each then names its own families;
    otherwise none does."""
    rows = list(rows)
    codes: dict[str, set[str]] = {}
    for setid, rxcui, *_ in rows:
        codes.setdefault(rxcui, set()).add(setid)
    return {
        setid: {
            "setid": setid,
            "version": version,
            "date": day,
            "product": product(title, ingredient),
            "ingredients": ingredient.split(RXNORM_JOIN),
            "forms": sorted(families) if len(codes[rxcui]) > 1 else [],
        }
        for setid, rxcui, ingredient, title, day, version, families in rows
    }


def named(opened: OpenRelease, setids: Iterable[str]) -> dict[str, dict]:
    """`parts` of the labels with these set IDs, read from the release."""
    wanted = sorted(set(setids))
    if not wanted:
        return {}
    path = str(opened.folder / opened.manifest["tables"][CANDIDATES]["path"])
    cur = opened.cursor()
    try:
        return parts(
            cur.execute(
                "SELECT setid_T, rxcui_T, ingredient_T, title_T, effective_date_T, spl_version_T,"
                " list(DISTINCT route_family_T) FROM read_parquet(?)"
                " WHERE setid_T IN (SELECT unnest(?::VARCHAR[])) GROUP BY ALL",
                [path, wanted],
            ).fetchall()
        )
    finally:
        cur.close()


__all__ = ["named", "parts", "product"]
