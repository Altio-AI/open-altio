"""open-altio demo, fetch and build, against FDA's download server faked on this machine."""

from __future__ import annotations

from datetime import date

import pytest

from open_altio import cli, rulebook
from open_altio.cli import data
from open_altio.explorer.context import explorer_of
from open_altio.faers import read_manifest
from open_altio.faers.drugnames import dictionary
from open_altio.faers.fda import quarters_until, zip_name
from open_altio.testing import fakefda
from open_altio.testing.rules import rules_with

LATEST = "2026q2"  # the newest fake quarter


@pytest.fixture
def today(monkeypatch):
    """A day on which FDA's newest quarter is the fakes' newest."""

    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 17)

    monkeypatch.setattr(data, "date", Today)


@pytest.fixture
def published(fake_fda, tmp_path_factory, today):
    """FDA's server holding the fake 2026Q2 quarter."""
    folder = fakefda.write_input(tmp_path_factory.mktemp("fda"), quarters=(LATEST,))
    fake_fda.files[zip_name(LATEST)] = (folder / zip_name(LATEST)).read_bytes()
    return fake_fda


def test_demo_downloads_the_latest_quarter_builds_it_and_serves_it(published, served, home, capsys):
    assert cli.main(["demo", "--no-open", "--port", "8767"]) == 0
    out = capsys.readouterr().out
    release = home / "releases" / "2026Q2"
    assert read_manifest(release)["quarters"] == [LATEST]
    assert (home / "fda" / zip_name(LATEST)).is_file()
    assert "FDA's latest quarter is 2026Q2" in out
    assert "[1/5] Reading FDA's files for 2026Q2" in out
    assert "Built 2026Q2 in " in out and f"cases in {release}" in out
    assert explorer_of(served["app"]).release.current().folder == release.resolve()
    assert served["port"] == 8767 and "opened" not in served


def test_demo_reads_drug_names_through_diana_s_dictionary(published, served, home, diana):
    assert cli.main(["demo", "--no-open"]) == 0
    assert (home / "reference" / diana.name).read_bytes() == diana.read_bytes()
    assert read_manifest(home / "releases" / "2026Q2")["drug_names"]["tables"]


def test_demo_without_diana_s_dictionary_is_built_without_ingredients_and_says_so(
    published, served, home, tmp_path, capsys
):
    with rules_with(tmp_path / "other", {dictionary.RULE: {"sha256": "0" * 64}}):
        assert cli.main(["demo", "--no-open"]) == 0
    assert "The demo is built without drug ingredients" in capsys.readouterr().out
    assert "tables" not in read_manifest(home / "releases" / "2026Q2")["drug_names"]


def test_demo_again_opens_the_same_release_without_fetching_or_building(published, served, capsys):
    assert cli.main(["demo", "--no-open"]) == 0
    capsys.readouterr()
    assert cli.main(["demo", "--no-open"]) == 0
    out = capsys.readouterr().out
    assert "its file is here already" in out
    assert "is built already" in out and "Building" not in out
    assert len(published.downloads_of(zip_name(LATEST))) == 1


def test_demo_builds_only_the_latest_quarter_when_every_quarter_is_here(
    published, served, home, fake_input
):
    for zipped in fake_input.glob("*.zip"):
        (home / "fda").mkdir(parents=True, exist_ok=True)
        (home / "fda" / zipped.name).write_bytes(zipped.read_bytes())
    assert cli.main(["demo", "--no-open"]) == 0
    assert read_manifest(home / "releases" / "2026Q2")["quarters"] == [LATEST]


def test_demo_with_fda_out_of_reach_uses_a_quarter_downloaded_before(
    published, served, home, monkeypatch, capsys
):
    assert cli.main(["demo", "--no-open"]) == 0
    monkeypatch.setattr("open_altio.faers.fda.EXPORTS", "http://127.0.0.1:9/")  # nothing listens
    assert cli.main(["demo", "--no-open"]) == 0
    assert (
        "Could not reach FDA, so the demo uses 2026Q2, downloaded before" in capsys.readouterr().out
    )


def test_demo_with_fda_out_of_reach_and_nothing_here_says_what_to_check(today, monkeypatch, capsys):
    monkeypatch.setattr("open_altio.faers.fda.EXPORTS", "http://127.0.0.1:9/")
    assert cli.main(["demo", "--no-open"]) == 2
    assert "Could not reach FDA" in capsys.readouterr().err


