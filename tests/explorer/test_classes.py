"""WHO's drug classes in the explorer (classes.py): the class filter, the classes it offers, the
breakdown by class, each drug's class on the list and in a case, and the release or the viewer
that has none. Over the fake release with the invented classes layer (open_altio.testing
.fakeclasses); what each count should be is read from the release's own files."""

from __future__ import annotations

import io
import json
import re
import zipfile

import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from open_altio.explorer.access import Viewer
from open_altio.explorer.classes import NOT_HELD, NOT_OPEN
from open_altio.explorer.explore import list_length
from open_altio.faers import open_release
from open_altio.testing import fakeclasses
from open_altio.testing.browser import tick_look

SUSPECT = ("PS", "SS")
ANY_ROLE = ("PS", "SS", "C")
# WHO's short line, wherever a class shows on a screen
WHO_LINE = (
    f"Drug classes: WHO ATC {fakeclasses.YEAR}, "
    "WHO Collaborating Centre for Drug Statistics Methodology, Oslo"
)


@pytest.fixture
def classed(explorer_app, classes_release) -> TestClient:
    return TestClient(explorer_app(classes_release))


@pytest.fixture(scope="module")
def kept(classes_release):
    """kept(substances, roles): the kept cases naming one of the substances in one of the roles,
    as case keys, from the release's own tables."""
    con = open_release(classes_release)

    def cases(substances: list[str], roles: tuple[str, ...] = SUSPECT) -> set[str]:
        rows = con.execute(
            "SELECT DISTINCT c.case_key_T FROM case_latest_T c "
            "JOIN drug_substance_T s USING (era_T, primaryid, quarter_T) "
            "JOIN drug_latest_T d USING (era_T, primaryid, quarter_T, drug_seq) "
            "WHERE c.dup_kept_T AND list_contains(?, s.substance_T) "
            "AND list_contains(?, upper(trim(d.role_cod)))",
            [substances, list(roles)],
        ).fetchall()
        return {r[0] for r in rows}

    yield cases
    con.close()


def counted(client, ask, **params) -> int:
    return ask(client, "/api/summary", **params)["cases"]


# the filter -------------------------------------------------------------------------------------


def test_the_class_filter_counts_suspect_drugs_by_default_with_the_drug_filters_roles(
    classed, ask, kept
):
    # omeprazole is only ever reported alongside (C), so a suspect count does not find it
    alongside = kept(["omeprazole"], ("C",))
    assert alongside and not kept(["omeprazole"])
    assert counted(classed, ask, atc="A02") == 0
    assert counted(classed, ask, atc="A02", arole="C") == len(alongside)
    assert counted(classed, ask, atc="B01") == len(kept(["warfarin"]))
    assert "role" in ask(classed, "/api/summary", 400, atc="B01", arole="X")["problem"].lower()


def test_could_be_adds_the_drugs_that_could_be_the_class_each_case_once(classed, ask, kept):
    warfarin, aspirin = kept(["warfarin"]), kept(["acetylsalicylic acid"])
    assert warfarin & aspirin  # a case naming both counts once
    assert counted(classed, ask, atc="B01") == len(warfarin)
    assert counted(classed, ask, atc="B01", could=1) == len(warfarin | aspirin)
    assert ask(classed, "/api/classes", atc="B01")["could"] == len(aspirin - warfarin)
    # aspirin could be a pain medicine; warfarin, whose class is known, never could
    assert counted(classed, ask, atc="N02") == 0
    assert counted(classed, ask, atc="N02", could=1) == len(aspirin)


def test_a_shared_class_counts_when_it_is_at_or_under_the_chosen_class(classed, ask, kept):
    ibuprofen = kept(["ibuprofen"])
    assert ibuprofen
    for code in ("M", "M01", "M01Z", "M01ZZ"):
        assert counted(classed, ask, atc=code) == len(ibuprofen), code
    # a class under the shared one is only what the drug could be
    assert counted(classed, ask, atc="M01ZZ01") == 0
    assert counted(classed, ask, atc="M01ZZ01", could=1) == len(ibuprofen)
    assert counted(classed, ask, atc="M01ZY") == 0


def test_two_classes_count_a_case_in_either(classed, ask, kept):
    both = kept(["warfarin", "digoxin"])
    assert counted(classed, ask, atc=["B01", "C01"]) == len(both)


