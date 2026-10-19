"""Code a label's sections into MedDRA terms, each kept, kept off or uncertain (rules
label-dictionary, label-negation, label-population, label-table-rows and
label-treated-disease)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import groupby

from open_altio import rulebook

from .scope import SECTION_OFF, SentenceRules, Verdict
from .sites import NO_SITE_TERM, SiteLists
from .tables import TableReader, cells
from .terms import Headings, Hit, Term, TermIndex
from .text import RULE, TextReader, Word
from .unstated import Unstated

TABLE_RULE = "label-table-rows"
TREATED = "label-treated-disease"

INDICATED = Verdict(True, TREATED, "indication", "the label's indications name it")
# nothing in the indications is left for review: a phrase the rules cannot read there is not
# taken as the disease treated, so the pair is compared with the safety sections as usual
NOT_SURE = Verdict(False, TREATED, "unsure", "the indications may not name it as the disease")


def _sited(verdicts: Sequence[Verdict], no_site: set[int]) -> list[Verdict]:
    return [NO_SITE_TERM if n in no_site else v for n, v in enumerate(verdicts)]


def _indication(verdict: Verdict) -> Verdict:
    if verdict.kept is None:
        return NOT_SURE
    return INDICATED if verdict.kept else verdict


TERM_COLUMNS = (
    "set_id",
    "section",
    "pt_code",
    "pt_name",
    "llt_code",
    "matched_text",
    "sentence",
    "kept",
    "rule",
    "decided_by",
    "item_id",
)
ITEM_FIELDS = (
    "item_id",
    "set_id",
    "rxcui",
    "drug",
    "label_date",
    "rank",
    "section",
    "sentence",
    "candidate_pt",
    "candidate_pt_code",
    "matched_text",
    "why_uncertain",
)


@dataclass(frozen=True)
class SectionRow:
    set_id: str
    section: str
    ordinal: int
    is_table_row: bool
    text: str


@dataclass(frozen=True)
class LabelInfo:
    """What a person deciding an item sees about its label; several drugs or RxNorm
    codes, when one label serves them, are joined with ";"."""

    rxcui: str
    drug: str
    label_date: str | None


NO_INFO = LabelInfo("", "", None)


@dataclass
class Coded:
    terms: list[dict] = field(default_factory=list)
    items: dict[str, dict] = field(default_factory=dict)  # by item_id


def item_id(set_id: str, section: str, sentence: str, pt_code: str | None, reason: str) -> str:
    """Stable across builds while the label says the same thing in the same place, so a
    person's decision on it carries over to the next build and the next label version."""
    raw = "\x1f".join((set_id, section, sentence, pt_code or "", reason))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class LabelCoder:
    def __init__(self, terms: Iterable[Term], heading_names: Iterable[str]) -> None:
        self.reader = TextReader.from_rules()
        self.index = TermIndex.from_rules(terms, self.reader)
        self.sites = SiteLists.from_rules(self.reader, self.index)
        headings = heading_names if rulebook.value(RULE, "body_system_headings") else ()
        self.headings = Headings(headings, self.reader)
        self.rules = SentenceRules.from_rules(self.reader)
        self.unstated = Unstated()
        self.tables = TableReader.from_rules(self.reader)
        self.sections = set(rulebook.value(RULE, "sections"))
        # switched off, the indications are not read, so nothing is the disease treated
        self.indications = rulebook.value(TREATED, "indications_section")
        if not rulebook.is_on(TREATED):
            self.indications = None
        self.unnamed_sections = set(rulebook.value(TABLE_RULE, "unnamed_row_sections"))
        if not rulebook.is_on(TABLE_RULE):
            self.unnamed_sections = set()

    def code(
        self, rows: Iterable[SectionRow], labels: Mapping[str, LabelInfo], into: Coded
    ) -> None:
        """Code rows of one or more labels, in (set_id, section, ordinal) order."""
        for (set_id, section), group in groupby(rows, key=lambda r: (r.set_id, r.section)):
            if section not in self.sections and section != self.indications:
                continue
            label = _Label(set_id, section, labels.get(set_id, NO_INFO), into, self.unstated)
            for is_table, run in groupby(group, key=lambda r: r.is_table_row):
                if is_table:
                    self._table(label, [r.text for r in run])
                else:
                    for row in run:
                        for sentence in self.reader.sentences(row.text):
                            self._sentence(label, sentence)

    def _sentence(self, label: _Label, sentence: str) -> None:
        words = self.reader.words(sentence)
        hits, no_site = self.sites.recode(words, self.index.hits(words))
        if not hits:
            return
        heads = self.headings.spans(words)
        if label.section != self.indications:
            verdicts = self.rules.judge(words, hits, heads, label.section)
            label.add(sentence, words, hits, _sited(verdicts, no_site))
            return
        verdicts = self.rules.judge(words, hits, heads, label.section, full=False)
        label.add(sentence, words, hits, [_indication(v) for v in _sited(verdicts, no_site)])

    def _table(self, label: _Label, rows: Sequence[str]) -> None:
        for row, reading in zip(rows, self.tables.read(rows), strict=True):
            if reading.verdict is None:
                self._sentence(label, row)
                continue
            words = self.reader.words(row)
            hits, no_site = self.sites.recode(words, self.index.hits(words))
            heads = self.headings.spans(words)
            verdicts = [self.rules.word_rule(words, h, heads) or reading.verdict for h in hits]
            verdicts = _sited(verdicts, no_site)
            if label.section in self.rules.population_sections:
                verdicts = [v if v.kept is False else SECTION_OFF for v in verdicts]
            if label.section == self.indications:
                verdicts = [_indication(v) for v in verdicts]
            label.add(row, words, hits, verdicts)
            first = cells(row)[0]
            unnamed = reading.under_header and reading.verdict.reason != "header"
            in_section = label.section in self.unnamed_sections - {self.indications}
            if unnamed and in_section and not hits and any(c.isalpha() for c in first):
                why = "the table lists something no MedDRA term matches"
                label.add_item(row, None, first, Verdict(None, TABLE_RULE, "unnamed-row", why))


