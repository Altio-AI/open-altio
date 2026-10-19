"""The page on a phone's touch screen, 390 wide: one tap does what it says (iOS takes a tap whose
hover changes the page for that hover, and asks for a second), no text box takes focus on its
own, none is small enough for iOS to zoom into, and the evidence charts keep their numbers in."""

from __future__ import annotations

from typing import Any

PHONE = {"width": 390, "touch": True}

# Counts what the page changes while a tap is still a hover (from its mouseover to its mousedown):
# iOS does not deliver the click of a tap that changed anything then.
WATCH_HOVER = """() => {
  window.hoverChanges = 0;
  let hovering = false;
  new MutationObserver((changes) => { if (hovering) window.hoverChanges += changes.length; })
    .observe(document.body, { subtree: true, childList: true, attributes: true,
      characterData: true });
  addEventListener('mouseover', () => { hovering = true; }, true);
  addEventListener('mousedown', () => { hovering = false; }, true);
}"""

TYPING_FOCUS = "() => !!document.activeElement?.matches('input, textarea, select')"


def pane(page: Any) -> str | None:
    """The sheet's pane in sight, and the filter whose options it shows."""
    shown = page.get_attribute("#oa-filter-menu", "data-pane")
    return shown if shown != "options" else page.text_content("#oa-filter-options .menu-heading")


def test_a_touch_screen_is_one_the_page_knows(opened):
    assert opened("/", **PHONE).evaluate("matchMedia('(pointer: coarse)').matches")


def test_one_tap_opens_a_filters_options_and_shows_no_tip(opened):
    page = opened("/all/overview", **PHONE)
    page.evaluate(WATCH_HOVER)
    page.tap(".oa-filters-btn")
    page.tap('#oa-filter-menu .oa-filter-row[data-row="sex"]')
    assert pane(page) == "Sex"
    page.tap('#oa-filter-menu [data-act="sheet-back"]')
    page.tap('#oa-filter-menu .oa-filter-row[data-row="country"]')
    assert pane(page) == "Country"
    page.tap('#oa-filter-menu [data-act="sheet-done"]')
    page.tap('[data-act="chart"][data-key="sex"]')
    assert page.is_hidden("#oa-tip")
    assert page.evaluate("window.hoverChanges") == 0


def test_a_filters_line_opens_its_options_at_once(opened):
    page = opened("/all/overview", **PHONE)
    page.tap('[data-act="chart"][data-key="sex"]')
    page.wait_for_selector('.oa-strip-edit[data-row="sex"]')
    page.tap('.oa-strip-edit[data-row="sex"]')
    assert pane(page) == "Sex"


def test_no_text_box_takes_focus_on_its_own_on_a_touch_screen(opened):
    page = opened("/product/valsartan/overview", **PHONE)
    page.tap(".oa-filters-btn")
    page.tap('#oa-filter-menu .oa-filter-row[data-row="spellings"]')
    assert page.is_visible("#oa-spell-find") and not page.evaluate(TYPING_FOCUS)
    page.tap('#oa-filter-menu [data-act="sheet-back"]')
    page.tap('#oa-filter-menu .oa-filter-row[data-row="reactions"]')
    page.tap('#oa-filter-menu [data-act="cmq-new"]')
    assert page.is_visible("#oa-cmq-name") and not page.evaluate(TYPING_FOCUS)
    # with a mouse, the box is ready for the typing
    desk = opened("/product/valsartan/overview")
    desk.click(".oa-filters-btn")
    desk.click('#oa-filter-menu .oa-filter-row[data-row="spellings"]')
    assert desk.evaluate("document.activeElement.id") == "oa-spell-find"
    desk.click('#oa-filter-menu .oa-filter-row[data-row="reactions"]')
    desk.click('#oa-filter-menu [data-act="cmq-new"]')
    assert desk.evaluate("document.activeElement.id") == "oa-cmq-name"


SIZES = """() => [...document.querySelectorAll(
    'input:not([type=checkbox]):not([type=radio]), textarea, select')]
  .filter((el) => el.getClientRects().length)
  .map((el) => parseFloat(getComputedStyle(el).fontSize))"""


def test_no_text_box_is_small_enough_for_ios_to_zoom_into(opened):
    page = opened("/all/overview", **PHONE)
    page.tap(".oa-filters-btn")
    sizes = []
    for row in ("reactions", "received", "country", "sender"):
        page.tap(f'#oa-filter-menu .oa-filter-row[data-row="{row}"]')
        sizes += page.evaluate(SIZES)
        page.tap('#oa-filter-menu [data-act="sheet-back"]')
    home = opened("/", **PHONE)
    sizes += home.evaluate(SIZES)
    assert len(sizes) >= 6 and min(sizes) >= 16
    assert min(opened("/").evaluate(SIZES)) < 16  # a mouse's screen keeps the smaller type


def test_the_evidence_charts_keep_every_number_and_note_inside_at_390(opened):
    outside = opened("/methods", **PHONE).evaluate("""async () => {
      const { drawCharts } = await import('/ui/rules/charts.js');
      const box = document.createElement('div');
      box.className = 'oa-evidence-chart';
      box.dataset.card = 'wide';
      box.style.width = '320px';
      document.querySelector('main').append(box);
      const chart = {
        type: 'stacked_bar', x: { label: 'Year', values: [2019, 2020, 2021, 2022] },
        y: { label: 'Cases', unit: 'count' },
        series: [{ name: 'Cases', values: [1234567, 900000, 1100000, 1200000] }],
        note: { x: 2020, text: 'From 2020 on, such a date no longer counts' },
      };
      drawCharts(document, [{ id: 'wide', title: 'Wide', chart }]);
      const svg = box.querySelector('svg').getBoundingClientRect();
      return [...box.querySelectorAll('text')].filter((t) => {
        const r = t.getBoundingClientRect();
        return r.left < svg.left - 1 || r.right > svg.right + 1;
      }).map((t) => t.textContent);
    }""")
    assert outside == []
