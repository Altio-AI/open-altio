"""The page in a real browser, for what only a browser shows: an app served on this machine and
opened in Playwright's headless Chromium, with the clock, the time zone and the browser's kept
choices fixed, so the same code draws the same page every time.

    with served(app) as base:                       # the app on a free port of 127.0.0.1
        page = open_page(browser, base + "/all/cases", width=390)
        assert first_column_held(page.locator(".dashboard-frame"))["held"]
        assert not cells_fit(page, ".oa-cases tr")["leaks"]

`chromium` in fixtures.py hands tests the browser, and skips them where Playwright or its
headless shell is not installed (`pip install playwright`, then
`playwright install chromium --only-shell`).
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

# the moment the browser's clock stands at, a time of day with the same greeting everywhere
NOW = datetime(2026, 7, 14, 10, 30, tzinfo=UTC)
HEIGHTS = {390: 844, 1024: 768, 1440: 900}

# drawn: every answer the page asked for has come, and nothing waits under a skeleton
STEADY = """() => window.asking === 0
  && !document.querySelector('#app .skeleton, #oa-layer .skeleton, [aria-busy="true"]')"""
# counts the answers the page is waiting for, each until its body is read and the page has had a
# turn to use it, so a test waits for those and not for a fixed while
ASKING = """(() => {
  window.asking = 0;
  const ask = window.fetch;
  const done = () => setTimeout(() => { window.asking -= 1; });
  window.fetch = (...args) => {
    window.asking += 1;
    const read = (r) => { r.clone().arrayBuffer().catch(() => {}).finally(done); return r; };
    return ask(...args).then(read, (err) => { done(); throw err; });
  };
})();"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def served(app: Any) -> Iterator[str]:
    """The app on a free port of this machine for as long as the block runs; yields its address."""
    import uvicorn

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def open_page(
    browser: Any,
    url: str,
    *,
    width: int = 1440,
    theme: str = "light",
    kept: dict[str, Any] | None = None,
    cookies: Sequence[dict[str, str]] = (),
    touch: bool = False,
) -> Any:
    """A new page at `url`, drawn and settled: `kept` is what the browser keeps for its person
    (the explorer's local storage, by key), `cookies` a session's, `touch` a phone's touch screen
    (pressed with page.tap). Close it with page.context.close()."""
    context = browser.new_context(
        viewport={"width": width, "height": HEIGHTS.get(width, 900)},
        locale="en-GB",
        timezone_id="UTC",
        device_scale_factor=1,
        color_scheme=theme,
        has_touch=touch,
        is_mobile=touch,
    )
    context.set_default_timeout(10_000)
    origin = urlsplit(url)
    context.add_cookies([{**c, "url": f"{origin.scheme}://{origin.netloc}/"} for c in cookies])
    stored = {**(kept or {}), "theme": theme}
    context.add_init_script(f"""(() => {{
      const kept = {json.dumps(stored)};
      try {{
        for (const [k, v] of Object.entries(kept)) {{
          localStorage.setItem(`open-altio.${{k}}`, JSON.stringify(v));
        }}
      }} catch {{ /* storage off */ }}
    }})();""")
    context.add_init_script(ASKING)
    page = context.new_page()
    page.clock.set_fixed_time(NOW)
    page.goto(url)
    settle(page)
    return page


# Two frames, so what the page set going in them has started, then until every motion that ends
# (a chevron turning as its row opens) has ended: a check reads the page at rest, as a person does.
AT_REST = """() => new Promise((frame) => requestAnimationFrame(() => requestAnimationFrame(frame)))
  .then(() => Promise.all(document.getAnimations()
    .filter((a) => a.effect && a.effect.getComputedTiming().endTime !== Infinity)
    .map((a) => a.finished.catch(() => null))))"""


def settle(page: Any) -> None:
    """Wait until the page has its answers and has drawn them."""
    page.wait_for_load_state("load")
    page.wait_for_function(STEADY, timeout=10_000)
    page.evaluate("() => document.fonts.ready")
    page.evaluate(AT_REST)


# A wide table's frame scrolled to its far end: where its first column and the first row's first
# cell stand against the frame's left edge, whether every head stands over its column, whether the
# first cell covers what scrolled under it, and its ground. A frame too wide to scroll at this width
# is narrowed first, so the scrolling itself is what is checked.
HELD = """(f) => {
  if (f.scrollWidth <= f.clientWidth) f.style.maxWidth = '240px';
  f.scrollLeft = f.scrollWidth;
  const t = f.querySelector('table');
  t.tBodies[0].rows[0].scrollIntoView({ block: 'center', inline: 'nearest' });
  const x = (c) => Math.round(c.getBoundingClientRect().left);
  const head = t.tHead.rows[0].cells, row = t.tBodies[0].rows[0].cells;
  const first = row[0].getBoundingClientRect();
  const on = document.elementFromPoint(first.left + 4, first.top + first.height / 2);
  const edge = Math.round(f.getBoundingClientRect().left + f.clientLeft);
  return { scrolled: f.scrollLeft > 0, edge,
    head: x(head[0]), cell: x(row[0]), in_line: [...head].every((h, i) => x(h) === x(row[i])),
    covers: row[0].contains(on), ground: getComputedStyle(row[0]).backgroundColor };
}"""


