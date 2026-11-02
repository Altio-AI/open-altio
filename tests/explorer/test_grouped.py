"""Statistics for a group of terms counted as one event, and on the cases since a day
(src/open_altio/explorer/grouped.py): a group of one term is that pair's own row of the release's
statistics, a group and a window are counted again apart from the explorer from the release's
own tables and agree, the prior is the release's and never fitted again, a release whose prior
did not fit says why EBGM is empty, and what cannot be answered is refused in plain words."""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
import pytest

from open_altio.explorer.access import LOCAL, Viewer
from open_altio.explorer.grouped import statistics
from open_altio.explorer.questions import open_release_data
from open_altio.explorer.statistics import BEFORE
from open_altio.faers import read_manifest
from open_altio.faers.dates import received_day
from open_altio.faers.statistics.scored import COLUMNS, MEASURES, SCORED
from open_altio.rulebook import value
from open_altio.stats import disproportionality as dp
from open_altio.stats import ebgm
from open_altio.testing.releasereader import ReleaseReader
from open_altio.testing.rules import rules_with

PATH = "/api/statistics/group"
EBGM = ("ebgm", "eb05", "eb95")


def same(got, want) -> bool:
    """Equal within a relative 1e-9, an empty value (null, or NaN in a table) only to one."""
    if want is None or (isinstance(want, float) and math.isnan(want)):
        return got is None
    return got is not None and got == pytest.approx(want, rel=1e-9)


def own_rows(release, table: str = "statistics_T") -> list[dict]:
    return ReleaseReader(release).dicts(f"SELECT * FROM {table} ORDER BY ALL")


def apart(release, ingredient: str, terms: list[str], since: date | None = None) -> dict:
    """The group's answer worked out apart from the explorer, from the release's own tables as
    rule statistics-cases words it: kept cases naming an ingredient of a drug in a suspect role
    and a reaction (FDA's text, case-blind), in strata of age band, sex and the year FDA first
    received the case, each case once; then E over the strata and the statistics' formulas under
    the prior the manifest records."""
    rel = ReleaseReader(release)
    window = f"AND c.{received_day()} >= $since" if since else ""
    text = "nullif(trim(regexp_replace(lower(r.pt), '\\s+', ' ', 'g')), '')"
    suspect = (
        "FROM drug_latest_T d JOIN drug_ingredient_T i USING (era_T, primaryid, quarter_T, "
        "drug_seq) WHERE d.era_T = c.era_T AND d.primaryid = c.primaryid "
        "AND d.quarter_T = c.quarter_T AND list_contains($roles, upper(trim(d.role_cod)))"
    )
    named = (
        "FROM reac_latest_T r WHERE r.era_T = c.era_T AND r.primaryid = c.primaryid "
        f"AND r.quarter_T = c.quarter_T AND {text} IS NOT NULL"
    )
    sql = f"""
    WITH counted AS (
      SELECT coalesce(c.age_band_T, $unknown) AS age, coalesce(c.sex_T, $unknown) AS sex,
        coalesce(CAST(c.init_year_T AS VARCHAR), $unknown) AS year,
        EXISTS (SELECT 1 {suspect} AND i.ingredient_T = $ingredient) AS hi,
        EXISTS (SELECT 1 {named} AND list_contains($terms, {text})) AS hg
      FROM case_latest_T c
      WHERE c.dup_kept_T {window} AND EXISTS (SELECT 1 {suspect}) AND EXISTS (SELECT 1 {named}))
    SELECT count(*), count(*) FILTER (WHERE hi), count(*) FILTER (WHERE hg),
      count(*) FILTER (WHERE hi AND hg)
    FROM counted GROUP BY age, sex, year"""
    given = {
        "roles": list(value("statistics-cases", "product_roles")),
        "unknown": value("statistics-cases", "unknown"),
        "ingredient": ingredient,
        "terms": terms,
        **({"since": since} if since else {}),
    }
    strata = np.array(rel.con.execute(sql, given).fetchall(), dtype=float).reshape(-1, 4)
    n, ni, ng, both = strata.T
    a, total = int(both.sum()), int(n.sum())
    e = float((ni * ng / n).sum())
    out = {"counted": total, "cases": a, "ingredient_cases": int(ni.sum())}
    out["reaction_cases"] = int(ng.sum())
    maths = dp.measures(**dp.table([a], [out["ingredient_cases"]], [out["reaction_cases"]], total))
    fit = rel.manifest["statistics"]["ebgm"]
    if fit["fitted"]:
        maths |= ebgm.score(ebgm.Prior(**fit["prior"]), [a], [e])
    for name in MEASURES:
        source = str(COLUMNS[name])
        out[name] = float(maths[source][0]) if source in maths else None
    out["expected"] = e
    return out


