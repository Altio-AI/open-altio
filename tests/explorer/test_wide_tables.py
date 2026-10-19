"""Every wide table outside Statistics (test_statistics_page.py has its own), in a browser: where
one scrolls sideways inside its frame, its first column stays in view with its head in line, like
a frozen column, in the light theme and the dark. The case list, a case's drugs and therapy
dates, a table's columns and an SQL result on Tables and SQL, and the export's files."""

from __future__ import annotations

from typing import Any

import pytest

from open_altio.testing.browser import first_column_held, settle

THEMES = ["light", "dark"]
# a result wider than a phone: twelve columns of one row
WIDE_SQL = "SELECT " + ", ".join(f"'value {n} of the row' AS column_{n}" for n in range(1, 13))


def held(page: Any, frame: str) -> dict[str, Any]:
    page.wait_for_selector(frame)
    return first_column_held(page.locator(frame).first)


@pytest.mark.parametrize("theme", THEMES)
def test_the_case_list_keeps_its_case_column_in_view(opened, theme):
    page = opened("/all/cases", width=1024, theme=theme)
    got = held(page, ".oa-cases-frame")
    assert got["held"], got


@pytest.mark.parametrize("theme", THEMES)
def test_a_cases_drugs_and_therapy_dates_keep_their_first_column_in_view(opened, stats_site, theme):
    page = opened("/all/cases?case=7700001", base=stats_site, width=390, theme=theme)
    for frame in (
        ".oa-case-scroll:has(> .oa-case-drugs)",
        ".oa-case-scroll:has(> .oa-case-therapy)",
    ):
        got = held(page, f"#oa-case {frame}")
        assert got["held"], (frame, got)


@pytest.mark.parametrize("theme", THEMES)
def test_tables_and_sql_keep_a_tables_column_names_and_a_results_first_column_in_view(
    opened, theme
):
    page = opened("/release", width=390, theme=theme)
    got = held(page, ".oa-card-cols")
    assert got["held"], got
    page.fill("#oa-sql-text", WIDE_SQL)
    page.click('[data-act="sql-run"]')
    settle(page)
    got = held(page, "#oa-sql-result .dashboard-frame")
    assert got["held"], got


@pytest.mark.parametrize("theme", THEMES)
def test_the_exports_files_keep_their_names_in_view(opened, theme):
    page = opened("/all/cases", width=390, theme=theme)
    page.click(".oa-export-btn")
    settle(page)
    got = held(page, ".dashboard-frame:has(> .oa-export-table)")
    assert got["held"], got
