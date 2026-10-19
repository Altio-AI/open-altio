"""Review batches: which items each holds, how the next is picked, and when it may start."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from open_altio import rulebook

from . import gates
from .items import Item, read_items
from .store import BATCHES, Clock, Folder, Refused, stamp, utc_now

RULE = "label-review"
Trait = tuple[str, str]  # (trait, value), such as ("section", "adverse_reactions")


@dataclass(frozen=True)
class Batch:
    number: int
    item_ids: tuple[str, ...]
    made_at: str


class GateClosed(Refused):
    """The current batch has not passed its gates, so a bigger one may not start."""

    def __init__(self, reasons: Sequence[str]) -> None:
        self.reasons = list(reasons)
        super().__init__("The next batch may not start: " + " ".join(self.reasons))


def batches(folder: Folder) -> list[Batch]:
    return [
        Batch(row["batch"], tuple(row["item_ids"]), row["made_at"]) for row in folder.read(BATCHES)
    ]


def current(folder: Folder) -> Batch | None:
    made = batches(folder)
    return made[-1] if made else None


def batch_of(folder: Folder) -> dict[str, int]:
    return {item_id: b.number for b in batches(folder) for item_id in b.item_ids}


def size_for(number: int) -> int:
    """The first size, then one step more for each batch after it (rule label-review)."""
    rule = rulebook.rule(RULE)
    return int(rule.value("first_batch_size")) + int(rule.value("batch_size_step")) * (number - 1)


def check(folder: Folder, batch: Batch) -> gates.GateResult:
    return gates.check(folder, batch.number, batch.item_ids)


def start_next(folder: Folder, clock: Clock = utc_now) -> Batch:
    """Pick and record the next batch. Refused while the current batch fails a gate."""
    made = batches(folder)
    if made:
        result = check(folder, made[-1])
        if not result.passed:
            raise GateClosed(result.reasons)
    taken = {item_id for b in made for item_id in b.item_ids}
    left_out = set(rulebook.value(RULE, "not_reviewed_sections"))
    pool = [
        i
        for i in read_items(folder).values()
        if i.item_id not in taken and i.section not in left_out
    ]
    if not pool:
        raise Refused("Every uncertain item that can be reviewed is already in a batch.")
    number = len(made) + 1
    picked = pick_mix(pool, size_for(number))
    batch = Batch(number, tuple(i.item_id for i in picked), stamp(clock))
    folder.append(
        BATCHES,
        [
            {
                "batch": batch.number,
                "item_ids": list(batch.item_ids),
                "items": [i.as_dict() for i in picked],
                "made_at": batch.made_at,
            }
        ],
    )
    return batch


def pick_mix(pool: Sequence[Item], size: int) -> list[Item]:
    """Each trait's values in about the pool's shares, every value at least once, and within
    that as many drugs as possible.

    The traits are the label section, the reason the rules were unsure, the label's age and the
    rank band. Items sharing all four form a group. Each pick looks at the groups holding the
    most values not yet in the batch, and among them those whose values are furthest below their
    share of the batch, within one item of the furthest; it takes the one whose least-picked
    drug was picked least, and from it an item of that drug. Taking turns by
    drug instead over-fills the batch with the phrases of the many drugs that have only a few,
    and leaves out the kinds of phrase that sit in long labels. Item ids are hashes, so
    ordering by them is a fixed shuffle and the same pool always gives the same batch.
    """
    size = min(size, len(pool))
    traits = _traits(pool)
    counts = Counter(t for item in pool for t in traits[item.item_id])
    aim = {t: max(1.0, size * n / len(pool)) for t, n in counts.items()}
    groups: dict[tuple[Trait, ...], list[Item]] = defaultdict(list)
    for item in sorted(pool, key=lambda i: i.item_id):
        groups[traits[item.item_id]].append(item)
    got: Counter[Trait] = Counter()
    drugs: Counter[str] = Counter()
    picked: list[Item] = []
    while len(picked) < size:
        left = [k for k, items in groups.items() if items]
        missing = {t for t in aim if not got[t]}
        most = max(len(missing.intersection(k)) for k in left)
        gaps = {
            k: sum(aim[t] - got[t] for t in k) for k in left if len(missing.intersection(k)) == most
        }
        furthest = max(gaps.values())
        key = min(
            (k for k, gap in gaps.items() if gap >= furthest - 1),
            key=lambda k: (min(drugs[i.rxcui] for i in groups[k]), -gaps[k], k),
        )
        best = min(groups[key], key=lambda i: (drugs[i.rxcui], i.item_id))
        groups[key].remove(best)
        picked.append(best)
        got.update(key)
        drugs[best.rxcui] += 1
    return picked


def _traits(pool: Sequence[Item]) -> dict[str, tuple[Trait, ...]]:
    """Older and newer, higher and lower: split at the middle of the pool."""
    dates = sorted(i.label_date for i in pool if i.label_date)
    ranks = sorted(i.rank for i in pool if i.rank is not None)
    date_cut = dates[len(dates) // 2] if dates else ""
    rank_cut = ranks[len(ranks) // 2] if ranks else 0.0

    def of(item: Item) -> tuple[Trait, ...]:
        age = (
            "unknown" if not item.label_date else "older" if item.label_date < date_cut else "newer"
        )
        rank = "unknown" if item.rank is None else "lower" if item.rank < rank_cut else "higher"
        return (
            ("section", item.section),
            ("why", item.why_uncertain),
            ("age", age),
            ("rank", rank),
        )

    return {item.item_id: of(item) for item in pool}
