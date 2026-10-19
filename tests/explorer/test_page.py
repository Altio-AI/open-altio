"""The page in a browser: what the explorer's page script does, checked where it runs.

Each test opens the explorer over the licensed fake release in headless Chromium
(`opened`, conftest.py) and checks what a person sees and what a click does. How the
pages look is the screenshot check's (scripts/screens.py); these hold what they do.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.responses import Response

from open_altio.explorer.access import LocalAccess
from open_altio.explorer.filters import NOT_GIVEN
from open_altio.rulebook import value
from open_altio.testing import fakefda
from open_altio.testing.browser import served, settle
from open_altio.testing.rules import rules_with

# what a page states ------------------------------------------------------------------------------


def test_home_states_the_releases_own_counts(opened, licensed_client):
    info = licensed_client.get("/api/release").json()
    card = opened("/").inner_text(".oa-release-card")
    assert card.startswith(f"{info['cases']:,} cases from FDA's quarters since ")
    assert f"{info['set_aside']:,} probable duplicates left out" in card


def test_the_count_line_is_the_releases_count_for_the_filters(opened, licensed_client):
    summary = licensed_client.get("/api/summary?product=valsartan").json()
    line = opened("/product/valsartan/overview").inner_text("#oa-countline")
    assert (
        line.startswith(f"{summary['cases']:,} cases") and f"{summary['serious']:,} serious" in line
    )


DUP_LINE = """() => {
  const l = document.querySelector('#oa-countline'), t = l.querySelector('.oa-dup-tick');
  const r = t.getBoundingClientRect(), b = l.getBoundingClientRect();
  return { words: t.innerText, x: r.x, y: r.y, w: r.width, h: r.height, lineH: b.height,
    over: document.documentElement.scrollWidth > innerWidth,
    on: l.querySelector('#oa-dups').checked }; }"""
CASES = """() => Number(
  document.querySelector('#oa-countline strong').innerText.replace(/,/g, ''))"""


@pytest.mark.parametrize("width", [1440, 1024, 768, 320])
@pytest.mark.parametrize("path", ["/all/overview", "/product/warfarin/overview"])
def test_probable_duplicates_are_one_tick_box_that_changes_the_counts_and_nothing_else(
    opened, width, path
):
    page = opened(path, width=width)
    before = page.evaluate(DUP_LINE)
    cases = page.evaluate(CASES)
    assert before["on"] is False and before["words"].startswith("Include ")
    assert page.get_by_role("checkbox", name="Include", exact=False).count() == 1
    page.check("#oa-dups")
    settle(page)
    after = page.evaluate(DUP_LINE)
    extra = int(before["words"].split()[1].replace(",", ""))
    assert after["on"] is True and page.evaluate(CASES) == cases + extra
    assert after["words"] == before["words"]
    assert page.evaluate("() => document.activeElement.id") == "oa-dups"
    page.uncheck("#oa-dups")
    settle(page)
    back = page.evaluate(DUP_LINE)
    assert back["on"] is False and page.evaluate(CASES) == cases
    for state in (after, back):
        assert state["words"] == before["words"] and state["lineH"] == before["lineH"]
        assert state["h"] == before["h"] and not state["over"]
        if width >= 1024:  # on a phone the line wraps with the digits of the counts
            assert abs(state["x"] - before["x"]) < 8 and state["y"] == before["y"]


AS_OF = """() => [...document.querySelectorAll('.oa-asof')]
  .filter((e) => e.checkVisibility()).map((e) => e.innerText)"""
# the page's words, less the line naming the release's folder on this computer
WORDS = """() => { const folder = document.querySelector('.oa-downloads-off');
  return document.body.innerText.replace(folder?.innerText || '', ''); }"""


@pytest.mark.parametrize("width", [1440, 1024, 390])
def test_every_page_says_once_how_current_its_data_is(opened, early_site, width):
    """A release built up to 2019Q1 says so in one quiet place on every page, and nowhere else."""
    page = opened("/", base=early_site, width=width)
    for path in ("/", "/all/overview", "/product/valsartan/overview", "/release", "/methods"):
        page.goto(early_site + path)
        settle(page)
        assert page.evaluate(AS_OF) == ["FDA data through 2019Q1"], path
        assert page.evaluate(WORDS).count("2019Q1") == 1, path


def test_the_page_names_where_the_quarters_start_and_the_last_day_the_release_holds(
    opened, early_site
):
    page = opened("/", base=early_site)
    assert "from FDA's quarters since 2012Q2," in page.inner_text(".oa-release-card")
    page.goto(early_site + "/all/overview")
    settle(page)
    assert page.inner_text("#oa-subtitle").endswith("from FDA's quarters since 2012Q2.")
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="received"]')
    years = page.eval_on_selector_all('[data-act="year"]', "bs => bs.map((b) => +b.dataset.v)")
    assert years == list(range(2019, 2012, -1))
    assert page.get_attribute('input[data-k="to"]', "max") == "2019-03-31"


UNDERLINE = "(el) => getComputedStyle(el).textDecorationLine"


def test_a_link_in_the_interface_underlines_only_to_press_and_one_in_a_sentence_always(opened):
    page = opened("/")
    link = page.locator('.oa-links a[href="/all/overview"]')
    assert link.evaluate(UNDERLINE) == "none"
    link.focus()  # by the keyboard: the focus shows, and the underline
    assert link.evaluate("(el) => el.matches(':focus-visible')")
    assert link.evaluate(UNDERLINE) == "underline"
    link.blur()
    link.hover()
    assert link.evaluate(UNDERLINE) == "underline"
    page = opened("/all/overview")
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="era"]')
    assert page.eval_on_selector(".oa-era-note .oa-link", UNDERLINE) == "underline"


# a colour's contrast with another, as WCAG works it out from their luminance
CONTRAST = """([a, b]) => {
  const cv = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const lum = (c) => {
    cv.fillStyle = c; cv.fillRect(0, 0, 1, 1);
    const [r, g, bl] = [...cv.getImageData(0, 0, 1, 1).data].map((v) => v / 255);
    const f = (v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl);
  };
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_link_reads_on_its_ground_and_is_not_the_colour_of_the_text_beside_it(opened, theme):
    page = opened("/", theme=theme)
    link, text, ground = page.eval_on_selector(
        ".oa-links a",
        """(a) => [a, a.closest('.oa-release-card'), a.closest('.panel')]
          .map((el, i) => getComputedStyle(el)[i < 2 ? 'color' : 'backgroundColor'])""",
    )
    assert page.evaluate(CONTRAST, [link, ground]) >= 4.5
    assert link != text


@pytest.mark.parametrize("width", [1440, 390])
def test_every_underline_sits_as_far_under_its_text_dotted_or_solid(opened, width):
    page = opened("/product/valsartan/overview", width=width)
    offsets = page.evaluate("""() => ['.oa-has-tip', '.oa-title-spellings', '.oa-links a', 'a']
      .map((s) => document.querySelector(s)).filter(Boolean)
      .map((el) => getComputedStyle(el).textUnderlineOffset)""")
    assert len(offsets) >= 3 and len(set(offsets)) == 1 and offsets[0] != "auto"


def test_the_eras_are_named_with_the_quarters_fda_published_them_in(opened):
    aers, faers = value("era-filter", "quarters")["AERS"], value("era-filter", "quarters")["FAERS"]
    page = opened("/all/overview")
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="era"]')
    choices = page.eval_on_selector_all(
        '[data-act="opt-era"] .menu-choice-words', "cs => cs.map((c) => c.innerText)"
    )
    assert choices == [f"FAERS, {faers[0]} onward", f"AERS, {aers[0]} to {aers[1]}"]


