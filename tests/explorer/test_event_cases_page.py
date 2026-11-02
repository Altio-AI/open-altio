"""An opened event's Cases tab (ui/event-cases.js, event-cols.js, event-heads.js, event-dups.js)
and a case read in its place (ui/event-case.js) in a browser, in an event a host's page module opens
under its row, at 320, 768, 1024 and 1440 pixels, light and dark: the columns ticked in Columns
show, and come back on a reload; a head's menu sorts the cases and narrows them, each value with its
count, its pick the event's own filter; a case's duplicate opens under it; a case opens in place,
the address names it, and ‹ Cases or Escape bring back the same page with its row marked; a drug's
time to onset on its first therapy row only; nothing
moves as the rows load; and nothing scrolls the page sideways.

Run over `breakdown_release` (open_altio.testing.fakefda.BREAKDOWN_STORY: valsartan and Headache,
with two copies of one case in 2019q1). What a page shows is checked against the release's own
answers, asked apart from the page: the cases by sex from the counted question (/api/count)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qsl, urlencode

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from open_altio.explorer.access import LocalAccess
from open_altio.explorer.app import create_app, host
from open_altio.explorer.pages import index
from open_altio.testing.browser import open_page, served, settle

WIDTHS = [320, 768, 1024, 1440]
THEMES = ["light", "dark"]
MODULE = "/cases-host/page.js"
PAGE = "/cases-demo"
DRUG, EVENT = "valsartan", "Headache"
KEY = f"{DRUG}|{EVENT.lower()}"
# the columns the tab opens with, Case first
SHOWN = [
    "Case", "Received", "Age", "Sex", "Suspect drugs", "Role", "Dose", "Taken for", "Onset",
    "Dechallenge", "Reporter", "Seriousness",
]  # fmt: skip

# A host's page: valsartan's events table, Headache's row open, its event on its Cases tab.
HOST_JS = """
import { eventsTable, extend, framed, openedEvent } from '/ui/app.js';

const asked = new URLSearchParams(location.search);
const PAGE = '<main class="product-page">'
  + '<section class="oa-chart oa-chart-wide" id="demo"></section></main>';
