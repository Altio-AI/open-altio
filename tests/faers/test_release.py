"""Build a release from fake FDA quarters and check only the release folder."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from open_altio import rulebook
from open_altio.faers import (
    RAW_COLUMNS,
    ReleaseError,
    build_release,
)
from open_altio.faers.drugnames import dictionary
from open_altio.faers.schema import CHILD_TABLES, TABLES
from open_altio.rulebook import UserRules
from open_altio.testing import fakediana, fakefda
from open_altio.testing.releasereader import ReleaseReader
from open_altio.testing.rules import rules_with

SUFFIX = rulebook.value("transformed-suffix-T", "derived_suffix")


def test_release_is_named_by_the_latest_fda_quarter(release):
    assert release.name == fakefda.RELEASE


def test_release_holds_parquet_per_table_original_and_derived(rel):
    tables = rel.manifest["tables"]
    for t in TABLES + ("deleted",):
        assert tables[t]["kind"] == "raw"
    derived = {t for t, e in tables.items() if e["kind"] == "derived"}
    assert {"demo_T", "demo_latest_T", "deleted_cases_T", "case_latest_T", "quarters_T"} <= derived
    assert {f"{t}_latest_T" for t in CHILD_TABLES} <= derived
    assert "case_dup_T" in derived
    for t, entry in tables.items():
        assert entry["path"] == f"parquet/{t}.parquet"
        assert (rel.path / entry["path"]).is_file()
    on_disk = {p.stem for p in (rel.path / "parquet").glob("*.parquet")}
    assert on_disk == set(tables)


def test_manifest_records_inputs_hash_build_time_and_row_counts(rel, fake_input):
    m = rel.manifest
    assert m["release"] == fakefda.RELEASE
    assert m["quarters"] == list(fakefda.QUARTERS)
    assert len(m["inputs_hash"]) == 64 and int(m["inputs_hash"], 16) >= 0
    assert datetime.fromisoformat(m["built_at"]).tzinfo is not None
    assert m["build_seconds"] >= 0
    # the release's size on disk: every file in it but the manifest itself
    files = [p for p in rel.path.rglob("*") if p.is_file() and p.name != "manifest.json"]
    assert m["release_bytes"] == sum(p.stat().st_size for p in files)
    assert m["peak_rss_bytes"] > 0
    for table, entry in m["tables"].items():
        assert rel.rows(f"SELECT count(*) FROM {table}")[0][0] == entry["rows"], table
    # every FDA text file read is listed with the hash of its bytes
    expected = {}
    for q in fakefda.QUARTERS:
        for path, data in fakefda.quarter_files(q).items():
            if path.lower().endswith(".txt") and not Path(path).name.upper().startswith(
                ("STAT", "SIZE")
            ):
                expected[path] = hashlib.sha256(data).hexdigest()
    listed = {i["source"].split("/", 1)[1]: i["sha256"] for i in m["inputs"]}
    assert listed == expected


def test_funnel_counts_per_step_and_era(rel):
    assert [s["id"] for s in rel.funnel["steps"]] == [
        "report_versions",
        "latest_versions",
        "after_deleted_lists",
        "kept_after_duplicates",
        "dates",
        "codes",
        "drug_names",
    ]
    assert rel.step("report_versions")["count"] == {"legacy": 11, "faers": 38, "total": 49}
    # two AERS cases carried into FAERS count once, as their FAERS version
    assert rel.step("latest_versions")["count"] == {"legacy": 7, "faers": 31, "total": 38}
    # FDA's deleted lists take out cases in both eras (rules/deleted-cases.md): 5100007 is legacy
    assert rel.step("after_deleted_lists")["count"] == {"legacy": 6, "faers": 27, "total": 33}
    assert rel.step("after_deleted_lists")["removed"] == {"legacy": 1, "faers": 4, "total": 5}
    assert rel.funnel["deleted_lists"] == {"caseids_listed": 7, "listings": 8}


def test_funnel_numbers_match_the_tables_they_name(rel):
    for step in rel.funnel["steps"]:
        assert rel.rows(f"SELECT count(*) FROM {step['table']}")[0][0] == step["count"]["total"]


def test_raw_columns_inside_derived_tables_are_unchanged(rel):
    cols = ", ".join(f'"{c}"' for c in RAW_COLUMNS["demo"] + ("quarter_T", "era_T"))
    assert rel.rows(f"SELECT {cols} FROM case_latest_T EXCEPT SELECT {cols} FROM demo") == []
    assert rel.rows(f"SELECT {cols} FROM demo EXCEPT SELECT {cols} FROM demo_T") == []


def test_every_derived_table_and_column_ends_in_the_suffix(rel):
    fda = {c for cols in RAW_COLUMNS.values() for c in cols}
    for table, entry in rel.manifest["tables"].items():
        if entry["kind"] == "raw":
            assert rel.columns(table) == list(RAW_COLUMNS[table]) + [
                c for c in ("quarter_T", "era_T") if table != "deleted" or c == "quarter_T"
            ]
            continue
        assert table.endswith(SUFFIX), table
        for c in rel.columns(table):
            assert c in fda or c.endswith(SUFFIX), f"{table}.{c}"


def test_a_release_can_be_built_for_an_earlier_quarter(fake_input, tmp_path):
    path = build_release(fake_input, tmp_path, quarter="2019Q1")
    older = ReleaseReader(path)
    assert path.name == "2019Q1"
    assert older.manifest["quarters"] == ["2012q2", "2012q3", "2012q4", "2018q1", "2019q1"]
    assert older.step("report_versions")["count"]["faers"] == 21


def test_an_existing_release_is_not_overwritten_by_accident(fake_input, tmp_path):
    build_release(fake_input, tmp_path, quarter="2012Q3")
    with pytest.raises(ReleaseError, match="already exists"):
        build_release(fake_input, tmp_path, quarter="2012Q3")
    assert build_release(fake_input, tmp_path, quarter="2012Q3", overwrite=True).name == "2012Q3"


def test_command_line_builds_a_release(fake_input, tmp_path):
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "open_altio.faers",
            "build",
            "--input",
            str(fake_input),
            "--out",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert done.returncode == 0, done.stderr
    assert Path(done.stdout.strip().splitlines()[-1]) == tmp_path / fakefda.RELEASE
    assert (
        json.loads((tmp_path / fakefda.RELEASE / "manifest.json").read_text())["release"]
        == fakefda.RELEASE
    )


def test_tables_are_stored_in_quarter_then_report_order(rel):
    """Rows sit in the Parquet files by quarter, then primaryid (or case),
    so a reader skips row groups by quarter and the files compress well; the
    statistics, which hold no case, by ingredient and reaction, or by level, class and reaction."""
    for table, entry in rel.manifest["tables"].items():
        cols = rel.columns(table)
        key = [c for c in ("quarter_T", "primaryid", "case_key_T", "caseid") if c in cols]
        by_class = ("level_T", "class_T", "reaction_T") if "class_T" in cols else ()
        key = key or [c for c in ("ingredient_T", *by_class, "reaction_T") if c in cols]
        if not key:  # the classes layer's index of WHO's codes holds no reports
            assert table == "atc_index_T", table
            continue
        sel = ", ".join(f'"{c}"' for c in key)
        stored = rel.rows(f"SELECT {sel} FROM read_parquet('{rel.path / entry['path']}')")
        assert stored == sorted(stored, key=lambda r: tuple((v is None, v or "") for v in r)), table


# ------------------------------------------------------------- the drug classes layer
def test_the_classes_follow_the_drug_names_as_a_layer_of_their_own(rel):
    """The shared release, built with the invented dictionary, carries the
    classes the drug-name step's substances join, as their own tables, listed
    in the manifest with the index year and WHO's citation."""
    entry = rel.manifest["classes"]
    assert entry["present"] and entry["index_year"] == int(
        rulebook.value("atc-index", "index_year")
    )
    assert entry["citation"] == rulebook.value("atc-index", "citation")
    kinds = rel.manifest["tables"]
    assert [t for t, e in kinds.items() if e["kind"] == "classes"] == entry["tables"]
    warfarin = """SELECT DISTINCT a.atc_code_T, a.atc_chosen_by_T FROM atc_drug_T a
                  JOIN drug_substance_T s USING (era_T, primaryid, quarter_T, drug_seq)
                  WHERE s.substance_T = 'warfarin'"""
    assert rel.rows(warfarin) == [("B01AA03", "only_code")]
    with_a_class = """SELECT count(DISTINCT case_key_T) FROM case_dedup_T
                      SEMI JOIN (SELECT * FROM atc_drug_T WHERE atc_code_T IS NOT NULL)
                      USING (era_T, primaryid, quarter_T)"""
    assert entry["cases"]["with_a_class"] == rel.rows(with_a_class)[0][0]
    methods = json.loads((rel.path / rel.manifest["methods"]).read_text())
    assert methods["classes"]["citation"] == entry["citation"]


