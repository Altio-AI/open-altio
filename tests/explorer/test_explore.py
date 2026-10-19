"""The explorer's questions over the live release (explore.py): the counts and charts, the
case list and one case, asked through the /api the page reads. The filters are
test_filters.py's, the searches test_search.py's, how a drug counts test_drugs.py's.

What each answer should hold is read from the release's own Parquet through `rel`, so the
explorer is checked against the release and not against itself. Page sizes come from rule
explorer-page-size.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from open_altio.explorer.filters import DIRECT
from open_altio.faers.derive import direct_report
from open_altio.rulebook import value
from open_altio.testing.rules import rules_with

# the charts --------------------------------------------------------------------------


def test_each_chart_counts_under_every_other_filter_but_its_own(client, rel, ask):
    got = ask(client, "/api/summary", sex="M")
    # F stays to choose
    assert dict(map(tuple, got["sex"])).get("F", 0) == len(rel.case_keys("c.sex_T = 'F'"))
    # other charts follow the filter
    died = rel.case_keys(
        f"c.sex_T = 'M' AND EXISTS (SELECT 1 FROM outc_latest_T o WHERE {rel.case_join('o')} "
        "AND o.outc_cod = 'DE')"
    )
    assert dict(map(tuple, got["outcome"])).get("DE", 0) == len(died)


# a case whose sex, event country, sender, age and weight read Not given (fakefda)
NOT_GIVEN_CASE = "9130013"


def test_a_value_that_says_unknown_is_charted_and_filtered_as_not_given(client, rel, ask):
    got = ask(client, "/api/summary")
    sexes = dict(map(tuple, got["sex"]))
    assert set(sexes) <= {"F", "M", None} and sexes[None] >= 1
    assert sexes[None] == len(rel.case_keys("c.sex_T IS NULL"))
    assert "faers/" + NOT_GIVEN_CASE in {
        f"{c['era_T']}/{c['case_key_T']}" for c in ask(client, "/api/cases", sex="_none")["cases"]
    }
    assert NOT_GIVEN_CASE not in {
        c["case_key_T"] for c in ask(client, "/api/cases", sex="NS")["cases"]
    }
    # the filler age is in no band; the reporter's country stands in for the unknown event country
    ages = dict(map(tuple, got["age"]))
    assert ages["_none"] == len(rel.case_keys("c.age_band_T IS NULL"))
    assert "faers/" + NOT_GIVEN_CASE in rel.case_keys("c.age_band_T IS NULL")
    assert "COUNTRY NOT SPECIFIED" not in dict(map(tuple, got["country"]))


def test_each_chart_says_how_many_of_its_cases_give_its_field(client, rel, ask):
    got = ask(client, "/api/summary")
    for name in ("sex", "age", "reporter", "country"):
        rows = dict((k, n) for k, n in got[name])
        given, cases = got["given"][name]
        assert cases == got["cases"] == sum(rows.values())
        assert given == cases - rows.get(None, 0) - rows.get("_none", 0)
    # it follows the other filters, never its own
    female = ask(client, "/api/summary", sex="F")
    assert female["given"]["sex"] == got["given"]["sex"]
    assert female["given"]["age"][1] == female["cases"] < got["cases"]


def test_the_other_charts_count_the_cases_with_a_reaction_a_serious_outcome_or_an_ingredient(
    client, rel, ask
):
    reacted = rel.case_keys(f"EXISTS (SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')})")
    serious = rel.case_keys(f"EXISTS (SELECT 1 FROM outc_latest_T o WHERE {rel.case_join('o')})")
    found = {
        f"{e}/{k}"
        for e, k in rel.rows(
            "SELECT DISTINCT c.era_T, c.case_key_T FROM case_latest_T c "
            "JOIN drug_latest_T d USING (era_T, primaryid, quarter_T) "
            "JOIN drug_substance_T s USING (era_T, primaryid, quarter_T, drug_seq) "
            "WHERE c.dup_kept_T AND s.substance_T IS NOT NULL AND d.role_cod IN ('PS', 'SS')"
        )
    }
    every = len(rel.case_keys())
    got = ask(client, "/api/summary")["given"]
    assert got["reaction"] == [len(reacted), every]
    assert got["outcome"] == [len(serious), every]
    assert got["dprods"] == [len(found), every]
    # each follows the other filters, and the outcome line never its own
    male = ask(client, "/api/summary", sex="M")
    assert male["given"]["reaction"][1] == male["cases"] < every
    died = ask(client, "/api/summary", outcome="DE")
    assert died["given"]["outcome"] == got["outcome"]
    # a product page has no ingredient chart, so no line for it
    assert "dprods" not in ask(client, "/api/summary", product="valsartan")["given"]


def test_the_companies_chart_lists_those_that_sent_most_then_not_given(client, rel, ask):
    got = ask(client, "/api/summary")
    named = dict((k, n) for k, n in got["sender"] if k not in (None, DIRECT))
    sent = dict(
        rel.rows(
            "SELECT company_T, count(*) FROM case_latest_T c WHERE dup_kept_T "
            f"AND NOT {direct_report('c.rept_cod')} GROUP BY 1"
        )
    )
    none = sent.pop(None)
    assert len(named) == min(len(sent), value("explorer-lists", "companies_charted"))
    assert sorted(named.values(), reverse=True) == sorted(sent.values(), reverse=True)[: len(named)]
    assert got["sender"][-1] == [None, none]
    # the reports sent straight to FDA are one bar, and give their sender
    direct = len(rel.case_keys(direct_report("c.rept_cod")))
    assert [DIRECT, direct] in got["sender"] and direct
    assert got["given"]["sender"] == [got["cases"] - none, got["cases"]]
    counts = [n for _, n in got["sender"][:-1]]
    assert counts == sorted(counts, reverse=True)
    # a company counts its spellings together, the legacy case sent under one of them too
    [(lilly,)] = rel.rows("SELECT company_T FROM case_latest_T WHERE case_key_T = '9120012'")
    assert dict(named)[lilly] == sent[lilly] == 3


def test_the_timeline_places_every_dated_case(client, rel, ask):
    got = ask(client, "/api/timeline", grain="year")
    assert got["grain"] == "year"
    cases = ask(client, "/api/summary")["cases"]
    assert sum(n for _, n in got["rows"]) + got["undated"] == cases
    assert got["undated"] == len(rel.case_keys("c.group_first_dt_T IS NULL"))
    # an unknown grain is a year
    assert ask(client, "/api/timeline", grain="fortnight")["grain"] == "year"


def test_years_and_the_timeline_date_a_group_by_its_first_receipt(client, rel, ask):
    """rules/dup-shown-copy.md: the shown copy counts in the year its group was first received."""
    by_year = "SELECT year({}), count(*) FROM case_latest_T WHERE dup_kept_T GROUP BY 1"
    by_group = dict(rel.rows(by_year.format("group_first_dt_T")))
    # 9021021, received in 2026, is shown for a group first received in 2019
    assert by_group != dict(rel.rows(by_year.format("first_fda_dt_T")))
    assert dict(map(tuple, ask(client, "/api/summary")["years"])) == by_group
    timeline = {int(k[:4]): n for k, n in ask(client, "/api/timeline", grain="year")["rows"]}
    assert timeline == {y: n for y, n in by_group.items() if y is not None}


def test_serious_counts_cases_with_any_outcome(client, rel, ask):
    want = rel.case_keys(
        f"EXISTS (SELECT 1 FROM outc_latest_T o WHERE {rel.case_join('o')} "
        "AND o.outc_cod IS NOT NULL)",
    )
    assert ask(client, "/api/summary")["serious"] == len(want)


# the case list ------------------------------------------------------------------


@pytest.mark.parametrize("sort, order", [("newest", "DESC"), ("oldest", "ASC")])
def test_the_case_list_pages_through_every_match_by_its_groups_first_receipt(
    client, rel, ask, tmp_path, sort, order
):
    size = 5  # small enough that the fake release spans several pages
    rows, page = [], 1
    with rules_with(tmp_path, {"explorer-page-size": {"cases_per_page": size}}):
        while True:
            got = ask(client, "/api/cases", dedup="all", sort=sort, page=page)
            assert got["size"] == size and len(got["cases"]) <= size
            rows += got["cases"]
            if len(got["cases"]) < size:
                break
            page += 1
    # rules/dup-shown-copy.md: a group is dated by its first receipt; undated last, ties in case
    # order
    want = rel.rows(
        "SELECT era_T || '/' || case_key_T, CAST(group_first_dt_T AS VARCHAR) "
        f"FROM case_latest_T ORDER BY group_first_dt_T {order} NULLS LAST, era_T, case_key_T"
    )
    assert [(f"{c['era_T']}/{c['case_key_T']}", c["group_first_dt_T"]) for c in rows] == want


def test_the_list_carries_each_cases_drugs_and_reactions(client, ask):
    rows = {
        f"{c['era_T']}/{c['case_key_T']}": c
        for c in ask(client, "/api/cases", reaction="Vomiting")["cases"]
    }
    case = rows["faers/9005005"]
    assert any(d[0] == "OMEPRAZOLE" and d[2] == "C" for d in case["drugs"])
    assert "Vomiting" in case["reactions"]


# the case drill-in -------------------------------------------------------------


def test_a_case_has_its_drugs_reactions_outcomes_indications_and_therapy(client, ask):
    case = ask(client, "/api/case/faers/9005005")
    drugs = {d["drugname"]: d for d in case["drug"]}
    assert "ASPIRIN" in drugs and "OMEPRAZOLE" in drugs
    assert drugs["OMEPRAZOLE"]["role_cod"] == "C"
    assert [r["pt"] for r in case["reac"]] == ["Vomiting"]  # not the 2019q1 version's Nausea
    assert {o["outc_cod"] for o in case["outc"]} == {"HO", "OT"}
    assert {i["indi_pt"] for i in case["indi"]} == {"Pain", "Dyspepsia"}
    assert "ther" in case


def test_a_case_keeps_fda_values_verbatim_beside_the_spelling_shown(client, ask):
    case = ask(client, "/api/case/faers/9007007")
    assert case["reac"][0]["pt"] == "Hepatic enzyme INCREASED"  # as FDA published it
    assert case["reac"][0]["pt_T"].lower() == "hepatic enzyme increased"


def test_each_drug_carries_its_ingredients_in_words_and_where_they_came_from(client, rel, ask):
    """Read from the drug-name step's own table (rule drug-names): the dictionary on FDA's name,
    the dictionary on FDA's active-ingredient field, or none."""
    sources = {
        r["drugname"]: (r["substance_T"], r["substance_source_T"])
        for r in rel.dicts(
            "SELECT d.drugname, s.substance_T, s.substance_source_T FROM drug_latest_T d "
            "JOIN drug_substance_T s USING (era_T, primaryid, quarter_T, drug_seq) "
            "WHERE d.drugname IN ('BAYER LOW DOSE', 'VALSARTAN TEVA', 'ENTRESTO')"
        )
    }
    got = {}
    for key in ("9004004", "9210006", "9210003"):
        for d in ask(client, f"/api/case/faers/{key}")["drug"]:
            got[d["drugname"]] = (d["substance_T"], d["substance_source_T"], d["ingredient_T"])
    assert {k: v[:2] for k, v in got.items()} == sources
    assert got["BAYER LOW DOSE"][1:] == ("diana_prod_ai", "Acetylsalicylic acid")
    assert got["VALSARTAN TEVA"][1:] == ("none", None)
    assert got["ENTRESTO"][2] == "Sacubitril and valsartan"