def test_the_overview_charts_as_many_reactions_as_the_rule_names(opened, licensed_client):
    summary = licensed_client.get("/api/summary").json()
    page = opened("/all/overview")
    shown = page.locator('[data-act="chart"][data-key="reaction"]').count()
    assert shown == len(summary["reactions"]) <= value("explorer-lists", "top_reactions")


def test_the_methods_page_says_the_statistics_take_no_case_out(opened, licensed_client):
    """A statistic works numbers out; a rule that takes cases out says how many it took."""
    rules = licensed_client.get("/api/rules").json()["rules"]
    statistics = [r["name"] for r in rules if r["step"]["id"] == "statistics"]
    assert statistics
    for name in [*statistics, "deleted-cases"]:
        page = opened(f"/methods?open={name}")
        moved = page.inner_text(f"#rule-{name} .oa-rule-moved")
        assert (moved == "No case removed") == (name in statistics), name


# what the rules say ------------------------------------------------------------------------------


def test_the_age_filter_offers_the_rules_bands_in_their_order(opened, licensed_client):
    present = {band for band, _ in licensed_client.get("/api/summary").json()["age"]}
    named = [(b["id"], b["label"]) for b in value("age-bands", "bands")]
    named.append((NOT_GIVEN, value("not-given", "label")))
    page = opened("/all/overview")
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="age"]')
    offered = page.eval_on_selector_all(
        '[data-act="opt"][data-key="age"] .menu-choice-words', "cs => cs.map((c) => c.innerText)"
    )
    assert offered == [label for band, label in named if band in present]


