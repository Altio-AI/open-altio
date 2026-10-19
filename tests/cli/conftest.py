"""What the command's tests share: its data folder in a temporary place, DiAna's download
faked, a server that records what it would serve instead of serving it, and a folder as a
rebuild leaves it."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import uvicorn

from open_altio.explorer.rebuild import POINTER, REBUILT
from open_altio.explorer.release import point_live
from open_altio.faers.drugnames import dictionary
from open_altio.testing import fakediana
from open_altio.testing.rules import rules_with


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Open Altio's data folder, empty, and a current folder of the test's own."""
    folder = tmp_path / "home"
    monkeypatch.setenv("OPEN_ALTIO_DATA_DIR", str(folder))
    monkeypatch.delenv("OPEN_ALTIO_FDA_DIR", raising=False)
    monkeypatch.delenv("OPEN_ALTIO_HOST", raising=False)
    monkeypatch.delenv(dictionary.DIANA_ENV, raising=False)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return folder


@pytest.fixture(autouse=True)
def diana(tmp_path):
    """DiAna's dictionary at its download address, faked: the invented one as a local file,
    whose checksum the rule pins, so no test reaches OSF. Returns that file."""
    source = fakediana.write_dictionary(tmp_path / "osf" / "DiAna_dictionary.csv")
    pins = {"download": source.as_uri(), "sha256": dictionary.sha256(source)}
    with rules_with(tmp_path / "diana-rules", {dictionary.RULE: pins}):
        yield source


@pytest.fixture
def served(monkeypatch) -> dict:
    """The explorer the command would run: its app, host and port, and no browser opened."""
    ran: dict = {}

    def run(server: uvicorn.Server) -> None:
        ran.update(app=server.config.app, host=server.config.host, port=server.config.port)

    monkeypatch.setattr(uvicorn.Server, "run", run)
    monkeypatch.setattr("webbrowser.open", lambda url: ran.setdefault("opened", url))
    return ran


@pytest.fixture
def left_by_a_rebuild(release):
    """A folder as the explorer's Rebuild leaves it: the release, the copy rebuilt beside it
    with deleted-cases off, and the pointer naming that copy. Returns the release's folder."""

    def make(folder: Path) -> Path:
        named = folder / release.name
        shutil.copytree(release, named)
        rebuilt = folder / REBUILT.format(release=release.name)
        shutil.copytree(release, rebuilt)
        manifest = rebuilt / "manifest.json"
        recorded = {"user_rules": {"off": ["deleted-cases"], "changed": []}}
        manifest.write_text(json.dumps(json.loads(manifest.read_text()) | recorded))
        point_live(folder / POINTER.format(release=release.name), rebuilt)
        return named

    return make
