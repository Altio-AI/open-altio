"""Tables and SQL takes a query in its address (ui/sql.js takeAddressQuery): the box holds it only
once the page can run a query, the address then loses `query`, and nothing runs by itself. A page
opened without it is as before."""

from __future__ import annotations

from typing import Any

BOX = "#oa-sql-text"
EXAMPLE_START = "-- Cases per year"
QUERY = "SELECT%201"


def box(page: Any) -> str:
    return page.input_value(BOX)


def search(page: Any) -> str:
    return page.evaluate("() => location.search")


def test_the_box_fills_from_the_address_and_the_address_loses_query(opened):
    page = opened(f"/sql?query={QUERY}")
    assert box(page) == "SELECT 1"
    assert "query" not in search(page)
    assert page.evaluate("() => location.pathname") == "/release"
    assert page.locator("#oa-sql-result").inner_text().strip() == "", "nothing ran by itself"


def test_the_box_stays_as_it_was_until_the_tables_are_listed(chromium, site):
    from open_altio.testing.browser import NOW

    context = chromium.new_context(viewport={"width": 1440, "height": 900})
    held: list[Any] = []
    try:
        page = context.new_page()
        page.clock.set_fixed_time(NOW)
        page.route("**/api/schema", lambda route: held.append(route))
        page.goto(f"{site}/release?query={QUERY}&other=1")
        page.wait_for_selector(BOX)
        while not held:
            page.wait_for_timeout(50)
        assert box(page).startswith(EXAMPLE_START), "filled before it could run"
        assert "query=" in search(page)
        held[0].continue_()
        page.wait_for_function("(sel) => document.querySelector(sel).value === 'SELECT 1'", arg=BOX)
        assert search(page) == "?other=1", "only query leaves the address"
    finally:
        context.close()


def test_a_reload_does_not_fill_the_box_again(opened):
    page = opened(f"/release?query={QUERY}")
    page.reload()
    assert box(page).startswith(EXAMPLE_START)


def test_a_page_opened_without_a_query_is_as_before(opened):
    page = opened("/release")
    assert box(page).startswith(EXAMPLE_START)
    assert search(page) == ""