def test_the_sex_filter_offers_female_male_and_not_given(opened):
    page = opened("/all/overview")
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="sex"]')
    offered = page.eval_on_selector_all(
        '[data-act="opt"][data-key="sex"] .menu-choice-words', "cs => cs.map((c) => c.innerText)"
    )
    assert sorted(offered) == ["Female", "Male", value("not-given", "label")]


def chart(page: Any, key: str) -> Any:
    return page.locator(".oa-chart", has=page.locator(f'[data-act="chart"][data-key="{key}"]'))


@pytest.mark.parametrize("width", [390, 1440])
def test_each_field_chart_says_how_many_give_it_and_sets_not_given_apart(
    opened, licensed_client, width
):
    given = licensed_client.get("/api/summary").json()["given"]
    page = opened("/all/overview", width=width)
    for key, words in (
        ("age", "Age given"),
        ("sex", "Sex given"),
        ("reporter", "Reporter given"),
        ("country", "Country given"),
        ("sender", "Company given"),
        ("reaction", "Reactions given"),
        ("dprods", "Ingredient found"),
        # FDA writes outcome rows only for serious ones: the line never calls the rest missing
        ("outcome", "A serious outcome given"),
    ):
        n, cases = given[key]
        line = chart(page, key).locator(".oa-chart-given").inner_text()
        assert line.startswith(f"{words} for ")
        p = n / cases
        share = (
            "all"
            if n == cases
            else "none"
            if not n
            else "under 1%"
            if p < 0.01
            else "over 99%"
            if p > 0.99
            else f"{p:.0%}"
        )
        assert line == f"{words} for {share} of these cases."
    for key in ("age", "sex", "reporter", "country", "sender"):
        # Not given is the last bar, set apart from the values given
        box = chart(page, key)
        assert box.locator(f'.oa-chart-none [data-v="{NOT_GIVEN}"]').count() == 1
        assert box.locator(f'.chart-rows:not(.oa-chart-none) [data-v="{NOT_GIVEN}"]').count() == 0


def test_a_fields_note_shows_while_the_dates_take_in_the_quarters_its_files_changed(opened):
    note = next(n for n in value("explorer-field-notes", "notes") if n["field"] == "occp_cod")
    page = opened("/all/overview")
    assert note["note"] in chart(page, "reporter").inner_text()
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="reporter"]')
    assert note["note"] in page.inner_text("#oa-filter-options")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="received"]')
    page.fill('[data-act="days"][data-k="to"]', "2019-12-31")
    page.dispatch_event('[data-act="days"][data-k="to"]', "change")
    page.wait_for_function(
        "note => ![...document.querySelectorAll('.oa-chart')].some((c) => c.innerText"
        ".includes(note)) && document.querySelector('[data-key=\"reporter\"]')",
        arg=note["note"],
    )


def test_a_companys_bar_or_any_of_fdas_spellings_typed_filters_to_the_company(
    opened, licensed_client
):
    summary = licensed_client.get("/api/summary").json()
    page = opened("/all/overview")
    company, n = summary["sender"][0]
    page.click(f'[data-act="chart"][data-key="sender"][data-v="{company}"]')
    page.wait_for_function(
        "n => document.getElementById('oa-countline').innerText.startsWith(n)",
        arg=f"{n:,} case",
    )
    spelled = fakefda.LILLY[1]
    want = licensed_client.get("/api/summary", params={"sender": spelled}).json()["cases"]
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="sender"]')
    page.fill("#oa-sender-find", spelled)
    page.dispatch_event("#oa-sender-find", "change")
    page.wait_for_function(
        "n => document.getElementById('oa-countline').innerText.startsWith(n)",
        arg=f"{want:,} case",
    )
    assert want == 3  # the legacy case sent under one of the spellings too


def test_a_report_sent_straight_to_fda_says_so_with_fdas_sender_under(opened):
    page = opened("/all/overview")
    bar = chart(page, "sender").locator('.chart-rows:not(.oa-chart-none) [data-v="_direct"]')
    assert bar.get_attribute("aria-label").startswith("Sent straight to FDA:")
    page = opened("/all/cases")
    page.click('tr[data-act="case"]:has-text("9004004")')
    page.wait_for_selector("#oa-case .oa-case-lead")
    company = page.locator("#oa-case .oa-fields dt", has_text="Company").locator(
        "xpath=following-sibling::dd[1]"
    )
    assert (
        company.inner_text() == f"Sent straight to FDA\nFDA: {value('company-names', 'fda_sender')}"
    )