def test_a_class_left_out_takes_only_its_drugs_out_of_the_class_above_it(classed, ask, kept):
    acid, sugar = kept(["omeprazole"], ANY_ROLE), kept(["metformin"], ANY_ROLE)
    assert acid - sugar and sugar - acid
    roles = {"arole": list(ANY_ROLE)}
    assert counted(classed, ask, atc="A", **roles) == len(acid | sugar)
    # metformin's class is three levels under A: leaving it out, or A10, keeps omeprazole
    assert counted(classed, ask, atc="A", atc_out="A10ZZ01", **roles) == len(acid)
    assert counted(classed, ask, atc="A", atc_out="A10", **roles) == len(acid)
    # ticked again under a class left out, it counts again
    both = counted(classed, ask, atc=["A", "A10ZZ01"], atc_out="A10", **roles)
    assert both == len(acid | sugar)
    # every class under B left out: no case
    assert counted(classed, ask, atc="B", atc_out="B01") == 0


def test_a_class_of_no_cases_left_out_changes_nothing(classed, ask, kept):
    # ibuprofen's records are in the shared class M01ZZ, so M01ZZ01 under it has none
    assert ask(classed, "/api/classes", parent="M01ZZ")["classes"][0]["cases"] == 0
    left = counted(classed, ask, atc="M", atc_out="M01ZZ01")
    assert left == counted(classed, ask, atc="M") == len(kept(["ibuprofen"]))


def test_the_could_be_tick_counts_none_of_what_is_left_out(classed, ask, kept):
    # aspirin could be B01ZZ01 or N02ZZ01: with B01ZZ left out of B01, it cannot be what is left
    left = counted(classed, ask, atc="B01", atc_out="B01ZZ", could=1)
    assert left == len(kept(["warfarin"]))
    assert ask(classed, "/api/classes", atc="B01", atc_out="B01ZZ")["could"] == 0


def test_a_class_is_left_out_only_under_a_chosen_one(classed, ask):
    for wrong in (
        {"atc_out": "B01"},
        {"atc": "B01", "atc_out": "B"},
        {"atc": "B01", "atc_out": "B01"},
        {"atc": "B01", "atc_out": "C01ZZ"},
    ):
        problem = ask(classed, "/api/summary", 400, **wrong)["problem"]
        assert "no class above it is chosen" in problem, wrong


def test_the_filter_names_the_classes_left_out_with_their_cases(classed, ask, kept):
    got = ask(classed, "/api/classes", atc="B", atc_out="B01ZY01")
    assert [c["code"] for c in got["chosen"]] == ["B"]
    out = got["left_out"]
    assert [(c["code"], c["level"], c["cases"]) for c in out] == [
        ("B01ZY01", 5, len(kept(["warfarin"])))
    ]
    assert out[0]["name"].lower() == "warfarin"


def test_the_filter_offers_the_main_groups_then_the_classes_under_each(classed, ask, kept):
    top = ask(classed, "/api/classes")
    mains = sorted(code for code, level, _ in fakeclasses.INDEX if level == 1)
    assert [c["code"] for c in top["classes"]] == mains
    assert (top["index_year"], top["citation"]) == (fakeclasses.YEAR, fakeclasses.CITATION)
    cases = {c["code"]: c["cases"] for c in top["classes"]}
    assert cases["B"] == len(kept(["warfarin"])) and cases["N"] == 0
    assert all(c["more"] for c in top["classes"])
    under = ask(classed, "/api/classes", parent="B01Z")["classes"]
    assert [c["code"] for c in under] == ["B01ZY", "B01ZZ"]
    leaves = ask(classed, "/api/classes", parent="B01ZY")["classes"]
    assert [(c["code"], c["more"]) for c in leaves] == [("B01ZY01", False)]


def test_a_search_finds_codes_and_names_with_the_classes_above_them(classed, ask):
    found = ask(classed, "/api/classes", q="Platelet")["classes"]
    assert [c["code"] for c in found if c["hit"]] == ["B01ZZ"]
    assert {c["code"] for c in found if not c["hit"]} == {"B", "B01", "B01Z"}
    by_code = [c["code"] for c in ask(classed, "/api/classes", q="b01z")["classes"] if c["hit"]]
    assert by_code[0] == "B01Z" and all(c.startswith("B01Z") for c in by_code)
    many = ask(classed, "/api/classes", q="i")["classes"]
    assert sum(c["hit"] for c in many) <= list_length("classes_found")