def first_column_held(frame: Any) -> dict[str, Any]:
    """What HELD finds of the table in `frame`, a Playwright locator of its scrolling box, and
    `held`: it scrolled with its first column, head and all, at the frame's left edge over a ground
    of its own, and every head over its column."""
    got = dict(frame.evaluate(HELD))
    opaque = got["ground"] not in ("transparent", "rgba(0, 0, 0, 0)")
    at_edge = got["head"] == got["cell"] == got["edge"]
    got["held"] = got["scrolled"] and at_edge and got["in_line"] and got["covers"] and opaque
    return got


# A grey line about a value: FDA's own value, where ours came from, a rule's link, a current PT, a
# reason, a label's result. Tags beside a name on the case list are not lines.
SECONDARY = (
    ".oa-fda, .oa-case-note, .oa-rule-tag, .oa-pt:not(.oa-cases .oa-pt), .oa-status-why, "
    ".oa-status-who, .oa-flag-reason, .oa-label-line"
)
# Every drawn row `rows` names, a table's <tr> or a grid's row of cells, and every drawn cell
# `cells` names on its own, such as a field's value: each cell whose contents are wider than it
# (they run into the next one, or are cut off); each row whose cells do not set their first line
# of text on one line (the line the letters stand on: the first text's top plus its font's
# ascent, so a smaller tag's words stand on it too; half a pixel apart is one line); and each grey
# line about a value that sits beside the cell's first line, or starts left or right of it, rather
# than on a line of its own under it, flush with it. A cell with no text says nothing.
CELLS = """([rows, cells, secondary]) => {
  const drawn = (el) => el.getClientRects().length > 0
    && getComputedStyle(el).visibility !== 'hidden';
  const said = (el) => el.innerText.replace(/\\s+/g, ' ').trim().slice(0, 50);
  const ruler = document.createElement('canvas').getContext('2d');
  const firstText = (box) => {
    const walk = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const at = n.data.search(/\\S/);
      if (at < 0 || !drawn(n.parentElement)) continue;
      const r = document.createRange();
      r.setStart(n, at);
      r.setEnd(n, at + 1);
      const rect = r.getClientRects()[0];
      if (!rect || rect.width === 0) continue;
      const f = getComputedStyle(n.parentElement);
      ruler.font = `${f.fontStyle} ${f.fontWeight} ${f.fontSize} ${f.fontFamily}`;
      const ascent = ruler.measureText(n.data[at]).fontBoundingBoxAscent;
      return { node: n, rect, baseline: rect.top + ascent };
    }
    return null;
  };
  const leaks = [], uneven = [], beside = [];
  const look = (cell, where) => {
    if (cell.scrollWidth > cell.clientWidth) {
      leaks.push({ where, cell: said(cell), wide: cell.scrollWidth, room: cell.clientWidth });
    }
    const first = firstText(cell);
    if (!first) return null;
    const flush = !['right', 'end', 'center'].includes(getComputedStyle(cell).textAlign);
    for (const line of cell.querySelectorAll(secondary)) {
      const own = drawn(line) && firstText(line);
      if (!own || own.node === first.node) continue;
      const under = own.rect.top >= first.rect.bottom - 1;
      const left = Math.round((own.rect.left - first.rect.left) * 10) / 10;
      if (!under || (flush && Math.abs(left) > 0.5)) {
        beside.push({ where, cell: said(cell), line: said(line), under, left });
      }
    }
    return first.baseline;
  };
  let count = 0;
  for (const row of rows ? document.querySelectorAll(rows) : []) {
    if (!drawn(row)) continue;
    count += 1;
    const where = `${row.closest('table, [class]')?.className || ''} row ${count}`;
    const lines = [];
    for (const cell of [...(row.cells || row.children)].filter(drawn)) {
      const y = look(cell, where);
      if (y != null) lines.push([Math.round(y * 10) / 10, said(cell).slice(0, 24)]);
    }
    const ys = lines.map(([y]) => y);
    if (Math.max(...ys) - Math.min(...ys) > 0.5) uneven.push({ where, lines });
  }
  for (const cell of cells ? document.querySelectorAll(cells) : []) {
    if (!drawn(cell)) continue;
    count += 1;
    look(cell, `${cell.closest('[class]')?.className || ''} ${count}`);
  }
  return { rows: count, leaks, uneven, beside };
}"""


def cells_fit(page: Any, rows: str = "", cells: str = "") -> dict[str, Any]:
    """What CELLS finds of the rows `rows` selects (`tr` of a table, or a grid's rows, whose
    children are its cells) and of the cells `cells` selects on their own: how many it looked at
    (`rows`), the cells too narrow for what they hold (`leaks`), the rows whose cells do not set
    their first line on one line (`uneven`) and the grey lines about a value that are not on a
    line of their own under it, flush with it (`beside`)."""
    return dict(page.evaluate(CELLS, [rows, cells, SECONDARY]))


# How a choice's tick box is drawn: its fill and edge, the colour of the mark in it, its size, and
# the tip it shows on hover.
TICK = """(e) => {
  const box = e.querySelector('.oa-tick'), mark = box.querySelector('svg');
  const s = getComputedStyle(box);
  return { fill: s.backgroundColor, edge: s.borderTopColor,
    size: [box.offsetWidth, box.offsetHeight], mark: mark && getComputedStyle(mark).color,
    tip: box.dataset.tip || null };
}"""


def tick_look(page: Any, selector: str) -> dict[str, Any]:
    """TICK for the first choice at `selector`."""
    return dict(page.eval_on_selector(selector, TICK))


__all__ = [
    "HEIGHTS",
    "NOW",
    "SECONDARY",
    "cells_fit",
    "first_column_held",
    "free_port",
    "open_page",
    "served",
    "settle",
    "tick_look",
]
