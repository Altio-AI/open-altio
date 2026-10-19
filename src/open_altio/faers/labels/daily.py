"""DailyMed's daily update files, fetched: the labels changed on one day (rules label-source and
label-refresh). Reading one is folder.read_day.

    days = due(as_of, applied, today)              the days whose files are still to be read
    found = fetch_days(client, days, into, say)    each of those days' files DailyMed has
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, timedelta
from pathlib import Path

import httpx

from open_altio import rulebook

from . import fetch

RULE = "label-source"


def file_name(day: date) -> str:
    """The name DailyMed gives the file of `day`'s changes."""
    return str(rulebook.value(RULE, "daily_file_pattern")).format(day=day)


def due(as_of: date, applied: Iterable[str], today: date) -> list[date]:
    """The days from `as_of` up to yesterday whose files are not applied yet. The day the labels
    are as of is asked for until its own file is applied, since a full release can be cut before
    all of that day's changes reach it; a day's file comes out after the day ends."""
    done = set(applied)
    days = (as_of + timedelta(days=n) for n in range((today - as_of).days))
    return [d for d in days if file_name(d) not in done]


def fetch_days(
    client: httpx.Client, days: Iterable[date], into: Path, say: Callable[[str], None]
) -> list[tuple[date, Path]]:
    """Each day's file DailyMed has, downloaded into `into` once, one request at a time. A day
    with no file (a weekend, a holiday, or a file not out yet) is passed over."""
    base = rulebook.value(RULE, "release_files_url")
    found = []
    for day in days:
        name = file_name(day)
        size = fetch.size_of(client, base + name)
        fetch.pause()
        if size is None:
            say(f"labels: DailyMed has no {name}")
            continue
        if fetch.download(client, base + name, into / name, size):
            fetch.pause()
        say(f"labels: {name}, {size} bytes")
        found.append((day, into / name))
    return found
