"""A menu opened from a button stays where it was set against that button as the page scrolls:
the Filters menu and the SQL examples menu keep their distance below it, and on a phone the Filters
menu stays a sheet over the whole screen. No sideways scroll, nothing else moves."""

from __future__ import annotations

import pytest

from open_altio.explorer.app import create_app
from open_altio.testing.browser import open_page, served, settle

WIDTHS = [320, 768, 1024, 1440]
MENUS = [
    ("/all/cases", ".oa-filters-btn", "#oa-filter-menu"),
    ("/sql", '[data-act="sql-examples"]', ".oa-examples"),
]
TALL = (
    "() => { const s = document.createElement('div'); s.style.height = '3000px';"
    " document.querySelector('main, body').appendChild(s); }"
)
GAP = """(button) => {
  const m = document.querySelector('.menu:popover-open').getBoundingClientRect();
  const b = document.querySelector(button).getBoundingClientRect();
  return [Math.round(m.top - b.bottom), Math.round(m.top), Math.round(b.top),
    Math.round(m.height), innerHeight]; }"""
# Scrolls, and answers once the page has had the scroll: the page's own scroll listeners were added
# first, so they have run when this one does, and a frame later the menu is drawn where they put it.
SCROLL = """(n) => new Promise((done) => {
  const drawn = () => requestAnimationFrame(() => done());
  document.addEventListener('scroll', drawn, { capture: true, once: true });
  window.scrollBy(0, n);
  document.querySelectorAll('*').forEach((e) => {
    const tall = e.scrollHeight > e.clientHeight + 400;
    if (tall && /auto|scroll/.test(getComputedStyle(e).overflowY) && !e.closest('.menu')) {
      e.scrollTop += n;
    }
  }); })"""


@pytest.fixture(scope="module")
def base(release):
    with served(create_app(release)) as url:
        yield url


@pytest.fixture(scope="module")
def labelled(labelled_release):
    with served(create_app(labelled_release)) as url:
        yield url


# Statistics of a drug: its Filters, Label status and Thresholds menus
STATISTICS = [
    ("/product/BLEOMYCIN%20SULFATE/statistics", '[data-act="stat-filters"]', ".menu:popover-open"),
    ("/product/BLEOMYCIN%20SULFATE/statistics", '[data-act="screens"]', ".menu:popover-open"),
]


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("path,button,menu", MENUS)
def test_the_menu_moves_with_its_button(chromium, base, width, path, button, menu):
    check(chromium, base, width, path, button, menu)


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("path,button,menu", STATISTICS)
def test_the_statistics_menus_move_with_their_buttons(
    chromium, labelled, width, path, button, menu
):
    check(chromium, labelled, width, path, button, menu)


def check(chromium, base, width, path, button, menu):
    page = open_page(chromium, base + path, width=width)
    settle(page)
    page.evaluate(TALL)
    page.click(button)
    page.wait_for_selector(menu)
    before = page.evaluate(GAP, button)
    page.evaluate(SCROLL, 400)
    after = page.evaluate(GAP, button)
    sheet = before[1] == 0 and before[3] >= before[4] - 1
    if sheet:
        assert after[1] == 0 and after[3] >= after[4] - 1
    else:
        assert before[2] > after[2], "the page did not scroll"
        assert after[0] == before[0]
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    page.context.close()