def test_a_search_lists_the_class_named_as_typed_then_those_starting_so_then_the_rest(classed, ask):
    """Each class above others comes where the first found under it does, so the tree the page
    draws keeps that order at every level."""
    found = ask(classed, "/api/classes", q="a")["classes"]
    # A is the code typed; B and N hold acetylsalicylic acid, which starts so; C and M hold
    # classes whose names hold it
    assert [c["code"] for c in found if c["level"] == 1] == ["A", "B", "N", "C", "M"]
    assert [c["code"] for c in found if c["code"].startswith("B01Z")] == [
        "B01Z",
        "B01ZZ",
        "B01ZZ01",
        "B01ZY",
        "B01ZY01",
    ]
    exact = ask(classed, "/api/classes", q="ibuprofen")["classes"]
    assert [c["code"] for c in exact if c["hit"]] == ["M01ZZ01", "M01ZZ51"]


def test_the_chosen_classes_come_back_with_their_names_and_cases(classed, ask, kept):
    got = ask(classed, "/api/classes", atc=["C01", "B01"])
    assert [(c["code"], c["name"]) for c in got["chosen"]] == [
        ("C01", "Invented heart beat medicines"),
        ("B01", "Invented clot medicines"),
    ]
    assert got["chosen"][0]["cases"] == len(kept(["digoxin"]))


# the breakdown on All cases' Overview -----------------------------------------------------------


def test_the_breakdown_counts_each_drug_in_one_class_and_could_be_several_once(classed, ask, kept):
    b = ask(classed, "/api/summary")["classes"]
    rows = {k: n for k, _, n in b["rows"]}
    aspirin = kept(["acetylsalicylic acid"])
    assert rows["B"] == len(kept(["warfarin"]))  # aspirin could be B or N: in neither bar
    assert rows["M"] == len(kept(["ibuprofen"]))
    assert "N" not in rows and b["several"] == len(aspirin)
    assert (b["parent"], b["roles"]) == ("", list(SUSPECT))
    # under a chosen class, the classes under it; a shared class has none to go to
    under = ask(classed, "/api/summary", atc="M01ZZ")["classes"]
    assert (under["parent"], under["rows"], under["several"]) == (
        "M01ZZ",
        [],
        len(kept(["ibuprofen"])),
    )


def test_the_class_chart_counts_the_cases_with_a_class_chosen_or_one_it_could_be(
    classed, ask, kept
):
    got = ask(classed, "/api/summary")
    chosen = kept(list(fakeclasses.CHOSEN))
    assert got["given"]["atc"] == [len(chosen), got["cases"]]
    assert len(chosen) < got["cases"]
    assert ask(classed, "/api/summary", arole="C")["given"]["atc"][0] != len(chosen)


def test_a_product_page_has_no_breakdown_by_class(classed, ask):
    assert "classes" not in ask(classed, "/api/summary", product="warfarin")


# each drug's class -----------------------------------------------------------------------------


def test_each_drug_on_the_list_shows_its_one_class_and_a_broader_one_says_so(classed, ask):
    drugs = [d for c in ask(classed, "/api/cases", atc="M01")["cases"] for d in c["drugs"]]
    assert ["M01ZZ", "Invented propionic acids", True] in [d[3] for d in drugs]
    shown = {
        d[1]: d[3] for d in ask(classed, "/api/cases", atc="B01", could=1)["cases"][0]["drugs"]
    }
    assert all(v is None or v[0].startswith("B01") for v in shown.values())
    aspirin = [
        d for c in ask(classed, "/api/cases")["cases"] for d in c["drugs"] if d[1] == "ASPIRIN"
    ]
    assert aspirin and all(d[3] is None for d in aspirin)  # can't tell: no class on the list


