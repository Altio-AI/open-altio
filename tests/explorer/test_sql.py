"""Read-only SQL over the live release (POST /api/sql), within the hard limits
of rule sql-limits, and the schema the SQL box lists; and the query behind a
counted question (/api/count's `sql`), which runs here to exactly its counts,
for every field and the filters in combination, with MedDRA's licensed tables
only for a viewer who may see them.

Expected answers are read from the release's own Parquet through `rel`.
Limits are read from the rule; a test that needs a small one runs under
rules_with, a copy of the rules with that one value changed.
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path

import duckdb
import pytest

from open_altio.explorer import counted
from open_altio.explorer.access import Viewer
from open_altio.explorer.context import explorer_of
from open_altio.explorer.sql import single_select
from open_altio.faers import open_release
from open_altio.faers.reader import quoted
from open_altio.rulebook import value
from open_altio.testing.countedquestions import DRUG, QUESTIONS, REACTIONS, by_value
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


# the query behind a count --------------------------------------------------------------------

BY = counted.choices()
LICENSED = ("reac_meddra_T", "indi_meddra_T", "meddra_pt")  # what a count by today's PT reads


def every_row(client, sql: str, headers: dict[str, str] | None = None) -> list[list]:
    """Every row a query gives in Tables and SQL, page by page."""
    first = run(client, sql, 1, **(headers or {}))
    assert first.status_code == 200, first.text
    got = first.json()
    rows = list(got["rows"])
    for page in range(2, -(-got["total"] // got["size"]) + 1):
        rows += cells(run(client, sql, page, **(headers or {})))
    return rows


def runs_to_its_counts(client, ask, headers: dict[str, str] | None = None, **question) -> dict:
    """The question counted; its `sql`, run in Tables and SQL, gives exactly the counts the
    answer gives, in the order it gives them."""
    got = ask(client, "/api/count", headers=headers, **question)
    assert got["check"]["agrees"] is True, got["check"]
    assert got["sql"] and got["why"] == {}
    rows = every_row(client, got["sql"], headers)
    assert rows == got["check"]["counts"]
    assert by_value(got["by"], rows) == by_value(got["by"], got["counts"])
    if got["by"] != "event":  # an event's name may differ in its capitals; its order with it
        assert [v for v, _ in rows] == [v for v, _, _ in got["counts"]]
    return got


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda q: "&".join(q) or "nothing")
def test_every_counts_query_runs_in_tables_and_sql_to_its_counts(question, client, ask, release):
    """And on the release as downloaded, opened with open_release."""
    downloaded = open_release(release)
    for by in BY:
        if by in question or (by == "outcome" and "outcome" in question):
            continue  # refused: a case can give several outcomes
        got = runs_to_its_counts(client, ask, by=by, **question)
        assert not any(name in got["sql"] for name in LICENSED)
        assert [list(r) for r in downloaded.execute(got["sql"]).fetchall()] == got["check"][
            "counts"
        ]
    downloaded.close()


@pytest.mark.parametrize("question", REACTIONS, ids=lambda q: "&".join(q))
def test_with_meddra_a_count_by_todays_terms_runs_on_its_licensed_tables(
    question, licensed_client, ask
):
    """Its licensed tables are named only where reactions or indications are read: a count by
    event, or a question choosing reactions or what the drug was taken for."""
    for by in BY:
        sql = runs_to_its_counts(licensed_client, ask, by=by, **question)["sql"]
        reactions, indications = by == "event" or "pt" in question, "indication" in question
        named = {name for name in LICENSED if name in sql}
        want = {"reac_meddra_T"} if reactions else set()
        want |= {"indi_meddra_T"} if indications else set()
        assert named == want | ({"meddra_pt"} if want else set())


ANN = {"X-Viewer": "ann"}  # shown today's PTs, but not MedDRA's licensed part
ANN_MEDDRA = {"X-Viewer": "ann+meddra"}


def test_a_viewer_without_meddras_licensed_part_gets_no_query_naming_it(
    people, licensed_release, ask
):
    web = people(licensed_release)
    for by in BY:
        got = ask(web, "/api/count", headers=ANN, by=by, product=DRUG, pt="Nausea")
        assert got["sql"] is None and got["why"] == {"sql": counted.LICENSED}
        assert got["check"]["agrees"] is True
        runs_to_its_counts(web, ask, headers=ANN_MEDDRA, by=by, product=DRUG, pt="Nausea")
    for name in LICENSED:  # nor a table of it to query
        assert run(web, f"SELECT count(*) FROM {name}", **ANN).status_code == 400
        assert run(web, f"SELECT count(*) FROM {name}", **ANN_MEDDRA).status_code == 200
    # a count that reads no reaction names no licensed table, so it runs for them too
    runs_to_its_counts(web, ask, headers=ANN, by="sex", product=DRUG)


def test_a_viewer_shown_fdas_text_gets_a_query_over_fdas_text(hooked, licensed_release, ask):
    shown = Viewer(id="fda", meddra=False, who=False, todays_names=False)
    web = hooked(viewer=shown, release_dir=licensed_release)
    for by in ("event", "sex"):
        got = runs_to_its_counts(web, ask, by=by, product=DRUG, pt=["Headache", "Nausea"])
        assert not any(name in got["sql"] for name in LICENSED)


def test_a_question_not_counted_again_has_no_query(client, ask):
    got = ask(client, "/api/count", by="sex", product=DRUG, points="3")
    assert got["sql"] is None and got["why"] == {"sql": counted.NOT_COUNTED_AGAIN}


# a value in each place the query writes one, each holding a quote or SQL text
SNEAKY = "x'); DELETE FROM case_latest_T; --"
WRITTEN: list[dict] = [
    {"product": f"it's{SNEAKY}"},
    {"product": DRUG, "include": f"A'B{SNEAKY}", "exclude": "C' OR '1'='1", "unit": "exact"},
    {"dprod": ["valsartan", f"x' OR 1=1 --{SNEAKY}"], "drole": ["PS", "SS"]},
    {"drug": "aspirin' OR 'a'='a", "role": ["PS", "PS' OR '1'='1"]},
    {"pt": ["Nausea", "Nausea' OR '1'='1"], "reaction": f"Headache{SNEAKY}"},
    {"product": DRUG, "country": ["US", "US' OR '1'='1"], "sex": ["F", "F'--"]},
    {"sender": f"eli lilly and co{SNEAKY}"},
    {"product": DRUG, "age": "$v1", "reporter": "1' OR '1'='1", "received_from": "2012-05-03'--"},
    {"product": "a\0b", "outcome": ["DE", "DE'; DROP VIEW outc_latest_T; --"]},
]


@pytest.mark.parametrize("question", WRITTEN, ids=lambda q: "&".join(q))
def test_a_value_holding_a_quote_or_sql_is_written_as_a_constant_and_changes_nothing(
    question, client, ask, rel
):
    (cases,) = rel.rows("SELECT count(*) FROM case_latest_T")[0]
    for by in ("sex", "event", "year"):
        got = runs_to_its_counts(client, ask, by=by, **question)
        assert single_select(got["sql"])  # one SELECT, whatever the values hold
        if "country" in question:  # a country is read as given, so written in as given
            assert quoted(question["country"][1]) in got["sql"]
    assert cells(run(client, "SELECT count(*) FROM case_latest_T")) == [[cases]]


def test_a_counts_query_made_to_change_the_release_is_refused(client, ask, rel, tmp_path):
    got = ask(client, "/api/count", by="sex", product=DRUG)
    target = tmp_path / "out.csv"
    for changed in (
        f"{got['sql']}; DELETE FROM case_latest_T",
        f"CREATE TABLE counted AS {got['sql']}",
        f"COPY ({got['sql']}) TO '{target}'",
        f"INSERT INTO case_latest_T {got['sql']}",
    ):
        answer = run(client, changed)
        assert answer.status_code == 400 and refusal(answer)
    assert not target.exists()
    assert every_row(client, got["sql"]) == got["check"]["counts"]  # nothing was changed


# a product's own instance, within limits it names ---------------------------------------


def own(release, tmp_path, **limits):
    """A service of a caller's own over the invented release, spilling under tmp_path."""
    from open_altio.explorer.release import LiveRelease
    from open_altio.explorer.sql import SqlService

    tmp_path.mkdir(parents=True, exist_ok=True)
    return SqlService(LiveRelease(release), limits=limits or None, home=tmp_path)


