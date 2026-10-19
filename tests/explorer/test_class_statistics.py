"""The Statistics tab's answers by WHO class (src/open_altio/explorer/statistics.py, rule
statistics-classes): the levels a release holds, the list of class and reaction pairs at one
level, a drug's rows with its class's EB05 beside its own, and none of it for a viewer the
classes are hidden from or a release without them. Checked against the release's own
atc_statistics_T, over the release whose priors fit (`stats_release`)."""

from __future__ import annotations

import duckdb
import pytest
from fastapi.testclient import TestClient

from open_altio.explorer.access import Viewer
from open_altio.faers.statistics import classes

DEFAULT = "eb05:at_least:2,cases:at_least:3"


def table(release, sql: str, *params):
    for name in (classes.TABLE, classes.INGREDIENTS_TABLE):
        sql = sql.replace(name, f"'{release / 'parquet' / f'{name}.parquet'}'")
    return duckdb.connect().execute(sql, list(params)).fetchall()


def deepest() -> int:
    return classes.levels()[-1]["level"]


def test_about_names_each_level_the_release_holds_in_the_rules_order(ask, stats_client):
    about = ask(stats_client, "/api/statistics/about")["classes"]
    assert [(v["level"], v["name"]) for v in about["levels"]] == [
        (v["level"], v["name"]) for v in classes.levels()
    ]
    assert all(v["fitted"] and v["pairs"] > 0 for v in about["levels"])
    assert about["rule"] == classes.RULE and about["line"]


@pytest.mark.parametrize("level", [v["level"] for v in classes.levels()])
def test_by_class_lists_one_levels_pairs_the_screen_passes_highest_eb05_first(
    ask, stats_client, stats_release, level
):
    got = ask(stats_client, "/api/statistics", by="class", level=level, **{"pass": DEFAULT})
    held = table(
        stats_release,
        f"SELECT class_T, reaction_T, eb05_T FROM {classes.TABLE} WHERE level_T = ? "
        "AND eb05_T >= 2 AND cases_T >= 3 ORDER BY eb05_T DESC, class_T, reaction_T",
        level,
    )
    assert got["by"] == "class" and got["level"] == level and got["matched"] == len(held) > 0
    shown = [(r["class"], r["term"], r["eb05"]) for r in got["rows"]]
    assert shown == [(c, r.lower(), e) for c, r, e in held][: len(shown)]
    assert all(r["level"] == level and r["class_name"] for r in got["rows"])
    assert "onset_days" not in got["rows"][0] and "ingredient" not in got["rows"][0]


def test_by_class_finds_a_class_by_its_name_or_code(ask, stats_client):
    one = ask(stats_client, "/api/statistics", by="class", level=deepest())["rows"][0]
    for typed in (one["class_name"][:6].lower(), one["class"].lower()):
        found = ask(stats_client, "/api/statistics", by="class", level=deepest(), find=typed)
        assert one["class"] in {r["class"] for r in found["rows"]}
        for r in found["rows"]:
            named = (r["class_name"].lower(), r["reaction"].lower())
            assert r["class"].lower().startswith(typed) or any(typed in n for n in named)


def test_a_drugs_rows_carry_its_classs_eb05_at_the_level_asked(ask, stats_client, stats_release):
    for v in classes.levels():
        got = ask(stats_client, "/api/statistics", ingredient="lisinopril", level=v["level"])
        [(code,)] = table(
            stats_release,
            f"SELECT class_T FROM {classes.INGREDIENTS_TABLE} WHERE ingredient_T = 'lisinopril' "
            "AND level_T = ?",
            v["level"],
        )
        assert got["class"]["code"] == code and got["class"]["level_name"] == v["name"]
        held = dict(
            table(
                stats_release,
                f"SELECT lower(reaction_T), eb05_T FROM {classes.TABLE} "
                "WHERE level_T = ? AND class_T = ?",
                v["level"],
                code,
            )
        )
        assert got["rows"] and all(r["class_eb05"] == held.get(r["term"]) for r in got["rows"])


def test_with_no_level_named_a_drug_gets_its_classs_at_the_deepest(ask, stats_client):
    got = ask(stats_client, "/api/statistics", ingredient="lisinopril")
    assert got["class"]["level"] == deepest()
    # the fixture's deepest class holds lisinopril alone: its EB05 is the drug's own
    assert all(r["class_eb05"] == pytest.approx(r["eb05"]) for r in got["rows"])


def test_a_level_the_release_does_not_hold_is_refused(ask, stats_client):
    ask(stats_client, "/api/statistics", 400, by="class", level=1)
    ask(stats_client, "/api/statistics", 400, ingredient="lisinopril", level="x")


def test_a_viewer_the_classes_are_hidden_from_sees_none_of_them(ask, hooked, stats_release):
    hidden = hooked(viewer=Viewer(id="ann", meddra=False, who=False), release_dir=stats_release)
    assert ask(hidden, "/api/statistics/about")["classes"] is None
    ask(hidden, "/api/statistics", 403, by="class", level=deepest())
    got = ask(hidden, "/api/statistics", ingredient="lisinopril")
    assert got["rows"] and "class" not in got and "class_eb05" not in got["rows"][0]


def test_a_release_without_classes_offers_none(ask, explorer_app, bare_release):
    bare = TestClient(explorer_app(bare_release))
    assert ask(bare, "/api/statistics/about")["classes"] is None
    ask(bare, "/api/statistics", 404, by="class", level=deepest())
