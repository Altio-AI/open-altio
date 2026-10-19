"""Pytest fixtures for the fake release. A conftest takes them with
`from open_altio.testing.fixtures import *`.

    fake_input        the fake FDA quarters as zips, once per session
    fake_diana        the invented DiAna dictionary (fakediana), once per session
    release           the release folder built from them once per session (read only), with
                      the drug-name step read through the invented dictionary
    rel               that release opened through its files
    dup_rel           a second fake release, built from fakefda.DUP_STORY: the duplicate rules
    demo_rel          a fake release of fakefda.DEMOGRAPHICS_STORY: sex, age, weight and country
    licensed_release  the fake release built again with the invented MedDRA 29.1, its one version
    classes_release   a copy of `release` with the invented drug classes layer (fakeclasses)
    bare_release      a copy of `release` built without the drug classes layer
    labelled_release  a copy of `licensed_release` with invented label flags (fakelabelflags.py)
    stats_release     a release of fakestats.STORY alone, enough cases for EBGM's prior to fit
    seizure_release   a release of fakefda.SEIZURE_STORY alone with the invented MedDRA 29.1:
                      FDA's Convulsion and Seizure, one PT by today's MedDRA
    fake_fda          FDA's download server, faked on 127.0.0.1, with open_altio.faers.fda pointed
                      at it
    chromium          Playwright's headless Chromium, once per session; skipped where it is missing,
                      unless OPEN_ALTIO_REQUIRE_BROWSER is set, as CI sets it
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from open_altio.faers import build_release, fda
from open_altio.testing import fakediana, fakefda, fakestats
from open_altio.testing.fakeclasses import add_classes, remove_classes
from open_altio.testing.fakelabelflags import add_label_flags
from open_altio.testing.fakemeddra import write_meddra
from open_altio.testing.fdaserver import FakeFda
from open_altio.testing.releasereader import ReleaseReader

__all__ = [
    "bare_release",
    "chromium",
    "classes_release",
    "demo_rel",
    "dup_rel",
    "fake_diana",
    "fake_fda",
    "fake_input",
    "labelled_release",
    "licensed_release",
    "rel",
    "release",
    "seizure_release",
    "stats_release",
]

REQUIRE_BROWSER = "OPEN_ALTIO_REQUIRE_BROWSER"


@pytest.fixture(scope="session")
def fake_input(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The fake quarters as FDA zips, the way a folder of FDA's downloads holds them."""
    return fakefda.write_input(tmp_path_factory.mktemp("zips"))


