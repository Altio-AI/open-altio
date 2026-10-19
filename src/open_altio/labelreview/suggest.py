"""Codings from any agent, file in and file out (rule label-agent).

`export_batch` writes a folder an agent can work in on its own: INSTRUCTIONS.md (the
published instructions and the coding question), items.jsonl and an empty
suggestions.jsonl. The person tells their agent to follow INSTRUCTIONS.md. Then
`import_suggestions` checks every line the agent wrote, every term against MedDRA's current
preferred terms, and keeps them with who produced them, or refuses the whole file with the
reasons. No model is called from here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from open_altio import rulebook

from . import coding, terms
from .items import Item, read_items
from .store import SUGGESTIONS, Clock, Folder, Refused, check_licensed, stamp, utc_now

RULE = "label-agent"
INSTRUCTIONS = "INSTRUCTIONS.md"
ITEMS = "items.jsonl"
ANSWERS = "suggestions.jsonl"
EXPORT = "export.json"
TERMS = "preferred_terms.txt"  # the version's preferred terms, so any agent can spell them exactly
PROBLEMS = "problems.txt"  # why the agent's last file was refused, for its next try
FIELDS = ("item_id", "pts", "none_reason", "note", "evidence", "reason")
ANSWERED = "answered"
NO_ANSWER = "no_answer"  # left out or left blank; asked again by the run command
REFUSED = "refused"  # still no answer after the run command's last retry


def instructions_version() -> int:
    return int(rulebook.value(RULE, "instructions_version"))


def instructions_document() -> str:
    """What the agent reads: the versioned instructions, then the coding question's rules."""
    name = f"v{instructions_version()}.md"
    text = resources.files(__package__).joinpath("instructions", name).read_text(encoding="utf-8")
    return text.rstrip() + "\n\n## The question and its rules\n\n" + coding.as_text()


def prompt_digest() -> str:
    """Changes whenever the words the agent reads change, so older suggestions show as stale."""
    return hashlib.sha256(instructions_document().encode("utf-8")).hexdigest()[:16]


def latest(folder: Folder) -> dict[str, dict[str, Any]]:
    """The newest suggestion for each item."""
    return {row["item_id"]: row for row in folder.read(SUGGESTIONS)}


def is_current(row: dict[str, Any], digest: str) -> bool:
    """`digest` is today's prompt_digest(), worked out once by the caller for a whole batch."""
    return row.get("prompt_digest") == digest


def is_answer(row: dict[str, Any]) -> bool:
    """False for an item the agent left blank, declined or refused: the reviewer decides it."""
    return row.get("status") == ANSWERED


def _settled(row: dict[str, Any] | None, digest: str) -> bool:
    """An item not to hand to the agent again: answered or refused under today's instructions."""
    return row is not None and is_current(row, digest) and row.get("status") != NO_ANSWER


def batch_dir(folder: Folder, number: int) -> Path:
    return folder.path / f"batch-{number}"


def export_batch(
    folder: Folder,
    clock: Clock = utc_now,
    replace_unimported: bool = False,
    release: Path | None = None,
) -> Path:
    """Write the current batch's unsettled items into a folder for an agent to work in."""
    from .batches import current  # batches imports gates, which imports this module

    batch = current(folder)
    if batch is None:
        raise Refused("There is no batch yet. Start one with the batch command.")
    items = read_items(folder)
    have = latest(folder)
    digest = prompt_digest()
    todo = [items[i] for i in batch.item_ids if not _settled(have.get(i), digest)]
    if not todo:
        raise Refused(f"Every item in batch {batch.number} already has a current suggestion.")
    out = check_licensed(batch_dir(folder, batch.number))
    sent = _read_json(out / EXPORT)
    if sent and not sent.get("imported") and _lines(out / ANSWERS) and not replace_unimported:
        raise Refused(f"{out / ANSWERS} holds answers not imported yet. Import them first.")
    out.mkdir(parents=True, exist_ok=True)
    (out / INSTRUCTIONS).write_text(instructions_document(), encoding="utf-8")
    names = sorted(terms.current_pts(release, folder.path).values())
    (out / TERMS).write_text("".join(n + "\n" for n in names), encoding="utf-8")
    (out / ITEMS).write_text("".join(json.dumps(_shown(i)) + "\n" for i in todo), encoding="utf-8")
    (out / ANSWERS).write_text("", encoding="utf-8")
    record = {
        "batch": batch.number,
        "item_ids": [i.item_id for i in todo],
        "instructions_version": instructions_version(),
        "prompt_digest": digest,
        "exported_at": stamp(clock),
        "imported": False,
    }
    (out / EXPORT).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return out


