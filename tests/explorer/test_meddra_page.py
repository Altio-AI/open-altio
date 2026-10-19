"""MedDRA terms on the page (ui/meddra.js, rules meddra-terms and legacy-term-spelling), at a
phone's width and a desktop's: FDA's text as written in the case list, MedDRA's spelling of an
old term with FDA's capitals beside it, the current PT beside FDA's text only for a viewer with
MedDRA's licensed part, and the release's MedDRA version wherever reactions are counted.

`site` is the explorer over the licensed fake release as one person runs it with their own
MedDRA (LocalAccess); `public_site` the same release for a viewer the hook gives no MedDRA, as
the hosted service gives a person who is not a verified subscriber while the public gets today's
names; `fda_text_site` for one the hook shows reactions as FDA wrote them. In the invented
MedDRA 29.1 FDA's Arrhythmia is a lower level term of the PT Heart rhythm abnormal.
"""

from __future__ import annotations

import pytest

from open_altio.explorer.access import LocalAccess, Viewer
from open_altio.explorer.app import create_app
from open_altio.testing.browser import served, settle, tick_look

WIDTHS = [390, 1440]
LEGACY = "5100009"  # an AERS case: FDA wrote ARRHYTHMIA


class NoMeddra(LocalAccess):
    def viewer(self, request):
        return Viewer(id="ann", meddra=False, who=False)


@pytest.fixture(scope="session")
def public_site(licensed_release):
    with served(create_app(licensed_release, access=NoMeddra())) as base:
        yield base


LINE = "Reactions as FDA wrote them here."


class FdaText(LocalAccess):
    """A viewer the hook shows reactions as FDA wrote them, with its line."""

    def viewer(self, request):
        return Viewer(id="ann", meddra=False, who=False, todays_names=False, fda_text_line=LINE)


@pytest.fixture(scope="session")
def fda_text_site(licensed_release):
    with served(create_app(licensed_release, access=FdaText())) as base:
        yield base


@pytest.mark.parametrize("width", WIDTHS)
def test_shown_fdas_text_the_page_says_so_in_one_quiet_line_where_reactions_are(
    opened, fda_text_site, width
):
    page = opened("/all", base=fda_text_site, width=width)
    page.wait_for_selector(".oa-chart .oa-pt-line")
    assert page.inner_text(".oa-chart .oa-pt-line") == LINE
    chart = page.locator(".oa-chart", has=page.locator(".oa-pt-line")).inner_text()
    assert "Arrhythmia" in chart and "Heart rhythm abnormal" not in chart
    assert "MedDRA 29.1" not in chart
    stats = opened("/all/statistics", base=fda_text_site, width=width)
    stats.wait_for_selector(".oa-stat-lead")
    assert LINE in stats.inner_text(".oa-stat-lead")


@pytest.mark.parametrize("width", WIDTHS)
def test_named_by_todays_version_the_page_has_no_such_line(opened, public_site, width):
    for page in (opened("/all", width=width), opened("/all", base=public_site, width=width)):
        settle(page)
        assert not page.query_selector(".oa-pt-line")
        assert "Heart rhythm abnormal" in page.inner_text("main")


def case_window(page, key: str) -> str:
    """The case window of the listed case `key`, opened by a click, as its text."""
    page.click(f'tr[data-act="case"]:has(.case-key:text-is("{key}"))')
    page.wait_for_selector("#oa-case .oa-case-lead")
    return page.inner_text("#oa-case")


@pytest.mark.parametrize("width", WIDTHS)
def test_a_legacy_term_shows_meddras_spelling_fdas_beside_and_its_current_pt(opened, width):
    page = opened("/all/cases", width=width)
    shown = case_window(page, LEGACY)
    assert "Arrhythmia" in shown and "FDA: ARRHYTHMIA" in shown
    assert "PT: Heart rhythm abnormal" in shown
    links = page.eval_on_selector_all(
        "#oa-case .oa-rule-tag", "els => els.map((e) => [e.innerText, e.getAttribute('href')])"
    )
    assert ["fixed rule: legacy-term-spelling", "/methods?open=legacy-term-spelling"] in links
    assert not any(href == "/methods?open=meddra-terms" for _, href in links)
    # the terms wrap within the window rather than pushing it wider
    assert page.evaluate(
        "() => [...document.querySelectorAll('#oa-case .oa-list')]"
        ".every((l) => l.scrollWidth <= l.clientWidth + 1)"
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_without_meddras_licensed_part_no_pt_is_shown_beside_a_text(opened, public_site, width):
    page = opened("/all/cases", base=public_site, width=width)
    assert not page.query_selector(".oa-pt-note") and not page.query_selector(".oa-pt")
    shown = case_window(page, LEGACY)
    assert "FDA: ARRHYTHMIA" in shown and "Heart rhythm abnormal" not in shown
    assert "PT:" not in shown and "MedDRA 29.1" not in shown


@pytest.mark.parametrize("width", WIDTHS)
def test_the_case_list_shows_fdas_text_as_written_with_the_pt_beside(opened, width):
    page = opened("/all/cases", width=width)
    row = page.inner_text(f'tr[data-act="case"]:has(.case-key:text-is("{LEGACY}"))')
    assert "ARRHYTHMIA" in row and "PT: Heart rhythm abnormal" in row
    note = page.inner_text(".oa-pt-note")
    assert "Reactions as FDA wrote them" in note and "MedDRA 29.1" in note


@pytest.mark.parametrize("width", WIDTHS)
def test_the_re_exposure_reaction_and_the_indications_are_shown_the_same_way(opened, width):
    page = opened("/all/cases", width=width)
    shown = case_window(page, "9013013")
    # FDA writes an apostrophe in this field as ^; its PT is MedDRA's own name
    assert "came back when the drug was given again" in shown.lower()  # headings in capitals
    assert "Parkinson^s disease" in shown and "PT: Parkinson's disease" in shown
    page.keyboard.press("Escape")
    legacy = case_window(page, LEGACY)
    assert "Pain" in legacy and "FDA: PAIN" in legacy


@pytest.mark.parametrize("width", WIDTHS)
def test_where_reactions_are_counted_the_page_names_the_meddra_version(opened, public_site, width):
    page = opened("/all/overview", base=public_site, width=width)
    chart = page.inner_text('.oa-chart:has([data-key="reaction"])')
    assert "by current PT in MedDRA 29.1" in chart and "Heart rhythm abnormal" in chart
    page.click(".oa-filters-btn:visible")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="reactions"]')
    page.wait_for_selector("#oa-term-find:visible")
    assert "current PT in MedDRA 29.1" in page.inner_text("#oa-filter-menu")