def test_a_case_shows_what_each_drug_could_be_and_how_its_class_was_chosen(classed, ask, kept):
    key = sorted(kept(["warfarin"]) & kept(["acetylsalicylic acid"]))[0]
    era = ask(classed, "/api/cases", atc="B01")["cases"][0]["era_T"]
    case = ask(classed, f"/api/case/{era}/{key}")
    by = {c["chosen_by"]: c for c in case["classes"]}
    assert by["only_code"]["code"] == "B01ZY01" and by["only_code"]["possible"] == []
    assert by["only_code"]["name"] == "Invented vitamin antagonists"  # the class it sits in
    cant = by["cannot_tell"]
    assert (cant["code"], cant["broader"]) == (None, False)
    assert cant["possible"] == [
        ["B01ZZ01", "Invented platelet inhibitors"],
        ["N02ZZ01", "Invented salicylic acids"],
    ]
    # under a shared class, what it could be is named where the codes part: the substance
    shared = ask(classed, "/api/case/" + _case_of(classed, ask, "M01"))["classes"]
    ibuprofen = next(c for c in shared if c["chosen_by"] == "shared_class")
    assert (ibuprofen["code"], ibuprofen["broader"]) == ("M01ZZ", True)
    assert ibuprofen["possible"] == [
        ["M01ZZ01", "ibuprofen"],
        ["M01ZZ51", "ibuprofen, combinations"],
    ]


def _case_of(client, ask, code: str) -> str:
    c = ask(client, "/api/cases", atc=code)["cases"][0]
    return f"{c['era_T']}/{c['case_key_T']}"


# a release without classes, and a viewer not shown them -----------------------------------------


def test_a_release_without_classes_offers_none_and_everything_else_works(
    explorer_app, bare_release, ask
):
    web = TestClient(explorer_app(bare_release))
    assert ask(web, "/api/release")["classes"] is None
    summary = ask(web, "/api/summary")
    assert summary["cases"] > 0 and "classes" not in summary
    assert ask(web, "/api/classes", 404)["problem"] == NOT_HELD
    assert ask(web, "/api/summary", 404, atc="B01")["problem"] == NOT_HELD
    listed = ask(web, "/api/cases")["cases"]
    assert listed and all(d[3] is None for c in listed for d in c["drugs"])
    assert "classes" not in ask(web, f"/api/case/{listed[0]['era_T']}/{listed[0]['case_key_T']}")
    assert not [t for t in ask(web, "/api/schema") if t["name"].startswith("atc_")]


def sql(client, text: str):
    return client.post("/api/sql", json={"sql": text, "page": 1})


def export_drugs(client, **params) -> tuple[list[str], dict]:
    got = client.get("/api/export", params={"format": "parquet", **params})
    assert got.status_code == 200, got.text
    z = zipfile.ZipFile(io.BytesIO(got.content))
    files = {n.rsplit("/", 1)[-1]: z.read(n) for n in z.namelist()}
    return pq.read_table(io.BytesIO(files["drugs.parquet"])).column_names, json.loads(
        files["manifest.json"]
    )


def test_a_viewer_not_shown_classes_meets_none_on_a_page_in_sql_or_in_an_export(
    hooked, classes_release, ask
):
    web = hooked(viewer=Viewer(id="ann", meddra=False, who=False), release_dir=classes_release)
    assert ask(web, "/api/release")["classes"] is None
    assert ask(web, "/api/classes", 403)["problem"] == NOT_OPEN
    assert ask(web, "/api/summary", 403, atc="B01")["problem"] == NOT_OPEN
    assert "classes" not in ask(web, "/api/summary")
    case = ask(web, "/api/cases")["cases"][0]
    assert all(d[3] is None for d in case["drugs"])
    assert "classes" not in ask(web, f"/api/case/{case['era_T']}/{case['case_key_T']}")
    refused = sql(web, "SELECT count(*) FROM atc_drug_T")
    assert refused.status_code == 400 and "atc_drug_T" in refused.json()["problem"]
    assert not [t for t in ask(web, "/api/schema") if t["name"].startswith("atc_")]
    assert not [t for t in ask(web, "/api/manifest")["tables"] if t["name"].startswith("atc_")]
    columns, manifest = export_drugs(web)
    assert not [c for c in columns if c.startswith("atc_")] and "classes" not in manifest


