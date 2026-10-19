"""The blind redo: once, spread across earlier batches, compared with the first codings."""

from __future__ import annotations

import pytest
from reviewhelpers import REVIEWER

from open_altio import rulebook
from open_altio.labelreview import decisions, redo
from open_altio.labelreview.page import state
from open_altio.labelreview.store import Refused

WANTED = rulebook.value("label-review", "blind_redo_items")


def test_the_redo_takes_the_rules_number_of_decided_items_and_happens_once(reviewed, clock):
    picked = redo.start(reviewed, clock.now)
    assert len(picked) == WANTED == len(set(picked))
    assert set(picked) <= set(decisions.latest(reviewed))
    with pytest.raises(Refused, match="once"):
        redo.start(reviewed, clock.now)


def test_the_redo_needs_enough_decided_items(folder, clock):
    with pytest.raises(Refused, match="needs"):
        redo.start(folder, clock.now)


def test_the_report_lists_other_terms_apart_from_a_different_reason_for_none(reviewed, clock):
    picked = redo.start(reviewed, clock.now)
    same, changed, reason = picked[0], picked[1], picked[2]
    # The first decisions all coded Nausea; make one of them none, to redo with another reason.
    decisions.decide(reviewed, reason, decisions.REJECT, [], "population", "", REVIEWER, clock.now)
    redo.answer(reviewed, same, ["Nausea"], "", "", REVIEWER, clock.now)
    redo.answer(reviewed, changed, ["Vomiting"], "", "", REVIEWER, clock.now)
    redo.answer(reviewed, reason, [], "did_not_happen", "", REVIEWER, clock.now)
    report = redo.compare(reviewed)
    assert report.items == WANTED and report.answered == 3
    assert [d.item_id for d in report.differences] == [changed]
    assert report.differences[0].first == ["Nausea"] and report.differences[0].redo == ["Vomiting"]
    assert [d.item_id for d in report.reason_only] == [reason]


def test_the_redo_page_shows_neither_the_first_answer_nor_the_agents_coding(reviewed, clock):
    redo.start(reviewed, clock.now)
    shown = state(reviewed, REVIEWER, True)
    assert shown["mode"] == "redo" and len(shown["items"]) == WANTED
    for item in shown["items"]:
        assert "decision" not in item and "suggestion" not in item
        assert item["answer"] is None


def test_an_item_outside_the_redo_cannot_be_answered(reviewed, clock):
    picked = set(redo.start(reviewed, clock.now))
    outside = next(i for i in decisions.latest(reviewed) if i not in picked)
    with pytest.raises(Refused, match="not in the blind redo"):
        redo.answer(reviewed, outside, ["Nausea"], "", "", REVIEWER, clock.now)
