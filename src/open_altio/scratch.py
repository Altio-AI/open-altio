"""Scratch folders that do not outlive a killed process.

A scratch folder (DuckDB's spill files, a zip being written) is removed by the code that made it,
or by a `weakref.finalize` when the process exits. A process that is killed, crashes or is stopped
without its exit hooks runs neither, and its folder stays in the temp directory. So each folder's
name carries the id of the process that made it, `<prefix><pid>-<random>`, and making one first
clears every folder of the same prefix whose process is gone.

Only a folder this user owns, whose name is exactly `<prefix><digits>-<random>`, and whose process
is gone is cleared. A folder of a live process, of another user, or with any other name is left
alone. A folder from before names carried a process id, `<prefix><random>`, is cleared once it is
older than a day.

This module imports nothing from the package, so any module may import it.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

OLD_AFTER_SECONDS = 24 * 60 * 60
_GONE = ".removing"
_WITH_PID = re.compile(r"(\d+)-[A-Za-z0-9_]+(?:" + re.escape(_GONE) + r")?")
_WITHOUT_PID = re.compile(r"[A-Za-z0-9_]{8}")


def make(prefix: str, in_dir: Path | None = None) -> Path:
    """A new empty folder `<prefix><pid>-<random>` in `in_dir` (the temp directory by default),
    after clearing the folders of `prefix` that processes now gone left behind."""
    where = in_dir if in_dir is not None else Path(tempfile.gettempdir())
    clear_left_behind(prefix, where)
    return Path(tempfile.mkdtemp(prefix=f"{prefix}{os.getpid()}-", dir=where))


def clear_left_behind(prefix: str, in_dir: Path, now: float | None = None) -> list[str]:
    """Remove the folders of `prefix` in `in_dir` that are safe to remove; the names removed."""
    now = time.time() if now is None else now
    removed: list[str] = []
    try:
        entries = list(in_dir.iterdir())
    except OSError:
        return removed
    for path in entries:
        name = path.name
        if not name.startswith(prefix):
            continue
        rest = name[len(prefix) :]
        try:
            if path.is_symlink() or not path.is_dir() or not _mine(path):
                continue
            if (m := _WITH_PID.fullmatch(rest)) is not None:
                if _alive(int(m.group(1))):
                    continue
            elif _WITHOUT_PID.fullmatch(rest) is None or now - path.stat().st_mtime < (
                OLD_AFTER_SECONDS
            ):
                continue
            aside = path if name.endswith(_GONE) else path.with_name(name + _GONE)
            if aside != path:
                path.rename(aside)
        except OSError:
            continue
        shutil.rmtree(aside, ignore_errors=True)
        removed.append(name)
    return removed


def _mine(path: Path) -> bool:
    getuid = getattr(os, "getuid", None)
    return getuid is None or path.stat().st_uid == getuid()


def _alive(pid: int) -> bool:
    """Whether process `pid` may still run. Where that cannot be told, it may."""
    if pid <= 0 or sys.platform == "win32":
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True
