"""The one events table (ui/eventstable.js, ui/eventmenus.js) in a browser, drawn by a host's page
module at an address of its own: a drug's events asked of the release, and rows a host gives of
two drugs with a column, a row class, a key, a drug and a pager of its own. At 320, 768, 1024 and
1440 pixels, light and dark: every cell holds one line and nothing scrolls the page sideways; the
event's name stays in view as the table scrolls; every menu opens inside the window, even with
its head at the window's foot; opening a menu or the rows arriving moves nothing. Trend opens no
menu; each head's arrow cycles its sort; a bound typed narrows at once; the Label
head's ticks count before Label narrows; and the person's columns and bounds come back on a
reload, from a host's `kept` where it keeps them, never this browser's storage then, while the
sort and the thresholds start again. Thresholds are the heads' At least values, and a host's listed
column and `beyond` work with them. A host's opened row (`opened`) at 320 and 1440 pixels:
its cell is drawn under the row across the row, in view as the table scrolls sideways, kept as
drawn through a sort, a paint and new rows, one open at a time, closed once its row leaves the
page, and opening it moves nothing above it."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import pytest
from fastapi import FastAPI, Response

from open_altio.explorer.access import LocalAccess
from open_altio.explorer.app import create_app, host
from open_altio.explorer.pages import index
from open_altio.testing.browser import first_column_held, open_page, served, settle

WIDTHS = [320, 768, 1024, 1440]
THEMES = ["light", "dark"]
MODULE = "/events-host/page.js"
PAGE = "/events-demo"
EVERY = [
    "expected", "eb95", "prr", "chi_square_yates", "ror", "ror_bounds", "ic", "ic025", "cases",
    "serious", "fatal", "onset_days",
]  # fmt: skip

# A host's page: the events table of ?drug=, or (?mode=rows) the host's own rows of two drugs,
# with its own Step column after the name, a tinted row, its keys, a marked cell and its pager;
# ?mode=opened the same rows, a press on one opening a cell under it that the host draws in, and
# ?opened= the key of a drug's row open as its table is drawn.
# ?hostkept keeps the person's choices in the host's own store (here a key of its own).
HOST_JS = """
import { eventsTable, extend, framed, tickMenu } from '/ui/app.js';

const asked = new URLSearchParams(location.search);
const row = (product, pt, cases, newest, year, death, eb05, prr, step) => ({
  product, pt, cases, newest, years: [[year, cases]], busiest_year: year, death, label: null,
  eb05, prr, step });
const ROWS = [
  row('alpha', 'Headache', 40, 3, 2019, 2, 2.4, 3.1, 'High'),
  row('beta', 'Headache', 12, 0, 2020, 0, 0.8, 1.1, 'Low'),
  row('beta', 'Nausea', 25, 5, 2021, 1, null, 2.2, 'Medium'),
];
const LEVEL = { High: 3, Medium: 2, Low: 1 };
window.opened = [];
window.ticked = [];
window.drawn = [];
window.inCell = 0;
window.ROWS = ROWS;
window.drawCell = (el, r) => {
  window.drawn.push(`${r.product}:${r.pt}`);
  window.box = el;
  el.innerHTML = `<p class="demo-opened">The cell of ${r.pt}</p>`
    + '<button type="button" class="btn" data-act="demo-in-cell">In the cell</button>';
};
if (asked.has('hostkept')) {
  const all = () => JSON.parse(localStorage.getItem('host-kept') || '{}');
  const put = (k, v) => JSON.stringify({ ...all(), [k]: v });
  const save = async (k, v) => localStorage.setItem('host-kept', put(k, v));
  extend({ kept: { load: async () => all(), save } });
}
const TICKS = [{ value: 'a', words: 'A', count: 2 }, { value: 'b', words: 'B', count: 1 }];
const STEP = {
  id: 'step', head: 'Step', after: 'event', cell: (r) => r.step, sort: (r) => LEVEL[r.step],
  words: ['High first', 'Low first'],
  ticks: { heading: 'Show steps', value: (r) => r.step, order: ['High', 'Medium', 'Low'] },
};
const pager = (rows) => ({
  rows: rows.slice(0, 2),
  html: `<span class="demo-pager">Events 1 to ${Math.min(2, rows.length)} of ${rows.length}</span>`,
});
const PAGE = '<main class="product-page">'
  + '<button type="button" class="btn" data-act="demo-ticks">Ticks</button>'
  + '<section class="oa-chart oa-chart-wide" id="demo"></section></main>';
