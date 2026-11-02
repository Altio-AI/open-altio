"""Sorting by a column title, in a browser, the same in every sortable table: the first press puts
the highest first (a name A to Z), the second the lowest first, the third the table's own order
again, every chevron neutral; and nothing on the page moves. The case list's own order is newest
first. On a phone the case list is cards, sorted by one choice above them, so its titles are
pressed at a tablet's width and a desktop's."""

from __future__ import annotations

from typing import Any

import pytest

from open_altio.testing.browser import settle

# each sortable title's chevron state, by the column it sorts
MARKS = """(sel) => Object.fromEntries([...document.querySelectorAll(sel)]
  .map((b) => [b.dataset.v || b.dataset.col, b.querySelector('.oa-sort').dataset.sort]))"""
# each head's box within its table, so a frame scrolled to bring a title into view does not count
BOXES = """(sel) => [...document.querySelectorAll(sel)].map((h) => {
  const b = h.getBoundingClientRect(), t = h.closest('table').getBoundingClientRect();
  return [b.x - t.x, b.y - t.y, b.width, b.height].map(Math.round);
})"""


def press(page: Any, selector: str) -> None:
    page.click(selector)
    settle(page)


def ages(page: Any) -> list[str]:
    """Each row's age as the list shows it, in order: the third cell."""
    return page.eval_on_selector_all(
        ".oa-cases tbody tr td:nth-child(3)", "cs => cs.map((c) => c.innerText.trim())"
    )


def years(shown: str) -> float:
    return float(shown.split()[0]) / 12 if shown.endswith("mo") else float(shown)


@pytest.mark.parametrize("width", [1024, 1440])
def test_a_case_list_title_sorts_highest_then_lowest_then_the_lists_own_order(opened, width):
    page = opened("/all/cases", width=width)
    titles = '.oa-cases thead [data-act="sort"]'
    own = ages(page)
    assert set(page.evaluate(MARKS, titles).values()) == {"none"}
    heads = page.evaluate(BOXES, ".oa-cases thead th")
    for mark in ("desc", "asc", "none"):
        press(page, f'{titles}[data-col="age"]')
        marks = page.evaluate(MARKS, titles)
        assert marks.pop("age") == mark and set(marks.values()) == {"none"}
        given = [years(a) for a in ages(page) if a]
        if mark != "none":
            assert given == sorted(given, reverse=mark == "desc"), mark
        assert page.evaluate(BOXES, ".oa-cases thead th") == heads  # nothing moves
    assert ages(page) == own
