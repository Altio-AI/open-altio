"""The statistics step of the build (src/open_altio/faers/statistics/step.py): the tables it
writes into the release, what the manifest says about the fit, the explorer's copies, and the
releases it leaves without EBGM or without statistics at all."""

from __future__ import annotations

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers import build_release, read_manifest
from open_altio.faers.dates import ONSET_REASONS
from open_altio.faers.explorer_db import STATISTICS, STATISTICS_STRATA
from open_altio.faers.statistics import COLUMNS, STRATA_TABLE, TABLE, strata
from open_altio.testing import fakefda, fakestats
from open_altio.testing.releasereader import ReleaseReader

SUFFIX = rulebook.value("transformed-suffix-T", "derived_suffix")


@pytest.fixture(scope="module")
def stats(stats_release) -> ReleaseReader:
    return ReleaseReader(stats_release)


def test_the_release_carries_its_statistics_as_a_derived_table(stats):
    entry = stats.manifest["tables"][TABLE]
    assert entry["kind"] == "derived" and entry["path"] == f"parquet/{TABLE}.parquet"
    assert stats.columns(TABLE) == [name + SUFFIX for name in COLUMNS]
    assert entry["rows"] == stats.manifest["statistics"]["counted"]["pairs"]
    [(cases,)] = stats.rows("SELECT count(*) FROM case_latest_T WHERE dup_kept_T")
    assert stats.manifest["statistics"]["counted"]["cases"] == cases == fakestats.CASES


def test_the_prior_is_fitted_on_the_releases_own_cases_and_recorded(stats):
    fit = stats.manifest["statistics"]["ebgm"]
    assert fit["fitted"] and fit["fit_on"] == rulebook.value("ebgm", "fit_on")
    assert set(fit["prior"]) == {"alpha1", "beta1", "alpha2", "beta2", "p"}
    assert len(fit["starts"]) == len(rulebook.value("ebgm", "starts"))
    assert sum(s["agrees_with_best"] for s in fit["starts"]) >= rulebook.value(
        "ebgm", "agreeing_starts"
    )
    [(below, above)] = stats.rows(
        f"SELECT count(*) FILTER (WHERE eb05_T > ebgm_T), count(*) FILTER (WHERE ebgm_T > eb95_T)"
        f" FROM {TABLE}"
    )
    assert (below, above) == (0, 0)


def test_the_pairs_drawn_far_more_often_stand_out(stats):
    for drug, reaction in fakestats.SIGNALS:
        [(ebgm,)] = stats.rows(
            f"SELECT ebgm_T FROM {TABLE} t JOIN (SELECT DISTINCT d.drugname, i.ingredient_T "
            "FROM drug_latest_T d JOIN drug_ingredient_T i USING (era_T, primaryid, quarter_T, "
            "drug_seq)) n ON n.ingredient_T = t.ingredient_T WHERE n.drugname = ? "
            "AND t.reaction_T = lower(?)",
            drug,
            reaction,
        )
        assert ebgm > 1.5, (drug, reaction)


def test_the_build_is_reproducible(stats, fake_diana, tmp_path):
    from open_altio.testing import fakediana

    with fakediana.pinned(fake_diana, tmp_path):
        again = build_release(
            fakestats.write_input(tmp_path / "zips"), tmp_path, diana_dictionary=fake_diana
        )
    first, second = stats.manifest["statistics"]["ebgm"], read_manifest(again)["statistics"]["ebgm"]
    assert first["prior"] == second["prior"]
    con = duckdb.connect()
    ours, theirs = (str(f / "parquet" / f"{TABLE}.parquet") for f in (stats.path, again))
    assert con.execute(f"SELECT * FROM '{ours}' EXCEPT SELECT * FROM '{theirs}'").fetchall() == []


@pytest.mark.parametrize(
    ("ours", "theirs"), [(STATISTICS, TABLE), (STATISTICS_STRATA, STRATA_TABLE)]
)
def test_the_explorer_database_holds_them_sorted_by_ingredient(stats, ours, theirs):
    con = duckdb.connect(str(stats.path / "explorer.duckdb"), read_only=True)
    rows = con.execute(f"SELECT ingredient_T, reaction_T FROM {ours}").fetchall()
    assert len(rows) == stats.manifest["tables"][theirs]["rows"] > 0
    assert rows == sorted(rows)
    assert stats.manifest["explorer"]["tables"][ours]["rows"] == len(rows)


def test_every_pair_counts_each_of_its_drugs_once_with_a_time_to_onset_or_why_not(stats):
    none = " + ".join(f"no_onset_{r}_T" for r in ONSET_REASONS)
    [(pairs, short, valued, each_reason)] = stats.rows(
        f"SELECT count(*), count(*) FILTER (WHERE onset_drugs_T + {none} < cases_T), "
        "count(*) FILTER (WHERE onset_drugs_T > 0 AND onset_days_T >= 1), "
        f"{' AND '.join(f'sum(no_onset_{r}_T) > 0' for r in ONSET_REASONS)} FROM {TABLE}"
    )
    assert pairs > 0 and short == 0  # each counted case gives the pair a drug at least
    assert valued > 0 and each_reason
    [(empty,)] = stats.rows(f"SELECT count(*) FROM {TABLE} WHERE onset_drugs_T = 0 "
                            "AND onset_days_T IS NOT NULL")  # fmt: skip
    assert empty == 0


def test_the_release_carries_each_pairs_ror_by_age_band_and_by_sex(stats):
    entry = stats.manifest["tables"][STRATA_TABLE]
    assert entry["kind"] == "derived" and entry["path"] == f"parquet/{STRATA_TABLE}.parquet"
    assert stats.columns(STRATA_TABLE) == [name + SUFFIX for name in strata.COLUMNS]
    assert stats.manifest["statistics"]["ror_strata"] == {
        "table": STRATA_TABLE,
        "by": strata.parts(),
    }
    # each part shares out every case of every pair
    [(unequal,)] = stats.rows(
        f"SELECT count(*) FROM (SELECT s.ingredient_T, s.reaction_T, s.by_T, sum(s.cases_T) AS n,"
        f" any_value(t.cases_T) AS cases FROM {STRATA_TABLE} s JOIN {TABLE} t USING "
        "(ingredient_T, reaction_T) GROUP BY ALL) WHERE n <> cases"
    )
    [(parts,)] = stats.rows(f"SELECT list(DISTINCT by_T ORDER BY by_T) FROM {STRATA_TABLE}")
    assert unequal == 0 and parts == sorted(strata.parts())


def test_a_release_too_small_to_fit_keeps_every_other_statistic(rel):
    entry = rel.manifest["statistics"]
    assert entry["present"] and entry["ebgm"]["fitted"] is False and entry["ebgm"]["reason"]
    [(pairs, ebgm, prr)] = rel.rows(f"SELECT count(*), count(ebgm_T), count(rrr_T) FROM {TABLE}")
    assert pairs > 0 and ebgm == 0 and prr == pairs


def test_a_release_without_drug_names_has_no_statistics_and_says_why(fake_input, tmp_path):
    folder = build_release(fake_input, tmp_path, quarters=[fakefda.QUARTERS[-1]])
    manifest = read_manifest(folder)
    assert TABLE not in manifest["tables"] and STRATA_TABLE not in manifest["tables"]
    assert manifest["statistics"] == {
        "present": False,
        "reason": "The release has no drug ingredients to count (rule drug-names).",
    }