extend({
  routes: [(parts) => (parts[0] === 'events-demo' ? { page: 'events-demo' } : null)],
  addresses: [(parts) => parts[0] === 'events-demo'],
  acts: {
    'demo-ticks': (el) => tickMenu(el, {
      heading: 'Show these', values: TICKS, foot: 'A foot.',
      onChange: (t) => window.ticked.push(t) }),
    'demo-in-cell': () => { window.inCell += 1; },
  },
  pages: {
    'events-demo': (route, app) => {
      app.innerHTML = framed(PAGE, 'events-demo');
      const el = app.querySelector('#demo');
      const open = (r) => window.opened.push(r.pt);
      const mode = asked.get('mode');
      window.table = mode === 'listed' ? eventsTable(el, {
        rows: ROWS, view: 'demo', columns: [{ ...STEP, after: undefined, listed: true }],
        rowKey: (r) => `${r.product}:${r.pt}`, product: (r) => r.product,
      }) : mode === 'rows' || mode === 'opened' ? eventsTable(el, {
        rows: ROWS, view: 'demo', open, columns: [STEP], pager,
        ...(mode === 'opened' && { opened: { draw: window.drawCell } }),
        rowClass: (r) => (r.step === 'High' ? 'oa-tinted' : ''),
        rowKey: (r) => `${r.product}:${r.pt}`,
        product: (r) => r.product,
        mark: (r, id) => (id === 'eb05' && r.eb05 >= 2 ? 'Past the line: EB05 at least 2' : ''),
        always: { columns: ['prr'], tip: 'Always shown here' },
        foot: (menu) => (menu === 'prr' ? 'The line: PRR at least 2.' : ''),
      }) : eventsTable(el, {
        drug: asked.get('drug'), open,
        ...(asked.has('limits') && { thresholds: JSON.parse(asked.get('limits')) }),
        ...(asked.has('ofcolumns') && { screensOfColumns: true }),
        ...(asked.has('beyond') && { beyond: (r) => r.pt === asked.get('beyond') }),
        ...(asked.has('opened') && { opened: { key: asked.get('opened'), draw: window.drawCell } }),
      });
    },
  },
});
"""


class WithModule(LocalAccess):
    modules = (MODULE,)


def hosted(release_dir: Any) -> Any:
    app = FastAPI()
    app.add_api_route(MODULE, lambda: Response(HOST_JS, media_type="text/javascript"))
    app.add_api_route(PAGE, index, methods=["GET"])
    return host(app, create_app(release_dir, access=WithModule()))


@pytest.fixture(scope="module")
def stats_host(stats_release) -> Iterator[str]:
    with served(hosted(stats_release)) as base:
        yield base


@pytest.fixture(scope="module")
def label_host(labelled_release) -> Iterator[str]:
    with served(hosted(labelled_release)) as base:
        yield base


@pytest.fixture
def page_at(chromium):
    pages: list[Any] = []

    def make(url: str, **how: Any) -> Any:
        page = open_page(chromium, url, **how)
        pages.append(page)
        return page

    yield make
    for page in pages:
        page.context.close()


def warfarin(stats_host: str) -> str:
    return f"{stats_host}{PAGE}?drug=warfarin"


# every column of the table showing, as a person who ticked them all keeps them
ALL_COLUMNS = {"events.columns": EVERY}

# Each cell of the table: how many lines its words take (rects of its text that share no height
# are lines of their own, so a smaller tag or an icon beside the words is the same line), whether
# they run past it (a name cut short on a phone carries its whole name as its tip), and how far
# the page scrolls sideways.
LINES = """() => {
  const lines = (cell) => {
    const walk = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT), boxes = [];
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (!n.data.trim()) continue;
      const r = document.createRange(); r.selectNodeContents(n);
      boxes.push(...[...r.getClientRects()].filter((x) => x.width > 0));
    }
    boxes.sort((a, b) => a.top - b.top);
    let count = 0, bottom = -Infinity;
    for (const b of boxes) {
      if (b.top >= bottom - 1) { count += 1; bottom = b.bottom; }
      else bottom = Math.max(bottom, b.bottom);
    }
    return count;
  };
  const cells = [...document.querySelectorAll('.oa-et-table tr > *')];
  return {
    cells: cells.length,
    tall: cells.filter((c) => lines(c) > 1).map((c) => c.textContent.trim()),
    cut: cells
      .filter((c) => c.scrollWidth > c.clientWidth && c.dataset.tip !== c.textContent.trim())
      .map((c) => c.textContent.trim()),
    page: document.documentElement.scrollWidth - innerWidth,
  };
}"""
# the words of one column's cells, top to bottom, by its head
COLUMN = """(id) => {
  const heads = [...document.querySelectorAll('.oa-et-table thead th')];
  const at = heads.findIndex((h) => h.dataset.col === id);
  const rows = [...document.querySelectorAll('.oa-et-table tbody tr')];
  return rows.map((r) => r.cells[at].textContent);
}"""


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_every_cell_holds_one_line_and_the_page_never_scrolls_sideways(
    page_at, stats_host, label_host, width, theme
):
    for url in (warfarin(stats_host), f"{label_host}{PAGE}?drug=acetylsalicylic%20acid"):
        page = page_at(url, width=width, theme=theme, kept=ALL_COLUMNS)
        got = page.evaluate(LINES)
        assert got["cells"] > 20, got
        assert got["tall"] == [] and got["cut"] == [] and got["page"] <= 0, (url, got)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_events_name_stays_in_view_as_the_table_scrolls_sideways(
    page_at, stats_host, width, theme
):
    page = page_at(warfarin(stats_host), width=width, theme=theme, kept=ALL_COLUMNS)
    got = first_column_held(page.locator(".oa-et-frame"))
    assert got["held"], got
    assert page.evaluate("() => document.querySelector('.oa-et-name').textContent") == "Event"


# Where a menu is drawn against the window, whichever menu is open.
INSIDE = """() => {
  const m = document.querySelector('.menu:popover-open').getBoundingClientRect();
  return { inside: m.left >= 0 && m.top >= 0 && m.right <= innerWidth && m.bottom <= innerHeight,
    rect: [m.left, m.top, m.right, m.bottom].map(Math.round), window: [innerWidth, innerHeight] };
}"""
LOW = """() => { const t = document.querySelector('.oa-et');
  t.style.marginTop = `${innerHeight - t.getBoundingClientRect().top - 150}px`; }"""
HEADS = "() => [...document.querySelectorAll('[data-act=\"et-head\"]')].map((b) => b.dataset.col)"


def menus_inside(page: Any) -> list[Any]:
    """Each head's menu and Columns opened in turn: those that reach past the window."""
    out = []
    for button in [*(f'[data-act="et-head"][data-col="{c}"]' for c in page.evaluate(HEADS)),
                   '[data-act="et-columns"]']:  # fmt: skip
        page.locator(button).scroll_into_view_if_needed()
        page.click(button)
        page.wait_for_selector(".menu:popover-open")
        got = page.evaluate(INSIDE)
        if not got["inside"]:
            out.append((button, got))
        page.keyboard.press("Escape")
        page.wait_for_selector(".menu:popover-open", state="detached")
    return out


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_every_menu_opens_inside_the_window_even_with_its_head_at_the_foot(
    page_at, label_host, width, theme
):
    page = page_at(f"{label_host}{PAGE}?drug=acetylsalicylic%20acid", width=width, theme=theme)
    assert menus_inside(page) == []
    page.evaluate(LOW)
    page.evaluate("() => window.scrollTo(0, 0)")
    assert menus_inside(page) == []


