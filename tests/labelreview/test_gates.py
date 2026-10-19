"""The gate maths before a bigger batch (rule label-review-gates)."""

from __future__ import annotations

from reviewhelpers import REVIEWER, accept_all, suggest_all

from open_altio import rulebook
from open_altio.labelreview import batches, decisions
from open_altio.labelreview.items import read_items
from open_altio.labelreview.store import Folder
from open_altio.testing.fakereview import item_rows, write_items
from open_altio.testing.rules import rules_with

BELOW = rulebook.value("label-review-gates", "other_share_below")


def _batch_where_the_agent_says_other_for(folder, clock, others: int, release=None):
    """The agent codes none, reason other, for the first `others` items; the reviewer accepts."""
    batch = batches.start_next(folder, clock.now)
    items = read_items(folder)
    phrases = {items[i].sentence: "other" for i in batch.item_ids[:others]}
    suggest_all(folder, clock, answers=phrases, release=release)
    accept_all(folder, clock, note="Nothing fits.")
    return batches.check(folder, batch)


def _decide_all_but_first(folder, clock, batch):
    for item_id in batch.item_ids[1:]:
        decisions.decide(folder, item_id, decisions.ACCEPT, [], "", "", REVIEWER, clock.now)


def test_a_batch_with_no_other_and_full_agreement_passes(reviewed):
    result = batches.check(reviewed, batches.current(reviewed))
    assert result.passed and result.reasons == []
    assert result.agreement == 1.0 and result.other_share == 0.0


def test_one_other_in_a_first_batch_fails_because_the_share_must_be_under_the_rule(folder, clock):
    result = _batch_where_the_agent_says_other_for(folder, clock, 1)
    assert result.other == 1 and result.other_share >= BELOW
    assert not result.passed
    assert any('"other"' in r for r in result.reasons)


def test_one_other_passes_in_a_batch_big_enough_to_keep_the_share_under_the_rule(
    tmp_path, clock, review_release
):
    size = round(2 / BELOW)  # one "other" is then half the allowed share
    path = tmp_path / "licensed"
    write_items(path, item_rows(drugs=10, per_drug=size // 10))
    with rules_with(tmp_path, {"label-review": {"first_batch_size": size}}):
        result = _batch_where_the_agent_says_other_for(Folder(path), clock, 1, review_release)
    assert result.items == size and result.other == 1
    assert result.passed


def test_other_terms_than_the_agent_named_block_the_next_batch(folder, clock):
    batch = batches.start_next(folder, clock.now)
    suggest_all(folder, clock)
    decisions.decide(
        folder,
        batch.item_ids[0],
        decisions.REJECT,
        ["Vomiting"],
        "",
        "",
        REVIEWER,
        clock.now,
    )
    _decide_all_but_first(folder, clock, batch)
    result = batches.check(folder, batch)
    assert result.agreed == result.items - 1 and not result.passed
    assert any("agreed" in r for r in result.reasons)


def test_both_saying_none_for_different_reasons_agrees_and_is_listed_for_tidying(folder, clock):
    batch = batches.start_next(folder, clock.now)
    first = batch.item_ids[0]
    suggest_all(folder, clock, answers={read_items(folder)[first].sentence: "population"})
    decisions.decide(folder, first, decisions.REJECT, [], "did_not_happen", "", REVIEWER, clock.now)
    _decide_all_but_first(folder, clock, batch)
    result = batches.check(folder, batch)
    assert result.passed and result.agreed == result.items
    assert result.reason_only == [first]


def test_a_rerun_after_the_fix_is_measured_against_the_reviewers_decisions(folder, clock, tmp_path):
    batch = batches.start_next(folder, clock.now)
    first = batch.item_ids[0]
    suggest_all(folder, clock, answers={read_items(folder)[first].sentence: ["Vomiting"]})
    decisions.decide(folder, first, decisions.REJECT, ["Nausea"], "", "", REVIEWER, clock.now)
    _decide_all_but_first(folder, clock, batch)
    assert not batches.check(folder, batch).passed
    # The fix changes what the agent reads, so every suggestion is stale until the rerun.
    changed = {"label-coding": {"question": "Which preferred terms does this phrase state?"}}
    with rules_with(tmp_path, changed):
        stale = batches.check(folder, batch)
        assert stale.stale == stale.items and not stale.passed
        suggest_all(folder, clock)
        assert batches.check(folder, batch).passed


def test_undecided_items_block_the_next_batch(folder, clock):
    batch = batches.start_next(folder, clock.now)
    suggest_all(folder, clock)
    decisions.decide(folder, batch.item_ids[0], decisions.ACCEPT, [], "", "", REVIEWER, clock.now)
    result = batches.check(folder, batch)
    assert result.decided == 1
    assert any("not decided" in r for r in result.reasons)