extend({
  routes: [(parts) => (parts[0] === 'cases-demo' ? { page: 'cases-demo' } : null)],
  addresses: [(parts) => parts[0] === 'cases-demo'],
  pages: {
    'cases-demo': (route, app) => {
      app.innerHTML = framed(PAGE, 'cases-demo');
      const drug = asked.get('drug');
      eventsTable(app.querySelector('#demo'), {
        drug, open: () => {},
        opened: {
          key: asked.get('opened'),
          draw: (box, row) => { window.ev = openedEvent(box, { drug, row, tab: 'cases' }); },
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
def cases_host(breakdown_release) -> Iterator[str]:
    with served(hosted(breakdown_release)) as base:
        yield base


@pytest.fixture
def bweb(explorer_app, breakdown_release) -> TestClient:
    return TestClient(explorer_app(breakdown_release))


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


def at(base: str, **asked: str) -> str:
    return f"{base}{PAGE}?{urlencode({'drug': DRUG, 'opened': KEY, **asked})}"


# What the tab shows: its heads, each row's cells, the count, the pager's range, the line's words,
# the address, and whether anything scrolls the page sideways
SEEN = """() => {
  const pane = document.querySelector('.oa-ev-pane[data-pane="cases"]');
  const words = (el) => (el ? el.textContent.replace(/\\s+/g, ' ').trim() : null);
  const heads = [...(pane?.querySelectorAll('.oa-ec-table thead th') || [])];
  return {
    heads: heads.map((h) => words(h)),
    rows: [...(pane?.querySelectorAll('tr.oa-ec-row') || [])].map((r) => [...r.cells].map(words)),
    keys: [...(pane?.querySelectorAll('tr.oa-ec-row') || [])]
      .map((r) => r.querySelector('.case-key').textContent),
    count: words(pane?.querySelector('.oa-ec-count')),
    range: words(pane?.querySelector('.oa-ec-prange')),
    none: words(pane?.querySelector('.oa-ec-none')),
    line: words(document.querySelector('.oa-ev-line')),
    shown: pane ? !pane.hidden : false,
    address: location.search,
    page: document.documentElement.scrollWidth - innerWidth,
  };
}"""


def seen(page: Any) -> dict[str, Any]:
    return page.evaluate(SEEN)


def ready(page: Any) -> dict[str, Any]:
    """The tab once its count and its rows are in."""
    page.wait_for_function(
        "() => { const p = document.querySelector('.oa-ev-pane[data-pane=\"cases\"]');"
        " return p && /\\d/.test(p.querySelector('.oa-ec-count')?.textContent || '')"
        " && !p.querySelector('.oa-ec-cases[data-state]') && !p.querySelector('.oa-ec-skeleton'); }"
    )
    settle(page)
    return seen(page)


def all_dates(page: Any) -> dict[str, Any]:
    """The window widened to every day, so the copies of 2019q1 are in it."""
    page.click(".oa-ev-dates")
    page.locator(".oa-ev-dates-menu .oa-choice", has_text="All dates").click()
    settle(page)
    return ready(page)


def column(got: dict[str, Any], head: str) -> list[str]:
    i = got["heads"].index(head)
    return [r[i] for r in got["rows"]]


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_columns_ticked_show_and_come_back_on_a_reload(page_at, cases_host, width, theme):
    page = page_at(at(cases_host), width=width, theme=theme)
    got = ready(page)
    assert got["heads"] == SHOWN, got
    assert got["rows"] and got["page"] <= 0, got
    assert got["count"].endswith("cases in the window"), got
    # the tab's count and the opened event's, each asked its own way, agree
    assert got["count"].split()[0] == page.locator(".oa-ev-count").inner_text().strip(), got
    page.click(".oa-ec-columns")
    menu = page.locator(".menu.oa-ec-colmenu")
    groups = menu.locator(".oa-ec-colgroup > .menu-heading").all_inner_texts()
    assert [g.strip().lower() for g in groups] == ["dates", "patient", "drugs", "course", "report"]
    menu.locator(".oa-choice", has_text="Event date").click()
    menu.locator(".oa-choice", has_text="Dose").first.click()
    page.keyboard.press("Escape")
    got = ready(page)
    assert "Event date" in got["heads"] and "Dose" not in got["heads"], got
    assert got["heads"].index("Event date") == got["heads"].index("Received") + 1
    assert got["page"] <= 0, got
    page.reload()
    settle(page)
    got = ready(page)
    assert "Event date" in got["heads"] and "Dose" not in got["heads"], got


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_a_head_menu_sorts_and_narrows_with_counts(page_at, cases_host, bweb, width, theme):
    page = page_at(at(cases_host), width=width, theme=theme)
    got = all_dates(page)
    total = int(got["count"].split()[0])
    # Age sorts oldest first, then youngest first, a case with no age last both ways
    page.click('.oa-ec-head[data-v="age"]')
    page.click('.oa-ec-hmenu .oa-choice[data-v="age"]')
    got = ready(page)
    ages = [int(a) if a.isdigit() else None for a in column(got, "Age")]
    given = [a for a in ages if a is not None]
    assert given == sorted(given, reverse=True) and ages[: len(given)] == given, ages
    assert len(given) > 1
    # each value once, Not given last
    shown = page.locator(".oa-ec-hmenu .oa-ec-hlist .menu-choice-words").all_inner_texts()
    assert len(shown) == len(set(shown)) and shown[-1] == "Not given", shown
    page.keyboard.press("Escape")
    # Sex: each value with its count among the event's cases in the window, every box ticked
    page.click('.oa-ec-head[data-v="sex"]')
    menu = page.locator(".menu.oa-ec-hmenu")
    menu.locator(".oa-choice").first.wait_for()
    values = menu.locator(".oa-ec-hlist .oa-choice").evaluate_all(
        "(els) => els.map((e) => [e.querySelector('.menu-choice-words').textContent.trim(),"
        " +e.querySelector('.choice-count').textContent, e.getAttribute('aria-checked')])"
    )
    asked = {"product": DRUG, "pt": EVENT, "by": "sex"}
    counted = {
        v or "_none": n for v, n, _ in bweb.get(f"/api/count?{urlencode(asked)}").json()["counts"]
    }
    words = {"Female": "F", "Male": "M", "Not given": "_none"}
    assert {words[w]: n for w, n, _ in values} == {k: counted.get(k, 0) for k in words.values()}
    assert all(on == "true" for _, _, on in values) and sum(n for _, n, _ in values) == total
    assert menu.locator(".oa-et-menu-line .oa-link").inner_text() == "Deselect all"
    # unticking Male narrows the event: the line names it and the count follows
    menu.locator('.oa-choice[data-v="M"]').click()
    got = ready(page)
    assert "Sex" in got["line"] and set(column(got, "Sex")) <= {"F", "Not given"}, got
    assert int(got["count"].split()[0]) == total - counted.get("M", 0), got
    # Deselect all: no case shows; Show all: every case again
    page.locator(".menu.oa-ec-hmenu .oa-et-menu-line .oa-link").click()  # Show all
    page.locator(".menu.oa-ec-hmenu .oa-et-menu-line .oa-link").click()  # Deselect all
    got = ready(page)
    assert got["none"] == "No cases in the window match these filters.", got
    assert got["count"].startswith("0 of"), got
    page.locator(".menu.oa-ec-hmenu .oa-et-menu-line .oa-link").click()
    got = ready(page)
    assert int(got["count"].split()[0]) == total and "Sex" not in got["line"], got


ASKED = "() => { const c = ev.context(); return [c.query(), c.before]; }"
VALUES = """(els) => els.map((e) => [e.dataset.v,
  e.querySelector('.menu-choice-words').textContent.trim(),
  +e.querySelector('.choice-count').textContent, e.getAttribute('aria-checked')])"""


def show_column(page: Any, words: str) -> None:
    page.click(".oa-ec-columns")
    page.locator(".menu.oa-ec-colmenu .oa-choice", has_text=words).first.click()
    page.keyboard.press("Escape")
    ready(page)


def head_values(page: Any, head: str) -> list[list[Any]]:
    page.click(f'.oa-ec-head[data-v="{head}"]')
    menu = page.locator(".menu.oa-ec-hmenu")
    menu.locator(".oa-ec-hlist .oa-choice").first.wait_for()
    return menu.locator(".oa-ec-hlist .oa-choice").evaluate_all(VALUES)


def line_counts(bweb: TestClient, page: Any, head: str) -> dict[str, int]:
    """What the head's values hold, asked apart from the page: /api/count for Route, /api/breakdowns
    (the line's values or bands) for the others."""
    query, before = page.evaluate(ASKED)
    pairs = [(k, v) for k, v in parse_qsl(query) if v] + [(k, v) for k, v in before.items() if v]
    if head == "route":
        got = bweb.get(f"/api/count?{urlencode([*pairs, ('pt', EVENT), ('by', 'route')])}").json()
        return {v or "_none": n for v, n, *_ in got["counts"]}
    got = bweb.get(f"/api/breakdowns?{urlencode([*pairs, ('reaction', EVENT)])}").json()
    line = next(x for x in got["lines"] if x["field"] == head)
    rows = line["bands"] if head == "onset" else line["values"]
    counts = {str(r["value"]): r["window"]["cases"] for r in rows}
    window = line["window"]  # the cases that do not give the field are the line's rest
    return {**counts, "_none": window["cases"] - window["given"]}


@pytest.mark.parametrize("head", ["onset", "route", "report_type"])
@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_a_drug_or_report_head_filters_with_counts(page_at, cases_host, bweb, width, theme, head):
    page = page_at(at(cases_host), width=width, theme=theme)
    got = all_dates(page)
    if head not in {h.lower().replace(" ", "_") for h in got["heads"]}:
        show_column(page, {"route": "Route", "report_type": "Report type"}[head])
    total = int(seen(page)["count"].split()[0])
    values = head_values(page, head)
    words = [w for _, w, _, _ in values]
    assert len(words) == len(set(words)) and all(on == "true" for *_, on in values), values
    keys = [v[0] for v in values]
    assert keys and "_none" not in keys[:-1], keys  # Not given, where there is one, last
    # each value's count is what the question asked apart gives
    asked = line_counts(bweb, page, head)
    for v, _, n, _ in values:
        assert n == asked.get(v, 0), (head, v, n, asked)
    # unticking a value that holds cases narrows the tab's count by exactly its cases
    menu = page.locator(".menu.oa-ec-hmenu")
    one = next(v for v in values if v[2] > 0 and v[0] != "_none")
    menu.locator(f'.oa-choice[data-v="{one[0]}"]').click()
    got = ready(page)
    words_of = {"route": "Route", "onset": "Onset", "report_type": "Report type"}[head]
    assert words_of in got["line"], got
    assert int(got["count"].split()[0]) == total - one[2], (got, one)
    assert got["page"] <= 0, got
    # ticked again: every case, the line without it
    menu.locator(f'.oa-choice[data-v="{one[0]}"]').click()
    got = ready(page)
    assert int(got["count"].split()[0]) == total and words_of not in got["line"], got


def test_a_long_head_list_scrolls_inside_its_menu_at_320(page_at, cases_host):
    page = page_at(at(cases_host), width=320)
    all_dates(page)
    show_column(page, "Lot")
    page.click('.oa-ec-head[data-v="lot"]')
    page.locator(".menu.oa-ec-hmenu .oa-ec-hlist .oa-choice").first.wait_for()
    # a list grown past the menu's room (the release has few lots) scrolls inside it, not the page
    shot = page.evaluate(
        """() => { const l = document.querySelector('.oa-ec-hmenu .oa-ec-hlist');
        l.insertAdjacentHTML('beforeend', '<p style="height:900px">x</p>');
        const m = l.closest('.menu'), r = m.getBoundingClientRect();
        return { room: l.clientHeight < l.scrollHeight, scrolls: getComputedStyle(l).overflowY,
          inside: r.right <= innerWidth && r.left >= 0,
          page: document.documentElement.scrollWidth - innerWidth }; }"""
    )
    assert shot["room"] and shot["scrolls"] == "auto" and shot["inside"] and shot["page"] <= 0, shot


@pytest.mark.parametrize("width", [320, 1440])
def test_a_duplicate_opens_under_its_case(page_at, cases_host, width):
    page = page_at(at(cases_host), width=width)
    all_dates(page)
    button = page.locator(".oa-ec-dupbtn").first
    assert button.inner_text().strip() == "1 duplicate"
    row = button.locator("xpath=ancestor::tr[1]")
    button.scroll_into_view_if_needed()
    settle(page)
    above = row.bounding_box()["y"]
    button.click()
    page.wait_for_selector(".oa-ec-duprow .oa-ec-dupsay")
    settle(page)
    said = page.locator(".oa-ec-duprow .oa-ec-dupsay").inner_text()
    assert said.startswith("Likely the same patient:") and "a day apart" in said, said
    assert row.bounding_box()["y"] == above
    assert button.get_attribute("aria-expanded") == "true"
    button.click()
    assert page.locator(".oa-ec-duprow").count() == 0


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_a_case_opens_in_place_and_cases_returns_to_the_same_page(
    page_at, cases_host, width, theme
):
    page = page_at(at(cases_host), width=width, theme=theme, kept={"event.casesPerPage": 4})
    all_dates(page)
    page.click('.oa-ec-pnum[aria-label="Page 2"]')
    got = ready(page)
    assert got["range"].startswith("Cases 5 to 8"), got
    key = got["keys"][1]
    page.click(f'tr.oa-ec-row[data-key$=":{key}"] td:nth-child(3)')
    page.wait_for_selector(".oa-cv-case")
    page.wait_for_selector(".oa-cv-pair")
    settle(page)
    assert page.locator(".oa-cv-case").inner_text() == f"Case {key}"
    assert not seen(page)["shown"] and f"case={key}" in seen(page)["address"]
    for part in ("The patient", "About the report", "Reactions", "The drugs"):
        assert page.locator(".oa-cv-gtitle", has_text=part).count() == 1, part
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    page.click(".oa-cv-back")
    settle(page)
    got = seen(page)
    assert (
        got["shown"] and got["range"].startswith("Cases 5 to 8") and "case=" not in got["address"]
    )
    marked = page.locator('tr.oa-ec-row[aria-current="true"]')
    assert marked.locator(".case-key").inner_text() == key
    assert page.evaluate("document.activeElement.matches('tr.oa-ec-row[aria-current]')")
    # Escape goes back too
    page.keyboard.press("Enter")
    page.wait_for_selector(".oa-cv-case")
    page.keyboard.press("Escape")
    settle(page)
    assert seen(page)["shown"] and "case=" not in seen(page)["address"]


def test_a_copied_link_to_a_case_opens_it_in_place(page_at, cases_host, bweb):
    key = bweb.get(f"/api/cases?product={DRUG}&pt={EVENT}").json()["cases"][0]["case_key_T"]
    page = page_at(at(cases_host, case=key))
    page.wait_for_selector(".oa-cv-pair")
    assert page.locator(".oa-cv-case").inner_text() == f"Case {key}"


def test_a_case_closed_stays_closed_as_the_event_changes(page_at, cases_host):
    page = page_at(at(cases_host))
    asked: list[str] = []
    page.on("request", lambda r: asked.append(r.url) if "/api/case/" in r.url else None)
    key = all_dates(page)["keys"][0]
    # ‹ Cases, then a filter changed under the tab
    page.click(f'tr.oa-ec-row[data-key$=":{key}"] td:nth-child(3)')
    page.wait_for_selector(".oa-cv-pair")
    page.click(".oa-cv-back")
    settle(page)
    asked.clear()
    page.click(".oa-ec-dupinc-box")
    settle(page)
    assert [u for u in asked if "/undefined" in u or "/null/" in u] == []
    assert "case=" not in page.evaluate("location.search")
    # another tab pressed from a case: the address names it no more, and Escape stays on that tab
    ready(page)
    page.locator("tr.oa-ec-row td:nth-child(3)").first.click()
    page.wait_for_selector(".oa-cv-pair")
    page.click('.oa-ev-tab[data-v="overview"]')
    settle(page)
    assert "case=" not in page.evaluate("location.search")
    page.keyboard.press("Escape")
    settle(page)
    assert page.locator('.oa-ev-tab[data-v="overview"]').get_attribute("aria-selected") == "true"
    # and the Cases tab pressed from a case shows the table
    page.click('.oa-ev-tab[data-v="cases"]')
    settle(page)
    assert seen(page)["shown"] and "case=" not in seen(page)["address"]


# each therapy row: its cells' words, how many rows each reaches, the tip on its last
THERAPY = """rows => rows.map((r) => ({
  cells: [...r.children].map((c) => c.innerText.trim()),
  spans: [...r.children].map((c) => c.rowSpan),
  tip: r.lastElementChild.querySelector('[data-tip]')?.dataset.tip || '',
}))"""


@pytest.mark.parametrize("width", WIDTHS)
def test_a_drugs_time_to_onset_shows_on_its_first_therapy_row_only(
    page_at, cases_host, bweb, width
):
    # the story's drugs have one therapy row each: this case's answer gains a second for its drug,
    # the way FDA gives a drug stopped and started again
    listed = bweb.get(f"/api/cases?product={DRUG}&pt={EVENT}&detail=columns").json()["cases"]
    case = next(c for c in listed if c["columns_T"]["onset"] is not None)
    key = case["case_key_T"]

    def two_rows(route: Any) -> None:
        got = route.fetch()
        answer = got.json()
        first = answer["ther"][0]
        answer["ther"].insert(1, {**first, "start_dt": "", "start_dt_T": None, "dur_days_T": None})
        route.fulfill(response=got, json=answer)

    page = page_at(at(cases_host), width=width)
    page.route(re.compile(rf"/api/case/\w+/{key}(\?.*)?$"), two_rows)
    page.goto(at(cases_host, case=key))
    page.wait_for_selector(".oa-cv-ther")
    settle(page)
    rows = page.eval_on_selector_all(".oa-cv-ther tbody tr", THERAPY)
    assert rows[0]["cells"][0] == rows[1]["cells"][0], rows
    assert rows[0]["cells"][-1] == f"Day {case['columns_T']['onset']}", rows
    assert "Counted from the first dose of this drug" in rows[0]["tip"], rows
    assert rows[1]["cells"][-1] == "", rows
    assert all(len(r["cells"]) == 5 and set(r["spans"]) == {1} for r in rows), rows


# where the tab's parts stand while its rows are held back, then once they are in
PLACES = """() => {
  const p = document.querySelector('.oa-ev-pane[data-pane="cases"]');
  const y = (sel) => Math.round(p.querySelector(sel).getBoundingClientRect().top);
  return { tools: y('.oa-ec-tools'), heads: y('.oa-ec-table thead'), frame: y('.oa-ec-body'),
    bar: Math.round(document.querySelector('.oa-ev-bar').getBoundingClientRect().top) };
}"""


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_nothing_moves_as_the_rows_load(page_at, cases_host, width, theme):
    held: list[Any] = []
    hold = [True]
    page = page_at(at(cases_host), width=width, theme=theme)
    ready(page)
    page.route("**/api/cases?*", lambda r: held.append(r) if hold[0] else r.continue_())
    # a new window asks for the rows again: the parts stand where they are while they come
    page.click(".oa-ev-dates")
    page.locator(".oa-ev-dates-menu .oa-choice", has_text="All dates").click()
    page.wait_for_function("() => document.querySelector('.oa-ec-cases[data-state=\"loading\"]')")
    before = page.evaluate(PLACES)
    hold[0] = False
    while held:
        held.pop().continue_()
    ready(page)
    assert page.evaluate(PLACES) == before