# Every cell's and control's box, to compare before and after something opens or arrives.
BOXES = """() => [...document.querySelectorAll('.oa-et-tools, .oa-et-table th, .oa-et-table td')]
  .map((e) => e.getBoundingClientRect())
  .map((r) => [r.left, r.top, r.width, r.height].map(Math.round))"""
HEAD_TOPS = """() => [...document.querySelectorAll('.oa-et-tools, .oa-et-table thead th')]
  .map((e) => Math.round(e.getBoundingClientRect().top))"""


@pytest.mark.parametrize("width", WIDTHS)
def test_opening_a_menu_moves_nothing_and_the_rows_arriving_move_no_head(
    page_at, chromium, stats_host, width
):
    page = page_at(warfarin(stats_host), width=width)
    show(page, "cases")
    before = page.evaluate(BOXES)
    for button in ('[data-act="et-head"][data-col="cases"]', '[data-act="et-columns"]'):
        page.locator(button).dispatch_event("click")  # no scrolling it into view first
        page.wait_for_selector(".menu:popover-open")
        assert page.evaluate(BOXES) == before, button
        page.keyboard.press("Escape")
    # the heads and the tools are drawn at once, where they stay once the rows have come
    slow = chromium.new_context(viewport={"width": width, "height": 900})
    try:
        late = slow.new_page()
        held: list[Any] = []
        late.route("**/api/events?*", lambda route: held.append(route))
        late.goto(warfarin(stats_host))
        late.wait_for_selector(".oa-et-loading")
        drawn = late.evaluate(HEAD_TOPS)
        held[0].continue_()
        late.wait_for_selector(".oa-et-table tbody tr[data-key]")
        assert late.evaluate(HEAD_TOPS) == drawn
    finally:
        slow.close()


def show(page: Any, *columns: str) -> None:
    """Ticks these columns in Columns."""
    page.click('[data-act="et-columns"]')
    for column in columns:
        page.click(f'[data-act="et-col"][data-v="{column}"]')
    page.keyboard.press("Escape")


def order(page: Any) -> list[str]:
    """The keys of the rows shown, top to bottom."""
    return page.eval_on_selector_all(
        ".oa-et-table tbody tr[data-key]", "rows => rows.map((r) => r.dataset.key)"
    )


def test_trend_has_no_menu_and_pressing_it_changes_nothing(page_at, stats_host):
    page = page_at(warfarin(stats_host))
    before = order(page)
    trend = page.locator('.oa-et-table thead th[data-col="trend"]')
    assert trend.locator("button, .icon").count() == 0
    trend.click()
    assert page.locator(".menu:popover-open").count() == 0 and order(page) == before
    tipped = page.locator("tbody tr:first-child .oa-et-trend").get_attribute("data-tip")
    assert " to " in tipped and (", most in " in tipped or tipped.startswith("No case"))


def test_a_drugs_rows_are_the_releases_and_a_head_sorts_them(page_at, stats_host, stats_client):
    asked = stats_client.get("/api/events", params={"product": "warfarin"}).json()
    page = page_at(warfarin(stats_host))
    shown = page.locator(".oa-et-count strong").inner_text()
    assert shown == str(len(asked["rows"]))
    named = [dict(zip(asked["columns"], r, strict=True)) for r in asked["rows"]]
    first = sorted(named, key=lambda r: (-r["newest"], r["pt"].lower()))[0]
    assert order(page)[0] == f"warfarin|{first['pt'].lower()}"  # most cases this quarter first
    head = '.oa-et-table th[data-col="%s"]'
    assert page.get_attribute(head % "newest", "aria-sort") == "descending"
    page.click('[data-act="et-cycle"][data-col="eb05"]')  # highest first, the column's own way
    page.click('[data-act="et-cycle"][data-col="eb05"]')  # then the other
    eb05 = page.evaluate(COLUMN, "eb05")
    numbers = [float(v) for v in eb05 if v]
    assert numbers == sorted(numbers) and all(eb05[: len(numbers)])  # empty values last
    assert page.get_attribute(head % "eb05", "aria-sort") == "ascending"
    assert page.get_attribute(head % "newest", "aria-sort") is None
    assert page.get_attribute('[data-act="et-head"][data-col="eb05"]', "aria-pressed") == "true"


def test_a_bound_typed_narrows_at_once_and_show_all_clears_it(page_at, stats_host):
    page = page_at(warfarin(stats_host))
    every = len(order(page))
    show(page, "cases")
    page.click('[data-act="et-head"][data-col="cases"]')
    page.fill('[data-et-bound="cases"]', "20")
    cases = [int(v.replace(",", "")) for v in page.evaluate(COLUMN, "cases")]
    assert cases and min(cases) >= 20 and len(cases) < every
    assert "at least 20 cases" in page.get_attribute(
        '[data-act="et-head"][data-col="cases"]', "data-tip"
    )
    page.fill('[data-et-bound="cases"]', "-1")  # refused: the box is marked and nothing changes
    assert page.get_attribute('[data-et-bound="cases"]', "aria-invalid") == "true"
    assert len(order(page)) == len(cases)
    page.click('[data-act="et-unbound"]')
    assert len(order(page)) == every