def test_the_classes_go_into_files_only_where_the_viewer_may_take_them_away(
    hooked, classed, classes_release, ask
):
    pages_only = hooked(
        viewer=Viewer(id="ann", meddra=False, who=True, who_files=False),
        release_dir=classes_release,
    )
    assert ask(pages_only, "/api/release")["classes"]["index_year"] == fakeclasses.YEAR
    assert sql(pages_only, "SELECT count(*) FROM atc_drug_T").status_code == 400
    columns, manifest = export_drugs(pages_only, atc="B01")
    assert not [c for c in columns if c.startswith("atc_")] and "classes" not in manifest
    # the filter names WHO's codes, so WHO's citation goes with it
    assert manifest["filters"]["classes"]["citation"] == fakeclasses.CITATION
    # on one's own machine they go everywhere the release does
    got = sql(classed, "SELECT count(*) FROM atc_drug_T")
    assert got.status_code == 200 and got.json()["rows"][0][0] > 0
    columns, manifest = export_drugs(classed, atc="B01")
    assert {"atc_code_T", "atc_name_T", "atc_level_T", "atc_chosen_by_T"} <= set(columns)
    assert manifest["classes"]["citation"] == fakeclasses.CITATION
    assert any(line.startswith("Drug class (ATC): B01 ") for line in manifest["described"])
    assert manifest["filters"]["classes"] == {
        "classes": ["B01"],
        "left_out": [],
        "roles": ["PS", "SS"],
        "could": False,
        "index_year": fakeclasses.YEAR,
        "citation": fakeclasses.CITATION,
    }
    _, manifest = export_drugs(classed, atc="B", atc_out="B01ZY01")
    assert manifest["filters"]["classes"]["left_out"] == ["B01ZY01"]
    assert any(", leaving out B01ZY01 " in line for line in manifest["described"])
    # a SQL result: WHO's citation in a Parquet file's metadata
    got = classed.post(
        "/api/sql/download", json={"sql": "SELECT * FROM atc_index_T", "format": "parquet"}
    )
    assert got.status_code == 200, got.text
    notes = pq.read_table(io.BytesIO(got.content)).schema.metadata
    assert notes[b"who_atc_citation"].decode() == fakeclasses.CITATION


def test_the_screens_show_sentence_case_and_files_keep_whos_capitals(classed, ask):
    got = ask(classed, "/api/classes")["classes"]
    assert [c["name"] for c in got][:2] == [
        "Invented digestion medicines",
        "Invented blood medicines",
    ]
    under = ask(classed, "/api/classes", parent="C01")["classes"]
    assert [c["name"] for c in under] == ["Invented ACE glycosides"]  # the abbreviation stays
    assert ask(classed, "/api/summary")["classes"]["rows"][0][1].startswith("Invented ")
    # WHO's exact text: in SQL and in an export row
    row = sql(classed, "SELECT atc_name_T FROM atc_index_T WHERE atc_code_T = 'C01Z'")
    assert row.json()["rows"] == [["INVENTED ACE GLYCOSIDES"]]
    _, manifest = export_drugs(classed, atc="C01")
    assert any("C01 INVENTED HEART BEAT MEDICINES" in line for line in manifest["described"])


# the page ---------------------------------------------------------------------------------------


SIZES = [(390, "light"), (390, "dark"), (1440, "light"), (1440, "dark")]


def open_class_filter(page) -> None:
    page.click(".oa-filters-btn")
    page.click('#oa-filter-menu [data-act="filter-row"][data-row="atc"]')
    page.wait_for_selector("#oa-class-results .oa-choice")


def open_classes(page, *codes: str) -> None:
    """Open each class in turn, a class under the one before."""
    for code in codes:
        page.click(f'#oa-class-results [data-act="class-expand"][data-code="{code}"]')
        page.wait_for_selector(
            f'#oa-class-results [data-act="class-pick"][data-code^="{code}"]'
            f':not([data-code="{code}"])'
        )


def pick(page, code: str) -> None:
    page.locator(f'#oa-class-results [data-act="class-pick"][data-code="{code}"]').first.click()


def until_ticked(page, **ticks: str) -> None:
    """Wait until every row of each class shows its tick: true, false or mixed (a dash)."""
    page.wait_for_function(
        """want => Object.entries(want).every(([code, tick]) => {
          const rows = [...document.querySelectorAll(`#oa-class-results [data-code="${code}"]`)]
            .filter((e) => e.dataset.act === 'class-pick');
          return rows.length && rows.every((e) => e.getAttribute('aria-checked') === tick);
        })""",
        arg=ticks,
    )


