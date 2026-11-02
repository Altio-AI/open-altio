"""The release folder in the contract: a release names its source and a format this version
reads, and every reader refuses any other folder, naming it, so no question is answered over an
unfinished or unknown folder."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_altio.explorer.access import LOCAL
from open_altio.explorer.questions import PUBLISHED, open_release_data
from open_altio.explorer.release import OpenRelease
from open_altio.explorer.sql import SqlDatabase
from open_altio.faers import FORMAT_VERSION, NotARelease, formats, open_release, read_manifest
from open_altio.testing.contract import answered

CHANGED = {
    "no-manifest": None,
    "newer-format": {"format_version": 99},
    "vaers": {"source": "vaers"},
}
NOT_LIVE = "No release is live yet."


@pytest.fixture(scope="module")
def not_releases(release, tmp_path_factory) -> dict[str, Path]:
    """Copies of the invented release: its manifest removed, naming a format version this
    version does not read, and naming another source."""
    made = {}
    for name, change in CHANGED.items():
        copy = tmp_path_factory.mktemp("not-a-release") / name
        shutil.copytree(release, copy)
        manifest = copy / "manifest.json"
        if change is None:
            manifest.unlink()
        else:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
            manifest.write_text(json.dumps(doc | change), encoding="utf-8")
        made[name] = copy
    return made


def test_a_release_names_its_source_and_a_format_this_version_reads(release):
    manifest = read_manifest(release)
    assert manifest["source"] in formats.SOURCES
    assert manifest["format_version"] == FORMAT_VERSION
    assert FORMAT_VERSION in formats.READABLE_VERSIONS


@pytest.mark.parametrize("name", CHANGED)
def test_every_reader_refuses_a_folder_that_is_not_a_release_naming_it(name, not_releases):
    folder = not_releases[name]
    for read in (
        read_manifest,
        OpenRelease,
        open_release,
        SqlDatabase,
        lambda f: open_release_data(f, LOCAL),
    ):
        with pytest.raises(NotARelease, match=f"^{name} is not a release"):
            read(folder)


@pytest.mark.parametrize("name", CHANGED)
def test_no_published_question_is_answered_over_a_folder_that_is_not_a_release(
    name, not_releases, contract_app
):
    """Each answers a problem, never a count. A folder whose manifest is gone is, to the
    explorer, a folder with no release in it; the others are named."""
    web = TestClient(contract_app(not_releases[name]))
    for route in PUBLISHED:
        if route == "GET /api/me":  # who is asking, which no release answers
            continue
        got = answered(web, route)
        assert got.status_code == 503, route
        said = got.json()["problem"]
        expected = NOT_LIVE if CHANGED[name] is None else f"{name} is not a release"
        assert said.startswith(expected), (route, said)
