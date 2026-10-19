"""The Statistics tab's /api (src/open_altio/explorer/statistics.py): what a release holds, its
pairs screened, sorted, found and paged, what it refuses, and who may ask. Every answer is checked
against the release's own statistics_T."""

from __future__ import annotations

import json

import duckdb
import pytest

from open_altio.explorer.access import Viewer
from open_altio.explorer.filters import NOT_GIVEN
from open_altio.explorer.found import found_order
from open_altio.explorer.statistics import BEFORE
from open_altio.faers.dates import ONSET_REASONS
from open_altio.rulebook import data_rule, value
from open_altio.stats import screen
from open_altio.testing import fakestats

DEFAULT = "eb05:at_least:2,cases:at_least:3"


def table(release, sql: str, *params):
    path = release / "parquet" / "statistics_T.parquet"
    strata = release / "parquet" / "statistics_strata_T.parquet"
    sql = sql.replace("STRATA", f"'{strata}'").replace("STATS", f"'{path}'")
    return duckdb.connect().execute(sql, list(params)).fetchall()


def test_about_says_what_was_counted_and_each_statistic_in_the_rules_words(ask, stats_client):
    about = ask(stats_client, "/api/statistics/about")
    assert about["present"] and about["ebgm"]["fitted"]
    assert about["counted"]["cases"] == fakestats.CASES
    assert [s["id"] for s in about["statistics"]] == list(screen.RULES)
    for s in about["statistics"]:
        assert s["line"] == data_rule(s["rule"]).line
        assert s["presets"] == screen.presets(s["id"]) and s["start"] == screen.start(s["id"])
    assert about["shown"] == value("explorer-lists", "statistics_shown")


def test_the_default_screen_lists_the_pairs_it_passes_highest_eb05_first(
    ask, stats_client, stats_release
):
    got = ask(stats_client, f"/api/statistics?pass={DEFAULT}")
    [(passing,)] = table(
        stats_release, "SELECT count(*) FROM STATS WHERE eb05_T >= 2 AND cases_T >= 3"
    )
    assert got["matched"] == passing == len(got["rows"]) > 0
    eb05 = [r["eb05"] for r in got["rows"]]
    assert eb05 == sorted(eb05, reverse=True) and min(eb05) >= 2
    assert all(r["cases"] >= 3 for r in got["rows"])


def test_an_ingredients_pairs_found_whatever_its_capitals(ask, stats_client, stats_release):
    got = ask(stats_client, "/api/statistics?ingredient=WARFARIN&sort=cases&dir=asc")
    [(pairs,)] = table(stats_release, "SELECT count(*) FROM STATS WHERE ingredient_T = 'warfarin'")
    assert got["ingredient"] == "warfarin" and got["matched"] == pairs
    assert {r["ingredient"] for r in got["rows"]} == {"warfarin"}
    assert [r["cases"] for r in got["rows"]] == sorted(r["cases"] for r in got["rows"])


def test_find_reads_the_reaction_and_across_the_release_the_ingredient(ask, stats_client):
    mine = ask(stats_client, "/api/statistics?ingredient=warfarin&find=HAEM")["rows"]
    assert mine and all("haem" in r["term"] for r in mine)
    every = ask(stats_client, "/api/statistics?find=warf")["rows"]
    assert every and all(r["ingredient"] == "warfarin" for r in every)


def test_find_lists_the_pairs_named_as_typed_then_starting_so_each_in_the_sorts_order(
    ask, stats_client
):
    """Typing Seizure on a drug's tab puts Seizure first, whatever the sort; an empty box sorts
    plainly. Across the release the ingredient is a name too."""

    def place(row: dict) -> int | None:
        return found_order("ar", row["term"].lower(), row["ingredient"])

    for sort in ("eb05", "cases"):
        answer = ask(stats_client, f"/api/statistics?find=ar&sort={sort}")
        got = answer["rows"]
        places = [place(r) for r in got]
        assert places == sorted(places) and None not in places and 1 in places and 2 in places
        for at in set(places):
            shown = [r[sort] for r in got if place(r) == at]
            assert shown == sorted(shown, key=lambda v: -(v or 0))  # the sort's order in each
        assert answer["matched"] > len(got)  # more than a page: the order picks the first page
    named = ask(stats_client, "/api/statistics?ingredient=warfarin&find=haemorrhage")["rows"]
    assert named[0]["term"] == "haemorrhage"
    assert (
        ask(stats_client, "/api/statistics?find=")["rows"]
        == ask(stats_client, "/api/statistics")["rows"]
    )


def test_a_reaction_is_shown_as_fda_spells_it_and_kept_as_the_filter_names_it(ask, stats_client):
    row = ask(stats_client, "/api/statistics?find=haemorrhage")["rows"][0]
    assert (row["reaction"], row["term"]) == ("Haemorrhage", "haemorrhage")
    assert ask(stats_client, "/api/statistics/about")["reaction_key"] == "fda_text"


def test_a_release_counted_by_pt_names_its_reactions_as_meddra_writes_them(ask, licensed_client):
    about = ask(licensed_client, "/api/statistics/about")
    assert (about["reaction_key"], about["meddra_version"]) == ("meddra_pt", "29.1")
    [row] = ask(licensed_client, "/api/statistics?ingredient=metformin&find=ACIDOSIS")["rows"]
    assert (row["reaction"], row["term"]) == ("Acidosis lactic", "Acidosis lactic")


