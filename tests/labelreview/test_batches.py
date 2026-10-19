"""Batches: picked as a mix, sized by rule label-review, and refused while a gate fails."""

from __future__ import annotations

import hashlib
from collections import Counter

import pytest
from reviewhelpers import REVIEWER, accept_all, suggest_all

from open_altio import rulebook
from open_altio.labelreview import batches, decisions
from open_altio.labelreview.items import read_items
from open_altio.labelreview.store import BATCHES, Folder
from open_altio.testing.fakereview import item_rows, write_items
from open_altio.testing.rules import rules_with


def test_the_first_batch_takes_the_first_size_in_the_rule(folder, clock):
    batch = batches.start_next(folder, clock.now)
    assert batch.number == 1
    assert len(batch.item_ids) == rulebook.value("label-review", "first_batch_size")


def test_each_batch_after_the_first_grows_by_the_rules_step(tmp_path):
    first = rulebook.value("label-review", "first_batch_size")
    step = rulebook.value("label-review", "batch_size_step")
    assert [batches.size_for(n) for n in (1, 2, 3)] == [
        first,
        first + step,
        first + 2 * step,
    ]
    with rules_with(tmp_path, {"label-review": {"first_batch_size": 7, "batch_size_step": 3}}):
        assert [batches.size_for(n) for n in (1, 2, 3)] == [7, 10, 13]


def _pool(path, rows):
    write_items(path, rows)
    return list(read_items(Folder(path)).values())


def _row(drug: int, k: int, section: str, why: str, date: str, rank: float | None) -> dict:
    return {
        "item_id": hashlib.sha256(f"{drug}-{k}".encode()).hexdigest()[:16],
        "set_id": f"set-{drug}",
        "rxcui": f"rx{drug}",
        "section": section,
        "sentence": f"Patients on drug {drug} reported glimmer {k}.",
        "candidate_pt": "",
        "why_uncertain": why,
        "label_date": date,
        "rank": rank,
    }


def test_a_batch_holds_each_kind_of_phrase_in_about_its_share_of_the_pool(tmp_path):
    # Many short old labels with one negation each, a few long new labels full of table rows,
    # and one rare kind: taking turns by drug would fill the batch with the negations.
    rows = [_row(d, 0, "precautions", "negation", "2008-01-01", None) for d in range(60)]
    for d in range(60, 64):
        for k in range(60):
            why = "table row" if k % 2 else "no term"
            rows.append(_row(d, k, "adverse_reactions", why, "2025-01-01", float(k % 9)))
    rows.append(_row(60, 99, "boxed_warning", "everyday word", "2025-01-01", None))
    pool = _pool(tmp_path / "licensed", rows)
    size = 30
    picked = batches.pick_mix(pool, size)
    assert len(picked) == size == len({i.item_id for i in picked})
    traits = batches._traits(pool)
    in_pool = Counter(t for i in pool for t in traits[i.item_id])
    in_batch = Counter(t for i in picked for t in traits[i.item_id])
    for trait, n in in_pool.items():
        assert in_batch[trait] >= 1, trait
        assert abs(in_batch[trait] - size * n / len(pool)) <= 1.5, trait
    assert in_batch[("why", "negation")] < size / 3  # turns by drug gave nearly all of them


def test_a_drug_with_many_phrases_does_not_fill_the_batch(tmp_path):
    pool = _pool(tmp_path / "licensed", item_rows(drugs=8, per_drug=6, skewed=60))
    size = 24
    picked = batches.pick_mix(pool, size)
    assert {i.rxcui for i in picked} == {i.rxcui for i in pool}
    big = sum(i.rxcui == "rx0" for i in pool) / len(pool)
    assert sum(i.rxcui == "rx0" for i in picked) < size * big


def test_phrases_from_sections_left_to_other_rules_never_reach_review(tmp_path, clock):
    left_out = rulebook.value("label-review", "not_reviewed_sections")
    rows = item_rows(drugs=2, per_drug=3)
    rows += [
        _row(9, k, section, "everyday word", "2020-01-01", None)
        for k, section in enumerate(left_out)
    ]
    path = tmp_path / "licensed"
    write_items(path, rows)
    with rules_with(tmp_path, {"label-review": {"first_batch_size": len(rows)}}):
        batch = batches.start_next(Folder(path), clock.now)
    assert len(batch.item_ids) == len(rows) - len(left_out)
    sections = {i.item_id: i.section for i in read_items(Folder(path)).values()}
    assert not {sections[i] for i in batch.item_ids} & set(left_out)


def test_the_same_pool_always_gives_the_same_batch(folder):
    pool = list(read_items(folder).values())
    assert batches.pick_mix(pool, 30) == batches.pick_mix(list(reversed(pool)), 30)


def test_a_bigger_batch_is_refused_while_a_gate_fails_and_nothing_is_recorded(folder, clock):
    batches.start_next(folder, clock.now)
    suggest_all(folder, clock)
    first, *rest = batches.current(folder).item_ids
    for item_id in rest:
        decisions.decide(folder, item_id, decisions.ACCEPT, [], "", "", REVIEWER, clock.now)
    # The reviewer disagrees with the agent on one item.
    decisions.decide(folder, first, decisions.REJECT, [], "population", "", REVIEWER, clock.now)
    with pytest.raises(batches.GateClosed) as refused:
        batches.start_next(folder, clock.now)
    assert any("agreed" in reason for reason in refused.value.reasons)
    assert len(folder.read(BATCHES)) == 1


def test_a_bigger_batch_is_refused_while_items_wait_for_a_decision(folder, clock):
    batches.start_next(folder, clock.now)
    suggest_all(folder, clock)
    with pytest.raises(batches.GateClosed):
        batches.start_next(folder, clock.now)


def test_the_next_batch_starts_when_every_gate_passes_and_skips_reviewed_items(reviewed, clock):
    first = batches.current(reviewed)
    second = batches.start_next(reviewed, clock.now)
    assert second.number == 2
    assert not set(first.item_ids) & set(second.item_ids)
    left = len(read_items(reviewed)) - len(first.item_ids)
    assert len(second.item_ids) == min(left, batches.size_for(2))


def test_when_every_item_is_batched_another_batch_is_refused(tmp_path, clock, review_release):
    path = tmp_path / "licensed"
    write_items(path, item_rows(drugs=2, per_drug=3))
    small = Folder(path)
    with rules_with(tmp_path, {"label-review": {"first_batch_size": 6}}):
        batches.start_next(small, clock.now)
        suggest_all(small, clock, release=review_release)
        accept_all(small, clock)
        with pytest.raises(batches.Refused, match="already in a batch"):
            batches.start_next(small, clock.now)
