"""The label flags in a browser: Label status in a drug's filters menu, the flags under a
case's reactions with each drug's Used for, their tips, About the label flags, and the Statistics
tab's Label column, Label status and cutoffs tick, over the fake release with invented flags
(`label_site`), and a release without flags (`site`). What the API answers is test_labels_api.py's.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import pytest

from open_altio.rulebook import value
from open_altio.testing.browser import settle
from open_altio.testing.fakelabelflags import LABELS, LABELS_AS_OF

OUTCOMES = value("explorer-label-flags", "outcomes")
UNEXPECTED = value("explorer-label-flags", "unexpected_only")
W = value("explorer-label-words", "words")  # each flag's word
WHY = value("explorer-label-words", "reasons")  # why a flag was not compared with the label
SUSPECTED = (
    "FAERS reports are suspected events, not proven reactions. "
    "The flag only says whether today's label lists the event."
)
ASPIRIN = [("product", "acetylsalicylic acid")]
PAGE = "/product/acetylsalicylic%20acid"

TICKS = """() => [...document.querySelectorAll('[data-act="opt-label"]')].map((b) => [
  b.dataset.v, b.getAttribute('aria-checked') === 'true',
  +b.querySelector('.choice-count').innerText])"""
# where everything outside the menu sits, from the page's top: the toolbar, the strip, the list
# and its columns (a press may scroll the page; that moves nothing on it)
PLACES = """() => {
  const top = document.querySelector('.product-title').getBoundingClientRect().top;
  return [...document.querySelectorAll(
    '.oa-toolbar, #oa-strip, #oa-body, .oa-cases thead th, .oa-stats thead th')].map((e) => {
    const r = e.getBoundingClientRect();
    return [Math.round(r.left), Math.round(r.top - top), Math.round(r.width)];
  });
}"""


def day(setid: str) -> str:
    """A fake label's date as the page writes it."""
    return LABELS[setid].strftime("%d-%b-%Y")


def as_of() -> str:
    """The day the fake release's labels are as of, as the page writes it (rule label-refresh)."""
    return LABELS_AS_OF.strftime("%d-%b-%Y")


def cases(client, *query: tuple[str, str]) -> int:
    return client.get(f"/api/summary?{urlencode([*ASPIRIN, *query])}").json()["cases"]


def label_menu(page: Any) -> None:
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="label"]')
    settle(page)


def press(page: Any, selector: str) -> None:
    page.click(selector)
    settle(page)


def open_case(page: Any, base: str, key: str) -> Any:
    page.goto(base + "/all/cases")
    settle(page)
    keys = page.eval_on_selector_all(
        'tr[data-act="case"] .case-key', "es => es.map((e) => e.innerText)"
    )
    page.query_selector_all('tr[data-act="case"]')[keys.index(key)].click()
    page.wait_for_selector("#oa-case .oa-case-lead")
    settle(page)
    return page.query_selector("#oa-case")


# Label status in a product's filters menu --------------------------------------------------------


def test_a_product_opens_on_every_case_with_every_label_tick_on(opened, label_site, label_client):
    page = opened(f"{PAGE}/cases", base=label_site)
    assert page.inner_text("#oa-countline").startswith(f"{cases(label_client):,} cases")
    assert page.inner_text("#oa-strip").startswith("No filters")
    label_menu(page)
    counts = label_client.get(f"/api/labels/cases?{urlencode(ASPIRIN)}").json()["cases"]
    assert page.evaluate(TICKS) == [[k, True, counts.get(k, 0)] for k in OUTCOMES]
    assert page.get_attribute('[data-act="label-unexpected"]', "aria-pressed") == "false"
    rows = page.eval_on_selector_all(".oa-filter-row", "rs => rs.map((r) => r.dataset.row)")
    assert rows.index("label") == rows.index("reactions") + 1  # Label status after Reactions


