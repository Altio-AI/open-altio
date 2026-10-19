"""Whether each term a sentence names is on the label: the sentence rules (rules
label-negation, label-population and label-dictionary)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property

from open_altio import rulebook

from .terms import Hit
from .text import RULE, TextReader, Word, is_mark

NEGATION = "label-negation"
POPULATION = "label-population"
KEPT_OFF = "kept_off"


@dataclass(frozen=True)
class Verdict:
    kept: bool | None  # None: the rules cannot settle it
    rule: str  # the rule file that decided
    reason: str  # a short fixed name, part of an uncertain item's id
    why: str  # plain words, for the person who decides an uncertain one


KEPT = Verdict(True, RULE, "named", "the label names it")
# the contraindications name who must not take the drug (rule label-population)
SECTION_OFF = Verdict(False, "label-population", "section", "names who must not take the drug")
# an outcome the drug lowers the risk of is not the disease it treats (label-treated-disease)
TREATED = "label-treated-disease"
NOT_TREATED = Verdict(False, TREATED, "risk", "names an outcome the drug lowers the risk of")


@dataclass(frozen=True)
class Cue:
    phrases: tuple[tuple[str, ...], ...]
    window: int
    bare_off: bool  # a term after a bare comma is kept off, else uncertain


class SentenceRules:
    def __init__(self, reader: TextReader, values: Mapping[str, Mapping]) -> None:
        def phrases(items: Iterable[str]) -> tuple[tuple[str, ...], ...]:
            found = (tuple(w.key for w in reader.words(p)) for p in items)
            return tuple(sorted(found, key=len, reverse=True))  # the longest phrase wins

        d, neg, pop = values[RULE], values[NEGATION], values[POPULATION]
        self._list_words = {reader.key(w) for w in d["list_words"]}
        self._gap = d["list_gap_words"]
        self._ends = {reader.key(w) for w in d["scope_ends"]} | {";", ":"}
        self._everyday = {
            name.lower(): {reader.key(w) for w in after}
            for name, after in d["everyday_names"].items()
        }
        self._boilerplate = {name.lower() for name in d["boilerplate_names"]}
        self._see = {reader.key(w) for w in d["cross_reference_words"]}
        bare_off = neg["bare_comma_items"] == KEPT_OFF
        self.before = Cue(phrases(neg["before"]), neg["window_words"], bare_off)
        self.after = Cue(phrases(neg["after"]), neg["window_words"], bare_off)
        self._exclusion = phrases(neg["exclusion"])
        self._exclusion_ends = {reader.key(w) for w in neg["exclusion_ends"]}
        self._clause_words = {reader.key(w) for w in neg["exclusion_clause_words"]}
        self._unread = {reader.key(w) for w in neg["unread_words"]}
        self._unread_window = neg["unread_window_words"]
        self.population = Cue(
            phrases(pop["phrases"]),
            pop["window_words"],
            pop["bare_comma_items"] == KEPT_OFF,
        )
        self.population_sections = set(pop["population_sections"])
        self._trial = phrases(pop["trial_exclusion"])
        self._risk_starts = phrases(pop["risk_starts"])
        self._risk_ends = phrases(pop["risk_ends"])
        self._people = {reader.key(w) for w in pop["people_words"]}

        self._risks = phrases(rulebook.value(TREATED, "risk_phrases"))
        self._risk_window = rulebook.value(TREATED, "risk_window_words")
        self._qualifiers = phrases(rulebook.value(TREATED, "qualifier_phrases"))
        self._never_treated = [
            f" {w.lower()} " for w in rulebook.value(TREATED, "never_treated_words")
        ]

    @classmethod
    def from_rules(cls, reader: TextReader) -> SentenceRules:
        names = {
            RULE: (
                "list_words",
                "list_gap_words",
                "scope_ends",
                "everyday_names",
                "boilerplate_names",
                "cross_reference_words",
            ),
            NEGATION: (
                "before",
                "after",
                "window_words",
                "bare_comma_items",
                "unread_words",
                "unread_window_words",
                "exclusion",
                "exclusion_ends",
                "exclusion_clause_words",
            ),
            POPULATION: (
                "phrases",
                "window_words",
                "bare_comma_items",
                "population_sections",
                "people_words",
                "trial_exclusion",
                "risk_starts",
                "risk_ends",
            ),
        }
        values = {
            rule: {key: rulebook.value(rule, key) for key in keys} for rule, keys in names.items()
        }
        # a rule a person switched off reads no phrase, so it keeps nothing off
        if not rulebook.is_on(NEGATION):
            values[NEGATION] = {
                **values[NEGATION],
                "before": [],
                "after": [],
                "unread_words": [],
                "exclusion": [],
            }
        if not rulebook.is_on(POPULATION):
            values[POPULATION] = {
                **values[POPULATION],
                "phrases": [],
                "people_words": [],
                "population_sections": [],
                "trial_exclusion": [],
                "risk_starts": [],
                "risk_ends": [],
            }
        return cls(reader, values)

    # the rules every hit passes, table rows included --------------------------------

    def word_rule(
        self, sentence: Sequence[Word], hit: Hit, headings: Sequence[tuple[int, int]]
    ) -> Verdict | None:
        """A verdict from the term's own words, or None when they settle nothing."""
        if self._excluded(sentence, hit):
            return Verdict(False, NEGATION, "exclusion", "an exclusion clause names it")
        name = hit.term.llt_name.lower()
        if name in self._boilerplate:
            return Verdict(False, RULE, "boilerplate", "a general word for side effects")
        if any(a <= hit.first and hit.last <= b for a, b in headings):
            return Verdict(False, RULE, "heading", "part of a body system heading")
        if self._in_cross_reference(sentence, hit):
            return Verdict(False, RULE, "cross-reference", "names another part of the label")
        if name in self._everyday:
            follows = sentence[hit.last].key if hit.last < len(sentence) else ""
            if follows in self._everyday[name]:
                return Verdict(False, RULE, "everyday", "used here as an everyday word")
            return Verdict(None, RULE, "everyday-word", "may be an everyday word here")
        return None

    def _excluded(self, sentence: Sequence[Word], hit: Hit) -> bool:
        """Inside an exclusion clause: "Dizziness (excluding vertigo)", "does not include
        injection site pain", to its closing bracket or the end of its clause."""
        keys = [w.key for w in sentence]
        for _a, b in self._find(self._exclusion, sentence, ()):
            if b <= hit.first and hit.last <= self._clause_end(keys, b):
                return True
        return False

    def _clause_end(self, keys: list[str], start: int) -> int:
        depth = 0
        for i in range(start, len(keys)):
            if keys[i] in {"(", "["}:
                depth += 1
            elif keys[i] in {")", "]"}:
                if depth == 0:
                    return i
                depth -= 1
            elif depth == 0 and self._ends_clause(keys, i):
                return i
        return len(keys)

    def _ends_clause(self, keys: list[str], i: int) -> bool:
        if keys[i] in self._exclusion_ends:
            return True
        return keys[i] == "," and i + 1 < len(keys) and keys[i + 1] in self._clause_words

    def _in_cross_reference(self, sentence: Sequence[Word], hit: Hit) -> bool:
        """Inside brackets that open with "see": a pointer to a section, such as
        "[see Warnings and Precautions (5.1)]", not a reaction."""
        depth = 0
        for i in range(hit.first - 1, -1, -1):
            key = sentence[i].key
            if key in {")", "]"}:
                depth += 1
            elif key in {"(", "["}:
                if depth == 0:
                    return i + 1 < len(sentence) and sentence[i + 1].key in self._see
                depth -= 1
        return False

    # sentences ----------------------------------------------------------------------

    def judge(
        self,
        sentence: Sequence[Word],
        hits: Sequence[Hit],
        headings: Sequence[tuple[int, int]],
        section: str,
        *,
        full: bool = True,
    ) -> list[Verdict]:
        """One verdict per hit. Not `full` (the indications section, which names the
        disease treated on purpose) only negation and the term's own words count."""
        cues: list[tuple[int, int]] = []
        off: dict[int, Verdict] = {}
        unsure: dict[int, Verdict] = {}
        neg_off = Verdict(False, NEGATION, "negation", "the label says it did not happen")
        neg_unsure = Verdict(
            None, NEGATION, "negation-comma", "may be in a list of what did not happen"
        )
        for a, b in self._find(self.before.phrases, sentence, hits):
            cues.append((a, b))
            sure, maybe = self._list_after(sentence, hits, b, self.before.window)
            self._mark(sure, maybe, self.before.bare_off, off, unsure, neg_off, neg_unsure)
        for a, b in self._find(self.after.phrases, sentence, hits):
            cues.append((a, b))
            sure, maybe = self._list_before(sentence, hits, a, self.after.window)
            self._mark(sure, maybe, self.after.bare_off, off, unsure, neg_off, neg_unsure)
        if not full:  # the indications: a risk the drug lowers, or a death, is not treated
            for n in self._guarded(sentence, hits):
                off.setdefault(n, NOT_TREATED)
            for a, b in self._find(self._qualifiers, sentence, ()):  # "signs of inflammation"
                for n, hit in enumerate(hits):
                    if a <= hit.first and hit.last <= b:
                        off.setdefault(n, NOT_TREATED)
        if full:
            pop_off = Verdict(False, POPULATION, "population", "says who the patients are")
            pop_unsure = Verdict(
                None, POPULATION, "population-comma", "may say who the patients are"
            )
            for a, b in self._find(self.population.phrases, sentence, hits):
                cues.append((a, b))
                sure, maybe = self._list_after(sentence, hits, b, self.population.window)
                bare = self.population.bare_off
                self._mark(sure, maybe, bare, off, unsure, pop_off, pop_unsure)
            trial = Verdict(False, POPULATION, "trial", "a trial's exclusions or a risk factor")
            for n in self._trial_or_risk(sentence, hits):
                off.setdefault(n, trial)
            for n, hit in enumerate(hits):  # "hypertensive patients", "diabetic women"
                after = sentence[hit.last].key if hit.last < len(sentence) else ""
                if after in self._people:
                    off.setdefault(n, pop_off)
        in_cue = {i for a, b in cues for i in range(a, b)}
        verdicts = []
        for n, hit in enumerate(hits):
            own = self.word_rule(sentence, hit, headings)
            if own is not None and own.kept is False:
                verdicts.append(own)
            elif n in off:
                verdicts.append(off[n])
            elif full and section in self.population_sections:
                verdicts.append(SECTION_OFF)
            elif own is not None:
                verdicts.append(own)
            elif n in unsure:
                verdicts.append(unsure[n])
            elif full and self._unread_before(sentence, hit, in_cue):
                why = "a word of negation the rules do not read comes just before it"
                verdicts.append(Verdict(None, NEGATION, "unread-negation", why))
            else:
                verdicts.append(KEPT)
        if not full and self._no_indication(sentence):  # a line naming no disease treated
            return [NO_INDICATION if v.kept else v for v in verdicts]
        return verdicts

    def _trial_or_risk(self, sentence: Sequence[Word], hits: Sequence[Hit]) -> set[int]:
        """The hits in a clause about a trial's exclusions ("the trial excluded patients
        with active pneumonitis"), and those between "patients with" and "are at greater
        risk" ("patients with renal impairment are at greater risk for TLS")."""
        keys = [w.key for w in sentence]
        cuts = [-1] + [i for i, k in enumerate(keys) if k == ";"] + [len(keys)]
        found: set[int] = set()
        for a, _b in self._find(self._trial, sentence, hits):
            lo = max(c for c in cuts if c < a)
            hi = min(c for c in cuts if c >= a)
            found |= {n for n, h in enumerate(hits) if lo < h.first and h.last <= hi}
        for _a, b in self._find(self._risk_starts, sentence, hits):
            ends = [e for e, _f in self._find(self._risk_ends, sentence, hits) if e >= b]
            if ends:
                found |= {n for n, h in enumerate(hits) if b <= h.first and h.last <= ends[0]}
        return found

    @staticmethod
    def _mark(
        sure: list[int],
        maybe: list[int],
        bare_off: bool,
        off: dict[int, Verdict],
        unsure: dict[int, Verdict],
        off_verdict: Verdict,
        unsure_verdict: Verdict,
    ) -> None:
        for n in sure + (maybe if bare_off else []):
            off.setdefault(n, off_verdict)
        for n in [] if bare_off else maybe:
            unsure.setdefault(n, unsure_verdict)

    def _find(
        self,
        phrases: Sequence[tuple[str, ...]],
        sentence: Sequence[Word],
        hits: Sequence[Hit],
    ) -> list[tuple[int, int]]:
        """Where the phrases stand, longest first, never inside a term."""
        taken = {i for h in hits for i in range(h.first, h.last)}
        keys = [w.key for w in sentence]
        found, i = [], 0
        while i < len(keys):
            for phrase in phrases:
                end = i + len(phrase)
                if tuple(keys[i:end]) == phrase and not taken & set(range(i, end)):
                    found.append((i, end))
                    i = end
                    break
            else:
                i += 1
        return found

    def _is_stop(self, word: Word) -> bool:
        return word.key in self._ends or is_mark(word.key)

    def _list_after(
        self, sentence: Sequence[Word], hits: Sequence[Hit], start: int, window: int
    ) -> tuple[list[int], list[int]]:
        """The terms listed from `start`: those surely in the list, and those after a
        bare comma with no "and" or "or" later, which may start a new clause."""
        by_first = {h.first: n for n, h in enumerate(hits)}
        n = self._next_hit(sentence, by_first, start, window)
        if n is None:
            return [], []
        sure, maybe = [n], list[int]()
        while True:
            k, comma, joined = hits[n].last, False, False
            while k < len(sentence) and sentence[k].key in {",", "/"} | self._list_words:
                comma |= sentence[k].key == ","
                joined |= sentence[k].key in self._list_words
                k += 1
            if not (comma or joined):
                break
            nxt = self._next_hit(sentence, by_first, k, self._gap)
            if nxt is None:
                break
            if joined:
                sure, maybe = sure + maybe + [nxt], []
            else:
                maybe.append(nxt)
            n = nxt
        return sure, maybe

    def _next_hit(
        self, sentence: Sequence[Word], by_first: dict[int, int], start: int, window: int
    ) -> int | None:
        for i in range(start, min(len(sentence), start + window + 1)):
            if i in by_first:
                return by_first[i]
            if self._is_stop(sentence[i]) and sentence[i].key != ",":
                return None
        return None

    def _list_before(
        self, sentence: Sequence[Word], hits: Sequence[Hit], end: int, window: int
    ) -> tuple[list[int], list[int]]:
        """The terms listed just before a phrase at `end`, read backwards. A term's own
        modifiers come before it, so a term further back must end right at the comma or
        "and" that joins it."""
        by_last = {h.last: n for n, h in enumerate(hits)}
        n = self._previous_hit(sentence, by_last, end, window)
        if n is None:
            return [], []
        sure, maybe, joined_seen = [n], list[int](), False
        separators = {",", "/"} | self._list_words
        while True:
            k, skipped = hits[n].first - 1, 0
            while k >= 0 and skipped < self._gap and k + 1 not in by_last:
                if sentence[k].key in separators or self._is_stop(sentence[k]):
                    break
                k, skipped = k - 1, skipped + 1
            comma, joined = False, False
            while k >= 0 and sentence[k].key in separators:
                comma |= sentence[k].key == ","
                joined |= sentence[k].key in self._list_words
                k -= 1
            if not (comma or joined) or k + 1 not in by_last:
                break
            n = by_last[k + 1]
            joined_seen |= joined
            (sure if joined_seen else maybe).append(n)
        return sure, maybe

    def _previous_hit(
        self, sentence: Sequence[Word], by_last: dict[int, int], end: int, window: int
    ) -> int | None:
        for i in range(end, max(-1, end - window - 1), -1):
            if i in by_last:
                return by_last[i]
            if i > 0 and self._is_stop(sentence[i - 1]) and sentence[i - 1].key != ",":
                return None
        return None

    def _unread_before(self, sentence: Sequence[Word], hit: Hit, in_cue: set[int]) -> bool:
        for i in range(hit.first - 1, max(-1, hit.first - self._unread_window - 1), -1):
            if self._is_stop(sentence[i]):
                return False
            if sentence[i].key in self._unread and i not in in_cue:
                return True
        return False

    def _guarded(self, sentence: Sequence[Word], hits: Sequence[Hit]) -> set[int]:
        """The hits listed after "the risks of" or "reduce the risk of" ("Because of the
        risks of addiction, abuse, misuse, overdose, and death, reserve opioid analgesics"),
        and every death."""
        found: set[int] = set()
        for _a, b in self._find(self._risks, sentence, hits):
            sure, maybe = self._list_after(sentence, hits, b, self._risk_window)
            found |= set(sure + maybe)
        for n, hit in enumerate(hits):
            name = f" {' '.join(hit.term.pt_name.lower().split())} "
            if any(w in name for w in self._never_treated):
                found.add(n)
        return found

    @cached_property
    def _no_indication_lines(self) -> tuple[tuple[str, ...], ...]:
        reader = TextReader.from_rules()
        lines = rulebook.value(TREATED, "not_indication_lines")
        return tuple(tuple(w.key for w in reader.words(p)) for p in lines)

    def _no_indication(self, sentence: Sequence[Word]) -> bool:
        """An indications sentence that names no disease treated: a risk lowered ("reduces
        the risk of cardiovascular death"), the opposite of an indication ("Limitations of
        Use", "has not been established"), or the class paragraph FDA puts on blood-pressure
        drugs ("many antihypertensive drugs have additional approved indications")."""
        return bool(self._find(self._no_indication_lines, sentence, ()))


NO_INDICATION = Verdict(False, TREATED, "not-indication", "the line names no disease treated")
