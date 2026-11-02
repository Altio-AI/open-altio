"""Home's updates in a browser (ui/updates.js). The band under the greeting says the newest update
on the first visit after it, not on later ones, and its close hides it at once; a newer update
brings it back once. The release card always says the newest; from two updates on, its All
updates, and the band's, open the history, newest first, its first few showing (rule
explorer-lists' updates_shown) and the older ones scrolling inside the menu."""

from __future__ import annotations

from typing import Any

import pytest

from open_altio.explorer.pages import UI
from open_altio.rulebook import value
from open_altio.testing.browser import settle

SHOWN = value("explorer-lists", "updates_shown")
BAND = "#oa-update"
WORDS = "#oa-update .oa-update-words"
LATEST = ".oa-release-card .oa-update-latest"
ALL = '.oa-release-card [data-act="updates"]'
MENU = ".menu.oa-updates:popover-open"
BOXES = """() => ['.greeting', '.oa-find', '#oa-home-products'].map((s) => {
  const r = document.querySelector(s).getBoundingClientRect();
  return [Math.round(r.top), Math.round(r.height)];
})"""


def updates(text: str | None = None) -> list[tuple[str, str, str]]:
    """Each update: its day, the band's short line and the history's full line."""
    text = (UI / "updates.txt").read_text(encoding="utf-8") if text is None else text
    parts = [
        (line[:10], *line[11:].split(" | ")) for line in text.splitlines() if line[:1].isdigit()
    ]
    return [(day, short.strip(), full.strip()) for day, short, full in parts]


FILE = (UI / "updates.txt").read_text(encoding="utf-8")
NEWER = "2027-01-04 A newer update. | The full line of a newer update.\n" + FILE
# a history longer than the menu shows, newest first
MANY = "\n".join(
    f"2026-{12 - n // 28:02d}-{28 - n % 28:02d} Update {n + 1}. | The full line of update {n + 1}."
    for n in range(15)
)


def serving(page: Any, text: str) -> Any:
    """The page again, with `text` in place of the updates file; what the browser keeps stays."""
    page.route(
        "**/ui/updates.txt", lambda route: route.fulfill(body=text, content_type="text/plain")
    )
    page.reload()
    page.wait_for_selector(LATEST)
    settle(page)
    return page


def home(opened: Any, width: int = 1440) -> Any:
    page = opened("/", width=width)
    page.wait_for_selector(LATEST)
    settle(page)
    return page


def test_the_updates_file_is_dated_newest_first_each_with_a_short_and_a_full_line():
    days = [day for day, _, _ in updates()]
    assert days and days == sorted(days, reverse=True)
    assert all(short.endswith(".") and full.endswith(".") for _, short, full in updates())


@pytest.mark.parametrize("width", [390, 1024, 1440, 2200])
def test_the_first_visit_shows_the_newest_in_a_band_and_the_next_does_not(opened, width: int):
    page = home(opened, width)
    assert page.inner_text(WORDS) == updates()[0][1]
    assert page.locator(WORDS).evaluate("(el) => el.scrollWidth <= el.clientWidth")  # none cut
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    band, find = (
        page.locator(BAND).bounding_box(),
        page.locator(".oa-find .search-bar").bounding_box(),
    )
    assert round(find["y"] - band["y"] - band["height"]) == 16  # the search close under the band
    with_band = page.evaluate(BOXES)
    page.reload()
    page.wait_for_selector(LATEST)
    settle(page)
    assert page.locator(BAND).count() == 0  # a later visit: no band
    without = page.evaluate(BOXES)
    assert without[0] == with_band[0]  # the greeting stays
    assert without[1][0] < with_band[1][0]  # the band's room is gone with it
    assert page.inner_text(LATEST) == f"Latest update: {updates()[0][1]}"


def test_one_update_has_nothing_to_open(opened):
    assert len(updates()) == 1  # this test's premise: change it once a second update is written
    page = home(opened)
    assert page.locator(f"{BAND} [data-act='updates'], {BAND} .oa-update-all").count() == 0
    page.click(WORDS)
    assert page.locator(MENU).count() == 0
    assert page.locator(ALL).count() == 0  # the release card says it, with nothing to open


def test_the_close_hides_the_band_at_once_and_for_later_visits(opened):
    page = home(opened)
    before = page.evaluate(BOXES)
    page.click(f"{BAND} [data-act='update-hide']")
    assert page.locator(BAND).count() == 0
    after = page.evaluate(BOXES)
    assert after[0] == before[0] and after[1][0] < before[1][0]  # the band's room goes with it
    page.reload()
    page.wait_for_selector(LATEST)
    assert page.locator(BAND).count() == 0


def test_a_newer_update_brings_the_band_back_once(opened):
    page = home(opened)
    page.reload()
    page.wait_for_selector(LATEST)
    assert page.locator(BAND).count() == 0
    serving(page, NEWER)
    assert page.inner_text(WORDS) == "A newer update."
    assert page.inner_text(LATEST) == "Latest update: A newer update."
    page.reload()
    page.wait_for_selector(LATEST)
    assert page.locator(BAND).count() == 0


@pytest.mark.parametrize("width", [390, 1440])
def test_many_updates_open_newest_first_in_a_menu_that_scrolls_inside_itself(opened, width: int):
    page = serving(opened("/", width=width), MANY)
    assert page.inner_text(WORDS) == "Update 1."
    # a phone has the chevron alone at the band's end; wider screens say All updates too
    assert page.locator(f"{BAND} .oa-update-all .icon").is_visible()
    assert page.locator(f"{BAND} .oa-update-all-words").is_visible() == (width >= 768)
    for opener in (ALL, f"{BAND} [data-act='updates']"):
        page.locator(opener).scroll_into_view_if_needed()
        page.click(opener)
        menu = page.locator(MENU)
        rows = menu.locator(".oa-update-row")
        assert [rows.nth(i).locator("span").nth(1).inner_text() for i in range(rows.count())] == [
            full for _, _, full in updates(MANY)
        ]
        box = menu.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width and box["y"] >= 0
        assert box["y"] + box["height"] <= page.evaluate("innerHeight")
        shown = SHOWN
        edge = rows.nth(shown - 1).bounding_box()
        assert abs(edge["y"] + edge["height"] - (box["y"] + box["height"])) <= 12
        assert rows.nth(shown).bounding_box()["y"] >= box["y"] + box["height"] - 8  # under the fold
        rows.last.scroll_into_view_if_needed()
        assert rows.last.is_visible() and menu.evaluate("(m) => m.scrollTop > 0")
        page.keyboard.press("Escape")
        assert menu.count() == 0