def test_a_group_of_one_term_is_that_pairs_own_row(stats_release):
    data = open_release_data(stats_release, LOCAL)
    rows = own_rows(stats_release)
    assert len(rows) > 100
    for row in rows:
        got = statistics(data, {"product": [row["ingredient_T"]], "reaction": [row["reaction_T"]]})
        for name in SCORED:
            assert same(got[name], row[f"{name}_T"]), (row["ingredient_T"], row["reaction_T"])
        assert got["not_available"] == {}


def test_a_group_of_one_pt_is_that_pairs_own_row_in_a_release_counted_by_pt(licensed_release):
    data = open_release_data(licensed_release, LOCAL)
    rows = own_rows(licensed_release)
    assert {r["reaction_T"] for r in rows} >= {"Acidosis lactic"}
    for row in rows:
        got = statistics(data, {"product": [row["ingredient_T"]], "reaction": [row["reaction_T"]]})
        assert got["reactions"] == [row["reaction_T"]]
        for name in SCORED:
            assert same(got[name], row[f"{name}_T"]), (row["ingredient_T"], row["reaction_T"])


def test_a_viewer_shown_fdas_text_is_counted_by_it(licensed_release):
    data = open_release_data(
        licensed_release, Viewer(id="ann", meddra=False, who=False, todays_names=False)
    )
    rows = own_rows(licensed_release, "statistics_as_published_T")
    assert {r["reaction_T"] for r in rows} >= {"lactic acidosis"}
    for row in rows:
        got = statistics(data, {"product": [row["ingredient_T"]], "reaction": [row["reaction_T"]]})
        for name in SCORED:
            assert same(got[name], row[f"{name}_T"]), (row["ingredient_T"], row["reaction_T"])


@pytest.mark.parametrize(
    ("fixture", "ingredient", "terms", "since"),
    [
        ("stats_release", "warfarin", ["haemorrhage", "nausea"], None),
        ("stats_release", "warfarin", ["haemorrhage", "nausea"], date(2025, 3, 1)),
        ("stats_release", "warfarin", ["haemorrhage"], date(2025, 3, 2)),
        ("release", "acetylsalicylic acid", ["headache", "nausea", "haemorrhage"], None),
        ("release", "valsartan", ["headache"], date(2019, 1, 1)),
    ],
)
def test_a_group_and_a_window_agree_with_a_count_made_apart(
    request, fixture, ingredient, terms, since
):
    release = request.getfixturevalue(fixture)
    query = {"product": [ingredient], "reaction": terms}
    if since:
        query["received_from"] = [since.isoformat()]
    got = statistics(open_release_data(release, LOCAL), query)
    want = apart(release, ingredient, terms, since)
    assert got["cases"] > 0 and got["received_from"] == since
    for name, number in want.items():
        assert same(got[name], number), name


def test_only_cases_naming_a_drug_in_one_of_the_rules_suspect_roles_are_counted(release, tmp_path):
    """Counted with the first suspect role alone, a case whose drugs are all in the others is no
    longer in the table: in the invented release one case names its ingredients only so."""
    first = list(value("statistics-cases", "product_roles"))[:1]
    with rules_with(tmp_path, {"statistics-cases": {"product_roles": first}}):
        query = {"product": ["acetylsalicylic acid"], "reaction": ["headache"]}
        got = statistics(open_release_data(release, LOCAL), query)
        want = apart(release, "acetylsalicylic acid", ["headache"])
    assert got["counted"] < read_manifest(release)["statistics"]["counted"]["cases"]
    for name, number in want.items():
        assert same(got[name], number), name


def test_a_case_naming_two_of_the_groups_terms_counts_once(ask, stats_client):
    group = ask(stats_client, PATH, product="warfarin", reaction=["Haemorrhage", "NAUSEA"])
    one = ask(stats_client, PATH, product="warfarin", reaction="haemorrhage")
    other = ask(stats_client, PATH, product="warfarin", reaction="nausea")
    assert group["reactions"] == ["Haemorrhage", "Nausea"]
    assert max(one["cases"], other["cases"]) < group["cases"] < one["cases"] + other["cases"]
    assert group["counted"] == one["counted"] == other["counted"]