def until_counted(page, n: int) -> None:
    page.wait_for_function(
        f"() => document.querySelector('#oa-countline strong')?.textContent === '{n:,}'"
    )


def row_top(page, code: str) -> int:
    """Where a class's row sits in the pane, whatever the pane is scrolled to."""
    return page.eval_on_selector(
        f'#oa-class-results [data-act="class-pick"][data-code="{code}"]',
        "e => { let y = 0; for (let n = e; n; n = n.offsetParent) y += n.offsetTop; return y; }",
    )


def test_the_page_filters_by_a_class_counts_could_be_and_cites_who(
    opened, classes_site, classed, ask, kept
):
    page = opened("/all", base=classes_site)
    open_class_filter(page)
    pane = page.locator("#oa-filter-options")
    assert WHO_LINE in pane.inner_text() and fakeclasses.CITATION not in pane.inner_text()
    link = pane.locator(".oa-who-line")
    assert link.get_attribute("href") == "/methods?open=atc-index"
    page.click('#oa-class-results [data-act="class-expand"][data-code="B"]')
    page.click('#oa-class-results [data-act="class-pick"][data-code="B01"]')
    page.wait_for_function(
        f"() => document.querySelector('#oa-countline strong')?.textContent === "
        f"'{len(kept(['warfarin']))}'"
    )
    could = page.locator('[data-act="class-could"] .choice-count')
    added = ask(classed, "/api/classes", atc="B01")["could"]
    could.filter(has_text=f"+{added}").wait_for()
    page.click('[data-act="class-could"]')
    both = len(kept(["warfarin"]) | kept(["acetylsalicylic acid"]))
    page.wait_for_function(
        f"() => document.querySelector('#oa-countline strong')?.textContent === '{both}'"
    )
    strip = page.locator("#oa-strip").inner_text()
    assert "Drug class (ATC)" in strip and "could be" in strip
    # the short line opens WHO's index rule on the methods page, under WHO's full citation
    rules = opened(link.get_attribute("href"), base=classes_site)
    assert rules.get_attribute("#rule-atc-index", "data-open") == "true"
    cite = rules.locator("#step-drug_classes .oa-rule-group-cite")
    assert cite.inner_text() == f"Cite as: {fakeclasses.CITATION}"
    rules.wait_for_function(
        "() => { const r = document.querySelector('#step-drug_classes .oa-rule-group-cite')"
        ".getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; }"
    )


def test_the_overview_breaks_cases_down_by_class_and_the_case_shows_its_classes(
    opened, classes_site
):
    page = opened("/all", base=classes_site)
    chart = page.locator(".oa-chart", has_text="Drug classes")
    assert "Could be several" in chart.inner_text()
    assert chart.locator(".oa-chart-given").inner_text().startswith("WHO class found for ")
    assert WHO_LINE in chart.inner_text() and fakeclasses.CITATION not in chart.inner_text()
    page = opened("/all/cases", base=classes_site)
    assert page.locator(".oa-class-cite").count() == 0  # the credit sits under the chart
    page.locator(".oa-cases tbody tr", has_text="IBUPROFEN").first.click()
    page.wait_for_selector(".oa-case-drugs .oa-class-cell")
    window = page.locator("#oa-case").inner_text().lower()  # chips and headings are capitals
    assert "who class (atc)" in window and "broader class" in window and "could be" in window
    assert "shared class" in window and WHO_LINE.lower() not in window
    assert fakeclasses.CITATION.lower() not in window


