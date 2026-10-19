"""Fixtures for the label review: a licensed folder holding invented uncertain phrases, inside a
copy of the fake release whose licensed part holds the invented MedDRA.

    review_release  a copy of the fake release with its MedDRA part, once per session
    folder          a licensed folder in it with the invented items (open_altio.testing.fakereview)
    clock           a clock that stands still, for who-and-when stamps
    reviewed        a folder whose first batch is coded and decided, every item agreeing
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from reviewhelpers import StillClock, accept_all, suggest_all

from open_altio.labelreview import batches
from open_altio.labelreview.store import Folder
from open_altio.testing.fakereview import item_rows, write_items


@pytest.fixture(scope="session")
def review_release(licensed_release, tmp_path_factory) -> Path:
    copy = tmp_path_factory.mktemp("review") / licensed_release.name
    shutil.copytree(licensed_release, copy)
    return copy


@pytest.fixture
def clock() -> StillClock:
    return StillClock()


@pytest.fixture
def folder(review_release, tmp_path) -> Folder:
    path = review_release / "licensed" / f"review-{tmp_path.name}"
    write_items(path, item_rows())
    return Folder(path)


@pytest.fixture
def reviewed(folder, clock) -> Folder:
    batches.start_next(folder, clock.now)
    suggest_all(folder, clock)
    accept_all(folder, clock)
    return folder
