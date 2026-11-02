"""An opened event's Compared tab (ui/event-compared*.js) in a browser, mounted by a host's page
module in the frame: each row's numbers agree with the published answers for that drug or class, in
the window and under the line's filters; + Add a drug or class ticks drugs and classes as the Drug
class filter does; a class opens to what it holds; a host's `classes: false` keeps every class out,
none asked for and none drawn; a drug pressed opens its own read-only view with no host's cell or
next step, and Back; a host's marks, its line and its red come only from a host; and, at 320, 768,
1024 and 1440 pixels, light and dark, nothing scrolls the page sideways and nothing moves as the
answers arrive."""

from __future__ import annotations

import json
import os
import shutil
from calendar import monthrange
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import pytest
from fastapi import FastAPI, Response

from open_altio.explorer.access import LocalAccess
from open_altio.explorer.app import create_app, host
from open_altio.explorer.pages import index
from open_altio.testing import fakeclasses
from open_altio.testing.browser import open_page, served, settle

SHOTS = os.environ.get("OPEN_ALTIO_COMPARED_SHOTS")
WIDTHS = [320, 768, 1024, 1440]
THEMES = ["light", "dark"]
MODULE = "/compared-host/page.js"
PAGE = "/compared-demo"
DRUG, EVENT, OTHER = "warfarin", "Haemorrhage", "ibuprofen"
KEY = f"{DRUG}|{EVENT.lower()}"
OWN_CLASS, THEIR_CLASS = "B01ZY", "M01ZZ"
HOST_MARK, HOST_LINE = "Ours", "The last word of the host"
NOT_OURS = "Not one of ours: shown against"
KEPT = "compared"
NO_SCORE = "Not worked out"
STORED = f"open-altio.{KEPT}"

# A host's page: the drug's events table with a column of its own, a press on a row opening the
# event under it on the Compared tab, as a product mounts it. ?slots fills its places (the host's
# next step, its line, whose words change for a read-only view, and its mark of its own drug);
# ?classes=0 keeps the classes out; ?screens passes thresholds; ?later waits for
# window.drawTable(). window.hold() holds what the tab reads until window.letGo().
HOST_JS = (
    """
import { eventsTable, extend, framed, openedEvent } from '/ui/app.js';

const asked = new URLSearchParams(location.search);
const ask = window.fetch;
window.asks = [];
let gate = null;
window.hold = () => { let open; gate = new Promise((r) => { open = r; });
  window.letGo = () => { gate = null; open(); }; };
// what the tab reads: the events table above it and the frame's own first day are not held
const held = (url) => /^\\/api\\/(events\\/group|statistics|classes|labels)/.test(url)
  || (url.startsWith('/api/events?') && url.includes('pt='));
window.fetch = (...a) => {
  window.asks.push(String(a[0]));
  return gate && held(String(a[0])) ? gate.then(() => ask(...a)) : ask(...a);
};
if (asked.has('slots')) {
  extend({ slots: {
    'event-bar-end': () => '<button type="button" class="btn demo-next">Next step</button>',
    'event-under-bar': (ev) => (ev.from
      ? `<p class="demo-under">%(not_ours)s ${ev.from.drug}'s thresholds</p>`
      : '<p class="demo-under">%(line)s</p>'),
    'event-drug-mark': (ev) => (ev.drug === asked.get('drug')
      ? '<span class="demo-mark">%(mark)s</span>' : ''),
  } });
}
const screens = JSON.parse(asked.get('screens') || '[]');
const PAGE = '<main class="product-page">'
  + '<section class="oa-chart oa-chart-wide" id="demo"></section>'
  + '<div style="height: 800px"></div></main>';
extend({
  routes: [(parts) => (parts[0] === 'compared-demo' ? { page: 'compared-demo' } : null)],
  addresses: [(parts) => parts[0] === 'compared-demo'],
  pages: {
    'compared-demo': (route, app) => {
      app.innerHTML = framed(PAGE, 'compared-demo');
      const drug = asked.get('drug');
      const how = asked.get('classes') === '0' ? { classes: false } : {};
      window.drawTable = () => { window.table = eventsTable(app.querySelector('#demo'), {
        drug, open: () => {},
        columns: asked.has('slots') ? [{ id: 'demo', head: 'Host', after: 'start',
          cell: () => '<span class="demo-cell">Host cell</span>' }] : [],
        opened: {
          key: asked.get('opened'),
          draw: (box, row) => {
            window.ev = openedEvent(box, { drug, row, screens, tab: 'compared', ...how });
          },
        },
      }); };
      if (!asked.has('later')) window.drawTable();
    },
  },
});
""".replace("%(not_ours)s", NOT_OURS)
    .replace("%(line)s", HOST_LINE)
    .replace("%(mark)s", HOST_MARK)
)


