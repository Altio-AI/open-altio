"""Thresholds (src/open_altio/stats/screen.py): the presets on each statistic's rule, where a
person's own screen starts, what a screen refuses, and the SQL it becomes, run on tables worked
by hand."""

from __future__ import annotations

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers.statistics.scored import COLUMNS
from open_altio.stats import disproportionality as dp
from open_altio.stats import screen


@pytest.mark.parametrize("statistic", sorted(screen.RULES))
def test_every_preset_reads_columns_the_statistics_have(statistic):
    for preset in screen.presets(statistic):
        assert preset["id"] and preset["label"] and preset["source"]
        assert screen.check(preset["when"], COLUMNS)
    assert sum(bool(p.get("default")) for p in screen.presets(statistic)) <= 1


def test_each_statistic_starts_from_its_default_or_its_own_screen():
    assert screen.start("EBGM") == [
        {"column": "eb05", "at_least": 2},
        {"column": "cases", "at_least": 3},
    ]
    assert screen.start("PRR")[1]["column"] == "chi_square_yates"
    assert screen.presets("RRR") == [] and screen.start("RRR") == rulebook.value("rrr", "own")


def table(*rows):
    """A DuckDB table of dp.measures over the (a, b, c, d) rows, with `cases` for a."""
    cells = dict(zip("abcd", zip(*rows, strict=True), strict=True))
    got = dp.measures(**cells)
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE t (cases DOUBLE, prr DOUBLE, chi_square DOUBLE, chi_square_yates DOUBLE,"
        " ror_lower DOUBLE)"
    )
    for i in range(len(rows)):
        con.execute(
            "INSERT INTO t VALUES (?, ?, ?, ?, ?)",
            [
                float(got["a"][i]),
                *(
                    None if v != v else float(v)
                    for v in (
                        got["PRR"][i],
                        got["chi_square"][i],
                        got["chi_square_yates"][i],
                        got["ROR_lower"][i],
                    )
                ),
            ],
        )
    return con


def meets(con, when):
    clause, params = screen.where(screen.check(when, COLUMNS), lambda c: c)
    return [
        r[0]
        for r in con.execute(f"SELECT ({clause}) IS TRUE FROM t ORDER BY rowid", params).fetchall()
    ]


def test_evans_preset_on_tables_worked_by_hand():
    """a = 10, b = 90, c = 40, d = 860: PRR 2.25, Yates chi-square 90/19 = 4.74, 10 cases, meets.
    a = 2, b = 18, c = 40, d = 940: PRR 2.45 but 2 cases, does not.
    a = 6, b = 94, c = 30, d = 1170: PRR 2.4, Yates chi-square 3.0, Pearson's 4.2, does not; it
    meets the same preset reading Pearson's chi-square instead."""
    con = table((10, 90, 40, 860), (2, 18, 40, 940), (6, 94, 30, 1170))
    evans = next(p for p in screen.presets("PRR") if p["default"])["when"]
    assert meets(con, evans) == [True, False, False]
    pearson = [
        dict(c, column="chi_square") if c["column"] == "chi_square_yates" else c for c in evans
    ]
    assert meets(con, pearson) == [True, False, True]


def test_above_is_strict_at_least_is_not_and_an_empty_value_meets_nothing():
    con = table((10, 90, 40, 860), (10, 90, 0, 900))  # no comparator: PRR and ROR are empty
    assert meets(con, [{"column": "prr", "at_least": 2.25}]) == [True, False]
    assert meets(con, [{"column": "prr", "above": 2.25}]) == [False, False]
    assert meets(con, [{"column": "prr", "below": 1e9}]) == [True, False]
    assert meets(con, []) == [True, True]


@pytest.mark.parametrize(
    "when",
    [
        [{"column": "prr"}],
        [{"column": "prr", "at_least": 2, "above": 1}],
        [{"column": "prr", "more_than": 2}],
        [{"column": "prr", "at_least": "2"}],
        [{"column": "prr", "at_least": True}],
        [{"column": "prr", "at_least": float("nan")}],
        [{"column": "prr; DROP TABLE t", "at_least": 2}],
    ],
)
def test_malformed_screens_are_refused(when):
    with pytest.raises(screen.ScreenError):
        screen.check(when, COLUMNS)
