"""drug_route_T over a real release's drug records (rule drug-route).

Slow: reads the drug table of the release named by OPEN_ALTIO_REAL_RELEASE (a
release folder, as for tests/faers/test_parity.py) and builds the cleaned route
over it, in about a minute and under DuckDB's memory limit below.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

from open_altio.faers import route
from open_altio.faers.route import RouteTables, families

pytestmark = pytest.mark.slow

RELEASE = os.environ.get("OPEN_ALTIO_REAL_RELEASE")
KEYS = ", ".join(route.KEY)


@pytest.fixture(scope="module")
def real(tmp_path_factory) -> duckdb.DuckDBPyConnection:
    if not RELEASE or not (Path(RELEASE).expanduser() / "manifest.json").is_file():
        pytest.skip("set OPEN_ALTIO_REAL_RELEASE to a release folder")
    drugs = (Path(RELEASE).expanduser() / "parquet" / "drug_latest_T.parquet").as_posix()
    con = duckdb.connect()
    spill = tmp_path_factory.mktemp("spill")
    con.execute(f"SET memory_limit = '6GB'; SET threads = 4; SET temp_directory = '{spill}'")
    con.execute("SET preserve_insertion_order = false")
    con.execute(f"CREATE VIEW drug_latest_T AS SELECT * FROM read_parquet('{drugs}')")
    route.build(con)
    return con


def test_one_row_per_drug_record_and_no_key_repeated(real):
    records = real.execute(
        f"SELECT count(*) FROM (SELECT DISTINCT {KEYS} FROM drug_latest_T)"
    ).fetchone()
    assert real.execute(f"SELECT count(*) FROM {route.TABLE}").fetchone() == records
    repeated = (
        f"SELECT count(*) FROM (SELECT {KEYS} FROM {route.TABLE} GROUP BY ALL HAVING count(*) > 1)"
    )
    assert real.execute(repeated).fetchone() == (0,)


def test_every_value_is_one_the_rule_names(real):
    t = RouteTables.read()
    codes = {c for (c,) in real.execute(f"SELECT DISTINCT route_T FROM {route.TABLE}").fetchall()}
    assert codes - {None} <= set(t.e2b)
    sources = {
        s for (s,) in real.execute(f"SELECT DISTINCT route_source_T FROM {route.TABLE}").fetchall()
    }
    named = {part for s in sources for part in s.split("+")}
    assert named <= {*route.SOURCES, "disagree", "none"}
    each = f"SELECT DISTINCT unnest(string_split(route_families_T, ';')) FROM {route.TABLE}"
    fams = real.execute(each).fetchall()
    assert {f for (f,) in fams} == set(families()[:-1])


def test_most_suspect_drug_records_have_a_possible_family(real):
    suspect = f"SELECT DISTINCT {KEYS} FROM drug_latest_T WHERE role_cod IN ('PS', 'SS')"
    said, total = real.execute(f"""
        SELECT count(route_families_T), count(*)
        FROM {route.TABLE} r JOIN ({suspect}) s USING ({KEYS})""").fetchone()
    assert said > total / 2  # a broken table would leave most records with none


def test_a_known_family_is_the_only_possible_one(real):
    unknown = families()[-1]
    assert real.execute(f"""
        SELECT count(*) FROM {route.TABLE}
        WHERE (route_family_T <> '{unknown}' AND route_families_T IS DISTINCT FROM route_family_T)
           OR (route_family_T = '{unknown}' AND NOT contains(coalesce(route_families_T, ';'), ';'))
        """).fetchone() == (0,)
