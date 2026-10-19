"""The disease a drug treats never comes from a risk it lowers, and never a death (rule
label-treated-disease).

Each test codes a few invented label lines with the invented MedDRA terms of
open_altio.testing.fakemeddra and reads back each term's verdict."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.faers.labeldict.coding import Coded, LabelCoder, LabelInfo, SectionRow
from open_altio.faers.labeldict.terms import Term
from open_altio.testing.fakemeddra import current_llts
from open_altio.testing.rules import rules_with


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


def test_an_outcome_the_drug_lowers_the_risk_of_is_not_the_disease_treated(coder):
    indications = rulebook.value("label-treated-disease", "indications_section")
    line = "Because of the risks of headache, nausea, and vomiting, reserve it for renal failure."
    assert verdicts(code(coder, line, section=indications)) == [
        ("headache", False, "label-treated-disease"),
        ("nausea", False, "label-treated-disease"),
        ("vomiting", False, "label-treated-disease"),
        ("renal failure", False, "label-treated-disease"),  # the whole line names no disease
    ]
    assert "risks of" in rulebook.value("label-treated-disease", "risk_phrases")


def test_a_death_is_never_the_disease_treated():
    terms = [Term("1", "Death", "1", "Death"), Term("2", "Heart failure", "2", "Heart failure")]
    coder = LabelCoder(terms, [])
    indications = rulebook.value("label-treated-disease", "indications_section")
    line = "Indicated for heart failure; cardiovascular death and hospitalization."
    assert [(m, k) for m, k, _ in verdicts(code(coder, line, section=indications))] == [
        ("heart failure", True),
        ("death", False),
    ]
    assert rulebook.value("label-treated-disease", "never_treated_words") == ["death"]


def test_outside_the_indications_a_risk_of_a_reaction_is_on_the_label(coder):
    assert verdicts(code(coder, "There is a risk of headache.")) == [
        ("headache", True, "label-dictionary")
    ]


def test_a_harm_named_after_because_of_is_not_the_disease_treated(coder):
    indications = rulebook.value("label-treated-disease", "indications_section")
    line = "Because of the nausea it causes, reserve it for patients with renal failure."
    assert [(m, k) for m, k, _ in verdicts(code(coder, line, section=indications))] == [
        ("nausea", False),
        ("renal failure", True),
    ]
    assert "because of" in rulebook.value("label-treated-disease", "risk_phrases")


def test_a_line_that_names_no_disease_treated_sets_nothing_aside(coder):
    indications = rulebook.value("label-treated-disease", "indications_section")
    for line in (
        "Many antihypertensive drugs have additional approved indications and effects "
        "(e.g., on headache, renal failure, or nausea).",
        "Lowering blood pressure reduces the risk of fatal and nonfatal headache.",
        "Limitations of Use: it is not indicated in nausea.",
        "Safety and effectiveness in renal failure has not been established.",
        "It reduces the risk of headache in patients with renal failure.",
    ):
        assert {k for _, k, _ in verdicts(code(coder, line, section=indications))} == {False}
    # a plain line that only names a disease still counts
    assert verdicts(code(coder, "Renal failure", section=indications)) == [
        ("Renal failure", True, "label-treated-disease")
    ]
    assert "limitations of use" in rulebook.value("label-treated-disease", "not_indication_lines")


def test_a_denied_effect_a_cause_and_a_patients_trouble_are_not_the_disease_treated(coder):
    indications = rulebook.value("label-treated-disease", "indications_section")
    denied = "It has not been shown to improve quality of life, headache, or well-being."
    assert {k for _, k, _ in verdicts(code(coder, denied, section=indications))} == {False}
    cause = "Indicated in renal failure due to nausea in the absence of organic pathology."
    trouble = (
        "Indicated in renal failure, e.g., patients experiencing nausea and vomiting with the "
        "first few doses."
    )
    for line, aside in ((cause, "nausea"), (trouble, "nausea")):
        got = {m: k for m, k, _ in verdicts(code(coder, line, section=indications))}
        assert got["renal failure"] is True
        assert got[aside] is False
    phrases = rulebook.value("label-treated-disease", "risk_phrases")
    assert {"due to", "experiencing"} <= set(phrases)
    assert "has not been shown" in rulebook.value("label-treated-disease", "not_indication_lines")


def test_a_history_a_cannot_take_and_an_unproven_effect_set_nothing_aside(coder):
    indications = rulebook.value("label-treated-disease", "indications_section")
    for line in (
        "It has not been studied in patients with a history of headache.",
        "Black patients have a higher incidence of nausea than others.",
        "For advice on goals of headache management, see published guidelines.",
        "The effectiveness in preventing vomiting has not been demonstrated.",
        "To maintain the effectiveness of inventamab, use it only for nausea that is proven.",
    ):
        assert {k for _, k, _ in verdicts(code(coder, line, section=indications))} == {False}
    assert "exclude intracranial hemorrhage" in rulebook.value(
        "label-treated-disease", "not_indication_lines"
    )


def test_a_word_that_only_qualifies_the_disease_is_not_the_disease_treated(tmp_path):
    indications = rulebook.value("label-treated-disease", "indications_section")
    line = "Indicated for renal failure with objective signs of headache."
    changes = {"label-treated-disease": {"qualifier_phrases": ["signs of headache"]}}
    with rules_with(tmp_path, changes):
        fresh = LabelCoder([Term(*t) for t in current_llts("29.1")], [])
        got = {m: k for m, k, _ in verdicts(code(fresh, line, section=indications))}
    assert got == {"renal failure": True, "headache": False}
    assert "signs of inflammation" in rulebook.value("label-treated-disease", "qualifier_phrases")
