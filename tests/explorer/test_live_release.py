"""Where the live release is: a release folder, or a pointer file naming one beside it, read
again on every request, so a rebuild or a publish switches the explorer without a restart and
without replacing a file the explorer holds open."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from open_altio import rulebook
from open_altio.explorer.meddra import ServedMeddra
from open_altio.explorer.release import OpenRelease, live_folder, point_live
from open_altio.faers.meddra import licensed_dir, read_licensed_manifest


def two_releases(tmp_path: Path, release: Path, dup_release: Path) -> tuple[Path, Path, Path]:
    """Copies of two different releases side by side, and where their pointer goes."""
    first, second = tmp_path / "first", tmp_path / "second"
    shutil.copytree(release, first)
    shutil.copytree(dup_release, second)
    return first, second, tmp_path / "live"


def latest_cases(reader) -> int:
    return reader.rows("SELECT count(*) FROM case_latest_T")[0][0]


def cases(client: TestClient) -> int:
    got = client.get("/api/release")
    assert got.status_code == 200, got.text
    return got.json()["all_cases"]


def test_the_explorer_follows_a_pointer_and_its_next_request_sees_it_repointed(
    explorer_app, release, dup_rel, rel, tmp_path
):
    first, second, pointer = two_releases(tmp_path, release, dup_rel.path)
    point_live(pointer, first)
    client = TestClient(explorer_app(pointer))
    assert cases(client) == latest_cases(rel) != latest_cases(dup_rel)

    point_live(pointer, second)
    assert cases(client) == latest_cases(dup_rel)
    sql = client.post("/api/sql", json={"sql": "SELECT count(*) AS n FROM case_latest_T"})
    assert sql.json()["rows"] == [[latest_cases(dup_rel)]]


def test_a_pointer_is_a_small_file_written_whole_and_never_a_link(release, dup_rel, tmp_path):
    first, second, pointer = two_releases(tmp_path, release, dup_rel.path)
    point_live(pointer, first)
    point_live(pointer, second)
    assert pointer.is_file() and not pointer.is_symlink()
    assert pointer.read_text(encoding="utf-8") == "second\n"
    assert live_folder(pointer) == second.resolve()
    # nothing half written
    assert sorted(p.name for p in tmp_path.iterdir()) == ["first", "live", "second"]


@pytest.mark.skipif(sys.platform == "win32", reason="making a link needs extra rights on Windows")
def test_a_release_folder_or_a_link_to_one_is_served_as_it_is(release, tmp_path):
    assert live_folder(release) == release.resolve()
    link = tmp_path / "link"
    link.symlink_to(release, target_is_directory=True)
    assert live_folder(link) == release.resolve()


def test_a_pointer_to_a_folder_with_no_release_answers_that_none_is_live(explorer_app, tmp_path):
    (tmp_path / "empty").mkdir()
    point_live(tmp_path / "live", tmp_path / "empty")
    got = TestClient(explorer_app(tmp_path / "live")).get("/api/release")
    assert got.status_code == 503
    assert got.json()["problem"] == "No release is live yet."


def test_the_release_and_its_meddra_part_are_read_within_the_memory_rule(licensed_release):
    """rules/explorer-read-memory.md: DuckDB's memory limit for the explorer's reads."""
    gb = rulebook.value("explorer-read-memory", "memory_limit_gb")
    same = duckdb.connect(config={"memory_limit": f"{gb}GB"})
    [entry] = read_licensed_manifest(licensed_release)["meddra"]["versions"].values()
    opened = OpenRelease(licensed_release)
    served = ServedMeddra(licensed_dir(licensed_release), entry)
    try:
        limit = "SELECT current_setting('memory_limit')"
        assert opened.cursor().execute(limit).fetchall() == same.execute(limit).fetchall()
        assert served._run(limit) == same.execute(limit).fetchall()
    finally:
        opened.close()
        same.close()


def test_a_manifest_written_anew_is_read_at_the_next_request(
    explorer_app, labelled_release, tmp_path
):
    """A label refresh switches in a new manifest, the day its labels are as of moved on (rule
    label-refresh): the next request reads it, without a restart."""
    copy = tmp_path / "release"
    shutil.copytree(labelled_release, copy)
    client = TestClient(explorer_app(copy))
    before = client.get("/api/release").json()["labels"]["as_of"]
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    manifest["labels"]["as_of"] = "2030-01-31"
    written = copy / ".manifest.json.new"
    written.write_text(json.dumps(manifest), encoding="utf-8")
    os.replace(written, copy / "manifest.json")
    assert client.get("/api/release").json()["labels"]["as_of"] == "2030-01-31" != before