def test_unexpected_only_is_one_click_that_ticks_the_unexpected_flags(
    opened, label_site, label_client
):
    page = opened(f"{PAGE}/cases", base=label_site)
    label_menu(page)
    press(page, '[data-act="label-unexpected"]')
    assert [k for k, on, _ in page.evaluate(TICKS) if on] == [
        k for k in OUTCOMES if k in UNEXPECTED
    ]
    assert page.get_attribute('[data-act="label-unexpected"]', "aria-pressed") == "true"
    # the footnote says what unexpected means, in FDA's words
    note = page.inner_text("#oa-filter-options .menu-footnote")
    assert 'unexpected when it is "not listed in the current labeling' in note
    assert "(21 CFR 314.80)" in note
    expected = cases(label_client, *[("label", k) for k in UNEXPECTED])
    assert 0 < expected < cases(label_client)
    assert page.inner_text("#oa-countline").startswith(f"{expected:,} cases")
    assert page.inner_text("#oa-strip .oa-strip-name") == "Label status"
    # Clear all goes back to every tick on
    page.keyboard.press("Escape")
    press(page, '[data-act="unfilter-all"]')
    assert page.inner_text("#oa-countline").startswith(f"{cases(label_client):,} cases")


def test_label_status_combines_with_the_other_filters(opened, label_site, label_client):
    page = opened(f"{PAGE}/cases", base=label_site)
    label_menu(page)
    press(page, '[data-act="opt-label"][data-v="on_label"]')
    page.hover('#oa-filter-menu [data-act="filter-row"][data-row="outcome"]')
    press(page, '[data-act="opt"][data-key="outcome"][data-v="OT"]')
    kept = [("label", k) for k in OUTCOMES if k != "on_label"] + [("outcome", "OT")]
    assert page.inner_text("#oa-countline").startswith(f"{cases(label_client, *kept):,} cases")
    names = page.eval_on_selector_all(
        "#oa-strip .oa-strip-name", "ns => ns.map((n) => n.innerText)"
    )
    assert names == ["Label status", "Outcome"]
    page.hover('#oa-filter-menu [data-act="filter-row"][data-row="label"]')
    settle(page)
    assert "your other filters: Outcome" in page.inner_text("#oa-filter-options .menu-footnote")
    counts = label_client.get(
        f"/api/labels/cases?{urlencode(ASPIRIN + [('outcome', 'OT')])}"
    ).json()
    assert [n for _, _, n in page.evaluate(TICKS)] == [counts["cases"].get(k, 0) for k in OUTCOMES]


def test_filtering_by_label_moves_nothing_on_the_page(opened, label_site):
    page = opened(f"{PAGE}/cases", base=label_site)
    before = page.evaluate(PLACES)
    label_menu(page)
    press(page, '[data-act="label-unexpected"]')
    press(page, '[data-act="opt-label"][data-v="uncertain"]')
    assert page.evaluate(PLACES) == before
    page.keyboard.press("Escape")
    press(page, '[data-act="unfilter-all"]')
    assert page.evaluate(PLACES) == before


# the case dialog -----------------------------------------------------------------------------


def test_each_reaction_shows_one_quiet_line_per_suspect_drug_with_its_flag(opened, label_site):
    page = opened("/", base=label_site)
    window = open_case(page, label_site, "9021021")
    assert "Reactions, and each suspect's label" in window.text_content()
    lines = page.evaluate("""() => Object.fromEntries(
      [...document.querySelectorAll('#oa-case .oa-reac-labelled')]
      .map((li) => [li.firstChild.textContent.trim(),
        [...li.querySelectorAll('.oa-label-line')]
          .map((l) => l.innerText.replace(/\\s+/g, ' '))]))""")
    assert lines == {
        "Haemorrhage": [
            f"Aspirin {W['on_label']}, warnings and precautions",
            f"warfarin {W['on_label']}, boxed warning",
        ],
        "Nausea": [f"Aspirin {W['not_on_label']}", f"warfarin {W['related']}"],
    }
    links = window.eval_on_selector_all(
        ".oa-label-sources a", "as => as.map((a) => [a.innerText, a.href])"
    )
    # each label by its product, its ingredients and its date, saying where the link goes, once
    assert page.inner_text("#oa-case .oa-label-sources").startswith(
        "Against today's US prescription labels: Aspirinex (aspirin) label"
    )
    assert links == [
        [
            f"Aspirinex (aspirin) label, {day('aspirin-by-mouth')}, on DailyMed",
            "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=aspirin-by-mouth&version=1",
        ],
        [
            f"Warfarex (warfarin) label, {day('warfarin-by-mouth')}, on DailyMed",
            "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=warfarin-by-mouth&version=1",
        ],
    ]
    # each link opens the version the flags were read from, and its tip says so, with the time
    # the labels are checked against DailyMed each day (rule label-refresh)
    tips = window.eval_on_selector_all(".oa-label-sources a", "as => as.map((a) => a.dataset.tip)")
    checked = value("label-refresh", "checked_at_utc")
    assert (
        tips
        == [
            "The version these flags were read from. Labels are checked against DailyMed every day "
            f"at {checked} UTC; the newest may differ until then."
        ]
        * 2
    )