def test_the_label_answer_links_its_label_and_its_head_counts_before_it_narrows(
    page_at, label_host
):
    page = page_at(f"{label_host}{PAGE}?drug=acetylsalicylic%20acid")
    show(page, "label")
    link = page.locator("tbody a.oa-et-label").first
    assert link.get_attribute("target") == "_blank"
    assert link.get_attribute("href").startswith("https://dailymed.nlm.nih.gov/")
    assert link.get_attribute("data-tip") == "Opens the label on DailyMed in a new tab"
    page.click('[data-act="et-head"][data-col="label"]')
    menu = page.locator(".menu:popover-open")
    assert menu.locator(".menu-heading").inner_text().lower() == "show events whose label status is"
    assert "Counts are events in the list before Label narrows it." in menu.inner_text()
    first = menu.locator('[data-act="et-tick"]').first
    counts = menu.locator(".choice-count").all_inner_texts()
    first.click()
    assert (
        menu.locator(".choice-count").all_inner_texts() == counts
    )  # its own ticks change no count
    assert menu.locator('[data-act="et-tick-all"]').inner_text() == "Show all"
    menu.locator('[data-act="et-tick-all"]').click()
    menu.locator('[data-act="et-tick-all"]').click()  # Deselect all: no event is left
    assert page.locator("tbody .oa-et-none").count() == 1
    menu.locator('[data-act="et-tick-all"]').click()  # Show all: every event again
    page.keyboard.press("Escape")
    page.click('[data-act="et-forms"]')
    page.wait_for_selector(".oa-et-forms-menu .oa-et-form")
    forms = page.locator(".oa-et-forms-menu .oa-et-form").all_inner_texts()
    assert len(forms) == 2 and all(" on the " in f for f in forms)


def test_a_hosts_column_row_class_keys_marks_and_pager_are_drawn(page_at, stats_host):
    page = page_at(f"{stats_host}{PAGE}?mode=rows")
    heads = page.evaluate(
        "() => [...document.querySelectorAll('.oa-et-table thead th')].map((h) => h.dataset.col)"
    )
    assert heads[:2] == ["event", "step"] and "eb05" in heads
    assert order(page) == ["beta:Nausea", "alpha:Headache"]  # two of three: the host's pager
    assert page.locator(".demo-pager").inner_text() == "Events 1 to 2 of 3"
    tinted = page.evaluate(
        "() => [...document.querySelectorAll('tbody tr.oa-tinted')].map((r) => r.dataset.key)"
    )
    assert tinted == ["alpha:Headache"]
    marked = page.locator("tbody td.oa-et-marked")
    assert (
        marked.count() == 1 and marked.get_attribute("data-tip") == "Past the line: EB05 at least 2"
    )
    page.click('[data-act="et-head"][data-col="step"]')
    page.click('[data-act="et-tick"][data-v="High"]')
    assert order(page) == ["beta:Nausea", "beta:Headache"]
    page.keyboard.press("Escape")
    page.click('[data-act="et-head"][data-col="prr"]')
    assert "The line: PRR at least 2." in page.inner_text(".menu:popover-open")
    page.keyboard.press("Escape")
    page.click('[data-act="et-columns"]')
    always = page.locator(".oa-et-always")
    assert always.inner_text() == "PRR" and always.get_attribute("data-tip") == "Always shown here"
    page.keyboard.press("Escape")
    page.click('tbody tr[data-key="beta:Nausea"] th')
    assert page.evaluate("window.opened") == ["Nausea"]
    assert page.locator("tbody tr[aria-expanded], tr.oa-et-opened").count() == 0  # none opens


# The opened row as it stands: the rows marked open and closed, each open cell, the row it sits
# under, how many columns it spans of how many, the host's words in it, whether it is the box the
# host drew in, whether that box lies inside the frame, as the window shows it, and whether the
# frame scrolls sideways.
OPENED = """() => {
  const rows = [...document.querySelectorAll('.oa-et-table tbody tr[data-key]')];
  const cells = [...document.querySelectorAll('.oa-et-table tr.oa-et-opened')];
  const cell = cells[0], box = cell?.querySelector('.oa-et-opened-box');
  const scroller = document.querySelector('.oa-et-frame');
  const frame = scroller.getBoundingClientRect(), b = box?.getBoundingClientRect();
  return {
    open: rows.filter((r) => r.getAttribute('aria-expanded') === 'true').map((r) => r.dataset.key),
    closed: rows.filter((r) => r.getAttribute('aria-expanded') === 'false').length,
    rows: rows.length, cells: cells.length, handle: window.table.opened(),
    under: cell?.previousElementSibling?.dataset.key ?? null,
    span: cell ? [cell.cells.length, cell.cells[0].colSpan] : null,
    heads: document.querySelectorAll('.oa-et-table thead th').length,
    words: box?.querySelector('.demo-opened')?.textContent ?? null,
    same: !!box && box === window.box,
    inView: !!b && b.left >= frame.left - 1 && b.right <= frame.right + 1,
    scrolls: scroller.scrollWidth > scroller.clientWidth,
  };
}"""
# every box above the opened row and the row itself: the tools, the heads and the rows' cells
ABOVE = """(key) => {
  const rows = [...document.querySelectorAll('.oa-et-table tbody tr[data-key]')];
  const upTo = rows.slice(0, rows.findIndex((r) => r.dataset.key === key) + 1);
  return [...document.querySelectorAll('.oa-et-tools, .oa-et-table thead th'),
    ...upTo.flatMap((r) => [...r.cells])]
    .map((e) => e.getBoundingClientRect())
    .map((r) => [r.left, r.top, r.width, r.height].map(Math.round));
}"""


def sort_by(page: Any, column: str, direction: str) -> None:
    head = f'.oa-et-table th[data-col="{column}"]'
    wanted = {"asc": "ascending", "desc": "descending"}[direction]
    while page.get_attribute(head, "aria-sort") != wanted:
        page.click(f'[data-act="et-cycle"][data-col="{column}"]')


def press_row(page: Any, key: str) -> None:
    page.click(f'tbody tr[data-key="{key}"] th')