@pytest.mark.parametrize("width", WIDTHS)
def test_a_statistics_pair_opens_as_many_cases_as_its_row_counts(opened, licensed_client, width):
    [row] = licensed_client.get("/api/statistics?ingredient=metformin&find=acidosis").json()["rows"]
    every = {"statistics-screens": {"list": "all"}}  # the list not screened, so the pair is in it
    page = opened("/product/metformin/statistics", width=width, kept=every)
    assert "Reactions under today's MedDRA 29.1 terms." in page.inner_text(".oa-stat-lead")
    page.click(f'tr[data-act="stat-row"][data-term="{row["term"]}"]')
    settle(page)
    assert page.evaluate("location.pathname").endswith("/cases")
    assert page.inner_text("#oa-countline").startswith(f"{row['cases']:,} case")


@pytest.mark.parametrize("width", WIDTHS)
def test_the_methods_page_names_the_version_and_the_free_text_indications(
    opened, licensed_client, width
):
    meddra = licensed_client.get("/api/rules").json()["meddra"]
    page = opened("/methods?open=meddra-terms", width=width)
    facts = page.inner_text("#rule-meddra-terms .oa-m-moved")
    assert "29.1" in facts and "search with the SMQ" in facts
    rows = meddra["free_text_indications"]["rows"]
    assert f"{rows} row" in facts and "shown as FDA wrote them" in facts


def test_home_says_a_meddra_part_an_older_version_added_is_left_out(opened, older_release):
    with served(create_app(older_release)) as base:
        said = opened("/", base=base).inner_text(".oa-meddra-older")
    assert "MedDRA 29.1 was added to this release by an older version" in said
    assert "open-altio serve --meddra <folder>" in said


def until_ticked(page, **ticks: str) -> None:
    """Wait until each term's rows, and each SMQ's (by its code), show their tick."""
    page.wait_for_function(
        """want => Object.entries(want).every(([k, tick]) => {
          const rows = [...document.querySelectorAll(`#oa-term-results [data-v="${k}"],
            #oa-term-results [data-act="smq-tick"][data-code="${k}"]`)];
          return rows.length && rows.every((e) => e.getAttribute('aria-checked') === tick);
        })""",
        arg=ticks,
    )


@pytest.mark.parametrize(("width", "theme"), [(w, t) for w in WIDTHS for t in ("light", "dark")])
def test_a_chosen_smq_ticks_its_terms_and_one_unticked_is_left_out(
    opened, licensed_client, ask, width, theme
):
    def count() -> str:
        return f"{ask(licensed_client, '/api/summary', **asked)['cases']:,}"

    page = opened("/all", width=width, theme=theme)
    page.click(".oa-filters-btn:visible")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="reactions"]')
    page.fill("#oa-term-find", "bleeding")
    page.click('[data-act="smq-add"][data-code="96000001"][data-scope="broad"]')
    page.click('[data-act="expand"][data-key="smq:96000001"]')
    until_ticked(page, Haemorrhage="true", Nausea="true")
    asked = {"smq": "96000001:broad"}
    page.wait_for_selector(f'#oa-countline strong:text-is("{count()}")')
    top = page.eval_on_selector('[data-act="pt"][data-v="Haemorrhage"]', "e => e.offsetTop")
    # unticked under the SMQ, a term is left out of it, and nothing moves
    page.click('[data-act="pt"][data-v="Nausea"]')
    until_ticked(page, Haemorrhage="true", Nausea="false")
    asked["pt_out"] = "Nausea"
    page.wait_for_selector(f'#oa-countline strong:text-is("{count()}")')
    assert page.eval_on_selector('[data-act="pt"][data-v="Haemorrhage"]', "e => e.offsetTop") == top
    assert "leaving out Nausea" in page.inner_text("#oa-strip")
    # among the chosen, the SMQ is partly ticked; pressed, it is whole again
    page.fill("#oa-term-find", "")
    until_ticked(page, **{"96000001": "mixed", "Nausea": "false"})
    smq = '#oa-term-results [data-act="smq-tick"][data-code="96000001"]'
    dash, plain = tick_look(page, smq), tick_look(page, '#oa-term-results [data-v="Nausea"]')
    page.click(smq)
    until_ticked(page, **{"96000001": "true", "Nausea": "true", "Haemorrhage": "true"})
    # the dash was a grey mark in the plain box, saying what it means; only the tick is lit
    tick = tick_look(page, smq)
    assert (dash["fill"], dash["edge"]) == (plain["fill"], plain["edge"])
    assert (dash["fill"], dash["edge"]) != (tick["fill"], tick["edge"])
    assert dash["mark"] == dash["edge"] and dash["size"] == tick["size"]
    assert dash["tip"] == "Part of this group is ticked" and tick["tip"] is None
    del asked["pt_out"]
    page.wait_for_selector(f'#oa-countline strong:text-is("{count()}")')
