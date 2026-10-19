"""Invented label review data: uncertain label phrases, an agent that codes them from a table,
and a small `label_flags_T`. No real label text and no MedDRA content."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from open_altio import rulebook
from open_altio.labelreview import suggest

SECTIONS = (
    "boxed_warning",
    "warnings_and_precautions",
    "adverse_reactions",
    "contraindications",
)
WHY = ("table cell matched no term", "list item matched no term", "population words")
FLAG_OUTCOMES = (
    "on_label",
    "related",
    "not_on_label",
    "treated_disease",
    "procedure",
    "not_a_medical_event",
    "no_label",
)


def item_rows(drugs: int = 6, per_drug: int = 40, skewed: int = 0) -> list[dict]:
    """`per_drug` items for each drug, plus `skewed` more for the first drug alone."""
    rows = []
    for d in range(drugs):
        for k in range(per_drug + (skewed if d == 0 else 0)):
            rows.append(
                {
                    "item_id": hashlib.sha256(f"{d}-{k}".encode()).hexdigest()[:16],
                    "set_id": f"set-{d}",
                    "rxcui": f"rx{d}",
                    "drug": f"Drug {d}",
                    "section": SECTIONS[k % len(SECTIONS)],
                    "sentence": f"Patients on drug {d} reported glimmer {k} in trials.",
                    # Every third phrase matched no term, as most uncertain phrases do.
                    "candidate_pt": "" if k % 3 == 0 else f"Glimmer {k}",
                    "why_uncertain": WHY[k % len(WHY)],
                    "label_date": f"20{10 + d}-0{1 + k % 9}-15",
                    "rank": float(k % 7),
                }
            )
    return rows


def write_items(folder: Path, rows: Sequence[dict]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "label_uncertain.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


DEFAULT_PTS = ("Nausea",)  # a preferred term of the invented MedDRA in fakemeddra


def answer_items(
    batch_dir: Path,
    answers: dict[str, list[str] | str] | None = None,
    pts: Sequence[str] = DEFAULT_PTS,
    evidence: str | None = None,
    blank: Sequence[str] = (),
) -> None:
    """Do what an agent does with an exported batch folder: write suggestions.jsonl.

    Each phrase gets `answers[phrase]`: a list of preferred terms, or a reason for none. Other
    phrases get `pts`. Items in `blank` get neither, which is no answer.
    """
    answers = answers or {}
    lines = []
    for line in (batch_dir / suggest.ITEMS).read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        given = answers.get(item["sentence"], list(pts))
        named, reason = (given, "") if isinstance(given, list) else ([], given)
        if item["item_id"] in blank:
            named, reason = [], ""
        row = {
            "item_id": item["item_id"],
            "pts": named,
            "none_reason": reason,
            "note": "The fake agent found no fit." if reason == "other" else "",
            "evidence": (evidence if evidence is not None else item["sentence"]) if named else "",
            "reason": "The fake agent read the phrase.",
        }
        lines.append(json.dumps(row) + "\n")
    (batch_dir / suggest.ANSWERS).write_text("".join(lines), encoding="utf-8")


def write_agent(
    path: Path, blank_calls: int = 0, never: Sequence[str] = (), junk_calls: int = 0
) -> str:
    """A tiny agent command line, for the run command: the command to pass as --agent.

    Its first `junk_calls` runs write a file that is not JSON; its first `blank_calls` runs
    leave every item blank; after that it answers every item except those in `never`. It
    counts its runs in a file beside itself.
    """
    config = {
        "counter": str(path.with_suffix(".runs")),
        "blank_calls": blank_calls,
        "never": list(never),
        "junk_calls": junk_calls,
    }
    path.write_text(
        "import sys\n"
        "from open_altio.testing.fakereview import agent_main\n"
        f"agent_main({config!r}, sys.argv[1:])\n",
        encoding="utf-8",
    )
    words = [sys.executable, str(path)]
    return subprocess.list2cmdline(words) if os.name == "nt" else shlex.join(words)


def agent_main(config: dict, argv: list[str]) -> None:
    """The body of the agent `write_agent` writes; it works in the folder it is started in."""
    counter = Path(config["counter"])
    runs = int(counter.read_text()) + 1 if counter.is_file() else 1
    counter.write_text(str(runs))
    if argv[-1:] != [suggest_prompt()]:
        raise SystemExit("the fake agent was not given the rule's prompt")
    here = Path.cwd()
    if runs <= config["junk_calls"]:
        (here / suggest.ANSWERS).write_text("not what was asked for\n", encoding="utf-8")
    elif runs <= config["blank_calls"]:
        items = [
            json.loads(line)["item_id"] for line in (here / suggest.ITEMS).read_text().splitlines()
        ]
        answer_items(here, blank=items)
    else:
        answer_items(here, blank=config["never"])


def suggest_prompt() -> str:
    return str(rulebook.value("label-agent", "prompt"))


def write_flags(path: Path, per_outcome: int = 30, not_by_rule: int = 5) -> Path:
    """A `label_flags_T`: `per_outcome` rule-made flags per outcome, and a few a person made."""
    rows = []
    for o, outcome in enumerate(FLAG_OUTCOMES):
        for k in range(per_outcome + not_by_rule):
            rows.append(
                {
                    "rxcui": f"rx{k % 9}",
                    "pt": f"Glimmer {o}-{k}",
                    "outcome": outcome,
                    "section": "" if outcome != "on_label" else "adverse_reactions",
                    "set_id": "" if outcome == "no_label" else f"set-{k % 9}",
                    "label_date": "2024-05-01",
                    "decided_by": "rule" if k < per_outcome else "model_reviewed",
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path
