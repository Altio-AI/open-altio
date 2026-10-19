"""Request this label: beside a drug with no label found, a quiet link that opens Improve this with
the request written and the spot named. Over the fake labelled release, with a copy's outbox."""

from __future__ import annotations

import pytest

from open_altio.explorer.app import create_app
from open_altio.explorer.outbox import Outbox
from open_altio.testing.browser import open_page, served, settle

ASK = "Please add the FDA label for BLEOMYCIN SULFATE. DailyMed link, if you have it: "


@pytest.fixture(scope="module")
def base(labelled_release, tmp_path_factory):
    outbox = Outbox(tmp_path_factory.mktemp("data"), "http://127.0.0.1:9/api/notes/local")
    with served(create_app(labelled_release, outbox=outbox)) as url:
        yield url


def open_case(page, key):
    page.goto(page.url.split("/all")[0].rstrip("/") + "/all/cases")
    settle(page)
    keys = page.eval_on_selector_all(
        'tr[data-act="case"] .case-key', "es => es.map((e) => e.innerText)"
    )
    page.query_selector_all('tr[data-act="case"]')[keys.index(key)].click()
    page.wait_for_selector("#oa-case .oa-case-lead")
    settle(page)


def test_the_link_shows_only_where_no_label_was_found_and_opens_improve_this_filled_in(
    chromium, base
):
    page = open_page(chromium, base + "/")
    open_case(page, "5100010")
    links = page.locator("#oa-case .oa-request-label")
    assert links.count() == 1 and links.inner_text() == "Request this label"
    links.click()
    assert page.input_value("#oa-note-text") == ASK
    assert page.evaluate("() => document.activeElement.id") == "oa-note-text"
    assert page.evaluate("() => document.activeElement.selectionStart") == len(ASK)
    assert page.inner_text(".oa-note-tag strong") == "Label for BLEOMYCIN SULFATE"
    page.context.close()
    # a case whose drugs all have labels shows no link
    page = open_page(chromium, base + "/")
    open_case(page, "9021021")
    assert page.locator(".oa-request-label").count() == 0
    page.context.close()


def test_a_drugs_page_without_a_label_offers_it_in_its_lead(chromium, base):
    page = open_page(chromium, base + "/product/BLEOMYCIN%20SULFATE/statistics")
    settle(page)
    assert page.locator(".oa-label-lead .oa-request-label").count() == 1
    page.click(".oa-label-lead .oa-request-label")
    assert page.input_value("#oa-note-text") == ASK
    page.context.close()
    page = open_page(chromium, base + "/product/acetylsalicylic%20acid/statistics")
    settle(page)
    assert page.locator(".oa-request-label").count() == 0
    page.context.close()


@pytest.mark.parametrize("width", [320, 768, 1024, 1440])
def test_the_link_shows_opens_and_moves_nothing_at_every_width(chromium, base, width):
    page = open_page(chromium, base + "/", width=width)
    open_case(page, "5100010")
    box = """() => [...document.querySelectorAll('#oa-case .oa-label-sources, .case-section')]
      .map((e) => Math.round(e.getBoundingClientRect().top))"""
    link = page.locator(".oa-request-label")
    r = link.bounding_box()
    assert r["x"] >= 0 and r["x"] + r["width"] <= width
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    before = page.evaluate(box)
    link.hover()
    assert page.evaluate(box) == before
    link.click()
    assert page.input_value("#oa-note-text") == ASK
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    dialog = page.locator(".oa-note-dialog").bounding_box()
    assert dialog["x"] >= 0 and dialog["x"] + dialog["width"] <= width
    page.context.close()
