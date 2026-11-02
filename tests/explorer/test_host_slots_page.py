"""The place a host draws in at the top right of every page (`corner-end`, ui/host.js SLOTS): its
buttons sit beside Improve this on a wide page and in the top bar on a phone, a page with no host
draws nothing there, and buttons that arrive after the page is drawn move nothing."""

from __future__ import annotations

import pytest
from fastapi.responses import Response

from open_altio.explorer.access import LocalAccess
from open_altio.testing.browser import served

FILLED_JS = """
import { extend } from '/ui/app.js';
extend({ improve: true, slots: { 'corner-end': (here) =>
  `<button type="button" class="btn host-btn" data-here="${here}">Share</button>` } });
"""
# says it will fill the place, draws nothing yet, and fills it once the page is drawn
LATE_JS = """
import { extend } from '/ui/app.js';
document.documentElement.style.setProperty('--corner-end-room', '120px');
extend({ improve: true, slots: { 'corner-end': () => '' } });
"""
BOXES = """() => {
  const box = (s) => { const r = document.querySelector(s)?.getBoundingClientRect();
    return r && [r.left, r.top, r.right, r.bottom].map(Math.round); };
  return { asof: box('.oa-corner .oa-asof'), improve: box('.oa-corner .oa-improve') };
}"""


class HostAccess(LocalAccess):
    modules = ("/host-ui/host.js",)


@pytest.fixture
def hosting(explorer_app, licensed_release):
    stack = []

    def serve(js: str) -> str:
        class Access(HostAccess):
            pass

        app = explorer_app(licensed_release, access=Access())
        app.add_api_route("/host-ui/host.js", lambda: Response(js, media_type="text/javascript"))
        context = served(app)
        stack.append(context)
        return context.__enter__()

    yield serve
    for context in reversed(stack):
        context.__exit__(None, None, None)


def test_a_hosts_buttons_sit_beside_improve_this_on_a_wide_page(opened, hosting):
    page = opened("/", width=1440, base=hosting(FILLED_JS))
    wide = page.evaluate(
        """() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
          const mine = r('.oa-corner .host-btn'), improve = r('.oa-corner .oa-improve');
          return { here: document.querySelector('.oa-corner .host-btn').dataset.here,
            beside: mine.left >= improve.right && Math.abs(mine.top - improve.top) < 8,
            inside: mine.right <= innerWidth, bar: getComputedStyle(
              document.querySelector('.oa-topbar')).display }; }"""
    )
    assert wide == {"here": "home", "beside": True, "inside": True, "bar": "none"}


def test_a_hosts_buttons_sit_in_the_top_bar_on_a_phone(opened, hosting):
    page = opened("/", width=320, base=hosting(FILLED_JS))
    assert page.is_visible(".oa-topbar .host-btn")
    assert not page.is_visible(".oa-corner .host-btn")
    fits = page.evaluate(
        """() => { const bar = document.querySelector('.oa-topbar').getBoundingClientRect();
          const mine = document.querySelector('.oa-topbar .host-btn').getBoundingClientRect();
          return { within: mine.left >= bar.left && mine.right <= bar.right,
            still: document.documentElement.scrollWidth <= innerWidth }; }"""
    )
    assert fits == {"within": True, "still": True}


@pytest.mark.parametrize("width", [320, 1440])
def test_a_page_with_no_host_draws_nothing_in_the_corner(opened, width):
    page = opened("/release", width=width)
    assert page.query_selector(".oa-corner-end") is None
    kinds = page.eval_on_selector_all(
        ".oa-corner > *", "els => els.map((e) => e.className.split(' ')[0])"
    )
    assert kinds == ["oa-asof"]


def test_buttons_that_arrive_after_the_page_is_drawn_move_nothing(opened, hosting):
    page = opened("/", width=1440, base=hosting(LATE_JS))
    before = page.evaluate(BOXES)
    page.evaluate(
        """() => document.querySelector('.oa-corner-end').innerHTML =
          '<button type="button" class="btn">Share</button>'"""
    )
    assert page.evaluate(BOXES) == before


HIDDEN_JS = """
import { extend } from '/ui/app.js';
extend({ hideAsOf: (here) => here === 'home' || here === 'methods' });
"""
ASOF_SEEN = "() => [...document.querySelectorAll('.oa-asof')].map((e) => e.textContent)"


@pytest.mark.parametrize("width", [320, 1440])
def test_a_host_can_leave_out_how_current_the_data_is_where_it_says_so(opened, hosting, width):
    """`hideAsOf(here)` true leaves the line out of the corner and the top bar; false, or none
    given, shows it on every page."""
    base = hosting(HIDDEN_JS)
    assert opened("/", width=width, base=base).evaluate(ASOF_SEEN) == []
    assert opened("/methods", width=width, base=base).evaluate(ASOF_SEEN) == []
    seen = opened("/release", width=width, base=base).evaluate(ASOF_SEEN)
    assert seen and all(line.startswith("Data refreshed") for line in seen)


@pytest.mark.parametrize("width", [320, 1440])
def test_with_no_hide_every_page_but_home_shows_how_current_the_data_is(opened, width):
    """Home says it in its release card instead."""
    for path in ("/methods", "/release"):
        seen = opened(path, width=width).evaluate(ASOF_SEEN)
        assert len(seen) == 2 and all(line.startswith("Data refreshed") for line in seen)
    assert opened("/", width=width).evaluate(ASOF_SEEN) == []
