"""The live release as the explorer sees it: which folder it is, its explorer database
(opened read only) and the queries the pages run. The one place that reads where the live
release is; SQL and the licensed MedDRA part ask it too.

`release_dir` is a release folder, or a pointer: a small file naming a release folder
beside it, which `point_live` repoints in one rename. A pointer is read again on every
request, so a rebuild or a publish switches the explorer without a restart, and without
replacing a file the explorer holds open, which Windows does not allow. A symbolic link to a
release folder works too.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import weakref
from pathlib import Path
from typing import Any

import duckdb

from open_altio import rulebook
from open_altio.faers import EXPLORER_FILE, MANIFEST_FILE, read_manifest
from open_altio.faers.reader import quoted

MEMORY_RULE = "explorer-read-memory"


def read_connection(owner: object) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB held to the explorer's memory limit (rule explorer-read-memory),
    spilling past it to a folder of its own, which goes when `owner` is closed or collected."""
    spill = Path(tempfile.mkdtemp(prefix="open-altio-explorer-"))
    weakref.finalize(owner, shutil.rmtree, spill, True)
    return duckdb.connect(
        config={
            "memory_limit": f"{rulebook.value(MEMORY_RULE, 'memory_limit_gb')}GB",
            "temp_directory": str(spill),
        }
    )


class NotLive(Exception):
    """There is no release the explorer can query; the message says why in plain words."""


class OpenRelease:
    """One release's explorer database, open read only and held to the explorer's memory
    limit (rule explorer-read-memory). Thread-safe: every query runs on its own cursor.

    The file is attached to a DuckDB of its own rather than opened by its path, which DuckDB
    would answer with any database it still holds open there: a file replaced in place (MedDRA
    added to a built release recounts its statistics) is then read anew."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.manifest = read_manifest(folder)
        self.name: str = self.manifest["release"]
        # the person's own rules it was built with, under which its pages are read (app.py)
        self.user_rules = rulebook.from_differences(self.manifest.get("user_rules") or {})
        self._con = read_connection(self)
        self._con.execute(f"ATTACH {quoted(str(folder / EXPLORER_FILE))} AS explorer (READ_ONLY)")

    def close(self) -> None:
        self._con.close()

    def cursor(self) -> duckdb.DuckDBPyConnection:
        """A cursor of its own on the read-only database; the caller closes it."""
        cur = self._con.cursor()
        cur.execute("USE explorer")
        return cur

    def rows(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """The query's rows, each as a dict of its columns."""
        cur = self.cursor()
        try:
            cur.execute(sql, params or [])
            names = [d[0] for d in cur.description]
            return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]
        finally:
            cur.close()


def live_folder(release_dir: Path) -> Path:
    """The release folder `release_dir` names: itself, or the folder its pointer file names."""
    if release_dir.is_file():
        return (release_dir.parent / release_dir.read_text(encoding="utf-8").strip()).resolve()
    return release_dir.resolve()


def point_live(pointer: Path, folder: Path) -> None:
    """Point `pointer` at `folder`, a release folder beside it, in one rename, so a request
    opens either the old release or the new one, never neither."""
    staged = pointer.with_name(f".{pointer.name}.{os.getpid()}.tmp")
    staged.write_text(folder.name + "\n", encoding="utf-8")
    os.replace(staged, pointer)


class LiveRelease:
    """Finds the live release folder on each request and keeps its database open until the
    folder or the database changes."""

    def __init__(self, release_dir: str | Path | None) -> None:
        self.release_dir = Path(release_dir) if release_dir else None
        self._lock = threading.Lock()
        self._open: OpenRelease | None = None
        self._key: tuple | None = None

    def folder(self) -> Path:
        """The live release folder, or NotLive when there is none."""
        if self.release_dir is None:
            raise NotLive("No release is live yet.")
        folder = live_folder(self.release_dir)
        if not (folder / MANIFEST_FILE).is_file():
            raise NotLive("No release is live yet.")
        return folder

    def current(self) -> OpenRelease:
        folder = self.folder()
        if not (folder / EXPLORER_FILE).is_file():
            raise NotLive("The live release has no explorer database yet.")
        stat, listed = (folder / EXPLORER_FILE).stat(), (folder / MANIFEST_FILE).stat()
        key = (folder, stat.st_ino, stat.st_mtime_ns, listed.st_ino, listed.st_mtime_ns)
        with self._lock:
            # A new folder, the file rebuilt in place, or a manifest written anew (the labels
            # brought up to date: rule label-refresh): open it. The old
            # connection is left to the garbage collector, so a request still
            # using it finishes.
            if self._open is None or self._key != key:
                self._open, self._key = OpenRelease(folder), key
            return self._open

    def user_rules(self) -> rulebook.UserRules:
        """The rules the live release was built with; Altio's standard while none is live."""
        try:
            return self.current().user_rules
        except NotLive:
            return rulebook.UserRules()

    def name(self) -> str | None:
        """The live release's name, or None while there is none the explorer can query."""
        try:
            return self.current().name
        except NotLive:
            return None


__all__ = [
    "LiveRelease",
    "NotLive",
    "OpenRelease",
    "live_folder",
    "point_live",
    "read_connection",
]
