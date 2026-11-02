"""A press outside an open menu only closes it (ui/overlays.js closedByThisClick): the chart bar,
link or tab under the press does nothing, so closing a menu never filters the page or leaves it by
the way, and a row of statistics opens no cases. The next press does what it says, a press on
the menu's own button closes it without opening it again, and a press inside the menu still
chooses."""

from __future__ import annotations

from typing import Any

import pytest

from open_altio.testing.browser import settle

WIDTHS = [1024, 1440]
OPEN = ".menu:popover-open"
# the centre of the first element `selector` names that the open menu does not cover
CLEAR = """(selector) => {
  const m = document.querySelector('.menu:popover-open')?.getBoundingClientRect();
  const off = (r) => !m
    || r.right < m.left || r.left > m.right || r.bottom < m.top || r.top > m.bottom;
  const el = [...document.querySelectorAll(selector)].find((e) => {
    const r = e.getBoundingClientRect();
    return r.width && r.top >= 0 && r.bottom <= innerHeight && off(r);
  });
  const r = el.getBoundingClientRect();
  return [r.left + r.width / 2, r.top + r.height / 2];
}"""
STRIP = "() => document.getElementById('oa-strip').textContent.trim()"
# a bar of the years chart or of a field's chart: each press filters the page
BARS = '[data-act="period"], [data-act="chart"]'


def press_clear(page: Any, selector: str) -> None:
    x, y = page.evaluate(CLEAR, selector)
    page.mouse.click(x, y)


def open_filters(page: Any) -> None:
    page.click(".oa-filters-btn")
    page.wait_for_selector(OPEN)


@pytest.mark.parametrize("width", WIDTHS)
def test_a_press_on_a_chart_bar_outside_an_open_menu_only_closes_it(opened, width):
    page = opened("/all/overview", width=width)
    strip = page.evaluate(STRIP)
    open_filters(page)
    press_clear(page, BARS)
    assert page.locator(OPEN).count() == 0
    settle(page)
    assert page.evaluate(STRIP) == strip and page.url.endswith("/all/overview")
    press_clear(page, BARS)  # no menu open: the bar filters
    settle(page)
    assert page.evaluate(STRIP) != strip


def test_a_press_on_a_tab_outside_an_open_menu_does_not_leave_the_page(opened):
    page = opened("/product/acetylsalicylic%20acid/overview")
    open_filters(page)
    press_clear(page, '.product-tab[href$="/cases"]')
    assert page.locator(OPEN).count() == 0
    assert page.url.endswith("/overview")
    press_clear(page, '.product-tab[href$="/cases"]')
    page.wait_for_url("**/cases")


def test_the_menus_own_button_closes_it_and_a_press_inside_still_chooses(opened):
    page = opened("/all/overview")
    open_filters(page)
    page.click(".oa-filters-btn")
    assert page.locator(OPEN).count() == 0
    open_filters(page)
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="sex"]')
    assert page.locator(OPEN).count() == 1  # the press inside opened the row's choices


def test_a_press_on_a_row_outside_the_thresholds_menu_opens_no_cases(opened, stats_site):
    page = opened("/all/statistics", base=stats_site)
    page.click('[data-act="screens"]')
    page.wait_for_selector(OPEN)
    press_clear(page, '[data-act="stat-row"]')
    assert page.locator(OPEN).count() == 0
    assert page.url.endswith("/all/statistics")
    press_clear(page, '[data-act="stat-row"]')
    page.wait_for_url("**/cases*")


# A menu whose rows change, opened from a button that stands where the test puts it
MENU = """async (fromFoot) => {
  const { popMenu } = await import('/ui/app.js');
  const button = document.createElement('button');
  const at = `left: 300px; top: ${innerHeight - fromFoot}px`;
  button.style.cssText = `position: fixed; ${at}; width: 80px; height: 30px; z-index: 9`;
  document.body.append(button);
  const menu = popMenu(button, '<div style="height: 200px"></div>');
  window.againstMenu = { menu, button };
}"""
RESIZE = """async (height) => {
  const { menu, button } = window.againstMenu;
  await new Promise((done) => requestAnimationFrame(done));
  menu.firstChild.style.height = `${height}px`;
  for (let frame = 0; frame < 10; frame += 1) {
    await new Promise((done) => requestAnimationFrame(done));
  }
  const m = menu.getBoundingClientRect(), b = button.getBoundingClientRect();
  return { over: b.top - m.bottom, under: m.top - b.bottom, top: m.top };
}"""


def test_a_menu_over_its_control_keeps_its_foot_there_as_its_rows_narrow(opened):
    page = opened("/", width=1440)
    page.evaluate(MENU, 200)
    start = page.evaluate(RESIZE, 200)
    assert 0 <= start["over"] <= 8, start
    assert page.evaluate(RESIZE, 60)["over"] == start["over"]
    assert page.evaluate(RESIZE, 300)["over"] == start["over"]


def test_a_menu_under_its_control_goes_over_it_once_it_no_longer_fits(opened):
    page = opened("/", width=1440)
    page.evaluate(MENU, 400)
    start = page.evaluate(RESIZE, 200)
    assert 0 <= start["under"] <= 8, start
    assert page.evaluate(RESIZE, 100)["under"] == start["under"]
    grown = page.evaluate(RESIZE, 400)
    assert grown["over"] == start["under"] and grown["top"] >= 0, grown
