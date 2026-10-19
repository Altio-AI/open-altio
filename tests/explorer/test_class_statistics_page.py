"""The Statistics tab by WHO class in a browser, over the release whose priors fit (`stats_site`):
All cases' list by class at each level, chosen in the menu beside Thresholds, a class's row opening
its cases, and a drug's rows with its class's EB05 at the level chosen, at a phone's width and a
laptop's; and none of it where the host hides the classes or the release has none."""

from __future__ import annotations

import pytest
from fastapi.requests import Request

from open_altio.explorer.access import LOCAL, LocalAccess, Viewer
from open_altio.explorer.app import create_app
from open_altio.faers.statistics import classes
from open_altio.testing.browser import served, settle

WIDTHS = [390, 1440]
BUTTON = '[data-act="stat-classes"]'


class NoClasses(LocalAccess):
    """A copy whose host hides WHO's classes, as the hosted switch does when off."""

    def viewer(self, request: Request) -> Viewer:
        return Viewer(id=LOCAL.id, meddra=True, who=False)


def choose(page, label: str) -> None:
    page.click(BUTTON)
    page.locator(".oa-classes-menu").get_by_role("menuitemradio", name=label).click()
    settle(page)


def first_cells(page) -> list[str]:
    return page.eval_on_selector_all(
        ".oa-stats tbody tr td:first-child", "cs => cs.map((c) => c.innerText.trim())"
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_all_cases_list_by_class_at_each_level_the_menu_offers(
    opened, stats_site, stats_client, width
):
    page = opened("/all/statistics", base=stats_site, width=width)
    assert page.inner_text(BUTTON).strip() == "By ingredient"
    page.click(BUTTON)
    offered = page.locator(".oa-classes-menu [role=menuitemradio] .menu-choice-words")
    names = [v["name"] for v in classes.levels()]
    assert [t.split("\n")[0].split(" ATC level")[0] for t in offered.all_inner_texts()] == [
        "Ingredient",
        *names,
    ]
    page.keyboard.press("Escape")
    for level in classes.levels():
        choose(page, level["name"])
        got = stats_client.get(f"/api/statistics?by=class&level={level['level']}&pass=").json()
        assert page.locator(".oa-stats thead th").first.inner_text().strip() == "Class"
        shown = first_cells(page)
        assert len(shown) == len(got["rows"]) > 0
        assert shown[0].startswith(got["rows"][0]["class_name"])
        assert got["rows"][0]["class"] in shown[0]
        assert level["name"].lower() in page.inner_text(".oa-stat-lead")
        assert page.inner_text(BUTTON).strip() == "By class"
        assert page.locator('.oa-stats thead [data-col="onset_days"]').count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    choose(page, "Ingredient")
    assert page.locator(".oa-stats thead th").first.inner_text().strip() == "Ingredient"


def test_a_class_rows_press_opens_every_cases_tab_filtered_to_the_class_and_reaction(
    opened, stats_site
):
    page = opened("/all/statistics", base=stats_site, width=1440)
    choose(page, classes.levels()[-1]["name"])
    row = page.locator(".oa-stats tbody tr").first
    code, reaction = row.get_attribute("data-class"), row.locator("th").inner_text()
    name = row.locator("td").first.inner_text().replace(code, "").strip()
    row.click()
    settle(page)
    assert page.url.endswith("/all/cases")
    strip = page.inner_text("#oa-strip").lower()
    assert reaction.lower() in strip and name.lower() in strip


@pytest.mark.parametrize("width", WIDTHS)
def test_a_drugs_rows_show_its_classs_eb05_beside_its_own_at_the_level_chosen(
    opened, stats_site, stats_client, width
):
    page = opened("/product/warfarin/statistics", base=stats_site, width=width)
    assert page.inner_text(BUTTON).strip() == "Class level"
    heads = page.eval_on_selector_all(
        ".oa-stats thead th", "hs => hs.map((h) => h.dataset.col || h.innerText.trim())"
    )
    assert heads[heads.index("eb05") + 1] == "class_eb05"
    tip = page.locator('.oa-stats thead [data-col="class_eb05"] [data-tip]').get_attribute(
        "data-tip"
    )
    for level in reversed(classes.levels()):
        if level is not classes.levels()[-1]:
            choose(page, level["name"])
        got = stats_client.get(
            f"/api/statistics?ingredient=warfarin&level={level['level']}&pass="
        ).json()
        column = heads.index("class_eb05")  # the reaction is the row's head, not a cell
        cells = page.eval_on_selector_all(
            f".oa-stats tbody tr td:nth-of-type({column})", "cs => cs.map((c) => c.innerText)"
        )
        assert len(cells) == len(got["rows"]) > 0
        for said, row in zip(cells, got["rows"], strict=True):
            assert (said == "") == (row["class_eb05"] is None)
            if row["class_eb05"] is not None:
                assert float(said.replace(",", "")) == pytest.approx(
                    row["class_eb05"], rel=0.01, abs=0.006
                )
        now = page.locator('.oa-stats thead [data-col="class_eb05"] [data-tip]')
        assert got["class"]["name"] in now.get_attribute("data-tip")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert tip and level["name"].lower() in now.get_attribute("data-tip")


@pytest.mark.parametrize("width", WIDTHS)
def test_where_the_host_hides_the_classes_or_the_release_has_none_nothing_of_them_shows(
    opened, stats_release, bare_site, width
):
    with served(create_app(stats_release, access=NoClasses())) as hidden:
        for base in (hidden, bare_site):
            for path in ("/all/statistics", "/product/warfarin/statistics"):
                page = opened(path, base=base, width=width)
                page.wait_for_selector(".oa-stats tbody tr")
                assert page.locator(BUTTON).count() == 0, (base, path)
                assert page.locator('.oa-stats [data-col="class_eb05"]').count() == 0
                assert page.locator('.oa-stats thead [data-col="class"]').count() == 0
