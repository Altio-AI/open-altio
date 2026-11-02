"""Whether a statistic is rising, read from its values at the end of each quarter (rule
trend-rising): its value at the newest quarter end against its value a number of quarter ends
before.

    risen({"eb05": [1.2, 1.4, 1.9, 2.3, 2.8]}, "eb05", 4)    # True: 2.8 is higher than 1.2

A series is a statistic's values by column, one per quarter end, oldest first, with no quarter
end left out, so `back` quarter ends before the newest is the value `back` places earlier. A
value the series does not hold, or holds empty, cannot be compared: the answer is then None,
never False.

Rising is not a signal and not evidence of cause; people judge what a pair means.
"""

from __future__ import annotations

import math
import operator
from collections.abc import Mapping, Sequence

from open_altio import rulebook

RULE = "trend-rising"
# How the newest value is compared with the earlier one, by the rule's `compare`.
COMPARES = {"higher": operator.gt}


def risen(
    series: Mapping[str, Sequence[float | None]],
    column: str,
    back: int,
    *,
    compare: str | None = None,
) -> bool | None:
    """Whether `column`'s value at the newest quarter end of `series` is higher than its value
    `back` quarter ends before, compared as the rule's `compare` says; a caller judging many
    series may read `compare` from the rule once and pass it. None where either value is empty
    or the series is not that long. Refused (ValueError) for a column the series does not have
    and for `back` under one quarter."""
    if column not in series:
        raise ValueError(f"The series has no {column}: it has {', '.join(sorted(series))}.")
    if back < 1:
        raise ValueError(f"A trend reads back one quarter end or more, not {back}.")
    if compare is None:
        compare = str(rulebook.value(RULE, "compare"))
    if compare not in COMPARES:
        raise rulebook.RuleError(
            f"rule {RULE} compares by one of {', '.join(sorted(COMPARES))}, not {compare}"
        )
    values = series[column]
    if len(values) <= back:
        return None
    newest, before = values[-1], values[-1 - back]
    if newest is None or before is None or math.isnan(newest) or math.isnan(before):
        return None
    return bool(COMPARES[compare](newest, before))


__all__ = ["COMPARES", "RULE", "risen"]