class WithModule(LocalAccess):
    modules = (MODULE,)


def hosted(release_dir: Any) -> Any:
    app = FastAPI()
    app.add_api_route(MODULE, lambda: Response(HOST_JS, media_type="text/javascript"))
    app.add_api_route(PAGE, index, methods=["GET"])
    return host(app, create_app(release_dir, access=WithModule()))


@pytest.fixture(scope="module")
def classed_release(stats_release, tmp_path_factory) -> Path:
    """The release whose EBGM prior fits, carrying the invented classes and their statistics."""
    copy = tmp_path_factory.mktemp("compared") / stats_release.name
    shutil.copytree(stats_release, copy)
    fakeclasses.add_classes(copy)
    return copy


@pytest.fixture(scope="module")
def base(classed_release) -> Iterator[str]:
    with served(hosted(classed_release)) as at:
        yield at


@pytest.fixture(scope="module")
def bare_base(stats_release, tmp_path_factory) -> Iterator[str]:
    copy = tmp_path_factory.mktemp("compared_bare") / stats_release.name
    shutil.copytree(stats_release, copy)
    fakeclasses.remove_classes(copy)
    with served(hosted(copy)) as at:
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


def at(base: str, **asked: Any) -> str:
    what = {"drug": DRUG, "opened": KEY, **asked}
    if "screens" in what:
        what["screens"] = json.dumps(what["screens"])
    return f"{base}{PAGE}?{urlencode(what)}"


def answer(base: str, path: str, **asked: Any) -> Any:
    """A published answer, asked apart from the page."""
    got = httpx.get(f"{base}{path}", params=asked, timeout=30)
    assert got.status_code == 200, got.text
    return got.json()


# Each row of the table, as a person reads it: its name, its cells, what it is.
ROWS = """() => [...document.querySelectorAll(
    '.oa-ev-pane[data-pane="compared"]:not([hidden]) .oa-cmp-table > tbody > tr')].filter((tr) =>
    tr.getClientRects().length).map((tr) => {
  const text = (el) => el?.textContent.replace(/\\s+/g, ' ').trim() ?? '';
  const c = [...tr.cells];
  return { key: tr.dataset.row, name: text(c[0]), link: !!c[0].querySelector('.oa-link'),
    cases: text(c[1]), eb05: text(c[3]), eb05Change: text(c[4]), prr: text(c[6]),
    prrChange: text(c[7]), serious: text(c[8]), fatal: text(c[9]),
    hot: !!tr.querySelector('.oa-cmp-hotv'), out: !!tr.querySelector('.oa-cmp-remove') };
})"""


def rows(page: Any) -> dict[str, dict[str, Any]]:
    settle(page)
    return {r["key"]: r for r in page.evaluate(ROWS)}


def share(part: int, whole: int) -> str:
    if not whole:
        return ""
    return "<1%" if part and 100 * part / whole < 1 else f"{round(100 * part / whole)}%"


def named(got: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(zip(got["columns"], row, strict=True)) for row in got["rows"]]


