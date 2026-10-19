"""A reaction's MedDRA system organ class (SOC) is licensed content: it is shown only where the
explorer shows MedDRA's other licensed parts, in the case list and the case, and carried by the API
only to a viewer with that part."""

from __future__ import annotations

import pytest

from open_altio.testing.browser import cells_fit, settle

SOC_WORDS = "System organ class"


@pytest.mark.parametrize("who", ["ann", "ann+meddra"])
def test_only_a_viewer_with_the_licensed_part_is_given_a_system_organ_class(
    people, licensed_release, ask, who
):
    web = people(licensed_release)
    seen = {"X-Viewer": who}
    listed = ask(web, "/api/cases", headers=seen, pt="Heart rhythm abnormal")
    one = ask(web, "/api/case/legacy/5100009", headers=seen)
    if who == "ann":
        assert all("socs_T" not in c for c in listed["cases"])
        assert all("soc_T" not in r for r in one["reac"])
    else:
        assert all(
            c["socs_T"] and all(s.startswith("Invented") for s in c["socs_T"])
            for c in listed["cases"]
        )
        assert one["reac"][0]["soc_T"].startswith("Invented")


def test_a_case_lists_each_system_organ_class_once_in_the_order_of_its_reactions(
    licensed_client, ask
):
    listed = ask(licensed_client, "/api/cases", size=200)["cases"]
    for c in listed:
        assert len(c["socs_T"]) == len(set(c["socs_T"]))
    assert any(len(c["socs_T"]) > 1 for c in listed)


def test_a_release_without_meddra_has_none(client, ask):
    assert all("socs_T" not in c for c in ask(client, "/api/cases")["cases"])


APP_WIDTHS = [320, 768, 1024, 1440]
NO_SIDEWAYS = "document.documentElement.scrollWidth <= innerWidth"


def open_case(page):
    page.locator(".oa-cases tbody tr").first.click()
    page.wait_for_selector("#oa-case .oa-case-lead")
    settle(page)


@pytest.mark.parametrize("width", APP_WIDTHS)
def test_a_subscriber_sees_the_column_and_the_line_and_nothing_overflows(site, opened, width):
    page = opened("/all/cases", base=site, width=width)
    page.wait_for_selector(".oa-cases tbody tr")
    assert page.evaluate(NO_SIDEWAYS)
    frame = page.locator(".oa-cases-frame")
    assert frame.evaluate("(f) => f.scrollWidth <= f.clientWidth")
    got = cells_fit(page, ".oa-cases tr") if width >= 768 else {"leaks": [], "beside": []}
    assert got["leaks"] == [] and got["beside"] == [], got
    # the column shows from 1024, as the outcome's place below 1440; the cards of a phone carry it
    shown = page.locator(".oa-cases tbody tr:first-child td:last-child").is_visible()
    assert shown == (width != 768)
    open_case(page)
    assert page.locator("#oa-case .oa-reac-list .oa-fda", has_text=SOC_WORDS).count() > 0
    assert page.evaluate(NO_SIDEWAYS)
    got = cells_fit(page, "#oa-case tr", "#oa-case dd:not(:has(.oa-reac-list)), #oa-case li")
    assert got["leaks"] == [] and got["beside"] == [], got


@pytest.mark.parametrize("width", APP_WIDTHS)
def test_a_viewer_without_the_part_sees_neither(demo_site, opened, width):
    page = opened("/all/cases", base=demo_site, width=width)
    page.wait_for_selector(".oa-cases tbody tr")
    assert page.evaluate(NO_SIDEWAYS)
    open_case(page)
    assert SOC_WORDS not in page.content()
