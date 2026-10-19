"""A trial's exclusions and a risk factor are populations (rule label-population).

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


def test_a_trials_exclusions_and_a_risk_factor_are_populations(coder):
    coded = code(coder, "The trial excluded patients with renal failure or prior haemorrhage.")
    assert {k for _, k, _ in verdicts(coded)} == {False}
    assert {r for _, _, r in verdicts(coded)} == {"label-population"}
    coded = code(coder, "Patients were excluded from the study if they had headache.")
    assert verdicts(coded)[0][1] is False
    line = "Patients with high tumour burden or renal failure are at greater risk for nausea."
    assert [(m, k) for m, k, _ in verdicts(code(coder, line))] == [
        ("renal failure", False),
        ("nausea", True),
    ]
    assert "are at greater risk" in rulebook.value("label-population", "risk_ends")


def test_a_trial_exclusion_reaches_only_its_own_clause(coder):
    coded = code(coder, "Headache occurred in 5%; the trial excluded patients with renal failure.")
    assert [(m, k) for m, k, _ in verdicts(coded)] == [("Headache", True), ("renal failure", False)]