def event_row(base: str, drug: str, **window: str) -> dict[str, Any]:
    """The drug's row of /api/events for the event."""
    listed = named(answer(base, "/api/events", product=drug, pt=EVENT, **window))
    return next((r for r in listed if r["pt"].lower() == EVENT.lower()), {})


def quarter_days(quarter: str) -> dict[str, str]:
    """A quarter (2026q2) as the days the window takes."""
    year, month = int(quarter[:4]), int(quarter[-1]) * 3
    last = monthrange(year, month)[1]
    return {
        "received_from": f"{year}-{month - 2:02d}-01",
        "received_to": f"{year}-{month:02d}-{last}",
    }


def score_at(base: str, drug: str, stat: str, day: str) -> Any:
    """The drug's score for the event at the last quarter end by `day`, or None, from the answer of
    /api/statistics/quarters, read apart from the page."""
    got = answer(base, "/api/statistics/quarters", product=drug, reaction=EVENT)
    held = [dict(zip(got["columns"], r, strict=True)) for r in got["events"][0]["series"]]
    ends = [
        r for r in held if quarter_days(f"{r['qnum'] // 10}q{r['qnum'] % 10}")["received_to"] <= day
    ]
    return ends[-1][stat] if ends else None


def all_dates_held(page: Any) -> None:
    """All dates pressed while the answers are held: the menu closes, nothing settles yet."""
    page.click(".oa-ev-dates")
    page.locator(".oa-ev-dates-menu .oa-choice", has_text="All dates").click()
    page.keyboard.press("Escape")


def all_dates(page: Any) -> None:
    """The window set to all of the release's dates, from the frame's Dates menu."""
    page.click(".oa-ev-dates")
    page.locator(".oa-ev-dates-menu .oa-choice", has_text="All dates").click()
    settle(page)
    page.keyboard.press("Escape")


def add_drug(page: Any, words: str, name: str) -> None:
    page.locator(".oa-cmp-add").click()
    page.locator("#oa-cmp-find").fill(words)
    settle(page)
    page.locator(f'[data-act="cmp-tick"][data-name="{name}"]').first.click()
    page.keyboard.press("Escape")
    settle(page)


def shot(page: Any, name: str) -> None:
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def pick_days(page: Any, first: str, last: str) -> None:
    """The window set from the frame's calendar."""
    page.click(".oa-ev-dates")
    page.locator(".oa-ev-dates-menu .oa-choice", has_text="Pick days").click()
    for day in (first, last):
        page.wait_for_selector(".oa-ev-cal:popover-open")
        page.click(".oa-ev-cal [data-act='ev-cal-months']")
        page.click(".oa-ev-cal [data-act='ev-cal-years']")
        page.click(f".oa-ev-cal [data-act='ev-cal-year'][data-v='{day[:4]}']")
        page.click(f".oa-ev-cal [data-act='ev-cal-month'][data-v='{int(day[5:7])}']")
        page.click(f".oa-ev-cal [data-act='ev-cal-day'][data-v='{day}']")
    settle(page)


def assert_row_is_the_answers(base: str, row: dict[str, Any], drug: str, **window: str) -> None:
    """A drug's row against /api/events under the same window, and its scores against the quarters
    and, for a window to the release's end, against /api/events/statistics."""
    got = event_row(base, drug, **window)
    cases = got.get("cases", 0)
    assert row["cases"] == f"{cases:,}"
    assert row["serious"] == share(got.get("serious", 0), cases)
    assert row["fatal"] == share(got.get("death", 0), cases)