def _shown(item: Item) -> dict[str, str]:
    return {
        "item_id": item.item_id,
        "drug": item.drug or f"RxNorm {item.rxcui}",
        "section": item.section,
        "sentence": item.sentence,
        "rules_guess": item.candidate_pt,
        "why_uncertain": item.why_uncertain,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@dataclass(frozen=True)
class ImportReport:
    batch: int
    answered: list[str]
    unanswered: list[str]


def import_suggestions(
    folder: Folder,
    by: str,
    source: Path | None = None,
    clock: Clock = utc_now,
    release: Path | None = None,
) -> ImportReport:
    """Keep every line of the agent's file, or refuse the whole file and say why."""
    from .batches import current

    if not by.strip():
        raise Refused('Say who produced the suggestions, such as --by "Codex, gpt-5".')
    batch = current(folder)
    if batch is None:
        raise Refused("There is no batch yet. Start one with the batch command.")
    out = source or batch_dir(folder, batch.number)
    sent = _read_json(out / EXPORT)
    if sent is None:
        raise Refused(f"{out} was not written by the export command.")
    if sent["prompt_digest"] != prompt_digest():
        raise Refused(
            "The instructions or the coding rules changed since this export. Export again."
        )
    items = read_items(folder)
    asked = {i: items[i] for i in sent["item_ids"]}
    known = terms.current_pts(release, folder.path)
    rows, problems = _check_file(_lines(out / ANSWERS), asked, known)
    if problems:
        raise Refused("The suggestions file was not imported:\n" + "\n".join(problems))
    made_at = stamp(clock)
    kept = []
    for item_id in sent["item_ids"]:
        row = rows.get(item_id) or blank(item_id)
        answered = bool(row["pts"] or row["none_reason"])
        kept.append(
            {
                **(row if answered else blank(item_id)),
                "status": ANSWERED if answered else NO_ANSWER,
                "batch": sent["batch"],
                "by": by.strip(),
                "instructions_version": sent["instructions_version"],
                "prompt_digest": sent["prompt_digest"],
                "made_at": made_at,
            }
        )
    folder.append(SUGGESTIONS, kept)
    (out / EXPORT).write_text(
        json.dumps(sent | {"imported": True}, indent=1) + "\n", encoding="utf-8"
    )
    done = [r["item_id"] for r in kept if r["status"] == ANSWERED]
    return ImportReport(
        sent["batch"], done, [r["item_id"] for r in kept if r["status"] != ANSWERED]
    )


def blank(item_id: str) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "pts": [],
        "none_reason": "",
        "note": "",
        "evidence": "",
        "reason": "",
    }


def mark_refused(folder: Folder, item_ids: list[str], by: str, clock: Clock = utc_now) -> None:
    """Items still without an answer after the last retry go to the reviewer as refused."""
    from .batches import batch_of

    numbers = batch_of(folder)
    rows = [
        blank(i)
        | {
            "status": REFUSED,
            "batch": numbers[i],
            "by": by,
            "instructions_version": instructions_version(),
            "prompt_digest": prompt_digest(),
            "made_at": stamp(clock),
        }
        for i in item_ids
    ]
    folder.append(SUGGESTIONS, rows)


def _check_file(
    lines: list[str], asked: dict[str, Item], known: dict[str, str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    reasons = coding.reasons()
    rows: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for number, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"line {number}: not a JSON object")
            continue
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            problems.append(f"line {number}: needs exactly the keys {', '.join(FIELDS)}")
            continue
        texts = [row[f] for f in FIELDS if f != "pts"]
        pts = row["pts"]
        if not all(isinstance(v, str) for v in texts) or not (
            isinstance(pts, list) and all(isinstance(p, str) for p in pts)
        ):
            problems.append(f"line {number}: pts is a list of names and every other value is text")
            continue
        why = _check_row(row, asked, known, reasons, rows)
        if why:
            problems.append(f"line {number}: {why}")
    return rows, problems


def _check_row(
    row: dict[str, Any],
    asked: dict[str, Item],
    known: dict[str, str],
    reasons: dict[str, coding.Reason],
    rows: dict[str, dict[str, Any]],
) -> str:
    """The plain reason a line is wrong, or nothing; a good line is added to `rows`."""
    item = asked.get(row["item_id"])
    if item is None:
        return f"item {row['item_id']!r} was not in this export"
    if row["item_id"] in rows:
        return f"item {row['item_id']} appears twice"
    spelt, unknown = terms.check_pts(row["pts"], known)
    if unknown:
        return "not a current MedDRA preferred term: " + ", ".join(repr(u) for u in unknown)
    reason = row["none_reason"]
    if spelt and reason:
        return "give preferred terms or a reason for none, not both"
    if spelt and not _quoted(row["evidence"], item.sentence):
        return "the evidence must be words copied from the label phrase"
    if reason and reason not in reasons:
        return f"{reason!r} is not a reason for none"
    if reason and reasons[reason].needs_note and not row["note"].strip():
        return f"{reason} needs a note saying why"
    rows[row["item_id"]] = {
        **row,
        "pts": spelt,
    }  # neither terms nor a reason: no answer
    return ""


def _quoted(evidence: str, sentence: str) -> bool:
    squash = " ".join(evidence.split()).casefold()
    return bool(squash) and squash in " ".join(sentence.split()).casefold()
