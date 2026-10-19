"""Run the person's own agent on a batch folder, import, and ask again for what it left blank.

The agent is any command line that takes the words of rule label-agent's `prompt` as its last
argument and works in the folder it is started in: `claude -p`, `codex exec`, `gemini -p`, or a
local model's command. Each attempt is logged in the batch folder. After the last retry an
item still without an answer is refused, and the reviewer decides it.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from open_altio import rulebook

from . import suggest
from .store import Clock, Folder, Refused, stamp, utc_now

RULE = "label-agent"
LOG = "attempts.jsonl"

Run = Callable[..., subprocess.CompletedProcess]


def waits() -> list[float]:
    """The wait before each retry: the first, then growing by the factor, never past the longest."""
    rule = rulebook.rule(RULE)
    first, factor = (
        float(rule.value("first_wait_seconds")),
        float(rule.value("wait_factor")),
    )
    longest = float(rule.value("longest_wait_seconds"))
    return [min(first * factor**k, longest) for k in range(int(rule.value("retries")))]


@dataclass(frozen=True)
class RunReport:
    batch: int
    attempts: int
    answered: int
    refused: list[str]


def run(
    folder: Folder,
    agent: str,
    by: str = "",
    clock: Clock = utc_now,
    sleep: Callable[[float], None] = time.sleep,
    start: Run = subprocess.run,
    release: Path | None = None,
) -> RunReport:
    """Export, run the agent, import; then retry only the items left without an answer."""
    if not agent.strip():
        raise Refused('Name the agent command, such as --agent "codex exec".')
    by = by.strip() or agent.strip()
    prompt = str(rulebook.value(RULE, "prompt"))
    timeout = float(rulebook.value(RULE, "attempt_timeout_minutes")) * 60
    pauses = [0.0, *waits()]
    answered = 0
    out = suggest.export_batch(folder, clock, release=release)
    for attempt, pause in enumerate(pauses):
        if attempt:
            sleep(pause)
            out = suggest.export_batch(folder, clock, replace_unimported=True, release=release)
        asked = json.loads((out / suggest.EXPORT).read_text(encoding="utf-8"))
        entry = {
            "attempt": attempt,
            "waited_seconds": pause,
            "started_at": stamp(clock),
            "items": asked["item_ids"],
        }
        try:
            done = start(
                _command_line(agent, prompt),
                cwd=out,
                timeout=timeout,
                capture_output=True,
                text=True,
            )
            entry["exit_code"] = done.returncode
        except (OSError, subprocess.TimeoutExpired) as failed:
            entry["exit_code"] = None
            entry["problem"] = str(failed)
        try:
            report = suggest.import_suggestions(folder, by, out, clock, release)
            left = report.unanswered
            answered += len(report.answered)
            entry["outcome"] = f"{len(report.answered)} answered, {len(left)} without an answer"
        except Refused as why:
            # A bad file keeps nothing, so every item is asked again; the file is kept to read.
            left = asked["item_ids"]
            kept = out / f"suggestions.attempt-{attempt}.jsonl"
            if (out / suggest.ANSWERS).is_file():
                (out / suggest.ANSWERS).replace(kept)
            entry["outcome"] = f"file refused, kept as {kept.name}: {why}"
            (out / suggest.PROBLEMS).write_text(f"{why}\n", encoding="utf-8")
        else:
            (out / suggest.PROBLEMS).unlink(missing_ok=True)  # an old complaint no longer holds
        entry["finished_at"] = stamp(clock)
        entry["left"] = left
        _log(out, entry)
        if not left:
            return RunReport(asked["batch"], attempt + 1, answered, [])
    suggest.mark_refused(folder, left, by, clock)
    _log(out, {"refused": left, "at": stamp(clock)})
    return RunReport(asked["batch"], len(pauses), answered, left)


def _command_line(agent: str, prompt: str) -> list[str] | str:
    """The agent's command line with the prompt as its last argument, read as the person's own
    system reads a command line."""
    if os.name == "nt":
        # A POSIX split reads the backslashes of a Windows path as escapes. Windows programs
        # split their own command line, so it goes to them whole, the prompt quoted for them.
        return f"{agent.strip()} {subprocess.list2cmdline([prompt])}"
    return [*shlex.split(agent), prompt]


def _log(out: Path, entry: dict) -> None:
    with (out / LOG).open("a", encoding="utf-8") as log:
        log.write(json.dumps(entry) + "\n")
