"""A person's own custom MedDRA queries on their own machine: kept in this browser, with nobody
signed in and no switch to share one; saved and used, still there after a reload, and deleted."""

from __future__ import annotations

from open_altio.testing.browser import settle

KEPT = "() => JSON.parse(localStorage.getItem('open-altio.cmqs'))"


def reactions(page, kind: str = "all") -> None:
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu .oa-filter-row[data-row="reactions"]')
    if kind != "all":
        page.click(f'#oa-kinds [data-v="{kind}"]')


def test_a_query_is_kept_in_this_browser_used_and_deleted(opened):
    page = opened("/all/overview")
    reactions(page)
    page.click('#oa-filter-menu [data-act="cmq-new"]')
    dialog = page.locator(".oa-cmq-dialog")
    assert "kept for you" in dialog.inner_text() and "Kept in this browser." in dialog.inner_text()
    assert dialog.locator('[data-act="cmq-share"]').count() == 0
    page.fill("#oa-cmq-name", "Head")
    page.fill("#oa-cmq-find", "Headache")
    page.click('#oa-cmq-found [data-act="cmq-term"][data-v="Headache"]')
    page.click('[data-act="cmq-save"]')
    page.wait_for_selector(".oa-cmq-dialog", state="detached")
    settle(page)
    assert "Head" in page.inner_text(".oa-strip")
    [query] = page.evaluate(KEPT)
    assert (query["name"], query["terms"], query["src"]) == (
        "Head",
        ["Headache"],
        {"Headache": "typed"},
    )

    page.reload()
    settle(page)
    reactions(page, "cmq")
    results = page.locator("#oa-term-results")
    assert results.locator(".menu-heading").count() == 0
    assert "Head" in results.inner_text() and "1 term" in results.inner_text()
    results.locator('[data-act="expand"]').click()
    results.locator('[data-act="cmq-edit"]').click()
    page.click('[data-act="cmq-delete"]')
    page.wait_for_selector(".oa-cmq-dialog", state="detached")
    assert page.evaluate(KEPT) == []
