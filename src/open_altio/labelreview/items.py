"""The uncertain phrases the label step hands to the review, one JSON object per line.

The label step writes the file again each time it runs, and a phrase a frozen coding decided
leaves it. So each batch keeps its own items (rule label-review), and the review reads the
file only for phrases no batch holds yet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .store import BATCHES, UNCERTAIN, Folder, Refused

REQUIRED = (
    "item_id",
    "set_id",
    "rxcui",
    "section",
    "sentence",
    "candidate_pt",
    "why_uncertain",
)


@dataclass(frozen=True)
class Item:
    item_id: str
    set_id: str
    rxcui: str
    section: str
    sentence: str
    candidate_pt: str
    why_uncertain: str
    # Shown and used for the mix when the label step provides them; the review works without.
    drug: str = ""
    label_date: str = ""
    rank: float | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Item:
        missing = [k for k in REQUIRED if k not in row]
        if missing:
            raise Refused(f"an uncertain item lacks {missing}: {row}")
        rank = row.get("rank")
        return cls(
            **{k: str(row[k] or "") for k in REQUIRED},
            drug=str(row.get("drug") or ""),
            label_date=str(row.get("label_date") or "").replace("-", ""),
            rank=float(rank) if rank is not None else None,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_items(folder: Folder) -> dict[str, Item]:
    """Every phrase a batch holds, as the batch kept it, and the uncertain phrases not in one."""
    items: dict[str, Item] = {}
    for row in folder.read(UNCERTAIN):
        item = Item.from_row(row)
        if item.item_id in items:
            raise Refused(f"item {item.item_id} appears twice in {UNCERTAIN}")
        items[item.item_id] = item
    for batch in folder.read(BATCHES):
        items.update((row["item_id"], Item.from_row(row)) for row in batch.get("items", []))
    return items
