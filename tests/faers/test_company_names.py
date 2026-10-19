"""A sender's spellings count under one company name in either era, read from the release only.
Rule: rules/company-names.md. The fake quarters send three cases under two spellings of one company
in the mapping (fakefda.LILLY), one of them a legacy case."""

from __future__ import annotations

import csv

import duckdb

from open_altio import rulebook
from open_altio.faers import not_given
from open_altio.faers.derive import direct_report, no_company
from open_altio.faers.insights.cards.publishing import SENDER_SPELLINGS
from open_altio.faers.reader import quoted
from open_altio.testing import fakefda


def _mapping_path() -> str:
    return (rulebook.data_root() / rulebook.value("company-names", "mapping")).as_posix()


def _mapping() -> list[dict[str, str]]:
    with open(_mapping_path(), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _company() -> dict[str, str]:
    return {r["fda_value"]: r["company"] for r in _mapping()}


def test_each_fda_spelling_maps_to_exactly_one_company_with_its_evidence():
    rows = _mapping()
    assert rows and set(rows[0]) == {"fda_value", "company", "how", "evidence", "cases"}
    spellings = [r["fda_value"] for r in rows]
    assert len(spellings) == len(set(spellings))
    for r in rows:
        assert r["company"].strip() and r["evidence"].strip(), r


def test_each_known_pair_of_one_senders_spellings_lands_in_one_company():
    company = _company()
    for _, short, long in SENDER_SPELLINGS:
        assert company[short] == company[long], (short, long)


# a firm's earlier or later name beside it, the name taken at a merger included
RENAMED = [
    ("LUITPOLD", "AMERICAN REGENT"),
    ("CONCORDIA", "ADVANZ PHARMA"),
    ("WESTWARD", "HIKMA"),
    ("BIOGEN IDEC", "BIOGEN"),
    ("STRIDES ARCOLAB LIMITED", "STRIDES"),
    ("AVENTIS", "SANOFI AVENTIS"),
    ("SANOFI AVENTIS", "SANOFI"),
    ("HORIZON", "HORIZON THERAPEUTICS"),
    ("JIANGSU HENGRUI MEDICINE", "JIANGSU HENGRUI PHARMACEUTICALS CO., LTD."),
    ("BIOVITRUM AB.", "SWEDISH ORPHAN BIOVITRUM"),
    ("SANKYO PHARMA INC.", "DAIICHI SANKYO INC."),
]

# FDA's FAERS name for a firm formed by a merger before FAERS began in 2012, beside the name the
# firm took at the merger
FAERS_NAMES = [
    ("DAIICHI", "DAIICHI SANKYO INC."),
    ("KYOWA", "KYOWA KIRIN PHARMACEUTICAL DEVELOPMENT"),
    ("SWEDISH ORPHAN", "SWEDISH ORPHAN BIOVITRUM"),
    ("BIOVITRUM", "SWEDISH ORPHAN BIOVITRUM"),
]


def test_a_renamed_company_is_never_counted_under_its_other_name():
    company = _company()
    for old, new in RENAMED:
        assert company[old] != company[new], (old, new)


def test_fdas_faers_name_for_a_firm_merged_before_faers_counts_under_that_firm():
    company = _company()
    for short, merged in FAERS_NAMES:
        assert company[short] == company[merged], (short, merged)
        assert "2012" in next(r for r in _mapping() if r["fda_value"] == short)["evidence"]
    # a name from before the merger is not FDA's FAERS name: it stays as FDA wrote it
    assert "DAIICHI PHARMACEUTICAL CO., LTD." not in company


def test_an_aers_spelling_or_account_code_counts_under_the_company_it_names():
    company = _company()
    assert company["PFIZERINC"] == company["PFIZER INC"] == company["PFIZER"]
    assert company["AZPRODUW00"] == company["ASTRAZENECA"]
    # the earlier name keeps its own company in AERS too
    assert company["BIOGEN IDEC INC."] == company["BIOGEN IDEC"] != company["BIOGEN"]
    # an account code is mapped only with the drugs behind it written down
    for code in ("AZPRODUW00", "NOVOPROD", "ALXNEU", "GNEFDAAERSPRD"):
        assert "drug" in next(r for r in _mapping() if r["fda_value"] == code)["evidence"]


def test_a_parent_with_other_drugs_is_not_its_subsidiary():
    company = _company()
    assert company["AVADEL PHARMACEUTICALS"] != company["AVADEL CNS PHARMA"]


def test_no_sender_that_only_says_unknown_is_a_company():
    unknown = duckdb.sql(
        f"SELECT fda_value FROM read_csv({quoted(_mapping_path())}, header=true, "
        f"all_varchar=true) WHERE {not_given.check('mfr_sndr', 'fda_value')}"
    ).fetchall()
    assert unknown == []


def _no_company(reports: list[tuple[str, str]]) -> dict[tuple[str, str], bool]:
    values = ", ".join(f"({quoted(s)}, {quoted(r)})" for s, r in reports)
    sql = f"SELECT s, r, {no_company('s', 'r')} FROM (VALUES {values}) t(s, r)"
    return {(s, r): bool(n) for s, r, n in duckdb.sql(sql).fetchall()}


def test_a_sender_that_names_no_company_has_none_and_a_company_keeps_its_own():
    fda = rulebook.value("company-names", "fda_sender")
    # FDA's intake on a company report, the rule's names, an ID number as the name, one character
    none = [fda.lower(), *not_given.fields()["mfr_sndr"]["codes"], "039976196:01", " 001307602 "]
    none += ["`", "q", ",..."]
    companies = ["3M", "UCB", "GENERICS [UK] LTD", "SANOFI PASTEUR", "PFIZERINC", "AZPRODUW00"]
    got = _no_company([(s, "EXP") for s in none + companies])
    assert [s for s in none if not got[(s, "EXP")]] == []
    assert [s for s in companies if got[(s, "EXP")]] == []
    # a report sent straight to FDA names no company whoever FDA wrote as its sender
    for d in rulebook.value("company-names", "direct_reports"):
        assert all(_no_company([(fda, d), ("3M", d)]).values())


def _companies(rel) -> dict[str, str | None]:
    return dict(rel.rows("SELECT case_key_T, company_T FROM case_latest_T"))


def test_a_faers_case_counts_under_its_senders_company(rel):
    got = _companies(rel)
    lilly = _company()[fakefda.LILLY[0]]
    assert got["9002002"] == got["9120012"] == lilly
    # a sender the mapping does not hold stays as FDA wrote it, each spelling its own
    assert got["9110011"] == "BETA LABS LTD"
    assert got["9001001"] == "ACME PHARMA, INC."


def test_a_legacy_case_sent_under_a_mapped_spelling_counts_under_that_company(rel):
    got = _companies(rel)
    assert got["5100002"] == got["9002002"] == _company()[fakefda.LILLY[0]]
    assert got["5100002"] != fakefda.LILLY[0]


def test_a_case_counts_under_the_sender_of_its_latest_version(rel):
    versions = dict(
        rel.rows("SELECT caseversion_T, company_T FROM demo_T WHERE case_key_T = '9004004'")
    )
    # version 2, which FDA published last, came from a company; version 3, the latest, did not
    assert versions[2] == "ACME PHARMA, INC." and versions[3] is None
    assert _companies(rel)["9004004"] is None


def test_a_sender_that_only_says_unknown_has_no_company(rel):
    assert _companies(rel)["9130013"] is None


def test_a_report_sent_straight_to_fda_has_no_company_whatever_its_sender(rel):
    assert rel.case_keys(direct_report("c.rept_cod")) == {"faers/9004004"}
    assert rel.rows(
        "SELECT mfr_sndr, company_T FROM case_latest_T WHERE case_key_T = '9004004'"
    ) == [(rulebook.value("company-names", "fda_sender"), None)]


def test_fdas_sender_is_unchanged(rel):
    got = dict(rel.rows("SELECT case_key_T, mfr_sndr FROM case_latest_T"))
    lilly, lilly_long = fakefda.LILLY
    assert (got["5100002"], got["9002002"], got["9120012"]) == (lilly, lilly, lilly_long)
    assert got["9130013"] == "UNKNOWN MANUFACTURER"


def test_the_duplicate_rules_compare_fdas_sender_not_the_company(rel):
    keys = dict(rel.rows("SELECT case_key_T, dup_number_key_T FROM case_dup_T"))
    assert keys["9120012"].startswith(f"{fakefda.LILLY[1]}|")
    assert keys["9002002"].startswith(f"{fakefda.LILLY[0]}|")
