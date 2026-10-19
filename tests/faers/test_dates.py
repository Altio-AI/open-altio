"""Dates read as far as they are known and can be true, and the times worked out from them: the
SQL on small tables made here, then the release built with the rules and without them."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers import build_release, dates, derive
from open_altio.rulebook import UserRules
from open_altio.testing import fakefda
from open_altio.testing.releasereader import ReleaseReader

DATE_RULES = frozenset({"event-date-precision", "date-limits", "time-to-onset", "therapy-duration"})


def _off(*names: str):
    return rulebook.use_user_rules(UserRules(off=frozenset(names)))


# ------------------------------------------------------------- the event date
def _event(era: str, quarter: str, event_dt: str | None, received: str = "20260415"):
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE demo AS SELECT ?::VARCHAR AS era_T, ?::VARCHAR AS quarter_T, "
        "?::VARCHAR AS event_dt, ?::VARCHAR AS init_fda_dt, NULL::VARCHAR AS fda_dt",
        [era, quarter, event_dt, received],
    )
    clean, known = dates.event_date()
    return con.execute(f"SELECT {clean}, {known} FROM demo").fetchone()


@pytest.mark.parametrize(
    ("era", "quarter", "event_dt", "want"),
    [
        ("legacy", "2012q2", "20120301", (None, 6)),  # the 1st: this month
        ("legacy", "2012q2", "20120101", (None, 4)),  # 1 January: this year
        ("legacy", "2012q2", "20120315", (date(2012, 3, 15), 8)),
        ("faers", "2021q2", "20210301", (date(2021, 3, 1), 8)),  # before the padding: as written
        ("faers", "2021q3", "20210601", (None, 6)),
        ("faers", "2026q2", "20250101", (None, 4)),
        ("faers", "2026q2", "202503", (None, 6)),  # FDA's own partial dates stay as they are
        ("faers", "2026q2", "20180230", (None, 8)),  # 30 February is no date
        ("faers", "2026q2", None, (None, None)),
    ],
)
def test_a_padded_event_date_is_known_to_its_month_or_year(era, quarter, event_dt, want):
    assert _event(era, quarter, event_dt) == want


def test_switched_off_every_full_event_date_is_known_to_the_day():
    with _off("event-date-precision"):
        assert _event("faers", "2021q3", "20210601") == (date(2021, 6, 1), 8)
        assert _event("legacy", "2012q2", "20120101") == (date(2012, 1, 1), 8)


@pytest.mark.parametrize(
    ("event_dt", "want"),
    [
        ("20260630", (date(2026, 6, 30), 8)),  # the quarter's last day
        ("20260715", (None, None)),  # after the quarter that published it
        ("20260701", (None, None)),  # read to the month, July is after the quarter
        ("202607", (None, None)),  # a partial date at its own precision
        ("202606", (None, 6)),
        ("2027", (None, None)),
    ],
)
def test_an_event_date_after_its_quarter_gets_no_clean_value(event_dt, want):
    assert _event("faers", "2026q2", event_dt) == want


def test_an_event_date_older_than_any_patient_gets_no_clean_value():
    oldest = rulebook.value("date-limits", "max_age_years")
    assert _event("faers", "2026q2", str(2026 - oldest)) == (None, 4)
    assert _event("faers", "2026q2", str(2026 - oldest - 1)) == (None, None)
    assert _event("faers", "2026q2", "1012", received="") == (None, 4)  # no receipt year, no floor


def test_switched_off_the_limits_read_every_date_as_written():
    with _off("date-limits"):
        assert _event("faers", "2026q2", "20260715") == (date(2026, 7, 15), 8)
        assert _event("faers", "2026q2", "1012") == (None, 4)


# ------------------------------------------------------------- therapy dates and duration
_CASE = (
    "CREATE TABLE case_latest_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
    + ", ".join(
        f"{c} {t}"
        for c, t in zip(
            dates.THERAPY_CASE_COLUMNS, ("DOUBLE", "INTEGER", "VARCHAR", "INTEGER"), strict=True
        )
    )
    + ", event_dt_T DATE)"
)


def _therapy(*rows, age=45.0, event_dt="20200315", received=2026, quarter="2026q2"):
    """ther_latest_T for one case, each row (start_dt, end_dt, dur, dur_cod)."""
    con = duckdb.connect()
    con.execute(_CASE)
    con.execute(
        "INSERT INTO case_latest_T VALUES ('faers', '1', ?, ?, ?, ?, ?, ?)",
        [quarter, age, received, event_dt, len(event_dt) if event_dt else None, None],
    )
    con.execute(
        "CREATE TABLE ther (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
        "dsg_drug_seq VARCHAR, start_dt VARCHAR, end_dt VARCHAR, dur VARCHAR, dur_cod VARCHAR)"
    )
    for r in rows:
        con.execute("INSERT INTO ther VALUES ('faers', '1', ?, '1', ?, ?, ?, ?)", [quarter, *r])
    con.execute(derive.child_latest("ther"))
    return con.execute(
        "SELECT start_dt_T, start_dt_prec_T, end_dt_T, end_dt_prec_T, dur_days_T FROM ther_latest_T"
    ).fetchall()


def test_a_therapy_date_after_its_quarter_gets_no_clean_value():
    assert _therapy(("20260701", "202607", None, None)) == [(None, None, None, None, None)]
    assert _therapy(("20260630", "202606", None, None)) == [(date(2026, 6, 30), 8, None, 6, None)]


def test_a_therapy_date_long_before_birth_gets_no_clean_value():
    before = rulebook.value("date-limits", "before_birth_years")
    born = math.floor(2020 - 45.3)  # the event year less the age, rounded down
    first = born - before
    kept = _therapy((f"{first}0101", f"{first - 1}1231", None, None), age=45.3)
    assert kept == [(date(first, 1, 1), 8, None, None, None)]
    # with no event year, the year FDA first received the case
    assert _therapy((f"{2026 - 45 - before}", None, None, None), event_dt=None)[0][1] == 4
    assert _therapy((f"{2026 - 45 - before - 1}", None, None, None), event_dt=None)[0][1] is None


def test_where_the_age_is_unknown_a_therapy_date_has_the_oldest_patient_floor():
    oldest = rulebook.value("date-limits", "max_age_years")
    for age in (None, -3.0):
        got = _therapy((str(2026 - oldest), str(2026 - oldest - 1), None, None), age=age)
        assert [(r[1], r[3]) for r in got] == [(4, None)]


def test_the_duration_comes_from_the_two_dates_else_from_fda():
    days = rulebook.value("therapy-duration", "unit_days")
    got = _therapy(
        ("20260101", "20260110", "99", "DAY"),  # the dates win
        ("20260110", "20260101", "5", "DAY"),  # the end before the start: FDA's duration
        ("202601", "", "2", "WK"),  # a partial date: FDA's duration
        ("20260101", "", "3", "HR"),  # no end: none is made up from the duration
        ("", "", "1.5", "MON"),
        ("", "", "two", "DAY"),  # not a number
        ("", "", "4", "QTR"),  # not a unit
    )
    assert [r[4] for r in got[:5]] == pytest.approx(
        [10, 5, 2 * days["WK"], 3 / 24, 1.5 * days["MON"]]
    )
    assert [r[4] for r in got[5:]] == [None, None]
    assert got[3][2] is None  # the end date stays empty


def test_a_duration_longer_than_the_patient_could_have_been_treated_is_empty():
    year = rulebook.value("therapy-duration", "unit_days")["YR"]
    longest = rulebook.value("therapy-duration", "max_years_unknown_age")
    assert _therapy(("", "", "11", "YR"), ("", "", "12", "YR"), age=10.0) == [
        (None, None, None, None, pytest.approx(11 * year)),
        (None, None, None, None, None),
    ]
    got = _therapy(("", "", str(longest), "YR"), ("", "", str(longest + 1), "YR"), age=None)
    assert [r[4] for r in got] == [pytest.approx(longest * year), None]


def test_switched_off_there_is_no_duration_and_dates_are_only_typed():
    with _off("therapy-duration", "date-limits"):
        assert _therapy(("20260701", "20260710", "9", "DAY")) == [
            (date(2026, 7, 1), 8, date(2026, 7, 10), 8, None)
        ]


# ------------------------------------------------------------- time to onset
def _onset(event: date | str | None, *starts: tuple, column: str = "time_to_onset_T"):
    """drug_onset_T's `column` for one case published in 2026Q2, whose event date is FDA's text
    (a date: that day written in full), read as the release reads it; therapy lines (drug_seq,
    FDA's start_dt[, its precision when the limits leave it none])."""
    con = duckdb.connect()
    raw = event.strftime("%Y%m%d") if isinstance(event, date) else event
    clean, known = dates.event_date()
    con.execute(
        "CREATE TABLE demo AS SELECT 'faers' AS era_T, '1' AS primaryid, '2026q2' AS quarter_T, "
        "?::VARCHAR AS event_dt, '20260401' AS init_fda_dt, NULL::VARCHAR AS fda_dt",
        [raw],
    )
    con.execute(
        "CREATE TABLE case_latest_T AS SELECT era_T, primaryid, quarter_T, event_dt, "
        f"{clean} AS event_dt_T, {known} AS event_dt_prec_T FROM demo"
    )
    con.execute(
        "CREATE TABLE drug_latest_T AS SELECT 'faers' AS era_T, '1' AS primaryid, "
        "'2026q2' AS quarter_T, unnest(['1', '1', '2', '3']) AS drug_seq"  # 1 twice: two regimens
    )
    con.execute(
        "CREATE TABLE ther_latest_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
        "dsg_drug_seq VARCHAR, start_dt VARCHAR, start_dt_prec_T INTEGER, start_dt_T DATE)"
    )
    for seq, start, *limited in starts:
        prec = limited[0] if limited else len(start)
        day = date(int(start[:4]), int(start[4:6]), int(start[6:])) if prec == 8 else None
        con.execute(
            "INSERT INTO ther_latest_T VALUES ('faers', '1', '2026q2', ?, ?, ?, ?)",
            [seq, start, prec, day],
        )
    con.execute(dates.onset())
    return dict(con.execute(f"SELECT drug_seq, {column} FROM {dates.ONSET_TABLE}").fetchall())


def test_time_to_onset_counts_the_first_dose_as_day_one_once_per_drug_record():
    got = _onset(
        date(2026, 1, 15),
        ("1", "20260110"),
        ("1", "20260105"),  # the record's earliest start
        ("2", "20260115"),  # the same day
        ("3", "20260116"),  # the event before the first dose
    )
    first = rulebook.value("time-to-onset", "first_dose_day")
    assert got == {"1": 10 + first, "2": first, "3": None}


def test_no_time_to_onset_when_a_partial_start_could_be_the_first_dose():
    got = _onset(
        date(2026, 3, 20),
        ("1", "20260315"),
        ("1", "2025"),  # an earlier course, known to the year: the first dose is unknown
        ("2", "20260315"),
        ("2", "202603"),  # the same month: it could be earlier
        ("3", "20260315"),
        ("3", "202604"),  # after the full start: it cannot be the first dose
        ("3", "2019", None),  # outside the limits: no date at all
    )
    assert got == {"1": None, "2": None, "3": 5 + rulebook.value("time-to-onset", "first_dose_day")}


def test_no_time_to_onset_without_both_dates_known_to_the_day_or_with_the_rule_off():
    assert _onset(None, ("1", "20260105")) == {"1": None, "2": None, "3": None}
    with _off("time-to-onset"):
        assert _onset(date(2026, 1, 15), ("1", "20260105"))["1"] is None


def why(event: date | str | None, *starts: tuple) -> dict:
    return _onset(event, *starts, column="time_to_onset_reason_T")


def test_a_drug_with_no_time_to_onset_says_why_and_one_with_a_value_says_nothing():
    padded, inexact, no_dose, before = dates.ONSET_REASONS
    starts = (("1", "20260105"), ("2", "202601"), ("3", "20260120"))
    assert why(date(2026, 1, 15), *starts) == {"1": None, "2": no_dose, "3": before}
    assert why("20260101", *starts) == dict.fromkeys("123", padded)  # read as known to the year
    assert why("20260401", *starts) == dict.fromkeys("123", padded)  # read as known to the month
    for event in ("202601", "20260230", "20990115", None):  # partial, no such day, too late, none
        assert why(event, *starts) == dict.fromkeys("123", inexact), event


def test_switched_off_no_drug_says_why():
    with _off("time-to-onset"):
        assert why(date(2026, 1, 15), ("1", "20260120")) == dict.fromkeys("123")


# ------------------------------------------------------------- the release
def test_the_release_carries_the_clean_dates_and_one_onset_row_per_drug_record(rel):
    legacy = rel.dicts("SELECT * FROM demo_T WHERE primaryid = '4100001'")[0]
    assert (legacy["event_dt"], legacy["event_dt_T"], legacy["event_dt_prec_T"]) == (
        "20120301",
        None,
        6,
    )
    assert rel.rows(
        "SELECT count(*) FROM ther_latest_T WHERE start_dt_prec_T = 6 AND start_dt_T IS NULL"
    ) == rel.rows("SELECT count(*) FROM ther_latest_T WHERE length(start_dt) = 6")
    records = "SELECT DISTINCT era_T, primaryid, quarter_T, drug_seq FROM drug_latest_T"
    assert rel.rows(f"SELECT count(*) FROM {dates.ONSET_TABLE}") == rel.rows(
        f"SELECT count(*) FROM ({records})"
    )


# The duplicate story with its padded groups published in 2026Q2, where their dates are padded.
_PADDED_IDS = {r.caseid for group in fakefda.PADDED_GROUPS.values() for r in group}
_STORY = [
    replace(r, quarter="2026q2", fda_dt="20260415") if r.caseid in _PADDED_IDS else r
    for r in fakefda.DUP_STORY
]


def _dup_built(tmp_path_factory, rules: UserRules) -> ReleaseReader:
    zips = fakefda.write_input(
        tmp_path_factory.mktemp("dates_zips"), quarters=fakefda.DUP_QUARTERS, story=_STORY
    )
    return ReleaseReader(build_release(zips, tmp_path_factory.mktemp("dates"), user_rules=rules))


@pytest.fixture(scope="module")
def dup_dates_on(tmp_path_factory):
    return _dup_built(tmp_path_factory, UserRules())


@pytest.fixture(scope="module")
def dup_dates_off(tmp_path_factory):
    return _dup_built(tmp_path_factory, UserRules(off=DATE_RULES))


def test_the_date_rules_change_no_duplicate_group_and_no_kept_case(dup_dates_on, dup_dates_off):
    flags = "SELECT * FROM case_dup_T ORDER BY era_T, case_key_T"  # every key, group and flag
    assert dup_dates_on.rows(flags) == dup_dates_off.rows(flags)
    padded = "SELECT count(*) FROM case_latest_T WHERE event_dt_prec_T < 8"
    assert dup_dates_on.rows(padded)[0][0] > dup_dates_off.rows(padded)[0][0]


def test_switched_off_the_dates_are_read_as_before(dup_dates_off):
    assert dup_dates_off.rows(
        "SELECT count(*) FROM demo_T WHERE event_dt_T IS DISTINCT FROM "
        "CAST(try_strptime(CASE WHEN length(event_dt) = 8 THEN event_dt END, '%Y%m%d') AS DATE) "
        "OR event_dt_prec_T IS DISTINCT FROM "
        "CASE WHEN length(event_dt) IN (4, 6, 8) THEN length(event_dt) END"
    ) == [(0,)]
    assert dup_dates_off.rows(
        f"SELECT count(time_to_onset_T) FROM {dates.ONSET_TABLE} "
        "UNION ALL SELECT count(dur_days_T) FROM ther_latest_T"
    ) == [(0,), (0,)]
