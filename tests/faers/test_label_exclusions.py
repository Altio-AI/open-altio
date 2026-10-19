"""A term inside an exclusion clause is kept off the label (rule label-negation, exclusion).

Each test codes a few invented label lines with the invented MedDRA terms of
open_altio.testing.fakemeddra and reads back each term's verdict."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.faers.labeldict.coding import Coded, LabelCoder, LabelInfo, SectionRow
from open_altio.faers.labeldict.terms import Term
from open_altio.testing.fakemeddra import current_llts


@pytest.fixture(scope="module")
def coder() -> LabelCoder:
    return LabelCoder([Term(*t) for t in current_llts("29.1")], [])


def code(coder, *lines, section="warnings_and_precautions") -> Coded:
    rows = [SectionRow("set-x", section, n, False, text) for n, text in enumerate(lines)]
    coded = Coded()
    coder.code(rows, {"set-x": LabelInfo("900009", "inventamab", "2025-06-01")}, coded)
    return coded


def verdicts(coded: Coded) -> list[tuple[str, bool | None, str]]:
    return [(r["matched_text"], r["kept"], r["rule"]) for r in coded.terms]


def test_a_term_inside_an_exclusion_clause_is_kept_off_and_the_term_it_qualifies_stays(coder):
    coded = code(coder, "Headache (excluding nausea) | 16 | 12", section="adverse_reactions")
    assert verdicts(coded) == [
        ("Headache", True, "label-dictionary"),
        ("nausea", False, "label-negation"),
    ]
    coded = code(coder, "** Does not include headache, nausea and vomiting.")
    assert [k for _, k, _ in verdicts(coded)] == [False, False, False]
    assert "does not include" in rulebook.value("label-negation", "exclusion")


def test_an_exclusion_clause_ends_at_its_bracket_or_its_clause(coder):
    coded = code(coder, "Renal failure (excluding acute renal failure) and headache occurred.")
    assert verdicts(coded) == [
        ("Renal failure", True, "label-dictionary"),
        ("acute renal failure", False, "label-negation"),
        ("headache", True, "label-dictionary"),
    ]
    coded = code(coder, "The rate, excluding nausea and vomiting, was 6%; headache was 2%.")
    assert [(m, k) for m, k, _ in verdicts(coded)] == [
        ("nausea", False),
        ("vomiting", False),
        ("headache", True),
    ]