def test_pages_follow_on_from_the_offset(ask, stats_client):
    shown = value("explorer-lists", "statistics_shown")
    first = ask(stats_client, "/api/statistics?sort=reaction&dir=asc")
    assert len(first["rows"]) == min(shown, first["matched"])
    rest = ask(stats_client, f"/api/statistics?sort=reaction&dir=asc&offset={shown}")
    seen = [(r["ingredient"], r["reaction"]) for r in first["rows"] + rest["rows"]]
    assert len(set(seen)) == len(seen) == min(2 * shown, first["matched"])


def test_each_pair_gives_its_time_to_onset_and_the_drugs_without_one_by_why(
    ask, stats_client, stats_release
):
    got = ask(stats_client, "/api/statistics?sort=onset_drugs&dir=desc")["rows"]
    none = [f"no_onset_{r}" for r in ONSET_REASONS]
    top = got[0]
    [(days, drugs, *why)] = table(
        stats_release,
        f"SELECT onset_days_T, onset_drugs_T, {', '.join(n + '_T' for n in none)} FROM STATS "
        "WHERE ingredient_T = ? AND reaction_T = ?",
        top["ingredient"],
        top["term"],
    )
    assert (top["onset_days"], top["onset_drugs"], [top[n] for n in none]) == (days, drugs, why)
    assert drugs > 0 and [r["onset_drugs"] for r in got] == sorted(
        (r["onset_drugs"] for r in got), reverse=True
    )
    assert ask(stats_client, "/api/statistics?pass=onset_days:at_least:30")["rows"]


def test_a_pairs_ror_by_age_band_and_by_sex_lists_every_value_in_the_explorers_order(
    ask, stats_client, stats_release
):
    pair = ask(stats_client, "/api/statistics?ingredient=warfarin&find=haemorrhage")["rows"][0]
    got = ask(stats_client, "/api/statistics/strata?ingredient=Warfarin&reaction=haemorrhage")
    assert (got["ingredient"], got["reaction"], got["term"], got["cases"]) == (
        "warfarin",
        "Haemorrhage",
        "haemorrhage",
        pair["cases"],
    )
    ages = [b["id"] for b in value("age-bands", "bands")]
    assert [p["by"] for p in got["parts"]] == value("ror-strata", "by")
    order = {"age_band": [*ages, NOT_GIVEN], "sex": [*value("sex-codes", "known"), NOT_GIVEN]}
    for part in got["parts"]:
        assert [s["stratum"] for s in part["strata"]] == order[part["by"]]
        assert sum(s["cases"] for s in part["strata"]) == pair["cases"]  # each case once
        empty = [s for s in part["strata"] if not s["cases"]]
        assert all(s["ror"] is None for s in empty)
    written = table(
        stats_release,
        "SELECT by_T, stratum_T, cases_T, ror_T FROM STRATA "
        "WHERE ingredient_T = 'warfarin' AND reaction_T = 'haemorrhage'",
    )
    shown = {(p["by"], s["stratum"]): (s["cases"], s["ror"]) for p in got["parts"]
             for s in p["strata"]}  # fmt: skip
    unknown = value("statistics-cases", "unknown")
    assert written and all(
        shown[(by, NOT_GIVEN if v == unknown else v)] == (n, ror) for by, v, n, ror in written
    )


def test_a_pair_the_statistics_do_not_name_is_not_found(ask, stats_client):
    got = ask(stats_client, "/api/statistics/strata?ingredient=warfarin&reaction=no+such", 404)
    assert got["problem"] == "The statistics name no such pair."


@pytest.mark.parametrize(
    "query",
    [
        "pass=eb05:at_least:two",
        "pass=ingredient:at_least:2",
        "pass=eb05:more_than:2",
        "sort=nothing",
        "dir=sideways",
        "offset=first",
    ],
)
def test_what_cannot_be_read_is_refused_in_words(ask, stats_client, query):
    assert ask(stats_client, f"/api/statistics?{query}", 400)["problem"]


def test_a_viewer_the_access_hook_does_not_open_statistics_to_is_refused(
    ask, hooked, stats_release
):
    closed = hooked(
        viewer=Viewer(id="ann", meddra=False, who=False, statistics=False),
        release_dir=stats_release,
    )
    assert ask(closed, "/api/me")["statistics"] is False
    assert "not open" in ask(closed, "/api/statistics/about", 403)["problem"]
    assert "not open" in ask(closed, f"/api/statistics?pass={DEFAULT}", 403)["problem"]
    assert (
        "not open" in ask(closed, "/api/statistics/strata?ingredient=a&reaction=b", 403)["problem"]
    )


def test_a_release_whose_prior_did_not_fit_still_has_the_other_statistics(ask, client):
    about = ask(client, "/api/statistics/about")
    assert about["present"] and not about["ebgm"]["fitted"] and about["ebgm"]["reason"]
    rows = ask(client, "/api/statistics")["rows"]
    assert rows and all(r["ebgm"] is None and r["rrr"] is not None for r in rows)


def test_a_release_built_before_the_statistics_says_so(ask, explorer_app, own_release):
    from fastapi.testclient import TestClient

    manifest = json.loads((own_release / "manifest.json").read_text())
    del manifest["statistics"]
    (own_release / "manifest.json").write_text(json.dumps(manifest))
    web = TestClient(explorer_app(own_release))
    assert ask(web, "/api/statistics/about") == {"present": False, "reason": BEFORE}
    assert ask(web, "/api/statistics", 404)["problem"] == BEFORE
