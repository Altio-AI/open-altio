"""Legacy MedDRA terms in MedDRA's spelling, from FAERS's own text (rule legacy-term-spelling)."""

from __future__ import annotations

import duckdb

from open_altio.faers import derive, spelling


def test_a_legacy_term_takes_the_spelling_faers_writes_and_faers_rows_keep_theirs(rel):
    reac = rel.rows("SELECT DISTINCT era_T, pt, pt_spelling_T FROM reac_latest_T")
    assert {(pt, shown) for era, pt, shown in reac if era == "legacy"} == {
        ("HEADACHE", "Headache"),
        ("ARRHYTHMIA", "Arrhythmia"),
    }
    assert all(pt == shown for era, pt, shown in reac if era == "faers")
    indi = rel.rows("SELECT DISTINCT era_T, indi_pt, indi_pt_spelling_T FROM indi_latest_T")
    assert {(t, shown) for era, t, shown in indi if era == "legacy"} == {("PAIN", "Pain")}
    assert all(t == shown for era, t, shown in indi if era == "faers")


def test_the_explorer_database_carries_the_spelling(rel):
    con = duckdb.connect(str(rel.path / "explorer.duckdb"), read_only=True)
    try:
        shown = con.execute("SELECT DISTINCT pt, pt_spelling_T FROM explorer_reac_T").fetchall()
        indi = con.execute(
            "SELECT DISTINCT indi_pt, indi_pt_spelling_T FROM explorer_indi_T"
        ).fetchall()
    finally:
        con.close()
    assert ("HEADACHE", "Headache") in shown and ("PAIN", "Pain") in indi


def test_the_more_common_spelling_wins_and_a_term_faers_never_spells_stays_as_written():
    con = duckdb.connect()
    con.execute("CREATE TABLE case_latest_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR)")
    con.execute(
        "CREATE TABLE reac (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, pt VARCHAR)"
    )
    rows = [
        ("faers", "1", "2019q1", "Drug ineffective"),
        ("faers", "2", "2019q1", "Drug ineffective"),
        ("faers", "3", "2019q1", "Drug Ineffective"),  # a second spelling, on fewer rows
        ("faers", "4", "2012q4", "NEVER SPELLED"),  # in capitals: not a spelling
        ("legacy", "5", "2010q1", "DRUG INEFFECTIVE"),
        ("legacy", "6", "2010q1", "NEVER SPELLED"),
    ]
    con.executemany("INSERT INTO reac VALUES (?, ?, ?, ?)", rows)
    con.execute("INSERT INTO case_latest_T SELECT era_T, primaryid, quarter_T FROM reac")
    con.execute(
        "CREATE TABLE indi (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, indi_pt VARCHAR)"
    )
    for statement in spelling.spelling_tables():
        con.execute(statement)
    con.execute(derive.child_latest("reac"))
    shown = dict(con.execute("SELECT primaryid, pt_spelling_T FROM reac_latest_T").fetchall())
    assert shown == {
        "1": "Drug ineffective",
        "2": "Drug ineffective",
        "3": "Drug Ineffective",
        "4": "NEVER SPELLED",
        "5": "Drug ineffective",
        "6": "NEVER SPELLED",
    }
    assert con.execute(
        "SELECT count(*) FROM reac_latest_T WHERE pt IS DISTINCT FROM upper(pt) "
        "AND era_T = 'legacy'"
    ).fetchone() == (0,)  # FDA's text is unchanged
