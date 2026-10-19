"""Improve this on a copy, in a browser (ui/outbox.js), against a fake of Altio's service.

The page keeps each note in the copy's outbox, sends it from the browser straight to the service
and crosses it off. Offline, or while the service does not answer, the note waits and goes when
the browser is back online or a page opens. A refusal is shown and nothing is kept. A setting
hides the button. Skipped where Playwright's headless Chromium is not installed (`chromium`).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request, Response

from open_altio.explorer.app import create_app
from open_altio.explorer.outbox import Outbox
from open_altio.testing.browser import open_page, served

WHAT_GOES = {"id", "text", "page", "route", "part", "where", "email"}
WORDS = "It would help to see how many groups the age guard skipped."
# A test says when the browser thinks it is offline, while the explorer on 127.0.0.1 still
# answers, as it does on a laptop with no connection.
OFFLINE_SWITCH = (
    "Object.defineProperty(navigator, 'onLine', { get: () => !window.offlineForTest });"
)


class FakeService:
    """Altio's service as a copy's page meets it: notes from a page on 127.0.0.1 only, answered
    as the test says."""

    def __init__(self) -> None:
        self.kept: list[dict] = []
        self.heard: list[dict[str, str]] = []  # each post's headers
        self.status, self.problem = 201, ""
        self.app = FastAPI()

        def readable(request: Request, response: Response) -> Response:
            if request.headers.get("origin", "").startswith("http://127.0.0.1:"):
                response.headers["Access-Control-Allow-Origin"] = request.headers["origin"]
            return response

        @self.app.options("/api/notes/local")
        def asked(request: Request) -> Response:
            response = readable(request, Response(status_code=204))
            response.headers["Access-Control-Allow-Methods"] = "POST"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response

        @self.app.post("/api/notes/local")
        async def note(request: Request) -> Response:
            self.heard.append(dict(request.headers))
            if self.status >= 400:
                return readable(
                    request,
                    Response(
                        f'{{"problem": "{self.problem}"}}',
                        self.status,
                        media_type="application/json",
                    ),
                )
            body = await request.json()
            if body["id"] not in {n["id"] for n in self.kept}:
                self.kept.append(body)
            return readable(
                request, Response('{"kept": true}', self.status, media_type="application/json")
            )


@pytest.fixture
def fake() -> Iterator[tuple[FakeService, str]]:
    service = FakeService()
    with served(service.app) as url:
        yield service, url


@pytest.fixture
def copy(tmp_path, release, fake):
    """The explorer as `open-altio serve` runs it, its outbox sending to the fake service."""
    _, url = fake
    outbox = Outbox(tmp_path / "data", f"{url}/api/notes/local")
    with served(create_app(release, outbox=outbox)) as page_url:
        yield page_url, outbox


@pytest.fixture
def page(chromium, copy):
    tab = open_page(chromium, copy[0] + "/")
    tab.context.add_init_script(OFFLINE_SWITCH)
    tab.evaluate(OFFLINE_SWITCH)
    yield tab
    tab.context.close()


def write_note(page, email: str = "") -> None:
    page.locator(".oa-improve").first.click()
    page.fill("#oa-note-text", WORDS)
    page.fill("#oa-note-email", email)
    page.get_by_role("button", name="Submit improvement").click()


def sent_and_crossed_off(page, service: FakeService, outbox: Outbox) -> None:
    """Wait, up to ten seconds, until the service has every note and the outbox is empty."""
    for _ in range(200):
        if service.kept and outbox.waiting() == []:
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"still waiting: {outbox.waiting()}")


def toast(page) -> str:
    return page.locator(".oa-toast").last.inner_text()


def test_a_note_goes_straight_to_altio_holding_only_what_the_dialog_says(page, fake, copy):
    service, _ = fake
    page_url, outbox = copy
    page.locator(".oa-improve").first.click()
    dialog = page.locator(".oa-note-dialog")
    assert "What was confusing, slow or missing here? *" in dialog.inner_text()
    assert "Your email, if you want to hear back optional" in dialog.inner_text()
    assert dialog.locator(".oa-note-privacy").inner_text() == (
        "We send only your words, the page you're on, the part you pointed at "
        "and your email if you give one. "
        "Nothing else."
    )
    assert dialog.locator(".oa-note-offline").count() == 0
    page.keyboard.press("Escape")
    write_note(page, "jane@example.org")
    page.wait_for_function("document.querySelector('.oa-toast')")
    assert toast(page) == "Noted. We'll email you once we've looked at it."
    [note] = service.kept
    assert set(note) == WHAT_GOES and note["text"] == WORDS and note["email"] == "jane@example.org"
    assert note["page"] == "Home" and note["route"] == "/"
    [heard] = service.heard
    assert heard["origin"] == page_url and "cookie" not in heard and "referer" not in heard
    assert outbox.waiting() == []


def test_a_note_from_a_drug_page_names_it_by_its_title_alone(chromium, fake, copy):
    """The spellings button inside a drug page's title is not part of the page's name."""
    service, _ = fake
    tab = open_page(chromium, copy[0] + "/product/valsartan/overview")
    tab.wait_for_selector(".oa-title-spellings")
    write_note(tab)
    sent_and_crossed_off(tab, service, copy[1])
    tab.context.close()
    [note] = service.kept
    assert note["page"] == "Valsartan"


def test_an_email_given_once_is_filled_in_next_time_in_this_browser(page, fake):
    write_note(page, "jane@example.org")
    page.wait_for_function("document.querySelector('.oa-toast')")
    page.reload()
    page.locator(".oa-improve").first.click()
    assert page.input_value("#oa-note-email") == "jane@example.org"


def test_offline_the_dialog_says_so_and_the_note_goes_once_back_online(page, fake, copy):
    service, url = fake
    _, outbox = copy
    page.route(f"{url}/**", lambda route: route.abort("internetdisconnected"))
    page.evaluate("window.offlineForTest = true")
    page.locator(".oa-improve").first.click()
    assert page.locator(".oa-note-offline").inner_text() == (
        "You're offline. Your note waits on this computer and is sent when you're back online."
    )
    page.keyboard.press("Escape")
    write_note(page)
    page.wait_for_function("document.querySelector('.oa-toast')")
    assert toast(page) == "Queued. It will send when you're back online."
    assert [n["text"] for n in outbox.waiting()] == [WORDS] and service.kept == []
    page.unroute(f"{url}/**")
    page.evaluate("window.offlineForTest = false; window.dispatchEvent(new Event('online'))")
    sent_and_crossed_off(page, service, outbox)
    assert [n["text"] for n in service.kept] == [WORDS]


def test_a_note_altio_did_not_answer_goes_when_a_page_next_opens(page, fake, copy):
    service, _ = fake
    _, outbox = copy
    service.status = 503
    write_note(page)
    page.wait_for_function("document.querySelector('.oa-toast')")
    assert toast(page) == "Queued. Altio did not answer, so it will send later."
    [waiting] = outbox.waiting()
    service.status = 201
    page.reload()
    sent_and_crossed_off(page, service, outbox)
    assert [n["id"] for n in service.kept] == [waiting["id"]]


def test_a_refusal_is_shown_the_text_stays_and_nothing_waits(page, fake, copy):
    service, _ = fake
    _, outbox = copy
    service.status, service.problem = (
        429,
        "Open Altio takes up to 3 notes a day from one connection.",
    )
    write_note(page)
    page.wait_for_function("document.querySelector('.oa-toast')")
    assert toast(page) == service.problem
    assert (
        page.locator(".oa-note-dialog").is_visible() and page.input_value("#oa-note-text") == WORDS
    )
    assert outbox.waiting() == [] and service.kept == []


def test_settings_hide_the_button_in_this_browser(page):
    page.locator("[data-act=settings]").first.click()
    page.locator('[data-act="improve-button"][data-v="hide"]').click()
    assert page.locator(".oa-improve").first.is_hidden()
    page.reload()
    page.locator("#app").wait_for()
    page.wait_for_function("document.querySelector('.frame-page, .product-page, main')")
    assert page.locator(".oa-improve").count() == 0
    page.locator("[data-act=settings]").first.click()
    page.locator('[data-act="improve-button"][data-v="show"]').click()
    assert page.locator(".oa-improve").first.is_visible()


def test_a_copy_asks_nobody_but_itself_for_anything_but_a_note_sent(chromium, fake, copy):
    """Screens, tabs, rules, a search and its pick and Improve this opened go nowhere: the
    copy's page asks only the copy, until the person presses Send on a note."""
    service, altio = fake
    page_url, outbox = copy
    context = chromium.new_context()
    asked: list[str] = []
    context.on("request", lambda r: asked.append(r.url))
    tab = context.new_page()
    tab.goto(page_url + "/")
    tab.fill("#oa-find", "valsar")
    tab.click('#oa-find-results a[href="/product/valsartan/overview"]')
    tab.wait_for_selector(".oa-title-spellings")
    for path in ("/product/valsartan/cases", "/all/overview", "/methods"):
        tab.evaluate("(path) => import('/ui/router.js').then((m) => m.go(path))", path)
        tab.wait_for_function("(path) => location.pathname + location.search === path", arg=path)
    tab.locator(".oa-improve").first.click()
    tab.keyboard.press("Escape")
    tab.wait_for_timeout(300)
    assert asked and all(url.startswith(page_url + "/") for url in asked)
    write_note(tab)
    sent_and_crossed_off(tab, service, outbox)
    context.close()
    elsewhere = [url for url in asked if not url.startswith(page_url + "/")]
    assert elsewhere and set(elsewhere) == {f"{altio}/api/notes/local"}
    assert len(service.kept) == 1
