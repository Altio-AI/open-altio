"""A drug's statistics with each of its events (src/open_altio/explorer/eventstats.py): every
event's numbers are its pair's own row of the release's statistics, no filter or drug setting
changes them, a release whose prior did not fit says why EBGM is empty, and what cannot be
answered is refused in plain words. What each answer should hold is read from the release's own
statistics_T."""

from __future__ import annotations

import json
import math

import duckdb
import pytest

from open_altio.explorer.access import Viewer
from open_altio.explorer.eventstats import EBGM, STATISTICS
from open_altio.explorer.statistics import BEFORE
from open_altio.faers import read_manifest

PATH = "/api/events/statistics"


def pairs(release, table: str = "statistics_T") -> dict[str, dict[str, dict]]:
    """The release's own statistics, read from its Parquet: ingredient -> reaction -> row."""
    cur = duckdb.connect().execute(
        "SELECT * FROM read_parquet(?)", [str(release / "parquet" / f"{table}.parquet")]
    )
    names = [d[0] for d in cur.description]
    out: dict[str, dict[str, dict]] = {}
    for values in cur.fetchall():
        row = dict(zip(names, values, strict=True))
        out.setdefault(row["ingredient_T"], {})[row["reaction_T"]] = row
    return out


def same(got, want) -> bool:
    """Equal within a relative 1e-9, an empty value (null, or NaN in the table) only to one."""
    if want is None or (isinstance(want, float) and math.isnan(want)):
        return got is None
    return got is not None and got == pytest.approx(want, rel=1e-9)


def rows_of(answer: dict) -> dict[str, dict]:
    """An answer's rows by `term`, each as {column: value}."""
    return {r[1]: dict(zip(answer["columns"], r, strict=True)) for r in answer["rows"]}


def test_each_event_carries_its_pairs_own_row_of_the_releases_statistics(
    ask, stats_client, stats_release
):
    every = pairs(stats_release)
    assert len(every) > 1
    for ingredient, own in every.items():
        got = ask(stats_client, PATH, product=ingredient)
        assert got["ingredient"] == ingredient and got["columns"] == ["pt", "term", *STATISTICS]
        found = rows_of(got)
        assert set(found) == set(own)
        for term, row in found.items():
            for name in STATISTICS:
                assert same(row[name], own[term][f"{name}_T"]), (ingredient, term, name)
    assert got["not_available"] == {}


def test_an_event_is_shown_as_fda_spells_it_and_kept_as_the_filter_names_it(ask, stats_client):
    row = rows_of(ask(stats_client, PATH, product="warfarin"))["haemorrhage"]
    assert (row["pt"], row["term"]) == ("Haemorrhage", "haemorrhage")


def test_no_filter_window_or_drug_setting_changes_them(ask, stats_client):
    plain = ask(stats_client, PATH, product="warfarin")
    narrowed = ask(
        stats_client,
        PATH,
        product="warfarin",
        sex="F",
        received_from="2025-01-01",
        prole="C",
        unit="exact",
        pt="Nausea",
        exclude="WARFARIN",
    )
    assert json.dumps(narrowed) == json.dumps(plain)


def test_another_of_fdas_names_for_the_drug_gives_its_ingredients_statistics(ask, stats_client):
    by_name = ask(stats_client, PATH, product="aspirin")
    assert by_name == ask(stats_client, PATH, product="acetylsalicylic acid")
    assert by_name["ingredient"] == "acetylsalicylic acid" and by_name["rows"]


def test_an_ingredient_never_a_suspect_drug_has_no_events_with_statistics(ask, client):
    """Omeprazole is named only as a concomitant drug in the invented release."""
    assert ask(client, PATH, product="omeprazole")["rows"] == []


def test_a_release_counted_by_pt_names_each_event_as_meddra_writes_it(
    ask, licensed_client, licensed_release
):
    found = rows_of(ask(licensed_client, PATH, product="metformin"))
    assert set(found) == set(pairs(licensed_release)["metformin"])
    assert (found["Acidosis lactic"]["pt"], found["Acidosis lactic"]["term"]) == (
        "Acidosis lactic",
        "Acidosis lactic",
    )


def test_a_viewer_shown_fdas_text_is_given_the_statistics_counted_by_it(
    ask, hooked, licensed_release
):
    fda_text = hooked(
        viewer=Viewer(id="ann", meddra=False, who=False, todays_names=False),
        release_dir=licensed_release,
    )
    found = rows_of(ask(fda_text, PATH, product="metformin"))
    own = pairs(licensed_release, "statistics_as_published_T")["metformin"]
    assert set(found) == set(own) == {"lactic acidosis"}
    for name in STATISTICS:
        assert same(found["lactic acidosis"][name], own["lactic acidosis"][f"{name}_T"]), name


def test_a_release_whose_prior_did_not_fit_says_why_ebgm_is_empty(ask, client, release):
    reason = read_manifest(release)["statistics"]["ebgm"]["reason"]
    got = ask(client, PATH, product="acetylsalicylic acid")
    assert got["not_available"] == dict.fromkeys(EBGM, reason)
    found = rows_of(got).values()
    assert found and all(r["ebgm"] is None and r["ic"] is not None for r in found)


@pytest.mark.parametrize(
    ("product", "status"),
    [
        ("", 400),  # no drug named
        ("sacubitril;valsartan", 400),  # a combination: each ingredient has its own
        ("VALSARTAN TEVA", 404),  # FDA's spelling with no ingredient
        ("no such drug", 404),
    ],
)
def test_what_has_no_statistics_is_refused_in_plain_words(ask, client, product, status):
    problem = ask(client, PATH, status, product=product)["problem"]
    assert problem.endswith(".") and "_T" not in problem


def test_a_viewer_the_access_hook_does_not_open_statistics_to_is_refused(
    ask, hooked, stats_release
):
    closed = hooked(
        viewer=Viewer(id="ann", meddra=False, who=False, statistics=False),
        release_dir=stats_release,
    )
    assert "not open" in ask(closed, PATH, 403, product="warfarin")["problem"]


def test_a_release_built_before_the_statistics_says_so(ask, explorer_app, own_release):
    from fastapi.testclient import TestClient

    manifest = json.loads((own_release / "manifest.json").read_text())
    del manifest["statistics"]
    (own_release / "manifest.json").write_text(json.dumps(manifest))
    web = TestClient(explorer_app(own_release))
    assert ask(web, PATH, 404, product="warfarin")["problem"] == BEFORE