def test_the_drugs_table_says_what_each_drug_was_used_for_as_the_report_says(opened, label_site):
    page = opened("/", base=label_site)
    open_case(page, label_site, "9005005")
    heads = page.eval_on_selector_all(
        "#oa-case .oa-case-drugs th", "hs => hs.map((h) => h.innerText.toLowerCase())"
    )
    at = heads.index("used for")  # after the ingredients, FDA's active ingredient under them
    assert heads[at - 1] == "ingredient"
    used = page.eval_on_selector_all(
        "#oa-case .oa-case-drugs tbody tr:not(.oa-case-divider)",
        "(rs, at) => rs.map((r) => [r.cells[1].innerText, r.cells[at].innerText])",
        at,
    )
    assert used == [["ASPIRIN", "Pain"], ["OMEPRAZOLE", "Dyspepsia"]]
    assert page.query_selector("#oa-case h3:text-is('Indications')") is None  # one place only
    # a drug the report gives no indication for: Not given, grey, with its tip
    open_case(page, label_site, "9021021")
    given = page.query_selector_all(f"#oa-case .oa-case-drugs tbody tr td:nth-child({at + 1})")
    assert [g.inner_text() for g in given] == ["Pain", "Pain", "Not given"]
    blank = given[2].query_selector(".oa-faint")
    assert (
        blank.get_attribute("data-tip") == "FAERS gives no indication for this drug on this report"
    )


def test_a_flags_tip_says_how_it_was_decided_its_labels_date_and_what_a_report_is(
    opened, label_site
):
    page = opened("/", base=label_site)
    open_case(page, label_site, "9021021")
    flag = page.locator("#oa-case .oa-label-line [data-flag]").first
    flag.scroll_into_view_if_needed()  # a scroll hides the tip, so scroll first, then hover
    page.wait_for_timeout(100)
    flag.hover()
    tip = page.query_selector("#oa-tip")
    assert tip.is_visible() and page.evaluate("() => !!document.querySelector('#oa-case #oa-tip')")
    assert tip.inner_text() == (
        f"{W['on_label']} on today's label, in warnings and precautions. Decided by rule. "
        f"Aspirinex (aspirin) label, {day('aspirin-by-mouth')}, on DailyMed. Labels as of "
        f"{as_of()}. {SUSPECTED}"
    )
    # a grey flag: a model's suggestion nobody has checked is Can't tell
    open_case(page, label_site, "9005005")
    flag = page.query_selector('#oa-case [data-flag="uncertain"]')
    assert "oa-faint" in flag.get_attribute("class")
    flag.hover()
    assert page.inner_text("#oa-tip").startswith(f"{W['uncertain']}: the rules could not settle")
    # read on another form's label: compared there, and the line and the tip say which; a record
    # with no RxNorm code was not compared, and says why
    open_case(page, label_site, "5100010")
    lines = page.eval_on_selector_all(
        "#oa-case .oa-label-line", "ls => ls.map((l) => l.innerText.replace(/\\s+/g, ' '))"
    )
    assert lines == [
        f"BLEOMYCIN SULFATE {W['no_label']} {WHY['no_label']}",
        f"DOXORUBICIN {W['on_label']} on the injected label; no by-mouth label",
    ]
    assert "BLEOMYCIN SULFATE: no label found" in page.inner_text("#oa-case .oa-label-sources")
    page.locator("#oa-case .oa-label-line").nth(1).locator("[data-flag]").hover()
    assert page.inner_text("#oa-tip").startswith(
        f"{W['on_label']} on the injected label; no by-mouth label. It names it in adverse "
        "reactions. Decided by rule."
    )
    # Forms differ is compared, and gives each form's answer in the flags' words
    open_case(page, label_site, "9013013")
    line = page.inner_text("#oa-case .oa-label-line")
    assert line.replace("\n", " ").endswith(
        f"{W['on_label']} on the by-mouth label, {W['not_on_label'].lower()} on the skin label"
    )