@pytest.mark.parametrize("width", [320, 1440])
def test_a_hosts_opened_row_keeps_its_cell_under_it_one_at_a_time_and_moves_nothing_above(
    page_at, stats_host, width
):
    page = page_at(f"{stats_host}{PAGE}?mode=opened", width=width)
    shut = page.evaluate(OPENED)
    assert shut["cells"] == 0 and shut["open"] == [] and shut["closed"] == shut["rows"] == 2
    above = page.evaluate(ABOVE, "beta:Nausea")
    press_row(page, "beta:Nausea")
    got = page.evaluate(OPENED)
    assert got["open"] == ["beta:Nausea"] and got["handle"] == "beta:Nausea", got
    assert got["cells"] == 1 and got["under"] == "beta:Nausea", got
    assert got["span"] == [1, got["heads"]] and got["words"] == "The cell of Nausea", got
    assert got["same"] and got["inView"], got
    assert page.evaluate(ABOVE, "beta:Nausea") == above  # opening it moves nothing above
    # a press in the cell, on its words or its button, leaves the row open
    page.click(".demo-opened")
    page.click('[data-act="demo-in-cell"]')
    assert page.evaluate("window.inCell") == 1 and page.evaluate(OPENED)["cells"] == 1
    assert page.evaluate("window.opened") == ["Nausea"]  # the host's press heard once
    # the table scrolled sideways, on a phone, the cell's box stays in view
    assert got["scrolls"] or width > 320, got
    page.evaluate("() => { document.querySelector('.oa-et-frame').scrollLeft = 10000; }")
    assert page.evaluate(OPENED)["inView"]
    page.evaluate("() => { document.querySelector('.oa-et-frame').scrollLeft = 0; }")

    # a sort, a paint and new rows keep the cell under its row as the host drew it
    show(page, "cases")
    sort_by(page, "cases", "asc")
    assert order(page) == ["beta:Headache", "beta:Nausea"]
    page.evaluate("() => window.table.paint()")
    page.evaluate("() => window.table.update({ rows: window.ROWS.map((r) => ({ ...r })) })")
    got = page.evaluate(OPENED)
    assert got["under"] == "beta:Nausea" and got["same"] and got["cells"] == 1, got
    assert page.evaluate("window.drawn") == ["beta:Nausea"]  # drawn once

    # one open at a time, and a second press closes it
    press_row(page, "beta:Headache")
    got = page.evaluate(OPENED)
    assert got["open"] == ["beta:Headache"] and got["cells"] == 1, got
    assert got["under"] == "beta:Headache" and got["words"] == "The cell of Headache", got
    press_row(page, "beta:Headache")
    got = page.evaluate(OPENED)
    assert got["cells"] == 0 and got["open"] == [] and got["handle"] is None, got

    # its row leaving the page closes it, and coming back does not open it again
    press_row(page, "beta:Nausea")
    sort_by(page, "event", "asc")
    assert "beta:Nausea" not in order(page)
    got = page.evaluate(OPENED)
    assert got["cells"] == 0 and got["handle"] is None, got
    sort_by(page, "cases", "desc")
    assert "beta:Nausea" in order(page) and page.evaluate(OPENED)["cells"] == 0

    # a host opens a row by its key
    page.evaluate(
        "() => window.table.update({ opened: { key: 'alpha:Headache', draw: window.drawCell } })"
    )
    got = page.evaluate(OPENED)
    assert got["open"] == ["alpha:Headache"] and got["under"] == "alpha:Headache", got


def test_a_pages_tick_menu_tells_each_change_and_keeps_its_height(page_at, stats_host):
    page = page_at(f"{stats_host}{PAGE}?mode=rows")
    page.click('[data-act="demo-ticks"]')
    menu = page.locator(".menu:popover-open")
    high = menu.bounding_box()["height"]
    menu.locator('[data-act="et-tick"][data-v="a"]').click()
    menu.locator('[data-act="et-tick-all"]').click()
    menu.locator('[data-act="et-tick-all"]').click()
    assert page.evaluate("window.ticked") == [["b"], None, []]
    assert menu.bounding_box()["height"] == high


KEPT = "() => Object.keys(localStorage).filter((k) => k.startsWith('open-altio.events'))"


def choose(page: Any) -> None:
    """Shows IC and Total cases, and keeps only events of at least 10 cases."""
    show(page, "ic", "cases")
    page.click('[data-act="et-head"][data-col="cases"]')
    page.fill('[data-et-bound="cases"]', "10")
    page.keyboard.press("Escape")


def seen(page: Any) -> dict[str, Any]:
    return page.evaluate("""() => ({
      heads: [...document.querySelectorAll('.oa-et-table thead th')].map((h) => h.dataset.col),
      rows: [...document.querySelectorAll('.oa-et-table tbody tr')].map((r) => r.dataset.key),
      bound: document.querySelector('[data-act="et-head"][data-col="cases"]')
        .getAttribute('aria-pressed') })""")


@pytest.mark.parametrize("where", ["browser", "host"])
def test_the_persons_columns_and_bound_come_back_on_a_reload_and_the_sort_does_not(
    page_at, stats_host, where
):
    url = warfarin(stats_host) + ("&hostkept=1" if where == "host" else "")
    page = page_at(url)
    choose(page)
    chosen = seen(page)
    assert "ic" in chosen["heads"] and chosen["bound"] == "true"
    page.reload()
    settle(page)
    assert seen(page) == chosen
    if where == "host":
        assert page.evaluate(KEPT) == []  # the host keeps them, not this browser
        kept = page.evaluate("() => JSON.parse(localStorage.getItem('host-kept'))")
        assert "events.sort" not in kept and kept["events.bounds"] == {"cases": 10}
    else:
        assert sorted(page.evaluate(KEPT)) == [
            f"open-altio.events.{k}" for k in ("bounds", "columns")
        ]