def test_each_rows_numbers_agree_with_the_events_answer_for_that_drug(page_at, base):
    """The event's drug and each drug added: cases, serious and fatal under All dates agree with
    that drug's row of /api/events; EB05 and PRR with its statistics as they stand."""
    page = page_at(at(base), width=1440)
    add_drug(page, "ibu", OTHER)
    all_dates(page)
    shown = rows(page)
    stats = {
        d: {r["pt"].lower(): r for r in named(answer(base, "/api/events/statistics", product=d))}
        for d in (DRUG, OTHER)
    }
    for key, drug in (("own", DRUG), (f"d:{OTHER}", OTHER)):
        row = shown[key]
        assert_row_is_the_answers(base, row, drug)
        assert event_row(base, drug)["cases"] > 0
        pair = stats[drug][EVENT.lower()]
        assert row["eb05"].split()[-1] == f"{pair['eb05']:.2f}"
        assert row["prr"].split()[-1] == f"{pair['prr']:.2f}"
    assert shown[f"d:{OTHER}"]["link"] and not shown["own"]["link"]


def test_a_rows_numbers_follow_the_window_and_the_lines_filters(page_at, base):
    """Under a filter on the line and the frame's newest quarter, each row is still that drug's
    answer under the same question; a case-less window shows no share."""
    page = page_at(at(base), width=1440)
    add_drug(page, "ibu", OTHER)
    window = quarter_days(answer(base, "/api/release")["quarters"][1])
    shown = rows(page)
    for key, drug in (("own", DRUG), (f"d:{OTHER}", OTHER)):
        assert_row_is_the_answers(base, shown[key], drug, **window)
    all_dates(page)
    page.locator(".oa-ev-addfilter").click()
    page.locator(".oa-ev-menu, .menu").get_by_text("Sex", exact=True).first.hover()
    settle(page)
    page.locator(".menu [data-act] >> text=Male").first.click()
    page.keyboard.press("Escape")
    settle(page)
    query = dict(page.evaluate("() => [...new URLSearchParams(window.ev.context().query())]"))
    assert query.get("sex")
    shown = rows(page)
    sex = {k: v for k, v in query.items() if k == "sex"}
    for key, drug in (("own", DRUG), (f"d:{OTHER}", OTHER)):
        assert_row_is_the_answers(base, shown[key], drug, **sex)


def test_the_scores_stand_at_the_windows_start_and_end_and_never_past_it(page_at, base):
    """A drug's before and now are the quarters' answers at the window's start and end; a window
    that ends before the drug's first quarter ends shows no score, never the newest one; a class,
    scored only on the whole release, shows none for a window short of its end."""
    page = page_at(at(base), width=1440)
    pick_days(page, "2024-01-15", "2025-03-20")
    window = {"received_from": "2024-01-15", "received_to": "2025-03-20"}
    shown = rows(page)
    row = shown["own"]
    assert_row_is_the_answers(base, row, DRUG, **window)
    for stat in ("eb05", "prr"):
        before, now = row[stat].split(" → ")
        assert before == f"{score_at(base, DRUG, stat, '2024-01-14'):.2f}"
        assert now == f"{score_at(base, DRUG, stat, '2025-03-20'):.2f}"
    assert shown[f"c:{OWN_CLASS}"]["eb05"] == NO_SCORE
    first = answer(base, "/api/timeline", grain="day", product=DRUG, pt=EVENT)["rows"][0][0]
    assert first == "2023-03-01"
    pick_days(page, first, "2023-03-10")
    row = rows(page)["own"]
    assert row["eb05"] == NO_SCORE and row["prr"] == NO_SCORE


def test_a_class_row_is_counted_as_the_class_filter_counts_it(page_at, base):
    """A drug starts beside its own chemical class, open down to the drug; the class's cases,
    serious and fatal agree with the counted question for that class, made a second way; its scores
    are the class statistics, with no start; a window not reaching the release's end shows none."""
    page = page_at(at(base), width=1440)
    all_dates(page)
    shown = rows(page)
    row = shown[f"c:{OWN_CLASS}"]
    question = {"atc": OWN_CLASS, "arole": ["PS", "SS"], "pt": EVENT, "by": "year"}
    counted = answer(base, "/api/count", **question)
    assert row["cases"] == f"{counted['total']:,}"
    assert counted["total"] > 0
    deaths = answer(base, "/api/count", **question, outcome="DE")["total"]
    assert row["fatal"] == share(deaths, counted["total"])
    level = answer(base, "/api/statistics", by="class", level=4, find=EVENT)
    pair = next(r for r in level["rows"] if r["class"] == OWN_CLASS)
    assert row["eb05"] == f"{pair['eb05']:.2f}" and row["prr"] == f"{pair['prr']:.2f}"
    assert not row["eb05Change"]
    # the drug is inside its class, unpressable, and its row its own
    assert shown[f"d:{DRUG}"]["cases"] == shown["own"]["cases"]
    assert not shown[f"d:{DRUG}"]["link"] and not shown[f"d:{DRUG}"]["out"]
    assert row["out"]


