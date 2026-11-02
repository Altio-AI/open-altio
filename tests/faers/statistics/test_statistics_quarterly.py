"""Quarter-end counts built once into the release (src/open_altio/faers/statistics/quarterly.py):
the statistics' own cases, each placed in the quarter of its received day (rule received-day)
or, with none, of its own file, counted by quarter and stratum, and by reaction too. Summed over
every quarter they give the statistics' margins; a release with MedDRA has the reactions by FDA's
text beside them; and the step run alone on a release built before it adds only its own tables
and manifest entry."""

from __future__ import annotations

import json
import shutil
from datetime import date

import pytest

from open_altio import rulebook
from open_altio.faers import read_manifest
from open_altio.faers.__main__ import main
from open_altio.faers.dates import received_day
from open_altio.faers.reader import write_manifest
from open_altio.faers.statistics import QUARTER_TABLES, STRATA_TABLE, TABLE, by_current_pt
from open_altio.faers.statistics import quarterly as q
from open_altio.faers.statistics.cases import RULE, roles_sql
from open_altio.testing.releasereader import ReleaseReader

SUFFIX = rulebook.value("transformed-suffix-T", "derived_suffix")
PARTS = [p + SUFFIX for p in rulebook.value(RULE, "strata")]
QNUM, CASES, REACTION = (f"{c}{SUFFIX}" for c in ("qnum", "cases", "reaction"))


@pytest.fixture(scope="module", params=["release", "stats_release"])
def built(request) -> ReleaseReader:
    """The invented release, too small for EBGM's prior to fit, and one where it fits."""
    return ReleaseReader(request.getfixturevalue(request.param))


def test_the_release_carries_the_two_tables_and_says_what_they_counted(built):
    entry = built.manifest["quarter_statistics"]
    assert entry["present"] and entry["received_day"] == received_day()
    assert (entry["table"], entry["reaction_table"]) == (q.QUARTERS, q.REACTIONS)
    assert entry["reaction_key"] == built.manifest["statistics"]["reaction_key"] == "fda_text"
    assert "as_published" not in entry and q.AS_PUBLISHED not in built.manifest["tables"]
    assert built.columns(q.QUARTERS) == [QNUM, *PARTS, CASES]
    assert built.columns(q.REACTIONS) == [REACTION, QNUM, *PARTS, CASES]
    for name in (q.QUARTERS, q.REACTIONS):
        table = built.manifest["tables"][name]
        assert table["kind"] == "derived" and table["path"] == f"parquet/{name}.parquet"
        [(rows,)] = built.rows(f"SELECT count(*) FROM {name}")
        assert entry["tables"][name] == {"rows": rows, "bytes": table["bytes"]} and rows > 0
        assert table["rows"] == rows
    assert entry["seconds"]["total"] >= entry["seconds"]["count"] >= 0
    [(quarters,)] = built.rows(f"SELECT count(DISTINCT {QNUM}) FROM {q.QUARTERS}")
    assert entry["counted"]["quarters"] == quarters


def test_summed_over_every_quarter_each_table_equals_the_statistics_own_margins(built):
    counted = built.manifest["statistics"]["counted"]
    [(cases, strata)] = built.rows(
        f"SELECT sum({CASES}), count(DISTINCT ({', '.join(PARTS)})) FROM {q.QUARTERS}"
    )
    assert (cases, strata) == (counted["cases"], counted["strata"])
    assert built.manifest["quarter_statistics"]["counted"]["cases"] == counted["cases"]
    # each reaction's cases, and its cases within each age band and each sex
    summed = f"SELECT {REACTION}, sum({CASES}) FROM {q.REACTIONS} GROUP BY ALL ORDER BY 1"
    margins = "SELECT reaction_T, any_value(reaction_cases_T) FROM {} GROUP BY ALL ORDER BY 1"
    assert built.rows(summed) == built.rows(margins.format(TABLE))
    assert len(built.rows(summed)) == counted["reactions"]
    for part in rulebook.value("ror-strata", "by"):
        column = part + SUFFIX
        by_value = f"SELECT {column}, sum({CASES}) FROM {q.QUARTERS} GROUP BY ALL ORDER BY 1"
        theirs = (
            f"SELECT stratum_T, any_value(stratum_cases_T) FROM {STRATA_TABLE} "
            f"WHERE by_T = '{part}' GROUP BY ALL ORDER BY 1"
        )
        # every value with a pair's case in it, which is every value with a counted case
        assert built.rows(by_value) == built.rows(theirs)
        reactions = (
            f"SELECT {REACTION}, {column}, sum({CASES}) FROM {q.REACTIONS} GROUP BY ALL "
            "ORDER BY 1, 2"
        )
        within = (
            f"SELECT reaction_T, stratum_T, any_value(reaction_cases_T) FROM {STRATA_TABLE} "
            f"WHERE by_T = '{part}' GROUP BY ALL ORDER BY 1, 2"
        )
        assert built.rows(reactions) == built.rows(within)


