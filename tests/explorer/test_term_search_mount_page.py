"""A host page mounts the term search (`termSearch`, ui/termsearch.js): it types, finds terms and
SMQs with the products it was given, hands the pick to the host, shows why there are no SMQs to a
viewer without MedDRA's licensed part, and moves nothing else on the page while results open."""

from __future__ import annotations

import pytest
from fastapi import Response

from open_altio.explorer.access import LocalAccess
from open_altio.testing.browser import open_page, served, settle

WIDTHS = [320, 1440]
HOST_JS = """
import { S, extend } from '/ui/app.js';
import { termSearch } from '/ui/app.js';
window.picks = [];
const LICENSED = __LICENSED__;
extend({
  start: async () => {
    S.me = { first_name: 'Host', tiers: { meddra: LICENSED } };
    S.release = await (await fetch('/api/release')).json();
  },
  routes: [(parts) => (parts.length === 0 ? { page: 'mounted' } : null)],
  pages: {
    mounted: (r, app) => {
      app.innerHTML = '<main><h1>Host page</h1><div id="above">Above</div><div id="mount"></div>'
        + '<p id="below">Below</p></main>';
      termSearch(document.getElementById('mount'), {
        products: new URLSearchParams(location.search).getAll('p'),
        onPick: (p) => window.picks.push(p) });
    },
  },
});
"""


class HostAccess(LocalAccess):
    modules = ("/host-ui/mount.js",)


def site(explorer_app, release, licensed):
    app = explorer_app(release, access=HostAccess())
    app.add_api_route(
        "/host-ui/mount.js",
        lambda: Response(
            HOST_JS.replace("__LICENSED__", str(licensed).lower()), media_type="text/javascript"
        ),
    )
    return served(app)


@pytest.fixture
def licensed_host(explorer_app, licensed_release):
    with site(explorer_app, licensed_release, True) as base:
        yield base


@pytest.fixture
def plain_host(explorer_app, release):
    with site(explorer_app, release, False) as base:
        yield base


def mounted(chromium, base, width, licensed, products=""):  # licensed: the host's module says so
    return open_page(chromium, base + "/" + products, width=width)


def type_in(page, words):
    page.fill("#mount input", words)
    page.wait_for_selector(
        "#mount .oa-choice, #mount .oa-smq, #mount .oa-pane-none:not(:has-text('Type'))"
    )
    settle(page)


BOXES = """() => ['above', 'below', 'mount'].map((id) => {
  const r = document.getElementById(id).getBoundingClientRect();
  return [id, Math.round(r.top), Math.round(r.height)]; })"""
SIDEWAYS = "() => document.documentElement.scrollWidth <= innerWidth"


@pytest.mark.parametrize("width", WIDTHS)
def test_a_pick_of_a_preferred_term_reaches_the_host_and_nothing_moves(
    chromium, licensed_host, width
):
    page = mounted(chromium, licensed_host, width, licensed=True)
    before = page.evaluate(BOXES)
    type_in(page, "nau")
    assert page.evaluate(BOXES) == before and page.evaluate(SIDEWAYS)
    page.click("#mount [data-pt='Nausea']")
    assert page.evaluate("window.picks") == [{"kind": "pt", "pt": "Nausea"}]
    page.context.close()


@pytest.mark.parametrize("width", WIDTHS)
def test_a_licensed_viewer_picks_an_smq_with_its_scope(chromium, licensed_host, width):
    page = mounted(chromium, licensed_host, width, licensed=True)
    type_in(page, "bleeding")
    assert page.locator(".oa-term-why").count() == 0
    page.click("#mount [data-smq='96000001'][data-scope='broad']")
    got = page.evaluate("window.picks")
    assert got == [{"kind": "smq", "code": "96000001", "name": got[0]["name"], "scope": "broad"}]
    assert "bleeding" in got[0]["name"].lower()
    page.context.close()


@pytest.mark.parametrize("width", WIDTHS)
def test_without_meddra_the_reason_shows_in_place_and_no_smq_is_offered(
    chromium, plain_host, width
):
    page = mounted(chromium, plain_host, width, licensed=False)
    before = page.evaluate(BOXES)
    page.fill("#mount input", "nau")
    page.wait_for_selector(".oa-term-why")
    settle(page)
    assert page.inner_text(".oa-term-why").strip()
    assert page.locator("#mount [data-smq]").count() == 0
    assert page.locator("#mount [role=tab]").all_inner_texts() == ["All", "PTs"]
    assert page.evaluate(BOXES) == before and page.evaluate(SIDEWAYS)
    page.click("#mount [data-pt='Nausea']")
    assert page.evaluate("window.picks") == [{"kind": "pt", "pt": "Nausea"}]
    page.context.close()


def test_the_products_given_are_the_ones_the_counts_are_asked_over(chromium, licensed_host):
    page = mounted(chromium, licensed_host, 320, licensed=True, products="?p=ASPIRIN&p=VALSARTAN")
    asked: list[str] = []
    page.on("request", lambda r: asked.append(r.url) if "/api/terms" in r.url else None)
    type_in(page, "nau")
    assert asked and "dprod=ASPIRIN" in asked[-1] and "dprod=VALSARTAN" in asked[-1]
    page.context.close()
