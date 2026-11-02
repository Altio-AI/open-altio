"""Scratch folders: a killed process's folder is cleared by the next one made, nothing else is."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from open_altio import scratch

PREFIX = "open-altio-test-"


def dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def folder(parent, name, age_days=0):
    path = parent / name
    path.mkdir()
    (path / "spill.tmp").write_bytes(b"x")
    if age_days:
        then = time.time() - age_days * 86400
        os.utime(path, (then, then))
    return path


def test_a_dead_process_folder_is_cleared_where_that_can_be_told(tmp_path):
    gone = folder(tmp_path, f"{PREFIX}{dead_pid()}-abc123_x")
    scratch.make(PREFIX, tmp_path)
    # on Windows a process's end cannot be told (scratch._alive), so its folder is kept
    assert gone.exists() == (sys.platform == "win32")


def test_a_live_process_folder_is_kept(tmp_path):
    live = folder(tmp_path, f"{PREFIX}{os.getpid()}-abc123_x")
    scratch.make(PREFIX, tmp_path)
    assert live.exists()


def test_an_unrecognized_name_is_kept(tmp_path):
    other = [
        folder(tmp_path, f"{PREFIX}{dead_pid()}"),
        folder(tmp_path, f"{PREFIX}notapid-abc123"),
        folder(tmp_path, f"{PREFIX}{dead_pid()}-abc.d"),
        folder(tmp_path, f"{PREFIX}download-{dead_pid()}-abc123", age_days=30),
        folder(tmp_path, f"other-prefix-{dead_pid()}-abc123"),
    ]
    scratch.make(PREFIX, tmp_path)
    assert all(p.exists() for p in other)


def test_an_old_folder_without_a_pid_is_cleared_and_a_new_one_kept(tmp_path):
    old = folder(tmp_path, f"{PREFIX}ab12cd_9", age_days=2)
    new = folder(tmp_path, f"{PREFIX}zz99yy_8")
    scratch.make(PREFIX, tmp_path)
    assert not old.exists()
    assert new.exists()


def test_a_file_with_a_dead_name_is_kept(tmp_path):
    file = tmp_path / f"{PREFIX}{dead_pid()}-abc123"
    file.write_text("x")
    scratch.make(PREFIX, tmp_path)
    assert file.exists()


def test_the_new_folder_carries_this_pid_and_survives_the_next(tmp_path):
    first = scratch.make(PREFIX, tmp_path)
    assert first.name.startswith(f"{PREFIX}{os.getpid()}-")
    scratch.make(PREFIX, tmp_path)
    assert first.exists()
