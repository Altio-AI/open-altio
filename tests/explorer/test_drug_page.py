"""A drug's page and the Drugs filter in a browser, at a phone's, a tablet's and a desktop's width
(rule explorer-drug-counts): the title names the drug and the spellings it counts, the roles are
FDA's codes as tick boxes with PS and SS ticked (any others stand on the filter strip), any
product containing the drug sits beside the product alone, the spellings can be left out and
FDA's spellings with no ingredient added, and an older address opens the drug its name is read
to. Ticking and switching change the counts and move nothing else on the page. On the Statistics
tab, which counts by the ingredient alone, the drug's line stands disabled where it stands.
"""

from __future__ import annotations

from typing import Any

import pytest

from open_altio.testing.browser import settle

WIDTHS = (390, 1024, 1440)
# what must stand still while a person ticks and switches: the page's head, the drug's line and
# the panel with its toolbar and filter strip
STILL = (
    "h1",
    ".product-tabs",
    ".oa-unit",
    ".oa-roles",
    ".product-panel",
    ".oa-filters-btn",
    ".oa-export-btn",
    ".oa-strip",
)


def boxes(page: Any, selectors: tuple[str, ...] = STILL) -> dict[str, tuple]:
    return page.evaluate(
        """(sels) => Object.fromEntries(sels.map((s) => {
          const b = document.querySelector(s).getBoundingClientRect();
          return [s, [b.x, b.y, b.width, b.height].map(Math.round)];
        }))""",
        list(selectors),
    )


def press(page: Any, selector: str) -> None:
    page.click(selector)
    settle(page)


def count(page: Any) -> int:
    return int(page.inner_text("#oa-countline strong").replace(",", ""))


def sideways(page: Any) -> bool:
    return page.evaluate("document.scrollingElement.scrollWidth > window.innerWidth")