def test_a_row_opened_as_a_drugs_table_is_drawn_opens_once_its_rows_have_come(
    page_at, stats_host, stats_client
):
    pt = stats_client.get("/api/events", params={"product": "warfarin"}).json()["rows"][-1][0]
    key = f"warfarin|{pt.lower()}"
    page = page_at(f"{warfarin(stats_host)}&opened={quote(key)}")
    got = page.evaluate(OPENED)
    assert got["open"] == [key] and got["under"] == key and got["cells"] == 1, got
    assert page.evaluate("window.drawn") == [f"warfarin:{pt}"]


LIMITS = "&limits=" + quote('[[{"column":"eb05","at_least":2},{"column":"cases","at_least":3}]]')
COUNT = ".oa-et-tools > .oa-et-count:not(.oa-et-quarters)"
HEAD_EB05 = '[data-act="et-head"][data-col="eb05"]'


def test_a_tables_thresholds_are_its_heads_values_every_one_and_start_again_on_a_visit(
    page_at, stats_host, stats_client
):
    page = page_at(warfarin(stats_host) + LIMITS)
    page.wait_for_function("!document.querySelector('.oa-et-due')")
    assert page.locator(".oa-et > :first-child").evaluate("(e) => e.className") == "oa-et-tools"
    assert re.fullmatch(r"\d{4} Q\d vs \d{4} Q\d", page.locator(".oa-et-quarters").inner_text())
    now = page.locator(".oa-et-quarters span").first.get_attribute("data-tip")
    assert re.fullmatch(r"\d{4} Q\d: 1 \w{3} to \d{2} \w{3} \d{4}", now)
    tipped = page.get_attribute('[data-act="et-head"][data-col="prior"]', "data-tip")
    assert re.search(r"\d{4} Q\d, 1 \w{3} to \d{2} \w{3}", tipped)
    assert "EB05 at least 2.0, cases at least 3" in page.get_attribute(HEAD_EB05, "data-tip")
    eb05 = [float(v) for v in page.evaluate(COLUMN, "eb05")]
    assert eb05 and min(eb05) >= 2
    every = len(stats_client.get("/api/events", params={"product": "warfarin"}).json()["rows"])
    meeting, of = page.locator(COUNT).inner_text().split(" events")[0].split(" of ")
    assert int(meeting) == len(eb05) and int(of) == every
    assert f"{every - len(eb05)} " in page.locator(".oa-et-limit-words").inner_text()
    # both values in its head's menu, in place, each with a reset arrow whose room is kept
    page.click('[data-act="et-head"][data-col="eb05"]')
    first, second = '[data-et-limit="eb05"][data-i="0"]', '[data-et-limit="eb05"][data-i="1"]'
    assert page.input_value(first) == "2.0" and page.input_value(second) == "3"
    reset = page.locator('[data-act="et-relimit"][data-i="1"]')
    assert reset.get_attribute("data-state") == "off" and reset.bounding_box() is not None
    at = page.locator(second).bounding_box()
    page.fill(second, "1")
    assert page.locator(second).bounding_box() == at  # typing moves nothing
    assert page.get_attribute(second, "data-changed") == "true"
    assert reset.get_attribute("data-state") == "on"
    assert len(page.evaluate(COLUMN, "eb05")) >= len(eb05)
    assert "cases at least 1" in page.get_attribute(HEAD_EB05, "data-tip")
    reset.click()
    assert page.input_value(second) == "3"
    page.click('.oa-et-menu-line [data-act="et-unbound"]')  # Show every event takes all of them off
    assert "at least" not in page.get_attribute(HEAD_EB05, "data-tip")
    assert page.locator(COUNT).inner_text() == f"{every} events"
    # never kept: a visit starts again at what was given
    page.keyboard.press("Escape")
    page.reload()
    settle(page)
    assert "EB05 at least 2.0, cases at least 3" in page.get_attribute(HEAD_EB05, "data-tip")


def test_a_threshold_holds_back_with_its_column_hidden_and_opens_in_its_menu_once_shown(
    page_at, stats_host
):
    limits = quote('[[{"column":"prr","at_least":1000000}]]')
    page = page_at(warfarin(stats_host) + f"&limits={limits}")
    assert page.locator('th[data-col="prr"]').count() == 0
    assert page.locator("tbody .oa-et-none").count() == 1
    show(page, "prr")
    page.click('[data-act="et-head"][data-col="prr"]')
    page.fill('[data-et-limit="prr"][data-i="0"]', "0")
    assert len(order(page)) > 0


def test_with_screens_of_columns_only_a_showing_columns_screen_holds_back(page_at, stats_host):
    limits = quote('[[{"column":"prr","at_least":1000000}]]')
    page = page_at(warfarin(stats_host) + f"&limits={limits}&ofcolumns=1")
    assert len(order(page)) > 0
    show(page, "prr")
    assert page.locator("tbody .oa-et-none").count() == 1


def test_show_every_event_takes_every_screen_off_from_one_heads_menu(
    page_at, stats_host, stats_client
):
    limits = quote('[[{"column":"eb05","at_least":1000000}],[{"column":"prr","at_least":1000000}]]')
    page = page_at(warfarin(stats_host) + f"&limits={limits}")
    every = len(stats_client.get("/api/events", params={"product": "warfarin"}).json()["rows"])
    page.click('[data-act="et-head"][data-col="eb05"]')
    page.click('.oa-et-menu-line [data-act="et-unbound"]')
    assert page.locator(COUNT).inner_text() == f"{every} events"


