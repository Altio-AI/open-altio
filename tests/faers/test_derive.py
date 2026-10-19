"""The derived steps of a release, read from the release folder only: the latest version of each
case, FDA's deleted cases, the child rows that come along, and the typed columns."""

from __future__ import annotations

import csv
from datetime import date

import pytest

from open_altio import rulebook
from open_altio.faers.schema import CHILD_TABLES


def test_latest_version_per_case(rel):
    kept = {
        (era, key): (pid, q)
        for era, key, pid, q in rel.rows(
            "SELECT era_T, case_key_T, primaryid, quarter_T FROM demo_latest_T"
        )
    }
    assert kept == {
        # legacy: latest fda_dt, then quarter, then primaryid
        ("legacy", "5100001"): ("4100004", "2012q3"),  # later follow-up
        ("legacy", "5100002"): ("4100002", "2012q2"),
        ("legacy", "ISR:4100003"): ("4100003", "2012q2"),  # no CASE: its own case
        ("legacy", "5100005"): ("4100006", "2012q3"),  # same day, same quarter: higher primaryid
        ("legacy", "5100007"): ("4100007", "2012q3"),
        # FAERS: caseversion, then fda_dt, then quarter, then primaryid
        ("faers", "9001001"): ("90010012", "2018q1"),  # version 2 beats version 1
        ("faers", "9002002"): ("90020021", "2012q4"),
        ("faers", "9003003"): ("90030032", "2019q1"),
        ("faers", "9004004"): ("90040043", "2019q1"),  # version 3 beats a later-arriving version 2
        ("faers", "9005005"): ("90050051", "2026q2"),  # re-published primaryid: later quarter
        ("faers", "9006006"): (
            "90060061",
            "2019q1",
        ),  # same version: later fda_dt beats higher primaryid
        ("faers", "9007007"): ("90070079", "2019q1"),  # all equal: higher primaryid
        ("faers", "9008008"): ("90080081", "2019q1"),
        ("faers", "9009009"): ("90090091", "2019q1"),
        ("faers", "9010010"): ("90100101", "2026q2"),
        ("faers", "9110011"): ("91100111", "2026q2"),
        ("faers", "9120012"): ("91200121", "2026q2"),
        ("faers", "9130013"): ("91300131", "2026q2"),
        ("faers", "9013013"): (
            "90130131",
            "2019q1",
        ),  # same version: later fda_dt beats later quarter
        # carried over from AERS (test_eras.py): the FAERS version, never a second legacy case
        ("faers", "5100010"): ("51000102", "2012q4"),
        ("faers", "5100011"): ("51000112", "2018q1"),
        # the duplicate groups (test_dedup.py): one version each
        ("legacy", "5100008"): ("4100008", "2012q3"),
        ("legacy", "5100009"): ("4100009", "2012q2"),
        ("faers", "9020020"): ("90200201", "2019q1"),
        ("faers", "9021021"): ("90210211", "2026q2"),
        ("faers", "9022022"): ("90220221", "2026q2"),
        ("faers", "9023023"): ("90230231", "2019q1"),
        ("faers", "9024024"): ("90240241", "2012q4"),
        ("faers", "9025025"): ("90250251", "2018q1"),
        ("faers", "9026026"): ("90260261", "2019q1"),
        # the drug names read to their ingredients (fakefda.DRUG_NAMES): one version each
        ("faers", "9210001"): ("92100011", "2026q2"),
        ("faers", "9210002"): ("92100021", "2026q2"),
        ("faers", "9210003"): ("92100031", "2026q2"),
        ("faers", "9210004"): ("92100041", "2026q2"),
        ("faers", "9210005"): ("92100051", "2026q2"),
        ("faers", "9210006"): ("92100061", "2026q2"),
        ("faers", "9210007"): ("92100071", "2026q2"),
        ("faers", "9210008"): ("92100081", "2026q2"),
    }


def test_deleted_cases_are_absent_from_the_kept_set(rel):
    assert set(rulebook.value("deleted-cases", "eras")) == {"legacy", "faers"}
    deleted = {"9008008", "9009009", "9010010", "5100007"}  # 5100007 is a legacy AERS case
    kept = {r[0] for r in rel.rows("SELECT caseid FROM case_latest_T WHERE caseid IS NOT NULL")}
    assert kept.isdisjoint(deleted)
    # legacy child rows carry no caseid: check them by report number
    legacy_deleted = {
        r[0]
        for r in rel.rows(
            "SELECT primaryid FROM demo WHERE era_T = 'legacy' AND caseid = '5100007'"
        )
    }
    for t in CHILD_TABLES:
        child = {r[0] for r in rel.rows(f"SELECT caseid FROM {t}_latest_T WHERE era_T = 'faers'")}
        assert child.isdisjoint(deleted), t
        legacy_child = {
            r[0] for r in rel.rows(f"SELECT primaryid FROM {t}_latest_T WHERE era_T = 'legacy'")
        }
        assert legacy_child.isdisjoint(legacy_deleted), t
    # the latest-version step still holds them: nothing is deleted from the record
    latest = {r[0] for r in rel.rows("SELECT caseid FROM demo_latest_T")}
    assert deleted <= latest
    # a legacy report with no CASE number is never matched to a list, and stays
    assert (
        rel.rows("SELECT count(*) FROM case_latest_T WHERE case_key_T = 'ISR:4100003'")[0][0] == 1
    )


