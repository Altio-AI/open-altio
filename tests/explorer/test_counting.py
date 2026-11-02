"""Cases, never rows: every count a question answers is of distinct cases, so a case that names
the drug on two drug rows and the event on two reaction rows counts once in each count. The
invented case is fakefda.EVENTS_STORY's, built into `events_release`; each question is asked of
that case alone, on its received day.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from open_altio.testing.releasereader import ReleaseReader

ASPIRIN = "acetylsalicylic acid"
DOUBLED = "7605001"  # aspirin on two drug rows, Nausea on two reaction rows


@pytest.fixture
def web(explorer_app, events_release) -> TestClient:
    return TestClient(explorer_app(events_release))


@pytest.fixture
def that_day(events_release) -> dict[str, str]:
    """The question's window: the doubled case's received day alone, which no other case of the
    story shares."""
    reader = ReleaseReader(events_release)
    [(day,)] = reader.rows("SELECT group_first_dt_T FROM case_latest_T WHERE caseid = ?", DOUBLED)
    others = reader.rows(
        "SELECT count(*) FROM case_latest_T WHERE group_first_dt_T = ? AND caseid <> ?",
        day,
        DOUBLED,
    )
    assert others == [(0,)]
    return {"received_from": day.isoformat(), "received_to": day.isoformat()}


def test_the_invented_case_names_the_drug_and_the_event_twice(events_release):
    reader = ReleaseReader(events_release)
    for table, column, named in (
        ("drug_latest_T", "drugname", "ASPIRIN"),
        ("reac_latest_T", "pt", "Nausea"),
    ):
        got = reader.rows(
            f"SELECT count(*) FROM case_latest_T c JOIN {table} t ON {reader.case_join('t')} "
            f"WHERE c.caseid = ? AND t.{column} = ?",
            DOUBLED,
            named,
        )
        assert got == [(2,)], table


def test_a_drugs_events_count_the_case_once(web, that_day, ask):
    got = ask(web, "/api/events", product=ASPIRIN, **that_day)
    [row] = [dict(zip(got["columns"], r, strict=True)) for r in got["rows"]]
    year = int(that_day["received_from"][:4])
    assert row["pt"] == "Nausea"
    assert row["cases"] == row["newest"] == row["serious"] == row["life_threatening"] == 1
    assert row["years"] == [[year, 1]] and row["busiest_year"] == year
    assert row["death"] == 0


def test_the_count_line_and_the_case_list_hold_the_case_once(web, that_day, ask):
    assert ask(web, "/api/summary", product=ASPIRIN, **that_day)["cases"] == 1
    listed = ask(web, "/api/cases", product=ASPIRIN, **that_day)["cases"]
    assert [c["case_key_T"] for c in listed] == [DOUBLED]
