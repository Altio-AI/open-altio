"""The methods page's /api: the rules in plain words with the release's methods, the person's
choices saved beside the release with their checks, and the same page read only where the
access hook does not let the rules be edited. The rebuild itself is test_rebuild.py's."""

from __future__ import annotations

import json
import shutil

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from open_altio.explorer.access import Viewer
from open_altio.explorer.rules_api import CLASSES, NAMED, NOT_HERE
from open_altio.faers.insights.cards.drug_classes import NB09
from open_altio.rulebook import catalogue, load_user_rules, steps
from open_altio.rulebook import rule as rule_file
from open_altio.testing.fakelabelflags import LABELS_AS_OF

OFF_AND_CHANGED = {
    "off": ["deleted-cases"],
    "changed": [{"rule": "dup-manufacturer-number", "key": "max_age_gap_years", "value": 5}],
}


def read(client, status: int = 200) -> dict:
    got = client.get("/api/rules")
    assert got.status_code == status, got.text
    return got.json()


def put(client, body, status: int = 200) -> dict:
    got = client.put("/api/rules", json=body)
    assert got.status_code == status, got.text
    return got.json()


def standard_of(rule: str, key: str):
    info = next(i for i in catalogue() if i.name == rule)
    return next(v.standard for v in info.values if v.key == key)


def test_every_rule_comes_in_plain_words_with_the_release_methods(own_client, own_release):
    got = read(own_client)
    assert [r["name"] for r in got["rules"]] == [i.name for i in catalogue()]
    for rule in got["rules"]:
        assert rule["title"] and rule["line"] and rule["step"]["id"] and rule["step"]["title"], rule
        assert bool(rule["why_locked"]) == rule["always_on"], rule["name"]
    manifest = json.loads((own_release / "manifest.json").read_text(encoding="utf-8"))
    methods = json.loads((own_release / manifest["methods"]).read_text(encoding="utf-8"))
    served = {
        **got["methods"],
        "insights": [
            {k: v for k, v in c.items() if k != "lines"} for c in got["methods"]["insights"]
        ],
    }
    assert served == methods
    assert any("lines" in c for c in got["methods"]["insights"])  # read at serve time
    assert got["release"]["name"] == manifest["release"]
    assert got["release"]["quarters"] == [manifest["quarters"][0], manifest["quarters"][-1]]
    assert got["built"] == {"off": [], "changed": []}  # built with Altio's standard rules
    assert got["standard"] is None


def test_the_page_gets_the_steps_the_rules_it_names_and_where_each_is_coded(
    own_client, own_release
):
    got = read(own_client)
    # the steps as rules/steps.yaml words them now, not as the release froze them
    assert [(s["id"], s["title"]) for s in got["steps"]] == [(s.id, s.title) for s in steps()]
    assert [r["name"] for r in got["named"]] == list(NAMED)
    for named in got["named"]:
        assert named["title"] and named["line"] and named["file"] == f"rules/{named['name']}.md"
    for each in got["rules"] + got["named"]:
        assert each["code"] is None or each["code"] in rule_file(each["name"]).enforced_in
        assert each["code"] is None or each["code"].startswith("src/")
    manifest = json.loads((own_release / "manifest.json").read_text(encoding="utf-8"))
    counted = (manifest.get("statistics") or {}).get("counted")
    assert got["release"]["statistics"] == counted


def test_the_lines_fda_ran_together_are_named(own_client, own_release):
    manifest = json.loads((own_release / "manifest.json").read_text(encoding="utf-8"))
    split = [
        (i["table"], i["quarter"])
        for i in manifest["inputs"]
        for line in i.get("overlong_lines", [])
        if line["records"] > 1
    ]
    assert split, "the fake release holds a run-on line"
    assert [(s["table"], s["quarter"]) for s in read(own_client)["release"]["split_lines"]] == split


def test_on_this_machine_the_rules_can_be_edited(own_client):
    got = read(own_client)
    assert got["editable"] is True
    assert got["saved"] == got["built"] and got["file"] is None
    assert got["rebuild"] == {"state": "idle"}