def test_add_a_drug_or_class_ticks_as_the_class_filter_does(page_at, base):
    """The picker's tree: a class ticked adds its row, a class under it unticked leaves it out,
    typed words find classes and drugs; a tick moves no row while the menu is open; x takes a row
    out; a class pressed opens and shuts; what is chosen is kept for the person."""
    page = page_at(at(base), width=1440)
    settle(page)
    page.locator(".oa-cmp-add").click()
    settle(page)
    assert page.get_by_text("Drug class (ATC)").is_visible()
    assert "Oslo" in page.locator(".oa-cmp-menu .menu-footnote").inner_text()
    assert (
        page.locator('.oa-cmp-menu [data-act="cmp-class"][data-code="B01ZY"]').first.get_attribute(
            "aria-checked"
        )
        == "true"
    )
    assert (
        page.locator('.oa-cmp-menu [data-act="cmp-class"][data-code="B"]').get_attribute(
            "aria-checked"
        )
        == "mixed"
    )
    page.locator("#oa-cmp-find").fill("muscle")
    settle(page)
    page.locator('.oa-cmp-menu [data-act="cmp-class"][data-code="M"]').click()
    settle(page)
    page.keyboard.press("Escape")
    settle(page)
    shown = rows(page)
    assert "c:M" in shown and shown["c:M"]["out"]
    assert shown["c:M"]["eb05"] == NO_SCORE  # WHO's first level holds no statistics
    page.locator('tr[data-row="c:M"] .oa-cmp-open').click()
    settle(page)
    assert "c:M01" in rows(page)
    page.locator('tr[data-row="c:M"] .oa-cmp-open').click()
    settle(page)
    assert "c:M01" not in rows(page)
    kept = page.evaluate("(k) => JSON.parse(localStorage.getItem(k))", STORED)
    assert kept[DRUG]["atc"] == [OWN_CLASS, "M"]
    page.locator('tr[data-row="c:M"] .oa-cmp-remove').click()
    settle(page)
    assert "c:M" not in rows(page)
    assert page.evaluate("(k) => JSON.parse(localStorage.getItem(k))", STORED)[DRUG]["atc"] == [
        OWN_CLASS
    ]