def test_each_drug_carries_its_route_families_and_the_fields_they_came_from(label_client, ask):
    """Read from the route step's own table (rule drug-route): every family the record could be
    in, sorted, and which of FDA's fields said so; none when nothing is known."""
    got = {
        key: [
            (d["route"], d["route_families_T"], d["route_source_T"])
            for d in ask(label_client, f"/api/case/faers/{key}")["drug"]
        ]
        for key in ("9004004", "9110011", "9013013")
    }
    assert got["9004004"] == [("ORAL", ["by_mouth"], "route")]
    assert got["9110011"] == [("ORAL", ["by_mouth", "skin"], "disagree")]
    assert [r[1] for r in got["9013013"]] == [[]]  # nothing known: no family


def test_a_release_without_routes_gives_no_route_families(explorer_app, own_release, ask):
    manifest = json.loads((own_release / "manifest.json").read_text(encoding="utf-8"))
    del manifest["tables"]["drug_route_T"]
    (own_release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    drug = ask(TestClient(explorer_app(own_release)), "/api/case/faers/9004004")["drug"][0]
    assert drug["route"] == "ORAL"
    assert "route_families_T" not in drug and "route_source_T" not in drug


def test_a_release_without_drug_names_gives_no_ingredient_or_source(dup_client, ask):
    drug = ask(dup_client, "/api/case/faers/7731004")["drug"][0]
    assert (drug["substance_T"], drug["substance_source_T"], drug["ingredient_T"]) == (None,) * 3


def test_fdas_words_for_no_country_are_no_country_and_reach_the_case_as_fda_wrote_them(
    dup_client, ask
):
    """Where FAERS wrote COUNTRY NOT SPECIFIED and gave no event country, country_T is empty and
    FDA's text stays in reporter_country (rule country-not-given)."""
    case = ask(dup_client, "/api/case/faers/7731002")
    assert case["country_T"] is None and case["country_source_T"] is None
    assert case["reporter_country"] in value("country-not-given", "not_countries")


def test_the_case_list_marks_reports_with_no_usable_drug_or_reaction_and_a_serious_outcome(
    dup_client, ask
):
    rows = {c["case_key_T"]: c for c in ask(dup_client, "/api/cases")["cases"]}
    flagged = {k for k, c in rows.items() if c["serious_no_drug_or_reaction_T"]}
    assert {"7731001", "7731003"} <= flagged and not {"7731002", "7731004"} & flagged


def test_case_therapy_dates_as_fda_gave_them(client, rel, ask):
    start = rel.rows(
        f"SELECT t.start_dt FROM ther_latest_T t JOIN case_latest_T c ON {rel.case_join('t')} "
        "WHERE c.caseid = '9020020'"
    )[0][0]
    assert start
    assert start in [t["start_dt"] for t in ask(client, "/api/case/faers/9020020")["ther"]]


def test_a_case_names_the_fields_that_read_not_given_and_keeps_fdas_values(client, ask):
    case = ask(client, f"/api/case/faers/{NOT_GIVEN_CASE}")
    assert {"mfr_sndr", "age", "wt"} <= set(case["not_given_T"])
    # sex and country are read by their own rules (sex-codes, country-not-given): sex_T and
    # country_T say they are not given, and this rule names neither
    assert not {"sex", "occr_country", "reporter_country"} & set(case["not_given_T"])
    assert (case["sex"], case["occr_country"], case["age"]) == (
        "NS",
        "COUNTRY NOT SPECIFIED",
        "999",
    )
    assert (case["sex_T"], case["age_years_T"], case["wt_kg_T"]) == (None, None, None)
    assert case["country_T"] == case["reporter_country"]
    real = ask(client, "/api/case/faers/9005005")
    assert "sex" not in real["not_given_T"] and real["sex_T"] == real["sex"]
    # a blank field reads Not given too
    assert real["age"] is None and "age" in real["not_given_T"]
    assert all("drugname" not in d["not_given_T"] for d in real["drug"])


def test_the_release_answer_carries_the_notes_on_fields_whose_fda_files_changed(client, ask):
    assert ask(client, "/api/release")["field_notes"] == value("explorer-field-notes", "notes")


def test_a_legacy_report_without_a_case_number_opens(client, ask):
    case = ask(client, "/api/case/legacy/ISR:4100003")
    assert case["era_T"] == "legacy" and "4100003" in case["case_key_T"]


def test_a_set_aside_duplicate_names_the_case_kept_instead(client, ask):
    case = ask(client, "/api/case/faers/9020020")
    assert case["dup_kept_T"] is False
    kept = next(g for g in case["group"] if g["dup_kept_T"])
    assert {"era_T": "faers", "case_key_T": "9021021"}.items() <= kept.items()


def test_an_unknown_case_is_not_found(client, ask):
    assert ask(client, "/api/case/faers/no-such-case", status=404)["problem"]


# why a probable duplicate is shown or set aside (rules/dup-shown-copy.md) ------------------


def test_a_set_aside_copy_names_the_copy_shown_and_the_rule_that_grouped_them(client, ask):
    assert ask(client, "/api/case/faers/9020020")["reasons"] == [
        value("dup-shown-copy", "set_aside_line").format(shown_case="9021021"),
        value("dup-shown-copy", "rule_lines")["aeolus"],
    ]


def test_the_shown_copy_names_its_copies_and_is_dated_by_its_groups_first_receipt(client, ask):
    case = ask(client, "/api/case/faers/9021021")
    assert case["reasons"] == [
        value("dup-shown-copy", "shown_line").format(
            other_cases="case 9020020", first_received="February 2019"
        )
    ]
    assert (case["group_first_dt_T"], case["first_fda_dt_T"]) == ("2019-02-10", "2026-05-15")
    # each copy in the group's list keeps its own receipt
    assert [(g["case_key_T"], g["first_fda_dt_T"]) for g in case["group"]] == [
        ("9020020", "2019-02-10")
    ]


def test_a_case_in_no_group_has_no_reason_line(client, ask):
    case = ask(client, "/api/case/faers/9005005")
    assert (case["probable_duplicate_T"], case["reasons"]) == (False, [])


def test_a_copy_grouped_by_both_rules_gives_a_line_for_each(dup_client, ask):
    """7721002 matches 7721001 by the AEOLUS rule and 7721003 by the manufacturer number;
    7721003, received last, is shown for all three."""
    rule_lines = value("dup-shown-copy", "rule_lines")
    assert ask(dup_client, "/api/case/faers/7721002")["reasons"] == [
        value("dup-shown-copy", "set_aside_line").format(shown_case="7721003"),
        rule_lines["aeolus"],
        rule_lines["manufacturer_number"],
    ]
    assert ask(dup_client, "/api/case/faers/7721003")["reasons"] == [
        value("dup-shown-copy", "shown_line").format(
            other_cases="cases 7721001 and 7721002", first_received="March 2019"
        )
    ]
