"""An event opened under its row (ui/event.js, event-dates.js, event-filters.js, event-stick.js) in
a browser, mounted by a host's page module in the cell a drug's events table opens under a row, at
320, 768, 1024 and 1440 pixels, light and dark: opening a row draws its copy, the line and the bar;
the tabs switch without moving the bar; Dates changes the window and the line says so; + Add a
filter adds a filter to the line and narrows the count; the layers stay stuck while the page
scrolls, where the table fits its frame; a host's places show what it draws; a registered pane is
drawn once and told each change; and a free page draws nothing of it."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI, Response

from open_altio.explorer.access import LocalAccess
from open_altio.explorer.app import create_app, host
from open_altio.explorer.pages import index
from open_altio.testing.browser import open_page, served, settle

WIDTHS = [320, 768, 1024, 1440]
THEMES = ["light", "dark"]
MODULE = "/event-host/page.js"
PAGE = "/event-demo"
DRUG, EVENT = "warfarin", "Haemorrhage"
KEY = f"{DRUG}|{EVENT.lower()}"
CODES = {"Female": "F", "Male": "M", "Not given": "_none"}  # the sex filter's values

# A host's page: warfarin's events table, a press on a row opening the event under it (?opened= the
# row open as the table is drawn). ?slots fills the event's places; ?pane registers a tall Overview
# that records what it is handed and each change it is told.
HOST_JS = """
import { choice, eventsTable, extend, framed, openedEvent, registerEventPane } from '/ui/app.js';

const asked = new URLSearchParams(location.search);
const SAID = ', since the host day';
window.told = [];
window.drawn = 0;
if (asked.has('slots')) {
  extend({ slots: {
    'event-bar-end': () => '<button type="button" class="btn demo-next">Next step</button>',
    'event-under-bar': (ev) => `<p class="demo-under">Under the bar of ${ev.reaction}</p>`,
    'event-line-note': () => '<span class="demo-note">A note of the host</span>',
    'event-window': (ev) => (ev.after === 'four' ? choice(ev.kind === 'host', 'Since the host day',
      null, `data-act="ev-window" data-k="host" data-from="2025-06-01" data-said="${SAID}"`,
      { radio: true }) : ''),
  } });
}
if (asked.has('pane')) {
  registerEventPane('overview', { draw: (pane, ctx) => {
    window.drawn += 1;
    window.told.push(ctx);
    pane.innerHTML = '<div class="demo-pane" style="height: 1600px">The host pane</div>';
    return { update: (next) => window.told.push(next) };
  } });
}
const PAGE = '<main class="product-page">'
  + '<section class="oa-chart oa-chart-wide" id="demo"></section>'
  + '<div class="demo-after" style="height: 1200px"></div></main>';
