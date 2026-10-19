"""Pinning a product: the pin on each product Home finds and on a product's page, the side panel
holding exactly the pinned products in the order the person drags them, and unpinning from the
same pin or the row's options. Kept in the browser."""

from __future__ import annotations

from typing import Any

from open_altio.testing.browser import settle

# kept before the page opens, every time it opens
NOTHING = {"products": []}


def side_rows(page: Any) -> list[str]:
    return page.eval_on_selector_all(
        ".side-panel .oa-prod-row", "rs => rs.map((r) => r.innerText.trim())"
    )


def kept(page: Any) -> list[tuple[str, bool]]:
    stored = page.evaluate("JSON.parse(localStorage.getItem('open-altio.products'))")
    return [(p["name"], p["pinned"]) for p in stored]


def find(page: Any, words: str) -> None:
    page.fill("#oa-find", words)
    page.wait_for_selector("#oa-find-results .oa-result")
    settle(page)


def pin_of(page: Any, name: str, where: str = "") -> Any:
    return page.locator(f'{where} .oa-pin[data-prod="{name}"]'.strip()).first


def test_a_found_product_pins_to_the_side_panel_and_unpins_from_the_same_pin(opened):
    page = opened("/", kept=NOTHING)
    assert side_rows(page) == [] and "Pin a product" in page.inner_text(".oa-side-products")
    find(page, "valsar")
    pin = pin_of(page, "valsartan", "#oa-find-results")
    assert pin.get_attribute("aria-pressed") == "false"
    assert pin.get_attribute("data-tip") == "Pin to the side panel"
    pin.click()
    assert (
        pin.get_attribute("aria-pressed") == "true"
        and pin.get_attribute("aria-label") == "Unpin Valsartan"
    )
    assert side_rows(page) == ["Valsartan"] and kept(page) == [("valsartan", True)]
    assert "Valsartan is pinned to the side panel." in page.inner_text("#oa-toasts")
    pin.click()
    assert pin.get_attribute("aria-pressed") == "false" and side_rows(page) == []
    assert kept(page) == [("valsartan", False)]


def test_opening_a_product_does_not_pin_it_and_its_page_header_does(opened, site):
    page = opened("/product/valsartan/overview")  # a new browser: nothing kept yet
    assert side_rows(page) == [] and kept(page) == [("valsartan", False)]
    pin_of(page, "valsartan", "h1").click()
    assert side_rows(page) == ["Valsartan"]
    page.goto(site + "/")
    settle(page)
    # kept in this browser: Home's search shows it pinned, and Home still lists it as opened
    assert side_rows(page) == ["Valsartan"]
    assert page.locator('#oa-home-list [data-tile="valsartan"]').count() == 1
    find(page, "valsar")
    assert pin_of(page, "valsartan", "#oa-find-results").get_attribute("aria-pressed") == "true"


def test_a_pinned_products_menu_renames_and_unpins_it(opened):
    page = opened("/product/valsartan/overview", kept=NOTHING)
    pin_of(page, "valsartan", "h1").click()
    page.hover('.oa-prod-row[data-prod="valsartan"]')
    page.click('.oa-prod-row[data-prod="valsartan"] [data-act="prod-menu"]')
    items = page.eval_on_selector_all(
        ".menu .menu-item", "els => els.map((e) => e.innerText.trim())"
    )
    assert items == ["Rename", "Unpin"]
    page.click('[data-act="prod-unpin"]')
    assert side_rows(page) == [] and "Pin a product" in page.inner_text(".oa-side-products")
    assert pin_of(page, "valsartan", "h1").get_attribute("aria-pressed") == "false"
    assert kept(page) == [("valsartan", False)]  # still opened lately on Home


def product(name: str, pinned: bool, opened: int = 1) -> dict[str, Any]:
    return {"name": name, "label": "", "opened": opened, "pinned": pinned}


