"""Thresholds: the screens a pair of the statistics may meet.

A screen is a list of conditions, all of which must hold for a pair to meet it:

    [{"column": "prr", "at_least": 2},
     {"column": "chi_square_yates", "at_least": 4},
     {"column": "cases", "at_least": 3}]

Each condition names a column of the statistics and exactly one comparison: `at_least` (>=),
`above` (>), `at_most` (<=) or `below` (<). An empty value meets no condition. The common
screens are presets kept on each statistic's rule (`presets` in its values); a person's own
screen has the same form, so a preset is only a starting point.

Meeting a screen is not a signal and not evidence of cause; people judge what a pair means.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from open_altio import rulebook

# Each statistic, by the name people know it by, and the rule that holds its presets.
RULES = {"EBGM": "ebgm", "PRR": "prr", "ROR": "ror", "RRR": "rrr", "IC": "ic"}
COMPARISONS = {"at_least": ">=", "above": ">", "at_most": "<=", "below": "<"}


class ScreenError(ValueError):
    """A screen that cannot be read, said in plain words."""


def presets(statistic: str) -> list[dict[str, Any]]:
    """The presets on the statistic's rule, each with id, label, source, when and (for one of
    them) default."""
    return [dict(p) for p in rulebook.value(RULES[statistic], "presets")]


def start(statistic: str) -> list[dict[str, Any]]:
    """Where a person's own screen for the statistic starts: its default preset, or, for a
    statistic with none, the rule's `own`."""
    found = next((p for p in presets(statistic) if p.get("default")), None)
    return list(found["when"]) if found else list(rulebook.value(RULES[statistic], "own"))


def check(
    when: Sequence[Mapping[str, Any]], columns: Collection[str]
) -> list[tuple[str, str, float]]:
    """The screen's conditions as (column, comparison, threshold); refused when one is not a
    column of `columns` with one comparison and a finite number."""
    out = []
    for cond in when:
        ops = [k for k in cond if k != "column"]
        if cond.get("column") not in columns or len(ops) != 1 or ops[0] not in COMPARISONS:
            raise ScreenError(
                f"A condition names one of {sorted(columns)} and one of {sorted(COMPARISONS)}: "
                f"{dict(cond)!r}"
            )
        threshold = cond[ops[0]]
        if isinstance(threshold, bool) or not isinstance(threshold, int | float):
            raise ScreenError(f"A condition's threshold is a number: {dict(cond)!r}")
        if threshold != threshold or abs(threshold) == float("inf"):
            raise ScreenError(f"A condition's threshold is a finite number: {dict(cond)!r}")
        out.append((str(cond["column"]), ops[0], float(threshold)))
    return out


def where(
    conditions: Sequence[tuple[str, str, float]], name: Callable[[str], str]
) -> tuple[str, list[float]]:
    """The checked conditions as SQL over columns named by `name`, and its parameters. An
    empty value meets no condition, as SQL's comparisons with NULL already hold."""
    if not conditions:
        return "TRUE", []
    clause = " AND ".join(f"{name(col)} {COMPARISONS[op]} ?" for col, op, _ in conditions)
    return clause, [threshold for _, _, threshold in conditions]
