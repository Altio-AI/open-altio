"""The review's files, all in one licensed folder.

Every file here ties label text to MedDRA terms, so the folder must be a
licensed one and never part of the public tree (rule meddra-licensed-tier).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_altio import rulebook
from open_altio.faers.labeldict import UNCERTAIN_FILE
from open_altio.faers.meddra import LABEL_CODINGS_FILE, LABEL_REVIEW_FILES

# The label step writes the uncertain items and reads the frozen codings; the review's own
# files are named beside them, so rebuilding the MedDRA version keeps them.
UNCERTAIN = UNCERTAIN_FILE
FROZEN = LABEL_CODINGS_FILE
BATCHES = LABEL_REVIEW_FILES["batches"]
SUGGESTIONS = LABEL_REVIEW_FILES["suggestions"]
DECISIONS = LABEL_REVIEW_FILES["decisions"]
REDO_SET = LABEL_REVIEW_FILES["redo_set"]
REDO_ANSWERS = LABEL_REVIEW_FILES["redo_answers"]
RULE_CHECK = LABEL_REVIEW_FILES["rule_check"]
LICENSED_PART = "licensed"

Clock = Callable[[], datetime]


class PublicPath(ValueError):
    """The folder would put MedDRA-coded results where the public could read them."""


class Refused(ValueError):
    """An act the review does not allow, with the reason in plain words."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def stamp(clock: Clock) -> str:
    return clock().astimezone(UTC).isoformat(timespec="seconds")


def check_licensed(path: str | os.PathLike[str]) -> Path:
    folder = Path(path).expanduser().resolve()
    if LICENSED_PART not in folder.parts:
        raise PublicPath(
            f"{folder} is not inside a folder named '{LICENSED_PART}'. The review's files tie "
            "label text to MedDRA terms, so they live only in a licensed folder."
        )
    root = rulebook.data_root().resolve()
    if (root / ".git").exists() and folder.is_relative_to(root) and not _ignored(root, folder):
        raise PublicPath(f"{folder} is inside the repository and git would publish it.")
    return folder


def _ignored(root: Path, folder: Path) -> bool:
    # git is the authority on what a commit can pick up, so ask it rather than copy .gitignore.
    probe = folder / UNCERTAIN
    done = subprocess.run(
        ["git", "check-ignore", "-q", str(probe)],
        cwd=root,
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


class Folder:
    """One licensed folder holding the input items and everything the review writes."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = check_licensed(path)
        self._lock = threading.Lock()

    def file(self, name: str) -> Path:
        return self.path / name

    def read(self, name: str) -> list[dict[str, Any]]:
        path = self.file(name)
        if not path.is_file():
            return []
        with path.open(encoding="utf-8") as lines:
            return [json.loads(line) for line in lines if line.strip()]

    def append(self, name: str, rows: Iterable[dict[str, Any]]) -> None:
        with self._lock:
            self.path.mkdir(parents=True, exist_ok=True)
            with self.file(name).open("a", encoding="utf-8") as out:
                for row in rows:
                    out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def replace(self, name: str, rows: Iterable[dict[str, Any]]) -> None:
        """Write a whole file at once, so a reader never sees half of it."""
        with self._lock:
            self.path.mkdir(parents=True, exist_ok=True)
            part = self.file(name + ".part")
            with part.open("w", encoding="utf-8") as out:
                for row in rows:
                    out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            part.replace(self.file(name))

    def read_json(self, name: str) -> dict[str, Any] | None:
        path = self.file(name)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def write_json(self, name: str, data: dict[str, Any]) -> None:
        with self._lock:
            self.path.mkdir(parents=True, exist_ok=True)
            self.file(name).write_text(
                json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8"
            )
