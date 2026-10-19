"""Which MedDRA version a release is built with (rule meddra-version): the newest held when it
is built, and only that one."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

from open_altio import rulebook

from .files import MeddraRefused

# MedDRA's numbering: version x.0 comes out in March and x.1 in September of
# the year x + this offset (26.0 in March 2023, 29.1 in September 2026).
# `--released` overrides it for a release that does not follow the pattern.
_VERSION_YEAR_OFFSET = 1997


def release_date(version: str) -> date:
    """The date MedDRA published `version` (x.0 on the rule's first release
    date, x.1 on its second), from MedDRA's numbering."""
    found = re.fullmatch(r"(\d+)\.(\d+)", version.strip())
    dates = rulebook.value("meddra-version", "release_dates")
    if not found or int(found.group(2)) >= len(dates):
        raise MeddraRefused(
            f"cannot tell when MedDRA {version} was released; pass --released yyyy-mm-dd"
        )
    month, day = (int(x) for x in dates[int(found.group(2))].split("-"))
    return date(int(found.group(1)) + _VERSION_YEAR_OFFSET, month, day)


def _number(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version))


def newest(versions: Iterable[str]) -> str | None:
    """The newest of MedDRA `versions` by their numbers (29.1 after 29.0 after 28.1), or None
    for none: the one a release is built with (rule meddra-version)."""
    return max(versions, key=_number, default=None)