def test_about_the_label_flags_leads_with_what_a_report_is_then_says_each_flag(opened, label_site):
    page = opened(f"{PAGE}/cases", base=label_site)
    label_menu(page)
    press(page, '#oa-filter-options [data-act="about"]')
    about = page.query_selector("#oa-about")
    assert about.query_selector(".dialog-body p").inner_text() == SUSPECTED
    flags = about.eval_on_selector_all(
        ".oa-about-list:first-of-type dt", "ds => ds.map((d) => d.innerText)"
    )
    # each flag's word, with the reason it was not compared under it
    assert flags == [W[k] + (f"\n{WHY[k]}" if k in WHY else "") for k in OUTCOMES]
    assert (
        "How each was decided" in about.text_content() and "today's label" in about.text_content()
    )
    page.keyboard.press("Escape")
    open_case(page, label_site, "9021021")
    press(page, '#oa-case [data-act="about"]')
    assert page.is_visible("#oa-about")


def test_one_function_names_every_label_by_product_ingredients_forms_and_date(opened, label_site):
    """labelName, on the parts labelnames.py gives: two products, one label, labels by form."""
    page = opened("/", base=label_site)
    named = page.evaluate("""async () => {
      const { labelName } = await import('/ui/labels.js');
      const label = (product, ingredients, forms, date) => labelName(
        { setid: 's', product, ingredients, forms, date });
      return [
        label('Diovan', ['valsartan'], [], '2026-08-11'),
        label('Diovan HCT', ['hydrochlorothiazide', 'valsartan'], [], '2026-02-13'),
        label(null, ['warfarin'], [], '2023-08-08'),
        label('Hemady', ['dexamethasone'], ['by_mouth', 'under_tongue'], '2026-01-09'),
        label(null, ['dexamethasone'], ['injected'], '2026-06-30'),
      ];
    }""")
    assert named == [
        "Diovan (valsartan) label, 11-Aug-2026",
        "Diovan HCT (hydrochlorothiazide and valsartan) label, 13-Feb-2026",
        "warfarin label, 08-Aug-2023",
        "Hemady (dexamethasone) by-mouth and under-the-tongue label, 09-Jan-2026",
        "dexamethasone injected label, 30-Jun-2026",
    ]


# phones, tablets and desktops -------------------------------------------------------------------


# the flags' words: whether the label lists the reaction, and nothing else -----------------------

UNDER = """() => {
  const line = document.querySelector('#oa-case [data-flag="no_label"]').closest('.oa-label-line');
  const word = line.querySelector('[data-flag]').getBoundingClientRect();
  const why = line.querySelector('.oa-flag-reason');
  const at = why.getBoundingClientRect();
  return [why.innerText, why.classList.contains('oa-faint'), at.top >= word.bottom - 1,
    Math.abs(at.left - line.getBoundingClientRect().left) <= 1];
}"""


