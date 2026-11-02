"""An opened event's breakdowns (ui/event-breakdowns.js, ui/event-breakdowns-menu.js) and the
filters of + Add a filter they share (ui/event-fields.js) in a browser, in the opened event's own
frame on a host's page: the three groups under the chart, each line reading /api/breakdowns; a line
pressed putting the value it shows on the event's line and listing every value with tick boxes and
counts, those counts /api/breakdowns' own under the event's other filters; a tick narrowing the
event's other panes to what the published questions count under it; Deselect all and Show all; a
line with no filter; + Add a filter's new fields; a host's alarm the only warning color; and, at
320, 768, 1024 and 1440 pixels, light and dark, nothing scrolling sideways and nothing moving as
the answers come."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode

import httpx
import pytest
from fastapi import FastAPI, Response

from open_altio.explorer.access import LocalAccess
from open_altio.explorer.app import create_app, host
from open_altio.explorer.pages import index
from open_altio.testing.browser import open_page, served, settle

# a folder to keep the pictures in, at each width and theme, to look at beside the design
SHOTS = os.environ.get("OPEN_ALTIO_BREAKDOWN_SHOTS")
WIDTHS = [320, 768, 1024, 1440]
THEMES = ["light", "dark"]
MODULE = "/breakdowns-host/page.js"
PAGE = "/breakdowns-demo"
DRUG, EVENT = "warfarin", "Haemorrhage"
KEY = f"{DRUG}|{EVENT.lower()}"
GROUPS = {
    "Clinical picture": "How serious, and who is affected",
    "Causality": "Timing, dechallenge, dose, other drugs",
    "Data quality": "How far the reports can be trusted",
}
OUTCOME = {"DE": "Death", "LT": "Life-threatening", "HO": "Hospitalization"}
FOOT = ".oa-bd-menu .oa-bd-foot .oa-link"
BOXES = ".oa-bd-menu .oa-choice"

# A host's page: the drug's events table, the event opened under its row in the frame, a pane of the
# host's on Compared that keeps each ctx it is told; ?screens gives the host's screens; ?later waits
# for window.drawTable(), and window.hold() holds the breakdowns' answers until window.letGo().
HOST_JS = """
import { eventsTable, extend, framed, openedEvent, registerEventPane } from '/ui/app.js';

const asked = new URLSearchParams(location.search);
const ask = window.fetch;
let gate = null;
window.hold = () => {
  let open;
  gate = new Promise((r) => { open = r; });
  window.letGo = () => { gate = null; open(); };
};
window.fetch = (...a) => (gate && String(a[0]).includes('/api/breakdowns')
  ? gate.then(() => ask(...a)) : ask(...a));