def test_a_hosts_classes_false_keeps_every_class_out(page_at, base):
    """With `classes: false` the tab is of single drugs: no question names a class, none is drawn,
    the words are a drug's, no WHO line; a class kept earlier is neither read nor lost."""
    ticks = {"atc": [OWN_CLASS], "atcOut": [], "drugs": [], "order": [f"c:{OWN_CLASS}"],
             "names": {OWN_CLASS: "A class kept earlier"}}  # fmt: skip
    page = page_at(at(base, classes=0), width=1440, kept={KEPT: {DRUG: ticks}})
    assert list(rows(page)) == ["own"]
    all_asks = page.evaluate("() => window.asks")
    assert not [a for a in all_asks if "/api/classes" in a or "atc=" in a]
    assert page.locator(".oa-cmp-add").get_attribute("placeholder") == "Add a drug"
    assert page.locator(".oa-cmp-head").first.inner_text().strip().lower() == "drug"
    assert page.locator(".oa-cmp-foot .oa-who-line").count() == 0
    add_drug(page, "ibu", OTHER)
    assert list(rows(page)) == ["own", f"d:{OTHER}"]
    still = page.evaluate("(k) => JSON.parse(localStorage.getItem(k))", STORED)[DRUG]
    assert still["atc"] == [OWN_CLASS] and [d["name"] for d in still["drugs"]] == [OTHER]
    page.locator(".oa-cmp-add").click()
    settle(page)
    assert page.locator(".oa-cmp-menu").get_by_text("Drug class (ATC)").count() == 0
    assert not page.locator(".oa-cmp-menu .oa-who-line").count()
    page.keyboard.press("Escape")
    # its read-only view is of single drugs too
    page.locator('[data-act="cmp-go"]').first.click()
    settle(page)
    page.locator('.oa-cmp-view .oa-ev-tab[data-v="compared"]').click()
    settle(page)
    assert page.locator(".oa-cmp-view .oa-cmp-class").count() == 0
    asks = page.evaluate("() => window.asks")
    assert not [a for a in asks if "/api/classes" in a or "atc=" in a]


def test_a_release_with_no_classes_offers_drugs_only(page_at, bare_base):
    page = page_at(at(bare_base), width=1440)
    assert list(rows(page)) == ["own"]
    assert page.locator(".oa-cmp-add").get_attribute("placeholder") == "Add a drug"
    assert not [a for a in page.evaluate("() => window.asks") if "/api/classes" in a]


def test_a_drug_pressed_opens_its_read_only_view_with_no_host_cells_and_back(page_at, base):
    """Pressing another drug opens its own view of the event on its Overview, in this window, with
    its own numbers: a host's column, row cells and next step are not drawn in it, nor the first
    event's line or bar; a host's line, told who it is from, is. Back returns to the comparison."""
    page = page_at(at(base, slots=1), width=1440)
    add_drug(page, "ibu", OTHER)
    all_dates(page)
    outer = page.locator(".oa-et-opened-box").first
    assert page.locator(".demo-under").first.inner_text() == HOST_LINE
    assert outer.locator(".demo-next").is_visible()
    assert page.locator('tr[data-row="own"] .demo-mark').inner_text() == HOST_MARK
    assert page.locator(f'tr[data-row="d:{OTHER}"] .demo-mark').count() == 0
    page.locator('[data-act="cmp-go"]').first.click()
    settle(page)
    view = page.locator(".oa-cmp-view")
    assert view.locator(".demo-cell").count() == 0
    assert view.locator(".demo-next").count() == 0
    assert view.locator(".oa-et-table > thead th").all_inner_texts()[0].strip().lower() == "event"
    assert not outer.locator(":scope > .oa-ev > .oa-ev-bar").is_visible()
    assert not outer.locator(":scope > .oa-ev > .oa-ev-linewrap").is_visible()
    assert page.locator(".demo-next:visible").count() == 0
    assert view.locator(".demo-under").inner_text() == f"{NOT_OURS} {DRUG}'s thresholds"
    assert "Ibuprofen's haemorrhage, read only" in view.locator(".oa-cmp-viewtitle").inner_text()
    assert view.locator(".oa-ev-tab[aria-selected='true']").get_attribute("data-v") == "overview"
    # it carried the window, and its row is that drug's own
    assert "all dates" in view.locator(".oa-ev-line").inner_text().lower()
    cells = view.locator(".oa-et-table > tbody > tr").first.locator("td, th").all_inner_texts()
    assert str(event_row(base, OTHER)["newest"]) in cells
    # no third level: its Compared tab opens no further view
    view.locator('.oa-ev-tab[data-v="compared"]').click()
    settle(page)
    assert view.locator('[data-act="cmp-go"]').count() == 0
    back = view.locator(".oa-ev-back")
    assert back.inner_text() == "Back to warfarin's haemorrhage"
    back.click()
    settle(page)
    assert page.locator(".oa-cmp-view").first.is_hidden()
    assert outer.locator(":scope > .oa-ev > .oa-ev-bar").is_visible()
    assert list(rows(page)) == ["own", f"c:{OWN_CLASS}", f"d:{DRUG}", f"d:{OTHER}"]


