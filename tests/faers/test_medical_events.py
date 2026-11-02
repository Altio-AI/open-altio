"""EMA's designated and important medical event lists (src/open_altio/faers/medical_events.py,
rule medical-event-lists): read from the files a builder gives, written into the release as
medical_events_T with a manifest entry, and, run alone on a built release, adding only that."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from open_altio.faers import read_manifest
from open_altio.faers.__main__ import main
from open_altio.faers.labeldict import read_ime as labels_read_ime
from open_altio.faers.medical_events import (
    TABLE,
    MedicalEventsRefused,
    add_medical_events,
    read_dme,
    read_ime,
    read_ime_terms,
)
from open_altio.testing.fakemedicalevents import DME_TERMS, IME_ROWS, write_dme, write_ime


@pytest.fixture(scope="module")
def files(tmp_path_factory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("lists")
    return {"dme": write_dme(folder / "dme.xlsx"), "ime": write_ime(folder / "ime.xlsx")}


def rows_of(folder: Path) -> list[tuple[str, str]]:
    table = pq.read_table(folder / "parquet" / f"{TABLE}.parquet").to_pydict()
    return list(zip(table["list_T"], table["pt_T"], strict=True))


def files_of(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def test_the_dme_file_gives_its_terms_and_its_date(files):
    names, day = read_dme(files["dme"])
    assert names == DME_TERMS and day == "2020-06-15"


def test_the_ime_file_gives_codes_names_and_version_and_only_from_its_first_sheet(files):
    pairs, version = read_ime_terms(files["ime"])
    assert pairs == IME_ROWS and version == "29.1"
    assert "94000001" not in {code for code, _ in pairs}  # the PT the later sheet dropped


def test_the_labels_step_reads_the_same_ime_codes_that_are_pts_of_its_version(files):
    held = {"94000027", "94000002", "94000001"}
    assert read_ime(files["ime"], held) == {"94000027", "94000002"}
    assert labels_read_ime is read_ime


def test_text_files_hold_one_term_or_code_a_line(tmp_path):
    (tmp_path / "dme.txt").write_text("Seizure\n\nRenal failure\n", encoding="utf-8")
    (tmp_path / "ime.txt").write_text("94000027 94000002\n", encoding="utf-8")
    assert read_dme(tmp_path / "dme.txt") == (["Seizure", "Renal failure"], None)
    assert read_ime_terms(tmp_path / "ime.txt")[0] == [("94000027", None), ("94000002", None)]


def test_a_file_that_is_not_a_list_is_refused_in_plain_words(tmp_path):
    (tmp_path / "other.xlsx").write_text("not a workbook", encoding="utf-8")
    with pytest.raises(MedicalEventsRefused, match="not a workbook EMA publishes"):
        read_dme(tmp_path / "other.xlsx")


def test_built_with_neither_list_the_table_is_empty_and_the_manifest_says_why(release):
    manifest = read_manifest(release)
    assert rows_of(release) == [] and manifest["tables"][TABLE]["rows"] == 0
    entry = manifest["medical_events"]
    assert entry["present"] is False
    for name in ("dme", "ime"):
        assert entry["lists"][name]["present"] is False
        assert name.upper() in entry["lists"][name]["reason"]


def test_built_with_both_lists_and_meddra_the_ime_is_named_as_the_release_names_it(
    listed_release,
):
    entry = read_manifest(listed_release)["medical_events"]
    dme, ime = entry["lists"]["dme"], entry["lists"]["ime"]
    assert dme["present"] and dme["date"] == "2020-06-15" and dme["terms"] == len(DME_TERMS)
    assert len(dme["sha256"]) == 64 and "reason" not in dme
    assert ime["present"] and ime["meddra_version"] == "29.1" and ime["named_by"] == "meddra"
    assert ime["release_meddra_version"] == "29.1" and ime["not_pts_of_release_version"] == 1
    assert rows_of(listed_release) == sorted(
        [("dme", t) for t in DME_TERMS]
        + [("ime", t) for t in ("Nausea", "Renal failure acute", "Seizure")]
    )


@pytest.mark.parametrize(
    ("given", "held", "missing"),
    [("dme", ["dme"], "ime"), ("ime", ["ime"], "dme"), ("both", ["dme", "ime"], None)],
)
def test_run_alone_on_a_release_with_no_meddra_it_marks_by_the_names_the_file_gives(
    given, held, missing, release, files, tmp_path
):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    entry = add_medical_events(
        copy,
        dme=files["dme"] if "dme" in held else None,
        ime=files["ime"] if "ime" in held else None,
    )
    assert [n for n, v in entry["lists"].items() if v["present"]] == held
    if missing:
        assert entry["lists"][missing]["present"] is False and entry["present"] is True
        assert {t for t, _ in rows_of(copy)} == set(held)
    if "ime" in held:
        assert entry["lists"]["ime"]["named_by"] == "file"
        assert ("ime", IME_ROWS[-1][1]) in rows_of(copy)  # no MedDRA to say it is no PT


def test_a_list_that_cannot_be_read_is_recorded_not_held_and_the_other_still_is(
    release, files, tmp_path
):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    bad = tmp_path / "ime.xlsx"
    bad.write_text("nothing", encoding="utf-8")
    entry = add_medical_events(copy, dme=files["dme"], ime=bad)
    assert entry["lists"]["dme"]["present"] and not entry["lists"]["ime"]["present"]
    assert "was not read" in entry["lists"]["ime"]["reason"]
    assert {t for t, _ in rows_of(copy)} == {"dme"}


def test_codes_alone_need_the_releases_meddra(release, tmp_path):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    codes = tmp_path / "ime.txt"
    codes.write_text("94000027\n", encoding="utf-8")
    entry = add_medical_events(copy, ime=codes)
    assert "holds no MedDRA" in entry["lists"]["ime"]["reason"]


def test_the_step_alone_adds_only_its_table_and_manifest_entry(release, files, tmp_path, capsys):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    before = files_of(copy)
    code = main(
        ["medical-events", str(copy), "--dme", str(files["dme"]), "--ime", str(files["ime"])]
    )
    assert code == 0 and "medical_events_T written" in capsys.readouterr().out
    after = files_of(copy)
    assert set(after) == set(before)  # the empty table was there; it is replaced whole
    changed = {name for name in before if after[name] != before[name]}
    assert changed == {"manifest.json", f"parquet/{TABLE}.parquet"}
    old, new = json.loads(before["manifest.json"]), json.loads(after["manifest.json"])
    assert new["tables"][TABLE]["rows"] > 0
    for doc in (old, new):
        doc["tables"].pop(TABLE)
        doc.pop("medical_events")
    assert new == old


def test_the_step_alone_on_a_release_without_the_table_adds_the_table_and_nothing_else(
    release, files, tmp_path
):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    (copy / "parquet" / f"{TABLE}.parquet").unlink()
    manifest = read_manifest(copy)
    manifest["tables"].pop(TABLE)
    manifest.pop("medical_events")
    (copy / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    before = files_of(copy)
    add_medical_events(copy, dme=files["dme"])
    after = files_of(copy)
    assert set(after) - set(before) == {f"parquet/{TABLE}.parquet"}
    assert {n for n in before if after[n] != before[n]} == {"manifest.json"}


def test_run_again_with_the_same_files_the_release_is_the_same(listed_release, files, tmp_path):
    copy = tmp_path / listed_release.name
    shutil.copytree(listed_release, copy)
    add_medical_events(copy, dme=files["dme"], ime=files["ime"])
    assert files_of(copy) == files_of(listed_release)


def test_the_step_refuses_a_folder_that_is_no_release(tmp_path, files):
    with pytest.raises(Exception, match="release"):
        add_medical_events(tmp_path, dme=files["dme"])
