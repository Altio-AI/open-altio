"""An opened event's Overview pane (ui/event-overview.js, ui/event-chart.js, ui/event-tiles.js) in a
browser, drawn by a host's page module through the pane's own draw, as the opened event's frame
draws it: the event's cases by quarter, its threshold strips and the four tiles, each number the
published answer it reads; the window dark under its mark; the usual thresholds as strips, another
statistic added from Statistics and kept, and a host's screens taking a usual one's place, the only
way a tile turns the warning color; the event's own date; a section registered under the chart; and,
at 320, 768, 1024 and 1440 pixels, light and dark, nothing scrolling sideways, no tile's words cut,
and nothing moving as the answers arrive."""

from __future__ import annotations

import json
import os
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
from open_altio.testing.browser import open_page, served, settle

# a folder to keep the pane's pictures in, at each width and theme, to look at beside the design
SHOTS = os.environ.get("OPEN_ALTIO_OVERVIEW_SHOTS")
WIDTHS = [320, 768, 1024, 1440]
THEMES = ["light", "dark"]
MODULE = "/overview-host/page.js"
PAGE = "/overview-demo"
DRUG, EVENT = "warfarin", "Haemorrhage"
# the window and the period before it: the release's last two quarters against every day before
WINDOW = {"received_from": "2026-01-01", "received_to": "2026-06-30"}
BEFORE_TO = "2025-12-31"
BEFORE = {"before_from": "", "before_to": BEFORE_TO}

# A host's page drawing the Overview pane into a box, with the ctx the frame hands a pane (or, with
# ?frame, the drug's events table with the event opened under its row in the frame itself): the
# address gives the drug, its reactions (pt, repeated), the window, the period before it, the date
# that counts (by), a host's screens (screens, JSON) and whether a field has nothing ticked (none).
# window.hold() holds the answers the pane asks for until window.letGo(), so a test can read the
# pane before they come; window.drawn() draws it again from the address.
HOST_JS = """
import { eventsTable, extend, framed, openedEvent } from '/ui/app.js';
import { overviewPane, overviewSection } from '/ui/event-overview.js';

const ask = window.fetch;
let gate = null;
window.hold = () => {
  let open;
  gate = new Promise((r) => { open = r; });
  window.letGo = () => { gate = null; open(); };
};
const held = (path) => String(path).startsWith('/api/')
  && !String(path).includes('/statistics/about');
window.fetch = (...a) => (gate && held(a[0]) ? gate.then(() => ask(...a)) : ask(...a));
window.sectionCtx = [];
overviewSection('demo', { order: 1, draw: (box, ctx) => {
  box.innerHTML = '<p class="demo-section">A section under the chart</p>';
  window.sectionCtx.push(ctx.drug);
  return { update: (next) => window.sectionCtx.push(`update:${next.drug}`) };
} });
const asked = new URLSearchParams(location.search);
const contextOf = () => {
  const by = asked.get('by') || 'received';
  const [f, t] = by === 'event' ? ['event_from', 'event_to'] : ['received_from', 'received_to'];
  const window = { [f]: asked.get('from') || '', [t]: asked.get('to') || '' };
  const before = {
    before_from: asked.get('before_from') || '', before_to: asked.get('before_to') || '' };
  const drug = asked.get('drug');
  return {
    drug, reaction: asked.getAll('pt'), row: {}, window, before, dateField: by, kind: 'days',
    filters: [], none: asked.has('none'), cases: null,
    screens: JSON.parse(asked.get('screens') || '[]'),
    query: (extra = {}) => new URLSearchParams({ product: drug, ...window, ...extra }).toString(),
    setFilter() {}, clearFilter() {}, openCase() {}, slot: () => '',
  };
};
window.drawn = () => {
  window.pane = overviewPane.draw(document.getElementById('demo'), contextOf()); };
window.update = () => window.pane.update(contextOf());
extend({
  routes: [(parts) => (parts[0] === 'overview-demo' ? { page: 'overview-demo' } : null)],
  addresses: [(parts) => parts[0] === 'overview-demo'],
  pages: {
    'overview-demo': (route, app) => {
      const main = '<main class="product-page"><div id="demo"></div></main>';
      app.innerHTML = framed(main, 'overview-demo');
      const drug = asked.get('drug');
      // ?frame: the drug's events table, the event opened under its row in the frame
      if (asked.has('frame')) {
        eventsTable(app.querySelector('#demo'), { drug, open: () => {}, opened: {
          key: `${drug}|${asked.get('pt').toLowerCase()}`,
          draw: (box, row) => { window.ev = openedEvent(box, { drug, row }); } } });
      } else if (!asked.has('later')) window.drawn();
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


def address(base: str, **asked: Any) -> str:
    """The host's page for the drug and event, the window and before it, with `asked` added."""
    what: dict[str, Any] = {
        "drug": DRUG, "pt": EVENT, "from": WINDOW["received_from"], "to": WINDOW["received_to"],
        **BEFORE, **asked,
    }  # fmt: skip
    if "screens" in what:
        what["screens"] = json.dumps(what["screens"])
    return f"{base}{PAGE}?{urlencode({k: v for k, v in what.items() if v is not None}, doseq=True)}"