extend({
  routes: [(parts) => (parts[0] === 'event-demo' ? { page: 'event-demo' } : null)],
  addresses: [(parts) => parts[0] === 'event-demo'],
  pages: {
    'event-demo': (route, app) => {
      app.innerHTML = framed(PAGE, 'event-demo');
      const drug = asked.get('drug');
      window.table = eventsTable(app.querySelector('#demo'), {
        order: [['cases', 'desc'], ['event', 'asc']],
        drug, open: () => {},
        opened: {
          key: asked.get('opened'),
          draw: (box, row) => { window.ev = openedEvent(box, { drug, row }); },
        },
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
def event_host(stats_release) -> Iterator[str]:
    with served(hosted(stats_release)) as base:
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


SHORT = 470  # a window too short for an opened event's cap: the page scrolls (css/event.css)


def at(base: str, **asked: str) -> str:
    return f"{base}{PAGE}?{urlencode({'drug': DRUG, 'opened': KEY, **asked})}"


# What an opened event shows: its line's words, its tabs and the Cases count, the row's copy over
# the row, the places of its layers in the window, and whether anything scrolls the page sideways.
SEEN = """() => {
  const box = document.querySelector('.oa-et-opened-box');
  const ev = box?.querySelector('.oa-ev');
  const row = document.querySelector('.oa-et-table > tbody > tr[aria-expanded="true"]');
  const copy = box?.querySelector('.oa-ev-copy');
  const top = (el) => (el ? Math.round(el.getBoundingClientRect().top) : null);
  // the words of each part, one space apart, as a person reads them
  const words = (el) => {
    const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), out = [];
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.data.trim()) out.push(n.data.trim());
    }
    return out.join(' ').replace(/\\s+/g, ' ').replace(/ ,/g, ',');
  };
  return {
    line: ev ? words(ev.querySelector('.oa-ev-line')) : null,
    tabs: [...(ev?.querySelectorAll('.oa-ev-tab') || [])].map((t) => words(t)),
    selected: ev?.querySelector('.oa-ev-tab[aria-selected="true"]')?.dataset.v ?? null,
    count: ev?.querySelector('.oa-ev-count')?.textContent.trim() ?? null,
    fits: document.querySelector('.oa-et-frame')?.dataset.evFits ?? null,
    copyShown: !!copy && copy.getClientRects().length > 0,
    copyOver: !!copy && copy.getClientRects().length > 0
      && Math.abs(copy.getBoundingClientRect().top - row.getBoundingClientRect().top) < 1,
    copyCells: copy ? [...copy.querySelectorAll('td, th')].map((c) => c.textContent.trim()) : [],
    rowCells: row ? [...row.cells].map((c) => c.textContent.trim()) : [],
    heads: top(document.querySelector('.oa-et-table > thead')),
    copyTop: top(copy),
    line_top: top(box?.querySelector('.oa-ev-linewrap')),
    bar: top(box?.querySelector('.oa-ev-bar')),
    page: document.documentElement.scrollWidth - innerWidth,
  };
}"""


# each value of the open field: its words, its count and whether its box is ticked
CHOICES = """(els) => els.map((e) => [e.querySelector('.menu-choice-words').textContent,
  +e.querySelector('.choice-count').textContent.replace(/,/g, ''),
  e.getAttribute('aria-checked')])"""


def seen(page: Any) -> dict[str, Any]:
    return page.evaluate(SEEN)


def ready(page: Any) -> dict[str, Any]:
    """The event once its window and its count are in."""
    page.wait_for_function(
        "() => /\\d/.test(document.querySelector('.oa-ev-count')?.textContent || '')"
        " && !document.querySelector('.oa-ev-dates-skeleton')"
    )
    settle(page)
    return seen(page)


def count_of(client: Any, **window: str) -> int:
    """The event's cases asked of the release apart from the page: a group of its one reaction."""
    asked = {"product": DRUG, "reaction": EVENT, **window}
    got = client.get(f"/api/events/group?{urlencode(asked, doseq=True)}")
    assert got.status_code == 200, got.text
    return got.json()["cases"]


def dates(page: Any, words: str) -> None:
    """Opens the Dates menu from the line and picks the choice of these words."""
    page.click(".oa-ev-dates")
    page.locator(".oa-ev-dates-menu .oa-choice", has_text=words).click()
    page.wait_for_function(
        "() => /\\d/.test(document.querySelector('.oa-ev-count')?.textContent || '')"
    )
    settle(page)


def menu_words(page: Any) -> list[str]:
    return page.eval_on_selector_all(
        ".menu:popover-open :is(.menu-heading, .oa-choice, .oa-filter-row)",
        "(els) => els.map((e) => e.textContent.replace(/\\s+/g, ' ').trim())",
    )


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_opening_a_row_draws_its_copy_the_line_and_the_bar(
    page_at, event_host, stats_client, width, theme
):
    page = page_at(at(event_host), width=width, theme=theme)
    got = ready(page)
    # the window opens on the newest quarter, before it every day from the event's first case
    first = stats_client.get(f"/api/timeline?grain=day&product={DRUG}&pt={EVENT}").json()["rows"][
        0
    ][0]
    assert first == "2023-03-01"
    assert got["line"] == (
        "Before 1 Mar 2023 to 31 Mar 2026 → window 1 Apr 2026 to 30 Jun 2026, the newest quarter"
        " · + Add a filter"
    ), got
    assert got["tabs"] == ["Overview", "Compared", f"Cases {got['count']}"], got
    assert int(got["count"]) == count_of(
        stats_client, received_from="2026-04-01", received_to="2026-06-30"
    )
    assert got["selected"] == "overview", got
    assert page.locator(".oa-ev-pane:not([hidden]) .oa-ov").count() == 1  # the Overview's own
    assert got["page"] <= 0, got
    if got["fits"] == "true":
        assert got["copyShown"] and got["copyOver"] and got["copyCells"] == got["rowCells"], got
    else:
        assert not got["copyShown"], got
    # a press on the row closes it, and the event with it
    page.click(
        ".oa-ev-copy tbody th"
        if got["copyShown"]
        else f'.oa-et-table > tbody > tr[data-key="{KEY}"] th'
    )
    assert (
        page.locator(".oa-ev").count() == 0
        and page.locator('tr[aria-expanded="true"]').count() == 0
    )


def held_opening(page: Any, reply: dict[str, Any] | None = None) -> Any:
    """Presses the row with the event's first day held back, so its line waits on its skeleton;
    gives back what lets that day go on, as the release says it or as `reply`."""
    routes: list[Any] = []
    page.route("**/api/timeline**", lambda route: routes.append(route))
    page.click(f'.oa-et-table > tbody > tr[data-key="{KEY}"] th')
    page.wait_for_selector(".oa-ev-dates-skeleton")
    while not routes:
        page.wait_for_timeout(20)

    def let_go() -> None:
        for route in routes:
            route.fulfill(json=reply) if reply else route.continue_()
        page.unroute("**/api/timeline**")

    return let_go


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_nothing_moves_as_the_dates_arrive(page_at, event_host, width, theme):
    page = page_at(f"{event_host}{PAGE}?drug={DRUG}&pane=1", width=width, theme=theme)
    page.wait_for_selector(f'.oa-et-table > tbody > tr[data-key="{KEY}"]')
    let_go = held_opening(page)
    waiting = seen(page)
    let_go()
    got = ready(page)
    assert "→ window" in got["line"], got
    assert (got["bar"], got["line_top"]) == (waiting["bar"], waiting["line_top"]), width


@pytest.mark.parametrize("width", WIDTHS)
def test_nothing_moves_when_the_dates_take_less_room_than_was_held(page_at, event_host, width):
    """An event whose first case is in the newest quarter has no period before its window."""
    page = page_at(f"{event_host}{PAGE}?drug={DRUG}&pane=1", width=width)
    page.wait_for_selector(f'.oa-et-table > tbody > tr[data-key="{KEY}"]')
    let_go = held_opening(page, {"grain": "day", "rows": [["2026-05-01", 1]], "undated": 0})
    waiting = seen(page)
    let_go()
    got = ready(page)
    assert got["line"].startswith("Window 1 May 2026 to 30 Jun 2026"), got
    assert got["bar"] == waiting["bar"], width
    # the room is held only as the event opens: the next change of the dates fits its own words
    dates(page, "The newest quarter")
    held = page.evaluate("() => document.querySelector('.oa-ev-line').style.minHeight")
    assert held == "", held


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_tabs_switch_without_moving_the_bar(page_at, event_host, width, theme):
    page = page_at(at(event_host, pane="1"), width=width, theme=theme)
    ready(page)
    bar = page.locator(".oa-ev-bar")
    still = bar.bounding_box()["y"]
    for tab in ("compared", "cases", "overview"):
        page.click(f'.oa-ev-tab[data-v="{tab}"]')
        assert seen(page)["selected"] == tab
        assert page.locator(f'.oa-ev-pane[data-pane="{tab}"]').is_visible()
        assert bar.bounding_box()["y"] == still, tab
    if seen(page)["fits"] != "true":
        return
    # in a window too short for the cap the page scrolls: once the bar has stuck at the top, a tab
    # shown starts right under it and the bar stays
    page.set_viewport_size({"width": width, "height": SHORT})
    settle(page)
    page.evaluate("() => { document.querySelector('.frame-page').scrollTop += 700; }")
    settle(page)
    stuck = bar.bounding_box()["y"]
    for tab in ("cases", "overview"):
        page.click(f'.oa-ev-tab[data-v="{tab}"]')
        settle(page)
        assert bar.bounding_box()["y"] == stuck, tab
        under = bar.bounding_box()["y"] + bar.bounding_box()["height"]
        assert page.locator(f'.oa-ev-pane[data-pane="{tab}"]').bounding_box()["y"] >= under - 1


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_dates_change_the_window_and_the_line_says_so(
    page_at, event_host, stats_client, width, theme
):
    page = page_at(at(event_host), width=width, theme=theme)
    ready(page)
    page.click(".oa-ev-dates")
    page.wait_for_selector(".oa-ev-countby .oa-choice-note:has-text('%')")
    words = menu_words(page)
    assert words[:5] == [
        "The window",
        "The newest quarter (2026 Q2)",
        "The last four quarters",
        "All dates",
        "Pick days…",
    ], words
    assert words[5:8] == [
        "Compared with",
        "The period before the window",
        "The same length just before",
    ]
    assert words[8:10] == ["Count cases by", "The date FDA received the report"]
    assert words[10].startswith(
        "The date the reaction started Only reports that give this date can be counted: "
    )
    assert page.evaluate(
        "() => !!document.querySelector('.oa-ev-dates-menu').matches(':popover-open')"
    )
    page.keyboard.press("Escape")

    dates(page, "The last four quarters")
    got = seen(page)
    assert "→ window 1 Jul 2025 to 30 Jun 2026, the last four quarters" in got["line"], got
    four = count_of(stats_client, received_from="2025-07-01", received_to="2026-06-30")
    assert int(got["count"]) == four and four > 0

    dates(page, "The same length just before")
    assert seen(page)["line"].startswith("Before 1 Jul 2024 to 30 Jun 2025 → window 1 Jul 2025")

    dates(page, "All dates")
    got = seen(page)
    assert got["line"].startswith("Window 1 Mar 2023 to 30 Jun 2026, all dates"), got
    assert int(got["count"]) == count_of(
        stats_client, received_from="2023-03-01", received_to="2026-06-30"
    )
    assert (
        int(got["count"])
        == stats_client.get(f"/api/events/group?product={DRUG}&reaction={EVENT}").json()["cases"]
    )

    # counted by the date the reaction started: the window on the event dates, only those given
    dates(page, "The date the reaction started")
    got = seen(page)
    timeline = stats_client.get(
        f"/api/timeline?grain=day&by=event&product={DRUG}&pt={EVENT}"
    ).json()
    first = timeline["rows"][0][0]
    assert "counted by the date the reaction started" in got["line"], got
    assert int(got["count"]) == count_of(stats_client, event_from=first, event_to="2026-06-30")
    dates(page, "The date FDA received the report")

    # Pick days: the first day, then the last, from the calendar under the line's days
    page.click(".oa-ev-dates")
    page.locator(".oa-ev-dates-menu .oa-choice", has_text="Pick days").click()
    page.wait_for_selector(".oa-ev-cal:popover-open")
    assert page.text_content(".oa-ev-cal .menu-heading") == "The window starts on"
    page.click(".oa-ev-cal [data-act='ev-cal-months']")
    page.click(".oa-ev-cal [data-act='ev-cal-years']")
    page.click(".oa-ev-cal [data-act='ev-cal-year'][data-v='2024']")
    page.click(".oa-ev-cal [data-act='ev-cal-month'][data-v='1']")
    page.click(".oa-ev-cal [data-act='ev-cal-day'][data-v='2024-01-15']")
    page.wait_for_selector(".oa-ev-cal:popover-open .menu-heading:has-text('The window ends on')")
    page.click(".oa-ev-cal [data-act='ev-cal-months']")
    page.click(".oa-ev-cal [data-act='ev-cal-years']")
    page.click(".oa-ev-cal [data-act='ev-cal-year'][data-v='2025']")
    page.click(".oa-ev-cal [data-act='ev-cal-month'][data-v='3']")
    page.click(".oa-ev-cal [data-act='ev-cal-day'][data-v='2025-03-20']")
    page.wait_for_function(
        "() => /\\d/.test(document.querySelector('.oa-ev-count')?.textContent || '')"
    )
    got = seen(page)
    # compared with the same length just before, as picked above: 431 days before 15 Jan 2024
    assert got["line"].startswith(
        "Before 10 Nov 2022 to 14 Jan 2024 → window 15 Jan 2024 to 20 Mar 2025 ·"
    ), got
    assert int(got["count"]) == count_of(
        stats_client, received_from="2024-01-15", received_to="2025-03-20"
    )


# how a Dates choice is drawn: its words' color, the cursor over it, its ground under the mouse
DRAWN = """(el) => { const css = getComputedStyle(el); return {
  words: getComputedStyle(el.querySelector('.menu-choice-words')).color,
  tick: getComputedStyle(el.querySelector('.oa-tick')).borderTopColor,
  cursor: css.cursor, ground: css.backgroundColor }; }"""
PALE = """() => { const probe = document.createElement('span');
  probe.style.color = 'var(--ink-pale)'; document.body.append(probe);
  const color = getComputedStyle(probe).color; probe.remove(); return color; }"""


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", [320, 1440])
def test_a_dates_choice_that_cannot_be_used_is_drawn_so(page_at, event_host, width, theme):
    page = page_at(at(event_host), width=width, theme=theme)
    ready(page)
    dates(page, "All dates")
    line = seen(page)["line"]
    page.click(".oa-ev-dates")
    menu = page.locator(".oa-ev-dates-menu")
    pale = page.evaluate(PALE)
    usable = menu.locator(".oa-choice", has_text="The last four quarters")
    assert usable.evaluate(DRAWN)["words"] != pale
    for words in ("The period before the window", "The same length just before"):
        off = menu.locator(".oa-choice", has_text=words)
        assert off.get_attribute("aria-disabled") == "true", words
        off.hover()
        drawn = off.evaluate(DRAWN)
        assert (drawn["words"], drawn["tick"], drawn["cursor"]) == (pale, pale, "not-allowed"), (
            words
        )
        assert drawn["ground"] == "rgba(0, 0, 0, 0)", words  # the mouse lights nothing
        off.click(force=True)  # a press does nothing, and the menu stays
        assert menu.is_visible() and seen(page)["line"] == line, words


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_add_a_filter_puts_it_on_the_line_and_narrows(
    page_at, event_host, stats_client, width, theme
):
    page = page_at(at(event_host), width=width, theme=theme)
    ready(page)
    dates(page, "All dates")
    every = int(seen(page)["count"])
    page.click(".oa-ev-addfilter")
    page.wait_for_selector(".oa-ev-af-menu:popover-open")
    rows = page.eval_on_selector_all(
        ".oa-ev-af-fields > *",
        "(els) => els.map((e) => e.textContent.replace(/\\s+/g, ' ').trim())",
    )
    assert rows == [
        "Patient",
        "Age",
        "Sex",
        "Country",
        "Drugs",
        "Other drugs",
        "Role",
        "Dose",
        "Route",
        "Dose form",
        "Taken for",
        "Lot",
        "Course",
        "Onset",
        "Dechallenge",
        "Rechallenge",
        "Seriousness",
        "Report",
        "Reporter",
        "Report type",
        "Company",
        "Other reactions",
    ]
    # Sex: each value with its count among the event's cases, every box ticked, Deselect all below
    page.locator(".oa-ev-af-menu .oa-filter-row", has_text="Sex").click()
    page.wait_for_selector(".oa-ev-af-list .oa-choice")
    if width < 768:  # a phone's sheet shows one pane at a time
        assert page.get_attribute(".oa-ev-af-menu", "data-pane") == "options"
    choices = page.eval_on_selector_all(
        ".oa-ev-af-list .oa-choice",
        CHOICES,
    )
    assert sum(n for _, n, _ in choices) == every and all(on == "true" for *_, on in choices), (
        choices
    )
    assert page.inner_text(".oa-ev-af-foot") == "Deselect all"
    female = dict((w, n) for w, n, _ in choices)["Female"]
    # unticking the others leaves Female: the line says it, and the count is its count
    for words, _, _ in choices:
        if words != "Female":
            page.click(f'.oa-ev-af-list .oa-choice[data-v="{CODES[words]}"]')
    page.wait_for_function(
        f"() => document.querySelector('.oa-ev-count')?.textContent.trim() === '{female}'"
    )
    assert "· Sex Female + Add a filter Clear all" in seen(page)["line"]
    assert female == count_of(
        stats_client, sex="F", received_from="2023-03-01", received_to="2026-06-30"
    )
    assert page.inner_text(".oa-ev-af-foot") == "Show all"
    # Deselect all leaves no case; Show all brings every case back
    page.click(".oa-ev-af-foot .oa-link")
    page.click(".oa-ev-af-foot .oa-link")
    page.wait_for_function(
        "() => document.querySelector('.oa-ev-count')?.textContent.trim() === '0'"
    )
    assert "Sex None" in seen(page)["line"]
    page.click(".oa-ev-af-foot .oa-link")
    page.wait_for_function(
        f"() => document.querySelector('.oa-ev-count')?.textContent.trim() === '{every}'"
    )
    assert "Sex" not in seen(page)["line"]
    # a filter's x takes it away, and Clear all every filter, the window staying
    page.click('.oa-ev-af-list .oa-choice[data-v="M"]')
    page.keyboard.press("Escape")
    page.wait_for_selector(".oa-ev-line .oa-strip-x")
    page.click(".oa-ev-line .oa-strip-x")
    page.wait_for_function(
        f"() => document.querySelector('.oa-ev-count')?.textContent.trim() === '{every}'"
    )
    assert seen(page)["line"].endswith("all dates · + Add a filter")


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_layers_stay_stuck_while_the_page_scrolls(page_at, event_host, width, theme):
    page = page_at(at(event_host, pane="1"), width=width, theme=theme)
    before = ready(page)
    page.set_viewport_size({"width": width, "height": SHORT})
    settle(page)
    page.evaluate("() => { document.querySelector('.frame-page').scrollTop += 600; }")
    settle(page)
    once = seen(page)
    page.evaluate("() => { document.querySelector('.frame-page').scrollTop += 400; }")
    settle(page)
    twice = seen(page)
    if before["fits"] != "true":
        # a table wider than its frame scrolls sideways: nothing sticks, all goes with the page
        assert twice["bar"] == once["bar"] - 400, (once, twice)
        return
    heights = page.evaluate("""() => ({
      head: document.querySelector('.oa-et-table > thead').getBoundingClientRect().height,
      row: document.querySelector('.oa-ev-copy').getBoundingClientRect().height,
      line: document.querySelector('.oa-ev-linewrap').getBoundingClientRect().height })""")
    for got in (once, twice):
        assert got["copyTop"] == got["heads"] + round(heights["head"]), got
        assert abs(got["line_top"] - (got["copyTop"] + heights["row"])) <= 1, got
        assert abs(got["bar"] - (got["line_top"] + heights["line"])) <= 1, got
    assert {k: once[k] for k in ("heads", "copyTop", "line_top", "bar")} == {
        k: twice[k] for k in ("heads", "copyTop", "line_top", "bar")
    }


@pytest.mark.parametrize("width", [320, 1440])
def test_a_hosts_places_show_what_it_draws(page_at, event_host, stats_client, width):
    page = page_at(at(event_host, slots="1"), width=width)
    ready(page)
    assert page.inner_text(".oa-ev-acts .demo-next") == "Next step"
    assert page.inner_text(".oa-ev-under .demo-under") == f"Under the bar of {EVENT}"
    assert page.inner_text(".oa-ev-line .demo-note") == "A note of the host"
    page.click(".oa-ev-dates")
    words = menu_words(page)
    assert words[1:5] == [
        "The newest quarter (2026 Q2)",
        "The last four quarters",
        "Since the host day",
        "All dates",
    ], words
    page.locator(".oa-ev-dates-menu .oa-choice", has_text="Since the host day").click()
    page.wait_for_function(
        "() => /\\d/.test(document.querySelector('.oa-ev-count')?.textContent || '')"
    )
    got = seen(page)
    assert "→ window 1 Jun 2025 to 30 Jun 2026, since the host day" in got["line"], got
    assert int(got["count"]) == count_of(
        stats_client, received_from="2025-06-01", received_to="2026-06-30"
    )
    # a filter on takes the note's place
    page.evaluate("() => window.ev.setFilter('sex', ['F'])")
    page.wait_for_selector(".oa-ev-line .oa-strip-item")
    assert page.locator(".oa-ev-line .demo-note").count() == 0


@pytest.mark.parametrize("theme", THEMES)
def test_a_registered_pane_is_drawn_once_and_told_each_change(page_at, event_host, theme):
    page = page_at(at(event_host, pane="1"), theme=theme)
    ready(page)
    told = page.evaluate(
        "() => window.told.map(({ drug, reaction, window, before, dateField, kind, filters, none })"
        " => ({ drug, reaction, window, before, dateField, kind, filters, none }))"
    )
    assert page.evaluate("window.drawn") == 1
    assert told[-1] == {
        "drug": DRUG,
        "reaction": [EVENT],
        "window": {"received_from": "2026-04-01", "received_to": "2026-06-30"},
        "before": {"before_from": "2023-03-01", "before_to": "2026-03-31"},
        "dateField": "received",
        "kind": "quarter",
        "filters": [],
        "none": False,
    }
    dates(page, "The last four quarters")
    page.evaluate("() => window.ev.setFilter('sex', ['F'])")
    page.click('.oa-ev-tab[data-v="cases"]')
    page.click('.oa-ev-tab[data-v="overview"]')
    last = page.evaluate(
        "() => { const c = window.told.at(-1);"
        " return { window: c.window, filters: c.filters, q: c.query({ page: '2' }) }; }"
    )
    assert page.evaluate("window.drawn") == 1  # switching tabs draws it no second time
    assert last["window"] == {"received_from": "2025-07-01", "received_to": "2026-06-30"}
    assert last["filters"] == [{"field": "sex", "values": ["F"]}]
    assert (
        last["q"] == f"product={DRUG}&sex=F&received_from=2025-07-01&received_to=2026-06-30&page=2"
    )


def test_a_free_page_draws_nothing_of_an_opened_event(page_at, event_host):
    # a drug's own page opens one only as a row is pressed
    page = page_at(f"{event_host}/product/{DRUG}")
    assert page.locator(".oa-ev, .oa-ev-copy, .oa-ev-line").count() == 0
    assert page.locator('.oa-et-table tbody tr[aria-expanded="true"]').count() == 0
    # a host's table with no `opened` opens nothing either
    page = page_at(f"{event_host}{PAGE}?drug={DRUG}")
    assert page.locator(".oa-et-table tbody tr").count() > 1
    assert page.locator(".oa-ev, .oa-et-opened").count() == 0
