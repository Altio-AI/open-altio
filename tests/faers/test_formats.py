"""Each JSON document of a release names its format; a release built under the earlier names
still opens, read under today's."""

from __future__ import annotations

import json
import shutil

import pytest

from open_altio.faers import formats, read_manifest
from open_altio.faers.insights.methods import validate
from open_altio.faers.meddra import read_licensed_manifest


def _earlier(name: str) -> str:
    return next(old for old, new in formats.EARLIER.items() if new == name)


def test_every_earlier_name_reads_as_one_of_todays():
    assert set(formats.EARLIER.values()) == {
        formats.RELEASE,
        formats.LICENSED,
        formats.METHODS,
        formats.RELEASES,
    }
    for old, new in formats.EARLIER.items():
        assert formats.with_current_name({"format": old, "release": "2026Q2"}) == {
            "format": new,
            "release": "2026Q2",
        }
    assert formats.with_current_name({"format": "csv"}) == {"format": "csv"}


def test_a_new_release_names_its_documents_by_todays_formats(rel, release, licensed_release):
    assert rel.manifest["format"] == formats.RELEASE
    assert (
        json.loads((release / "methods.json").read_text(encoding="utf-8"))["format"]
        == formats.METHODS
    )
    assert read_licensed_manifest(licensed_release)["format"] == formats.LICENSED


@pytest.fixture
def earlier_release(licensed_release, tmp_path):
    """A copy of the fake release whose documents carry the earlier format names."""
    copy = tmp_path / licensed_release.name
    shutil.copytree(licensed_release, copy)
    for path, name in [
        (copy / "manifest.json", formats.RELEASE),
        (copy / "methods.json", formats.METHODS),
        (copy / "licensed" / "manifest.json", formats.LICENSED),
    ]:
        doc = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**doc, "format": _earlier(name)}), encoding="utf-8")
    return copy


def test_a_release_built_under_the_earlier_names_still_reads(earlier_release):
    assert read_manifest(earlier_release)["format"] == formats.RELEASE
    assert read_licensed_manifest(earlier_release)["format"] == formats.LICENSED
    methods = json.loads((earlier_release / "methods.json").read_text(encoding="utf-8"))
    assert validate(methods) == []
