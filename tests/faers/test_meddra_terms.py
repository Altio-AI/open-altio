"""FDA's MedDRA terms read to one MedDRA version (rules/meddra-terms.md).

The shared fake release's licensed part holds the invented MedDRA 29.1
(open_altio.testing.fakemeddra), read back only through its files. The same
check runs on each of the three columns that hold MedDRA terms.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers.meddra import MeddraRefused, ascii_folder, build_licensed, load
from open_altio.faers.meddra.terms import COLUMNS, map_terms, term_key
from open_altio.testing.fakemeddra import write_meddra

# FDA's text -> (matched_as_T, pt_code_T, pt_current_T) in the invented 29.1, by column
EXPECTED = {
    "pt": {
        "Headache": ("pt", "94000001", True),
        "Hepatic enzyme INCREASED": ("pt", "94000005", True),  # capitals do not matter
        "ARRHYTHMIA": ("llt", "94000007", False),  # demoted in 29.1: its new PT
        "Lactic acidosis": ("former_name", "94000008", False),  # renamed in 29.1: the history file
    },
    "drug_rec_act": {
        "Head pain": ("llt", "94000001", False),
        "Parkinson^s disease": ("pt", "94000010", True),  # FDA writes the apostrophe as ^ here
    },
    "indi_pt": {
        "PAIN": ("pt", "94000009", True),
        "Dyspepsia": (None, None, False),  # no MedDRA name: left as FDA wrote it
    },
}


def _versions(folder):
    manifest = json.loads((folder / "licensed" / "manifest.json").read_text())
    return manifest["meddra"]["versions"]


def _table(folder, column):
    entry = _versions(folder)["29.1"]["tables"][COLUMNS[column].table]
    rel = duckdb.sql(f"SELECT * FROM read_parquet('{folder / 'licensed' / entry['path']}')")
    rows = (dict(zip(rel.columns, r, strict=True)) for r in rel.fetchall())
    return {r[COLUMNS[column].term]: r for r in rows}


@pytest.mark.parametrize("column", list(COLUMNS))
def test_every_text_of_the_column_maps_to_the_pt_meddra_gives_it(licensed_release, rel, column):
    table = _table(licensed_release, column)
    source = COLUMNS[column].source
    in_release = {
        t for (t,) in rel.rows(f"SELECT DISTINCT {column} FROM {source} WHERE {column} IS NOT NULL")
    }
    assert set(table) == {term_key(column, t) for t in in_release}  # one row per distinct text
    for text, (matched, pt, current) in EXPECTED[column].items():
        row = table[term_key(column, text)]
        assert (row["matched_as_T"], row["pt_code_T"], row["pt_current_T"]) == (
            matched,
            pt,
            current,
        ), text


def test_the_caret_is_read_as_an_apostrophe_only_where_fda_writes_it_so():
    assert rulebook.value("meddra-terms", "apostrophe_as_caret") == ["drug_rec_act"]
    assert term_key("drug_rec_act", "Parkinson^s  Disease") == "parkinson's disease"
    assert term_key("pt", "Parkinson^s disease") == "parkinson^s disease"


def test_the_licensed_manifest_reports_each_column(licensed_release, rel):
    terms = _versions(licensed_release)["29.1"]["terms"]
    columns = terms["columns"]
    assert {c: columns[c]["table"] for c in columns} == {c: COLUMNS[c].table for c in COLUMNS}
    assert columns["pt"]["former_names"] == 1 and columns["pt"]["unmapped"]["texts"] == 0
    assert columns["drug_rec_act"]["unmapped"]["texts"] == 0
    [(rows, first, last)] = rel.rows(
        "SELECT count(*), min(quarter_T), max(quarter_T) FROM indi WHERE indi_pt = 'Dyspepsia'"
    )
    assert columns["indi_pt"]["unmapped"] == {"texts": 1, "rows": rows, "quarters": [first, last]}
    assert terms["quarters_fitting_no_version"] == []


def _mapped(tmp_path, reactions):
    """map_terms over a reac table of (quarter_T, pt) rows, with the invented 29.1."""
    con = duckdb.connect()
    load(con, ascii_folder(write_meddra(tmp_path / "m", "29.1")))
    con.execute("CREATE TABLE reac (quarter_T VARCHAR, pt VARCHAR, drug_rec_act VARCHAR)")
    con.executemany("INSERT INTO reac VALUES (?, ?, NULL)", reactions)
    con.execute("CREATE TABLE indi (quarter_T VARCHAR, indi_pt VARCHAR)")
    return map_terms(con, "29.1")


def test_a_quarter_whose_terms_fit_no_single_version_is_reported(tmp_path):
    # Arrhythmia was a PT until 29.1, Heart rhythm abnormal is one from 29.1, Lactic acidosis
    # from 29.0
    report = _mapped(
        tmp_path,
        [
            ("2026q1", "Arrhythmia"),
            ("2026q1", "Arrhythmia"),
            ("2026q1", "Lactic acidosis"),
            ("2026q1", "Heart rhythm abnormal"),
            ("2026q2", "Heart rhythm abnormal"),
            ("2026q2", "Lactic acidosis"),  # fits 29.1
        ],
    )
    assert report["quarters_fitting_no_version"] == [
        {"quarter": "2026q1", "nearest": "29.0", "rows_off": 1}
    ]


def test_a_reaction_matching_nothing_is_counted_with_its_rows_and_quarters(tmp_path):
    report = _mapped(
        tmp_path, [("2025q4", "Not a term"), ("2026q2", "not  a TERM"), ("2026q2", "Headache")]
    )
    assert report["columns"]["pt"]["unmapped"] == {
        "texts": 1,
        "rows": 2,
        "quarters": ["2025q4", "2026q2"],
    }


def test_a_meddra_file_older_than_the_data_is_refused_in_plain_words(release_copy, tmp_path):
    with pytest.raises(MeddraRefused) as refused:
        build_licensed(release_copy, write_meddra(tmp_path / "m", "28.1"))  # no Lactic acidosis yet
    message = str(refused.value)
    assert message.startswith("1 text in pt (")
    assert "is no name in MedDRA 28.1 or in its history file" in message
    assert "the MedDRA file is older than this release's data" in message
    assert message.endswith("Use the newest MedDRA version.")
    assert not (release_copy / "licensed").exists()
