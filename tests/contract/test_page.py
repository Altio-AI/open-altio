"""The page's extension points (docs/reference/page-extension.md): `extend()` takes only the keys in
`EXTEND_KEYS` and a host draws only in the places in `SLOTS`, each refusal thrown at once; a
place in the side panel and its rail names itself by its address; `brand` names the product and
`kept` keeps a person's view choices on a host's server; and no word of a product's own workflow
is anywhere on the public page."""

from __future__ import annotations

import re
from pathlib import Path

from open_altio.explorer import access

UI = Path(access.__file__).resolve().parent / "ui"
DOCS = Path(__file__).resolve().parents[2] / "docs" / "reference" / "page-extension.md"
# the words of one product's workflow, which no public slot, hook or text may name
WORKFLOW_WORDS = ("assessment", "committee", "priority", "potential signal")


def listed(name: str) -> list[str]:
    """The names in one of host.js's exported lists."""
    found = re.search(rf"export const {name} = \[([^\]]*)\]", (UI / "host.js").read_text())
    assert found, name
    return re.findall(r"'([^']+)'", found.group(1))


def exported() -> list[str]:
    """Every name app.js exports, the list a page module may import."""
    text = (UI / "app.js").read_text(encoding="utf-8")
    groups = re.findall(r"export \{([^}]*)\}", text)
    return [name.strip() for group in groups for name in group.split(",")]


def scripts() -> dict[str, str]:
    return {p.relative_to(UI).as_posix(): p.read_text(encoding="utf-8") for p in UI.rglob("*.js")}


def thrown(page, code: str) -> str | None:
    """The message `code` throws in the page, with app.js as `app` and host.js as `host`."""
    return page.evaluate(f"""async () => {{
      const app = await import('/ui/app.js'), host = await import('/ui/host.js');
      try {{ {code}; return null; }} catch (e) {{ return e.message; }}
    }}""")


# the closed lists ---------------------------------------------------------------------------------


def test_extend_throws_for_a_key_or_a_slot_it_does_not_take_and_changes_nothing(opened, site):
    page = opened(site + "/")
    assert thrown(page, "app.extend({ unknownKey: 1 })") == 'extend() takes no key "unknownKey"'
    assert thrown(page, "app.extend({ brand: 'B', keepSide: 1 })") == (
        'extend() takes no key "keepSide"'
    )
    assert thrown(page, "app.extend({ slots: { nowhere: () => 'x' } })") == (
        'extend() takes no slot "nowhere"'
    )
    assert page.evaluate("async () => (await import('/ui/host.js')).host.brand") == "Open Altio"
    assert page.evaluate("async () => (await import('/ui/app.js')).EXTEND_KEYS") == listed(
        "EXTEND_KEYS"
    )
    assert page.evaluate("async () => (await import('/ui/app.js')).SLOTS") == listed("SLOTS")


def test_slot_throws_for_a_place_not_listed(opened, site):
    page = opened(site + "/")
    assert thrown(page, "host.slot('nowhere')") == 'slot() takes no slot "nowhere"'
    assert thrown(page, "host.slot('side-places', 'home')") is None


def test_every_place_the_page_draws_a_slot_in_is_listed_and_every_listed_place_is_drawn():
    drawn = {name for text in scripts().values() for name in re.findall(r"\bslot\('([^']+)'", text)}
    assert drawn == set(listed("SLOTS"))


def test_the_new_keys_are_listed():
    assert {"brand", "kept"} <= set(listed("EXTEND_KEYS"))
    assert "keepSide" not in listed("EXTEND_KEYS")  # kept holds the side panel's fold


def test_the_page_extension_page_lists_every_key_place_and_export():
    page = re.sub(r"```.*?```", "", DOCS.read_text(encoding="utf-8"), flags=re.S)
    named = {re.match(r"[\w-]*", code).group(0) for code in re.findall(r"`([^`]+)`", page)}
    for name in (*listed("EXTEND_KEYS"), *listed("SLOTS"), *exported()):
        assert name in named, name


def test_no_text_of_the_public_page_names_a_products_workflow():
    for path in UI.rglob("*"):
        if path.is_file() and path.suffix in (".js", ".html", ".css"):
            text = path.read_text(encoding="utf-8").lower()
            for word in WORKFLOW_WORDS:
                assert word not in text, (path.relative_to(UI).as_posix(), word)


# a place names itself by its address --------------------------------------------------------------

PLACES_JS = """
import { extend, railPlace, sidePlace } from '/ui/app.js';
extend({ slots: {
  'side-places': (here) => sidePlace('/acme', 'admin', 'Acme', here === 'acme'),
  'rail-places': (here) => railPlace('/acme', 'admin', 'Acme', here === 'acme'),
} });
"""
PLACES = "(sel) => [...document.querySelectorAll(sel)].map((el) => el.dataset.place)"


def test_each_place_in_the_side_panel_and_its_rail_is_named_by_its_address(opened, hosted):
    page = opened(hosted(PLACES_JS) + "/")
    own = ["/", "/all/overview", "/release", "/methods", "/acme"]
    assert page.evaluate(PLACES, ".side-panel [data-place]") == own
    assert page.evaluate(PLACES, ".oa-rail [data-place]") == own


# the product's name -------------------------------------------------------------------------------

BRANDS = """() => ({
  title: document.title,
  names: [...document.querySelectorAll('.brand-name')].map((el) => el.textContent),
  home: [...document.querySelectorAll('.brand-home')].map((el) => el.getAttribute('aria-label')),
  rail: document.querySelector('.oa-rail')?.getAttribute('aria-label'),
})"""