def test_the_side_panel_holds_the_pinned_products_in_the_order_they_are_dragged(opened):
    page = opened(
        "/",
        kept={
            "products": [
                product("valsartan", True),
                product("metformin", False),
                product("omeprazole", True),
                product("acetylsalicylic acid", True),
            ]
        },
    )
    assert side_rows(page) == ["Valsartan", "Omeprazole", "Acetylsalicylic acid"]
    page.drag_and_drop(
        '.oa-prod-row[data-prod="acetylsalicylic acid"]',
        '.oa-prod-row[data-prod="valsartan"]',
        target_position={"x": 20, "y": 2},
    )
    assert side_rows(page) == ["Acetylsalicylic acid", "Valsartan", "Omeprazole"]
    pinned = [name for name, on in kept(page) if on]
    assert pinned == ["acetylsalicylic acid", "valsartan", "omeprazole"]
    # a new pin goes to the foot of the list
    find(page, "metformin")
    pin_of(page, "metformin", "#oa-find-results").click()
    assert side_rows(page)[-1] == "Metformin"


def test_a_list_kept_before_pins_stays_in_the_side_panel(opened):
    page = opened("/", kept={"products": [{"name": "valsartan", "label": "Mine", "opened": 1}]})
    assert side_rows(page) == ["Mine"]


def test_on_a_phone_a_tap_pins_and_the_pinned_rows_options_need_no_hover(opened):
    page = opened("/", width=390, touch=True, kept=NOTHING)
    find(page, "valsar")
    page.tap('#oa-find-results .oa-pin[data-prod="valsartan"]')
    assert pin_of(page, "valsartan", "#oa-find-results").get_attribute("aria-pressed") == "true"
    page.tap('.oa-topbar [data-act="side-open"]')
    dots = page.locator('.oa-prod-row[data-prod="valsartan"] [data-act="prod-menu"]')
    box = dots.bounding_box()
    assert box and box["width"] >= 32 and dots.is_visible()
    dots.tap()
    assert page.locator('.menu [data-act="prod-unpin"]').is_visible()


def home_section(page: Any) -> tuple[str, list[str]]:
    head = page.text_content("#oa-home-products .section-head")
    tiles = page.eval_on_selector_all(
        "#oa-home-list .oa-tile", "ts => ts.map((t) => t.dataset.tile)"
    )
    return head, tiles


def test_home_shows_the_pinned_products_once_any_is_pinned_else_those_opened_lately(opened):
    lately = [product("metformin", False, 3), product("omeprazole", False, 2)]
    page = opened("/", kept={"products": lately})
    assert home_section(page) == ("Opened lately", ["metformin", "omeprazole"])
    # pinning from the search turns the section to the pinned ones, the search left open
    find(page, "valsar")
    pin_of(page, "valsartan", "#oa-find-results").click()
    settle(page)
    assert home_section(page) == ("Pinned", ["valsartan"])
    assert page.is_visible("#oa-find-results") and page.input_value("#oa-find") == "valsar"
    # unpinned from its card, the last pin goes and opened lately comes back
    page.press("#oa-find", "Escape")
    pin_of(page, "valsartan", "#oa-home-list").click()
    settle(page)
    assert home_section(page) == ("Opened lately", ["metformin", "omeprazole"])


def test_home_lists_the_pinned_products_in_the_side_panels_order(opened):
    kept = [
        product("metformin", False, 9),
        product("omeprazole", True, 0),
        product("valsartan", True),
    ]
    page = opened("/", kept={"products": kept})
    assert home_section(page) == ("Pinned", ["omeprazole", "valsartan"])
    assert side_rows(page) == ["Omeprazole", "Valsartan"]


SHOWN = "(el) => getComputedStyle(el).opacity"


def test_a_cards_pin_shows_on_hover_and_once_pinned_and_always_on_a_phone(opened):
    kept = {"products": [product("metformin", False, 2), product("omeprazole", False)]}
    page = opened("/", kept=kept)
    metformin = pin_of(page, "metformin", "#oa-home-list")
    assert metformin.evaluate(SHOWN) == "0"
    page.hover('#oa-home-list [data-tile="metformin"]')
    page.wait_for_timeout(300)
    assert metformin.evaluate(SHOWN) == "1"
    metformin.click()
    page.mouse.move(0, 0)
    settle(page)
    shown = pin_of(page, "metformin", "#oa-home-list")
    assert shown.get_attribute("aria-pressed") == "true" and shown.evaluate(SHOWN) == "1"
    phone = opened("/", width=390, touch=True, kept=kept)
    pins = phone.locator("#oa-home-list .oa-pin")
    assert pins.count() == 2 and all(p.evaluate(SHOWN) == "1" for p in pins.all())
    pins.first.tap()
    assert side_rows(phone) == ["Metformin"]
