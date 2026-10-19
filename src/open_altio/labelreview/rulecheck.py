"""The rule check: a seeded random sample of rule-decided flags, each marked right or wrong by hand.

The error rate per outcome, with a Wilson interval, is what gets published about the fixed
rules (rule label-rule-check).
"""

from __future__ import annotations

import math
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any

import pyarrow.parquet as pq

from open_altio import rulebook

from .store import DECISIONS, RULE_CHECK, Clock, Folder, Refused, stamp, utc_now

RULE = "label-rule-check"
KIND = "rule_check"
RIGHT = "right"
WRONG = "wrong"
COLUMNS = (
    "rxcui",
    "pt",
    "outcome",
    "section",
    "set_id",
    "label_date",
    "decided_by",
    "drug",
)


def outcomes() -> dict[str, str]:
    """The outcomes sampled, each with its name."""
    return dict(rulebook.value(RULE, "outcomes"))


def flag_key(row: dict[str, Any]) -> str:
    return f"{row['rxcui']}|{row['pt']}"


def share_out(size: int, available: dict[str, int]) -> dict[str, int]:
    """Split `size` as evenly as possible; what one outcome cannot fill goes to the others."""
    taken = {o: 0 for o in available}
    left = size
    while left > 0:
        open_ = [o for o in available if taken[o] < available[o]]
        if not open_:
            break
        each = max(1, left // len(open_))
        for o in open_:
            step = min(each, available[o] - taken[o], left)
            taken[o] += step
            left -= step
    return taken


def draw(
    folder: Folder, flags_path: str | os.PathLike[str], clock: Clock = utc_now
) -> list[dict[str, Any]]:
    """Draw the sample once from `label_flags_T` and keep it in the licensed folder."""
    if folder.read_json(RULE_CHECK) is not None:
        raise Refused("The rule check sample is already drawn; it is drawn once.")
    table = pq.read_table(flags_path)
    columns = [c for c in COLUMNS if c in table.column_names]
    decided_by = rulebook.value(RULE, "decided_by")
    wanted = list(outcomes())
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in table.select(columns).to_pylist():
        if row.get("decided_by", decided_by) == decided_by and row["outcome"] in wanted:
            groups[row["outcome"]].append({k: "" if v is None else str(v) for k, v in row.items()})
    shares = share_out(
        int(rulebook.value(RULE, "sample_size")), {o: len(groups[o]) for o in wanted}
    )
    chance = random.Random(int(rulebook.value(RULE, "sample_seed")))
    picked: list[dict[str, Any]] = []
    for outcome in wanted:
        # Sorted first, so the seed alone decides the sample, not the table's row order.
        pool = sorted(groups[outcome], key=lambda r: (r["rxcui"], r["pt"]))
        picked += chance.sample(pool, shares[outcome])
    folder.write_json(
        RULE_CHECK,
        {"source": Path(flags_path).name, "drawn_at": stamp(clock), "flags": picked},
    )
    return picked


def sample(folder: Folder) -> list[dict[str, Any]]:
    drawn = folder.read_json(RULE_CHECK)
    if drawn is None:
        raise Refused(
            "There is no rule check sample yet. Draw it with: sample --flags label_flags_T.parquet."
        )
    return list(drawn["flags"])


def checks(folder: Folder) -> dict[str, dict[str, Any]]:
    return {row["flag"]: row for row in folder.read(DECISIONS) if row.get("kind") == KIND}


def check(
    folder: Folder,
    key: str,
    verdict: str,
    right_outcome: str | None,
    note: str,
    reviewer: str,
    clock: Clock = utc_now,
) -> dict[str, Any]:
    flag = next((f for f in sample(folder) if flag_key(f) == key), None)
    if flag is None:
        raise Refused("That flag is not in the rule check sample.")
    if not reviewer.strip():
        raise Refused("A check needs the reviewer's name.")
    if verdict == RIGHT:
        right = flag["outcome"]
    elif verdict == WRONG:
        if right_outcome not in outcomes():
            raise Refused("Choose the right outcome before marking a flag wrong.")
        if right_outcome == flag["outcome"]:
            raise Refused("That is the outcome the rules gave. Mark it right instead.")
        right = right_outcome
    else:
        raise Refused(f"A flag is marked {RIGHT} or {WRONG}, not {verdict!r}.")
    row = {
        "kind": KIND,
        "flag": key,
        "rxcui": flag["rxcui"],
        "pt": flag["pt"],
        "outcome": flag["outcome"],
        "verdict": verdict,
        "right_outcome": right,
        "note": note.strip(),
        "reviewer": reviewer.strip(),
        "decided_at": stamp(clock),
    }
    folder.append(DECISIONS, [row])
    return row


@dataclass(frozen=True)
class Rate:
    outcome: str
    drawn: int
    checked: int
    wrong: int
    low: float
    high: float

    @property
    def rate(self) -> float:
        return self.wrong / self.checked if self.checked else 0.0


def wilson(wrong: int, checked: int, confidence: float) -> tuple[float, float]:
    """The range the true error rate likely lies in; honest at 0 wrong, unlike plus or minus."""
    if checked == 0:
        return 0.0, 1.0
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = wrong / checked
    denominator = 1 + z * z / checked
    centre = (p + z * z / (2 * checked)) / denominator
    half = z * math.sqrt(p * (1 - p) / checked + z * z / (4 * checked * checked)) / denominator
    # With none wrong the range starts at exactly 0, and with all wrong it ends at exactly 1:
    # centre and half are then equal in theory, but rounding can leave a crumb between them.
    low = 0.0 if wrong == 0 else max(0.0, centre - half)
    high = 1.0 if wrong == checked else min(1.0, centre + half)
    return low, high


def error_rates(folder: Folder) -> list[Rate]:
    confidence = float(rulebook.value(RULE, "confidence"))
    done = checks(folder)
    drawn = sample(folder)
    rates = []
    for outcome in outcomes():
        keys = [flag_key(f) for f in drawn if f["outcome"] == outcome]
        checked = [done[k] for k in keys if k in done]
        wrong = sum(c["verdict"] == WRONG for c in checked)
        low, high = wilson(wrong, len(checked), confidence)
        rates.append(Rate(outcome, len(keys), len(checked), wrong, low, high))
    return rates
