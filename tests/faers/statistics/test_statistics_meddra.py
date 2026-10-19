"""Which key the statistics count a reaction by (rule statistics-cases): its current preferred
term where the release holds MedDRA, FDA's text where it does not, said in the manifest, and
never a MedDRA code, lower level term or text to PT link in the public part. MedDRA added to a
release already built counts it again, as a build with MedDRA does."""

from __future__ import annotations

import json
import shutil

import duckdb
import pytest

from open_altio.faers.meddra import build_licensed, licensed_dir, read_licensed_manifest
from open_altio.faers.statistics import STRATA_TABLE, TABLE, cases
from open_altio.faers.statistics.classes import TABLE as CLASS_TABLE
from open_altio.testing.fakemeddra import write_meddra
from open_altio.testing.releasereader import ReleaseReader

KEY = "era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR"
# primaryid, ingredient; each drug the case's primary suspect
DRUGS = [("1", "aspirin"), ("2", "aspirin"), ("3", "warfarin")]
# Case 1 names Headache and a lower level term of it; case 2 the lower level term alone, in
# capitals; case 3 a PT's former name.
REACTIONS = [("1", "Headache"), ("1", "Head pain"), ("2", "HEAD PAIN"), ("3", "Lactic acidosis")]
MAPPING = [("headache", "1"), ("head pain", "1"), ("lactic acidosis", "2")]  # reac_meddra_T
PTS = [("1", "Headache"), ("2", "Acidosis lactic")]  # meddra_pt


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        f"CREATE TABLE case_latest_T ({KEY}, age_band_T VARCHAR, sex_T VARCHAR, "
        "init_year_T INTEGER, dup_kept_T BOOLEAN)"
    )
    con.execute(f"CREATE TABLE drug_latest_T ({KEY}, drug_seq VARCHAR, role_cod VARCHAR)")
    con.execute(f"CREATE TABLE drug_ingredient_T ({KEY}, drug_seq VARCHAR, ingredient_T VARCHAR)")
    con.execute(f"CREATE TABLE reac_latest_T ({KEY}, pt VARCHAR)")
    con.execute("CREATE TABLE reac_meddra_T (reac_term_T VARCHAR, pt_code_T VARCHAR)")
    con.execute("CREATE TABLE meddra_pt (pt_code VARCHAR, pt_name VARCHAR)")
    row = "'faers', ?, '2026q2'"
    for primaryid, ingredient in DRUGS:
        con.execute(
            f"INSERT INTO case_latest_T VALUES ({row}, '18-64', 'F', 2020, TRUE)", [primaryid]
        )
        con.execute(f"INSERT INTO drug_latest_T VALUES ({row}, '1', 'PS')", [primaryid])
        con.execute(
            f"INSERT INTO drug_ingredient_T VALUES ({row}, '1', ?)", [primaryid, ingredient]
        )
    con.executemany(f"INSERT INTO reac_latest_T VALUES ({row}, ?)", REACTIONS)
    con.executemany("INSERT INTO reac_meddra_T VALUES (?, ?)", MAPPING)
    con.executemany("INSERT INTO meddra_pt VALUES (?, ?)", PTS)
    return con


def _pairs(counts: cases.Counts) -> dict[tuple[str, str], int]:
    p, e, n = counts.pairs["product"], counts.pairs["event"], counts.pairs["n"]
    return {
        (counts.ingredients[i], counts.reactions[j]): int(k)
        for i, j, k in zip(p, e, n, strict=True)
    }


def test_with_meddra_a_case_counts_once_under_the_current_pt_of_each_text():
    counts = cases.count(_connection(), "meddra_pt")
    assert counts.cases == 3
    assert _pairs(counts) == {("aspirin", "Headache"): 2, ("warfarin", "Acidosis lactic"): 1}


def test_without_meddra_each_text_counts_apart_whatever_its_capitals():
    counts = cases.count(_connection(), "fda_text")
    assert counts.cases == 3
    assert _pairs(counts) == {
        ("aspirin", "headache"): 1,
        ("aspirin", "head pain"): 2,
        ("warfarin", "lactic acidosis"): 1,
    }


@pytest.fixture(scope="module")
def licensed(licensed_release) -> ReleaseReader:
    return ReleaseReader(licensed_release)


def _statistics(reader: ReleaseReader) -> dict[tuple[str, str], int]:
    rows = reader.rows(f"SELECT ingredient_T, reaction_T, cases_T FROM {TABLE}")
    return {(i, r): n for i, r, n in rows}


