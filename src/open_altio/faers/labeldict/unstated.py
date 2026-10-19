"""A line the rules could not read, but that does not state the reaction (rules label-negation,
label-population and label-dictionary): a negation just before the term that no phrase reads, a
patient's condition before it, or a body-system word used as a heading."""

from __future__ import annotations

import re
from dataclasses import dataclass

from open_altio import rulebook

from .scope import NEGATION, POPULATION, Verdict
from .text import RULE


@dataclass(frozen=True)
class _Before:
    """A phrase within `chars` characters before the term makes the line unstated, unless the
    sentence holds a word that says the event was seen."""

    phrases: re.Pattern[str]
    chars: int
    verdict: Verdict


class Unstated:
    def __init__(self) -> None:
        negation, population = rulebook.is_on(NEGATION), rulebook.is_on(POPULATION)
        self._unless = re.compile(
            "|".join(map(re.escape, rulebook.value(NEGATION, "unstated_unless"))), re.I
        )
        self._either_way = re.compile(rulebook.value(NEGATION, "unstated_either_way"), re.I)
        rule = rulebook.value(NEGATION, "unstated_negation")
        words = "|".join(map(re.escape, rule["words"]))
        contraction = re.escape(rule["contraction"])
        self._negation = _Before(
            re.compile(rf"\b({words})\b|{contraction}\b", re.I),
            rule["chars"],
            Verdict(False, NEGATION, "unstated-negation", "a negation just before it, unread"),
        )
        rule = rulebook.value(POPULATION, "unstated_context")
        self._context = _Before(
            re.compile("|".join(map(re.escape, rule["phrases"])), re.I),
            rule["chars"],
            Verdict(False, POPULATION, "unstated-context", "a patient's condition before it"),
        )
        self._on = {"negation": negation, "context": population}
        self._headings = {w.lower() for w in rulebook.value(RULE, "heading_words")}
        self._heading = Verdict(False, RULE, "heading-word", "a body-system word as a heading")

    def verdict(self, sentence: str, matched: str) -> Verdict | None:
        """The verdict that says the line states nothing, or None when it may state it."""
        if matched.strip().lower() in self._headings:
            return self._heading
        if self._unless.search(sentence):
            return None
        at = sentence.lower().find(matched.lower())
        if at < 0:
            return None
        if (
            self._on["negation"]
            and not self._either_way.search(sentence)
            and self._negation.phrases.search(sentence[max(0, at - self._negation.chars) : at])
        ):
            return self._negation.verdict
        if self._on["context"] and self._context.phrases.search(
            sentence[max(0, at - self._context.chars) : at]
        ):
            return self._context.verdict
        return None