def test_a_window_counts_the_cases_received_that_day_or_later(ask, stats_client, stats_release):
    whole = ask(stats_client, PATH, product="warfarin", reaction="nausea")
    first = ReleaseReader(stats_release).rows(f"SELECT min({received_day()}) FROM case_latest_T")
    from_first = ask(
        stats_client, PATH, product="warfarin", reaction="nausea", received_from=first[0][0]
    )
    for answer in (whole, from_first):
        del answer["received_from"]
    assert from_first == whole
    later = ask(
        stats_client, PATH, product="warfarin", reaction="nausea", received_from="2025-03-01"
    )
    after = ask(
        stats_client, PATH, product="warfarin", reaction="nausea", received_from="2025-03-02"
    )
    assert whole["counted"] > later["counted"] > after["counted"] > 0
    assert later["received_from"] == "2025-03-01"


def test_a_window_after_the_last_case_counts_none_and_gives_no_statistic(ask, stats_client):
    got = ask(stats_client, PATH, product="warfarin", reaction="nausea", received_from="2099-01-01")
    assert (got["counted"], got["cases"], got["expected"]) == (0, 0, 0)
    assert all(got[name] is None for name in MEASURES if name != "expected")


def test_the_prior_is_the_releases_own_and_never_fitted_again(stats_release, monkeypatch):
    def no_fit(*args, **kwargs):
        raise AssertionError("the group's statistics fitted a prior")

    monkeypatch.setattr(ebgm, "fit_prior", no_fit)
    data = open_release_data(stats_release, LOCAL)
    since = {"received_from": ["2025-03-01"]}
    got = statistics(data, {"product": ["warfarin"], "reaction": ["nausea"]} | since)
    prior = ebgm.Prior(**read_manifest(stats_release)["statistics"]["ebgm"]["prior"])
    [want] = ebgm.score(prior, [got["cases"]], [got["expected"]])["EBGM"]
    assert got["ebgm"] == pytest.approx(want, rel=1e-12)


def test_a_release_whose_prior_did_not_fit_answers_ebgm_as_not_available_with_its_reason(
    ask, client, release
):
    reason = read_manifest(release)["statistics"]["ebgm"]["reason"]
    got = ask(client, PATH, product="acetylsalicylic acid", reaction=["headache", "nausea"])
    assert got["not_available"] == dict.fromkeys(EBGM, reason)
    assert all(got[name] is None for name in EBGM) and got["ic"] is not None


def test_an_ingredient_never_a_suspect_drug_has_no_case_and_no_statistic(ask, client):
    """Omeprazole is named only as a concomitant drug in the invented release."""
    got = ask(client, PATH, product="omeprazole", reaction="headache")
    assert (got["cases"], got["ingredient_cases"], got["expected"]) == (0, 0, 0)
    assert got["reaction_cases"] > 0 and got["ic"] is None


@pytest.mark.parametrize(
    ("query", "status"),
    [
        ({"product": "warfarin"}, 400),  # no term
        ({"product": "warfarin", "reaction": " "}, 400),
        ({"product": "warfarin", "reaction": "nausea", "received_from": "2025-3-1"}, 400),
        ({"product": "warfarin", "reaction": "nausea", "received_from": "20250301"}, 400),
        ({"product": "warfarin", "reaction": "nausea", "received_from": "2025-02-30"}, 400),
        ({"reaction": "nausea"}, 400),  # no drug
        ({"product": "no such drug", "reaction": "nausea"}, 404),
    ],
)
def test_what_cannot_be_counted_is_refused_in_plain_words(ask, stats_client, query, status):
    problem = ask(stats_client, PATH, status, **query)["problem"]
    assert problem.endswith(".") and "_T" not in problem


def test_a_combination_is_refused_for_its_ingredients_own(ask, client):
    got = ask(client, PATH, 400, product="sacubitril;valsartan", reaction="headache")
    assert "each of its ingredients" in got["problem"]


def test_a_viewer_the_access_hook_does_not_open_statistics_to_is_refused(
    ask, hooked, stats_release
):
    closed = hooked(
        viewer=Viewer(id="ann", meddra=False, who=False, statistics=False),
        release_dir=stats_release,
    )
    assert "not open" in ask(closed, PATH, 403, product="warfarin", reaction="nausea")["problem"]


def test_a_release_built_before_the_statistics_says_so(ask, explorer_app, own_release):
    from fastapi.testclient import TestClient

    manifest = json.loads((own_release / "manifest.json").read_text())
    del manifest["statistics"]
    (own_release / "manifest.json").write_text(json.dumps(manifest))
    web = TestClient(explorer_app(own_release))
    assert ask(web, PATH, 404, product="warfarin", reaction="nausea")["problem"] == BEFORE
