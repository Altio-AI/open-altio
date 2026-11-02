"""Rising (src/open_altio/stats/trend.py, rule trend-rising): the newest quarter end's value
against the value the rule's number of quarter ends before, compared as the rule says; an empty
value, or a series too short to reach back, answers None and never False; and what cannot be
read is refused."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.stats import trend
from open_altio.testing.rules import rules_with

BACK = rulebook.value("trend-rising", "quarters_back")


def series(*values):
    """A series of `values` for eb05, ending with the newest, the value BACK quarter ends
    before it placed first."""
    return {"eb05": [*values[:1], *[1.0] * (BACK - 1), *values[1:]]}


def test_a_value_higher_than_back_quarter_ends_before_is_rising():
    assert trend.risen(series(1.5, 2.0), "eb05", BACK) is True
    assert trend.risen(series(2.0, 1.5), "eb05", BACK) is False


def test_a_comparison_read_once_by_the_caller_answers_as_the_rule_does():
    compare = rulebook.value("trend-rising", "compare")
    for values in (series(1.5, 2.0), series(2.0, 1.5), series(None, 2.0)):
        assert trend.risen(values, "eb05", BACK, compare=compare) is trend.risen(
            values, "eb05", BACK
        )


def test_a_value_that_stayed_the_same_is_not_rising():
    assert trend.risen(series(2.0, 2.0), "eb05", BACK) is False


def test_only_the_two_ends_are_compared():
    """A series that fell between its two ends and came back higher is rising."""
    values = {"eb05": [1.0, 3.0, 0.5, 0.2, 1.1]}
    assert trend.risen(values, "eb05", len(values["eb05"]) - 1) is True
    assert trend.risen(values, "eb05", 1) is True and trend.risen(values, "eb05", 3) is False


@pytest.mark.parametrize(
    "values",
    [
        series(None, 2.0),
        series(1.5, None),
        series(float("nan"), 2.0),
        series(1.5, float("nan")),
        {"eb05": [2.0] * BACK},  # no value BACK quarter ends before the newest
        {"eb05": []},
    ],
)
def test_an_empty_value_at_either_end_is_none_never_false(values):
    assert trend.risen(values, "eb05", BACK) is None


def test_a_column_not_in_the_series_is_refused():
    with pytest.raises(ValueError, match="eb95"):
        trend.risen(series(1.5, 2.0), "eb95", BACK)
    with pytest.raises(ValueError, match="eb05"):
        trend.risen({"eb05": []}, "prr", BACK)


@pytest.mark.parametrize("back", [0, -1])
def test_back_under_one_quarter_end_is_refused(back):
    with pytest.raises(ValueError, match="one quarter end or more"):
        trend.risen(series(1.5, 2.0), "eb05", back)


def test_a_comparison_the_rule_does_not_know_is_refused(tmp_path):
    with (
        rules_with(tmp_path, {"trend-rising": {"compare": "steeper"}}),
        pytest.raises(rulebook.RuleError, match="steeper"),
    ):
        trend.risen(series(1.5, 2.0), "eb05", BACK)


def test_the_rule_waits_on_its_evidence_notebook():
    assert rulebook.is_placeholder("trend-rising")
    assert rulebook.value("trend-rising", "compare") in trend.COMPARES
