"""The cards of the demographics notebook, computed on a few hand-made cases with known answers."""

from __future__ import annotations

import duckdb
import pytest

from open_altio.faers.insights.cards import compute_cards

QUARTERS = [("2013q1", 20131), ("2014q2", 20142), ("2024q1", 20241), ("2025q3", 20253)]
CASE_COLUMNS = (
    "case_key_T, caseid, era_T, quarter_T, sex, age, age_cod, occr_country, reporter_country, "
    "mfr_num"
)
CASES = [
    # the six quarters in which FDA wrote NS for an empty sex
    ("1", "1", "faers", "2013q1", "NS", "40", "YR", "US", "US", "US-A-1"),
    ("2", "2", "faers", "2014q2", "F", None, None, "US", "US", "US-A-2"),
    # an age with no unit, and one in years; case 3's earlier version gives the same number in years
    ("3", "3", "legacy", "2013q1", "M", "63", None, None, "US", None),
    ("4", "4", "faers", "2024q1", None, "8", None, "US", "US", "US-A-4"),
    # EU in place of a member state; case 5's earlier version names FR, case 6's none
    ("5", "5", "faers", "2025q3", "F", "70", "YR", "EU", "EU", "EU-A-5"),
    ("6", "6", "faers", "2025q3", "M", "50", "YR", None, "EU", "DE-A-6"),
    ("7", "7", "faers", "2025q3", "F", "30", "YR", "US", "US", "US-A-7"),
    ("8", "8", "faers", "2025q3", "M", "20", "YR", "JP", "JP", "JP-A-8"),
]
VERSIONS = [
    ("3", "legacy", "63", "YR", None),
    ("4", "faers", "8", "DEC", "US"),
    ("5", "faers", "70", "YR", "FR"),
    ("6", "faers", "50", "YR", "EU"),
]


@pytest.fixture
def cards() -> dict[str, dict]:
    con = duckdb.connect()
    con.execute("CREATE TABLE quarters_T (quarter_T VARCHAR, qnum_T INTEGER)")
    con.executemany("INSERT INTO quarters_T VALUES (?, ?)", QUARTERS)
    con.execute(
        "CREATE TABLE case_latest_T ("
        + ", ".join(f"{c.strip()} VARCHAR" for c in CASE_COLUMNS.split(","))
        + ")"
    )
    con.executemany(f"INSERT INTO case_latest_T VALUES ({', '.join('?' * 10)})", CASES)
    con.execute(
        "CREATE TABLE demo_T (caseid VARCHAR, era_T VARCHAR, age VARCHAR, age_cod VARCHAR, "
        "occr_country VARCHAR)"
    )
    con.executemany("INSERT INTO demo_T VALUES (?, ?, ?, ?, ?)", VERSIONS)
    ids = ["sex_not_specified_for_empty", "ages_without_a_unit", "european_union_for_member_state"]
    return {c["id"]: c for c in compute_cards(con, ids)}


def _series(card: dict, name: str) -> list:
    return next(s["values"] for s in card["chart"]["series"] if s["name"] == name)


def test_ns_card_counts_ns_and_empty_in_the_six_quarters(cards):
    card = cards["sex_not_specified_for_empty"]
    # 2013Q1 holds an NS case and an AERS case; the six quarters hold three cases, one of them NS
    assert _series(card, "Sex written NS (not specified)") == [50, 0, 0, 0]
    assert (
        "33% of cases say NS (not specified) and 0 of 3 have an empty sex" in card["two_sentences"]
    )
    assert "misses 1 case in those quarters" in card["two_sentences"]
    assert card["tag"] == {"kind": "documented"}


def test_unitless_age_card_counts_only_ages_with_no_unit_and_checks_them_on_other_versions(cards):
    card = cards["ages_without_a_unit"]
    assert sum(_series(card, "Cases with an age but no unit")) == 2
    assert card["title"].startswith("2 cases")
    # case 3 says years elsewhere, case 4 decades: one of the two checked is in years
    assert "years for 50% of 2 cases" in card["two_sentences"]
    assert card["chart"]["note"]["x"] in card["chart"]["x"]["values"]


def test_eu_card_counts_eu_from_either_field_and_the_states_earlier_versions_name(cards):
    card = cards["european_union_for_member_state"]
    assert card["chart"]["x"]["values"] == ["2024Q1", "2025Q3"]
    assert _series(card, "Member state named by an earlier version") == [0, 1]
    assert _series(card, "No member state given") == [0, 1]  # its only other version says EU
    assert card["two_sentences"].startswith("Since 2025Q3, 2 of the 4 cases published (50%)")
    assert "one case in 2" in card["title"]
    assert card["chart"]["note"] == {"x": "2025Q3", "text": "EU replaces the member state"}