def answer(base: str, path: str, **asked: Any) -> Any:
    """A published answer, asked apart from the page."""
    got = httpx.get(f"{base}{path}", params=asked)
    assert got.status_code == 200, got.text
    return got.json()


# What the pane shows, read as a person reads it.
SHOWN = """() => {
  const all = (s) => [...document.querySelectorAll(s)];
  const text = (el) => el?.textContent.replace(/\\s+/g, ' ').trim();
  return {
    title: text(document.querySelector('.oa-ov-head .chart-lead')),
    sub: text(document.querySelector('.oa-ov-sub')),
    strips: all('.oa-ov-sname').map(text),
    own: all('.oa-ov-sname.oa-ov-own').map(text),
    bars: all('.oa-ov-bar').length,
    window: all('.oa-ov-bar[data-in="window"]').length,
    heights: all('.oa-ov-bar').map((b) => +getComputedStyle(b).getPropertyValue('--h')),
    tips: all('.oa-ov-slot').map((s) => s.dataset.tip),
    mark: text(document.querySelector('.oa-ov-wmark')),
    tiles: all('.oa-ov-tile').map((t) => ({ k: text(t.querySelector('.oa-ov-k')),
      v: text(t.querySelector('.oa-ov-v')), s: text(t.querySelector('.oa-ov-s')),
      marks: [...t.querySelectorAll('svg text')].map(text),
      hot: !!t.querySelector('[data-hot="true"]') })),
    past: all('.oa-ov-cell[data-past="true"]').length,
    section: text(document.querySelector('.oa-ov-section .demo-section')),
  };
}"""


SIGN = {"at_least": "≥", "above": ">"}
NAME = {"eb05": "EB05", "prr": "PRR", "ror_lower": "ROR lower", "ic025": "IC025"}


def usual(base: str) -> dict[str, dict[str, Any]]:
    """Each statistic's usual threshold, its default preset, by the column it reads first."""
    about = answer(base, "/api/statistics/about")
    found = {}
    for s in about["statistics"]:
        for p in s["presets"]:
            if p.get("default"):
                found[p["when"][0]["column"]] = p
    return found


def label(preset: dict[str, Any]) -> str:
    """A strip's name: its first condition, as EB05 ≥ 2."""
    first = preset["when"][0]
    op = next(k for k in first if k != "column")
    return f"{NAME[first['column']]} {SIGN[op]} {first[op]}"


def fig(v: float) -> str:
    """A ratio as the page writes it: three figures or so."""
    return f"{round(v):,}" if abs(v) >= 100 else f"{v:.1f}" if abs(v) >= 10 else f"{v:.2f}"


def quarter(day: str) -> str:
    return f"{day[:4]} Q{(int(day[5:7]) + 2) // 3}"


def test_the_chart_counts_the_events_cases_by_quarter_as_the_timeline_does(page_at, base):
    page = page_at(address(base))
    got = page.evaluate(SHOWN)
    months = answer(base, "/api/timeline", grain="month", product=DRUG, pt=EVENT)
    by_quarter: dict[str, int] = {}
    for day, n in months["rows"]:
        by_quarter[quarter(day)] = by_quarter.get(quarter(day), 0) + n
    said = {tip.split(":")[0]: int(tip.split(": ")[1].split(" ")[0].replace(",", ""))
            for tip in got["tips"]}  # fmt: skip
    assert {q: n for q, n in said.items() if n} == by_quarter
    assert sum(said.values()) == sum(n for _, n in months["rows"])
    # every quarter from the first with a case to the release's newest, none left out
    assert got["bars"] == len(said) and min(said) == min(by_quarter) and max(said) == "2026 Q2"
    assert max(got["heights"]) <= 1 and got["sub"] == "cases by quarter received"


