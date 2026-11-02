"""The window an event's breakdowns look at and the time before it, both on the day a case is
dated by (rule received-day). The window is the question's own `received_from` and `received_to`,
by default the release's newest quarters (rule breakdown-lines, `default_window_quarters`) to its
end; before is `before_from` to `before_to`, by default every day before the window. Before must
end before the window starts, so no case is in both. A question that names its window by the
day the event began (`event_from`, `event_to`) and no received day places each case by its full
event date (`event_dt_T`, as the event date filter reads it) instead; a case with none is in
neither period.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from open_altio.faers.dates import received_day
from open_altio.rulebook import value

from ..answers import Problem
from ..explore import Data, Query, value_of

RULE = "breakdown-lines"
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
WINDOW, BEFORE = "window", "before"


EVENT_DAYS = ("event_from", "event_to")


@dataclass(frozen=True)
class Periods:
    window_from: date
    window_to: date
    before_from: date | None  # None: every day before the window
    before_to: date
    by_event: bool = False  # placed by the day the event began, not the day the case is dated by

    @property
    def dates(self) -> dict[str, None]:
        """The filters' dates the periods take the place of, for Scope.where."""
        names = EVENT_DAYS if self.by_event else ("received_from", "received_to")
        return dict.fromkeys(names)

    def of(self, case: str) -> tuple[str, list[Any]]:
        """SQL: WINDOW or BEFORE for a case of the case table `case` (its alias), or NULL for a
        case in neither, and its parameters."""
        day = f"{case}.{'event_dt_T' if self.by_event else received_day()}"
        since = f"{day} >= ? AND " if self.before_from else ""
        return (
            f"CASE WHEN {day} BETWEEN ? AND ? THEN '{WINDOW}' "
            f"WHEN {since}{day} <= ? THEN '{BEFORE}' END",
            [
                self.window_from,
                self.window_to,
                *([self.before_from] if self.before_from else []),
                self.before_to,
            ],
        )

    def described(self) -> dict[str, dict[str, date | None]]:
        return {
            WINDOW: {"from": self.window_from, "to": self.window_to},
            BEFORE: {"from": self.before_from, "to": self.before_to},
        }


def _day(query: Query, name: str) -> date | None:
    text = value_of(query, name).strip()
    if not text:
        return None
    try:
        if not DAY.fullmatch(text):
            raise ValueError(text)
        return date.fromisoformat(text)
    except ValueError:
        raise Problem(400, f"Write {name} as yyyy-mm-dd, such as 2026-03-12.") from None


def _quarter_start(day: date, back: int = 0) -> date:
    """The first day of `day`'s quarter, or of the quarter `back` quarters before it."""
    n = day.year * 4 + (day.month - 1) // 3 - back
    return date(n // 4, n % 4 * 3 + 1, 1)


def release_end(data: Data) -> date:
    """The last day of the release's newest quarter."""
    newest = data.opened.manifest["quarters"][-1]  # as FDA's files name it, 2026q2
    first = date(int(newest[:4]), (int(newest[-1]) - 1) * 3 + 1, 1)
    return _quarter_start(first, -1) - timedelta(days=1)


def asked(data: Data, query: Query) -> Periods:
    """The question's window and before; refused when a day is not one, or a period ends before
    it starts, or before does not end before the window starts."""
    received = [_day(query, n) for n in ("received_from", "received_to")]
    events = [_day(query, n) for n in EVENT_DAYS]
    by_event = any(events) and not any(received)
    asked_from, asked_to = events if by_event else received
    window_to = asked_to or release_end(data)
    back = int(value(RULE, "default_window_quarters")) - 1
    window_from = asked_from or _quarter_start(window_to, back)
    if window_to < window_from:
        raise Problem(400, "The window ends before it starts.")
    before_from = _day(query, "before_from")
    before_to = _day(query, "before_to") or window_from - timedelta(days=1)
    if before_to >= window_from:
        raise Problem(400, "Before must end before the window starts, so no case is in both.")
    if before_from and before_to < before_from:
        raise Problem(400, "Before ends before it starts.")
    return Periods(window_from, window_to, before_from, before_to, by_event)


__all__ = ["BEFORE", "WINDOW", "Periods", "asked", "release_end"]
