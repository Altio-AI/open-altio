"""Whether a batch has earned a bigger one (rule label-review-gates)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from open_altio import rulebook

from . import decisions, suggest
from .store import Folder

RULE = "label-review-gates"
OTHER = "other"


@dataclass(frozen=True)
class GateResult:
    batch: int
    items: int
    decided: int
    other: int
    agreed: int
    stale: int
    no_answer: int
    reasons: list[str] = field(default_factory=list)
    # both said none, for different reasons: for tidying the reasons, never blocking
    reason_only: list[str] = field(default_factory=list)

    @property
    def other_share(self) -> float:
        return self.other / self.items if self.items else 0.0

    @property
    def agreement(self) -> float:
        return self.agreed / self.items if self.items else 0.0

    @property
    def passed(self) -> bool:
        return not self.reasons


def check(folder: Folder, number: int, item_ids: Sequence[str]) -> GateResult:
    made = decisions.latest(folder)
    said = suggest.latest(folder)
    decided = [made[i] for i in item_ids if i in made]
    other = sum(not d.pts and d.none_reason == OTHER for d in decided)
    agreed = sum(d.item_id in said and decisions.agrees(d, said[d.item_id]) for d in decided)
    digest = suggest.prompt_digest()
    stale = sum(i not in said or not suggest.is_current(said[i], digest) for i in item_ids)
    blank = sum(i in said and not suggest.is_answer(said[i]) for i in item_ids)
    tidy = [
        d.item_id
        for d in decided
        if d.item_id in said and decisions.differs_only_in_reason(d, said[d.item_id])
    ]
    result = GateResult(
        number,
        len(item_ids),
        len(decided),
        other,
        agreed,
        stale,
        blank,
        reason_only=tidy,
    )
    result.reasons.extend(_reasons(result))
    return result


def _reasons(r: GateResult) -> list[str]:
    below = float(rulebook.value(RULE, "other_share_below"))
    at_least = float(rulebook.value(RULE, "agreement_at_least"))
    reasons = []
    if r.decided < r.items:
        reasons.append(f"{r.items - r.decided} of {r.items} items are not decided yet.")
    if r.other_share >= below:
        reasons.append(
            f'{r.other} of {r.items} are "other" ({r.other_share:.1%}); '
            f"it must be under {below:.0%}."
        )
    if r.agreement < at_least:
        reasons.append(
            f"The agent agreed on {r.agreed} of {r.items} ({r.agreement:.0%}); "
            f"it must agree on at least {at_least:.0%}."
        )
    if r.no_answer:
        reasons.append(
            f"{r.no_answer} items have no answer from the agent; each counts as a disagreement."
        )
    if r.stale:
        reasons.append(
            f"{r.stale} suggestions are missing or came from older instructions or "
            "coding rules; export and import again, or run the agent again."
        )
    return reasons
