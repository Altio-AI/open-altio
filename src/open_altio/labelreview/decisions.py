"""The reviewer's decisions: accept the agent's coding, or give the right one.

The file only grows. A later decision on the same item replaces the earlier one in effect,
and the earlier one stays as the record of what changed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import coding, suggest, terms
from .store import DECISIONS, Clock, Folder, Refused, stamp, utc_now

ACCEPT = "accept"
REJECT = "reject"
KIND = "phrase"  # the rule check's marks share the file under their own kind


@dataclass(frozen=True)
class Decision:
    item_id: str
    batch: int
    verdict: str
    pts: list[str]
    none_reason: str
    note: str
    reviewer: str
    decided_at: str
    suggested_pts: list[str]
    suggested_none_reason: str
    suggested_by: str
    instructions_version: int

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Decision:
        return cls(**{k: row[k] for k in cls.__dataclass_fields__})


def latest(folder: Folder) -> dict[str, Decision]:
    rows = folder.read(DECISIONS)
    return {row["item_id"]: Decision.from_row(row) for row in rows if row.get("kind") == KIND}


def same_terms(a: list[str], b: list[str]) -> bool:
    return {t.casefold() for t in a} == {t.casefold() for t in b}


def agrees(decision: Decision, suggestion: dict[str, Any]) -> bool:
    """Agreement is the same preferred terms, or none on both sides whatever the reasons."""
    if not suggest.is_answer(suggestion):
        return False
    return same_terms(decision.pts, suggestion["pts"])


def differs_only_in_reason(decision: Decision, suggestion: dict[str, Any]) -> bool:
    """Both said none for different reasons: listed for tidying, never blocking."""
    return (
        suggest.is_answer(suggestion)
        and not decision.pts
        and not suggestion["pts"]
        and decision.none_reason != suggestion["none_reason"]
    )


def decide(
    folder: Folder,
    item_id: str,
    verdict: str,
    pts: list[str],
    none_reason: str,
    note: str,
    reviewer: str,
    clock: Clock = utc_now,
    release: Path | None = None,
) -> Decision:
    """Record one decision. Accept takes the agent's coding; reject takes the reviewer's."""
    from .batches import batch_of  # batches imports gates, which imports this module

    batch = batch_of(folder).get(item_id)
    if batch is None:
        raise Refused("That item is not in a review batch.")
    suggestion = suggest.latest(folder).get(item_id)
    if suggestion is None:
        raise Refused("The agent has not suggested anything for that item yet.")
    if not reviewer.strip():
        raise Refused("A decision needs the reviewer's name.")
    if verdict == ACCEPT:
        if not suggest.is_answer(suggestion):
            raise Refused(
                "The agent gave no answer to accept. Give the right one and press Reject."
            )
        chosen, reason = list(suggestion["pts"]), suggestion["none_reason"]
    elif verdict == REJECT:
        chosen, reason = own_coding(folder, pts, none_reason, release)
        if (
            suggest.is_answer(suggestion)
            and same_terms(chosen, suggestion["pts"])
            and (chosen or reason == suggestion["none_reason"])
        ):
            raise Refused("That is what the agent suggested. Press Accept instead.")
    else:
        raise Refused(f"A decision is {ACCEPT} or {REJECT}, not {verdict!r}.")
    reasons = coding.reasons()
    if reason and reasons[reason].needs_note and not note.strip():
        raise Refused(f'"{reasons[reason].name}" needs a note saying why.')
    decision = Decision(
        item_id=item_id,
        batch=batch,
        verdict=verdict,
        pts=chosen,
        none_reason=reason,
        note=note.strip(),
        reviewer=reviewer.strip(),
        decided_at=stamp(clock),
        suggested_pts=list(suggestion["pts"]),
        suggested_none_reason=suggestion["none_reason"],
        suggested_by=suggestion["by"],
        instructions_version=suggestion["instructions_version"],
    )
    folder.append(DECISIONS, [{"kind": KIND, **asdict(decision)}])
    return decision


def own_coding(
    folder: Folder, pts: list[str], none_reason: str, release: Path | None
) -> tuple[list[str], str]:
    """The reviewer's own coding, checked like an agent's: current terms, or one reason for none."""
    names = [p for p in pts if p.strip()]
    if names and none_reason:
        raise Refused("Give preferred terms or a reason for none, not both.")
    if not names:
        if none_reason not in coding.reasons():
            raise Refused("Give the preferred terms the phrase states, or a reason for none.")
        return [], none_reason
    known = terms.current_pts(release, folder.path)
    spelt, unknown = terms.check_pts(names, known)
    if unknown:
        raise Refused("Not a current MedDRA preferred term: " + ", ".join(unknown))
    return spelt, ""
