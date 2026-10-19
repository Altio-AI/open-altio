"""Helpers the label review tests share, beside the fixtures in this folder's conftest.py."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from open_altio.labelreview import batches, decisions, suggest
from open_altio.labelreview.store import Folder
from open_altio.testing.fakereview import answer_items

REVIEWER = "the reviewer"


class StillClock:
    """Time that stands still, so every who-and-when stamp in a test is known."""

    def __init__(self) -> None:
        self.at = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.at


def accept_all(folder: Folder, clock: StillClock, note: str = "") -> None:
    batch = batches.current(folder)
    assert batch is not None
    for item_id in batch.item_ids:
        decisions.decide(folder, item_id, decisions.ACCEPT, [], "", note, REVIEWER, clock.now)


def suggest_all(
    folder: Folder,
    clock: StillClock,
    by: str = "fake agent",
    release: Path | None = None,
    **answers,
) -> None:
    """Export the batch, let the fake agent code it, import: what a person and their agent do."""
    out = suggest.export_batch(folder, clock.now, release=release)
    answer_items(out, **answers)
    suggest.import_suggestions(folder, by, out, clock.now, release)
