"""Every table of the explorer, and the case window's fields, in a browser at a laptop's two
widths: no cell's words run into the next cell or are cut off, every cell of a row sets its first
line on one line, and every grey line about a value (FDA's own value, where ours came from, a
rule's link, a current PT, a label's result) sits on a line of its own under the value, flush with
it. The case list, Statistics and a pair's ROR by age band and by sex, the case window, Tables and
SQL with its results, the export's files, the rules, and the filters' lists with a count column."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from open_altio.testing.browser import cells_fit, settle

WIDTHS = [1280, 1440]
# a result wider than the page: twelve columns of one row
WIDE_SQL = "SELECT " + ", ".join(f"'value {n} of the row' AS column_{n}" for n in range(1, 13))


def nothing(page: Any) -> None:
    pass


def sql(query: str) -> Callable[[Any], None]:
    def run(page: Any) -> None:
        page.fill("#oa-sql-text", query)
        page.click('[data-act="sql-run"]')
        settle(page)

    return run


def export(page: Any) -> None:
    page.click(".oa-export-btn")
    settle(page)


def filter_list(row: str) -> Callable[[Any], None]:
    def show(page: Any) -> None:
        page.click(".oa-filters-btn")
        page.click(f'#oa-filter-menu [data-act="filter-row"][data-row="{row}"]')
        settle(page)

    return show


def drug_search(words: str) -> Callable[[Any], None]:
    """The Drugs filter's search: each drug found with the names it was reported under, a line
    under its name, and its count."""

    def find(page: Any) -> None:
        filter_list("drugs")(page)
        page.fill("#oa-drug-find", words)
        page.wait_for_selector("#oa-drug-results .oa-choice-note")
        settle(page)

    return find


def strata(page: Any) -> None:
    page.locator(".oa-stats tbody tr").first.click()
    settle(page)


# what each table is: the site that has it, its address, what opens it, and its rows
TABLES = {
    "the case list": ("demo_site", "/all/cases", nothing, ".oa-cases tr"),
    "the case list with MedDRA's system organ classes": (
        "site",
        "/all/cases",
        nothing,
        ".oa-cases tr",
    ),
    "Statistics": ("stats_site", "/all/statistics", nothing, ".oa-stats tr"),
    "a product's Statistics": (
        "stats_site",
        "/product/warfarin/statistics",
        nothing,
        ".oa-stats tr",
    ),
    "a pair's ROR by age band and by sex": (
        "stats_site",
        "/product/warfarin/statistics",
        strata,
        ".oa-strata-table tr",
    ),
    "the tables and a table's columns": (
        "site",
        "/release",
        nothing,
        ".oa-cat-cols, .oa-cat-pick, .oa-coltable tr",
    ),
    "an SQL result": ("site", "/release", sql(WIDE_SQL), ".oa-sql-table tr"),
    "an SQL result of the case table": (
        "site",
        "/release",
        sql("SELECT * FROM demo LIMIT 20"),
        ".oa-sql-table tr",
    ),
    "the export's files": ("site", "/all/cases", export, ".oa-export-table tr"),
    "the rules": ("classes_site", "/methods?open=classes", nothing, ".oa-rule-head"),
    "a rule opened": ("site", "/rules?open=meddra-terms", nothing, ".oa-rule-head"),
    "the countries to filter by": ("site", "/all/cases", filter_list("country"), ".oa-choice"),
    "the senders to filter by": ("site", "/all/cases", filter_list("sender"), ".oa-choice"),
    "the drugs to filter by": ("site", "/all/cases", filter_list("drugs"), ".oa-choice"),
    "the drugs a search finds": ("site", "/all/cases", drug_search("aspirin"), ".oa-choice"),
}

# cases whose window shows each kind of value: a site, and the case's address
CASES = {
    "therapy dates, durations and times to onset": ("stats_site", "case=7700001"),
    "WHO classes": ("classes_site", "case=9020020&era=faers"),
    "MedDRA's current terms": ("site", "case=9020020&era=faers"),
    "an ingredient read through FDA's active ingredient": ("site", "case=9004004&era=faers"),
    "FDA's codes read in words": ("site", "case=9002002&era=faers"),
    "an AERS country read to its code": ("site", "case=5100005&era=legacy"),
    "an EU country from an earlier version": ("demo_site", "case=7906001&era=faers"),
    "an age band": ("demo_site", "case=7902001&era=faers"),
    "label flags under the reactions": ("label_site", "case=9005005&era=faers"),
}


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("table", list(TABLES))
def test_every_cell_holds_its_words_on_one_first_line_with_its_grey_lines_under_it(
    request, opened, table, width
):
    site, path, show, rows = TABLES[table]
    page = opened(path, base=request.getfixturevalue(site), width=width)
    show(page)
    got = cells_fit(page, rows)
    assert got["rows"] > 0
    assert got["leaks"] == [] and got["uneven"] == [] and got["beside"] == [], got


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("case", list(CASES))
def test_the_case_windows_tables_and_fields_hold_their_words_with_fdas_under_ours(
    request, opened, case, width
):
    site, query = CASES[case]
    page = opened(f"/all/cases?{query}", base=request.getfixturevalue(site), width=width)
    page.wait_for_selector("#oa-case .oa-case-lead")
    got = cells_fit(
        page, "#oa-case tr", "#oa-case dd:not(:has(.oa-reac-list)), #oa-case .oa-list > li"
    )
    assert got["rows"] > 0
    assert got["leaks"] == [] and got["uneven"] == [] and got["beside"] == [], got
    # the drugs fit the window whole, every column in view
    frame = page.locator("#oa-case .oa-case-scroll:has(> .oa-case-drugs)")
    assert frame.evaluate("(f) => f.scrollWidth <= f.clientWidth"), case