@pytest.mark.parametrize("width", [390, 1440])
def test_every_flag_speaks_of_listing_and_not_compared_says_why_under_it(opened, label_site, width):
    """The words of rule explorer-label-words wherever a flag shows, on a phone and a desktop:
    no flag's word says related, Not compared has its reason in grey under its line, flush with
    it, and Forms differ gives each form's answer inside the Label column."""
    page = opened("/", base=label_site, width=width)
    open_case(page, label_site, "5100010")  # BLEOMYCIN SULFATE has no RxNorm code
    assert page.evaluate(UNDER) == [WHY["no_label"], True, True, True]
    page.keyboard.press("Escape")
    # Label status: each flag's word, Not compared with its reason under it
    page.goto(f"{label_site}{PAGE}/cases")
    settle(page)
    label_menu(page)
    ticks = page.eval_on_selector_all(
        '[data-act="opt-label"] .menu-choice-words',
        "ws => ws.map((w) => w.innerText.replace(/\\s+/g, ' '))",
    )
    assert ticks == [f"{W[k]} {WHY[k]}" if k in WHY else W[k] for k in OUTCOMES]
    page.keyboard.press("Escape")
    # the Statistics tab: Forms differ's answers wrap inside the column, never cut
    page.goto(f"{label_site}{PAGE}/statistics")
    settle(page)
    split = page.locator('.oa-stats td.oa-label-col:has([data-flag="forms_differ"])')
    assert split.inner_text().replace("\n", " ") == (
        f"{W['on_label']} on the by-mouth label, {W['not_on_label'].lower()} on the skin label"
    )
    assert split.evaluate("(c) => c.scrollWidth <= c.clientWidth")
    # forms with the same answer are named together
    grouped = page.evaluate("""async () => (await import('/ui/labels.js')).formsSplit({ families: [
      ['by_mouth', 'on_label'], ['eye', 'not_on_label'], ['injected', 'not_on_label'],
      ['under_tongue', 'on_label']] })""")
    assert grouped == (
        f"{W['on_label'].lower()} on the by-mouth and under-the-tongue labels, "
        f"{W['not_on_label'].lower()} on the eye and injected labels"
    )
    shown = page.eval_on_selector_all(".oa-stats [data-flag]", "fs => fs.map((f) => f.innerText)")
    assert shown and not any("related" in words.lower() for words in [*shown, *ticks])


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_label_status_and_the_case_lines_fit_every_width(opened, label_site, width):
    page = opened(f"{PAGE}/cases", base=label_site, width=width)
    label_menu(page)
    inside = """(sel) => { const r = document.querySelector(sel).getBoundingClientRect();
      return r.left >= 0 && r.right <= innerWidth && r.width > 0; }"""
    assert page.evaluate(inside, "#oa-filter-menu")
    assert all(page.is_visible(f'[data-act="opt-label"][data-v="{k}"]') for k in OUTCOMES)
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    page.keyboard.press("Escape")
    open_case(page, label_site, "9021021")
    assert page.evaluate(inside, "#oa-case") and page.evaluate(inside, "#oa-case .oa-label-line")
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


# a release without flags ----------------------------------------------------------------------


def test_a_release_without_flags_shows_no_label_status_and_no_lines(opened, site):
    page = opened(f"{PAGE}/cases")
    page.click(".oa-filters-btn")
    rows = page.eval_on_selector_all(".oa-filter-row", "rs => rs.map((r) => r.dataset.row)")
    assert "label" not in rows
    page.keyboard.press("Escape")
    window = open_case(page, site, "9021021")
    assert window.query_selector(".oa-label-line, .oa-label-sources, [data-act='about']") is None
    assert (
        "Used for" in window.text_content() and "each suspect's label" not in window.text_content()
    )


# the Statistics tab -----------------------------------------------------------------------------

SHOWN = """() => [...document.querySelectorAll('.oa-stats tbody tr')].map((r) => [
  r.querySelector('th').innerText, r.querySelector('[data-flag]')?.dataset.flag])"""