def test_a_row_is_kept_only_when_every_screen_passes_and_the_export_says_the_same(
    page_at, stats_host
):
    none = '[{"column":"newest","at_least":100000}]'
    every = '[{"column":"prior","at_least":0}]'
    page = page_at(warfarin(stats_host) + "&limits=" + quote(f"[{every}]"))
    assert len(order(page)) > 0
    page = page_at(warfarin(stats_host) + "&limits=" + quote(f"[{none},{every}]"))
    assert page.locator("tbody .oa-et-none").count() == 1  # the screen no row passes holds all back
    said = """async (screens) => {
      const { meetsThresholds } = await import('/ui/app.js');
      const row = { eb05: 2.5, cases: 3, pair_cases: 2 };
      return meetsThresholds(row, screens); }"""
    one_fails = [[{"column": "eb05", "above": 9}], [{"column": "eb05", "at_least": 2}]]
    both_pass = [[{"column": "eb05", "above": 1}], [{"column": "eb05", "at_least": 2}]]
    within = [[{"column": "eb05", "at_least": 2}, {"column": "cases", "at_least": 3}]]
    assert page.evaluate(said, one_fails) is False
    assert page.evaluate(said, both_pass) is True
    assert page.evaluate(said, within) is False  # all of a screen together, on its own count
    assert page.evaluate(said, []) is True


def test_a_head_shows_an_arrow_only_for_a_chosen_sort_up_for_highest_first(page_at, stats_host):
    page = page_at(warfarin(stats_host))
    shown = """(col) => [...document.querySelectorAll(`th[data-col="${col}"] .oa-sort path`)]
      .filter((p) => getComputedStyle(p).stroke !== 'rgba(0, 0, 0, 0)')
      .map((p) => p.getAttribute('class'))"""
    page.mouse.move(0, 0)
    assert page.evaluate(shown, "newest") == ["oa-sort-up"]  # the table opens highest first
    assert page.evaluate(shown, "eb05") == []
    page.click('[data-act="et-cycle"][data-col="newest"]')
    page.mouse.move(0, 0)
    assert page.evaluate(shown, "newest") == ["oa-sort-down"]


def test_a_heads_arrow_cycles_highest_lowest_and_the_tables_own_order(page_at, stats_host):
    page = page_at(warfarin(stats_host))
    head = '.oa-et-table th[data-col="eb05"]'
    arrow = '[data-act="et-cycle"][data-col="eb05"]'
    start = order(page)
    page.click(arrow)
    assert page.get_attribute(head, "aria-sort") == "descending"
    page.click(arrow)
    assert page.get_attribute(head, "aria-sort") == "ascending"
    page.click(arrow)
    assert page.get_attribute(head, "aria-sort") is None and order(page) == start
    assert page.get_attribute('.oa-et-table th[data-col="newest"]', "aria-sort") == "descending"


def test_a_row_a_host_keeps_beyond_the_thresholds_shows_and_is_not_counted_as_meeting(
    page_at, stats_host, stats_client
):
    asked = stats_client.get("/api/events", params={"product": "warfarin"}).json()
    last = asked["rows"][-1][0]
    high = quote('[[{"column":"newest","at_least":100000}]]')
    page = page_at(warfarin(stats_host) + f"&limits={high}&beyond={quote(last)}")
    assert order(page) == [f"warfarin|{last.lower()}"]
    assert page.locator(COUNT).inner_text().startswith("0 of ")
    n = len(asked["rows"]) - 1
    assert f"{n} " in page.locator(".oa-et-limit-words").inner_text()


def test_a_hosts_listed_column_starts_hidden_and_narrows_by_its_ticks(page_at, stats_host):
    page = page_at(f"{stats_host}{PAGE}?mode=listed")
    assert page.locator('th[data-col="step"]').count() == 0
    show(page, "step")
    assert page.locator('th[data-col="step"]').count() == 1
    page.click('[data-act="et-head"][data-col="step"]')
    assert "show steps" in page.inner_text(".menu:popover-open").lower()


# ---- a drug's own Events tab: a press on a row opens its event ---------------------------------
OWN_ROWS = ".oa-et-frame > table > tbody > tr[data-key]"


def own_events(page_at, stats_host, width=1440):
    """The Events tab of a drug's own page, every event showing."""
    page = page_at(f"{stats_host}/product/warfarin/events", width=width)
    page.wait_for_selector('[data-act="et-head"][data-col="eb05"]')
    page.click('[data-act="et-head"][data-col="eb05"]')
    page.click('.oa-et-menu-line [data-act="et-unbound"]')
    page.keyboard.press("Escape")
    page.wait_for_selector(OWN_ROWS)
    return page


STILL = """(el) => new Promise((done) => {
  let last, still = 0;
  const look = () => {
    const y = el.getBoundingClientRect().top;
    still = y === last ? still + 1 : 0;
    last = y;
    if (still >= 10) done(); else requestAnimationFrame(look);
  };
  look();
})"""


def press_own_row(page, n):
    """A press where the row stands, once it stands still: an open row's copy lies over it, as a
    person meets it, and what comes into the open event moves the rows under it."""
    cell = page.locator(OWN_ROWS).nth(n).locator("td").first
    cell.evaluate(STILL)
    cell.click(force=True)


def own_open_rows(page):
    return page.locator(f'{OWN_ROWS}[aria-expanded="true"]').evaluate_all(
        "rows => rows.map((r) => r.dataset.key)"
    )