def test_typing_fdas_intake_or_the_words_shown_finds_the_reports_sent_straight_to_fda(
    opened, licensed_client
):
    direct = licensed_client.get("/api/summary", params={"sender": "_direct"}).json()["cases"]
    lilly = licensed_client.get("/api/summary", params={"sender": fakefda.LILLY[1]}).json()["cases"]
    page = opened("/all/overview")
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="sender"]')
    for typed, want in (
        ("sent straight to fda", direct),
        (fakefda.LILLY[1], lilly),
        (value("company-names", "fda_sender"), direct),
    ):
        page.fill("#oa-sender-find", typed)
        page.dispatch_event("#oa-sender-find", "change")
        page.wait_for_function(
            "n => document.getElementById('oa-countline').innerText.startsWith(n)",
            arg=f"{want:,} case",
        )
        if typed == "sent straight to fda":
            # the words choose the group itself, as clicking it does
            ticked = page.locator('#oa-filter-menu [data-act="opt-sender"][data-v="_direct"]')
            assert ticked.get_attribute("aria-checked") == "true"
            assert page.input_value("#oa-sender-find") == "Sent straight to FDA"
    assert direct != lilly


def test_the_case_window_reads_not_given_with_fdas_value_under(opened):
    page = opened("/all/cases")
    page.click('tr[data-act="case"]:has-text("9130013")')
    page.wait_for_selector("#oa-case .oa-case-lead")
    fields = dict(
        zip(
            page.eval_on_selector_all("#oa-case .oa-fields dt", "ds => ds.map((d) => d.innerText)"),
            page.eval_on_selector_all("#oa-case .oa-fields dd", "ds => ds.map((d) => d.innerText)"),
            strict=True,
        )
    )
    assert fields["Sex"] == "Not given\nFDA: NS"
    assert fields["Where it happened"] == "Not given\nFDA: COUNTRY NOT SPECIFIED"
    assert fields["Company"] == "Not given\nFDA: UNKNOWN MANUFACTURER"
    assert fields["Age"] == "Not given\nFDA: 999 YR"
    assert fields["Country"] != "Not given"


SHORT = {"home_tiles": 1, "countries_charted": 1, "years_offered": 2}


def test_the_pages_short_lists_are_as_long_as_the_rule_says(
    opened, explorer_app, licensed_release, tmp_path
):
    with (
        rules_with(tmp_path, {"explorer-lists": SHORT}),
        served(explorer_app(licensed_release)) as base,
    ):
        home = opened("/", base=base, kept={"products": []})
        assert home.locator("#oa-home-list .oa-tile").count() == SHORT["home_tiles"]
        page = opened("/all/overview", base=base)
        # the countries given, then Not given apart at the bottom
        countries = page.locator(
            f'[data-act="chart"][data-key="country"]:not([data-v="{NOT_GIVEN}"])'
        ).count()
        assert countries == SHORT["countries_charted"]
        page.click(".oa-filters-btn")
        page.click('#oa-filter-menu [data-act="filter-row"][data-row="received"]')
        assert page.locator('[data-act="year"]').count() == SHORT["years_offered"]


# addresses ---------------------------------------------------------------------------------------

ROUTES = {
    "/": ("/", "home", None),
    "/all": ("/all", "scope", "Overview"),
    "/all/overview": ("/all/overview", "scope", "Overview"),
    "/all/cases": ("/all/cases", "scope", "Cases"),
    "/product/valsartan": ("/product/valsartan", "scope", "Overview"),
    "/product/sacubitril%3Bvalsartan/cases": (
        "/product/sacubitril%3Bvalsartan/cases",
        "scope",
        "Cases",
    ),
    # an older address names FDA's active ingredient: the page of the drug it is read to opens
    "/product/aspirin": ("/product/acetylsalicylic%20acid/overview", "scope", "Overview"),
    "/product/ASPIRIN/cases": ("/product/acetylsalicylic%20acid/cases", "scope", "Cases"),
    "/release": ("/release", "release", None),
    "/sql": ("/release", "release", None),  # the old addresses of Tables and SQL
    "/downloads": ("/release", "release", None),
    "/all/nothing": ("/", "home", None),
    "/all/overview/more": ("/", "home", None),
    "/product/ASPIRIN/nothing": ("/", "home", None),
    "/product/NO-SUCH-PRODUCT/overview": ("/", "home", None),
    "/release/more": ("/", "home", None),
}


def where(page: Any) -> tuple[str, str, str | None]:
    tab = page.query_selector('.product-tab[aria-selected="true"]')
    return (
        page.evaluate("location.pathname"),
        page.evaluate("document.body.dataset.page"),
        (tab.inner_text() if tab else None),
    )


def test_each_address_opens_its_page_and_any_other_goes_home(opened, site):
    page = opened("/")
    for address, expected in ROUTES.items():
        page.goto(site + address)
        settle(page)
        assert where(page) == expected, address