def _quarter(day: date | None, own: str) -> int:
    """yyyyq, worked out here apart from the step's SQL."""
    if day is None:
        return int(own[:4]) * 10 + int(own[5])
    return day.year * 10 + (day.month - 1) // 3 + 1


def test_each_case_is_counted_in_the_quarter_of_its_received_day_else_its_own_file(rel):
    """A second count, apart from the step: the statistics' cases picked here, each quarter
    worked out in Python."""
    picked = rel.rows(
        f"SELECT c.{received_day()}, c.quarter_T FROM case_latest_T c WHERE c.dup_kept_T "
        "AND EXISTS (SELECT 1 FROM drug_latest_T d JOIN drug_ingredient_T i "
        "USING (era_T, primaryid, quarter_T, drug_seq) WHERE d.era_T = c.era_T AND "
        "d.primaryid = c.primaryid AND d.quarter_T = c.quarter_T "
        f"AND upper(trim(d.role_cod)) IN ({roles_sql()})) "
        "AND EXISTS (SELECT 1 FROM reac_latest_T r WHERE r.era_T = c.era_T AND "
        "r.primaryid = c.primaryid AND r.quarter_T = c.quarter_T AND trim(r.pt) <> '')"
    )
    want: dict[int, int] = {}
    for day, own in picked:
        want[_quarter(day, own)] = want.get(_quarter(day, own), 0) + 1
    got = dict(rel.rows(f"SELECT {QNUM}, sum({CASES}) FROM {q.QUARTERS} GROUP BY ALL"))
    assert got == want
    # the invented release has cases received before the quarter of the file that holds them;
    # a case with no received day is the next test's
    assert any(day is not None and _quarter(day, own) != _quarter(None, own) for day, own in picked)


def test_a_case_with_no_received_day_goes_to_its_own_quarter(small_release):
    con = small_release(
        case_latest_T=[("1", "18-64", "F", 2019, True), ("2", "18-64", "F", 2026, True)],
        drug_latest_T=[("1", "1", "PS"), ("2", "1", "PS")],
        drug_ingredient_T=[("1", "1", "aspirin"), ("2", "1", "aspirin")],
        reac_latest_T=[("1", "Headache"), ("2", "Headache")],
    )
    con.execute(f"ALTER TABLE case_latest_T ADD COLUMN {received_day()} DATE")
    con.execute(
        f"UPDATE case_latest_T SET {received_day()} = DATE '2019-02-10' WHERE primaryid = '1'"
    )
    parts = q.place(con)
    quarters = con.execute(f"SELECT {QNUM}, {CASES} FROM ({q.select(q.QUARTERS, parts)})")
    assert sorted(quarters.fetchall()) == [(20191, 1), (20262, 1)]  # 2026q2 is the file's
    reactions = con.execute(f"SELECT {REACTION}, {QNUM} FROM ({q.select(q.REACTIONS, parts)})")
    assert sorted(reactions.fetchall()) == [("headache", 20191), ("headache", 20262)]


def test_a_release_without_drug_ingredients_has_none_and_says_why(tmp_path):
    written, entry = q.build(tmp_path, {})
    assert written == {} and entry == {
        "present": False,
        "reason": "The release has no drug ingredients to count (rule drug-names).",
    }


