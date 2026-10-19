"""The release carries the explorer's database.

The explorer queries one DuckDB file in the release folder, built from the
release's own Parquet: a case table holding what the filters need, child
tables for the drill-in, and term tables sorted so drug and reaction filters
read only the rows they match. Checked here only through the release folder.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers import (
    EXPLORER_FILE,
    build_explorer_db,
    open_explorer,
    open_release,
)
from open_altio.faers.explorer_db import build_connection, parts
from open_altio.faers.schema import RAW_COLUMNS
from open_altio.rulebook import UserRules
from open_altio.testing import fakefda

COMPARE_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compare_explorer_db.py"


@pytest.fixture(scope="module")
def ex(release):
    con = open_explorer(release)
    yield con
    con.close()


def rows(con, sql, *params):
    return con.execute(sql, params).fetchall()


def test_the_release_lists_its_explorer_database(rel, release):
    entry = rel.manifest["explorer"]
    assert entry["file"] == EXPLORER_FILE
    assert (release / EXPLORER_FILE).stat().st_size == entry["bytes"]
    assert (
        entry["tables"]["explorer_case_T"]["rows"]
        == rel.manifest["tables"]["case_latest_T"]["rows"]
    )


def test_the_explorer_database_opens_read_only(ex):
    with pytest.raises(duckdb.Error):
        ex.execute("CREATE TABLE scribble_T (x INTEGER)")


def test_it_names_the_release_it_was_built_from(ex, rel):
    assert rows(ex, "SELECT release_T FROM explorer_release_T") == [(rel.manifest["release"],)]


def test_every_case_once_with_its_duplicate_flag(ex, rel):
    want = set(
        rel.rows("SELECT era_T, case_key_T, dup_kept_T, probable_duplicate_T FROM case_latest_T")
    )
    got = rows(
        ex, "SELECT era_T, case_key_T, dup_kept_T, probable_duplicate_T FROM explorer_case_T"
    )
    assert len(got) == len(want) and set(got) == want


def test_case_ids_follow_era_and_case_key(ex):
    got = rows(ex, "SELECT case_id_T, era_T, case_key_T FROM explorer_case_T ORDER BY case_id_T")
    assert [r[0] for r in got] == list(range(1, len(got) + 1))
    assert [r[1:] for r in got] == sorted(r[1:] for r in got)


def test_case_columns_the_filters_need(ex, rel):
    # sex, age, weight and country are the release's own, read by their rules
    cols = (
        "era_T, case_key_T, first_fda_dt_T, group_first_dt_T, event_dt, event_dt_T, age, age_cod, "
        "age_years_T, age_band_T, sex, sex_T, wt_kg_T, country_T, country_source_T, occp_cod, "
        "mfr_sndr"
    )
    want = set(rel.rows(f"SELECT {cols} FROM case_latest_T"))
    got = set(rows(ex, f"SELECT {cols} FROM explorer_case_T"))
    assert got == want
    # the event country, else the reporter's where the event's is no country (country-not-given)
    countries = dict(rows(ex, "SELECT case_key_T, country_T FROM explorer_case_T"))
    assert countries["9130013"] == "GB"
    # the release's country_T: legacy names read as ISO codes, so one filter finds both eras
    assert rows(
        ex,
        "SELECT DISTINCT country_T FROM explorer_case_T WHERE era_T = 'legacy' "
        "AND reporter_country = 'CANADA'",
    ) == [("CA",)]


def test_case_rows_carry_the_duplicate_columns_of_the_release(ex, rel):
    cols = (
        "case_key_T, dup_group_T, group_first_dt_T, dup_rule_T, dup_shown_case_T, "
        "dup_other_cases_T, "
        "no_drug_or_reaction_T, serious_no_drug_or_reaction_T"
    )
    want = {r[0]: r for r in rel.rows(f"SELECT {cols} FROM case_latest_T")}
    got = {r[0]: r for r in rows(ex, f"SELECT {cols} FROM explorer_case_T")}
    assert got == want
    assert got["9021021"][3] == ["aeolus"] and got["9020020"][4] == "9021021"


def test_a_sender_spelling_or_company_name_in_capitals_names_its_companies(ex, rel):
    got: dict[str, set] = {}
    for spelling, company in rows(ex, "SELECT spelling_T, company_T FROM explorer_sender_T"):
        got.setdefault(spelling, set()).add(company)
    lilly = rel.rows("SELECT company_T FROM case_latest_T WHERE case_key_T = '9120012'")[0][0]
    # a spelling names its company in either era, so it names that company alone
    assert got[fakefda.LILLY[0]] == got[fakefda.LILLY[1]] == got[lilly.upper()] == {lilly}
    assert got["BETA LABS LTD"] == {"BETA LABS LTD"}
    # a sender that only says unknown names no company
    assert "UNKNOWN MANUFACTURER" not in got


def test_outcomes_are_listed_on_the_case(ex):
    got = dict(rows(ex, "SELECT case_key_T, outcomes_T FROM explorer_case_T WHERE era_T = 'faers'"))
    assert got["9005005"] == ["HO", "OT"]
    assert got["9013013"] == ["DE"]
    assert got["9001001"] == ["OT"]


def test_drug_terms_hold_the_normalised_name_and_ingredient_with_role(ex):
    got = set(
        rows(
            ex,
            """SELECT t.term_T, t.role_T FROM explorer_drug_term_T t
                          JOIN explorer_case_T c USING (case_id_T)
                          WHERE c.case_key_T = '9004004'""",
        )
    )
    assert got == {("BAYER LOW DOSE", "PS"), ("ASPIRIN", "PS")}
    got = set(
        rows(
            ex,
            """SELECT t.term_T, t.role_T FROM explorer_drug_term_T t
                          JOIN explorer_case_T c USING (case_id_T)
                          WHERE c.case_key_T = '9006006'""",
        )
    )
    assert got == {("IBUPROFEN", "SS"), ("ASPIRIN", "I")}


def test_term_tables_are_sorted_by_term(ex):
    for table in ("explorer_drug_term_T", "explorer_reac_term_T"):
        terms = [r[0] for r in rows(ex, f"SELECT term_T FROM {table}")]  # physical order
        assert terms == sorted(terms)


def test_each_drug_carries_the_ingredients_the_release_read_it_to(ex, rel):
    want = dict(
        rel.rows("""SELECT d.drugname, any_value(s.substance_T) FROM drug_latest_T d
        JOIN drug_substance_T s USING (era_T, primaryid, quarter_T, drug_seq) GROUP BY 1""")
    )
    got = dict(rows(ex, "SELECT drugname, any_value(substance_T) FROM explorer_drug_T GROUP BY 1"))
    assert got == want
    assert got["ENTRESTO"] == "sacubitril;valsartan" and got["VALSARTAN TEVA"] is None


def test_ingredient_tables_hold_each_ingredient_and_each_spelling_with_none(ex):
    entresto = set(
        rows(
            ex,
            """SELECT ingredient_T, substance_T, spelling_T, role_T
        FROM explorer_ingredient_T WHERE spelling_T = 'ENTRESTO'""",
        )
    )
    assert entresto == {
        ("sacubitril", "sacubitril;valsartan", "ENTRESTO", "PS"),
        ("valsartan", "sacubitril;valsartan", "ENTRESTO", "PS"),
    }
    none = {r[0] for r in rows(ex, "SELECT spelling_T FROM explorer_no_ingredient_T")}
    assert "VALSARTAN TEVA" in none and "DIOVAN" not in none
    for table, key in (
        ("explorer_ingredient_T", "ingredient_T"),
        ("explorer_no_ingredient_T", "spelling_T"),
    ):
        terms = [r[0] for r in rows(ex, f"SELECT {key} FROM {table}")]  # physical order
        assert terms == sorted(terms)


def test_drug_names_say_which_ingredients_each_of_fdas_names_was_read_to(ex):
    got = set(
        rows(
            ex,
            """SELECT field_T, substance_T FROM explorer_drug_name_T
        WHERE name_T = 'SACUBITRIL\\VALSARTAN'""",
        )
    )
    assert got == {("prod_ai", "sacubitril;valsartan")}
    assert rows(
        ex, "SELECT substance_T FROM explorer_drug_name_T WHERE name_T = 'VALSARTAN TEVA'"
    ) == [(None,)]


def test_reactions_kept_verbatim_and_matched_case_blind(ex):
    got = rows(
        ex,
        """SELECT r.pt, t.term_T FROM explorer_reac_T r JOIN explorer_case_T c USING (case_id_T)
                      JOIN explorer_reac_term_T t USING (case_id_T)
                      WHERE c.case_key_T = '9007007'""",
    )
    assert got == [("Hepatic enzyme INCREASED", "hepatic enzyme increased")]


def test_child_tables_carry_only_the_kept_quarter(ex):
    got = rows(
        ex,
        """SELECT r.pt FROM explorer_reac_T r JOIN explorer_case_T c USING (case_id_T)
                      WHERE c.case_key_T = '9005005'""",
    )
    assert got == [("Vomiting",)]


def test_child_tables_for_the_drill_in(ex, rel):
    for child in ("drug", "reac", "outc", "ther", "indi"):
        n = rows(ex, f"SELECT count(*) FROM explorer_{child}_T")[0][0]
        assert n == rel.manifest["tables"][f"{child}_latest_T"]["rows"], child


def test_each_drug_and_therapy_row_carries_its_clean_values_beside_fdas(ex, rel):
    onset = "time_to_onset_T, time_to_onset_reason_T"
    want = rel.rows(f"""SELECT d.primaryid, d.drug_seq, {onset} FROM drug_latest_T d
        JOIN drug_onset_T USING (era_T, primaryid, quarter_T, drug_seq) ORDER BY ALL""")
    got = rows(
        ex,
        f"""SELECT c.primaryid, d.drug_seq, {onset} FROM explorer_drug_T d
        JOIN explorer_case_T c USING (case_id_T) ORDER BY ALL""",
    )
    assert got == want and any(r[3] for r in got)
    clean = "start_dt, start_dt_T, start_dt_prec_T, end_dt_T, end_dt_prec_T, dur_days_T"
    want = rel.rows(f"SELECT primaryid, dsg_drug_seq, {clean} FROM ther_latest_T ORDER BY ALL")
    got = rows(
        ex,
        f"""SELECT c.primaryid, t.dsg_drug_seq, {clean} FROM explorer_ther_T t
        JOIN explorer_case_T c USING (case_id_T) ORDER BY ALL""",
    )
    assert got == want


def test_explorer_tables_and_derived_columns_end_in_the_suffix(ex):
    suffix = rulebook.value("transformed-suffix-T", "derived_suffix")
    fda = {c for cols in RAW_COLUMNS.values() for c in cols}
    for (table,) in rows(ex, "SELECT table_name FROM duckdb_tables()"):
        assert table.endswith(suffix)
        for (col,) in rows(
            ex, f"SELECT column_name FROM duckdb_columns() WHERE table_name = '{table}'"
        ):
            assert col in fda or col.endswith(suffix), f"{table}.{col}"


def test_open_release_reads_tables_and_views_from_the_folder(release, rel):
    con = open_release(release)
    try:
        assert rows(con, "SELECT count(*) FROM case_dedup_T") == [
            (rel.step("kept_after_duplicates")["count"]["total"],)
        ]
        assert (
            rows(con, "SELECT count(*) FROM drug_latest_T")[0][0]
            == rel.manifest["tables"]["drug_latest_T"]["rows"]
        )
    finally:
        con.close()


# Two class tables as one statement each over the whole release: what the quarters' parts must
# add up to.
WHOLE_RELEASE = {
    "explorer_atc_drug_T": """
        WITH several AS (
          SELECT era_T, primaryid, quarter_T, drug_seq,
                 list_sort(list_distinct(list(atc_code_T))) AS codes_T
          FROM atc_drug_codes_T GROUP BY ALL HAVING count(DISTINCT atc_code_T) > 1)
        SELECT c.case_id_T, a.drug_seq, a.atc_code_T, a.atc_level_T, a.atc_chosen_by_T,
               a.atc_possible_codes_T, s.codes_T
        FROM atc_drug_T a JOIN ex.explorer_case_T c USING (era_T, primaryid, quarter_T)
        LEFT JOIN several s USING (era_T, primaryid, quarter_T, drug_seq)""",
    "explorer_atc_could_T": """
        SELECT DISTINCT p.atc_code_T, a.atc_code_T, d.role_T, c.case_id_T
        FROM atc_drug_codes_T p JOIN ex.explorer_case_T c USING (era_T, primaryid, quarter_T)
        JOIN ex.explorer_atc_drug_T a ON a.case_id_T = c.case_id_T AND a.drug_seq = p.drug_seq
        JOIN ex.explorer_drug_T d ON d.case_id_T = c.case_id_T AND d.drug_seq = p.drug_seq
        WHERE d.role_T IS NOT NULL AND (a.atc_code_T IS NULL OR a.atc_level_T < 5)""",
}


def test_class_tables_built_a_quarter_at_a_time_equal_the_whole_release_at_once(
    classes_release,
):
    """A record's possible codes are listed one quarter's cases at a time, so the build fits
    its memory (rule explorer-build-memory); the tables hold what one pass would."""
    con = open_release(classes_release)
    con.execute(f"ATTACH '{classes_release / EXPLORER_FILE}' AS ex (READ_ONLY)")
    try:
        listed = rows(
            con,
            "SELECT count(DISTINCT quarter_T) FROM (SELECT quarter_T FROM atc_drug_codes_T "
            "GROUP BY era_T, primaryid, quarter_T, drug_seq HAVING count(DISTINCT atc_code_T) > 1)",
        )
        assert listed[0][0] > 1  # records with several codes in more than one quarter
        for table, whole in WHOLE_RELEASE.items():
            got = rows(con, f"SELECT * FROM ex.{table}")
            assert got and sorted(got, key=repr) == sorted(rows(con, whole), key=repr)
    finally:
        con.close()


def test_explorer_database_can_be_rebuilt_for_an_existing_release(release_copy, ex):
    (release_copy / EXPLORER_FILE).unlink()
    done = subprocess.run(
        [sys.executable, "-m", "open_altio.faers", "explorer", str(release_copy)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    con = open_explorer(release_copy)
    try:
        count = "SELECT count(*) FROM explorer_case_T"
        assert rows(con, count) == rows(ex, count)
    finally:
        con.close()


def test_building_twice_replaces_the_file(release_copy):
    first = build_explorer_db(release_copy)
    second = build_explorer_db(release_copy)
    assert first["tables"] == second["tables"]


def test_the_build_is_held_to_the_memory_rule(tmp_path):
    """rules/explorer-build-memory.md: DuckDB's memory limit and threads for the build."""
    con = build_connection(tmp_path / EXPLORER_FILE, spill=tmp_path / "spill")
    same = duckdb.connect(
        config={
            "memory_limit": f"{rulebook.value('explorer-build-memory', 'memory_limit_gb')}GB",
            "max_temp_directory_size": (
                f"{rulebook.value('explorer-build-memory', 'spill_limit_gb')}GB"
            ),
        }
    )
    try:
        for setting in ("memory_limit", "max_temp_directory_size"):
            assert rows(con, f"SELECT current_setting('{setting}')") == rows(
                same, f"SELECT current_setting('{setting}')"
            )
        assert rows(con, "SELECT current_setting('threads')") == [
            (rulebook.value("explorer-build-memory", "threads"),)
        ]
        assert rows(con, "SELECT current_setting('temp_directory')") == [(str(tmp_path / "spill"),)]
    finally:
        con.close()
        same.close()


