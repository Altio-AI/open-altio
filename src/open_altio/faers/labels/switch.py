"""Files built beside a release moved into it as one change (rule label-refresh).

    switch(staging, release_dir, moves)   each (staged file, its place in the release), in order
    finish(staging, release_dir)          a switch a crash stopped, finished

The moves are written down first. Each file the switch replaces is copied aside, and the new
one is copied in beside it and renamed over it, so a reader sees the old file or the new one,
never part of one. When a move fails, the files already moved are put back and the release is
as it was. A crash leaves the list and every staged file behind, whole, so the next refresh
moves them all in.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path, PurePosixPath

MOVES = "moves.json"
ASIDE = "previous"


class SwitchStopped(Exception):
    """A failed switch whose files could not all be put back; the next refresh finishes it."""


def _place(folder: Path, rel: str) -> Path:
    return folder.joinpath(*PurePosixPath(rel).parts)


def _move_in(staged: Path, target: Path) -> None:
    incoming = target.with_name(f".{target.name}.incoming")
    try:
        shutil.copy2(staged, incoming)
        os.replace(incoming, target)
    finally:
        incoming.unlink(missing_ok=True)


def switch(staging: Path, release_dir: Path, moves: list[tuple[str, str]]) -> None:
    """Move each staged file (a path in `staging`) to its place (a path in `release_dir`), the
    last one last, then remove `staging`."""
    written = staging / f".{MOVES}"
    written.write_text(json.dumps(moves), encoding="utf-8")
    os.replace(written, staging / MOVES)
    aside = staging / ASIDE
    aside.mkdir()
    done: list[tuple[Path, Path | None]] = []
    try:
        for n, (staged, rel) in enumerate(moves):
            target = _place(release_dir, rel)
            kept = aside / str(n) if target.is_file() else None
            if kept is not None:
                shutil.copy2(target, kept)
            _move_in(_place(staging, staged), target)
            done.append((target, kept))
    except OSError as stopped:
        try:
            for target, kept in reversed(done):
                if kept is None:
                    target.unlink()
                else:
                    os.replace(kept, target)
        except OSError as again:
            raise SwitchStopped(
                f"the new labels were half switched in and could not be put back ({again}); "
                "the next refresh switches the rest in"
            ) from stopped
        shutil.rmtree(staging)
        raise
    shutil.rmtree(staging)


def finish(staging: Path, release_dir: Path) -> bool:
    """Finish a switch a crash stopped, and remove what a refresh left before its switch.
    True when a stopped switch was finished."""
    listed = staging / MOVES
    stopped = listed.is_file()
    if stopped:
        for staged, rel in json.loads(listed.read_text(encoding="utf-8")):
            _move_in(_place(staging, staged), _place(release_dir, rel))
    if staging.exists():
        shutil.rmtree(staging)
    return stopped