def test_statistics_label_column_sits_after_reaction_and_sorts_furthest_from_the_label_first(
    opened, label_site, label_client
):
    page = opened(f"{PAGE}/statistics", base=label_site)
    assert page.locator(".oa-stats tbody tr th").count() == 5  # the tab starts on every pair
    heads = page.eval_on_selector_all(".oa-stats thead th", "hs => hs.map((h) => h.innerText)")
    assert [h.title() for h in heads[:3]] == ["Reaction", "Label", "Cases"]
    shown = page.evaluate(SHOWN)
    assert len(shown) == 5 and all(flag for _, flag in shown)  # every row flagged
    # the statistics count any product containing aspirin, so every report is read on
    # aspirin's own label, the one coded as a combination too: one label, named by its product
    # and ingredients, with no forms
    assert page.inner_text(".oa-label-lead") == (
        "Label compares each reaction with today's US prescription label: Aspirinex (aspirin) "
        f"label, {day('aspirin-by-mouth')}, on DailyMed. About the label flags"
    )
    page.keyboard.press("Escape")
    press(page, '[data-act="stat-sort"][data-v="label"]')
    ranks = [OUTCOMES.index(flag) for _, flag in page.evaluate(SHOWN)]
    assert ranks == sorted(ranks)
    page.hover('.oa-stats [data-flag="on_label"]')
    assert page.inner_text("#oa-tip").startswith(
        f"{W['on_label']} on today's label, in warnings and precautions."
    )


def test_statistics_label_status_narrows_the_list_on_the_strip_and_moves_nothing(
    opened, label_site, label_client
):
    page = opened(f"{PAGE}/statistics", base=label_site)
    page.click('.oa-toolbar [data-act="stat-filters"]')
    settle(page)
    counts = label_client.get(
        f"/api/statistics?{urlencode(ASPIRIN).replace('product', 'ingredient')}"
    ).json()["label"]["counts"]
    ticks = page.evaluate("""() => [...document.querySelectorAll('[data-act="stat-label"]')]
      .map((b) => [b.dataset.v, b.getAttribute('aria-checked') === 'true',
        +b.querySelector('.choice-count').innerText])""")
    assert ticks == [[k, True, counts.get(k, 0)] for k in OUTCOMES]
    assert "(21 CFR 314.80)" in page.inner_text("#oa-label-options .menu-footnote")
    before = page.evaluate(PLACES)
    press(page, '[data-act="stat-unexpected"]')
    assert [flag for _, flag in page.evaluate(SHOWN)] and all(
        flag in UNEXPECTED for _, flag in page.evaluate(SHOWN)
    )
    assert len(page.evaluate(SHOWN)) == 4
    assert page.inner_text("#oa-strip .oa-strip-name") == "Label status"
    assert page.evaluate(PLACES)[:2] == before[:2]  # the toolbar and the strip stay put
    page.keyboard.press("Escape")
    press(page, '#oa-strip [data-act="stat-unfilter"]')
    assert len(page.evaluate(SHOWN)) == 5


def test_a_release_without_flags_has_no_label_column_on_statistics(opened, stats_site):
    page = opened("/product/warfarin/statistics", base=stats_site)
    heads = page.eval_on_selector_all(".oa-stats thead th", "hs => hs.map((h) => h.innerText)")
    assert heads and "Label" not in [h.title() for h in heads]
    assert page.locator('[data-act="stat-filters"]').count() == 0


def test_the_cutoffs_tick_is_the_screens_lists_choice_of_every_pair_or_the_passing_ones(
    opened, label_site
):
    page = opened(f"{PAGE}/statistics", base=label_site)
    page.click('.oa-toolbar [data-act="stat-filters"]')
    settle(page)
    tick = '[data-act="stat-pass"]'
    assert page.get_attribute(tick, "aria-checked") == "false"  # the list opens on every pair
    assert "Every drug and reaction" in page.inner_text("#oa-countline")
    assert page.locator(".oa-stats tbody tr th").count() == 5
    press(page, tick)
    assert page.get_attribute(tick, "aria-checked") == "true"
    assert page.inner_text("#oa-countline").endswith("Only those that pass EBGM's threshold")
    assert page.locator(".oa-stats tbody tr th").count() == 0  # the fake's EBGM passes none
    press(page, tick)
    assert page.locator(".oa-stats tbody tr th").count() == 5


def test_the_methods_page_says_the_day_the_labels_are_as_of(opened, label_site):
    page = opened("/methods", base=label_site)
    page.wait_for_selector(".oa-rules .oa-subtitle")
    assert f"Labels as of {as_of()}" in page.inner_text(".oa-rules .oa-subtitle")