@dataclass
class _Label:
    set_id: str
    section: str
    info: LabelInfo
    into: Coded
    unstated: Unstated

    def add(
        self,
        sentence: str,
        words: Sequence[Word],
        hits: Sequence[Hit],
        verdicts: Sequence[Verdict],
    ) -> None:
        for hit, verdict in zip(hits, verdicts, strict=True):
            matched = sentence[words[hit.first].start : words[hit.last - 1].end]
            if verdict.kept is None:  # a line the rules could not read may still state nothing
                verdict = self.unstated.verdict(sentence, matched) or verdict
            item = None
            if verdict.kept is None:
                item = self.add_item(sentence, hit.term, matched, verdict)
            self.into.terms.append(
                {
                    "set_id": self.set_id,
                    "section": self.section,
                    "pt_code": hit.term.pt_code,
                    "pt_name": hit.term.pt_name,
                    "llt_code": hit.term.llt_code,
                    "matched_text": matched,
                    "sentence": sentence,
                    "kept": verdict.kept,
                    "rule": verdict.rule,
                    "decided_by": None if verdict.kept is None else "rule",
                    "item_id": item,
                }
            )

    def add_item(self, sentence: str, term: Term | None, matched: str, verdict: Verdict) -> str:
        pt_code = term.pt_code if term else None
        key = item_id(self.set_id, self.section, sentence, pt_code, verdict.reason)
        self.into.items.setdefault(
            key,
            {
                "item_id": key,
                "set_id": self.set_id,
                "rxcui": self.info.rxcui,
                "drug": self.info.drug,
                "label_date": self.info.label_date,
                "rank": None,
                "section": self.section,
                "sentence": sentence,
                "candidate_pt": term.pt_name if term else None,
                "candidate_pt_code": pt_code,
                "matched_text": matched,
                "why_uncertain": verdict.why,
            },
        )
        return key


def distinct_terms(rows: Iterable[dict]) -> list[dict]:
    """A label repeats itself (the same sentence in two places of one section); one row
    per term, sentence and outcome is enough."""
    seen, out = set(), []
    for row in rows:
        key = (
            row["set_id"],
            row["section"],
            row["llt_code"],
            row["sentence"],
            row["kept"],
        )
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out