def test_a_product_page_names_its_drug_and_the_spellings_it_counts(opened):
    page = opened("/product/sacubitril%3Bvalsartan/overview")
    assert page.inner_text("h1").startswith("Sacubitril and valsartan")
    assert page.inner_text(".oa-title-spellings") == "1 spelling"


def test_a_link_to_a_page_opens_it_here_and_back_returns(opened):
    page = opened("/")
    page.evaluate("window.stayed = true")
    page.click('.side-panel a[href="/all/overview"]')
    settle(page)
    assert where(page) == ("/all/overview", "scope", "Overview")
    assert page.evaluate("window.stayed") is True  # drawn here, not loaded again
    page.click('.product-tab[href="/all/cases"]')
    settle(page)
    page.go_back()
    settle(page)
    assert where(page) == ("/all/overview", "scope", "Overview")
    page.go_back()
    settle(page)
    assert where(page) == ("/", "home", None) and page.evaluate("window.stayed") is True


def test_the_page_writes_no_hash_into_its_addresses(opened):
    page = opened("/")
    hrefs = page.eval_on_selector_all("a[href]", "as => as.map((a) => a.getAttribute('href'))")
    assert hrefs and not [h for h in hrefs if "#" in h]


# keys and clicks ---------------------------------------------------------------------------------


def test_enter_and_space_open_a_case_row_as_a_click_does(opened):
    page = opened("/all/cases")
    rows = page.query_selector_all('tr[data-act="case"]')
    rows[0].focus()
    page.keyboard.press("Enter")
    page.wait_for_selector("#oa-case .oa-case-lead")
    page.keyboard.press("Escape")
    page.wait_for_selector("#oa-case", state="detached")
    rows = page.query_selector_all('tr[data-act="case"]')
    rows[1].focus()
    page.keyboard.press(" ")
    page.wait_for_selector("#oa-case .oa-case-lead")


def test_the_case_window_shows_the_event_date_as_far_as_it_is_known(opened, rel):
    page = opened("/all/cases")
    for prec in (6, 4):
        era, key, raw = rel.rows(
            "SELECT era_T, case_key_T, event_dt FROM case_latest_T "
            "WHERE event_dt_prec_T = ? ORDER BY length(event_dt) DESC, case_key_T LIMIT 1",
            prec,
        )[0]
        page.evaluate(
            """([era, key]) => { const b = document.createElement('button');
               Object.assign(b.dataset, { act: 'case-jump', era, key });
               document.body.append(b); b.click(); }""",
            [era, key],
        )
        page.wait_for_selector("#oa-case .oa-case-lead")
        shown = page.evaluate(
            """() => [...document.querySelectorAll('#oa-case dt')]
               .find((dt) => dt.textContent === 'Event date').nextElementSibling.innerText"""
        )
        known = date(int(raw[:4]), int(raw[4:6]), 1).strftime("%B %Y") if prec == 6 else raw[:4]
        assert shown.startswith(known), (raw, shown)
        assert (f"FDA: {raw}" in shown) == (raw != known), (raw, shown)
        page.keyboard.press("Escape")
        page.wait_for_selector("#oa-case", state="detached")


def _case_window(page, era: str, key: str) -> dict[str, Any]:
    """Open a case's window and read it: each field's text by its label, and the drug rows by
    column heading."""
    page.evaluate(
        """([era, key]) => { const b = document.createElement('button');
           Object.assign(b.dataset, { act: 'case-jump', era, key });
           document.body.append(b); b.click(); }""",
        [era, key],
    )
    page.wait_for_selector("#oa-case .oa-case-lead")
    seen = page.evaluate(
        """() => {
          const fields = Object.fromEntries([...document.querySelectorAll('#oa-case dt')]
            .map((dt) => [dt.textContent, dt.nextElementSibling.innerText]));
          const table = document.querySelector('#oa-case .oa-case-drugs');
          const heads = [...table.querySelectorAll('th')].map((th) => th.textContent);
          const drugs = [...table.querySelectorAll('tbody tr')].map((tr) => Object.fromEntries(
            [...tr.children].map((td, i) => [heads[i], td.innerText])));
          return { fields, drugs };
        }"""
    )
    page.keyboard.press("Escape")
    page.wait_for_selector("#oa-case", state="detached")
    return seen


