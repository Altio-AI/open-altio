"""The rule check: a seeded sample of rule-made flags and their error rates."""

from __future__ import annotations

import pyarrow.parquet as pq
import pytest

from open_altio import rulebook
from open_altio.labelreview import decisions, rulecheck
from open_altio.labelreview.store import DECISIONS, Folder, Refused
from open_altio.testing.fakereview import FLAG_OUTCOMES, write_flags

SIZE = rulebook.value("label-rule-check", "sample_size")


@pytest.fixture
def flags(tmp_path):
    return write_flags(tmp_path / "public" / "label_flags_T.parquet")


def test_the_sample_is_shared_across_outcomes_and_takes_only_rule_decided_flags(
    folder, flags, clock
):
    drawn = rulecheck.draw(folder, flags, clock.now)
    assert len(drawn) == SIZE
    by_outcome = {o: sum(f["outcome"] == o for f in drawn) for o in FLAG_OUTCOMES}
    assert max(by_outcome.values()) - min(by_outcome.values()) <= 1
    assert all(f["decided_by"] == rulebook.value("label-rule-check", "decided_by") for f in drawn)


def test_the_same_seed_draws_the_same_sample_whatever_the_row_order(tmp_path, flags, clock):
    table = pq.read_table(flags)
    reversed_path = tmp_path / "public" / "reversed.parquet"
    pq.write_table(table.take(list(reversed(range(table.num_rows)))), reversed_path)
    one = rulecheck.draw(Folder(tmp_path / "a" / "licensed"), flags, clock.now)
    two = rulecheck.draw(Folder(tmp_path / "b" / "licensed"), reversed_path, clock.now)
    assert one == two


def test_the_sample_is_drawn_once(folder, flags, clock):
    rulecheck.draw(folder, flags, clock.now)
    with pytest.raises(Refused, match="once"):
        rulecheck.draw(folder, flags, clock.now)


def test_an_outcome_with_few_flags_gives_its_share_to_the_others():
    assert rulecheck.share_out(10, {"a": 2, "b": 50, "c": 50}) == {
        "a": 2,
        "b": 4,
        "c": 4,
    }
    assert rulecheck.share_out(10, {"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_a_check_marks_right_or_wrong_with_the_right_outcome_in_the_decisions_file(
    folder, flags, clock
):
    drawn = rulecheck.draw(folder, flags, clock.now)
    first, second = rulecheck.flag_key(drawn[0]), rulecheck.flag_key(drawn[1])
    rulecheck.check(folder, first, rulecheck.RIGHT, None, "", "the reviewer", clock.now)
    with pytest.raises(Refused, match="Choose"):
        rulecheck.check(folder, second, rulecheck.WRONG, None, "", "the reviewer", clock.now)
    with pytest.raises(Refused, match="Mark it right"):
        rulecheck.check(
            folder,
            second,
            rulecheck.WRONG,
            drawn[1]["outcome"],
            "",
            "the reviewer",
            clock.now,
        )
    other = next(o for o in rulecheck.outcomes() if o != drawn[1]["outcome"])
    rulecheck.check(folder, second, rulecheck.WRONG, other, "", "the reviewer", clock.now)
    rows = folder.read(DECISIONS)
    assert [r["kind"] for r in rows] == [rulecheck.KIND, rulecheck.KIND]
    assert rows[1]["right_outcome"] == other and rows[1]["reviewer"] == "the reviewer"
    assert decisions.latest(folder) == {}  # the phrase review reads none of them


def test_error_rates_per_outcome_with_a_wilson_range(folder, flags, clock):
    drawn = rulecheck.draw(folder, flags, clock.now)
    on_label = [f for f in drawn if f["outcome"] == "on_label"]
    for f in on_label[1:]:
        rulecheck.check(folder, rulecheck.flag_key(f), rulecheck.RIGHT, None, "", "r", clock.now)
    rulecheck.check(
        folder,
        rulecheck.flag_key(on_label[0]),
        rulecheck.WRONG,
        "related",
        "",
        "r",
        clock.now,
    )
    rates = {r.outcome: r for r in rulecheck.error_rates(folder)}
    on = rates["on_label"]
    assert (on.checked, on.wrong) == (len(on_label), 1)
    assert on.low < on.rate < on.high
    assert rates["related"].checked == 0 and (
        rates["related"].low,
        rates["related"].high,
    ) == (0.0, 1.0)


def test_the_wilson_range_is_honest_at_zero_wrong():
    low, high = rulecheck.wilson(0, 20, 0.95)
    assert low == 0.0 and 0.15 < high < 0.17
    low, high = rulecheck.wilson(10, 20, 0.95)
    assert low == pytest.approx(1 - high)
