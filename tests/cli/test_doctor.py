"""open-altio doctor: each check says what it found, and what falls short says how to fix it."""

from __future__ import annotations

import json
import shutil
from collections import namedtuple

import pytest

from open_altio import cli, rulebook
from open_altio.cli import console, doctor
from open_altio.testing.fakemeddra import as_an_older_version_wrote_it

GB = 2**30
Usage = namedtuple("Usage", "total used free")


@pytest.fixture
def machine(monkeypatch, fake_fda):
    """A machine with what the rule asks for and a reachable FDA; tests take some away."""
    fake_fda.files["aers_ascii_2004q1.zip"] = b"PK"
    monkeypatch.setattr(doctor, "total_memory_bytes", lambda: 64 * GB)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(0, 0, 500 * 10**9))
    monkeypatch.setattr(doctor, "_newest_on_pypi", lambda: None)
    return monkeypatch


def lines(capsys) -> list[str]:
    return [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]


def test_a_machine_with_what_open_altio_needs_is_all_good(machine, capsys):
    assert cli.main(["doctor"]) == 0
    out = lines(capsys)
    assert out[-1] == "All good."
    assert not [line for line in out if line.startswith("fix")]
    assert any(line.startswith("ok    Python 3.") for line in out)


def test_too_little_memory_for_the_demo_says_how_much_is_needed(machine, capsys):
    machine.setattr(doctor, "total_memory_bytes", lambda: 1 * GB)
    assert cli.main(["doctor"]) == 1
    out = lines(capsys)
    need = rulebook.value("machine-needs", "demo_memory_gb")
    assert any(line.startswith("fix") and f"needs about {need} GB" in line for line in out)
    assert "1 thing to fix, above." in out
    assert "To report it later: open-altio report" in out


def test_memory_for_the_demo_but_not_every_quarter_is_worth_knowing(machine, capsys):
    build = rulebook.value("machine-needs", "build_memory_gb")
    machine.setattr(doctor, "total_memory_bytes", lambda: (build - 1) * GB)
    assert cli.main(["doctor"]) == 0
    assert any(line.startswith("note  Memory:") for line in lines(capsys))


def test_too_little_disk_says_where_to_move_the_data_folder(machine, capsys):
    machine.setattr(shutil, "disk_usage", lambda path: Usage(0, 0, 10**8))
    assert cli.main(["doctor"]) == 1
    assert any(
        line.startswith("fix   Free disk") and "OPEN_ALTIO_DATA_DIR" in line
        for line in lines(capsys)
    )


def test_fda_out_of_reach_is_to_fix(machine, capsys):
    machine.setattr("open_altio.faers.fda.EXPORTS", "http://127.0.0.1:9/")
    assert cli.main(["doctor"]) == 1
    assert any(line.startswith("fix   Could not reach FDA") for line in lines(capsys))


def test_a_stopped_download_and_an_older_release_are_noted(machine, home, release, capsys):
    (home / "fda").mkdir(parents=True)
    (home / "fda" / "faers_ascii_2026q2.zip.part").write_bytes(b"PK")
    old = home / "releases" / release.name
    shutil.copytree(release, old)
    manifest = json.loads((old / "manifest.json").read_text())
    (old / "manifest.json").write_text(json.dumps({**manifest, "code_version": "0.9.0"}))
    assert cli.main(["doctor"]) == 0
    out = lines(capsys)
    assert any("download stopped part way" in line for line in out)
    assert any(
        line.startswith("note  Release 2026Q2") and "open-altio 0.9.0" in line for line in out
    )


def test_a_meddra_part_an_older_version_added_says_how_to_add_it(
    machine, home, licensed_release, capsys
):
    older = home / "releases" / licensed_release.name
    shutil.copytree(licensed_release, older)
    as_an_older_version_wrote_it(older)
    assert cli.main(["doctor"]) == 0
    [said] = [line for line in lines(capsys) if "MedDRA 29.1" in line]
    assert said.startswith(f"note  Release in {older}: MedDRA 29.1 was added to this release by")
    assert "open-altio serve --meddra <folder>" in said


def test_a_release_without_its_explorer_database_is_to_fix(machine, release, tmp_path, capsys):
    broken = tmp_path / "work" / release.name
    broken.mkdir()
    shutil.copy(release / "manifest.json", broken / "manifest.json")
    assert cli.main(["doctor"]) == 1
    assert any(
        line.startswith("fix   Release 2026Q2") and "no explorer.duckdb" in line
        for line in lines(capsys)
    )


def test_no_drug_dictionary_yet_is_worth_knowing(machine, capsys):
    assert cli.main(["doctor"]) == 0
    assert any(
        line.startswith("note  DiAna's drug dictionary: not downloaded yet")
        and "open-altio fetch" in line
        for line in lines(capsys)
    )


def test_the_drug_dictionary_the_rule_names_is_ok(machine, home, diana, capsys):
    (home / "reference").mkdir(parents=True)
    shutil.copy(diana, home / "reference" / diana.name)
    assert cli.main(["doctor"]) == 0
    assert any(line.startswith("ok    DiAna's drug dictionary, in") for line in lines(capsys))


def test_another_drug_dictionary_is_to_fix(machine, home, capsys):
    (home / "reference").mkdir(parents=True)
    (home / "reference" / "DiAna_dictionary.csv").write_text("drugname;Substance\n")
    assert cli.main(["doctor"]) == 1
    assert any(
        line.startswith("fix   DiAna's drug dictionary in") and "so a build stops" in line
        for line in lines(capsys)
    )


def test_a_newer_open_altio_on_pypi_says_how_to_upgrade(machine, capsys):
    machine.setattr(doctor, "_newest_on_pypi", lambda: "99.0.0")
    assert cli.main(["doctor"]) == 0
    assert any(
        "open-altio 99.0.0 is out" in line and "uv tool upgrade open-altio" in line
        for line in lines(capsys)
    )


def test_something_to_fix_asks_to_report_it(machine, capsys):
    machine.setattr(doctor, "total_memory_bytes", lambda: 1 * GB)
    machine.setattr(console, "ask", lambda question: True)
    opened = []
    machine.setattr("webbrowser.open", opened.append)
    assert cli.main(["doctor"]) == 1
    assert len(opened) == 1 and "open-altio+doctor" in opened[0]


def test_pypi_out_of_reach_is_only_worth_knowing(machine, capsys):
    def unreachable():
        raise OSError("no route to host")

    machine.setattr(doctor, "_newest_on_pypi", unreachable)
    assert cli.main(["doctor"]) == 0
    assert "note  Could not reach PyPI to see if a newer open-altio is out." in lines(capsys)
