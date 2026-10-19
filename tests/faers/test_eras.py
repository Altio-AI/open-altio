"""A case is one case across AERS and FAERS, read from the release only.

FDA carried AERS cases into FAERS in 2012 under the same case number, with
FAERS's caseversion counting on from the AERS versions (notebook
02_case_versions). The fake quarters carry two such cases
(fakefda.CARRIED_OVER), and legacy country names and reaction terms as AERS
wrote them (fakefda.LEGACY_COUNTRY; terms in capitals). Rules:
rules/latest-version.md, rules/legacy-country.md, rules/reaction-term-case.md.
"""

from __future__ import annotations

import csv
import re

import pytest

from open_altio import rulebook
from open_altio.faers import ReleaseError, build_release
from open_altio.testing import fakefda


def test_a_case_carried_from_aers_into_faers_is_one_case_its_faers_version(rel):
    assert rulebook.value("latest-version", "across_eras") is True
    assert rel.rows("SELECT era_T, primaryid FROM demo_latest_T WHERE caseid = '5100010'") == [
        ("faers", "51000102")
    ]
    # the AERS version stays in the record, as every version does
    assert sorted(rel.rows("SELECT era_T, primaryid FROM demo_T WHERE caseid = '5100010'")) == [
        ("faers", "51000102"),
        ("legacy", "4100010"),
    ]
    # and its child rows come with the FAERS version only
    assert rel.rows(
        "SELECT DISTINCT era_T FROM drug_latest_T WHERE caseid = '5100010' OR primaryid = '4100010'"
    ) == [("faers",)]


def test_no_case_number_is_counted_in_both_eras(rel):
    assert rel.rows(
        "SELECT count(*) FROM (SELECT caseid FROM demo_latest_T WHERE caseid IS NOT NULL "
        "GROUP BY caseid HAVING count(*) > 1)"
    ) == [(0,)]


def test_a_deleted_faers_case_does_not_survive_through_its_aers_version(rel):
    assert rel.rows("SELECT era_T FROM demo_latest_T WHERE caseid = '5100011'") == [("faers",)]
    assert rel.rows("SELECT count(*) FROM case_latest_T WHERE caseid = '5100011'") == [(0,)]


def test_legacy_country_names_are_read_as_iso_codes(rel):
    assert dict(
        rel.rows(
            "SELECT DISTINCT reporter_country, country_T FROM demo_T "
            "WHERE era_T = 'legacy' AND reporter_country IS NOT NULL"
        )
    ) == {"UNITED STATES": "US", "CANADA": "CA"}
    # the 2004Q1 layout publishes no country, and a stray `$` can empty it: no country_T
    assert rel.rows(
        "SELECT count(*) FROM demo_T WHERE era_T = 'legacy' AND reporter_country IS NULL "
        "AND country_T IS NOT NULL"
    ) == [(0,)]
    # FAERS: the occurrence country, else the reporter's, as FDA wrote them; FDA's words for no
    # country are none (rule country-not-given)
    nots = rulebook.value("country-not-given", "not_countries")
    for occr, reporter, country in rel.rows(
        "SELECT occr_country, reporter_country, country_T FROM demo_T WHERE era_T = 'faers'"
    ):
        assert country == next((c for c in (occr, reporter) if c and c not in nots), None)
    # the raw column is untouched
    assert rel.rows("SELECT count(*) FROM demo WHERE reporter_country = 'CANADA'") == [(1,)]


def test_the_duplicate_key_compares_countries_across_eras_as_codes(rel):
    keys = dict(
        rel.rows(
            "SELECT case_key_T, dup_key_T FROM case_dup_T "
            "WHERE case_key_T IN ('5100008', '9024024')"
        )
    )
    assert keys["5100008"] == keys["9024024"]
    assert "|CA|" in keys["5100008"]


def test_reaction_terms_are_compared_in_capitals_and_kept_as_written(rel):
    assert rulebook.is_on("reaction-term-case")
    # the raw term stays as each era wrote it
    assert dict(
        rel.rows("SELECT era_T, pt FROM reac_latest_T WHERE primaryid IN ('4100008', '90240241')")
    ) == {"legacy": "ARRHYTHMIA", "faers": "Arrhythmia"}
    # pt_norm_T is the same in both eras
    assert rel.rows(
        "SELECT DISTINCT pt_norm_T FROM reac_latest_T WHERE primaryid IN ('4100008', '90240241')"
    ) == [("ARRHYTHMIA",)]
    assert rel.rows(
        "SELECT count(*) FROM reac_latest_T WHERE pt_norm_T IS DISTINCT FROM upper(pt)"
    ) == [(0,)]


def test_the_duplicate_key_compares_reaction_terms_in_capitals(rel):
    keys = dict(
        rel.rows(
            "SELECT case_key_T, dup_key_T FROM case_dup_T "
            "WHERE case_key_T IN ('5100008', '9025025')"
        )
    )
    assert keys["5100008"] == keys["9025025"]
    assert keys["5100008"].endswith("|ARRHYTHMIA")


def _mapping() -> list[dict[str, str]]:
    path = rulebook.data_root() / rulebook.value("legacy-country", "mapping")
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_the_legacy_country_mapping_is_one_code_per_name_with_its_evidence():
    rows = _mapping()
    assert rows and set(rows[0]) == {"fda_value", "iso2", "evidence"}
    names = [r["fda_value"] for r in rows]
    assert len(names) == len(set(names))
    for r in rows:
        assert re.fullmatch(r"[A-Z]{2}", r["iso2"]), r
        assert r["evidence"].strip(), r
    for code, name in fakefda.LEGACY_COUNTRY.items():
        assert {"fda_value": name, "iso2": code} in [
            {k: r[k] for k in ("fda_value", "iso2")} for r in rows
        ]


def test_a_legacy_country_the_mapping_does_not_know_stops_the_build(tmp_path):
    folder = fakefda.write_input(tmp_path / "raw", as_zips=False, quarters=("2012q3",))
    demo = folder / "2012q3" / "ascii" / "DEMO12Q3.TXT"
    demo.write_bytes(demo.read_bytes().replace(b"$CANADA$", b"$ATLANTIS$"))
    with pytest.raises(ReleaseError, match="ATLANTIS"):
        build_release(folder, tmp_path / "out")
    assert not (tmp_path / "out" / "2012Q3").exists()