def disk(folder: Path) -> int:
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())


SPILLING = "SELECT i, md5(i::VARCHAR) AS h FROM range(3000000) t(i) ORDER BY h"  # sorts past memory


def test_a_query_needing_more_than_the_spill_limit_fails_and_leaves_the_disk_under_it(
    release, tmp_path
):
    from open_altio.explorer.sql import LimitHit

    cap = 20 * 1024 * 1024
    service = own(
        release,
        tmp_path / "capped",
        memory_limit="64MB",
        threads=1,
        max_temp_directory_size=f"{cap}B",
    )
    db = service.current(classes=True, by_pt=True)
    settings = db.run("SELECT current_setting('max_temp_directory_size')").rows[0][0]
    assert settings.endswith("MiB") or settings.endswith("MB")
    with pytest.raises(LimitHit) as hit:
        db.run(SPILLING)
    assert hit.value.outcome == "memory"
    assert disk(tmp_path / "capped") <= cap
    assert db.run("SELECT 42").rows == [(42,)]  # still answering
    roomy = own(release, tmp_path / "roomy", memory_limit="64MB", threads=1).current(
        classes=True, by_pt=True
    )  # the same query, with no spill limit, runs: it is the limit that stopped it
    assert roomy.run(SPILLING).total == 3000000


def test_a_second_instances_slow_query_leaves_the_explorers_own_answering(
    client, release, tmp_path
):
    import threading

    db = own(release, tmp_path, memory_limit="256MB", threads=1).current(classes=True, by_pt=True)
    with rules_with(tmp_path / "rules", {"sql-limits": {"timeout_seconds": 3}}):
        slow = threading.Thread(target=lambda: _quietly(db.run, HEAVY), daemon=True)
        slow.start()
        time.sleep(0.5)
        started = time.monotonic()
        assert cells(run(client, "SELECT 1")) == [[1]]
        assert time.monotonic() - started < 5
        assert slow.is_alive()  # still busy while the explorer answered
        slow.join(15)
        assert not slow.is_alive()


def _quietly(call, *args):
    with contextlib.suppress(Exception):  # the thread's end is not what the test reads
        call(*args)


def test_with_no_limits_the_settings_are_the_rules(release, tmp_path):
    from open_altio.explorer.release import LiveRelease
    from open_altio.explorer.sql import SqlService

    db = SqlService(LiveRelease(release)).current(classes=True, by_pt=True)
    gb = value("sql-limits", "memory_limit_gb")
    got = db.run("SELECT current_setting('memory_limit'), current_setting('threads')").rows
    assert got == [(f"{float(gb):.1f} GiB", int(value("sql-limits", "threads")))]
    given = own(release, tmp_path, memory_limit="512MB", threads=1)
    given = given.current(classes=True, by_pt=True)
    assert given.run("SELECT current_setting('threads')").rows == [(1,)]