@pytest.fixture(scope="module")
def compare():
    """scripts/compare_explorer_db.py, which compares two builds of the explorer database."""
    spec = importlib.util.spec_from_file_location("compare_explorer_db", COMPARE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_rebuild_matches_the_first_build_value_for_value_and_in_order(
    compare, release, release_copy, capsys
):
    build_explorer_db(release_copy)
    built = [str(release / EXPLORER_FILE), str(release_copy / EXPLORER_FILE)]
    assert compare.main(built) == 0
    assert "RESULT: every table and view matches" in capsys.readouterr().out


def test_the_comparison_catches_a_changed_value_and_a_changed_order(
    compare, release, tmp_path, capsys
):
    changed = tmp_path / EXPLORER_FILE
    shutil.copy(release / EXPLORER_FILE, changed)
    con = duckdb.connect(str(changed))
    con.execute("UPDATE explorer_reac_T SET pt = pt || 'x' WHERE rowid = 0")
    con.execute("CREATE TABLE resorted AS SELECT * FROM explorer_drug_term_T ORDER BY term_T DESC")
    con.execute("DROP TABLE explorer_drug_term_T")
    con.execute("ALTER TABLE resorted RENAME TO explorer_drug_term_T")
    con.close()
    assert compare.main([str(release / EXPLORER_FILE), str(changed)]) == 1
    out = capsys.readouterr().out
    assert "explorer_reac_T.pt:" in out
    assert "explorer_drug_term_T: storage order differs" in out
    assert "explorer_drug_term_T.term_T" not in out  # same values, only the order moved


def in_parts_of(cases: int) -> UserRules:
    return UserRules(values={"explorer-build-memory": {"cases_per_part": cases}})


def test_the_cases_are_cut_into_parts_in_order():
    with rulebook.use_user_rules(in_parts_of(3)):
        assert parts(7) == [(1, 3), (4, 6), (7, 9)]
        assert parts(6) == [(1, 3), (4, 6)]
        assert parts(0) == [(1, 3)]  # one part, so every table is made, empty or not


def test_tables_built_a_part_of_the_cases_at_a_time_equal_one_pass(
    compare, release, release_copy, capsys
):
    """The case and child tables are written a few cases at a time (rule explorer-build-memory):
    the same rows, values and storage order as the session's build, which wrote each at once."""
    con = open_explorer(release)
    try:
        cases = rows(con, "SELECT count(*) FROM explorer_case_T")[0][0]
    finally:
        con.close()
    assert cases > 3 * 5  # several parts
    assert parts(cases) == [(1, rulebook.value("explorer-build-memory", "cases_per_part"))]
    with rulebook.use_user_rules(in_parts_of(3)):
        build_explorer_db(release_copy)
    built = [str(release / EXPLORER_FILE), str(release_copy / EXPLORER_FILE)]
    assert compare.main(built) == 0
    assert "RESULT: every table and view matches" in capsys.readouterr().out