def test_the_case_window_reads_fdas_codes_in_words_with_fdas_code_under(opened, rel):
    page = opened("/all/cases")
    [(occp, freq, rechal)] = rel.rows(
        "SELECT c.occp_cod, d.dose_freq, d.rechal FROM case_latest_T c JOIN drug_latest_T d "
        "USING (era_T, primaryid, quarter_T) WHERE c.case_key_T = '9002002'"
    )
    seen = _case_window(page, "faers", "9002002")
    for label, code in (("Who reported", occp), ("Report type", "EXP")):
        assert f"FDA: {code}" in seen["fields"][label] and not seen["fields"][label].startswith(
            "FDA"
        ), seen["fields"][label]
    [drug] = seen["drugs"]
    # how often, in FDA's words after the dose, with FDA's code under them
    assert drug["Dose"].endswith(f"\nFDA: {freq}") and len(drug["Dose"]) > len(freq) + 5
    # FDA's rechallenge D in 2012Q4 to 2015Q3 is a filler: Not given, FDA's code under it
    # (rule not-given); D outside those quarters reads in its plain label
    assert drug["Stopped and restarted"].endswith(f"Restarted Not given\nFDA: {rechal}")
    label = page.evaluate("async (c) => (await import('/ui/codes.js')).RECHAL[c]", rechal)
    assert label == "Does not apply"
    # OT before 2020 and HP after it are one type, named the same, each with FDA's code
    ot = _case_window(page, "faers", "9006006")["fields"]["Who reported"]
    hp = _case_window(page, "faers", "9013013")["fields"]["Who reported"]
    assert ot.replace("FDA: OT", "") == hp.replace("FDA: HP", "")


def test_no_outcome_is_never_non_serious_and_an_unknown_frequency_stays_fdas_code(opened):
    page = opened("/")
    words = page.evaluate(
        """async () => { const { noOutcome, freqWords } = await import('/ui/codes.js');
           return { exp: noOutcome('EXP'), per: noOutcome('PER'), none: noOutcome(null),
                    unknown: [freqWords('999'), freqWords('UD')],
                    perWeek: [freqWords('/wk'), freqWords('/WK')] }; }"""
    )
    assert words["exp"] != words["per"] == words["none"]
    assert not any(
        "non-serious" in w.lower() or "not serious" in w.lower()
        for w in words.values()
        if isinstance(w, str)
    )
    assert words["unknown"] == ["", ""]
    assert words["perWeek"][0] == words["perWeek"][1] != ""


def test_a_space_typed_in_a_box_stays_typing(opened):
    page = opened("/")
    page.click("#oa-find")
    page.keyboard.type("as p")
    assert page.input_value("#oa-find") == "as p"


def test_clicking_the_button_that_opened_a_menu_closes_it(opened):
    page = opened("/all/overview")
    page.click(".oa-filters-btn")
    page.wait_for_selector("#oa-filter-menu")
    page.click(".oa-filters-btn")
    page.wait_for_selector("#oa-filter-menu", state="detached")


def test_a_menu_opened_in_a_dialog_lives_in_it_so_it_can_be_clicked(opened):
    page = opened("/")
    inside = page.evaluate("""async () => {
      const { dialog, popMenu } = await import('/ui/app.js');
      const dlg = dialog('A dialog', '<button type="button" class="btn" id="opener">Open</button>');
      const item = '<button type="button" class="menu-item" id="item">One</button>';
      const menu = popMenu(dlg.querySelector('#opener'), item);
      const r = menu.querySelector('#item').getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return [menu.closest('dialog') === dlg, hit?.id];
    }""")
    assert inside == [True, "item"]


# the side panel and its folded rail --------------------------------------------------------------
# Every icon the two share sits at the same height, so a person reaches for one without looking
# whether the panel is open or folded.

PLACES = ("Home", "All cases", "Tables and SQL", "Products", "Settings")

PLACE_OF = """(labels) => Object.fromEntries(labels.map((label) => {
  const open = [...document.querySelectorAll('.side-panel .oa-side-row, .side-panel .oa-prod-head')]
    .find((el) => el.innerText.trim().toLowerCase() === label.toLowerCase());
  const folded = document.querySelector(`.oa-rail [aria-label="${label}"]`);
  const box = (el) => {
    const r = el.querySelector('.icon').getBoundingClientRect();
    return Math.round(r.top + r.height / 2);
  };
  const svg = (el) => el.querySelector('.icon svg').innerHTML;
  const same = !!open && !!folded && svg(open) === svg(folded);
  return [label, { open: open && box(open), folded: folded && box(folded), same }];
}))"""


def test_the_open_panel_and_the_rail_give_each_place_one_icon_at_one_height(opened):
    open_panel = opened("/", width=1440).evaluate(PLACE_OF, list(PLACES))
    folded = opened("/", width=1440, kept={"side": "closed"}).evaluate(PLACE_OF, list(PLACES))
    for label in PLACES:
        assert open_panel[label]["same"], label
        assert open_panel[label]["open"] == folded[label]["folded"], label


