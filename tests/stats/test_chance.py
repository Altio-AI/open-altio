"""The chance test (rule chance-test): worked examples with known answers, the limit between
the two tests, a table with an empty cell, and the same answer every time. The expected p-values
are from textbooks, or from scipy worked out once by hand; scipy is not used to make them here."""

import pytest

from open_altio import rulebook
from open_altio.stats.chance import CHI_SQUARE, FISHER, days, two_by_two
from open_altio.testing.rules import rules_with

TOL = 1e-9
LIMIT = rulebook.value("chance-test", "fisher_up_to")
ALPHA = rulebook.value("chance-test", "alpha")


@pytest.mark.parametrize(
    ("table", "p"),
    [
        # the lady tasting tea (Fisher, 1935)
        ((3, 1, 1, 3), 0.48571428571428565),
        ((10, 0, 0, 10), 1.082508822446903e-05),
        ((8, 2, 1, 5), 0.034965034965034975),
    ],
)
def test_fishers_exact_test_gives_the_known_two_sided_p(table, p):
    got = two_by_two(*table)
    assert got.test == FISHER
    assert got.p == pytest.approx(p, abs=TOL)


@pytest.mark.parametrize(
    ("table", "p"),
    [
        ((12, 88, 30, 70), 0.0017787338817784157),
        ((5, 95, 0, 100), 0.023540058261177988),
        ((20, 80, 20, 80), 1.0),
    ],
)
def test_the_chi_square_test_above_the_limit_gives_the_known_p(table, p, tmp_path):
    """The tables hold 200 reports, so a limit under that sends them to the chi-square test."""
    with rules_with(tmp_path, {"chance-test": {"fisher_up_to": 199}}):
        got = two_by_two(*table)
    assert got.test == CHI_SQUARE
    assert got.p == pytest.approx(p, abs=TOL)


def test_a_table_of_exactly_the_limit_takes_fishers_test_and_one_more_report_the_chi_square():
    at = two_by_two(LIMIT // 4, LIMIT // 4, LIMIT // 4 + 7, LIMIT - 3 * (LIMIT // 4) - 7)
    assert at.test == FISHER
    over = two_by_two(LIMIT // 4 + 1, LIMIT // 4, LIMIT // 4 + 7, LIMIT - 3 * (LIMIT // 4) - 7)
    assert over.test == CHI_SQUARE


def test_a_pass_is_a_p_under_alpha():
    clear = two_by_two(10, 0, 0, 10)
    assert clear.p < ALPHA
    assert clear.passes is True
    assert two_by_two(3, 1, 1, 3).passes is False
    assert two_by_two(3, 1, 1, 3, alpha=0.5).passes is True


def test_a_zero_cell_is_tested_and_an_empty_row_or_column_has_no_change(tmp_path):
    assert two_by_two(5, 0, 0, 5).p == pytest.approx(0.007936507936507936, abs=TOL)
    assert two_by_two(0, 7, 0, 9).p == 1.0
    assert two_by_two(4, 0, 6, 0).p == 1.0
    with rules_with(tmp_path, {"chance-test": {"fisher_up_to": 1}}):
        assert two_by_two(0, 7, 0, 9).p == 1.0
        assert two_by_two(5, 0, 7, 0).passes is False


@pytest.mark.parametrize("bad", [-1, 2.5, True])
def test_a_count_that_is_not_a_whole_number_of_zero_or_more_is_refused(bad):
    with pytest.raises(ValueError, match="whole number"):
        two_by_two(bad, 1, 1, 1)


def test_other_sides_are_refused(tmp_path):
    with (
        rules_with(tmp_path, {"chance-test": {"sides": "one"}}),
        pytest.raises(ValueError, match="sides"),
    ):
        two_by_two(1, 2, 3, 4)


def test_the_mann_whitney_test_gives_the_known_p():
    before = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    window = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    assert days(before, window).p == pytest.approx(0.005075392315273923, abs=TOL)
    assert days(before, window).passes is True
    tied = days([1, 2, 2, 3, 5, 8, 13, 21], [2, 4, 4, 6, 9, 15, 30, 40, 60])
    assert tied.p == pytest.approx(0.13463311829717942, abs=TOL)
    assert tied.passes is False
    # a small sample without ties is worked out exactly
    assert days([19, 22, 16, 29, 24], [20, 11, 17, 12]).p == pytest.approx(1 / 9, abs=TOL)


def test_an_empty_set_of_days_cannot_be_compared():
    assert days([], [1, 2]).p is None
    assert days([3], []).passes is None


def test_the_same_inputs_give_the_same_answer():
    assert two_by_two(12, 88, 30, 70) == two_by_two(12, 88, 30, 70)
    assert days([1, 5, 9], [2, 6, 10, 14]) == days([1, 5, 9], [2, 6, 10, 14])