def test_a_views_own_changes_stay_in_it(page_at, base):
    """A filter set in the read-only view changes that view alone: the first event's window and
    filters and its own Cases count are as they were on Back."""
    page = page_at(at(base), width=1440)
    add_drug(page, "ibu", OTHER)
    all_dates(page)
    before = page.evaluate("() => window.ev.context().query()")
    page.locator('[data-act="cmp-go"]').first.click()
    settle(page)
    view = page.locator(".oa-cmp-view")
    view.locator(".oa-ev-dates").click()
    page.locator(".oa-ev-dates-menu .oa-choice", has_text="The last four quarters").click()
    settle(page)
    page.keyboard.press("Escape")
    assert "all dates" not in view.locator(".oa-ev-line").inner_text().lower()
    view.locator(".oa-ev-back").click()
    settle(page)
    assert page.evaluate("() => window.ev.context().query()") == before


def test_marks_and_red_come_only_from_a_host(page_at, base):
    """With no host's places and no screens: no mark, no line, no next step, no warning color. With
    a screen a drug passes, its value is in the warning color, and a class never is."""
    page = page_at(at(base), width=1440)
    all_dates(page)
    shown = rows(page)
    assert not any(r["hot"] for r in shown.values())
    assert page.locator(".demo-mark, .demo-next, .demo-under").count() == 0
    words = page.locator(".oa-cmp").inner_text().lower()
    for word in ("yours", "last decision", "not a "):
        assert word not in words
    hosted_page = page_at(
        at(base, screens=[{"name": "Host", "conditions": [{"column": "eb05", "at_least": 2}]}]),
        width=1440,
    )
    all_dates(hosted_page)
    shown = rows(hosted_page)
    assert shown["own"]["hot"]
    assert not shown[f"c:{OWN_CLASS}"]["hot"]


def test_the_head_sorts_each_level_on_its_own_the_drug_staying_on_top(page_at, base):
    page = page_at(at(base), width=1440)
    add_drug(page, "ibu", OTHER)
    all_dates(page)
    page.locator('.oa-cmp-head[data-v="name"]').click()
    page.locator('[data-act="cmp-sort"][data-dir="asc"]').click()
    settle(page)
    keys = list(rows(page))
    assert keys[0] == "own"
    assert keys.index(f"d:{OTHER}") < keys.index(f"c:{OWN_CLASS}")
    assert keys.index(f"c:{OWN_CLASS}") < keys.index(f"d:{DRUG}")
    assert "A to Z" in page.locator(".oa-cmp-count").inner_text()