def ticked(page: Any, scope: str = "") -> list[str]:
    return page.eval_on_selector_all(
        f'{scope} .oa-roles .oa-choice[aria-checked="true"]', "bs => bs.map((b) => b.dataset.v)"
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_the_roles_are_fdas_codes_ps_and_ss_ticked_each_named_on_hover(opened, width):
    page = opened("/product/valsartan/overview", width=width)
    codes = page.eval_on_selector_all(
        ".oa-drugbar .oa-roles .oa-choice", "bs => bs.map((b) => [b.dataset.v, b.dataset.tip])"
    )
    assert codes == [
        ["PS", "Primary suspect"],
        ["SS", "Secondary suspect"],
        ["I", "Interacting"],
        ["C", "Concomitant"],
    ]
    assert ticked(page, ".oa-drugbar") == ["PS", "SS"]
    assert not sideways(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_ticking_a_role_or_switching_the_unit_changes_the_count_and_moves_nothing(opened, width):
    page = opened("/product/valsartan/overview", width=width)
    before, suspect = boxes(page), count(page)
    assert page.inner_text(".oa-title-spellings") == "3 spellings"
    press(page, '.oa-drugbar [data-act="prole"][data-v="I"]')
    assert ticked(page, ".oa-drugbar") == ["PS", "SS", "I"] and count(page) == suspect + 1
    assert boxes(page) == before
    press(page, '.oa-drugbar [data-act="prole"][data-v="I"]')
    press(page, '[data-act="unit"][data-v="exact"]')
    assert count(page) == suspect - 1  # Entresto's case is the combination's, not valsartan alone's
    assert page.inner_text(".oa-title-spellings") == "2 spellings"
    assert boxes(page) == before
    assert not sideways(page)


def test_the_last_role_ticked_stays_ticked(opened):
    page = opened("/product/valsartan/overview")
    press(page, '.oa-drugbar [data-act="prole"][data-v="PS"]')
    press(page, '.oa-drugbar [data-act="prole"][data-v="SS"]')
    assert ticked(page, ".oa-drugbar") == ["SS"] and count(page) == 1


def strip(page: Any) -> list[list[str]]:
    """The filter strip's items as [name, value], or [] when it says there are none."""
    return page.eval_on_selector_all(
        ".oa-strip .oa-strip-item",
        """items => items.map((i) => [i.querySelector('.oa-strip-name').textContent,
                                     i.querySelector('.oa-strip-value').textContent])""",
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_roles_other_than_ps_and_ss_stand_on_the_filter_strip_until_taken_off(opened, width):
    page = opened("/product/valsartan/overview", width=width)
    before, suspect = boxes(page), count(page)
    assert strip(page) == [] and "No filters" in page.inner_text(".oa-strip")
    press(page, '.oa-drugbar [data-act="prole"][data-v="I"]')
    press(page, '.oa-drugbar [data-act="prole"][data-v="C"]')
    assert strip(page) == [["Roles", "PS, SS, I or C"]]
    assert boxes(page) == before
    press(page, '.oa-strip [data-act="roles-ticks"]')
    assert page.evaluate("document.activeElement.dataset.v") == "PS"  # its edit is the ticks
    press(page, '.oa-strip [data-act="unfilter"][data-key="roles"]')
    assert ticked(page, ".oa-drugbar") == ["PS", "SS"] and count(page) == suspect
    assert strip(page) == [] and boxes(page) == before
    # ticked back by hand to the roles the page opens with, they leave the strip too
    press(page, '.oa-drugbar [data-act="prole"][data-v="SS"]')
    assert strip(page) == [["Roles", "PS"]]
    press(page, '.oa-drugbar [data-act="prole"][data-v="SS"]')
    assert strip(page) == []
    assert not sideways(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_the_drugs_line_leaves_the_panel_where_all_cases_has_it(opened, site, width):
    page = opened("/all/overview", width=width)
    on_all = boxes(page, (".product-panel", ".oa-toolbar", ".oa-strip"))
    page.goto(site + "/product/valsartan/overview")
    settle(page)
    on_drug = boxes(page, (".product-panel", ".oa-toolbar", ".oa-strip"))
    if width >= 1024:  # beside the tabs; on a phone it stands over them
        assert {k: v[:3] for k, v in on_drug.items()} == {k: v[:3] for k, v in on_all.items()}
    assert not sideways(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_the_spellings_are_listed_ticked_and_one_can_be_left_out_or_added(opened, width):
    page = opened("/product/valsartan/overview", width=width)
    every = count(page)
    press(page, ".oa-title-spellings")
    listed = page.eval_on_selector_all(
        '#oa-spell-results [data-act="spell"]',
        "bs => bs.map((b) => [b.dataset.v, b.getAttribute('aria-checked')])",
    )
    assert sorted(listed) == [["DIOVAN", "true"], ["ENTRESTO", "true"], ["VALSARTAN", "true"]]
    rows = boxes(page, ('#oa-spell-results [data-v="ENTRESTO"]', "#oa-spell-find"))
    press(page, '#oa-spell-results [data-act="spell"][data-v="ENTRESTO"]')
    assert count(page) == every - 1
    assert page.get_attribute('[data-act="spell"][data-v="ENTRESTO"]', "aria-checked") == "false"
    assert boxes(page, tuple(rows)) == rows  # unticked in its place
    page.fill("#oa-spell-find", "valsar")
    page.wait_for_selector('[data-act="spell-add"][data-v="VALSARTAN TEVA"]')
    settle(page)
    press(page, '[data-act="spell-add"][data-v="VALSARTAN TEVA"]')
    assert count(page) == every
    page.keyboard.press("Escape")
    strip = page.inner_text("#oa-strip")
    assert "1 left out" in strip and "1 with no ingredient added" in strip
    assert page.inner_text(".oa-title-spellings") == "3 spellings"  # two of its own, one added
    assert not sideways(page)


def test_an_older_address_opens_its_drug_and_the_list_keeps_it_under_that_name(opened):
    kept = {"products": [{"name": "ASPIRIN", "label": "My aspirin", "opened": 0}]}
    page = opened("/product/ASPIRIN/cases", kept=kept)
    assert page.evaluate("location.pathname") == "/product/acetylsalicylic%20acid/cases"
    assert page.inner_text("h1").startswith("My aspirin")
    stored = page.evaluate("JSON.parse(localStorage.getItem('open-altio.products'))")
    assert [(p["name"], p["label"], p["title"]) for p in stored] == [
        ("acetylsalicylic acid", "My aspirin", "Acetylsalicylic acid")
    ]


def test_a_page_of_fdas_spelling_with_no_ingredient_is_its_own_product(opened):
    page = opened("/product/VALSARTAN%20TEVA/overview")
    assert page.inner_text("h1").startswith("VALSARTAN TEVA")
    assert "FDA's spelling with no ingredient" in page.inner_text("#oa-subtitle")
    assert page.get_attribute('[data-act="unit"][data-v="any"]', "aria-disabled") == "true"
    assert page.get_attribute('[data-act="unit"][data-v="exact"]', "aria-selected") == "true"


@pytest.mark.parametrize("width", [390, 1440])
def test_on_the_statistics_tab_the_drugs_line_stands_disabled_where_it_stands(opened, width):
    page = opened("/product/valsartan/overview", width=width)
    press(page, '[data-act="unit"][data-v="exact"]')
    line = (".oa-unit", ".oa-roles", '.oa-roles [data-v="C"]')
    before = boxes(page, line)
    press(page, '.product-tab[href$="/statistics"]')
    assert boxes(page, line) == before
    controls = page.locator(".oa-drugbar :is(.view-switch-half, .oa-choice)")
    assert controls.count() == 6
    assert all(c.get_attribute("aria-disabled") == "true" for c in controls.all())
    # one tip over the whole greyed line, the same wherever the pointer is on it
    assert page.locator(".oa-drugbar [data-tip]").count() == 1
    for piece in (
        '[data-act="unit"][data-v="any"]',
        '[data-act="unit"][data-v="exact"]',
        ".oa-roles .field-label",
        '.oa-roles [data-v="PS"]',
        '.oa-roles [data-v="C"]',
    ):
        page.hover(piece, force=True)
        assert page.inner_text("#oa-tip") == (
            "Statistics count every product containing the ingredient, "
            "as primary or secondary suspect"
        )
        holder = page.evaluate(
            "(s) => document.querySelector(s).closest('[data-tip]').className", piece
        )
        assert holder == "oa-drugline", piece
    page.click('[data-act="unit"][data-v="any"]', force=True)
    page.click('.oa-drugbar [data-act="prole"][data-v="C"]', force=True)
    settle(page)
    assert page.get_attribute('[data-act="unit"][data-v="exact"]', "aria-selected") == "true"
    assert ticked(page, ".oa-drugbar") == ["PS", "SS"]
    press(page, '.product-tab[href$="/overview"]')
    assert page.locator('.oa-drugbar [aria-disabled="true"]').count() == 0
    page.hover('.oa-roles [data-v="PS"]')
    assert page.inner_text("#oa-tip") != "" and "Statistics count" not in page.inner_text("#oa-tip")
    assert page.get_attribute('[data-act="unit"][data-v="exact"]', "aria-selected") == "true"
    assert not sideways(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_the_drugs_filter_finds_ingredients_and_spellings_with_role_tick_boxes(opened, width):
    page = opened("/all/overview", width=width)
    press(page, ".oa-filters-btn")
    press(page, '#oa-filter-menu [data-act="filter-row"][data-row="drugs"]')
    assert ticked(page, "#oa-filter-menu") == ["PS", "SS"]
    page.fill("#oa-drug-find", "valsar")
    page.wait_for_selector('#oa-drug-results [data-act="dprod"][data-v="VALSARTAN TEVA"]')
    settle(page)
    offered = page.eval_on_selector_all(
        '#oa-drug-results [data-act="dprod"]', "bs => bs.map((b) => b.dataset.v)"
    )
    assert offered == ["valsartan", "sacubitril;valsartan", "VALSARTAN TEVA"]
    press(page, '#oa-drug-results [data-act="dprod"][data-v="valsartan"]')
    press(page, '#oa-filter-menu [data-act="drole"][data-v="C"]')
    assert ticked(page, "#oa-filter-menu") == ["PS", "SS", "C"]
    page.keyboard.press("Escape")
    assert "Valsartan, as PS, SS or C" in page.inner_text("#oa-strip")
    assert not sideways(page)


def test_home_finds_a_drug_by_a_spelling_and_offers_spellings_with_no_ingredient(opened):
    page = opened("/")
    page.fill("#oa-find", "diovan")
    page.wait_for_selector('#oa-find-results a[href="/product/valsartan/overview"]')
    page.fill("#oa-find", "valsar")
    page.wait_for_selector('#oa-find-results a[href="/product/VALSARTAN%20TEVA/overview"]')
    assert "WITH NO INGREDIENT" in page.inner_text("#oa-find-results").upper()


# the middle of the title's small letters, and the middle of the spellings count beside it
MIDDLES = """() => {
  const h = document.querySelector('h1');
  const words = document.createRange();
  words.selectNodeContents([...h.childNodes].find((n) => n.nodeType === Node.TEXT_NODE));
  const glyphs = document.createElement('canvas').getContext('2d');
  glyphs.font = getComputedStyle(h).font;
  const x = glyphs.measureText('x');
  const line = words.getBoundingClientRect();
  const baseline = line.bottom - glyphs.measureText('x').fontBoundingBoxDescent;
  const count = document.querySelector('.oa-title-spellings').getBoundingClientRect();
  return [baseline - x.actualBoundingBoxAscent / 2, (count.top + count.bottom) / 2];
}"""


@pytest.mark.parametrize("width", [390, 1440])
def test_the_spellings_count_sits_on_the_titles_small_letters_and_underlines_to_press(
    opened, width
):
    page = opened("/product/valsartan/overview", width=width)
    letters, count = page.evaluate(MIDDLES)
    assert abs(letters - count) <= 2
    underline = "(el) => getComputedStyle(el).textDecorationLine"
    assert page.eval_on_selector(".oa-title-spellings", underline) == "none"
    page.hover(".oa-title-spellings")
    assert page.eval_on_selector(".oa-title-spellings", underline) == "underline"