@pytest.mark.parametrize(("width", "theme"), SIZES)
def test_unticking_a_class_deep_in_a_ticked_one_dashes_each_class_above_it(
    opened, classes_site, kept, width, theme
):
    page = opened("/all", base=classes_site, width=width, theme=theme)
    open_class_filter(page)
    # the could-be tick keeps its row before a class is ticked, so ticking moves nothing
    assert page.get_attribute('[data-act="class-could"]', "aria-disabled") == "true"
    open_classes(page, "B", "B01", "B01Z", "B01ZY", "B01ZZ")
    tree = ("B", "B01", "B01Z", "B01ZY", "B01ZY01", "B01ZZ", "B01ZZ01")
    pick(page, "B")
    until_ticked(page, **dict.fromkeys(tree, "true"))
    warfarin = len(kept(["warfarin"]))
    until_counted(page, warfarin)
    top = row_top(page, "B01ZZ")
    # three levels down: warfarin's class out, each class above it partly ticked, the rest kept
    pick(page, "B01ZY01")
    until_ticked(
        page, B="mixed", B01="mixed", B01Z="mixed", B01ZY="false", B01ZY01="false",
        B01ZZ="true", B01ZZ01="true",
    )  # fmt: skip
    until_counted(page, 0)
    assert row_top(page, "B01ZZ") == top
    assert "leaving out B01ZY" in page.locator("#oa-strip").inner_text()
    # ticked again, the last one unticked under B: B is whole again
    pick(page, "B01ZY01")
    until_ticked(page, **dict.fromkeys(tree, "true"))
    until_counted(page, warfarin)
    assert row_top(page, "B01ZZ") == top
    assert "leaving out" not in page.locator("#oa-strip").inner_text()


def test_a_press_that_cannot_change_the_cases_shows_no_loading(opened, classes_site, kept):
    page = opened("/all", base=classes_site)
    open_class_filter(page)
    open_classes(page, "M", "M01", "M01Z", "M01ZZ")
    pick(page, "M")
    until_counted(page, len(kept(["ibuprofen"])))
    page.evaluate("""() => {
      window.loadingSeen = false;
      const seen = () => {
        const body = document.getElementById('oa-body');
        const counting = document.querySelector('#oa-countline .skeleton');
        if (body?.dataset.state === 'loading' || counting) window.loadingSeen = true;
      };
      new MutationObserver(seen).observe(document.querySelector('.oa-panel'), {
        attributes: true, childList: true, subtree: true,
      });
    }""")
    # M01ZZ01 has no cases: leaving it out, or putting it back through the class above, changes none
    pick(page, "M01ZZ01")
    until_ticked(page, M="mixed", M01ZZ="mixed", M01ZZ01="false", M01ZZ51="true")
    assert "leaving out M01ZZ01" in page.locator("#oa-strip").inner_text()
    pick(page, "M01ZZ")
    until_ticked(page, M="true", M01ZZ="true", M01ZZ01="true")
    assert not page.evaluate("window.loadingSeen")
    # a press that changes the cases loads them
    pick(page, "M")
    until_ticked(page, M="false", M01ZZ01="false")
    page.wait_for_function("() => window.loadingSeen")


# a class above one class only, with records of its own (fakeclasses.GROUP_CLASS): as WHO's C09A
# holds C09AA alone, and FAERS reports naming only "an ACE inhibitor" are classed at C09A itself


@pytest.fixture
def grouped(explorer_app, group_release) -> TestClient:
    return TestClient(explorer_app(group_release))


def test_each_class_says_whether_records_are_classed_at_it_itself(grouped, ask, kept):
    valsartan, adalimumab = kept(["valsartan"]), kept(["adalimumab"])
    under = ask(grouped, "/api/classes", parent="C09Z")["classes"]
    assert [(c["code"], c["cases"], c["own"]) for c in under] == [("C09ZZ", len(valsartan), False)]
    # adalimumab's records are classed at C09Z itself: more cases than its one class under it
    above = ask(grouped, "/api/classes", parent="C09")["classes"]
    assert [(c["code"], c["cases"], c["own"]) for c in above] == [
        ("C09Z", len(valsartan | adalimumab), True)
    ]
    assert valsartan and adalimumab - valsartan
    leaves = ask(grouped, "/api/classes", parent="C09ZZ")["classes"]
    assert [(c["code"], c["own"]) for c in leaves] == [("C09ZZ01", True)]
    got = ask(grouped, "/api/classes", atc="C09Z", atc_out="C09ZZ")
    assert [(c["code"], c["own"]) for c in got["chosen"] + got["left_out"]] == [
        ("C09Z", True),
        ("C09ZZ", False),
    ]