def test_the_rail_does_not_repeat_the_mark(opened):
    page = opened("/", width=1024)
    assert page.is_visible(".oa-rail") and page.query_selector(".oa-rail .mark") is None
    labels = page.eval_on_selector_all(
        ".oa-rail .oa-rail-item", "els => els.map((e) => e.getAttribute('aria-label'))"
    )
    assert labels == [
        "Open the side panel",
        "Home",
        "All cases",
        "Tables and SQL",
        "How we clean FAERS",
        "Products",
        "Settings",
    ]


# a host's page modules ---------------------------------------------------------------------------

HOST_JS = """
import { S, extend, framed, sidePlace, railPlace } from '/ui/app.js';
window.order = [];
extend({
  start: async () => {
    window.order.push('start');
    S.me = { first_name: 'Host' };
    S.release = await (await fetch('/api/release')).json();
  },
  routes: [(parts) => (parts[0] === 'hosted' ? { page: 'hosted' } : null)],
  addresses: [(parts) => parts[0] === 'hosted'],
  pages: {
    hosted: (r, app) => {
      window.order.push('hosted');
      app.innerHTML = framed('<main><h1>A host screen</h1></main>', 'hosted');
    },
  },
  after: [(r) => window.order.push(`after ${r.page}`)],
  slots: {
    'side-places': (here) => sidePlace('/hosted', 'admin', 'Hosted', here === 'hosted'),
    'rail-places': (here) => railPlace('/hosted', 'admin', 'Hosted', here === 'hosted'),
  },
});
"""


class HostAccess(LocalAccess):
    modules = ("/host-ui/host.js",)


@pytest.fixture
def host_site(explorer_app, licensed_release):
    app = explorer_app(licensed_release, access=HostAccess())
    app.add_api_route("/host-ui/host.js", lambda: Response(HOST_JS, media_type="text/javascript"))
    with served(app) as base:
        yield base


def test_a_hosts_module_starts_first_then_adds_its_screen_and_its_places(opened, host_site):
    page = opened("/", base=host_site)
    assert page.evaluate("window.order") == ["start", "after home"]
    assert page.inner_text("h1.greeting") == "Good morning, Host."
    rows = page.eval_on_selector_all(
        ".side-panel .oa-side-row", "els => els.map((e) => e.innerText.trim())"
    )
    assert rows[:5] == ["Home", "All cases", "Tables and SQL", "How we clean FAERS", "Hosted"]
    page.click('.side-panel a[href="/hosted"]')
    settle(page)
    assert (
        page.inner_text("h1") == "A host screen" and page.evaluate("location.pathname") == "/hosted"
    )
    assert page.evaluate("window.order")[-2:] == ["hosted", "after hosted"]


def test_every_page_draws_with_no_error(opened, site):
    page = opened("/")
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    for address in (
        "/",
        "/all/overview",
        "/product/ASPIRIN/overview",
        "/product/ASPIRIN/cases",
        "/product/valsartan/overview",
        "/product/VALSARTAN%20TEVA/cases",
        "/release",
        "/all/cases",
    ):
        page.goto(site + address)
        settle(page)
    page.click('tr[data-act="case"]')
    page.wait_for_selector("#oa-case .oa-case-lead")
    page.keyboard.press("Escape")
    page.click(".oa-filters-btn")
    page.wait_for_selector("#oa-filter-menu")
    assert errors == []


def _menu(page: Any, row: str) -> tuple[list[str], str]:
    """The choices a filter row offers, in order, and its footnote."""
    page.click(".oa-filters-btn")
    page.click(f'#oa-filter-menu [data-act="filter-row"][data-row="{row}"]')
    offered = page.eval_on_selector_all(
        f'[data-act="opt"][data-key="{row}"] .menu-choice-words', "cs => cs.map((c) => c.innerText)"
    )
    return offered, page.inner_text("#oa-filter-options .menu-footnote")


def test_the_age_menu_says_what_the_youngest_bands_hold(opened, demo_site):
    labels = {b["id"]: b["label"] for b in value("age-bands", "bands")}
    offered, note = _menu(opened("/all/overview", base=demo_site), "age")
    assert offered[:3] == [labels["0-27d"], labels["28d-1"], labels["under-1"]]
    assert "every case under 2" in note and f"{labels['under-1']} holds" in note
    assert "written as 0 years" in note and "negative age" in note


def test_the_sex_menu_offers_female_male_and_not_given_and_says_what_not_given_holds(
    opened, demo_site
):
    offered, note = _menu(opened("/all/overview", base=demo_site), "sex")
    assert sorted(offered) == ["Female", "Male", value("not-given", "label")]
    assert "NS" in note and "UNK" in note


def test_the_country_menu_names_the_union_and_offers_no_words_for_no_country(opened, demo_site):
    offered, _ = _menu(opened("/all/overview", base=demo_site), "country")
    assert "European Union, member state not given" in offered
    assert not [c for c in offered if "Specified" in c or c == "A1"]