@pytest.mark.parametrize("width", [390, 1440])
def test_a_press_on_a_row_of_a_drugs_events_tab_opens_its_event_and_again_closes_it(
    page_at, stats_host, width
):
    page = own_events(page_at, stats_host, width)
    keys = page.locator(OWN_ROWS).evaluate_all("rows => rows.map((r) => r.dataset.key)")
    assert len(keys) >= 2, keys

    press_own_row(page, 0)
    page.wait_for_selector(".oa-ev")
    assert own_open_rows(page) == [keys[0]]
    tabs = '.oa-ev [data-act="ev-tab"]'
    assert page.locator(tabs).evaluate_all("tabs => tabs.map((t) => t.dataset.v)")[:3] == [
        "overview",
        "compared",
        "cases",
    ]
    for tab in ("compared", "cases"):
        page.click(f'{tabs}[data-v="{tab}"]')
        assert page.locator(f'.oa-ev [data-v="{tab}"][aria-selected="true"]').count() == 1

    # the rows under the open event stand still only once its Cases have come
    page.wait_for_function(
        "() => { const p = document.querySelector('.oa-ev .oa-ev-pane:not([hidden])');"
        " return p && p.querySelector('.oa-ec-cases')"
        " && !p.querySelector('.oa-ec-cases[data-state]')"
        " && !p.querySelector('.oa-ec-skeleton'); }"
    )

    # one row at a time, and a press on the open row closes it
    press_own_row(page, 1)
    page.wait_for_function(
        'key => document.querySelector(`tr[data-key="${key}"] + tr.oa-et-opened .oa-ev`)',
        arg=keys[1],
    )
    assert own_open_rows(page) == [keys[1]] and page.locator("tr.oa-et-opened").count() == 1
    press_own_row(page, 1)
    page.wait_for_selector(".oa-ev", state="detached")
    assert own_open_rows(page) == [] and page.locator("tr.oa-et-opened").count() == 0


CAP = """() => {
  const ev = document.querySelector('.oa-ev'), pane = ev.querySelector('.oa-ev-pane:not([hidden])');
  const table = ev.closest('table');
  const under = parseFloat(getComputedStyle(table).getPropertyValue('--ev-st2'));
  return { max: getComputedStyle(ev).maxHeight, room: innerHeight - under - 80,
           scrolls: getComputedStyle(pane).overflowY, held: pane.style.minHeight };
}"""


def test_an_opened_event_is_no_taller_than_the_window_and_its_tab_scrolls_inside(
    page_at, stats_host
):
    page = own_events(page_at, stats_host)
    press_own_row(page, 0)
    page.wait_for_selector(".oa-ev")
    for tab in ("overview", "compared", "cases"):
        page.click(f'.oa-ev [data-act="ev-tab"][data-v="{tab}"]')
        page.wait_for_function(
            "() => { const v = getComputedStyle(document.querySelector('.oa-ev')).maxHeight;"
            " return v !== 'none'; }"
        )
        got = page.evaluate(CAP)
        assert abs(float(got["max"].removesuffix("px")) - got["room"]) <= 1, got
        assert got["scrolls"] == "auto" and got["held"] == "", got


def test_in_a_window_too_short_for_the_cap_the_page_scrolls_as_before(page_at, stats_host):
    page = own_events(page_at, stats_host)
    page.set_viewport_size({"width": 1440, "height": 460})
    press_own_row(page, 0)
    page.wait_for_selector(".oa-ev")
    got = page.evaluate(CAP)
    assert got["max"] == "none" and got["scrolls"] == "visible", got


def test_a_drugs_events_tab_starts_every_statistic_and_they_narrow_together(page_at, stats_host):
    page = page_at(f"{stats_host}/product/warfarin/events")
    page.wait_for_selector('[data-act="et-head"][data-col="eb05"]')
    assert "N at least 3" in page.get_attribute(
        '[data-act="et-head"][data-col="newest"]', "data-tip"
    )
    assert "EBGM at least 2.0" in page.get_attribute(
        '[data-act="et-head"][data-col="ebgm"]', "data-tip"
    )
    # N's value is a whole number of cases, typed in place in its own head
    page.click('[data-act="et-head"][data-col="newest"]')
    assert page.input_value('[data-et-limit="newest"][data-i="0"]') == "3"
    page.fill('[data-et-limit="newest"][data-i="0"]', "0")
    page.keyboard.press("Escape")
    page.click('[data-act="et-head"][data-col="ebgm"]')
    page.fill('[data-et-limit="ebgm"][data-i="0"]', "0")
    page.keyboard.press("Escape")
    page.click('[data-act="et-head"][data-col="eb05"]')
    page.fill('[data-et-limit="eb05"][data-i="0"]', "0")
    page.fill('[data-et-limit="eb05"][data-i="1"]', "0")
    page.keyboard.press("Escape")
    all_rows = len(order(page))
    assert all_rows > 1
    # a hidden column's start applies once Columns shows it, and narrows on top of the others
    show(page, "prr")
    shown = len(order(page))
    assert shown <= all_rows
    assert "chi" in page.get_attribute('[data-act="et-head"][data-col="prr"]', "data-tip").lower()
    page.click('[data-act="et-head"][data-col="prr"]')
    page.fill('[data-et-limit="prr"][data-i="0"]', "1000000")
    page.keyboard.press("Escape")
    assert page.locator("tbody .oa-et-none").count() == 1
    # Trend stands after every statistic, the chosen ones too
    heads = page.locator(".oa-et-frame > table > thead th").evaluate_all(
        "ths => ths.map((t) => t.dataset.col)"
    )
    assert heads.index("prr") < heads.index("trend") and heads[-1] == "trend", heads
    assert heads[:6] == ["event", "newest", "prior", "ebgm", "ebgm_prior", "eb05"], heads


def test_the_address_keeps_the_row_open_and_a_link_opens_one_past_the_thresholds(
    page_at, stats_host
):
    page = own_events(page_at, stats_host)
    key = page.locator(OWN_ROWS).first.get_attribute("data-key")
    assert "open=" not in page.url
    press_own_row(page, 0)
    page.wait_for_selector(".oa-ev")
    assert "open=" in page.url
    # a reload opens it again, though the thresholds start again and hold it back
    page.reload()
    page.wait_for_selector(".oa-ev")
    assert own_open_rows(page) == [key]
    # taken off the list, its cell closes and the address lets it go
    press_own_row(page, 0)
    page.wait_for_selector(".oa-ev", state="detached")
    assert "open=" not in page.url