def _held(release, sql: str) -> set[str]:
    """Values from the MedDRA version the release's licensed part holds (`sql` reads its
    tables as {meddra_pt}, {meddra_llt} and {meddra_term_T})."""
    [entry] = read_licensed_manifest(release)["meddra"]["versions"].values()
    paths = {
        t: f"read_parquet('{licensed_dir(release) / entry['tables'][t]['path']}')"
        for t in ("meddra_pt", "meddra_llt", "meddra_term_T")
    }
    return {v for (v,) in duckdb.sql(sql.format(**paths)).fetchall()}


def test_a_release_without_meddra_counts_fdas_text_and_says_so(rel):
    entry = rel.manifest["statistics"]
    assert entry["reaction_key"] == "fda_text" and "meddra_version" not in entry
    texts = {t.lower() for (t,) in rel.rows("SELECT DISTINCT pt FROM reac_latest_T")}
    assert {r for _i, r in _statistics(rel)} <= texts


def test_a_release_with_meddra_counts_its_current_pts_and_says_which_version(
    rel, licensed, licensed_release
):
    entry = licensed.manifest["statistics"]
    assert entry["reaction_key"] == "meddra_pt" and entry["meddra_version"] == "29.1"
    by_pt, by_text = _statistics(licensed), _statistics(rel)
    assert {r for _i, r in by_pt} <= _held(licensed_release, "SELECT pt_name FROM {meddra_pt}")
    # a renamed PT and a demoted one count under today's PT, with the same cases
    assert by_pt[("metformin", "Acidosis lactic")] == by_text[("metformin", "lactic acidosis")]
    assert by_pt[("digoxin", "Heart rhythm abnormal")] == by_text[("digoxin", "arrhythmia")]
    assert entry["counted"]["cases"] == rel.manifest["statistics"]["counted"]["cases"]


def test_the_public_part_names_pts_but_no_code_lower_level_term_or_former_name(
    licensed, licensed_release
):
    codes = _held(
        licensed_release, "SELECT pt_code FROM {meddra_pt} UNION SELECT llt_code FROM {meddra_llt}"
    )
    others = _held(
        licensed_release,
        "SELECT llt_name FROM {meddra_llt} WHERE llt_name NOT IN (SELECT pt_name FROM {meddra_pt})",
    ) | {"lactic acidosis", "arrhythmia"}  # former names, as FDA's text keys them
    named = {
        v for row in licensed.rows(f"SELECT ingredient_T, reaction_T FROM {TABLE}") for v in row
    }
    assert codes and not named & (codes | others)
    entry = json.dumps(licensed.manifest["statistics"])
    assert not [c for c in codes if c in entry]
    con = duckdb.connect(str(licensed_release / "explorer.duckdb"), read_only=True)
    shown = con.execute("SELECT DISTINCT reaction_T FROM explorer_statistics_T").fetchall()
    con.close()
    assert {r for (r,) in shown} == {r for _i, r in _statistics(licensed)}


def test_meddra_added_to_a_built_release_counts_its_statistics_as_a_build_with_it_does(
    release, licensed, tmp_path
):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    build_licensed(copy, write_meddra(tmp_path / "meddra", "29.1"))
    added = ReleaseReader(copy)
    entry, built = added.manifest["statistics"], licensed.manifest["statistics"]
    assert (entry["reaction_key"], entry["meddra_version"]) == ("meddra_pt", "29.1")
    assert entry["counted"] == built["counted"]
    assert _statistics(added) == _statistics(licensed)
    con = duckdb.connect(str(copy / "explorer.duckdb"), read_only=True)
    shown = con.execute(
        "SELECT ingredient_T, reaction_T, cases_T FROM explorer_statistics_T"
    ).fetchall()
    con.close()
    assert {(i, r): n for i, r, n in shown} == _statistics(licensed)
    tables = added.manifest["explorer"]["tables"]
    assert tables["explorer_statistics_T"]["rows"] == len(shown)
    assert added.manifest["tables"][TABLE]["rows"] == len(shown)
    # the ROR by stratum is counted again too, by the same PTs
    strata = f"SELECT * FROM {STRATA_TABLE} ORDER BY ALL"
    assert added.rows(strata) == licensed.rows(strata)
    assert tables["explorer_statistics_strata_T"]["rows"] == len(added.rows(strata)) > 0
    # and the statistics of each class, by the same PTs (rule statistics-classes)
    by_class = f"SELECT * FROM {CLASS_TABLE} ORDER BY ALL"
    assert added.rows(by_class) == licensed.rows(by_class) != []
    assert added.manifest["class_statistics"]["reaction_key"] == "meddra_pt"
    assert not list(copy.glob(".*"))  # no work folder left behind