def _shown(page: Any, selector: str) -> list[str]:
    return page.eval_on_selector_all(selector, "cs => cs.map((c) => c.innerText.split('\\n')[0])")


def test_the_country_and_company_boxes_list_the_name_typed_then_those_starting_so(opened):
    page = opened("/all/overview")
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="country"]')
    countries = "#oa-country-list .menu-choice-words"
    plain = _shown(page, countries)
    page.fill("#oa-menu-find", "n")  # Not given starts so; the others hold it
    assert _shown(page, countries) == ["Not given"] + [c for c in plain if c != "Not given"]
    page.fill("#oa-menu-find", "gb")  # a country's code, typed whole
    assert _shown(page, countries) == ["United Kingdom"]
    page.fill("#oa-menu-find", "")
    assert _shown(page, countries) == plain
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="sender"]')
    companies = "#oa-sender-list .menu-choice-words"
    plain = _shown(page, companies)
    page.fill("#oa-sender-find", "s")
    assert _shown(page, companies) == ["Sent straight to FDA", "BETA LABS LTD"]
    page.fill("#oa-sender-find", "")
    assert _shown(page, companies) == plain and len(plain) > 2


def test_the_release_tables_find_lists_the_table_named_as_typed_first(opened):
    page = opened("/release")
    page.fill("#oa-table-find", "demo_t")
    picked = _shown(page, ".oa-cat-group .oa-cat-pick code")
    assert picked[0] == "demo_T" and all("demo_t" in t.lower() for t in picked[:3])


def test_home_says_when_the_release_was_last_updated(opened, licensed_client):
    built = licensed_client.get("/api/release").json()["built_at"][:10]
    year, month, dayno = built.split("-")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    shown = f"Updated {dayno}-{months[int(month) - 1]}-{year}"
    assert shown in opened("/").inner_text(".oa-release-card")


def test_home_says_the_reports_are_mostly_postmarketing(opened):
    card = opened("/").inner_text(".oa-release-card")
    assert "Mostly postmarketing, from FDA's FAERS and the older AERS" in card


def test_the_release_card_is_three_lines(opened):
    page = opened("/")
    page.wait_for_selector(".oa-release-kind:has-text('Updated')")
    lines = page.eval_on_selector_all(
        ".oa-release-card > p:not(.oa-note)", "ps => ps.map((p) => p.innerText)"
    )
    assert len(lines) == 3, lines
    assert "probable duplicates left out." in lines[0] and "Updated" in lines[1]


def test_the_case_window_says_fda_publishes_no_narrative(opened):
    page = opened("/all/cases")
    page.click('tr[data-act="case"]:has-text("9004004")')
    page.wait_for_selector("#oa-case .oa-case-lead")
    assert "does not publish the reporter's narrative" in page.inner_text("#oa-case")


def test_the_custom_query_window_saves_with_save_and_run(opened):
    page = opened("/product/valsartan/overview")
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu .oa-filter-row[data-row="reactions"]')
    page.click('#oa-filter-menu [data-act="cmq-new"]')
    assert page.inner_text('[data-act="cmq-save"]') == "Save and run"


FIT = """() => {
  const el = document.documentElement;
  const box = (s) => document.querySelector(s)?.getBoundingClientRect();
  return { wide: el.scrollWidth > el.clientWidth, top: box('.oa-release-card')?.top ?? null };
}"""


@pytest.mark.parametrize("width", [320, 768, 1024, 1440])
def test_the_new_lines_fit_at_every_width_and_move_nothing(opened, width):
    page = opened("/", width=width)
    page.wait_for_selector(".oa-release-kind:has-text('Updated')")
    assert "postmarketing" in page.inner_text(".oa-release-card")
    before = page.evaluate(FIT)
    settle(page)
    assert not before["wide"]
    assert page.evaluate(FIT) == before
    page = opened("/all/cases", width=width)
    page.click('tr[data-act="case"]:has-text("9004004")')
    page.wait_for_selector("#oa-case .oa-case-lead")
    note = page.locator("#oa-case .oa-case-narrative")
    assert "narrative" in note.inner_text()
    assert not page.evaluate(FIT)["wide"]
    assert note.evaluate("(e) => e.scrollWidth <= e.clientWidth")
    page.click('[data-act="close-dialog"]')
    page = opened("/product/valsartan/overview", width=width)
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu .oa-filter-row[data-row="reactions"]')
    page.click('#oa-filter-menu [data-act="cmq-new"]')
    save = page.locator('[data-act="cmq-save"]')
    assert save.inner_text() == "Save and run"
    assert save.evaluate("(e) => e.getBoundingClientRect().right <= innerWidth")
    assert not page.evaluate(FIT)["wide"]
