"""Where Open Altio keeps its files: the platform's own data folder, unless a setting moves it."""

from __future__ import annotations

from pathlib import Path

import pytest

from open_altio import paths


@pytest.fixture(autouse=True)
def no_settings(monkeypatch):
    for name in (paths.DATA_ENV, paths.FDA_ENV, "XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("darwin", Path.home() / "Library" / "Application Support" / "open-altio"),
        ("linux", Path.home() / ".local" / "share" / "open-altio"),
        ("win32", Path.home() / "AppData" / "Local" / "open-altio"),
    ],
)
def test_each_platform_keeps_the_data_in_its_own_place(platform, expected, monkeypatch):
    monkeypatch.setattr("sys.platform", platform)
    assert paths.data_folder() == expected
    assert "Documents" not in paths.data_folder().parts
    assert paths.fda_folder() == expected / "fda"
    assert paths.releases_folder() == expected / "releases"


def test_the_platform_s_own_setting_is_followed(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert paths.data_folder() == tmp_path / "open-altio"
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert paths.data_folder() == tmp_path / "Local" / "open-altio"


def test_settings_move_the_whole_folder_or_only_fda_s_files(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path / "oa"))
    assert paths.releases_folder() == tmp_path / "oa" / "releases"
    monkeypatch.setenv(paths.FDA_ENV, str(tmp_path / "zips"))
    assert paths.fda_folder() == tmp_path / "zips"
    assert paths.releases_folder() == tmp_path / "oa" / "releases"
