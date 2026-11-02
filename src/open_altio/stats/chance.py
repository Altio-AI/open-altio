"""Whether a change between two periods is more than chance (rule chance-test).

    two_by_two(12, 88, 30, 70).passes     # 12 of 100 reports against 30 of 100

`two_by_two(a, b, c, d)` takes the earlier period's reports with a value and without it, then
the later period's: Fisher's exact test (Fisher, 1922) where the table holds at most the rule's
`fisher_up_to` reports, Pearson's chi-square test above that, which is the two-proportion z test.
`days(before, window)` compares two sets of days with the Mann-Whitney test (Mann and Whitney,
1947), as scipy works it out. Both are two-sided and pass when p is under the rule's `alpha`.
Nothing here reads a release.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple

from scipy import stats

from open_altio import rulebook

RULE = "chance-test"
FISHER = "fisher"
CHI_SQUARE = "chi_square"
MANN_WHITNEY = "mann_whitney"


class Chance(NamedTuple):
    """The p-value, the test that gave it and whether it is under alpha. `p` and `passes` are
    None where there was nothing to compare."""

    p: float | None
    test: str
    passes: bool | None


def two_by_two(a: int, b: int, c: int, d: int, *, alpha: float | None = None) -> Chance:
    """Test the table [[a, b], [c, d]] of counts of reports, for a change in either direction.
    Refused (ValueError) for a count that is negative or not whole."""
    for count in (a, b, c, d):
        if isinstance(count, bool) or int(count) != count or count < 0:
            raise ValueError(
                f"A count of reports must be a whole number of 0 or more, not {count!r}"
            )
    _two_sided()
    a, b, c, d = int(a), int(b), int(c), int(d)
    if a + b + c + d <= rulebook.value(RULE, "fisher_up_to"):
        test = FISHER
        p = 1.0 if _empty_line(a, b, c, d) else float(stats.fisher_exact([[a, b], [c, d]])[1])
    else:
        test = CHI_SQUARE
        p = _chi_square_p(a, b, c, d)
    return Chance(p, test, p < _alpha(alpha))


def days(before: Sequence[float], window: Sequence[float], *, alpha: float | None = None) -> Chance:
    """Test whether two sets of days, the earlier period's and the later's, differ in either
    direction. Empty where either set is empty."""
    _two_sided()
    if rulebook.value(RULE, "days") != MANN_WHITNEY:
        raise ValueError(f"The rule {RULE} names a test for days this code does not know")
    if len(before) == 0 or len(window) == 0:
        return Chance(None, MANN_WHITNEY, None)
    p = float(stats.mannwhitneyu(before, window, alternative="two-sided").pvalue)
    return Chance(p, MANN_WHITNEY, p < _alpha(alpha))


def _two_sided() -> None:
    if rulebook.value(RULE, "sides") != "two":
        raise ValueError(f"The rule {RULE} names sides this code does not know")


def _alpha(alpha: float | None) -> float:
    return float(rulebook.value(RULE, "alpha")) if alpha is None else alpha


def _empty_line(a: int, b: int, c: int, d: int) -> bool:
    return 0 in (a + b, c + d, a + c, b + d)


def _chi_square_p(a: int, b: int, c: int, d: int) -> float:
    """Pearson's chi-square on one degree of freedom, N (ad - bc)^2 / (row and column totals)."""
    if _empty_line(a, b, c, d):
        return 1.0
    n = a + b + c + d
    chi = n * (a * d - b * c) ** 2 / ((a + b) * (c + d) * (a + c) * (b + d))
    return math.erfc(math.sqrt(chi / 2))