def test_fetch_downloads_every_quarter_and_carries_on_where_it_stopped(
    fake_fda, today, home, capsys
):
    fake_fda.publish_until(LATEST)
    every = quarters_until(LATEST)
    (home / "fda").mkdir(parents=True)
    (home / "fda" / zip_name(every[0])).write_bytes(fake_fda.files[zip_name(every[0])])
    assert cli.main(["fetch"]) == 0
    out = capsys.readouterr().out
    assert f"FDA has published {len(every)} quarters, 2004Q1 to 2026Q2. Here already: 1, in " in out
    assert sorted(p.name for p in (home / "fda").iterdir()) == sorted(map(zip_name, every))
    assert fake_fda.downloads_of(zip_name(every[0])) == []
    assert cli.main(["fetch"]) == 0
    assert sum(len(fake_fda.downloads_of(zip_name(q))) for q in every) == len(every) - 1


def test_fetch_brings_diana_s_dictionary_and_says_whose_it_is(fake_fda, today, home, diana, capsys):
    fake_fda.publish_until(LATEST)
    assert cli.main(["fetch"]) == 0
    assert "DiAna's drug dictionary (University of Bologna, CC BY 4.0" in capsys.readouterr().out
    assert (home / "reference" / diana.name).read_bytes() == diana.read_bytes()
    assert cli.main(["fetch"]) == 0
    assert "DiAna's drug dictionary is here already" in capsys.readouterr().out


def test_fetch_keeps_no_dictionary_whose_checksum_is_not_the_rule_s(
    fake_fda, today, home, tmp_path, capsys
):
    fake_fda.publish_until(LATEST)
    with rules_with(tmp_path / "other", {dictionary.RULE: {"sha256": "0" * 64}}):
        assert cli.main(["fetch"]) == 2
    assert "not the one rule drug-names pins" in capsys.readouterr().err
    assert list((home / "reference").iterdir()) == []


def test_build_writes_the_release_into_the_current_folder(
    fake_input, monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("OPEN_ALTIO_FDA_DIR", str(fake_input))
    assert cli.main(["build"]) == 0
    out = capsys.readouterr().out
    release = tmp_path / "work" / "2026Q2"
    assert len(read_manifest(release)["quarters"]) == len(fakefda.QUARTERS)
    assert f"from {len(fakefda.QUARTERS)} quarters of FDA's files" in out
    assert "with Altio's standard rules" in out
    assert "Explore it with: open-altio serve" in out


def test_build_replaces_what_a_rebuild_in_the_explorer_left_beside_the_release(
    fake_input, left_by_a_rebuild, monkeypatch, tmp_path
):
    monkeypatch.setenv("OPEN_ALTIO_FDA_DIR", str(fake_input))
    here = left_by_a_rebuild(tmp_path / "work")
    assert cli.main(["build"]) == 0
    assert read_manifest(here)["user_rules"]["off"] == []
    assert [p.name for p in (tmp_path / "work").iterdir()] == [here.name]


def test_build_follows_the_rules_toml_in_the_current_folder(
    fake_input, monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("OPEN_ALTIO_FDA_DIR", str(fake_input))
    (tmp_path / "work" / rulebook.FILE_NAME).write_text("[deleted-cases]\non = false\n")
    assert cli.main(["build"]) == 0
    assert "with your rules.toml" in capsys.readouterr().out
    assert read_manifest(tmp_path / "work" / "2026Q2")["user_rules"]["off"] == ["deleted-cases"]


def test_build_refuses_a_rules_file_naming_a_rule_that_does_not_exist(
    fake_input, monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("OPEN_ALTIO_FDA_DIR", str(fake_input))
    (tmp_path / "work" / rulebook.FILE_NAME).write_text("[duplicates]\non = false\n")
    assert cli.main(["build"]) == 2
    assert "There is no data rule called duplicates." in capsys.readouterr().err
    assert not (tmp_path / "work" / "2026Q2").exists()


def test_build_refuses_a_rules_file_that_is_not_toml(fake_input, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPEN_ALTIO_FDA_DIR", str(fake_input))
    (tmp_path / "work" / rulebook.FILE_NAME).write_text("[deleted-cases\n")
    assert cli.main(["build"]) == 2
    assert "rules.toml is not a valid rules file" in capsys.readouterr().err
