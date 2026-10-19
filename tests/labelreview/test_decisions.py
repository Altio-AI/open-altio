"""The reviewer's decisions: accept the agent's coding, or give the right one, with who and when."""

from __future__ import annotations

import pytest
from reviewhelpers import REVIEWER, suggest_all

from open_altio.labelreview import batches, decisions, suggest
from open_altio.labelreview.items import read_items
from open_altio.labelreview.store import Refused


@pytest.fixture
def suggested(folder, clock):
    batches.start_next(folder, clock.now)
    suggest_all(folder, clock)
    return folder, batches.current(folder).item_ids[0]


def _decide(folder, clock, item_id, verdict, pts=(), reason="", note=""):
    return decisions.decide(folder, item_id, verdict, list(pts), reason, note, REVIEWER, clock.now)


def test_accept_takes_the_agents_coding_and_records_who_and_when(suggested, clock):
    folder, item_id = suggested
    d = _decide(folder, clock, item_id, decisions.ACCEPT)
    said = suggest.latest(folder)[item_id]
    assert d.pts == said["pts"] and d.none_reason == said["none_reason"]
    assert d.suggested_by == said["by"]
    assert d.reviewer == REVIEWER and d.decided_at == clock.now().isoformat(timespec="seconds")
    assert decisions.latest(folder)[item_id] == d


def test_the_reviewers_terms_are_checked_against_meddra_and_spelt_as_meddra_spells_them(
    suggested, clock
):
    folder, item_id = suggested
    with pytest.raises(Refused, match="Not a current MedDRA preferred term: Glimmer"):
        _decide(folder, clock, item_id, decisions.REJECT, ["Vomiting", "Glimmer"])
    with pytest.raises(Refused, match="Head pain"):  # a lower level term, not a preferred term
        _decide(folder, clock, item_id, decisions.REJECT, ["Head pain"])
    d = _decide(folder, clock, item_id, decisions.REJECT, ["vomiting ", "HEADACHE", "Vomiting"])
    assert d.pts == ["Vomiting", "Headache"]


def test_reject_needs_terms_or_one_reason_and_not_the_agents_own_coding(suggested, clock):
    folder, item_id = suggested
    with pytest.raises(Refused, match="or a reason for none"):
        _decide(folder, clock, item_id, decisions.REJECT)
    with pytest.raises(Refused, match="not both"):
        _decide(folder, clock, item_id, decisions.REJECT, ["Vomiting"], "population")
    with pytest.raises(Refused, match="Accept instead"):
        _decide(folder, clock, item_id, decisions.REJECT, ["Nausea"])
    d = _decide(folder, clock, item_id, decisions.REJECT, [], "did_not_happen")
    assert d.pts == [] and d.none_reason == "did_not_happen" and d.suggested_pts == ["Nausea"]


def test_the_reason_other_needs_a_note(suggested, clock):
    folder, item_id = suggested
    with pytest.raises(Refused, match="note"):
        _decide(folder, clock, item_id, decisions.REJECT, [], "other")
    assert (
        _decide(folder, clock, item_id, decisions.REJECT, [], "other", "Cut off.").note
        == "Cut off."
    )


def test_an_item_outside_a_batch_or_without_a_suggestion_cannot_be_decided(folder, clock):
    batches.start_next(folder, clock.now)
    outside = next(i for i in read_items(folder) if i not in batches.batch_of(folder))
    with pytest.raises(Refused, match="not in a review batch"):
        _decide(folder, clock, outside, decisions.ACCEPT)
    with pytest.raises(Refused, match="not suggested"):
        _decide(folder, clock, batches.current(folder).item_ids[0], decisions.ACCEPT)


def test_a_later_decision_takes_effect_and_the_earlier_one_stays_on_file(suggested, clock):
    folder, item_id = suggested
    _decide(folder, clock, item_id, decisions.ACCEPT)
    _decide(folder, clock, item_id, decisions.REJECT, ["Headache"])
    assert decisions.latest(folder)[item_id].pts == ["Headache"]
    assert len(folder.read("label_decisions.jsonl")) == 2