def test_the_frame_and_the_title_name_open_altio_by_default(opened, site):
    seen = opened(site + "/").evaluate(BRANDS)
    assert seen["title"] == "Open Altio" and seen["rail"] == "Open Altio"
    assert seen["names"] == ["Open Altio", "Open Altio"]
    assert seen["home"] == ["Open Altio, home", "Open Altio, home"]


def test_a_hosts_brand_names_the_frame_the_title_and_the_methods_page(opened, hosted):
    base = hosted("import { extend } from '/ui/app.js'; extend({ brand: 'Acme Safety' });")
    seen = opened(base + "/").evaluate(BRANDS)
    assert seen["title"] == "Acme Safety" and seen["rail"] == "Acme Safety"
    assert seen["names"] == ["Acme Safety", "Acme Safety"]
    assert seen["home"] == ["Acme Safety, home", "Acme Safety, home"]
    methods = opened(base + "/methods").evaluate(BRANDS)
    assert methods["title"] == "Acme Safety" and set(methods["names"]) == {"Acme Safety"}


# a person's view choices --------------------------------------------------------------------------

KEPT_JS = """
import { extend } from '/ui/app.js';
window.saved = [];
extend({ kept: {
  load: async () => (%s),
  save: async (key, value) => { window.saved.push([key, value]); },
} });
"""
SIDE = "() => document.querySelector('.frame').dataset.sidePanelState"
IN_BROWSER = "() => localStorage.getItem('open-altio.side')"


def test_a_hosts_kept_choices_are_read_and_saved_in_place_of_the_browsers(opened, hosted):
    page = opened(hosted(KEPT_JS % "{ side: 'closed' }") + "/", kept={"side": "open"})
    assert page.evaluate(SIDE) == "closed"  # the host's choice, not this browser's
    page.click('.oa-rail [data-act="side-open"]')
    page.click(".side-panel .side-collapse")
    assert page.evaluate("window.saved") == [["side", "open"], ["side", "closed"]]
    assert page.evaluate(IN_BROWSER) == '"open"'  # this browser's left as it was


def test_a_host_that_cannot_give_its_kept_choices_leaves_each_at_its_default(opened, hosted):
    base = hosted(KEPT_JS % "(() => { throw new Error('signed out'); })()")
    page = opened(base + "/", width=1440, kept={"side": "closed"})
    assert page.evaluate(SIDE) == "open"  # open from 1440 until a choice is made


def test_without_a_host_the_choices_are_kept_in_this_browser(opened, site):
    page = opened(site + "/", width=1440, kept={"side": "closed"})
    assert page.evaluate(SIDE) == "closed"
    page.click('.oa-rail [data-act="side-open"]')
    assert page.evaluate(IN_BROWSER) == '"open"'


# what the page reports ----------------------------------------------------------------------------

REPORT_JS = """
import { extend } from '/ui/app.js';
window.reported = [];
extend({ report: (kind) => window.reported.push(kind) });
"""


def test_the_page_reports_only_the_listed_kinds(opened, hosted):
    page = opened(hosted(REPORT_JS) + "/")
    assert page.evaluate("window.reported") == ["screen"]
    sent = "host.report('downloaded_tables', {}); host.report('rule', { rule: 'x' })"
    assert thrown(page, sent) is None
    assert page.evaluate("window.reported") == ["screen", "rule"]
    assert listed("REPORTED") == list(access.REPORTED)


# the query builder's words ------------------------------------------------------------------------

QUERIES_JS = """
import { extend } from '/ui/app.js';
extend({ queries: {
  group: '',
  save: async (q) => ({ ...q, id: 'k1', mine: true }),
  remove: async () => ({}),
  words: {
    intro: 'Kept in the Zed settings.',
    save: 'Keep it',
    saved: (q) => `Zed keeps ${q.name} with ${q.terms.length} terms.`,
  },
} });
"""


def build_a_query(page) -> None:
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu .oa-filter-row[data-row="reactions"]')
    page.click('#oa-filter-menu [data-act="cmq-new"]')
    page.fill("#oa-cmq-name", "Head")
    page.fill("#oa-cmq-find", "Headache")
    page.click('#oa-cmq-found [data-act="cmq-term"][data-v="Headache"]')


def test_a_hosts_words_show_in_the_query_builders_intro_button_and_saved_line(opened, hosted):
    page = opened(hosted(QUERIES_JS) + "/all/overview")
    build_a_query(page)
    dialog = page.locator(".oa-cmq-dialog")
    assert "Kept in the Zed settings." in dialog.inner_text()
    assert "in your account" not in dialog.inner_text()
    assert dialog.locator('[data-act="cmq-save"]').inner_text() == "Keep it"
    page.click('[data-act="cmq-save"]')
    page.wait_for_selector(".oa-cmq-dialog", state="detached")
    assert "Zed keeps Head with 1 terms." in page.inner_text("body")
    assert "chosen under Reactions" not in page.inner_text("body")


def test_without_a_hosts_words_the_query_builder_says_what_it_always_said(opened, site):
    page = opened(site + "/all/overview")
    build_a_query(page)
    dialog = page.locator(".oa-cmq-dialog")
    assert "kept for you" in dialog.inner_text()
    assert dialog.locator('[data-act="cmq-save"]').inner_text() == "Save and run"
    page.click('[data-act="cmq-save"]')
    page.wait_for_selector(".oa-cmq-dialog", state="detached")
    assert "CMQ Head: 1 terms, chosen under Reactions." in page.inner_text("body")
