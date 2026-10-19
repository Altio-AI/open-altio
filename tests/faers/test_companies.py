"""The company table put in a release already built (src/open_altio/faers/companies.py) gives what
a build with the table gives, writes nothing when run again, and keeps the rules the release was
built with. Rule: rules/company-names.md. The story's senders are FDA's FAERS names of firms
formed by a merger before 2012, their AERS names from before the merger and after it, a firm kept
apart from the merged one, and a direct report."""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers import build_release
from open_altio.faers.__main__ import main
from open_altio.faers.companies import TABLES, apply_company_table
from open_altio.faers.explorer_db import EXPLORER_FILE
from open_altio.faers.insights import numbers
from open_altio.faers.reader import MANIFEST_FILE, read_manifest
from open_altio.rulebook import UserRules
from open_altio.testing import fakefda
from open_altio.testing.releasereader import ReleaseReader
from open_altio.testing.rules import rules_with

R = fakefda.R
DIRECT = rulebook.value("company-names", "direct_reports")[0]
FDA = rulebook.value("company-names", "fda_sender")
# fmt: off
STORY = [
    R("2012q3", "4200001", "5200001", "20120801", caseversion="", sender="SANKYO PHARMA INC."),
    R("2012q3", "4200002", "5200002", "20120802", caseversion="", sender="DAIICHI SANKYO INC."),
    R("2012q3", "4200003", "5200003", "20120803", caseversion="",
      sender="DAIICHI PHARMACEUTICAL CO., LTD."),
    R("2012q3", "4200004", "5200004", "20120804", caseversion="", sender="BIOVITRUM AB."),
    R("2019q1", "92100011", "9210001", "20190110", sender="DAIICHI"),
    R("2019q1", "92200021", "9220002", "20190111", sender="KYOWA"),
    R("2019q1", "92300031", "9230003", "20190112", sender="SWEDISH ORPHAN"),
    R("2019q1", "92400041", "9240004", "20190113", sender="BIOVITRUM"),
    R("2019q1", "92500051", "9250005", "20190114", sender=fakefda.LILLY[0]),
    R("2019q1", "92600061", "9260006", "20190115", rept_cod=DIRECT, sender=FDA),
    R("2026q2", "92100012", "9210001", "20260501", caseversion="2", sender="DAIICHI"),
    R("2026q2", "92700071", "9270007", "20260502", sender="SWEDISH ORPHAN BIOVITRUM"),
]
# fmt: on
QUARTERS = ("2012q3", "2019q1", "2026q2")
# each FAERS name as the table counted it before: a company of its own
BEFORE = {
    "DAIICHI": "Daiichi",
    "KYOWA": "Kyowa",
    "SWEDISH ORPHAN": "Swedish Orphan",
    "BIOVITRUM": "Biovitrum",
}
# what a build writes differently each time it runs
BUILD_FACTS = ("built_at", "build_seconds", "peak_rss_bytes", "release_bytes")


