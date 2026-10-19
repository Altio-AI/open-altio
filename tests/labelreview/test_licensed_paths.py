"""Nothing licensed is written to a public path: the review writes only into a licensed folder."""

from __future__ import annotations

import subprocess

import pytest

from open_altio import rulebook
from open_altio.labelreview import store
from open_altio.labelreview.__main__ import main
from open_altio.labelreview.store import Folder, PublicPath

ROOT = rulebook.data_root()
WRITTEN = [
    store.BATCHES,
    store.SUGGESTIONS,
    store.DECISIONS,
    store.REDO_SET,
    store.REDO_ANSWERS,
    store.FROZEN,
    store.RULE_CHECK,
    store.UNCERTAIN,
]


def test_a_folder_outside_a_licensed_part_is_refused(tmp_path):
    with pytest.raises(PublicPath, match="licensed"):
        Folder(tmp_path / "mappings")


def test_a_licensed_folder_git_would_publish_is_refused():
    for public in ("mappings", "rules", "src", "docs"):
        with pytest.raises(PublicPath, match="git would publish"):
            Folder(ROOT / public / "licensed" / "meddra")


def test_a_licensed_folder_outside_the_repository_is_accepted(tmp_path):
    assert Folder(tmp_path / "release" / "licensed" / "meddra").path.parts[-2] == "licensed"


def test_no_file_the_review_writes_is_tracked_by_git():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    names = {line.rsplit("/", 1)[-1] for line in tracked.stdout.splitlines()}
    assert not names & set(WRITTEN)


def test_the_command_refuses_a_public_folder_and_writes_nothing(tmp_path, capsys):
    public = tmp_path / "mappings"
    assert main(["batch", "--folder", str(public)]) == 1
    assert "licensed" in capsys.readouterr().err
    assert not public.exists()