def test_choices_are_saved_beside_the_release_and_read_back(own_client, own_release):
    saved = put(own_client, OFF_AND_CHANGED)
    gap = standard_of("dup-manufacturer-number", "max_age_gap_years")
    assert saved["saved"] == {
        "off": ["deleted-cases"],
        "changed": [
            {
                "rule": "dup-manufacturer-number",
                "key": "max_age_gap_years",
                "standard": gap,
                "value": 5,
            }
        ],
    }
    path = own_release.parent / "rules.toml"
    assert saved["file"] == path.read_text(encoding="utf-8")
    chosen = load_user_rules(path)
    assert chosen.off == {"deleted-cases"}
    assert chosen.values == {"dup-manufacturer-number": {"max_age_gap_years": 5}}
    again = read(own_client)
    assert again["saved"] == saved["saved"] and again["file"] == saved["file"]
    assert again["built"] == {"off": [], "changed": []}  # the release itself is not rebuilt yet


def test_choosing_altios_values_again_leaves_nothing_changed(own_client):
    put(own_client, OFF_AND_CHANGED)
    gap = standard_of("dup-manufacturer-number", "max_age_gap_years")
    back = put(
        own_client,
        {
            "off": [],
            "changed": [
                {"rule": "dup-manufacturer-number", "key": "max_age_gap_years", "value": gap}
            ],
        },
    )
    assert back["saved"] == {"off": [], "changed": []}


@pytest.mark.parametrize(
    ("body", "said"),
    [
        ({"off": ["latest-version"]}, "is always on"),
        ({"off": ["no-such-rule"]}, "There is no data rule called no-such-rule."),
        (
            {
                "changed": [
                    {"rule": "dup-manufacturer-number", "key": "max_age_gap_years", "value": "five"}
                ]
            },
            "max_age_gap_years must be a number",
        ),
        (
            {"changed": [{"rule": "dup-manufacturer-number", "key": "nothing", "value": 1}]},
            "has no value nothing to set",
        ),
    ],
)
def test_choices_that_break_a_rule_are_refused_in_plain_words(own_client, own_release, body, said):
    put(own_client, OFF_AND_CHANGED)
    before = (own_release.parent / "rules.toml").read_text(encoding="utf-8")
    refused = put(own_client, body, 400)
    assert said in refused["problem"]
    assert (own_release.parent / "rules.toml").read_text(
        encoding="utf-8"
    ) == before  # nothing saved


@pytest.mark.parametrize(
    "body", [{"off": "deleted-cases"}, {"changed": [{"rule": "deleted-cases"}]}, {"off": [1]}]
)
def test_choices_in_another_shape_are_refused(own_client, own_release, body):
    assert "Send the rules as" in put(own_client, body, 400)["problem"]
    assert not (own_release.parent / "rules.toml").exists()