window.told = [];
registerEventPane('compared', { draw: (pane, ctx) => {
  window.told.push(ctx.query());
  pane.innerHTML = '<p class="demo-pane">The host pane</p>';
  return { update: (next) => window.told.push(next.query()) };
} });
extend({
  routes: [(parts) => (parts[0] === 'breakdowns-demo' ? { page: 'breakdowns-demo' } : null)],
  addresses: [(parts) => parts[0] === 'breakdowns-demo'],
  pages: {
    'breakdowns-demo': (route, app) => {
      const box = '<section class="oa-chart oa-chart-wide" id="demo"></section>';
      app.innerHTML = framed(`<main class="product-page">${box}</main>`, 'breakdowns-demo');
      const drug = asked.get('drug');
      const screens = JSON.parse(asked.get('screens') || '[]');
      const at = app.querySelector('#demo');
      window.drawTable = () => eventsTable(at, { drug, open: () => {}, opened: {
        key: asked.get('opened'),
        draw: (box, row) => { window.ev = openedEvent(box, { drug, row, screens }); },
      } });
      if (!asked.has('later')) window.drawTable();
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
def base(stats_release) -> Iterator[str]:
    with served(hosted(stats_release)) as at:
        yield at


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


def opened(page_at: Any, base: str, *, four: bool = True, **how: Any) -> Any:
    """The event opened in its frame, on the last four quarters, every answer in."""
    screens = how.pop("screens", None)
    asked = {"drug": DRUG, "opened": KEY} | ({"screens": json.dumps(screens)} if screens else {})
    page = page_at(f"{base}{PAGE}?{urlencode(asked)}", **how)
    page.wait_for_function(
        "() => /\\d/.test(document.querySelector('.oa-ev-count')?.textContent || '')"
    )
    if four:
        page.click(".oa-ev-dates")
        page.locator(".oa-ev-dates-menu .oa-choice", has_text="The last four quarters").click()
    landed(page)
    return page


def landed(page: Any) -> None:
    """Every answer of the section in, and the Cases count with it."""
    page.wait_for_function(
        "() => document.querySelector('.oa-bd-line[data-field=\"seriousness\"] .skeleton') === null"
        " && !document.querySelector('.oa-bd[data-state=\"loading\"]')"
        " && !document.querySelector('.oa-ev-count .skeleton')"
    )
    settle(page)


def question(page: Any, without: str = "") -> list[tuple[str, str]]:
    """The question the event asks now, as the event's own context says it."""
    got = page.evaluate(
        """(without) => { const c = window.ev.context();
        const out = new URLSearchParams(c.query({}, { without }));
        for (const [k, v] of Object.entries(c.before)) if (v) out.set(k, v);
        return out.toString(); }""",
        without,
    )
    return parse_qsl(got)


def answer(base: str, path: str, asked: list[tuple[str, str]]) -> Any:
    got = httpx.get(f"{base}{path}", params=asked)
    assert got.status_code == 200, got.text
    return got.json()


def breakdowns(base: str, page: Any, without: str = "") -> dict[str, dict[str, Any]]:
    got = answer(base, "/api/breakdowns", [*question(page, without), ("reaction", EVENT)])
    return {line["field"]: line for line in got["lines"]}


def group_cases(base: str, page: Any, **more: Any) -> int:
    window = [(k, v) for k, v in question(page) if not k.startswith("before_")]
    asked = window + [(k, v) for k, vs in more.items() for v in vs] + [("reaction", EVENT)]
    return answer(base, "/api/events/group", asked)["cases"]


# What the section shows, read as a person reads it.
SHOWN = """() => {
  const text = (el) => el?.textContent.replace(/\\s+/g, ' ').trim();
  return {
    groups: [...document.querySelectorAll('.oa-bd-group')].map((g) => ({
      title: text(g.querySelector('.oa-bd-gtitle')), sub: text(g.querySelector('.oa-bd-gsub')),
      heads: [...g.querySelectorAll('.oa-bd-gh')].map(text),
      lines: [...g.querySelectorAll('.oa-bd-line')].map((l) => ({
        field: l.dataset.field, name: text(l.querySelector('.oa-bd-name')),
        value: text(l.querySelector('.oa-bd-vname')), nums: text(l.querySelector('.oa-bd-nums')),
        change: text(l.querySelector('.oa-bd-chg')), given: text(l.querySelector('.oa-bd-given')),
        tip: l.dataset.tip, presses: l.dataset.act === 'bd-line',
        hot: !!l.querySelector('[data-hot="true"]') })) })),
    chips: [...document.querySelectorAll('.oa-ev-line .oa-strip-edit')].map((c) =>
      `${text(c.querySelector('.oa-strip-name'))} ${text(c.querySelector('.oa-strip-value'))}`),
    count: text(document.querySelector('.oa-ev-count')),
    tile: text(document.querySelector('.oa-ov-tile .oa-ov-v')),
  };
}"""
LIST = """() => {
  const text = (el) => el?.textContent.replace(/\\s+/g, ' ').trim();
  return { rows: [...document.querySelectorAll('.oa-bd-menu .oa-choice')].map((b) => ({
      words: b.querySelector('.menu-choice-words').firstChild.textContent.trim(),
      note: text(b.querySelector('.oa-choice-note')),
      n: +text(b.querySelector('.choice-count')).replace(/,/g, ''),
      on: b.getAttribute('aria-checked') === 'true',
      off: b.getAttribute('aria-disabled') === 'true' })),
    foot: text(document.querySelector('.oa-bd-menu .oa-bd-foot .oa-link')),
    name: text(document.querySelector('.oa-bd-menu .menu-heading')) };
}"""


FILTERS = (
    """() => Object.fromEntries(window.ev.context().filters.map((f) => [f.field, f.values]))"""
)


def lines_of(page: Any) -> dict[str, dict[str, Any]]:
    return {x["field"]: x for g in page.evaluate(SHOWN)["groups"] for x in g["lines"]}


def press(page: Any, field: str) -> None:
    page.click(f'.oa-bd-line[data-field="{field}"]')
    page.wait_for_selector(".oa-bd-menu:popover-open")
    page.wait_for_function("() => !document.querySelector('.oa-bd-menu .skeleton')")
    landed(page)


def tick(page: Any, words: str) -> None:
    page.locator(BOXES, has_text=words).first.click()
    landed(page)


def expected(line: dict[str, Any]) -> dict[str, int]:
    """A line's list as /api/breakdowns gives it: each value's window cases by its filter's value,
    the onset in its bands, the reports giving no value last."""
    rows = line["bands"] if line["field"] == "onset" else line["values"]
    got = {str(v["value"]): v["window"]["cases"] for v in rows if v["value"] != "serious"}
    if line["window"]["given_share"] is not None and "_none" not in got:
        missing = line["window"]["cases"] - line["window"]["given"]
        if missing or line["before"]["cases"] - line["before"]["given"]:
            got["_none"] = missing
    return got


def test_three_groups_under_the_chart_each_line_as_the_answer_gives_it(page_at, base):
    page = opened(page_at, base)
    got = page.evaluate(SHOWN)
    assert {g["title"]: g["sub"] for g in got["groups"]} == GROUPS
    assert all(g["heads"] == ["Change", "Given in"] for g in got["groups"])
    # the section is under the chart and the tiles
    below = page.evaluate(
        "() => document.querySelector('.oa-bd').getBoundingClientRect().top"
        " >= document.querySelector('.oa-ov-top').getBoundingClientRect().bottom"
    )
    assert below
    lines = breakdowns(base, page)
    shown = lines_of(page)
    assert list(shown) == list(lines)
    for field, line in lines.items():
        assert shown[field]["name"] == line["name"]
        if field in ("duplicates",) or line["shown"] is None:
            continue
        s = line["shown"]
        given = line["window"]["given_share"]
        assert shown[field]["given"] == ("–" if given is None else f"{round(100 * given)}%")
        if s["change"] is not None:
            assert shown[field]["change"].endswith(str(int(abs(s["change"]) + 0.5))), field
            assert shown[field]["change"][0] == ("▲" if s["change"] >= 0 else "▼")
        if s["pick"] != "median_days" and s["window"]["share"] is not None:
            share = s["window"]["share"]
            ends = "under 1%" if 0 < share < 0.01 else f"{round(100 * share)}%"
            assert shown[field]["nums"].endswith(ends), (field, shown[field], s)


def test_a_press_filters_by_the_lines_value_and_lists_every_value_with_its_counts(page_at, base):
    """Preview's way: the press puts the value the line shows on the line above, as its filter,
    so the list shows that box ticked and Show all; the other boxes tick from there."""
    page = opened(page_at, base)
    before = breakdowns(base, page)["seriousness"]
    assert before["shown"]["value"] == "DE"
    press(page, "seriousness")
    got = page.evaluate(SHOWN)
    assert "Seriousness Death" in got["chips"]
    # the counts narrow to the filter, as the published question counts it
    assert got["count"] == str(group_cases(base, page))
    assert group_cases(base, page) == group_cases(base, page, outcome=["DE"])
    menu = page.evaluate(LIST)
    assert menu["name"] == "Seriousness" and menu["foot"] == "Show all"
    assert {r["words"]: r["on"] for r in menu["rows"]}["Death"] is True
    assert sum(r["on"] for r in menu["rows"]) == 1
    # the list keeps its counts: those under the event's other filters, the line's own left out
    want = expected(breakdowns(base, page, "outcome")["seriousness"])
    assert sorted(r["n"] for r in menu["rows"] if r["n"]) == sorted(n for n in want.values() if n)
    assert expected(before) == want
    # every criterion stays listed, with no case or not, in the order of the shot
    assert [r["words"] for r in menu["rows"]][:3] == list(OUTCOME.values())
    # a second press only closes the list: the filter stays, once
    page.click('.oa-bd-line[data-field="seriousness"]')
    assert page.locator(".oa-bd-menu").count() == 0
    settle(page)
    assert page.evaluate(SHOWN)["chips"] == ["Seriousness Death"]
    press(page, "seriousness")
    assert page.evaluate(SHOWN)["chips"] == ["Seriousness Death"]
    assert page.evaluate(LIST)["foot"] == "Show all"


def test_a_press_on_a_value_with_cases_narrows_every_count_to_it(page_at, base):
    page = opened(page_at, base)
    every = int(page.evaluate(SHOWN)["count"])
    shown = breakdowns(base, page)["sex"]["shown"]
    press(page, "sex")
    got = page.evaluate(SHOWN)
    assert got["chips"] == [f"Sex {dict(F='Female', M='Male')[shown['value']]}"]
    assert 0 < int(got["count"]) < every
    assert got["count"] == str(shown["window"]["cases"]) == got["tile"]
    assert got["count"] == str(group_cases(base, page))


def test_every_lines_list_agrees_with_the_answer_and_each_box_with_its_filter(page_at, base):
    """Each line's list against /api/breakdowns, each value's count against the cases its filter
    keeps, as the list's own tick picks them: the filter, the line and the count one reading."""
    page = opened(page_at, base)
    lines = breakdowns(base, page)
    pressed = 0
    for field, line in lines.items():
        if (
            field == "duplicates"
            or field not in lines_of(page)
            or not lines_of(page)[field]["presses"]
        ):
            continue
        press(page, field)
        pressed += 1
        menu = page.evaluate(LIST)
        want = expected(line)
        assert sorted(r["n"] for r in menu["rows"] if r["n"]) == sorted(
            n for n in want.values() if n
        ), field
        name = line["filter"]
        if name:
            for value, n in want.items():
                window = [(k, v) for k, v in question(page, name) if not k.startswith("before_")]
                got = answer(
                    base, "/api/events/group", [*window, (name, value), ("reaction", EVENT)]
                )
                assert got["cases"] == n, (field, value)
        page.keyboard.press("Escape")
        settle(page)
        page.evaluate(
            "() => { for (const f of window.ev.context().filters) "
            "window.ev.setFilter(f.field, null); }"
        )
        landed(page)
    assert pressed >= 10


def test_a_tick_narrows_the_events_other_panes(page_at, base):
    """A value unticked keeps the others, and every pane counts under the filter: the Cases count,
    the tiles, the other lines and a pane of the host's, which is told it."""
    page = opened(page_at, base)
    page.click('.oa-ev-tab[data-v="compared"]')
    assert page.locator(".demo-pane").is_visible()
    page.click('.oa-ev-tab[data-v="overview"]')
    before = page.evaluate(SHOWN)
    told = page.evaluate("() => window.told.length")
    press(page, "sex")
    page.click(FOOT)  # Show all: every box ticked, no filter
    landed(page)
    menu = page.evaluate(LIST)
    assert all(r["on"] for r in menu["rows"])
    # a box unticked keeps the others; a value with cases, so the counts must narrow
    dropped = next(r for r in menu["rows"] if r["n"] and r["words"] != "Not given")
    tick(page, dropped["words"])
    menu = page.evaluate(LIST)
    assert [r["words"] for r in menu["rows"] if not r["on"]] == [dropped["words"]]
    assert menu["foot"] == "Show all"
    page.keyboard.press("Escape")
    landed(page)
    after = page.evaluate(SHOWN)
    assert len(after["chips"]) == 1 and after["chips"][0].startswith("Sex ")
    assert dropped["words"] not in after["chips"][0]
    kept = next(v for k, v in page.evaluate(FILTERS).items() if k == "sex")
    narrowed = group_cases(base, page)
    assert narrowed == int(before["count"]) - dropped["n"]
    assert after["count"] == str(narrowed) and after["tile"] == str(narrowed)
    # every other line counts under it, as the published answer does
    lines = breakdowns(base, page)
    for field, line in lines_of(page).items():
        if (
            field != "duplicates"
            and lines[field]["shown"]
            and lines[field]["window"]["given_share"]
        ):
            assert line["given"] == f"{round(100 * lines[field]['window']['given_share'])}%", field
    assert lines["age"]["window"]["cases"] == narrowed
    # the host's pane was told the filter
    last = page.evaluate("() => window.told.at(-1)")
    assert page.evaluate("() => window.told.length") > told
    assert all(f"sex={v}" in last for v in kept)


def test_deselect_all_shows_no_case_and_show_all_every_case(page_at, base):
    page = opened(page_at, base)
    press(page, "age")
    page.click(FOOT)  # Show all: the press's own filter goes, every box ticked
    landed(page)
    menu = page.evaluate(LIST)
    assert menu["foot"] == "Deselect all" and all(r["on"] for r in menu["rows"])
    assert page.evaluate(SHOWN)["chips"] == []
    every = page.evaluate(SHOWN)["count"]
    page.click(FOOT)  # Deselect all: nothing ticked, no case shows, and the list stays
    landed(page)
    menu = page.evaluate(LIST)
    assert menu["foot"] == "Show all" and not any(r["on"] for r in menu["rows"])
    assert all(r["n"] >= 0 for r in menu["rows"]) and sum(r["n"] for r in menu["rows"]) > 0
    got = page.evaluate(SHOWN)
    assert got["count"] == "0" and got["chips"] == ["Age None"]
    shown = lines_of(page)
    assert {x["value"] for x in shown.values()} == {None}
    assert shown["age"]["presses"] and not shown["sex"]["presses"]
    # from nothing ticked, a box is the only one
    first = menu["rows"][0]["words"]
    tick(page, first)
    menu = page.evaluate(LIST)
    assert [r["words"] for r in menu["rows"] if r["on"]] == [first]
    page.click(FOOT)
    landed(page)
    assert page.evaluate(SHOWN)["count"] == every


def test_a_line_with_no_value_of_its_filter_filters_nothing_as_it_opens(page_at, base):
    page = opened(page_at, base)
    press(page, "onset")  # the median is no value of the onset filter: its bands are
    assert page.evaluate(SHOWN)["chips"] == []
    menu = page.evaluate(LIST)
    assert menu["foot"] == "Deselect all" and all(r["on"] for r in menu["rows"])
    assert [r["words"] for r in menu["rows"]][:2] == ["Same day", "2 to 7 days"]
    page.keyboard.press("Escape")
    press(page, "key_details")  # no filter at all: its values to read, nothing to change
    menu = page.evaluate(LIST)
    assert menu["foot"] is None and all(r["off"] for r in menu["rows"])
    page.locator(BOXES).first.click(force=True)
    settle(page)
    assert page.evaluate(SHOWN)["chips"] == []


def test_keys_open_a_line_and_tips_rest_while_its_list_is_open(page_at, base):
    page = opened(page_at, base)
    assert lines_of(page)["sex"]["tip"].startswith("Sex: ")
    assert lines_of(page)["sex"]["tip"].endswith("Press to filter by it and list every value.")
    page.focus('.oa-bd-line[data-field="sex"]')
    page.keyboard.press("Enter")
    page.wait_for_selector(".oa-bd-menu:popover-open")
    landed(page)
    assert lines_of(page)["age"]["tip"] is None
    assert page.get_attribute('.oa-bd-line[data-field="sex"]', "aria-expanded") == "true"
    page.keyboard.press("Escape")
    settle(page)
    assert page.locator(".oa-bd-menu").count() == 0
    assert lines_of(page)["age"]["tip"].startswith("Age: ")


def test_a_host_alone_turns_a_line_the_warning_color(page_at, base):
    page = opened(page_at, base)
    assert not any(x["hot"] for x in lines_of(page).values())
    page = opened(page_at, base, screens=[{"breakdowns": {"points": 1}}])
    lines = answer(base, "/api/breakdowns", [*question(page), ("reaction", EVENT), ("points", "1")])
    want = {x["field"] for x in lines["lines"] if x["alarm"] and x["field"] != "duplicates"}
    assert {f for f, x in lines_of(page).items() if x["hot"]} == want


# The new filters of + Add a filter: a value from its own list, and what the event then counts.
NEW = [
    ("Other drugs", "other_drug"),
    ("Dose", "dose"),
    ("Route", "route"),
    ("Dose form", "dose_form"),
    ("Taken for", "indication"),
    ("Lot", "lot"),
    ("Onset", "onset"),
    ("Dechallenge", "dechal"),
    ("Rechallenge", "rechal"),
    ("Report type", "report_type"),
    ("Other reactions", "other_reaction"),
]


@pytest.mark.parametrize(("words", "name"), NEW)
def test_add_a_filter_lists_each_new_field_and_narrows_by_it(page_at, base, words, name):
    page = opened(page_at, base)
    every = int(page.evaluate(SHOWN)["count"])
    page.click(".oa-ev-addfilter")
    page.locator(".oa-ev-af-menu .oa-filter-row", has_text=words).first.click()
    list_ = ".oa-ev-af-menu .oa-ev-af-list"
    page.wait_for_function(f"() => !document.querySelector('{list_} .skeleton')")
    rows = page.evaluate(
        f"""() => [...document.querySelectorAll('{list_} .oa-choice')].map((b) => ({{
          v: b.dataset.v, words: b.querySelector('.menu-choice-words').textContent.trim(),
          n: +b.querySelector('.choice-count').textContent.replace(/,/g, ''),
          on: b.getAttribute('aria-checked') === 'true' }}))"""
    )
    assert rows and all(r["on"] for r in rows), words
    assert page.locator(".oa-ev-af-menu .oa-ev-af-foot .oa-link").text_content() == "Deselect all"
    # each value's count is the cases its filter keeps
    for r in rows:
        assert group_cases(base, page, **{name: [r["v"]]}) == r["n"], (words, r)
    # Deselect all, then one ticked: the event counts it, and the line says it in words
    page.click(".oa-ev-af-menu .oa-ev-af-foot .oa-link")
    pick = max(rows, key=lambda r: r["n"])
    page.locator(f'{list_} .oa-choice[data-v="{pick["v"]}"]').click()
    page.keyboard.press("Escape")
    landed(page)
    got = page.evaluate(SHOWN)
    # the only value there is, ticked: every box, so no filter
    assert got["chips"] == ([f"{words} {pick['words']}"] if len(rows) > 1 else [])
    assert got["count"] == str(pick["n"] if len(rows) > 1 else every)


def test_a_line_not_available_says_so_and_opens_nothing(page_at, base):
    page = opened(page_at, base)
    line = lines_of(page).get("pregnancy")
    assert line and line["presses"] is False
    assert "not available" in line["tip"]


# Where the section's parts stand, and what spills.
PLACES = """() => {
  const box = (el) => { const r = el.getBoundingClientRect();
    return [r.left, r.top, r.right, r.bottom].map(Math.round); };
  return { section: box(document.querySelector('.oa-bd')),
    groups: [...document.querySelectorAll('.oa-bd-group')].map(box),
    names: [...document.querySelectorAll('.oa-bd-name')].map((n) => {
      const at = document.querySelector('.oa-bd').getBoundingClientRect();
      const r = n.getBoundingClientRect();
      return [r.left - at.left, r.top - at.top].map(Math.round); }),
    spill: [...document.querySelectorAll('.oa-bd-line')].filter((l) => {
      const within = l.getBoundingClientRect().right + 1;
      return [...l.children].some((c) => c.getBoundingClientRect().right > within);
    }).map((l) => l.dataset.field),
    page: document.documentElement.scrollWidth - innerWidth };
}"""


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_nothing_spills_or_moves_as_the_answers_arrive(page_at, base, width, theme):
    asked = urlencode({"drug": DRUG, "opened": KEY, "later": 1})
    page = page_at(f"{base}{PAGE}?{asked}", width=width, theme=theme)
    page.evaluate("() => { window.hold(); window.drawTable(); }")
    page.wait_for_selector(".oa-bd .skeleton")
    page.wait_for_function(
        "() => /\\d/.test(document.querySelector('.oa-ev-count')?.textContent || '')"
    )
    waiting = page.evaluate(PLACES)
    page.evaluate("() => window.letGo()")
    landed(page)
    drawn = page.evaluate(PLACES)
    assert waiting["groups"] == drawn["groups"], (waiting["groups"], drawn["groups"])
    assert waiting["names"] == drawn["names"]
    assert drawn["page"] <= 0 and drawn["spill"] == [], drawn
    # a press changes what the lines say, never where they stand
    press(page, "sex")
    moved = page.evaluate(PLACES)
    assert moved["names"] == drawn["names"] and moved["page"] <= 0
    menu = page.locator(".oa-bd-menu").bounding_box()
    assert menu["x"] >= 0 and menu["x"] + menu["width"] <= width + 1
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"list-{width}-{theme}.png"))
        page.keyboard.press("Escape")
        settle(page)
        page.locator(".oa-bd").screenshot(path=str(Path(SHOTS) / f"groups-{width}-{theme}.png"))


def test_a_free_page_draws_no_breakdowns(page_at, base):
    page = page_at(f"{base}/")
    assert page.locator(".oa-bd").count() == 0


def test_with_a_wider_font_in_inters_place_a_list_leaves_its_line_to_press(page_at, base):
    page = opened(page_at, base)
    page.add_style_tag(content=':root { --font-sans: "DejaVu Sans", Verdana, sans-serif; }')
    settle(page)
    press(page, "seriousness")
    line = page.locator('.oa-bd-line[data-field="seriousness"]').bounding_box()
    menu = page.locator(".oa-bd-menu").bounding_box()
    assert menu["y"] >= line["y"] + line["height"] or menu["y"] + menu["height"] <= line["y"]
    page.click('.oa-bd-line[data-field="seriousness"]')  # a second press closes it
    assert page.locator(".oa-bd-menu").count() == 0
