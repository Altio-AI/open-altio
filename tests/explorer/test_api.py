"""The /api routes beyond the questions of explore.py: who is asking
(/api/me), the release being queried and its manifest, and the answers kept
per release. Filters are test_filters.py's, searches test_search.py's, SQL test_sql.py's.
"""

from __future__ import annotations

from open_altio.rulebook import value


def test_me_says_what_this_person_may_do_here(client, ask):
    assert ask(client, "/api/me") == {
        "tiers": {"meddra": False, "who": True},
        "sql": True,
        "exports": True,
        "statistics": True,
        "sql_seconds": value("sql-limits", "timeout_seconds"),
    }


def test_the_release_being_queried_is_named(client, rel, ask):
    got = ask(client, "/api/release")
    assert got["release"] == rel.manifest["release"]
    assert got["cases"] == rel.step("kept_after_duplicates")["count"]["total"]
    assert got["all_cases"] == rel.step("after_deleted_lists")["count"]["total"]
    assert got["set_aside"] == got["all_cases"] - got["cases"]
    # the quarters it holds, and FDA's systems with the quarters each published (rule era-filter)
    assert got["quarters"] == [rel.manifest["quarters"][0], rel.manifest["quarters"][-1]]
    assert got["eras"] == value("era-filter", "quarters")


def test_the_page_is_sent_the_names_and_notes_of_codes_that_name_no_country_of_today(client, ask):
    sent = ask(client, "/api/release")["countries"]
    assert sent == {
        "noted": value("legacy-country", "noted_codes"),
        "not_given": value("country-not-given", "not_countries"),
    }
    assert set(sent["noted"]) == {"CS", "YU", "AN", "EU", "FX"}
    assert all(w["name"] and w["note"] for w in sent["noted"].values())


def test_the_manifest_is_summed_up_with_its_case_funnel(client, rel, ask):
    got = ask(client, "/api/manifest")
    assert got["release"] == rel.manifest["release"]
    assert got["quarters"] == [rel.manifest["quarters"][0], rel.manifest["quarters"][-1]]
    assert {t["name"] for t in got["tables"]} == set(rel.manifest["tables"])
    # the case funnel in the release's own words, each step counted on its own table
    assert got["funnel"] == [
        {"label": s["label"], "table": s["table"], "cases": s["count"]["total"]}
        for s in rel.funnel["steps"]
    ]


def test_a_kept_answer_is_never_given_to_someone_who_may_not_see_it(people, licensed_release, ask):
    """Answers are kept per release; who may see SMQs is part of what they are kept under."""
    web = people(licensed_release)
    path = "/api/summary?smq=96000001:narrow"
    assert ask(web, path, headers={"X-Viewer": "ann+meddra"})["cases"] >= 1
    assert ask(web, path, 403, headers={"X-Viewer": "bo"})["problem"]