def test_with_meddra_reactions_count_by_pt_and_again_by_fdas_text(seizure_release):
    seizure = ReleaseReader(seizure_release)
    entry, statistics = seizure.manifest["quarter_statistics"], seizure.manifest["statistics"]
    assert (entry["reaction_key"], entry["meddra_version"]) == ("meddra_pt", "29.1")
    second = entry["as_published"]
    assert second["reaction_key"] == "fda_text" and second["reaction_table"] == q.AS_PUBLISHED
    assert set(second["tables"]) == {q.AS_PUBLISHED}
    # the same cases either way, so one table of cases by quarter serves both
    assert entry["counted"]["cases"] == second["counted"]["cases"]
    assert statistics["counted"]["cases"] == statistics["as_published"]["counted"]["cases"]
    summed = "SELECT {}, sum({}) FROM {} GROUP BY ALL ORDER BY 1"
    margins = "SELECT reaction_T, any_value(reaction_cases_T) FROM {} GROUP BY ALL ORDER BY 1"
    for ours, theirs in ((q.REACTIONS, TABLE), (q.AS_PUBLISHED, "statistics_as_published_T")):
        assert seizure.rows(summed.format(REACTION, CASES, ours)) == seizure.rows(
            margins.format(theirs)
        )
    # Convulsion and Seizure are one PT today, two texts as FDA wrote them
    names = "SELECT list(DISTINCT {} ORDER BY {}) FROM {}"
    [(by_pt,)] = seizure.rows(names.format(REACTION, REACTION, q.REACTIONS))
    [(as_written,)] = seizure.rows(names.format(REACTION, REACTION, q.AS_PUBLISHED))
    assert "convulsion" in as_written and "Seizure" in by_pt and len(as_written) == len(by_pt) + 1
    # a viewer shown FDA's text is given the reactions by FDA's text alone
    hidden = by_current_pt(seizure.manifest)
    assert q.REACTIONS in hidden and q.AS_PUBLISHED not in hidden and q.QUARTERS not in hidden


def _as_built_before(release, folder):
    """A copy of `release` as a build before the step left it: none of its files or manifest
    entries, and nothing else changed."""
    copy = folder / release.name
    shutil.copytree(release, copy)
    manifest = read_manifest(copy)
    for name in QUARTER_TABLES:
        if name in manifest["tables"]:
            (copy / manifest["tables"].pop(name)["path"]).unlink()
    del manifest["quarter_statistics"]
    write_manifest(copy, manifest)
    return copy


def _files(folder) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("which", ["release", "seizure_release"])
def test_the_step_alone_on_a_built_release_adds_only_its_tables_and_manifest_entry(
    which, request, tmp_path, capsys
):
    release = request.getfixturevalue(which)
    copy = _as_built_before(release, tmp_path)
    before = _files(copy)
    assert main(["quarter-statistics", str(copy)]) == 0
    assert "quarter_strata_T, reaction_quarter_strata_T" in capsys.readouterr().out
    after = _files(copy)
    built = read_manifest(release)
    added = {built["tables"][n]["path"] for n in QUARTER_TABLES if n in built["tables"]}
    assert set(after) == set(before) | added
    changed = {name for name in before if after[name] != before[name]}
    assert changed == {"manifest.json"}
    # the manifest gains the tables and the entry, and nothing else in it changes
    old, new = json.loads(before["manifest.json"]), json.loads(after["manifest.json"])
    gained = {n: e for n, e in new["tables"].items() if n not in old["tables"]}
    assert set(gained) == {n for n in QUARTER_TABLES if n in built["tables"]}
    new["tables"] = {n: e for n, e in new["tables"].items() if n in old["tables"]}
    entry = new.pop("quarter_statistics")
    assert new == old
    # what the step writes is what the build writes
    for name in gained:
        assert after[gained[name]["path"]] == (release / gained[name]["path"]).read_bytes()
        assert gained[name] == built["tables"][name] | {"bytes": gained[name]["bytes"]}

    def same(e: dict) -> dict:
        e = json.loads(json.dumps(e))
        for s in (e, e.get("as_published") or {}):
            s.pop("seconds", None)
        return e

    assert same(entry) == same(built["quarter_statistics"])
    # run again: the same, and nothing left beside the files it wrote
    q.add_quarters(copy)
    assert {k: v for k, v in _files(copy).items() if k != "manifest.json"} == {
        k: v for k, v in after.items() if k != "manifest.json"
    }
    assert not [p.name for p in copy.rglob("*") if ".writing" in p.name or "spill" in p.name]
