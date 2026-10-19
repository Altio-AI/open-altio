"""What the page tells a host's report hook (`report` in ui/host.js): each screen and tab
opened, each rule read, each result picked from a search, MedDRA's licensed levels and WHO's
classes by their codes. The hook is empty on its own (test_outbox_browser.py shows a copy sends
nothing); here each test turns it on in the page, as a host's page module does."""

from __future__ import annotations

import pytest

# the host's hook, turned on: every report kept in the page, to be read back
HEAR = """() => import('/ui/host.js').then((m) => {
  window.heard = [];
  m.host.report = (kind, detail) => window.heard.push({ kind, ...detail });
})"""


def hearing(page):
    page.evaluate(HEAR)
    return page


def heard(page, kind: str | None = None) -> list[dict]:
    got = page.evaluate("() => window.heard")
    return [r for r in got if kind is None or r["kind"] == kind]


def go(page, path: str) -> None:
    """Open another page here, as a click on a link to it does."""
    page.evaluate("(path) => import('/ui/router.js').then((m) => m.go(path))", path)
    page.wait_for_function("(path) => location.pathname + location.search === path", arg=path)


def until(page, kind: str, n: int = 1) -> list[dict]:
    """The reports of this kind, once there are `n` of them (up to five seconds)."""
    for _ in range(100):
        if len(heard(page, kind)) >= n:
            break
        page.wait_for_timeout(50)
    return heard(page, kind)


def test_each_screen_and_tab_opened_is_reported_once_and_rules_read_by_name(opened):
    page = hearing(opened("/"))
    go(page, "/all/overview")
    go(page, "/all/cases")
    go(page, "/product/valsartan/statistics")
    page.evaluate("() => import('/ui/router.js').then((m) => m.render())")  # drawn again
    go(page, "/methods?open=ebgm,prr")
    assert heard(page, "screen") == [
        {"kind": "screen", "screen": "scope", "tab": "overview", "product": ""},
        {"kind": "screen", "screen": "scope", "tab": "cases", "product": ""},
        {"kind": "screen", "screen": "scope", "tab": "statistics", "product": "valsartan"},
        {"kind": "screen", "screen": "methods", "tab": "", "product": ""},
    ]
    assert heard(page, "rule") == [
        {"kind": "rule", "rule": "ebgm"},
        {"kind": "rule", "rule": "prr"},
    ]


def test_a_rule_opened_on_the_methods_page_is_a_rule_read(opened):
    page = hearing(opened("/methods?open=a_stats"))
    row = page.locator('[data-act="rule-toggle"][data-id="ebgm"]')
    row.click()
    assert until(page, "rule") == [{"kind": "rule", "rule": "ebgm"}]
    row.click()  # closing it reads nothing
    assert len(heard(page, "rule")) == 1


def test_a_product_picked_from_home_is_reported_with_the_words_typed(opened):
    page = hearing(opened("/"))
    page.fill("#oa-find", "valsar")
    page.click('#oa-find-results a[href="/product/valsartan/overview"]')
    assert until(page, "pick") == [
        {"kind": "pick", "search": "products", "words": "valsar", "picked": "valsartan"}
    ]


def test_a_drug_picked_in_the_drugs_filter_is_reported_by_its_name(opened):
    page = hearing(opened("/all/overview"))
    page.click(".oa-filters-btn:visible")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="drugs"]')
    page.fill("#oa-drug-find", "valsar")
    page.click('#oa-drug-results [data-act="dprod"][data-v="valsartan"]')
    assert until(page, "pick") == [
        {"kind": "pick", "search": "drugs", "words": "valsar", "picked": "valsartan"}
    ]
    page.click('#oa-filter-menu [data-act="dprod"][data-v="valsartan"]')  # unpicked: no pick
    assert len(heard(page, "pick")) == 1


def test_meddra_s_licensed_levels_are_reported_by_code_and_a_preferred_term_by_name(
    opened, licensed_client
):
    [llt] = licensed_client.get("/api/terms?q=arrhythm&meddra=1").json()["llts"]
    page = hearing(opened("/all"))
    page.click(".oa-filters-btn:visible")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="reactions"]')
    page.fill("#oa-term-find", "nause")
    page.click('#oa-term-results [data-act="pt"][data-v="Nausea"]')
    page.fill("#oa-term-find", "arrhythm")
    page.click(f'[data-act="pt"][data-llt="{llt[4]}"]')
    page.fill("#oa-term-find", "bleeding")
    page.click('[data-act="smq-add"][data-code="96000001"][data-scope="broad"]')
    picks = until(page, "pick", 3)
    by = {"kind": "pick", "search": "reactions"}
    assert picks == [
        by | {"words": "nause", "picked": "Nausea"},
        by | {"words": "arrhythm", "level": "llt", "code": llt[4]},
        by | {"words": "bleeding", "level": "smq", "code": "96000001"},
    ]
    # pressing a chosen term again leaves it out: that is not a pick
    page.fill("#oa-term-find", "nause")
    page.click('#oa-term-results [data-act="pt"][data-v="Nausea"]')
    assert len(heard(page, "pick")) == 3
    assert llt[0] not in str(picks)  # the licensed name never goes


@pytest.fixture
def classed_page(opened, classes_site):
    return hearing(opened("/all", base=classes_site))


def test_a_who_class_is_reported_by_its_code(classed_page):
    page = classed_page
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="atc"]')
    page.wait_for_selector("#oa-class-results .oa-choice")
    page.fill("#oa-class-find", "C01")
    page.locator('#oa-class-results [data-act="class-pick"][data-code="C01"]').first.click()
    [pick] = until(page, "pick")
    assert pick == {
        "kind": "pick",
        "search": "classes",
        "words": "C01",
        "level": "class",
        "code": "C01",
    }


def test_a_hook_that_fails_never_stops_the_click(opened):
    page = opened("/")
    broken = "() => { throw new Error('the host is gone'); }"
    page.evaluate(f"() => import('/ui/host.js').then((m) => {{ m.host.report = {broken}; }})")
    page.fill("#oa-find", "valsar")
    page.click('#oa-find-results a[href="/product/valsartan/overview"]')
    page.wait_for_function("() => location.pathname === '/product/valsartan/overview'")
