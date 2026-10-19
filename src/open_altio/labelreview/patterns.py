"""Repeated patterns among decided items, as candidates for fixed rules.

The tool only points at candidates. A person reads them and writes any fixed rule.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from open_altio import rulebook

from . import decisions
from .items import Item, read_items
from .store import Folder

RULE = "label-review"


@dataclass(frozen=True)
class Pattern:
    kind: str
    value: str
    coded_as: str
    items: int
    drugs: int
    examples: tuple[str, ...]


def _keys(item: Item) -> list[tuple[str, str]]:
    words = int(rulebook.value(RULE, "pattern_opening_words"))
    opening = " ".join(item.sentence.casefold().split()[:words])
    keys = [
        ("why uncertain", item.why_uncertain),
        ("section", item.section),
        ("opening words", opening),
    ]
    if item.candidate_pt:
        keys.append(("rules' guess", item.candidate_pt.casefold()))
    return keys


def _coded_as(d: decisions.Decision) -> str:
    return "terms: " + "; ".join(sorted(d.pts)) if d.pts else f"none: {d.none_reason}"


def repeated(folder: Folder) -> list[Pattern]:
    """Groups of at least `pattern_min_items` decided items sharing a trait and coded alike."""
    least = int(rulebook.value(RULE, "pattern_min_items"))
    items = read_items(folder)
    groups: dict[tuple[str, str], list[tuple[Item, str]]] = defaultdict(list)
    for item_id, d in sorted(decisions.latest(folder).items()):
        item = items[item_id]
        for key in _keys(item):
            groups[key].append((item, _coded_as(d)))
    found = []
    for (kind, value), members in groups.items():
        coded = {c for _, c in members}
        if len(members) >= least and len(coded) == 1 and value:
            found.append(
                Pattern(
                    kind=kind,
                    value=value,
                    coded_as=coded.pop(),
                    items=len(members),
                    drugs=len({i.rxcui for i, _ in members}),
                    examples=tuple(i.item_id for i, _ in members[:3]),
                )
            )
    return sorted(found, key=lambda p: (-p.items, p.kind, p.value))