# The roll-up rule, on a tree as the page learns it: the classes under each class, and whether
# records are classed at it itself. Each press gives the classes chosen and left out after it.
PRESSES = """async ({ kids, own, start, presses }) => {
  const { press } = await import('/ui/classes.js');
  const tree = { kids: new Map(Object.entries(kids)), own: new Map(Object.entries(own)) };
  const f = { atc: [...start[0]], atcOut: [...start[1]] };
  const now = () => [[...f.atc].sort(), [...f.atcOut].sort()];
  return presses.map((code) => { press(f, code, tree); return now(); });
}"""
TREE = {
    "kids": {
        "C": ["C01", "C09"],
        "C01": ["C01Z"],
        "C09": ["C09A"],
        "C09A": ["C09AA"],
        "C09AA": ["C09AA01", "C09AA02"],
    },
    "own": {"C": False, "C01": False, "C09": False, "C09A": True, "C09AA": False},
}


def presses(page, *codes: str, start=([], [])) -> list:
    return page.evaluate(PRESSES, {**TREE, "start": start, "presses": list(codes)})


def test_a_class_ends_ticked_or_unticked_with_those_under_it_only_when_it_holds_no_records_itself(
    opened, classes_site
):
    page = opened("/all", base=classes_site)
    # C09AA is C09A's one class, but C09A holds records of its own: C09AA stays the one ticked
    assert presses(page, "C09AA") == [[["C09AA"], []]]
    # every class under C09AA, which holds none: C09AA, and no higher
    assert presses(page, "C09AA01", "C09AA02")[-1] == [["C09AA"], []]
    # a class with no records of its own and its one class under it are the same cases
    assert presses(page, "C01Z") == [[["C01"], []]]
    # unticking C09AA in a ticked C09A leaves C09A's own records ticked; ticked again, C09A is whole
    assert presses(page, "C09AA", "C09AA", start=(["C09A"], [])) == [
        [["C09A"], ["C09AA"]],
        [["C09A"], []],
    ]
    # unticking a whole class above takes everything under it, its own records too
    assert presses(page, "C09A", start=(["C09A"], [])) == [[[], []]]


@pytest.mark.parametrize(("width", "theme"), SIZES)
def test_ticking_the_one_class_under_a_class_with_records_of_its_own_keeps_to_that_class(
    opened, group_site, kept, width, theme
):
    """As C09AA under WHO's C09A: ticking C09ZZ counts valsartan's cases and names C09ZZ alone;
    C09Z and each class above it show a quiet dash that says what it means, and nothing moves."""
    page = opened("/all", base=group_site, width=width, theme=theme)
    open_class_filter(page)
    page.fill("#oa-class-find", "C09ZZ")
    row = '#oa-class-results [data-act="class-pick"][data-code="{}"]'.format
    page.wait_for_selector(row("C09ZZ01"))
    plain = tick_look(page, row("C09Z"))
    top = row_top(page, "C09ZZ01")
    pick(page, "C09ZZ")
    until_ticked(page, C="mixed", C09="mixed", C09Z="mixed", C09ZZ="true", C09ZZ01="true")
    until_counted(page, len(kept(["valsartan"])))
    strip = page.locator("#oa-strip").inner_text()
    assert re.findall(r"\bC\d\d\w*", strip) == ["C09ZZ"], strip
    assert row_top(page, "C09ZZ01") == top
    # the dash is drawn in the plain box, a grey mark on its grey edge; only the tick is lit
    dash, tick = tick_look(page, row("C09Z")), tick_look(page, row("C09ZZ"))
    assert (dash["fill"], dash["edge"]) == (plain["fill"], plain["edge"])
    assert (dash["fill"], dash["edge"]) != (tick["fill"], tick["edge"])
    assert dash["mark"] == dash["edge"] and dash["size"] == tick["size"] == plain["size"]
    assert dash["tip"] == "Part of this class is ticked"
    assert tick["tip"] is None and plain["tip"] is None
    # hovered, the dash's tip shows in the open menu, so the browser draws it above the menu
    page.hover(row("C09Z") + " .oa-tick")
    page.wait_for_selector(":popover-open #oa-tip:not([hidden])")
    assert page.inner_text("#oa-tip") == "Part of this class is ticked"


def test_a_release_without_classes_offers_no_class_filter(opened, bare_site):
    page = opened("/all", base=bare_site)
    page.click(".oa-filters-btn")
    assert page.locator('#oa-filter-menu [data-row="atc"]').count() == 0
    assert page.locator(".oa-chart", has_text="Drug classes").count() == 0