def test_with_the_classes_switched_off_a_release_has_none_and_is_otherwise_the_same(
    fake_input, fake_diana, rel, tmp_path
):
    """The drug classes' one switch, rule atc-index, off in a person's rules: the release is
    built without the layer, says why, and every other table is the standard release's."""
    with fakediana.pinned(fake_diana, tmp_path):
        bare = ReleaseReader(
            build_release(
                fake_input,
                tmp_path / "out",
                diana_dictionary=fake_diana,
                user_rules=UserRules(off=frozenset({"atc-index"})),
            )
        )
    entry = bare.manifest["classes"]
    assert entry["present"] is False and entry["reason"] == "switched off in your rules"
    assert not [t for t, e in bare.manifest["tables"].items() if e["kind"] == "classes"]
    assert bare.manifest["user_rules"] == {"off": ["atc-index"], "changed": []}
    assert set(bare.manifest["tables"]) == set(rel.manifest["tables"]) - set(
        rel.manifest["classes"]["tables"]
    )
    for table, e in bare.manifest["tables"].items():
        assert rel.manifest["tables"][table]["rows"] == e["rows"], table


def test_without_the_class_table_a_release_has_no_classes_says_why_and_is_otherwise_the_same(
    fake_input, fake_diana, rel, tmp_path
):
    pinned = {"drug-names": {"sha256": dictionary.sha256(fake_diana)}}
    missing = {"atc-index": {"table": str(tmp_path / "no-classes.csv")}}
    with rules_with(tmp_path, pinned | missing):
        bare = ReleaseReader(
            build_release(fake_input, tmp_path / "out", diana_dictionary=fake_diana)
        )
    entry = bare.manifest["classes"]
    assert entry["present"] is False and "no class table" in entry["reason"]
    assert not [t for t, e in bare.manifest["tables"].items() if e["kind"] == "classes"]
    for table, e in bare.manifest["tables"].items():
        assert rel.manifest["tables"][table]["rows"] == e["rows"], table
    methods = json.loads((bare.path / bare.manifest["methods"]).read_text())
    assert methods["classes"] == {k: entry[k] for k in ("present", "source", "reason")}
