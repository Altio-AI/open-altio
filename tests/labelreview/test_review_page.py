"""The review page: what it shows, what it saves, and what it refuses."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from reviewhelpers import REVIEWER, suggest_all

from open_altio import rulebook
from open_altio.labelreview import batches, coding, decisions, redo, rulecheck
from open_altio.labelreview.page import create_app
from open_altio.testing.fakereview import write_flags

HOST = f"http://{rulebook.value('label-review', 'page_host')}"


def _client(folder, clock) -> TestClient:
    return TestClient(create_app(folder, REVIEWER, clock.now), base_url=HOST)


@pytest.fixture
def suggested(folder, clock):
    batches.start_next(folder, clock.now)
    suggest_all(folder, clock)
    return folder


def test_the_page_and_its_scripts_are_served(suggested, clock):
    client = _client(suggested, clock)
    page = client.get("/")
    assert page.status_code == 200 and "/ui/review.js" in page.text
    assert client.get("/ui/review.js").status_code == 200
    assert client.get("/check").status_code == 200
    assert client.get("/ui/../store.py").status_code == 404


def test_each_item_shows_drug_section_date_phrase_and_the_agents_coding(suggested, clock):
    shown = _client(suggested, clock).get("/api/state").json()
    assert shown["batch"]["number"] == 1
    item = shown["items"][0]
    for field in (
        "drug",
        "section",
        "label_date",
        "sentence",
        "rules_guess",
        "why_uncertain",
    ):
        assert field in item
    assert item["suggestion"]["pts"] == ["Nausea"] and item["suggestion"]["current"]
    assert item["suggestion"]["reason"] and item["decision"] is None
    assert shown["question"] == coding.question()
    assert [r["key"] for r in shown["reasons"]] == list(coding.reasons())
    assert shown["gates"]["passed"] is False and shown["gates"]["reason_only"] == []


def test_the_reviewer_codes_with_terms_or_a_reason_from_the_page(suggested, clock):
    client = _client(suggested, clock)
    first, second = client.get("/api/state").json()["items"][:2]
    after = client.post(
        "/api/decide",
        json={"item_id": first["item_id"], "verdict": "reject", "pts": ["headache"]},
    ).json()
    assert after["items"][0]["decision"]["pts"] == ["Headache"]
    after = client.post(
        "/api/decide",
        json={
            "item_id": second["item_id"],
            "verdict": "reject",
            "none_reason": "population",
        },
    ).json()
    assert after["items"][1]["decision"]["none_reason"] == "population"
    unknown = client.post(
        "/api/decide",
        json={"item_id": first["item_id"], "verdict": "reject", "pts": ["Glimmer"]},
    )
    assert unknown.status_code == 409 and "MedDRA" in unknown.json()["refused"]


def test_a_decision_is_saved_with_who_and_the_gates_move(suggested, clock):
    client = _client(suggested, clock)
    first = client.get("/api/state").json()["items"][0]
    after = client.post(
        "/api/decide", json={"item_id": first["item_id"], "verdict": "accept"}
    ).json()
    assert after["gates"]["decided"] == 1
    assert after["items"][0]["decision"]["reviewer"] == REVIEWER
    assert decisions.latest(suggested)[first["item_id"]].verdict == decisions.ACCEPT


def test_a_refused_decision_says_why_and_saves_nothing(suggested, clock):
    client = _client(suggested, clock)
    first = client.get("/api/state").json()["items"][0]
    refused = client.post("/api/decide", json={"item_id": first["item_id"], "verdict": "reject"})
    assert refused.status_code == 409 and "reason for none" in refused.json()["refused"]
    assert decisions.latest(suggested) == {}


def test_only_this_machine_may_post_and_only_as_json(suggested, clock):
    app = create_app(suggested, REVIEWER, clock.now)
    stranger = TestClient(app, base_url="http://elsewhere.example")
    assert stranger.get("/api/state").status_code == 403
    form = TestClient(app, base_url=HOST).post(
        "/api/decide", data={"item_id": "x", "verdict": "accept"}
    )
    assert form.status_code == 415


def test_the_redo_queue_is_blind(reviewed, clock):
    redo.start(reviewed, clock.now)
    shown = _client(reviewed, clock).get("/api/state", params={"queue": "redo"}).json()
    assert shown["mode"] == "redo"
    assert all("suggestion" not in i and "decision" not in i for i in shown["items"])


def test_the_redo_queue_says_when_there_is_no_redo(suggested, clock):
    answer = _client(suggested, clock).get("/api/state", params={"queue": "redo"})
    assert answer.status_code == 409 and "no blind redo" in answer.json()["refused"]


def test_the_rule_check_queue_shows_flags_and_rates_and_saves_checks(folder, clock, tmp_path):
    rulecheck.draw(folder, write_flags(tmp_path / "public" / "label_flags_T.parquet"), clock.now)
    client = _client(folder, clock)
    shown = client.get("/api/check").json()
    flag = shown["flags"][0]
    assert {"flag", "pt", "outcome", "set_id", "label_date"} <= set(flag)
    assert len(shown["rates"]) == len(rulecheck.outcomes())
    after = client.post("/api/check", json={"flag": flag["flag"], "verdict": "right"}).json()
    assert after["flags"][0]["check"]["verdict"] == "right"
    assert sum(r["checked"] for r in after["rates"]) == 1
