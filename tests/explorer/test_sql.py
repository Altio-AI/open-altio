"""Read-only SQL over the live release (POST /api/sql), within the hard limits
of rule sql-limits, and the schema the SQL box lists.

Expected answers are read from the release's own Parquet through `rel`.
Limits are read from the rule; a test that needs a small one runs under
rules_with, a copy of the rules with that one value changed.
"""

from __future__ import annotations

import time
from pathlib import Path

import duckdb
import pytest

from open_altio.explorer.context import explorer_of
from open_altio.rulebook import value
from open_altio.testing.rules import rules_with

HEAVY = "SELECT sum(a.range * b.range) FROM range(100000) a, range(100000) b"  # minutes of work
GREEDY = "SELECT string_agg(repeat('x', 1024)) FROM range(1000000)"  # one huge string, cannot spill


def run(client, sql: str, page: int = 1, **headers: str):
    return client.post("/api/sql", json={"sql": sql, "page": page}, headers=headers)


def cells(answer) -> list[list]:
    got = answer.json()
    assert "rows" in got, got
    return got["rows"]


def refusal(answer) -> str:
    got = answer.json()
    assert got.get("problem"), got
    return got["problem"]


def test_the_query_must_come_as_json(client):
    got = client.post(
        "/api/sql", content='{"sql": "SELECT 1"}', headers={"Content-Type": "text/plain"}
    )
    assert got.status_code == 415
    assert run(client, "SELECT 1").status_code == 200


# answers ---------------------------------------------------------------------------


def test_a_simple_query_returns_the_release_rows(client, rel):
    want = rel.rows("SELECT era_T, count(*) FROM case_latest_T GROUP BY 1 ORDER BY 1")
    got = run(client, "select era_T, count(*) AS n from case_latest_T group by 1 order by 1")
    assert got.status_code == 200, got.text
    assert cells(got) == [[e, n] for e, n in want]
    assert got.json()["columns"] == ["era_T", "n"]
    assert got.json()["total"] == len(want)


def test_the_deduplicated_views_are_queryable(client, rel):
    (want,) = rel.rows("SELECT count(*) FROM case_latest_T WHERE dup_kept_T")[0]
    assert cells(run(client, "SELECT count(*) FROM case_dedup_T")) == [[want]]


def test_a_final_semicolon_and_comments_are_fine(client):
    assert cells(run(client, "-- the answer\nSELECT 42 AS a; -- done")) == [[42]]
    assert cells(run(client, "/* lead */ WITH x AS (SELECT 1 AS a) SELECT a FROM x -- tail")) == [
        [1]
    ]


def test_the_schema_lists_every_table_and_view_with_its_columns(client, rel):
    got = client.get("/api/schema")
    assert got.status_code == 200
    by_name = {t["name"]: t for t in got.json()}
    for table in list(rel.manifest["tables"]) + list(rel.manifest["views"]["views"]):
        assert table in by_name, f"{table} not in the schema"
        assert [c for c, _ in by_name[table]["columns"]] == rel.columns(table), table
    assert by_name["case_dedup_T"]["view"] is True and by_name["demo"]["view"] is False


def test_a_page_holds_rows_shown_rows_and_says_how_many_there_are(client, tmp_path):
    query = "SELECT range FROM range(12) ORDER BY range DESC"
    with rules_with(tmp_path, {"sql-limits": {"rows_shown": 5}}):
        first = run(client, query).json()
        assert [r[0] for r in first["rows"]] == [11, 10, 9, 8, 7]
        assert (first["total"], first["page"], first["size"]) == (12, 1, 5)
        third = run(client, query, page=3).json()
        assert [r[0] for r in third["rows"]] == [1, 0] and third["page"] == 3
        assert run(client, query, page=99).json()["page"] == 3  # past the end: the last page
        assert run(client, "SELECT 1 WHERE false").json()["total"] == 0


def test_memory_and_threads_come_from_the_rule(client):
    gb = value("sql-limits", "memory_limit_gb")
    got = cells(run(client, "SELECT current_setting('memory_limit'), current_setting('threads')"))
    assert got == [[f"{float(gb):.1f} GiB", int(value("sql-limits", "threads"))]]


# limits ----------------------------------------------------------------------------


def test_a_query_past_the_timeout_is_stopped_with_a_clear_message(client, tmp_path):
    with rules_with(tmp_path, {"sql-limits": {"timeout_seconds": 0.5}}):
        started = time.monotonic()
        got = run(client, HEAVY)
        assert time.monotonic() - started < 10
        assert got.status_code == 422
        message = refusal(got)
        assert "0.5 seconds" in message and "Narrow" in message and "full release" in message
        assert run(client, "SELECT 42").status_code == 200  # the slot was given back


