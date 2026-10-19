"""A line the rules could not read that states nothing (rules label-negation, label-population
and label-dictionary)."""

from __future__ import annotations

from open_altio.faers.labeldict.unstated import Unstated

unstated = Unstated()


def test_an_unread_negation_before_the_term_states_nothing_unless_it_was_seen():
    said = unstated.verdict("The dose is not confused with the other strength.", "confused")
    assert said is not None and said.kept is False and said.rule == "label-negation"
    assert unstated.verdict("Deaths were not clearly linked, death occurred.", "death") is None
    assert unstated.verdict("Fever with or without chills.", "chills") is None
    assert unstated.verdict("Confusion, not the drug, was blamed.", "Confusion") is None  # after


def test_a_patients_condition_before_the_term_states_nothing():
    said = unstated.verdict(
        "Use with care in elderly patients with thrombophlebitis.", "thrombophlebitis"
    )
    assert said is not None and said.rule == "label-population"
    assert (
        unstated.verdict(
            "Thrombophlebitis was reported in patients with cancer.", "Thrombophlebitis"
        )
        is None
    )


def test_a_body_system_word_alone_is_a_heading():
    said = unstated.verdict("Nervous: agitation, confusion", "Nervous")
    assert said is not None and said.rule == "label-dictionary"
    assert unstated.verdict("Nervous breakdown was seen", "Nervous breakdown") is None