def test_deleted_cases_table_reads_every_list_variant(rel):
    got = {r["caseid"]: r for r in rel.dicts("SELECT * FROM deleted_cases_T")}
    assert set(got) == {"9008008", "9999998", "5100011", "9009009", "9010010", "5100007", "9999999"}
    assert got["9008008"]["n_listings_T"] == 2
    assert got["9008008"]["first_listed_quarter_T"] == "2019q1"
    assert got["9008008"]["in_all_history_list_T"] is True
    assert got["9009009"]["in_all_history_list_T"] is True
    assert got["9009009"]["first_listed_quarter_T"] is None  # only on the whole-history list
    assert got["9010010"]["first_listed_quarter_T"] == "2026q2"
    assert got["9010010"]["in_all_history_list_T"] is False


def test_child_tables_join_on_era_primaryid_and_quarter(rel):
    # primaryid 90050051 is in 2019q1 and again in 2026q2; only the kept quarter's rows come along
    assert rel.rows("SELECT pt FROM reac_latest_T WHERE primaryid = '90050051'") == [("Vomiting",)]
    for t in CHILD_TABLES:
        orphans = rel.rows(
            f"SELECT count(*) FROM {t}_latest_T a "
            "ANTI JOIN case_latest_T c USING (era_T, primaryid, quarter_T)"
        )
        assert orphans == [(0,)], t
        expected = rel.rows(
            f"SELECT count(*) FROM {t} a "
            "SEMI JOIN case_latest_T c USING (era_T, primaryid, quarter_T)"
        )
        assert rel.rows(f"SELECT count(*) FROM {t}_latest_T") == expected, t


def test_typed_columns_full_dates_with_precision_age_in_years_weight_in_kg(rel):
    got = {(r["quarter_T"], r["primaryid"]): r for r in rel.dicts("SELECT * FROM demo_T")}

    def one(q, pid):
        return got[(q, pid)]

    r = one("2012q2", "4100001")
    # legacy AERS padded a month to its 1st, so 1 March is known to the month (test_dates.py)
    assert (r["event_dt"], r["event_dt_T"], r["event_dt_prec_T"]) == ("20120301", None, 6)
    assert r["age_years_T"] == pytest.approx(45)
    times, over = rulebook.value("weight-in-kg", "units")["LBS"]
    assert r["wt_kg_T"] == pytest.approx(154 * times / over)
    assert r["fda_dt_T"] == date(2012, 4, 15) and r["first_fda_dt_T"] == date(2012, 4, 15)
    r = one("2012q2", "4100002")
    assert (r["event_dt_T"], r["event_dt_prec_T"]) == (None, 4)  # a year alone is no date
    assert r["age_years_T"] == pytest.approx(1.5)  # 18 months
    assert r["wt_kg_T"] == pytest.approx(70)
    r = one("2012q3", "4100005")
    assert (r["event_dt_T"], r["event_dt_prec_T"]) == (None, 6)  # a month alone is no date
    r = one("2012q3", "4100004")
    assert r["age_years_T"] == pytest.approx(60)  # 6 decades
    assert r["wt_kg_T"] == pytest.approx(3.5)  # grams
    r = one("2018q1", "90030031")
    assert (r["event_dt_T"], r["event_dt_prec_T"]) == (None, 8)  # 30 February
    assert r["age_years_T"] == pytest.approx(1, rel=1e-3)  # hours
    r = one("2012q4", "90020021")
    assert r["age_years_T"] == pytest.approx(2, rel=1e-3)  # weeks
    r = one("2019q1", "90030032")
    assert r["age_years_T"] == pytest.approx(2, rel=1e-3)  # days
    assert r["first_fda_dt_T"] == date(2018, 1, 15)  # init_fda_dt before fda_dt
    assert r["caseversion_T"] == 2
    r = one("2018q1", "90010012")
    assert r["wt_kg_T"] == pytest.approx(81)  # KGS
    assert one("2026q2", "91100111")["age_years_T"] is None  # '4O' is not a number
    assert one("2026q2", "91200121")["age_years_T"] is None  # unknown unit
    assert one("2012q2", "4100003")["event_dt_prec_T"] is None  # no date given
    assert one("2012q2", "4100001")["caseversion_T"] is None  # legacy has no caseversion


def test_drug_names_are_normalised_beside_the_raw_spelling(rel):
    got = dict(rel.rows("SELECT drugname, drugname_norm_T FROM drug_latest_T"))
    assert got["CAFÉ  TABLETS"] == "CAFÉ TABLETS"
    assert got[" ibuprofen "] == "IBUPROFEN"
    assert got["ASPIRIN."] == "ASPIRIN"
    assert "drugname_norm_T" not in rel.columns("drug")


def test_reporter_codes_are_read_as_the_e2b_qualification_through_the_mapping(rel):
    mapping = rulebook.data_root() / rulebook.value("reporter-type", "mapping")
    with mapping.open(encoding="utf-8") as f:
        accepted = {r["fda_value"]: r["e2b_code"] for r in csv.DictReader(f)}
    got = dict(rel.rows("SELECT DISTINCT occp_cod, reporter_type_T FROM demo_T"))
    assert {"MD", "OT", "HP", "RN", "SALES", None} <= got.keys()
    assert all(got[c] == accepted.get(c) for c in got)  # SALES and no code: no type
    assert got["OT"] == got["HP"] == got["RN"]
    assert "reporter_type_T" not in rel.columns("demo")
