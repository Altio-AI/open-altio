"""The blind redo: once, the reviewer decides earlier items again without seeing the first answers.

Where the two answers differ, a definition is not as clear as it reads, so it is tightened.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from open_altio import rulebook

from . import coding, decisions
from .store import REDO_ANSWERS, REDO_SET, Clock, Folder, Refused, stamp, utc_now

RULE = "label-review"


def start(folder: Folder, clock: Clock = utc_now) -> list[str]:
    """Pick the items to redo, spread across the earlier batches. Refused if a redo exists."""
    if folder.read_json(REDO_SET) is not None:
        raise Refused("The blind redo has already been set up; it happens once.")
    wanted = int(rulebook.value(RULE, "blind_redo_items"))
    by_batch: dict[int, list[str]] = defaultdict(list)
    for item_id, d in sorted(decisions.latest(folder).items()):
        by_batch[d.batch].append(item_id)
    if sum(map(len, by_batch.values())) < wanted:
        raise Refused(f"The blind redo needs {wanted} decided items to choose from.")
    picked: list[str] = []
    queues = [by_batch[b] for b in sorted(by_batch)]
    while len(picked) < wanted:
        for queue in queues:
            if queue and len(picked) < wanted:
                picked.append(queue.pop(0))
    folder.write_json(REDO_SET, {"item_ids": picked, "made_at": stamp(clock)})
    return picked


def item_ids(folder: Folder) -> list[str]:
    made = folder.read_json(REDO_SET)
    if made is None:
        raise Refused("There is no blind redo yet. Start it with: redo start.")
    return list(made["item_ids"])


def answer(
    folder: Folder,
    item_id: str,
    pts: list[str],
    none_reason: str,
    note: str,
    reviewer: str,
    clock: Clock = utc_now,
    release: Path | None = None,
) -> None:
    if item_id not in item_ids(folder):
        raise Refused("That item is not in the blind redo.")
    chosen, reason = decisions.own_coding(folder, pts, none_reason, release)
    reasons = coding.reasons()
    if reason and reasons[reason].needs_note and not note.strip():
        raise Refused(f'"{reasons[reason].name}" needs a note saying why.')
    row = {
        "item_id": item_id,
        "pts": chosen,
        "none_reason": reason,
        "note": note.strip(),
        "reviewer": reviewer.strip(),
        "decided_at": stamp(clock),
    }
    folder.append(REDO_ANSWERS, [row])


def answers(folder: Folder) -> dict[str, dict]:
    return {row["item_id"]: row for row in folder.read(REDO_ANSWERS)}


@dataclass(frozen=True)
class Difference:
    item_id: str
    first: list[str]
    first_reason: str
    redo: list[str]
    redo_reason: str


@dataclass(frozen=True)
class RedoReport:
    items: int
    answered: int
    differences: list[Difference]  # other preferred terms, or terms against none
    reason_only: list[Difference]  # none both times, for different reasons


def compare(folder: Folder) -> RedoReport:
    """Where the redo coding differs from the first decision."""
    first = decisions.latest(folder)
    redone = answers(folder)
    ids = item_ids(folder)
    pairs = [
        Difference(i, first[i].pts, first[i].none_reason, r["pts"], r["none_reason"])
        for i in ids
        if (r := redone.get(i))
    ]
    differences = [d for d in pairs if not decisions.same_terms(d.first, d.redo)]
    reason_only = [
        d for d in pairs if not d.first and not d.redo and d.first_reason != d.redo_reason
    ]
    return RedoReport(len(ids), len(pairs), differences, reason_only)
