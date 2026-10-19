"""open-altio serve: the explorer on this machine only, over a release it finds or is given."""

from __future__ import annotations

import shutil
import socket

import pytest

from open_altio import cli, paths
from open_altio.cli import serve
from open_altio.explorer.context import explorer_of
from open_altio.faers.build import Inputs
from open_altio.faers.meddra import read_licensed_manifest
from open_altio.testing.fakemeddra import write_meddra


@pytest.fixture
def copy(release):
    """A release of the test's own, to find or to write into."""

    def make(folder):
        target = folder / release.name
        shutil.copytree(release, target)
        return target

    return make


def test_serve_runs_the_explorer_on_the_loopback_address_only(release, served, capsys):
    assert cli.main(["serve", "--release", str(release), "--port", "8765", "--no-open"]) == 0
    assert (served["host"], served["port"]) == ("127.0.0.1", 8765)
    assert "http://127.0.0.1:8765" in capsys.readouterr().out
    assert explorer_of(served["app"]).release.current().folder == release.resolve()
    assert "opened" not in served


def test_serve_tells_the_explorer_where_fdas_files_are_for_a_rebuild(release, served, home):
    """The rules page's Rebuild reads FDA's files where fetch and demo put them."""
    assert cli.main(["serve", "--release", str(release), "--no-open"]) == 0
    assert served["app"].state.explorer.rebuild.fda_dir == paths.fda_folder()


def test_serve_finds_the_newest_release_in_the_current_folder(copy, served, tmp_path):
    here = copy(tmp_path / "work")
    assert cli.main(["serve", "--no-open"]) == 0
    assert explorer_of(served["app"]).release.current().folder == here.resolve()


def test_serve_puts_the_release_rebuilt_last_time_under_its_own_name(
    left_by_a_rebuild, served, tmp_path
):
    here = left_by_a_rebuild(tmp_path / "work")
    assert cli.main(["serve", "--no-open"]) == 0
    opened = explorer_of(served["app"]).release.current()
    assert opened.folder == here.resolve()
    assert opened.manifest["user_rules"]["off"] == ["deleted-cases"]
    assert [p.name for p in (tmp_path / "work").iterdir()] == [here.name]


def test_serve_falls_back_to_the_demo_release(copy, served, home):
    demo = copy(home / "releases")
    assert cli.main(["serve", "--no-open"]) == 0
    assert explorer_of(served["app"]).release.current().folder == demo.resolve()


def test_serve_with_no_release_anywhere_says_how_to_make_one(served, capsys):
    assert cli.main(["serve"]) == 2
    err = capsys.readouterr().err
    assert "There is no release in " in err and "open-altio demo" in err


def test_serve_refuses_a_folder_that_is_no_release(tmp_path, capsys):
    assert cli.main(["serve", "--release", str(tmp_path)]) == 2
    assert "no manifest.json" in capsys.readouterr().err


def test_serve_says_how_to_build_a_missing_explorer_database(release, tmp_path, capsys):
    copy = tmp_path / release.name
    copy.mkdir()
    (copy / "manifest.json").write_text((release / "manifest.json").read_text())
    assert cli.main(["serve", "--release", str(copy)]) == 2
    assert f"python -m open_altio.faers explorer {copy}" in capsys.readouterr().err


def _taken(port: int) -> socket.socket:
    holder = socket.socket()
    holder.bind((serve.LOOPBACK, port))
    holder.listen()
    return holder


def test_a_taken_default_port_moves_to_the_next_free_one(release, served, monkeypatch):
    with socket.socket() as probe:
        probe.bind((serve.LOOPBACK, 0))
        free = probe.getsockname()[1]
    monkeypatch.setattr(serve, "PORT", free)
    with _taken(free):
        assert cli.main(["serve", "--release", str(release), "--no-open"]) == 0
    assert served["port"] > free


def test_a_taken_port_asked_for_is_refused(release, served, capsys):
    with _taken(0) as holder:
        port = holder.getsockname()[1]
        assert cli.main(["serve", "--release", str(release), "--port", str(port)]) == 2
    assert f"Port {port} is in use" in capsys.readouterr().err


def test_the_container_setting_moves_the_address_it_listens_on(release, served, monkeypatch):
    monkeypatch.setenv("OPEN_ALTIO_HOST", "0.0.0.0")
    assert cli.main(["serve", "--release", str(release), "--port", "8766", "--no-open"]) == 0
    assert served["host"] == "0.0.0.0"


def test_meddra_files_are_added_to_the_release_once(copy, served, tmp_path, capsys):
    mine = copy(tmp_path / "work")
    meddra = write_meddra(tmp_path / "meddra", "29.1")
    assert cli.main(["serve", "--meddra", str(meddra), "--no-open"]) == 0
    assert "29.1" in read_licensed_manifest(mine)["meddra"]["versions"]
    assert served["app"].state.explorer.rebuild.inputs.meddra == meddra  # a rebuild reads it again
    assert cli.main(["serve", "--meddra", str(meddra), "--no-open"]) == 0
    assert "has MedDRA 29.1 already" in capsys.readouterr().out


def test_serve_gives_a_rebuild_the_other_files_the_release_was_built_with(
    release, served, tmp_path
):
    """RxNorm's files, the labels folder and EMA's list, as MedDRA's: the Rules page's rebuild
    reads them again, so the rebuilt release holds the same layers."""
    rxnorm, labels, ime = (tmp_path / "rxnorm", tmp_path / "labels", tmp_path / "ime.xlsx")
    rxnorm.mkdir()
    labels.mkdir()
    ime.touch()
    given = ["--rxnorm", str(rxnorm), "--labels", str(labels), "--ime", str(ime)]
    assert cli.main(["serve", "--release", str(release), *given, "--no-open"]) == 0
    assert served["app"].state.explorer.rebuild.inputs == Inputs(
        rxnorm=rxnorm, labels=labels, ime=ime
    )


def test_serve_refuses_a_file_that_is_not_there(release, served, tmp_path, capsys):
    gone = tmp_path / "labels"
    assert cli.main(["serve", "--release", str(release), "--labels", str(gone)]) == 2
    assert f"{gone} is not there." in capsys.readouterr().err
    assert "app" not in served


def test_the_browser_opens_once_the_explorer_answers(monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)

    class Up:
        started = True

    serve._open_when_up(Up(), "http://127.0.0.1:8000")
    assert opened == ["http://127.0.0.1:8000"]
