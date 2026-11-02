"""A pair's cases in a browser, over the release whose EBGM prior fits (`stats_site`): a product's
Cases tab narrowed to one reaction shows the pair's ROR by age band and by sex under the list, at a
phone's width and a wider one. The shots go to OPEN_ALTIO_STATISTICS_SHOTS when it names a
folder."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import pytest

from open_altio.testing.browser import settle

SHOTS = os.environ.get("OPEN_ALTIO_STATISTICS_SHOTS")


def cells(page, selector: str) -> list[list[str]]:
    return page.eval_on_selector_all(
        selector, "rs => rs.map((r) => [...r.cells].map((c) => c.innerText.trim()))"
    )


@pytest.mark.parametrize("width", [390, 1440])
def test_a_pairs_cases_show_its_ror_by_age_band_and_by_sex_under_them(
    opened, stats_site, stats_client, width
):
    got = stats_client.get("/api/statistics?ingredient=warfarin&pass=").json()["rows"][0]
    term = got["term"]
    page = opened(f"/product/warfarin/cases?reaction={quote(term)}", base=stats_site, width=width)
    page.wait_for_selector(".oa-strata")
    settle(page)
    want = stats_client.get(
        f"/api/statistics/strata?ingredient=warfarin&reaction={quote(term)}"
    ).json()
    block = page.locator(".oa-strata")
    assert "ror by age band and by sex" in block.inner_text().lower()
    assert f"on the {want['cases']} cases" in block.inner_text()
    shown = [cells(page, f".oa-strata-table:nth-of-type({k}) tbody tr") for k in (1, 2)]
    for part, rows in zip(want["parts"], shown, strict=True):
        assert [int(r[1]) for r in rows] == [s["cases"] for s in part["strata"]]
        assert all(
            r[2] == "" for r, s in zip(rows, part["strata"], strict=True) if s["ror"] is None
        )
    assert rule_link(page) == "/methods?open=ror-strata"
    # the pager stays where the list put it: the block is under it
    pager = page.locator(".oa-pager").bounding_box()
    assert block.bounding_box()["y"] >= pager["y"] + pager["height"]
    inside = """(b) => [...b.querySelectorAll('table')].every((t) =>
        t.getBoundingClientRect().right <= b.getBoundingClientRect().right + 1)"""
    assert block.evaluate(inside)  # each table whole inside the block, none cut at the edge
    heights = block.evaluate(
        "(b) => [...b.querySelectorAll('tbody tr')].map((r) => r.getBoundingClientRect().height)"
    )
    assert max(heights) < 2 * min(heights)  # side by side, the shorter table is not stretched
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if SHOTS:
        block.screenshot(path=str(Path(SHOTS) / f"strata-warfarin-{width}.png"))


def rule_link(page) -> str:
    return page.get_attribute(".oa-strata a.oa-rule-tag", "href")


def test_a_case_list_of_more_than_one_reaction_shows_no_ratios(opened, stats_site):
    page = opened("/product/warfarin/cases", base=stats_site)
    assert page.locator(".oa-strata").count() == 0
