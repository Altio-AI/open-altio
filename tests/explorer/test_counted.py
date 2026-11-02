"""A counted question (/api/count): a question's cases counted by one field of rule
counted-question, each value with the case list's question for exactly its cases. A `by` outside
the rule is refused naming the choices; a filter value that is not one of its choices is left out
and the answer says so; the same question gives the same bytes.

Run over the invented release (`release`) and the same with MedDRA (`licensed_release`).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from open_altio.explorer.access import LOCAL
from open_altio.explorer.answers import Problem, answer
from open_altio.explorer.filters import NOT_A_CHOICE, NOT_A_DAY, NOT_GIVEN
from open_altio.explorer.questions import ask as ask_in_process
from open_altio.explorer.questions import open_release_data
from open_altio.rulebook import value
from open_altio.testing.caselists import each_lists, over_http

DRUG = "acetylsalicylic acid"
BY = list(value("counted-question", "by"))
QUESTIONS = [
    {},
    {"product": DRUG},
    # a window that starts and ends inside a year, a quarter and a month holding the drug's cases
    {"product": DRUG, "received_from": "2012-05-03", "received_to": "2019-03-02"},
    {"product": DRUG, "sex": "F", "age": NOT_GIVEN, "received_from": "2013-03-02"},
    {"product": DRUG, "dedup": "all", "prole": ["PS", "SS", "I", "C"]},
    # reactions the question already names, which an event's cases must name too
    {"pt": ["Nausea"]},
    {"pt": ["Headache", "Nausea"], "reaction": "Headache"},
]


def test_a_by_outside_the_rule_answers_400_naming_the_choices(client, release):
    for by in ("", "weight", "Sex", "drug"):
        got = client.get(f"/api/count?by={by}")
        assert got.status_code == 400, by
        said = got.json()["problem"]
        assert all(choice in said for choice in BY), said
    with pytest.raises(Problem) as refused:
        ask_in_process("GET /api/count", open_release_data(release, LOCAL), {"by": ["weight"]})
    assert refused.value.status == 400


def test_a_filter_value_that_is_not_a_choice_is_left_out_and_described_says_so(client, ask):
    plain = ask(client, "/api/count", product=DRUG, by="sex")
    odd = {"role": "XX", "age": "no-such-band", "received_to": "2026-13-40", "label": "maybe"}
    got = ask(client, "/api/count", product=DRUG, by="sex", **odd)
    assert [r[:2] for r in got["counts"]] == [r[:2] for r in plain["counts"]]
    assert got["total"] == plain["total"] > 0
    assert not [line for line in plain["described"] if line.startswith("Left out")]
    for name, given in odd.items():
        why = NOT_A_DAY if name == "received_to" else NOT_A_CHOICE
        assert f"Left out: {name} {given}, {why}" in got["described"], name
    # the question as asked keeps them
    assert {k: got["question"][k] for k in odd} == {k: [v] for k, v in odd.items()}


@pytest.mark.parametrize("by", BY)
@pytest.mark.parametrize("question", QUESTIONS)
def test_each_cases_query_lists_exactly_its_cases(by, question, client, licensed_client, ask):
    for web in (client, licensed_client):
        got = ask(web, "/api/count", by=by, **question)
        assert got["by"] == by and got["total"] == ask(web, "/api/summary", **question)["cases"]
        queried = [(n, q) for _, n, q in got["counts"] if q is not None]
        assert each_lists(over_http(web), queried) == len(queried) > 0
        # only the cases no filter picks have no question: those with no day or no reaction
        assert all(v is None for v, _, q in got["counts"] if q is None)
        if by not in ("event", "outcome", "route", "dose_form", "lot"):  # one value of each other
            assert sum(n for _, n, _ in got["counts"]) == got["total"]


@pytest.mark.parametrize("question", [{"reaction": "Pregnancy"}, {"pt": ["Pregnancy"]}])
def test_an_event_under_the_questions_own_reactions_lists_the_cases_naming_both(
    question, explorer_app, breakdown_release, ask
):
    """On the breakdowns' release, Pregnancy's one case also names Headache, which most of
    valsartan's cases name."""
    web = TestClient(explorer_app(breakdown_release))
    got = ask(web, "/api/count", product="valsartan", by="event", **question)
    assert counts_of(got["counts"])["Headache"] == 1
    assert each_lists(over_http(web), [(n, q) for _, n, q in got["counts"]]) == 2


def counts_of(got: dict[str, Any]) -> dict[Any, int]:
    return {v: n for v, n, *_ in got}


def test_each_field_counts_as_the_overview_charts_it(client, ask):
    """A second reading of the same numbers: the Overview's charts, each counted under every
    other filter, so with no filter of their own they count what the counted question does."""
    overview = ask(client, "/api/summary", product=DRUG)
    for by in ("sex", "age", "country", "reporter", "outcome"):
        got = ask(client, "/api/count", product=DRUG, by=by)
        charted = {NOT_GIVEN if v is None else v: n for v, n in counts_of(overview[by]).items()}
        assert counts_of(got["counts"]) == charted, by
    got = ask(client, "/api/count", product=DRUG, by="year")
    assert counts_of(got["counts"]) == counts_of(overview["years"])
    assert [v for v, *_ in got["counts"]] == sorted(v for v, *_ in got["counts"])


def test_a_count_by_outcome_takes_no_outcome_filter(client):
    got = client.get(f"/api/count?product={DRUG}&by=outcome&outcome=DE")
    assert got.status_code == 400 and "outcome" in got.json()["problem"]


@pytest.mark.parametrize("by", ["route", "dose_form", "lot"])
def test_a_count_by_a_drug_records_field_takes_no_filter_on_that_field(client, by):
    got = client.get(f"/api/count?product={DRUG}&by={by}&{by}=ORAL")
    assert got.status_code == 400 and by in got.json()["problem"]


def test_the_same_question_asked_twice_gives_the_same_bytes(client, release):
    data = open_release_data(release, LOCAL)
    for by in BY:
        address = f"/api/count?product={DRUG}&by={by}&sex=F"
        first, again = client.get(address), client.get(address)
        assert first.status_code == 200 and first.content == again.content, by
        query = {"product": [DRUG], "by": [by], "sex": ["F"]}
        fresh = open_release_data(release, LOCAL)
        assert answer(ask_in_process("GET /api/count", fresh, query)).body == first.content, by
        assert json.loads(answer(ask_in_process("GET /api/count", data, query)).body) == (
            first.json()
        )
