"""The case window in a browser, at a phone's and a desktop's width: a cleaned value sits over
FDA's with a link to the rule that cleaned it (rule legacy-country for a country, drug-names for a
drug's ingredients, drug-route for its route families), codes that name no country of today carry
their note and FDA's words for no country read as not given; FDA system says it is the system of
the case's latest version and points to the received-date filter; a copy in a group of duplicates
links the copies it names and shows both receipt dates; a report with no usable drug or reaction
that gives a serious outcome carries its flag; the address names the case open, so a bookmark
opens it again; and the window reads in a reviewer's order, the suspect drugs before the drugs
taken alongside them.
"""

from __future__ import annotations

from typing import Any

import pytest

from open_altio.rulebook import value
from open_altio.testing.browser import settle

WIDTHS = (390, 1440)


def field(page: Any, label: str) -> str:
    """The text of the case window's value under `label`."""
    return page.evaluate(
        """(label) => [...document.querySelectorAll('#oa-case dt')]
          .find((dt) => dt.textContent === label)?.nextElementSibling.textContent ?? null""",
        label,
    )


def rule_links(page: Any, scope: str = "#oa-case") -> dict[str, str]:
    """Each rule link's words in `scope`, with the rule it opens."""
    return page.eval_on_selector_all(
        f"{scope} a.oa-rule-tag",
        "as => Object.fromEntries(as.map((a) => [a.textContent, a.getAttribute('href')]))",
    )


def sideways(page: Any) -> bool:
    return page.evaluate("document.scrollingElement.scrollWidth > window.innerWidth")


def case_param(page: Any) -> str | None:
    return page.evaluate("new URLSearchParams(location.search).get('case')")


@pytest.mark.parametrize("width", WIDTHS)
def test_an_aers_country_shows_its_name_and_code_with_fdas_name_and_its_rule_under(opened, width):
    page = opened("/all/cases?case=5100005&era=legacy", width=width)
    country = field(page, "Country")
    assert country.startswith("United States (US)") and "FDA: UNITED STATES" in country
    assert rule_links(page)["fixed rule: legacy-country"] == "/methods?open=legacy-country"
    assert not sideways(page)