def test_the_window_is_dark_under_its_mark(page_at, base):
    got = page_at(address(base)).evaluate(SHOWN)
    assert got["mark"] == "Window" and got["window"] == 2
    every = page_at(address(base, **{"from": "", "to": ""})).evaluate(SHOWN)
    assert every["window"] == every["bars"]


def test_the_usual_thresholds_are_the_strips_and_the_title_says_when_they_passed(page_at, base):
    got = page_at(address(base)).evaluate(SHOWN)
    presets = usual(base)
    assert got["strips"] == [label(presets["eb05"]), label(presets["prr"])]
    series = answer(base, "/api/statistics/quarters", product=DRUG, reaction=EVENT)
    cols, rows = series["columns"], series["events"][0]["series"]

    def meets(when: list[dict[str, Any]], row: list[Any]) -> bool:
        values = dict(zip(cols, row, strict=True))
        return all(values[c["column"]] is not None and values[c["column"]] >= c["at_least"]
                   for c in when)  # fmt: skip

    past = sum(meets(presets[s]["when"], r) for s in ("eb05", "prr") for r in rows)
    assert got["past"] == past and past > 0
    assert "passed" in got["title"] and got["title"].endswith(("Q1", "Q2", "Q3", "Q4"))


def test_the_tiles_read_the_window_against_before_it(page_at, base):
    got = page_at(address(base)).evaluate(SHOWN)
    tiles = {t["k"]: t for t in got["tiles"]}
    assert list(tiles) == [
        "Cases in the window", "EB05 during the window", "PRR during the window", "Serious · fatal",
    ]  # fmt: skip
    now = answer(base, "/api/events/group", product=DRUG, reaction=EVENT, **WINDOW)
    every = answer(base, "/api/events/group", product=DRUG, reaction=EVENT, dedup="all", **WINDOW)
    assert tiles["Cases in the window"]["v"] == f"{now['cases']:,}"
    left = every["cases"] - now["cases"]
    plural = "" if left == 1 else "s"
    assert tiles["Cases in the window"]["s"] == f"{left} duplicate{plural} left out"
    series = answer(base, "/api/statistics/quarters", product=DRUG, reaction=EVENT)
    cols, rows = series["columns"], series["events"][0]["series"]
    by_q = {r[0]: dict(zip(cols, r, strict=True)) for r in rows}
    end, start = by_q[20262], by_q[20254]
    for stat, name in (("eb05", "EB05"), ("prr", "PRR")):
        tile = tiles[f"{name} during the window"]
        assert tile["v"].startswith(fig(end[stat]))
        assert tile["marks"] == [f"{fig(start[stat])} at its start"]
        assert not tile["hot"]
    before = answer(base, "/api/events/group", product=DRUG, reaction=EVENT, received_to=BEFORE_TO)
    serious = round(100 * now["serious"] / now["cases"])
    assert tiles["Serious · fatal"]["v"].startswith(f"{serious}%")
    change = serious - round(100 * before["serious"] / before["cases"])
    assert f"{'▲' if change >= 0 else '▼'}{abs(change)}" in tiles["Serious · fatal"]["v"]
    assert not tiles["Serious · fatal"]["hot"]


def test_a_window_ending_before_the_drugs_first_quarter_shows_no_score_never_the_newest(
    page_at, base
):
    """EB05 and PRR on every case up to the last quarter that ends in the window; for a window that
    ends before the drug's first quarter ends there is none, so the tile says it is not worked out
    and never shows the newest quarter's score."""
    first = answer(base, "/api/timeline", grain="day", product=DRUG, pt=EVENT)["rows"][0][0]
    series = answer(base, "/api/statistics/quarters", product=DRUG, reaction=EVENT)
    newest = dict(zip(series["columns"], series["events"][0]["series"][-1], strict=True))
    got = page_at(address(base, **{"from": first, "to": first, "before_to": ""})).evaluate(SHOWN)
    tiles = {t["k"]: t for t in got["tiles"]}
    for stat, name in (("eb05", "EB05"), ("prr", "PRR")):
        tile = tiles[f"{name} during the window"]
        assert tile["v"] == "Not worked out", tile
        assert fig(newest[stat]) not in tile["v"], tile
        assert tile["marks"] == []