@pytest.fixture(scope="session")
def fake_diana(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The invented DiAna dictionary, in DiAna's file format."""
    return fakediana.write_dictionary(tmp_path_factory.mktemp("diana") / "DiAna_dictionary.csv")


@pytest.fixture(scope="session")
def release(fake_input: Path, fake_diana: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The release folder built once from the fake zips, the drug names read through the
    invented dictionary, whose checksum the rule pins for this build. Shared: never write
    into it."""
    folder = tmp_path_factory.mktemp("releases")
    with fakediana.pinned(fake_diana, folder):
        return build_release(fake_input, folder, diana_dictionary=fake_diana)


@pytest.fixture(scope="session")
def rel(release: Path) -> ReleaseReader:
    """The release opened through its Parquet and JSON files."""
    return ReleaseReader(release)


@pytest.fixture(scope="session")
def dup_rel(tmp_path_factory: pytest.TempPathFactory) -> ReleaseReader:
    """A release built from fakefda.DUP_STORY alone (two FAERS quarters), opened
    through its files. Kept apart so the main fake release stays one page."""
    zips = fakefda.write_input(
        tmp_path_factory.mktemp("dup_zips"), quarters=fakefda.DUP_QUARTERS, story=fakefda.DUP_STORY
    )
    return ReleaseReader(build_release(zips, tmp_path_factory.mktemp("dup_releases")))


@pytest.fixture(scope="session")
def demo_rel(tmp_path_factory: pytest.TempPathFactory) -> ReleaseReader:
    """A release built from fakefda.DEMOGRAPHICS_STORY alone (two FAERS quarters), opened
    through its files."""
    zips = fakefda.write_input(
        tmp_path_factory.mktemp("demographics_zips"),
        quarters=fakefda.DUP_QUARTERS,
        story=fakefda.DEMOGRAPHICS_STORY,
    )
    return ReleaseReader(build_release(zips, tmp_path_factory.mktemp("demographics")))


@pytest.fixture(scope="session")
def stats_release(fake_diana: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A release built from fakestats.STORY alone, its drug names read through the invented
    dictionary. Kept apart so the main fake release stays one page."""
    zips = fakestats.write_input(tmp_path_factory.mktemp("stats_zips"))
    folder = tmp_path_factory.mktemp("stats_releases")
    with fakediana.pinned(fake_diana, folder):
        return build_release(zips, folder, diana_dictionary=fake_diana)


@pytest.fixture(scope="session")
def seizure_release(fake_diana: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A release built from fakefda.SEIZURE_STORY alone (two FAERS quarters) with the invented
    MedDRA 29.1, where FDA's Convulsion is a lower level term of the PT Seizure. Shared: never
    write into it."""
    zips = fakefda.write_input(
        tmp_path_factory.mktemp("seizure_zips"),
        quarters=fakefda.DUP_QUARTERS,
        story=fakefda.SEIZURE_STORY,
    )
    meddra = write_meddra(tmp_path_factory.mktemp("seizure_meddra") / "29.1", "29.1")
    folder = tmp_path_factory.mktemp("seizure_releases")
    with fakediana.pinned(fake_diana, folder):
        return build_release(zips, folder, diana_dictionary=fake_diana, meddra_dir=meddra)


@pytest.fixture(scope="session")
def licensed_release(
    fake_input: Path, fake_diana: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """The fake release built again, as a host builds one, with the invented MedDRA 29.1
    (released 1 September 2026) given to the build: its licensed part holds that one version
    (rule meddra-version). Shared: never write into it."""
    meddra = write_meddra(tmp_path_factory.mktemp("meddra") / "29.1", "29.1")
    folder = tmp_path_factory.mktemp("licensed")
    with fakediana.pinned(fake_diana, folder):
        return build_release(fake_input, folder, diana_dictionary=fake_diana, meddra_dir=meddra)


@pytest.fixture(scope="session")
def classes_release(release: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the session release carrying the invented drug classes layer
    (open_altio.testing.fakeclasses), its explorer database rebuilt with them."""
    copy = tmp_path_factory.mktemp("classes") / release.name
    shutil.copytree(release, copy)
    add_classes(copy)
    return copy


@pytest.fixture(scope="session")
def bare_release(release: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the session release as one built without the drug classes layer."""
    copy = tmp_path_factory.mktemp("bare") / release.name
    shutil.copytree(release, copy)
    remove_classes(copy)
    return copy


@pytest.fixture(scope="session")
def labelled_release(licensed_release: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the licensed release with the invented label flags and the tables they are
    read through. The shared releases are never written into."""
    copy = tmp_path_factory.mktemp("labelled") / licensed_release.name
    shutil.copytree(licensed_release, copy)
    return add_label_flags(copy)


@pytest.fixture
def fake_fda(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeFda]:
    """FDA's download server, faked, with nothing published until a test adds files."""
    server = FakeFda()
    monkeypatch.setattr(fda, "EXPORTS", server.url)
    monkeypatch.setattr(fda, "RETRY_WAIT_SECONDS", 0)
    yield server
    server.close()


@pytest.fixture(scope="session")
def chromium() -> Iterator[Any]:
    """The browser the page tests open pages in (open_altio.testing.browser.open_page). Skips the
    test where Playwright or its headless shell is not installed; fails it instead where
    OPEN_ALTIO_REQUIRE_BROWSER is set, so CI never passes without having drawn a page."""
    missing = pytest.fail if os.environ.get(REQUIRE_BROWSER) else pytest.skip
    try:
        from playwright import sync_api as sync
    except ImportError:
        missing("Playwright is not installed")
    with sync.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except sync.Error as exc:
            missing(f"no headless Chromium: {str(exc).splitlines()[0]}")
        yield browser
        browser.close()
