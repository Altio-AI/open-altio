"""Each drug record's ingredients (rule drug-names): by name, by FDA's prod_ai
where the name has none, combinations whole and per ingredient, the trial mark
and where every answer came from, on a few invented drug records and the
invented dictionary (open_altio.testing.fakediana)."""

from __future__ import annotations

import duckdb
import pytest

from open_altio.faers.drugnames import dictionary, substances
from open_altio.testing import fakediana
from open_altio.testing.rules import rules_with

# (drug_seq, drugname, prod_ai): one invented report's drug records
RECORDS = [
    ("1", "HUMIRA (ADALIMUMAB )", None),  # by name, through DiAna's key
    ("2", "Bayer Low Dose", "ASPIRIN"),  # DiAna lists the name with no substance: prod_ai, whole
    ("3", "MY OWN COMBINATION", "SACUBITRIL\\VALSARTAN"),  # prod_ai split on FDA's backslash
    ("4", "SOMETHING ELSE", "ENTRESTO\\ASPIRIN"),  # a part that is a combination adds all of it
    ("5", "NOT LISTED", "ASPIRIN\\NOT LISTED"),  # a part not found: no answer
    ("6", "ENTRESTO", None),  # DiAna's combination out of order, sorted
    ("7", "BLINDED LCZ696", None),  # a trial mark
    ("8", "VEVYE", None),  # a name DiAna writes two ways
    ("9", "TECFIDERA", "DIMETHYL FUMARATE"),  # our correction
    ("10", "STUDY DRUG", None),
    ("11", None, None),
]


@pytest.fixture
def built(tmp_path):
    path = fakediana.write_dictionary(tmp_path / "DiAna_dictionary.csv")
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE drug_latest_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
        "drug_seq VARCHAR, drugname VARCHAR, prod_ai VARCHAR)"
    )
    con.executemany(
        "INSERT INTO drug_latest_T VALUES ('faers', '1001', '2026q2', ?, ?, ?)", RECORDS
    )
    # since 2024Q4 one drug record can be written on several rows, one per dosage regimen
    con.execute(
        "INSERT INTO drug_latest_T VALUES "
        "('faers', '1001', '2026q2', '1', 'HUMIRA (ADALIMUMAB )', NULL)"
    )
    with rules_with(tmp_path, {dictionary.RULE: {"sha256": dictionary.sha256(path)}}):
        entry = substances.build(con, path)
    rows = con.execute(
        "SELECT drug_seq, substance_T, substance_source_T, diana_trial_T FROM drug_substance_T"
    ).fetchall()
    return con, entry, {seq: (sub, source, trial) for seq, sub, source, trial in rows}


def test_one_row_per_drug_record_whatever_its_rows(built):
    con, _, got = built
    assert len(got) == len(RECORDS)
    assert con.execute("SELECT count(*) FROM drug_latest_T").fetchone()[0] == len(RECORDS) + 1


def test_a_name_finds_its_ingredient_through_dianas_key(built):
    assert built[2]["1"] == ("adalimumab", "diana_name", False)


def test_where_the_name_has_none_prod_ai_is_read_whole_or_in_parts(built):
    got = built[2]
    assert got["2"] == ("acetylsalicylic acid", "diana_prod_ai", False)
    assert got["3"] == ("sacubitril;valsartan", "diana_prod_ai", False)
    assert got["4"] == ("acetylsalicylic acid;sacubitril;valsartan", "diana_prod_ai", False)


def test_a_prod_ai_with_a_part_not_found_and_a_name_not_found_give_none(built):
    got = built[2]
    assert got["5"] == (None, "none", False)
    assert got["11"] == (None, "none", False)


def test_combinations_are_sorted_and_trial_marks_kept_apart(built):
    got = built[2]
    assert got["6"] == ("sacubitril;valsartan", "diana_name", False)
    assert got["7"] == ("sacubitril;valsartan", "diana_name", True)
    assert got["10"] == ("unspecified", "diana_name", True)


def test_our_names_and_corrections_say_they_are_ours(built):
    got = built[2]
    assert got["8"] == ("ciclosporin", "correction", False)
    assert got["9"] == ("dimethyl fumarate", "correction", False)


def test_one_row_per_record_and_ingredient(built):
    con = built[0]
    rows = con.execute(
        "SELECT drug_seq, ingredient_T FROM drug_ingredient_T ORDER BY 1, 2"
    ).fetchall()
    assert [r for r in rows if r[0] == "4"] == [
        ("4", "acetylsalicylic acid"),
        ("4", "sacubitril"),
        ("4", "valsartan"),
    ]
    assert not [r for r in rows if r[0] in ("5", "11")]


def test_the_entry_counts_drug_records_by_source(built):
    _, entry, _ = built
    assert entry["present"] is True
    assert entry["tables"] == list(substances.TABLES)
    # records, never rows: the second dose row of record 1 is not counted again
    assert entry["drug_records"] == len(RECORDS)
    assert entry["records_by_source"] == {
        "diana_name": 4,
        "diana_prod_ai": 3,
        "correction": 2,
        "none": 2,
    }
    assert entry["unmapped_records"] == 2
    assert entry["unmapped_share"] == round(100 * 2 / len(RECORDS), 2)


def test_corrections_that_change_nothing_are_listed(built):
    _, entry, _ = built
    unused = {c["substance"] for c in entry["unused_corrections"]}
    assert "dimethyl fumarate" not in unused
    assert "epoetin beta" in unused  # no NeoRecormon in the invented dictionary


def test_without_a_dictionary_nothing_is_built_and_the_entry_says_why():
    con = duckdb.connect()
    assert substances.build(con, None) == {"present": False, "reason": "no DiAna dictionary given"}
    assert con.execute("SELECT count(*) FROM duckdb_tables()").fetchone()[0] == 0