NOTE_BOXES = """() => [...document.querySelectorAll('.oa-ov-tile')].flatMap((t) => {
  const tile = t.getBoundingClientRect();
  return [...t.querySelectorAll('.oa-ov-mtext')].map((el) => {
    const r = el.getBoundingClientRect();
    return { k: t.querySelector('.oa-ov-k').textContent, words: el.textContent,
      out: r.left < tile.left - 1 || r.right > tile.right + 1 };
  });
})"""


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_words_under_a_mark_stay_inside_their_tile_under_all_dates(page_at, base, width, theme):
    """Under All dates the window starts before the drug's first quarter, so a mark says "none at
    its start" under its filled dot, at the tile's far end: those words stay inside the tile."""
    page = page_at(
        address(base, **{"from": None, "to": None, "before_to": None}), width=width, theme=theme
    )
    notes = page.evaluate(NOTE_BOXES)
    assert any(n["words"] == "none at its start" for n in notes), notes
    assert [n for n in notes if n["out"]] == [], notes


def test_a_hosts_screen_takes_the_usual_strips_place_and_alone_turns_a_tile_the_warning_color(
    page_at, base
):
    screen = {"name": "Our EB05", "conditions": [{"column": "eb05", "at_least": 1}]}
    share = {"share": "serious", "points": 101}
    got = page_at(address(base, screens=[screen, share])).evaluate(SHOWN)
    prr = label(usual(base)["prr"])
    assert got["strips"] == ["Our EB05", prr]
    assert got["own"] == [prr]  # beside a host's, the person's own read lighter
    tiles = {t["k"]: t for t in got["tiles"]}
    assert tiles["EB05 during the window"]["hot"] and not tiles["PRR during the window"]["hot"]
    # the shares came, with the chance test the host's alarm asks for, and none rose 101 points
    assert "%" in tiles["Serious · fatal"]["v"] and not tiles["Serious · fatal"]["hot"]


def test_statistics_adds_a_strip_for_another_statistic_and_keeps_it(page_at, base):
    eb05, prr, ror = (label(usual(base)[c]) for c in ("eb05", "prr", "ror_lower"))
    page = page_at(address(base))
    page.click(".oa-ov-more")
    page.click('[data-act="ev-ov-strip"][data-v="ror_lower"]')
    page.keyboard.press("Escape")
    settle(page)
    assert page.evaluate(SHOWN)["strips"] == [eb05, prr, ror]
    page.reload()
    settle(page)
    assert page.evaluate(SHOWN)["strips"] == [eb05, prr, ror]
    page.click(".oa-ov-more")
    page.click('[data-act="ev-ov-strip"][data-v="eb05"]')
    page.keyboard.press("Escape")
    settle(page)
    assert page.evaluate(SHOWN)["strips"] == [prr, ror]


def test_by_the_day_the_event_began_the_chart_says_so_and_counts_the_undated_apart(page_at, base):
    url = address(
        base, by="event", **{"from": "2025-01-01", "to": "2025-12-31"}, before_to="2024-12-31"
    )
    got = page_at(url).evaluate(SHOWN)
    months = answer(base, "/api/timeline", grain="month", by="event", product=DRUG, pt=EVENT)
    assert got["sub"].startswith("cases by quarter the reaction started")
    if months["undated"]:
        assert f"{months['undated']:,} case" in got["sub"]
    assert sum(int(t.split(": ")[1].split(" ")[0].replace(",", "")) for t in got["tips"]) == sum(
        n for _, n in months["rows"]
    )
    now = answer(base, "/api/events/group", product=DRUG, reaction=EVENT,
                 event_from="2025-01-01", event_to="2025-12-31")  # fmt: skip
    assert {t["k"]: t for t in got["tiles"]}["Cases in the window"]["v"] == f"{now['cases']:,}"


def test_a_section_draws_under_the_chart_and_is_told_each_change(page_at, base):
    page = page_at(address(base))
    got = page.evaluate(SHOWN)
    assert got["section"] == "A section under the chart"
    order = page.evaluate("""() => {
      const r = (s) => document.querySelector(s).getBoundingClientRect();
      return r('.oa-ov-section').top >= r('.oa-ov-chart').bottom; }""")
    assert order
    assert page.evaluate("() => window.sectionCtx") == [DRUG]
    page.evaluate("() => window.update()")
    assert page.evaluate("() => window.sectionCtx") == [DRUG, f"update:{DRUG}"]


def test_nothing_ticked_shows_no_case_and_no_number(page_at, base):
    got = page_at(address(base, none=1)).evaluate(SHOWN)
    assert got["bars"] == 0
    assert {t["k"]: t for t in got["tiles"]}["Cases in the window"]["v"] == "0"