def test_a_faers_country_is_fdas_own_code_and_names_no_rule(opened):
    page = opened("/all/cases?case=9005005&era=faers")
    assert field(page, "Country") == "United States (US)"
    assert "fixed rule: legacy-country" not in rule_links(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_a_code_of_a_country_that_no_longer_exists_carries_its_name_and_note(
    opened, dup_site, width
):
    noted = value("legacy-country", "noted_codes")["YU"]
    page = opened("/all/cases?case=7731004&era=faers", base=dup_site, width=width)
    country = field(page, "Country")
    assert country.startswith(f"{noted['name']} (YU)") and noted["note"].strip() in country
    assert not sideways(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_fdas_words_for_no_country_read_as_not_given_with_fdas_text_kept(opened, dup_site, width):
    written = value("country-not-given", "not_countries")[0]
    page = opened("/all/cases?case=7731002&era=faers", base=dup_site, width=width)
    assert field(page, "Country").startswith(f"Not given FDA: {written}")
    assert rule_links(page)["fixed rule: country-not-given"] == "/methods?open=country-not-given"
    assert " in " not in page.inner_text(".oa-case-lead").split(".")[0]  # no country in the lead
    page.click('#oa-case [data-act="close-dialog"]')
    settle(page)
    row = page.locator("tr[data-act='case']", has_text="7731002")
    assert row.locator("td").nth(4).inner_text() == "Not given"
    assert not sideways(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_fda_system_is_the_latest_versions_and_points_to_the_received_filter(opened, width):
    page = opened("/all/cases?case=5100010&era=faers", width=width)  # carried from AERS
    system = field(page, "FDA system")
    assert system.startswith("FAERS") and "latest version" in system and "15-Aug-2012" in system
    assert rule_links(page)["fixed rule: latest-version"] == "/methods?open=latest-version"
    page.click('#oa-case [data-act="close-dialog"]')
    page.click(".oa-filters-btn")
    page.click('.oa-filter-row[data-row="era"]')
    note = page.inner_text(".oa-era-note")
    assert "latest version" in note and "carried from AERS into FAERS" in note
    page.click('.oa-era-note [data-act="filter-goto"]')
    assert page.text_content("#oa-filter-options .menu-heading") == "Received by FDA"
    assert not sideways(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_a_set_aside_copy_links_the_copy_shown_and_opens_it(opened, width):
    page = opened("/all/cases?case=9020020&era=faers", width=width)
    links = page.eval_on_selector_all(
        "#oa-case .oa-case-why [data-act='case-jump']", "bs => bs.map((b) => b.textContent)"
    )
    assert links == ["9021021"]
    page.click("#oa-case .oa-case-why [data-act='case-jump']")
    settle(page)
    assert page.inner_text("#oa-case .dialog-title").startswith("Case 9021021")
    assert case_param(page) == "9021021"
    assert not sideways(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_the_shown_copy_links_its_copies_and_labels_both_receipt_dates(opened, width):
    page = opened("/all/cases?case=9021021&era=faers", width=width)
    links = page.eval_on_selector_all(
        "#oa-case .oa-case-why [data-act='case-jump']", "bs => bs.map((b) => b.textContent)"
    )
    assert links == ["9020020"]
    assert field(page, "First received (any copy)") == "10-Feb-2019"
    assert field(page, "First received (this copy)").startswith("15-May-2026")
    assert "(any copy)" in page.inner_text(".oa-case-lead")
    assert not sideways(page)


def test_a_case_in_no_group_has_one_receipt_date(opened):
    page = opened("/all/cases?case=9005005&era=faers")
    assert field(page, "First received (any copy)") is None
    assert field(page, "First received").startswith("15-Jan-2019")


@pytest.mark.parametrize("width", WIDTHS)
def test_a_case_number_alone_in_the_address_opens_it_set_aside_or_not(opened, width):
    page = opened("/all/cases?case=9020020", width=width)
    assert page.inner_text("#oa-case .dialog-title").startswith("Case 9020020")
    assert "9021021" in page.inner_text("#oa-case .oa-case-why")
    page.click('#oa-case [data-act="close-dialog"]')
    settle(page)
    assert case_param(page) is None  # closed, the address no longer names it
    assert not sideways(page)


def test_a_case_not_in_the_release_says_so(opened):
    page = opened("/all/cases?case=no-such-case")
    assert "no case no-such-case in this release" in page.inner_text("#oa-case")
    assert rule_links(page)["Cases FDA deleted"] == "/methods?open=deleted-cases"


def test_opening_a_case_from_the_list_names_it_in_the_address(opened):
    page = opened("/all/cases")
    first = page.inner_text("tr[data-act='case'] .case-key")
    page.click("tr[data-act='case']")
    settle(page)
    assert case_param(page) == first
    page.click('#oa-case [data-act="case-step"][data-v="1"]')
    settle(page)
    assert case_param(page) != first


def test_a_rule_link_closes_the_window_and_opens_the_rule(opened):
    page = opened("/all/cases?case=5100005&era=legacy")
    page.click('#oa-case a.oa-rule-tag[href="/methods?open=legacy-country"]')
    settle(page)
    assert page.query_selector("#oa-case") is None
    assert page.evaluate("location.pathname + location.search") == "/methods?open=legacy-country"


@pytest.mark.parametrize("width", WIDTHS)
def test_a_report_with_no_usable_drug_or_reaction_and_a_serious_outcome_is_flagged(
    opened, dup_site, width
):
    page = opened("/all/cases?case=7731001&era=faers", base=dup_site, width=width)
    flag = page.text_content("#oa-case .oa-case-flag")
    assert "serious outcome reported" in flag
    assert rule_links(page, "#oa-case .oa-case-flag") == {
        "fixed rule: no-drug-or-reaction": "/methods?open=no-drug-or-reaction"
    }
    page.goto(dup_site + "/all/cases?case=7731002&era=faers")  # no serious outcome: no flag
    settle(page)
    assert page.query_selector("#oa-case .oa-case-flag") is None
    assert not sideways(page)


def test_the_case_list_flags_the_same_reports(opened, dup_site):
    page = opened("/all/cases", base=dup_site)
    flagged = page.eval_on_selector_all(
        "tr[data-act='case']:has(.oa-chip-serious) .case-key", "ks => ks.map((k) => k.textContent)"
    )
    assert {"7731001", "7731003"} <= set(flagged) and "7731002" not in flagged


@pytest.mark.parametrize("width", WIDTHS)
def test_each_drug_shows_its_ingredients_and_where_they_came_from(opened, width):
    page = opened("/all/cases?case=9004004&era=faers", width=width)  # BAYER LOW DOSE
    cells = page.eval_on_selector_all(
        "#oa-case .oa-case-drugs tbody td:nth-child(3)", "ts => ts.map((t) => t.innerText)"
    )
    # FDA's active ingredient under ours, then where ours came from
    assert cells == ["Acetylsalicylic acid\nFDA: ASPIRIN\nDiAna, via FDA's active ingredient"]
    assert rule_links(page, "#oa-case .oa-case-drugs")["DiAna, via FDA's active ingredient"] == (
        "/methods?open=drug-names"
    )
    page.goto(page.url.split("/all")[0] + "/all/cases?case=9210006&era=faers")  # VALSARTAN TEVA
    settle(page)
    assert page.inner_text("#oa-case .oa-case-drugs tbody td:nth-child(3)") == (
        "No ingredient\nFDA: Not given"
    )
    page.goto(page.url.split("/all")[0] + "/all/cases?case=9210001&era=faers")
    settle(page)
    assert page.inner_text("#oa-case .oa-case-drugs tbody td:nth-child(3)").endswith(
        "DiAna dictionary"
    )
    assert not sideways(page)


def route_cells(page: Any) -> list[str]:
    """The text of each drug's cell under the drug table's Route heading."""
    return page.evaluate(
        """() => {
          const table = document.querySelector('#oa-case .oa-case-drugs');
          const heads = [...table.querySelectorAll('thead th')];
          const i = heads.findIndex((th) => th.textContent === 'Route');
          return [...table.querySelectorAll('tbody tr')].map((tr) => tr.children[i].textContent);
        }"""
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_each_drug_shows_its_route_family_over_fdas_route_with_its_rule(opened, label_site, width):
    """One family, or what the record could be when its fields allow several, with FDA's route
    under it and the rule that read them; FDA's route alone where nothing is known."""
    page = opened("/all/cases?case=9004004&era=faers", base=label_site, width=width)
    assert route_cells(page) == ["By mouth FDA: ORALFrom FDA's route"]
    assert rule_links(page, "#oa-case .oa-case-drugs")["From FDA's route"] == (
        "/methods?open=drug-route"
    )
    page.goto(f"{label_site}/all/cases?case=9110011&era=faers")
    settle(page)
    assert route_cells(page) == [
        "Could be by mouth or on the skin FDA: ORALIts route, dose form and name disagree"
    ]
    page.goto(f"{label_site}/all/cases?case=9013013&era=faers")
    settle(page)
    assert route_cells(page) == ["ORAL"]
    assert not sideways(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_the_flag_stays_inside_the_window_and_its_cell(opened, dup_site, width):
    page = opened("/all/cases?case=7731001&era=faers", base=dup_site, width=width)
    assert page.evaluate(
        """() => { const f = document.querySelector('#oa-case .oa-case-flag .oa-chip');
          const box = document.querySelector('#oa-case .dialog-head').getBoundingClientRect();
          return f.getBoundingClientRect().right <= box.right; }"""
    )
    page.click('#oa-case [data-act="close-dialog"]')
    settle(page)
    assert page.evaluate(
        """() => [...document.querySelectorAll('.oa-cases .oa-chip-serious')].every((c) => {
          const cell = c.closest('td').getBoundingClientRect(), chip = c.getBoundingClientRect();
          return chip.right <= cell.right + 1; })"""
    )


# The case window's patient, from the release of fakefda.DEMOGRAPHICS_STORY: each cleaned value
# over FDA's (rules sex-codes, age-in-years, weight-in-kg, age-bands, eu-member-state).
@pytest.mark.parametrize("width", WIDTHS)
def test_an_eu_case_shows_the_member_state_of_an_earlier_version_with_its_rule(
    opened, demo_site, width
):
    page = opened("/all/cases?case=7906001&era=faers", base=demo_site, width=width)
    country = field(page, "Country")
    assert (
        country.startswith("Germany (DE) FDA: EU")
        and "From an earlier version of this case" in country
    )
    assert rule_links(page)["fixed rule: eu-member-state"] == "/methods?open=eu-member-state"
    assert not sideways(page)


def test_an_eu_case_with_no_earlier_member_state_is_named_as_the_union(opened, demo_site):
    page = opened("/all/cases?case=7906004&era=faers", base=demo_site)
    noted = value("legacy-country", "noted_codes")["EU"]
    assert noted["name"] == "European Union, member state not given"
    assert field(page, "Country").startswith(f"{noted['name']} (EU)")
    assert "fixed rule: eu-member-state" not in rule_links(page)
    assert field(page, "Where it happened") == f"{noted['name']} FDA: EU"


@pytest.mark.parametrize(
    ("caseid", "label", "shown"),
    [
        ("7901003", "Sex", "Not given FDA: NS"),
        ("7901001", "Sex", "Female FDA: F"),
        ("7902004", "Age", "Not given FDA: -1 YR"),
        ("7902006", "Age", "Not given FDA: 123 YR"),
        ("7903003", "Weight", "Not given FDA: 0 KG"),
        ("7903005", "Weight", "Not given FDA: 636 KG"),
        ("7903007", "Weight", "Not given FDA: 70"),
        ("7903001", "Weight", "69.9 kg FDA: 154 LBS"),
    ],
)
def test_sex_age_and_weight_sit_over_fdas_value_and_an_impossible_one_is_not_given(
    opened, demo_site, caseid, label, shown
):
    page = opened(f"/all/cases?case={caseid}&era=faers", base=demo_site)
    assert field(page, label) == shown


def test_an_age_shows_its_band_and_an_age_with_no_unit_is_read_as_years(opened, demo_site):
    labels = {b["id"]: b["label"] for b in value("age-bands", "bands")}
    page = opened("/all/cases?case=7902001&era=faers", base=demo_site)
    assert field(page, "Age") == f"45 years FDA: 45{labels['18-64']} fixed rule: age-bands"
    assert rule_links(page)["fixed rule: age-bands"] == "/methods?open=age-bands"
    page = opened("/all/cases?case=7904003&era=faers", base=demo_site)  # 0 years, no age group
    assert labels["under-1"] in field(page, "Age")


def therapy(page: Any) -> list[list[str]]:
    """The case window's therapy table, a list of cells a row."""
    return page.eval_on_selector_all(
        "#oa-case .oa-case-therapy tbody tr",
        "rs => rs.map((r) => [...r.cells].map((c) => c.innerText.replace(/\\s+/g, ' ').trim()))",
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_the_therapy_table_shows_clean_dates_duration_and_time_to_onset_over_fdas(
    opened, stats_site, width
):
    # the stats fakes' case 1: its suspect started on 1 January 2019, a day before the event,
    # and stopped a day after it started
    page = opened("/all/cases?case=7700001", base=stats_site, width=width)
    heads = page.eval_on_selector_all(
        "#oa-case .oa-case-therapy thead th", "hs => hs.map((h) => h.innerText)"
    )
    assert heads == ["Drug", "Start", "End", "Duration", "Time to onset"]
    first = value("time-to-onset", "first_dose_day")
    assert therapy(page)[0] == [
        "IBUPROFEN",
        "01-Jan-2019 FDA: 20190101",
        "02-Jan-2019 FDA: 20190102",
        "2 days fixed rule: therapy-duration",
        f"Day {1 + first} fixed rule: time-to-onset",
    ]
    links = rule_links(page, "#oa-case .oa-case-therapy")
    assert links["fixed rule: time-to-onset"] == "/methods?open=time-to-onset"
    assert links["fixed rule: therapy-duration"] == "/methods?open=therapy-duration"
    assert not sideways(page)


def test_a_drug_with_no_time_to_onset_says_why_and_a_partial_start_shows_its_month(
    opened, stats_site
):
    # case 17 gives its suspect's start to the month alone
    page = opened("/all/cases?case=7700017", base=stats_site)
    row = therapy(page)[0]
    assert row[1] == "January 2019 FDA: 201901" and row[4] == "No exact first dose"
    tip = page.get_attribute("#oa-case .oa-case-therapy tbody tr td:nth-child(5) span", "data-tip")
    assert tip and "known to the day" in tip


# the order a safety reviewer reads a case in: a line about it, what happened, the drugs, the
# patient, and the report itself last
PARTS = """(body) => [...body.querySelectorAll(':scope > .oa-case-lead, .oa-case-part')]
  .map((part) => part.matches('.oa-case-lead')
  ? ['summary', []]
  : [part.querySelector(':scope > h3').textContent,
     [...part.querySelectorAll(':scope > dl > dt')].map((dt) => dt.textContent)])"""


@pytest.mark.parametrize("width", WIDTHS)
def test_the_window_reads_in_a_reviewers_order_with_the_suspects_first(opened, site, width):
    """A copy in a group of duplicates whose first drug is made a concomitant on the way to the
    page: the summary, what happened (the reactions, then the outcomes), the drugs, the patient,
    and about the report last with its probable duplicates; the suspects come first, then Taken
    alongside, and the therapy dates follow the drugs' order."""
    page = opened("/all/cases", width=width)

    def concomitant_first(route: Any) -> None:
        case = route.fetch().json()
        case["drug"][0]["role_T"] = "C"
        route.fulfill(json=case)

    page.route("**/api/case/*/9021021", concomitant_first)
    page.goto(site + "/all/cases?case=9021021&era=faers")
    settle(page)
    page.wait_for_selector("#oa-case .oa-case-part")
    parts = dict(page.locator("#oa-case .oa-case-body").evaluate(PARTS))
    assert list(parts) == [
        "summary",
        "What happened",
        "The drugs",
        "The patient",
        "About the report",
    ]
    assert parts["What happened"] == ["Reactions", "Outcomes", "Event date"]
    assert parts["The patient"] == [
        "Age",
        "Sex",
        "Weight",
        "Country",
        "Where it happened",
        "Reporter's country",
    ]
    report = parts["About the report"]
    assert report[0] == "Case number" and report[-1] == "Probable duplicates"
    assert {"FDA quarter", "FDA system", "Report type", "Who reported", "Company"} <= set(report)
    # the patient and the report share a row on a wide screen and stack on a phone
    tops = page.eval_on_selector_all(
        "#oa-case .oa-case-pair > .oa-case-part",
        "ps => ps.map((p) => p.getBoundingClientRect().top)",
    )
    assert (tops[0] == tops[1]) == (width > 600)
    # the reactions sit side by side on a wide screen and one under another on a phone
    reactions = page.eval_on_selector_all(
        "#oa-case .oa-reac-list > li", "ls => ls.map((l) => l.getBoundingClientRect().top)"
    )
    assert len(reactions) > 1 and (reactions[0] == reactions[1]) == (width > 600)
    rows = page.eval_on_selector_all(
        "#oa-case .oa-case-drugs tbody tr",
        """rs => rs.map((r) => r.matches('.oa-case-divider') ? [r.innerText.trim()]
             : [r.cells[0].innerText, r.cells[1].innerText.trim()])""",
    )
    assert [row[0] for row in rows] == ["PS", "PS", "Taken alongside", "C"]
    therapy = page.eval_on_selector_all(
        "#oa-case .oa-case-therapy tbody tr td:first-child", "ts => ts.map((t) => t.innerText)"
    )
    assert therapy == [row[1] for row in rows if len(row) == 2]
    assert not sideways(page)


# every field the window has: what each case's values are labelled by, the drugs' and therapy
# dates' columns included
FIELDS = """(body) => [...body.querySelectorAll('dt, thead th, .oa-case-sub')]
  .map((f) => f.textContent)"""
EVERY_FIELD = {
    "Reactions",
    "Reactions, and each suspect's label",
    "Came back when the drug was given again",
    "Outcomes",
    "Event date",
    "Role",
    "As reported",
    "Ingredient",
    "Used for",
    "WHO class (ATC)",
    "Route",
    "Dose",
    "Stopped and restarted",
    "Therapy dates",
    "Drug",
    "Start",
    "End",
    "Duration",
    "Time to onset",
    "Age",
    "Sex",
    "Weight",
    "Country",
    "Where it happened",
    "Reporter's country",
    "Case number",
    "Report",
    "Version",
    "FDA quarter",
    "FDA system",
    "First received",
    "First received (any copy)",
    "First received (this copy)",
    "This version received",
    "Report type",
    "Who reported",
    "Company",
    "Probable duplicates",
}
# cases that between them have every field: a site, and the case's address
FIELD_CASES = [
    ("site", "case=9021021&era=faers"),  # a copy in a group of duplicates
    ("site", "case=9013013&era=faers"),  # a reaction that came back when the drug was given again
    ("site", "case=5100005&era=legacy"),  # an AERS case in no group
    ("classes_site", "case=9020020&era=faers"),  # WHO classes
    ("label_site", "case=9005005&era=faers"),  # label flags under the reactions
    ("stats_site", "case=7700001"),  # therapy dates
]


def test_reading_order_moves_the_fields_and_drops_none(request, opened):
    """Across cases that between them have every field, the window shows each field the case
    has, once, and no field is missing from all of them: the order a reviewer reads a case in
    moves where each field sits, never whether it is shown."""
    shown: set[str] = set()
    for site, query in FIELD_CASES:
        base = request.getfixturevalue(site)
        page = opened(f"/all/cases?{query}", base=base, width=1440)
        page.wait_for_selector("#oa-case .oa-case-part")
        fields = page.locator("#oa-case .oa-case-body").evaluate(FIELDS)
        assert len(fields) == len(set(fields)), (query, fields)
        shown |= set(fields)
    assert shown == EVERY_FIELD
