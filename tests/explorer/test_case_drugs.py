"""The case window's Drugs and Therapy dates, in a browser: the drugs fit the window from a laptop's
width up in eight columns, each role as FDA codes it with its name on hover, FDA's active
ingredient under the ingredients, the dose and how often in one cell, and stopped and restarted
in one, each under its label; narrower, the table scrolls with its role held. Therapy dates name
each drug as it was reported, with FDA's number beside where two drugs share a name."""

from __future__ import annotations

from typing import Any

import pytest

from open_altio.testing.browser import first_column_held, settle

HEADS = [
    "Role",
    "As reported",
    "Ingredient",
    "Used for",
    "WHO class (ATC)",
    "Route",
    "Dose",
    "Stopped and restarted",
]


def drugs(page: Any) -> list[list[str]]:
    """The case window's drugs table, its head first, a list of cells a row."""
    return page.eval_on_selector_all(
        "#oa-case .oa-case-drugs tr", "rs => rs.map((r) => [...r.cells].map((c) => c.innerText))"
    )


@pytest.mark.parametrize("width", [1280, 1440])
def test_the_drugs_fit_the_window_in_eight_columns(opened, classes_site, width):
    page = opened("/all/cases?case=9020020&era=faers", base=classes_site, width=width)
    head, *rows = drugs(page)
    assert head == HEADS
    frame = page.locator("#oa-case .oa-case-scroll:has(> .oa-case-drugs)")
    assert frame.evaluate("(f) => f.scrollWidth <= f.clientWidth")
    role, named, ingredient, _, _, _, dose, stopped = rows[0]
    assert (role, named) == ("PS", "WARFARIN")
    assert ingredient.split("\n") == ["Warfarin", "FDA: Not given", "DiAna dictionary"]
    assert dose.split("\n") == ["100 MG, QD, daily", "FDA: QD"]
    assert stopped.split("\n") == ["Stopped Does not apply", "Restarted Not given", "FDA: U"]
    tip = page.get_attribute("#oa-case .oa-case-drugs tbody td:first-child span", "data-tip")
    assert tip == "Primary suspect"


def test_narrower_than_a_laptop_the_drugs_scroll_with_their_role_held(opened, classes_site):
    page = opened("/all/cases?case=9020020&era=faers", base=classes_site, width=1024)
    frame = page.locator("#oa-case .oa-case-scroll:has(> .oa-case-drugs)")
    assert frame.evaluate("(f) => f.scrollWidth > f.clientWidth")
    assert first_column_held(frame)["held"]


def therapy_drugs(page: Any) -> list[str]:
    return page.eval_on_selector_all(
        "#oa-case .oa-case-therapy tbody tr td:first-child", "ts => ts.map((t) => t.innerText)"
    )


def test_therapy_dates_name_each_drug_as_it_was_reported(opened, stats_site):
    page = opened("/all/cases?case=7700001", base=stats_site)
    assert therapy_drugs(page) == ["IBUPROFEN", "LISINOPRIL"]


def test_two_drugs_of_one_name_keep_fdas_numbers(opened, stats_site):
    """The same case, its second drug renamed as its first on the way to the page: the
    therapy dates tell the two apart by FDA's number."""
    page = opened("/all/cases", base=stats_site)

    def renamed(route: Any) -> None:
        case = route.fetch().json()
        for drug in case["drug"]:
            drug["drugname"] = "IBUPROFEN"
        route.fulfill(json=case)

    page.route("**/api/case/*/7700001", renamed)
    page.goto(stats_site + "/all/cases?case=7700001")
    settle(page)
    page.wait_for_selector("#oa-case .oa-case-therapy")
    assert therapy_drugs(page) == ["IBUPROFEN (1)", "IBUPROFEN (2)"]
    assert [row[1] for row in drugs(page)[1:]] == ["IBUPROFEN", "IBUPROFEN"]