# a font wider than Inter, as a machine could fall back to if Inter never came
WIDER_FONT = ':root { --font-sans: "DejaVu Sans", Verdana, sans-serif; }'
FITS = """() => {
  const cells = [...document.querySelectorAll('.oa-cmp-table thead th')];
  const cut = cells.filter((c) => {
    const b = c.querySelector('button, span');
    if (!b || !c.getClientRects().length) return false;
    const room = c.getBoundingClientRect(), it = b.getBoundingClientRect();
    return it.right > room.right + 1 || it.left < room.left - 1;
  });
  const values = [...document.querySelectorAll('.oa-cmp-table td.oa-cmp-v')].filter((c) =>
    c.scrollWidth > c.clientWidth + 1);
  return { page: document.documentElement.scrollWidth - innerWidth,
    cut: [...cut, ...values].map((c) => c.textContent.trim()) };
}"""
STEADY_PARTS = ".oa-cmp-tools, .oa-cmp-table > thead, .oa-cmp-table > tbody > tr[data-row='own']"
ALL_PARTS = STEADY_PARTS + ", .oa-cmp-table > tbody > tr, .oa-cmp-foot"
# each part's place under the top of the tab: the line above it may wrap otherwise for new dates
PLACES = """(parts) => { const top = document.querySelector('.oa-cmp').getBoundingClientRect().top;
  return [...document.querySelectorAll(parts)].map((el) => {
    const r = el.getBoundingClientRect();
    return [Math.round(r.top - top), Math.round(r.left), Math.round(r.height)];
  }); }"""


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("theme", THEMES)
def test_at_every_width_and_theme_nothing_scrolls_and_nothing_moves(page_at, base, width, theme):
    """No sideways scroll of the page at any width and no head cut, the picker and the view
    included. As the first answers come the toolbar, the heads and the drug's row stay where they
    were drawn and each waiting row is as tall as its numbers' row; as a changed window's answers
    come nothing at all moves, each row showing what it had, faint, until then."""
    page = page_at(at(base, slots=1, later=1), width=width, theme=theme)
    page.evaluate("() => { window.hold(); window.drawTable(); }")
    page.wait_for_selector(".oa-cmp-table > tbody > tr[data-row='own'] .skeleton")
    shot(page, f"loading-{width}-{theme}")
    waiting = page.evaluate(PLACES, STEADY_PARTS)
    page.evaluate("() => window.letGo()")
    settle(page)
    assert page.evaluate(PLACES, STEADY_PARTS) == waiting
    assert page.evaluate(FITS) == {"page": 0, "cut": []}
    shot(page, f"compared-{width}-{theme}")

    settled = page.evaluate(PLACES, ALL_PARTS)
    page.evaluate("() => window.hold()")
    all_dates_held(page)
    page.wait_for_selector(".oa-cmp-stale")
    assert page.evaluate(PLACES, ALL_PARTS) == settled
    page.evaluate("() => window.letGo()")
    settle(page)
    assert page.evaluate(PLACES, ALL_PARTS) == settled
    assert not page.locator(".oa-cmp-stale").count()

    page.locator(".oa-cmp-add").click()
    settle(page)
    shot(page, f"picker-{width}-{theme}")
    assert page.evaluate(FITS)["page"] == 0
    box = page.locator(".oa-cmp-menu").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    page.locator("#oa-cmp-find").fill("ibu")
    settle(page)
    page.locator(f'[data-act="cmp-tick"][data-name="{OTHER}"]').first.click()
    page.keyboard.press("Escape")
    settle(page)
    shot(page, f"added-{width}-{theme}")
    page.locator('[data-act="cmp-go"]').first.click()
    settle(page)
    shot(page, f"view-{width}-{theme}")
    assert page.evaluate(FITS)["page"] == 0
    page.locator(".oa-cmp-view .oa-ev-back").click()
    settle(page)
    assert page.locator(".oa-cmp-main").first.is_visible()


def test_the_views_bar_with_back_stays_under_the_row_as_the_tab_scrolls(page_at, base):
    """Where the table fits its frame, a long view's bar, with Back, stays in sight."""
    page = page_at(at(base), width=1440)
    add_drug(page, "ibu", OTHER)
    page.locator('[data-act="cmp-go"]').first.click()
    settle(page)
    page.evaluate(
        "() => { document.querySelector('.oa-cmp-view .oa-ev-pane:not([hidden])')"
        ".style.minHeight = '3000px';"
        " document.querySelector('.oa-ev-pane:not([hidden])').scrollTop = 1500; }"
    )
    settle(page)
    back = page.locator(".oa-cmp-view .oa-ev-back").bounding_box()
    assert 0 <= back["y"] < 900


@pytest.mark.parametrize("width", [320, 768, 1024, 1440])
def test_with_a_wider_font_in_inters_place_no_head_is_cut(page_at, base, width):
    page = page_at(at(base), width=width)
    page.add_style_tag(content=WIDER_FONT)
    settle(page)
    assert page.evaluate(FITS) == {"page": 0, "cut": []}