def test_a_query_past_the_memory_limit_is_stopped_with_a_clear_message(client, tmp_path):
    with rules_with(tmp_path, {"sql-limits": {"memory_limit_gb": 0.05}}):
        got = run(client, GREEDY)
        assert got.status_code == 422
        message = refusal(got)
        assert "memory" in message and "Narrow" in message and "full release" in message
        assert run(client, "SELECT 42").status_code == 200


def test_a_second_query_from_the_same_viewer_while_one_runs_is_refused(people):
    web = people()
    with explorer_of(web.app).sql.slot("ann"):  # ann's first query, still running
        got = run(web, "SELECT 1", **{"X-Viewer": "ann"})
        assert got.status_code == 429
        assert "already have a query running" in refusal(got)
        # someone else is not held up
        assert run(web, "SELECT 1", **{"X-Viewer": "bo"}).status_code == 200
    assert cells(run(web, "SELECT 1", **{"X-Viewer": "ann"})) == [[1]]


def test_how_many_queries_one_person_may_run_comes_from_the_rule(client, tmp_path):
    slot = explorer_of(client.app).sql.slot
    with rules_with(tmp_path, {"sql-limits": {"concurrent_queries_per_user": 2}}), slot("local"):
        assert run(client, "SELECT 1").status_code == 200
        with slot("local"):
            assert run(client, "SELECT 1").status_code == 429


# no writes, no files ---------------------------------------------------------------


def forbidden(tmp: Path) -> list[str]:
    out = tmp / "out.csv"
    return [
        f"COPY (SELECT 1) TO '{out}'",
        f"copy case_latest_T to '{out}' (FORMAT csv)",
        f"/* harmless */ AtTaCh '{tmp / 'x.duckdb'}' AS x",
        "INSTALL httpfs",
        "-- just a load\nload httpfs",
        "CREATE TABLE t AS SELECT 1",
        "create temp table t (a int)",
        "CREATE VIEW v AS SELECT 1",
        "SET memory_limit = '64GB'",
        "set threads = 64",
        "RESET memory_limit",
        "PRAGMA database_list",
        "/* list */ pragma version",
        f"EXPORT DATABASE '{tmp / 'dump'}'",
        "DROP VIEW case_latest_T",
        "SELECT 1; DROP VIEW case_latest_T",
        "select 1 -- fine so far\n; DrOp VIEW case_latest_T",
        "SELECT 1; SELECT 2",
        "DELETE FROM case_latest_T",
        "DETACH sql_catalog",
        "CALL pragma_version()",
        "EXPLAIN ANALYZE SELECT 1",
        "",
        "SELEC 1",
        "SELECT 1) UNION ALL (SELECT 2",
    ]


@pytest.mark.parametrize("index", range(len(forbidden(Path("/x")))))
def test_statements_other_than_one_select_are_refused(client, rel, tmp_path, index):
    targets = tmp_path / "targets"
    targets.mkdir()
    got = run(client, forbidden(targets)[index])
    assert got.status_code == 400, got.text
    assert refusal(got)
    assert list(targets.iterdir()) == []  # nothing written
    (n,) = rel.rows("SELECT count(*) FROM case_latest_T")[0]
    assert cells(run(client, "SELECT count(*) FROM case_latest_T")) == [[n]]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "select * from READ_TEXT('/etc/passwd')",
        "SELECT * FROM glob('/etc/*')",
        "SELECT * FROM read_parquet('{other}')",
        "SELECT * FROM '{other}'",
    ],
)
def test_select_cannot_read_files_outside_the_release(client, tmp_path, sql):
    other = tmp_path / "other.parquet"
    duckdb.execute(f"COPY (SELECT 'secret' AS s) TO '{other}'")
    got = run(client, sql.format(other=other))
    assert got.status_code == 400
    assert "rows" not in got.json() and "secret" not in got.text


def test_the_configuration_cannot_be_changed_from_a_select(client):
    gb = value("sql-limits", "memory_limit_gb")
    got = run(client, "SELECT * FROM query('SET memory_limit = ''64GB''')")
    assert got.status_code == 400
    assert cells(run(client, "SELECT current_setting('memory_limit')")) == [
        [f"{float(gb):.1f} GiB"]
    ]
