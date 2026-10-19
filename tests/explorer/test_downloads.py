"""What the Tables page offers to download here, and a SQL result whole as a
file (POST /api/sql/download; rules sql-result-download, sql-limits and
export-csv-row-cap). The filtered export is test_export.py's.

Run on its own, the explorer has the release's tables on this machine, so
/api/downloads says where they are rather than offering them. Limits come
from the rules; a test that needs a small one runs under rules_with.
"""

from __future__ import annotations

import csv
import io

from open_altio.rulebook import value
from open_altio.testing.rules import rules_with


def sql_download(client, sql: str, fmt: str):
    return client.post("/api/sql/download", json={"sql": sql, "format": fmt})


def test_whole_tables_are_not_offered_here_and_the_page_is_told_where_they_are(
    client, release, rel
):
    got = client.get("/api/downloads")
    assert got.status_code == 200
    body = got.json()
    assert body["on"] is False and body["release"] == rel.manifest["release"]
    assert str(release.resolve() / "parquet") in body["why"]
    assert body["csv_row_cap"] == value("export-csv-row-cap", "csv_row_cap")
    assert body["sql_download_rows"] == value("sql-result-download", "max_rows")


def test_a_sql_result_downloads_whole_as_csv_not_just_the_page_shown(client, rel, tmp_path):
    sql = (
        "SELECT era_T, case_key_T, [era_T, case_key_T] AS both_T FROM case_dedup_T "
        "ORDER BY era_T, case_key_T"
    )
    want = rel.rows("SELECT count(*) FROM case_latest_T WHERE dup_kept_T")[0][0]
    assert want > 2
    with rules_with(tmp_path, {"sql-limits": {"rows_shown": 2}}):
        got = sql_download(client, sql, "csv")
    assert got.status_code == 200, got.text
    assert got.headers["content-type"].startswith("text/csv")
    assert ".csv" in got.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(got.text)))
    assert rows[0] == ["era_T", "case_key_T", "both_T"] and len(rows) == want + 1
    # a list joined with ';', as the export joins outcomes_T
    assert all(r[2] == f"{r[0]};{r[1]}" for r in rows[1:])


def test_a_sql_result_downloads_whole_as_parquet(client, rel, parquet_rows):
    got = sql_download(client, "SELECT * FROM drug_dedup_T", "parquet")
    assert got.status_code == 200, got.text
    (kept_drugs,) = rel.rows(
        f"SELECT count(*) FROM drug_latest_T d SEMI JOIN case_latest_T c ON {rel.case_join('d')} "
        "AND c.dup_kept_T"
    )[0]
    assert len(parquet_rows(got.content)) == kept_drugs


def test_a_sql_result_past_the_limit_is_refused_with_a_pointer_to_the_tables(client, tmp_path):
    with rules_with(tmp_path, {"sql-result-download": {"max_rows": 3}}):
        assert sql_download(client, "SELECT * FROM range(3)", "parquet").status_code == 200
        refused = sql_download(client, "SELECT * FROM range(4)", "parquet")
    assert refused.status_code == 409
    words = refused.json()["problem"]
    assert (
        "4 rows" in words and "more than the 3" in words and "Download the tables it reads" in words
    )


def test_csv_of_a_sql_result_stops_at_the_cap_with_its_header(client, tmp_path):
    with rules_with(tmp_path, {"export-csv-row-cap": {"csv_row_cap": 5}}):
        assert len(sql_download(client, "SELECT * FROM range(4)", "csv").text.splitlines()) == 5
        refused = sql_download(client, "SELECT * FROM range(5)", "csv")
        assert refused.status_code == 409 and "Download it as Parquet" in refused.json()["problem"]
        assert sql_download(client, "SELECT * FROM range(5)", "parquet").status_code == 200


def test_a_refused_statement_downloads_nothing(client):
    got = sql_download(client, "DROP TABLE demo", "csv")
    assert got.status_code == 400 and got.json()["problem"]


def test_a_sql_download_needs_a_known_format(client):
    got = sql_download(client, "SELECT 1", "xlsx")
    assert got.status_code == 400 and got.json()["problem"]
