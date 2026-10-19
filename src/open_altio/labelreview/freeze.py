"""Decided codings become frozen data, so a release build codes the same and never runs an agent.

The label step reads `label_codings_frozen.jsonl` (`open_altio.faers.labeldict.codings`), one
line per decided item: `item_id`, `set_id`, `section`, `sentence`, `pts` (preferred term names,
empty for none), `none_reason`, `agent` (who suggested), `instructions_version`, `reviewed_at`.
It turns those terms into flags by its own rules; nothing here decides a flag.
"""

from __future__ import annotations

from typing import Any

from . import decisions
from .items import read_items
from .store import FROZEN, Folder


def frozen_rows(folder: Folder) -> list[dict[str, Any]]:
    items = read_items(folder)
    return [
        {
            "item_id": item_id,
            "set_id": items[item_id].set_id,
            "section": items[item_id].section,
            "sentence": items[item_id].sentence,
            "pts": d.pts,
            "none_reason": d.none_reason,
            "agent": d.suggested_by,
            "instructions_version": d.instructions_version,
            "reviewed_at": d.decided_at,
        }
        for item_id, d in sorted(decisions.latest(folder).items())
    ]


def freeze(folder: Folder) -> int:
    """Write every decided item to the frozen file, in a fixed order, and say how many."""
    rows = frozen_rows(folder)
    folder.replace(FROZEN, rows)
    return len(rows)