# Where the pane's parts stand, and what spills: the page scrolling sideways, a tile's words running
# past it, the strips' names or the years cut.
BOXES = """() => {
  const box = (s) => { const r = document.querySelector(s)?.getBoundingClientRect();
    return r && [r.left, r.top, r.right, r.bottom].map(Math.round); };
  const hides = (el) => getComputedStyle(el).overflow !== 'visible';
  const cut = [...document.querySelectorAll('.oa-ov-tile, .oa-ov-tile *, .oa-ov-sname')]
    .filter((el) => el.scrollWidth > el.clientWidth + 1 && hides(el))
    .map((el) => el.className.baseVal ?? el.className);
  // the claim itself is never cut: only the words after it give way
  const lead = [...document.querySelector('.oa-ov-head .chart-lead').getClientRects()].at(-1);
  const line = document.querySelector('.oa-ov-head .chart-sentence').getBoundingClientRect();
  if (lead.right > line.right + 1 || lead.bottom > line.bottom + 1) cut.push('chart-lead');
  const tiles = [...document.querySelectorAll('.oa-ov-tile')];
  const spill = tiles.flatMap((t) => [...t.querySelectorAll('.oa-ov-v, .oa-ov-k, .oa-ov-s, svg')]
    .filter((el) => el.getBoundingClientRect().right > t.getBoundingClientRect().right + 1)
    .map((el) => `${t.querySelector('.oa-ov-k').textContent}: ${el.textContent}`));
  return { chart: box('.oa-ov-chart'), plot: box('.oa-ov-plot'), tiles: box('.oa-ov-tiles'),
    section: box('.oa-ov-section'), cut, spill,
    page: document.documentElement.scrollWidth - innerWidth };
}"""


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_nothing_spills_or_moves_as_the_answers_arrive(page_at, base, width, theme):
    page = page_at(address(base, later=1), width=width, theme=theme)
    page.evaluate("() => { window.hold(); window.drawn(); }")
    # measured once the page's fonts have come: their arrival moves words, and this is the answers'
    page.evaluate(
        "async () => { await document.fonts.load('400 13px Inter'); await document.fonts.ready; }"
    )
    waiting = page.evaluate(BOXES)
    assert page.locator(".oa-ov .skeleton").count() > 0
    page.evaluate("() => window.letGo()")
    settle(page)
    drawn = page.evaluate(BOXES)
    assert page.locator(".oa-ov-bar").count() > 0
    for part in ("chart", "plot", "tiles", "section"):
        assert waiting[part] == drawn[part], (part, waiting[part], drawn[part])
    assert drawn["page"] <= 0 and drawn["cut"] == [] and drawn["spill"] == [], drawn
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.locator(".oa-ov").screenshot(path=str(Path(SHOTS) / f"overview-{width}-{theme}.png"))


def test_the_frame_opens_on_the_overview_and_its_dates_move_the_window(page_at, base):
    page = page_at(f"{base}{PAGE}?{urlencode({'frame': 1, 'drug': DRUG, 'pt': EVENT})}")
    in_window = "() => /\\d/.test(document.querySelector('.oa-ev-count')?.textContent || '')"
    page.wait_for_function(in_window)
    settle(page)
    pane = '.oa-ev-pane[data-pane="overview"]'
    assert page.locator(f"{pane} .oa-ov-plot").is_visible()
    got = page.evaluate(SHOWN)
    newest = answer(base, "/api/release")["quarters"][1]
    assert got["bars"] > 0 and got["window"] == 1 and got["tips"][-1].startswith(quarter_of(newest))
    page.click(".oa-ev-dates")
    page.locator(".oa-ev-dates-menu .oa-choice", has_text="The last four quarters").click()
    page.wait_for_function(in_window)
    settle(page)
    got = page.evaluate(SHOWN)
    assert got["window"] == 4
    last = [int(t.split(": ")[1].split(" ")[0].replace(",", "")) for t in got["tips"][-4:]]
    cases = {t["k"]: t for t in got["tiles"]}["Cases in the window"]["v"]
    assert cases == f"{sum(last):,}"
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.locator(".oa-et-opened, .oa-ev").first.screenshot(
            path=str(Path(SHOTS) / "frame-1440.png")
        )


def quarter_of(name: str) -> str:
    """An FDA quarter, 2026q2, as the chart names it."""
    return f"{name[:4]} Q{name[-1]}"


def test_a_free_page_draws_no_overview(page_at, base):
    page = page_at(f"{base}/")
    assert page.locator(".oa-ov").count() == 0