def test_choices_come_as_json_only(own_client, own_release):
    got = own_client.put(
        "/api/rules",
        content="off=deleted-cases",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert got.status_code == 415
    assert not (own_release.parent / "rules.toml").exists()


def test_a_rules_file_that_cannot_be_read_is_said_and_the_switches_show_the_release(
    own_client, own_release
):
    (own_release.parent / "rules.toml").write_text("[deleted-cases\non = false\n", encoding="utf-8")
    got = read(own_client)
    assert "could not be read" in got["problem"]
    assert got["saved"] == got["built"]


def test_where_the_rules_cannot_be_edited_the_page_only_reads(hooked, own_release):
    web = hooked(edits_rules=False, release_dir=own_release)
    got = read(web)
    assert got["editable"] is False
    assert {"saved", "file", "rebuild"}.isdisjoint(got)
    assert got["rules"] and got["methods"]
    for refused in (
        web.put("/api/rules", json=OFF_AND_CHANGED),
        web.post("/api/rules/rebuild", json={}),
        web.get("/api/rules/rebuild"),
    ):
        assert refused.status_code == 403
        assert refused.json() == {"problem": NOT_HERE}
    assert not (own_release.parent / "rules.toml").exists()


def test_who_may_read_the_rules_is_the_access_hooks_to_say(hooked, own_release):
    def nobody(request: Request):
        raise HTTPException(401, "Sign in to use Open Altio.")

    web = hooked(viewer=nobody, release_dir=own_release)
    assert web.get("/api/rules").status_code == 401
    assert web.put("/api/rules", json=OFF_AND_CHANGED).status_code == 401
    assert not (own_release.parent / "rules.toml").exists()


def test_with_no_release_live_the_rules_say_so(explorer_app, tmp_path):
    got = TestClient(explorer_app(tmp_path)).get("/api/rules")
    assert got.status_code == 503
    assert got.json()["problem"] == "No release is live yet."


# ------------------------------------------------------------- WHO's drug classes
def class_rules(got: dict) -> list[dict]:
    return [r for r in got["rules"] if r["step"]["id"] == CLASSES]


def class_cards(got: dict) -> list[str]:
    return [c["id"] for c in got["methods"]["insights"] if c["notebook"] == NB09]


def test_the_drug_classes_are_a_section_of_their_own_with_one_switch(explorer_app, classes_release):
    got = read(TestClient(explorer_app(classes_release)))
    rules = class_rules(got)
    assert [r["name"] for r in rules] == [
        "atc-index",
        "atc-spelling-bridges",
        "atc-group-classes",
        "atc-class-choice",
        "statistics-classes",
    ]
    assert all(r["step"]["switch"] == "atc-index" and r["line"] for r in rules)
    manifest = json.loads((classes_release / "manifest.json").read_text(encoding="utf-8"))
    cards = class_cards(got)
    assert cards, "the release's methods carry the classes' evidence"
    assert got["classes"] == {
        "step": CLASSES,
        "present": True,
        "index_year": manifest["classes"]["index_year"],
        "citation": manifest["classes"]["citation"],
        "cases": manifest["classes"].get("cases"),
        "evidence": {"atc-class-choice": cards},
    }


def test_where_the_host_hides_whos_classes_the_page_holds_nothing_of_them(hooked, classes_release):
    got = read(
        hooked(viewer=Viewer(id="ann", meddra=False, who=False), release_dir=classes_release)
    )
    assert got["classes"] is None and class_rules(got) == [] and class_cards(got) == []
    shown = read(hooked(release_dir=classes_release))
    assert len(got["rules"]) == len(shown["rules"]) - len(class_rules(shown))


def test_where_the_host_hides_whos_classes_the_page_holds_none_of_their_numbers(
    hooked, classes_release, tmp_path
):
    copy = tmp_path / classes_release.name
    shutil.copytree(classes_release, copy)
    methods = json.loads((copy / "methods.json").read_text(encoding="utf-8"))
    methods["numbers"]["classes"] = {"rows": 1}
    (copy / "methods.json").write_text(json.dumps(methods), encoding="utf-8")
    hidden = read(hooked(viewer=Viewer(id="ann", meddra=False, who=False), release_dir=copy))
    assert "classes" not in hidden["methods"]["numbers"] and hidden["methods"]["numbers"]
    assert read(hooked(release_dir=copy))["methods"]["numbers"]["classes"] == {"rows": 1}


def test_a_release_without_the_classes_has_no_section(explorer_app, bare_release):
    got = read(TestClient(explorer_app(bare_release)))
    assert got["classes"] is None and class_rules(got) == [] and class_cards(got) == []


def test_a_class_rule_is_switched_only_with_the_whole_section(own_client, own_release):
    refused = put(own_client, {"off": ["atc-class-choice"]}, 400)
    assert "switch atc-index off instead" in refused["problem"]
    assert not (own_release.parent / "rules.toml").exists()
    saved = put(own_client, {"off": ["atc-index"]})
    assert saved["saved"] == {"off": ["atc-index"], "changed": []}
    assert load_user_rules(own_release.parent / "rules.toml").off == {"atc-index"}


def test_the_release_says_the_day_its_labels_are_as_of(explorer_app, labelled_release, own_client):
    """Rule label-refresh: the page's first line names it; a release without labels has none."""
    got = read(TestClient(explorer_app(labelled_release)))["release"]
    assert got["labels_as_of"] == LABELS_AS_OF.isoformat()
    assert read(own_client)["release"]["labels_as_of"] is None


def test_the_counts_that_need_meddra_come_with_its_version_and_nothing_of_its_content(
    licensed_client,
):
    meddra = licensed_client.get("/api/rules").json()["meddra"]
    numbers = meddra["numbers"]
    assert isinstance(numbers["terms"]["meddra_terms"], int)
    older = numbers["older_terms"]
    assert older["missed_by_todays_term"] <= older["with_an_older_term"] <= older["cases"]
    assert set(meddra) == {"version", "free_text_indications", "numbers"}
