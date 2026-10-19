"""Small releases written by hand for the statistics' tests: the tables cases.count reads, in one
DuckDB, each case of FAERS 2026Q2."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import duckdb
import pytest

from open_altio.faers.dates import ONSET_TABLE

KEY = "era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR"
TABLES = {
    "case_latest_T": "age_band_T VARCHAR, sex_T VARCHAR, init_year_T INTEGER, dup_kept_T BOOLEAN",
    "drug_latest_T": "drug_seq VARCHAR, role_cod VARCHAR",
    "drug_ingredient_T": "drug_seq VARCHAR, ingredient_T VARCHAR",
    "reac_latest_T": "pt VARCHAR",
    ONSET_TABLE: "drug_seq VARCHAR, time_to_onset_T INTEGER, time_to_onset_reason_T VARCHAR",
}


@pytest.fixture
def small_release() -> Callable[..., duckdb.DuckDBPyConnection]:
    """A connection holding the tables named, from rows that start with the case's primaryid:
    case_latest_T (age band, sex, receipt year, kept), drug_latest_T (drug_seq, role),
    drug_ingredient_T (drug_seq, ingredient), reac_latest_T (FDA's term) and drug_onset_T
    (drug_seq, time to onset, why none)."""

    def make(**rows: Sequence[tuple]) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect()
        for table, columns in TABLES.items():
            con.execute(f"CREATE TABLE {table} ({KEY}, {columns})")
            given = rows.get(table, ())
            if given:
                marks = ", ".join(["?"] * (len(given[0]) - 1))
                con.executemany(
                    f"INSERT INTO {table} VALUES ('faers', ?, '2026q2', {marks})", given
                )
        return con

    return make