def _old_table(folder: Path) -> Path:
    """The company table as it was, each of FDA's FAERS names in BEFORE a company of its own."""
    mapping = rulebook.data_root() / rulebook.value("company-names", "mapping")
    with open(mapping, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["company"] = BEFORE.get(row["fda_value"], row["company"])
    path = folder / "old.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _company_of(spelling: str) -> str:
    """The company today's table names for a spelling."""
    mapping = rulebook.data_root() / rulebook.value("company-names", "mapping")
    with open(mapping, encoding="utf-8", newline="") as f:
        return next(r["company"] for r in csv.DictReader(f) if r["fda_value"] == spelling)


def _files(release: Path) -> dict[str, tuple[int, int]]:
    return {
        p.relative_to(release).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(release.rglob("*"))
        if p.is_file()
    }


def _companies(release: Path) -> dict[str, str | None]:
    return dict(ReleaseReader(release).rows("SELECT case_key_T, company_T FROM case_latest_T"))


@pytest.fixture(scope="module")
def zips(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return fakefda.write_input(
        tmp_path_factory.mktemp("company_zips"), quarters=QUARTERS, story=STORY
    )


@pytest.fixture(scope="module")
def built(zips: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The story built with today's company table."""
    return build_release(zips, tmp_path_factory.mktemp("company_built"))


@pytest.fixture(scope="module")
def applied(zips: Path, tmp_path_factory: pytest.TempPathFactory) -> dict:
    """The story built with the old table, its companies then, and the table put in it."""
    scratch = tmp_path_factory.mktemp("company_applied")
    with rules_with(scratch, {"company-names": {"mapping": _old_table(scratch).as_posix()}}):
        release = build_release(zips, scratch / "releases")
    before = _companies(release)
    return {"release": release, "before": before, "done": apply_company_table(release)}


def test_the_old_table_counted_each_faers_name_apart_and_the_command_changes_those_rows(applied):
    before, changed = applied["before"], applied["done"]["changed"]
    assert before["9210001"] == BEFORE["DAIICHI"] and before["9230003"] == BEFORE["SWEDISH ORPHAN"]
    assert before["9240004"] == BEFORE["BIOVITRUM"]
    # two versions of the DAIICHI case, and one each of KYOWA, SWEDISH ORPHAN and BIOVITRUM
    assert changed == {
        "demo_T": 5,
        "demo_latest_T": 4,
        "case_latest_T": 4,
        "explorer_case_T": 4,
    }


def test_a_release_given_the_table_is_the_release_built_with_it(applied, built):
    release = applied["release"]
    for table, entry in read_manifest(built)["tables"].items():
        mine, theirs = release / entry["path"], built / entry["path"]
        assert mine.read_bytes() == theirs.read_bytes(), table
    con = duckdb.connect()
    con.execute(f"ATTACH '{release / EXPLORER_FILE}' AS mine (READ_ONLY)")
    con.execute(f"ATTACH '{built / EXPLORER_FILE}' AS theirs (READ_ONLY)")
    for table in read_manifest(built)["explorer"]["tables"]:
        columns = "* EXCLUDE (built_at_T)" if table == "explorer_release_T" else "*"
        a, b = (f"SELECT {columns} FROM {db}.{table}" for db in ("mine", "theirs"))
        apart = f"SELECT count(*) FROM (({a} EXCEPT ALL {b}) UNION ALL ({b} EXCEPT ALL {a}))"
        assert con.execute(apart).fetchall() == [(0,)], table
    con.close()
    mine, theirs = read_manifest(release), read_manifest(built)
    assert mine["explorer"]["tables"] == theirs["explorer"]["tables"]
    for manifest in (mine, theirs):
        manifest["explorer"].pop("bytes")
    assert {k: v for k, v in mine.items() if k not in BUILD_FACTS} == {
        k: v for k, v in theirs.items() if k not in BUILD_FACTS
    }
    # the manifest's sizes are the files' own, as the build counts them
    on_disk = _files(release)
    assert read_manifest(release)["release_bytes"] == sum(
        size for path, (size, _) in on_disk.items() if path != MANIFEST_FILE
    )
    assert read_manifest(release)["explorer"]["bytes"] == on_disk[EXPLORER_FILE][0]
    # then the methods command records the rule as the build does
    numbers.write(release)
    assert (release / "methods.json").read_bytes() == (built / "methods.json").read_bytes()


def test_a_second_run_writes_nothing(applied, capsys):
    release = applied["release"]
    files = _files(release)
    assert main(["companies", "--release", str(release)]) == 0
    out = capsys.readouterr().out
    assert all(f"0 rows of {t}" in out for t in TABLES), out
    assert _files(release) == files


def test_fdas_faers_names_of_merged_firms_count_under_them_and_older_names_stay_apart(built):
    got = _companies(built)
    merged = got["5200002"]  # DAIICHI SANKYO INC., in AERS after the merger
    assert got["9210001"] == merged
    assert got["9220002"] == _company_of("KYOWA KIRIN PHARMACEUTICAL DEVELOPMENT")
    assert got["9230003"] == got["9240004"] == got["9270007"]
    assert got["9230003"] == _company_of("SWEDISH ORPHAN BIOVITRUM")
    # AERS names from before the merger, and the firm kept apart, stay their own
    assert got["5200001"] == _company_of("SANKYO PHARMA INC.") != merged
    assert got["5200003"] == "DAIICHI PHARMACEUTICAL CO., LTD."
    assert got["5200004"] == _company_of("BIOVITRUM AB.") != got["9240004"]
    assert got["9260006"] is None
    # the Company filter finds the merged firm by FDA's FAERS name
    senders = dict(
        duckdb.connect(str(built / EXPLORER_FILE), read_only=True)
        .execute("SELECT spelling_T, company_T FROM explorer_sender_T")
        .fetchall()
    )
    assert senders["DAIICHI"] == senders["DAIICHI SANKYO INC."] == merged
    assert BEFORE["DAIICHI"] not in senders.values()


def test_a_release_built_with_the_rule_off_keeps_every_sender_as_written(zips, tmp_path):
    release = build_release(zips, tmp_path, user_rules=UserRules(off=frozenset({"company-names"})))
    files = _files(release)
    assert set(apply_company_table(release)["changed"].values()) == {0}
    assert _files(release) == files
    assert _companies(release)["9210001"] == "DAIICHI"
