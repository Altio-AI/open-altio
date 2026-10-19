"""The Statistics tab in a browser, over the release whose EBGM prior fits (`stats_site`): the
default screen, a person's own numbers, a product's pairs, each pair's time to onset, and a
pair's cases with its ROR by age band and by sex under them, at a phone's width and two wider;
a combination's tab, which sends to each of its ingredients' own; and the table's fit: whole on a
laptop's screen, and on a phone scrolling sideways with its first column held. The shots go to
OPEN_ALTIO_STATISTICS_SHOTS when it names a folder."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from open_altio.rulebook import value
from open_altio.testing.browser import first_column_held, settle

SHOTS = os.environ.get("OPEN_ALTIO_STATISTICS_SHOTS")


def numbers(page, column: int) -> list[float]:
    """The figures of one column of the table, the first figure of each cell."""
    cells = page.eval_on_selector_all(
        f".oa-stats tbody tr td:nth-of-type({column})", "cs => cs.map((c) => c.innerText)"
    )
    return [float(c.split()[0].replace(",", "")) for c in cells]


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_the_release_wide_list_starts_on_every_pair_sorted_by_eb05_highest_first(
    opened, stats_site, stats_client, width
):
    page = opened("/all/statistics", base=stats_site, width=width)
    found = stats_client.get("/api/statistics?pass=").json()
    rows = page.locator(".oa-stats tbody tr")
    assert rows.count() == min(found["matched"], value("explorer-lists", "statistics_shown"))
    assert rows.count() > 0
    assert page.inner_text("#oa-countline").startswith(f"{found['matched']:,} pairs")
    # ingredient, then cases (2nd column of cells) and EB05 (5th): nothing is screened out
    assert any(n < 3 for n in numbers(page, 2)) or any(n < 2 for n in numbers(page, 5))
    assert numbers(page, 5) == sorted(numbers(page, 5), reverse=True)
    assert page.locator('.oa-stats tbody tr:first-child td[data-state="pass"]').count() >= 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert "How these are worked out" in page.inner_text("#oa-strip")
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"statistics-all-{width}.png"), full_page=True)


def test_an_old_kept_list_is_moved_to_every_pair_once_and_keeps_its_numbers(
    opened, stats_site, stats_client
):
    page = opened("/all/statistics", base=stats_site)
    every = stats_client.get("/api/statistics?pass=").json()["matched"]
    assert page.inner_text("#oa-countline").startswith(f"{every:,} pairs")
    key = "open-altio.statistics-screens"
    by = {"EBGM": {"preset": "own", "when": [{"column": "eb05", "at_least": 2.8}]}}
    page.evaluate(
        "([k, v]) => localStorage.setItem(k, JSON.stringify(v))", [key, {"list": "EBGM", "by": by}]
    )
    page.reload()
    settle(page)
    assert "Every drug and reaction" in page.inner_text("#oa-countline")
    kept = page.evaluate("(k) => JSON.parse(localStorage.getItem(k))", key)
    assert kept["by"] == by and kept.get("list") is None
    # the numbers are kept: choosing EBGM's list again narrows by them, not by the threshold
    page.click(".oa-screens-btn")
    page.click('[data-act="screen-list"][data-v="EBGM"]')
    settle(page)
    assert all(n >= 2.8 for n in numbers(page, 5))
    page.reload()  # a choice made after the move is not let go again
    settle(page)
    assert "Only those that pass EBGM" in page.inner_text("#oa-countline")


@pytest.mark.parametrize("width", [390, 1440])
def test_the_strip_says_the_filters_do_not_change_them_whole_at_every_width(
    opened, stats_site, width
):
    page = opened("/all/statistics", base=stats_site, width=width)
    strip = page.locator("#oa-strip").bounding_box()
    said = page.get_by_text("The filters do not change them").bounding_box()
    assert strip["x"] <= said["x"] and said["x"] + said["width"] <= strip["x"] + strip["width"]
    assert strip["y"] <= said["y"] and said["y"] + said["height"] <= strip["y"] + strip["height"]


def test_a_screen_of_ones_own_narrows_the_list_and_is_kept(opened, stats_site):
    page = opened("/all/statistics", base=stats_site)
    page.click(".oa-screens-btn")
    page.click('[data-act="screen-list"][data-v="EBGM"]')
    settle(page)
    before = page.locator(".oa-stats tbody tr").count()
    page.click('[data-act="screen-row"][data-row="EBGM"]')
    page.fill('.oa-screen-number input[data-i="0"]', "2.8")
    settle(page)
    assert page.get_attribute('[data-act="screen-preset"][data-v="own"]', "aria-checked") == "true"
    after = page.locator(".oa-stats tbody tr").count()
    assert 0 < after < before and all(n >= 2.8 for n in numbers(page, 5))
    page.reload()
    settle(page)
    assert page.locator(".oa-stats tbody tr").count() == after


def test_every_pair_shows_once_the_list_is_not_screened(opened, stats_site, stats_client):
    page = opened("/all/statistics", base=stats_site)
    page.click(".oa-screens-btn")
    page.click('[data-act="screen-list"][data-v="all"]')
    settle(page)
    every = stats_client.get("/api/statistics").json()["matched"]
    assert page.inner_text("#oa-countline").startswith(f"{every:,} pairs")
    assert page.locator(".oa-stats tbody tr").count() == min(
        every, value("explorer-lists", "statistics_shown")
    )


def test_a_products_tab_lists_its_own_pairs_and_a_row_opens_their_cases(opened, stats_site):
    page = opened("/product/warfarin/statistics", base=stats_site, width=1024)
    assert page.locator(".oa-stats thead th").first.inner_text().startswith("Reaction")
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / "statistics-warfarin-1024.png"), full_page=True)
    reaction = page.locator(".oa-stats tbody th").first.inner_text()
    page.locator(".oa-stats tbody tr").first.click()
    settle(page)
    assert page.url.endswith("/product/warfarin/cases")
    assert reaction.lower() in page.inner_text("#oa-strip").lower()


@pytest.mark.parametrize("width", [390, 1440])
def test_a_combinations_tab_sends_to_each_ingredients_own_with_nothing_of_its_page(opened, width):
    page = opened("/product/sacubitril%3Bvalsartan/overview", width=width)
    page.click('.oa-drugbar [data-act="prole"][data-v="C"]')
    page.click('.product-tab[href$="/statistics"]')
    settle(page)
    said = page.inner_text("#oa-body")
    assert said == "Statistics are worked out for each ingredient: sacubitril and valsartan."
    assert page.inner_text("#oa-countline") == ""
    links = page.eval_on_selector_all("#oa-body a", "as => as.map((a) => a.getAttribute('href'))")
    assert links == ["/product/sacubitril/statistics", "/product/valsartan/statistics"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.click('#oa-body a[href="/product/sacubitril/statistics"]')
    settle(page)
    assert page.url.endswith("/product/sacubitril/statistics")
    on = page.eval_on_selector_all(
        '.oa-roles .oa-choice[aria-checked="true"]', "bs => bs.map((b) => b.dataset.v)"
    )
    assert on == ["PS", "SS"]
    assert page.locator(".oa-stats").count() == 1


def cells(page, selector: str) -> list[list[str]]:
    return page.eval_on_selector_all(
        selector, "rs => rs.map((r) => [...r.cells].map((c) => c.innerText.trim()))"
    )


@pytest.mark.parametrize("width", [390, 1440])
def test_each_pair_shows_its_median_onset_and_the_drugs_it_rests_on(
    opened, stats_site, stats_client, width
):
    page = opened("/product/warfarin/statistics", base=stats_site, width=width)
    heads = page.eval_on_selector_all(".oa-stats thead th", "hs => hs.map((h) => h.innerText)")
    assert heads[-1].startswith("Onset")
    page.click('.oa-stats thead [data-v="onset_days"]')
    settle(page)
    got = stats_client.get(
        "/api/statistics?ingredient=warfarin&sort=onset_days&dir=desc&pass="
    ).json()["rows"][0]
    none = sum(v for k, v in got.items() if k.startswith("no_onset_"))
    shown = page.inner_text(".oa-stats tbody tr:first-child td:last-child").split()
    median = got["onset_days"]
    assert shown[0] == (f"{median:g}" if median == int(median) else f"{median:.1f}")
    assert shown[1] == ("day" if median == 1 else "days")
    assert shown[2:] == [str(got["onset_drugs"]), "of", str(got["onset_drugs"] + none), "drugs"]
    why = page.get_attribute(".oa-stats tbody tr:first-child td:last-child .oa-faint", "data-tip")
    assert why.startswith(f"{got['onset_drugs']} of the pair's")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [390, 1440])
def test_a_pairs_cases_show_its_ror_by_age_band_and_by_sex_under_them(
    opened, stats_site, stats_client, width
):
    page = opened("/product/warfarin/statistics", base=stats_site, width=width)
    term = page.locator(".oa-stats tbody tr").first.get_attribute("data-term")
    page.locator(".oa-stats tbody tr").first.click()
    settle(page)
    assert page.url.endswith("/product/warfarin/cases")
    want = stats_client.get(f"/api/statistics/strata?ingredient=warfarin&reaction={term}").json()
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


def test_a_median_onset_names_its_unit_one_day_or_many(opened, stats_site, stats_client):
    page = opened("/product/warfarin/statistics", base=stats_site)
    page.click('.oa-stats thead [data-v="onset_days"]')
    settle(page)
    got = stats_client.get(
        "/api/statistics?ingredient=warfarin&sort=onset_days&dir=desc&pass="
    ).json()["rows"]
    shown = page.eval_on_selector_all(
        ".oa-stats tbody tr td:last-child", "cs => cs.map((c) => c.innerText.split('\\n')[0])"
    )
    for row, said in zip(got, shown, strict=True):
        if row["onset_days"] is not None:
            assert said.endswith(" day" if row["onset_days"] == 1 else " days"), said


# the frame and its table: how wide each is, and whether any cell's words run past its edges
FIT = """() => {
  const t = document.querySelector('.oa-stats'), f = t.parentElement;
  const cut = [...t.querySelectorAll('th, td')].filter((c) => c.scrollWidth > c.clientWidth + 1);
  return { table: t.scrollWidth, frame: f.clientWidth, cut: cut.map((c) => c.innerText) };
}"""
HEADS = """() => [...document.querySelectorAll('.oa-stats thead th')].map((h) => {
  const b = h.getBoundingClientRect();
  const words = h.querySelector('[data-tip]').dataset.tip;
  return [h.innerText.trim(), Math.round(b.x), Math.round(b.width), words];
})"""


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1280, 1440])
@pytest.mark.parametrize("path", ["/product/warfarin/statistics", "/all/statistics"])
def test_the_table_fits_a_laptops_screen_with_every_column_and_sorting_moves_nothing(
    opened, stats_site, path, width, theme
):
    page = opened(path, base=stats_site, width=width, theme=theme)
    fit = page.evaluate(FIT)
    assert fit["table"] <= fit["frame"] and fit["cut"] == []
    heads = page.evaluate(HEADS)
    names = [h[0].title() for h in heads]
    # a drug's rows hold its class's EB05 beside its own (rule statistics-classes)
    beside = ["Class Eb05"] if path.startswith("/product") else []
    assert names[-12 - len(beside) :] == [
        "Cases",
        "Exp. Count",
        "Ebgm",
        "Eb05",
        *beside,
        "Eb95",
        "Prr",
        "Chi²",
        "Yates",
        "Ror",
        "Rrr",
        "Ic",
        "Onset",
    ]
    tips = {h[0].title(): h[3] for h in heads}
    assert tips["Exp. Count"].startswith("Expected count:")
    assert tips["Yates"].startswith("Chi² Yates:")
    # the grey interval sits under its value, not beside it
    ror = page.locator(".oa-stats tbody tr:first-child td").nth(len(heads) - 5)
    value, grey = ror.evaluate(
        """(c) => [c.getClientRects()[0], c.querySelector('.oa-faint')?.getBoundingClientRect()]
          .map((b) => b && b.top)"""
    )
    assert grey is None or grey > value
    for by in ("cases", "onset_days", "reaction"):
        page.click(f'.oa-stats thead [data-v="{by}"]')
        settle(page)
        assert [h[1:3] for h in page.evaluate(HEADS)] == [h[1:3] for h in heads], by
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if SHOTS:
        name = path.strip("/").replace("/", "-")
        page.screenshot(path=str(Path(SHOTS) / f"fit-{name}-{width}-{theme}.png"))


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("path", ["/product/warfarin/statistics", "/all/statistics"])
def test_on_a_phone_the_table_scrolls_sideways_with_its_first_column_held(
    opened, stats_site, path, theme
):
    page = opened(path, base=stats_site, width=390, theme=theme)
    first = page.locator(".oa-stats thead th").first.inner_text().title()
    assert first == ("Reaction" if path.startswith("/product") else "Ingredient")
    frame = page.locator(".dashboard-frame:has(> .oa-stats)")
    assert frame.evaluate("(f) => f.scrollWidth > f.clientWidth")  # too wide for a phone
    got = first_column_held(frame)
    assert got["held"], got
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if SHOTS:
        page.locator(".oa-stats").scroll_into_view_if_needed()
        name = path.strip("/").replace("/", "-")
        page.screenshot(path=str(Path(SHOTS) / f"held-{name}-390-{theme}.png"))
