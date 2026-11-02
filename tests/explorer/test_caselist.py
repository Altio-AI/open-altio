"""The case list (/api/cases) and the cases behind any count: each count of a drug's events, of a
group of reactions, of the Overview and of an event's breakdowns carries the case list's question
for its cases (`cases_query`), and /api/cases with it lists exactly that many cases, page by page,
each once. A breakdown's period, field or value the breakdowns do not know is refused.

Run over the invented release (`release`), the same with MedDRA (`licensed_release`), and the
breakdowns over `breakdown_release` (open_altio.testing.fakefda.BREAKDOWN_STORY: valsartan and
Headache, before the newest quarter and in it).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode

import pytest
from fastapi.testclient import TestClient

from open_altio.explorer.access import LOCAL, Viewer
from open_altio.explorer.breakdowns.fields import SERIOUS
from open_altio.explorer.filters import NOT_GIVEN
from open_altio.explorer.questions import ask as ask_in_process
from open_altio.explorer.questions import open_release_data
from open_altio.testing.caselists import each_lists, listed, over_http

DRUG = "acetylsalicylic acid"
GROUP = ["Headache", "Nausea"]
BREAKDOWN_DRUG, BREAKDOWN_EVENT = "valsartan", "Headache"
NEWEST = {"received_from": "2026-04-01", "received_to": "2026-06-30"}  # 2026q2, the newest quarter
PERIODS = ("before", "window")
# a question that narrows by a reaction both ways the filters can, so an event is counted under them
BOTH_REACTIONS = {"pt": ["Headache", "Nausea"], "reaction": "Headache"}

# a drug's events and a group of reactions --------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [{}, {"sex": "F"}, {"dedup": "all", "prole": ["PS", "SS", "I", "C"]}, BOTH_REACTIONS],
)
def test_every_event_of_a_drug_lists_exactly_its_cases(question, client, licensed_client, ask):
    for web in (client, licensed_client):
        got = ask(web, "/api/events", product=DRUG, **question)
        cases, query = got["columns"].index("cases"), got["columns"].index("cases_query")
        rows = [(r[cases], r[query]) for r in got["rows"]]
        assert each_lists(over_http(web), rows) == len(got["rows"]) > 0


@pytest.mark.parametrize("question", [{"reaction": "Pregnancy"}, {"pt": ["Pregnancy"]}])
def test_an_event_under_the_questions_own_reactions_lists_the_cases_naming_both(
    question, bweb, ask
):
    """Pregnancy's one case also names Headache, which most of the drug's cases name."""
    got = ask(bweb, "/api/events", product=BREAKDOWN_DRUG, **question)
    cases, query = got["columns"].index("cases"), got["columns"].index("cases_query")
    [headache] = [r for r in got["rows"] if r[0] == "Headache"]
    assert headache[cases] == 1
    assert each_lists(over_http(bweb), [(r[cases], r[query]) for r in got["rows"]]) == 2


@pytest.mark.parametrize("question", [{}, {"sex": "F"}, {"pt": ["Haemorrhage"]}])
def test_a_group_of_reactions_lists_exactly_its_cases(question, client, licensed_client, ask):
    for web in (client, licensed_client):
        got = ask(web, "/api/events/group", product=DRUG, reaction=GROUP, **question)
        assert got["cases"] > 0
        assert each_lists(over_http(web), [(got["cases"], got["cases_query"])]) == 1


def test_an_event_no_case_names_lists_no_case(client, ask):
    assert ask(client, "/api/cases", product=DRUG, event="No such reaction")["cases"] == []
    every = ask(client, "/api/cases", product=DRUG)["cases"]
    assert ask(client, "/api/cases", product=DRUG, event=GROUP)["cases"] != every


# the Overview ------------------------------------------------------------------------------------

CHARTS = ("sex", "age", "reporter", "country", "sender", "outcome", "era", "soc", "reactions")


def overview_counts(got: dict[str, Any]) -> list[tuple[int, str]]:
    """The Overview's count line and every bar of its charts, with their questions."""
    counts = [(got["cases"], got["cases_query"])]
    for chart in CHARTS:
        counts += [(n, q) for _, n, q in got.get(chart, [])]
    counts += [(n, q) for _, n, _, q in got.get("drugs", [])]
    counts += [(n, q) for _, n, q in got["years"] if q is not None]
    return counts


@pytest.mark.parametrize(
    "question",
    [
        {},
        {"product": DRUG},
        {"sex": "F", "received_from": "2013-01-01", "received_to": "2020-06-30"},
        {"outcome": "OT", "dedup": "all"},
        BOTH_REACTIONS,
    ],
)
def test_every_bar_of_the_overview_lists_exactly_its_cases(question, client, licensed_client, ask):
    for web in (client, licensed_client):
        got = ask(web, "/api/summary", **question)
        assert each_lists(over_http(web), overview_counts(got)) > len(CHARTS)
        # only the cases with no full date have no question: no filter picks them
        assert all(year is None for year, _, q in got["years"] if q is None)
    assert "soc" in ask(licensed_client, "/api/summary", **question)


def test_a_year_takes_in_only_the_days_the_question_asks_for(client, ask):
    asked = {"received_from": "2013-03-02", "received_to": "2020-06-30"}
    got = ask(client, "/api/summary", **asked)
    by_year = {year: parse_qs(q) for year, _, q in got["years"] if year is not None}
    assert len(by_year) > 1
    for year, q in by_year.items():
        assert q["received_from"] == [max(f"{year}-01-01", asked["received_from"])]
        assert q["received_to"] == [min(f"{year}-12-31", asked["received_to"])]


# an event's breakdowns ---------------------------------------------------------------------------


def breakdown_counts(got: dict[str, Any]) -> list[tuple[int, str]]:
    """Every count of the breakdowns, with its question: the cases in each period, and each
    line's reports, those giving its field, and each value's and onset band's cases."""
    counts = [(got["cases"][p], got["cases_query"][p]) for p in PERIODS]
    for line in got["lines"]:
        for p in PERIODS:
            counts.append((line[p]["cases"], line[p]["cases_query"]))
            if line[p]["given"] is not None:
                counts.append((line[p]["given"], line[p]["given_query"]))
            else:
                assert line[p]["given_query"] is None, line["field"]
            each = [*line["values"], *line.get("bands", [])]
            counts += [(v[p]["cases"], v[p]["cases_query"]) for v in each]
    return counts


@pytest.fixture
def bweb(explorer_app, breakdown_release) -> TestClient:
    return TestClient(explorer_app(breakdown_release))


@pytest.mark.parametrize(
    "question",
    [{}, {"dedup": "all"}, {"sex": "M"}, {"received_from": "2019-01-01"}, {"dechal": ["Y", "N"]}],
)
def test_every_count_of_the_breakdowns_lists_exactly_its_cases(question, bweb, ask):
    got = ask(bweb, "/api/breakdowns", product=BREAKDOWN_DRUG, reaction=BREAKDOWN_EVENT, **question)
    counts = breakdown_counts(got)
    values = sum(len(line["values"]) for line in got["lines"])
    assert each_lists(over_http(bweb), counts) > 2 * values > 0


def test_a_viewer_without_meddra_lists_the_cases_of_every_line_they_are_given(breakdown_release):
    data = open_release_data(breakdown_release, Viewer(id=LOCAL.id, meddra=False, who=False))
    question = {"product": [BREAKDOWN_DRUG], "reaction": [BREAKDOWN_EVENT]}
    got = ask_in_process("GET /api/breakdowns", data, question)
    assert "pregnancy" in got["not_available"]

    def answers(query: dict[str, list[str]]) -> dict[str, Any]:
        return ask_in_process("GET /api/cases", data, query)

    assert each_lists(answers, breakdown_counts(got)) > 0


def test_the_set_aside_copies_are_listed_only_where_their_count_holds_them(bweb, ask):
    got = ask(bweb, "/api/breakdowns", product=BREAKDOWN_DRUG, reaction=BREAKDOWN_EVENT)
    [line] = [line for line in got["lines"] if line["field"] == "duplicates"]
    [aside] = [v for v in line["values"] if v["value"] == "set_aside"]
    assert aside["before"]["cases"] > 0
    copies = listed(over_http(bweb), aside["before"]["cases_query"])
    counted = listed(over_http(bweb), got["cases_query"]["before"])
    assert not set(copies) & set(counted)
    assert set(counted) < set(listed(over_http(bweb), line["before"]["cases_query"]))


def cases_of(web: TestClient, status: int = 200, **asked: Any) -> dict[str, Any]:
    question = {"product": BREAKDOWN_DRUG, "event": BREAKDOWN_EVENT, "period": "window"}
    got = web.get(f"/api/cases?{urlencode(question | asked, doseq=True)}")
    assert got.status_code == status, got.text[:300]
    return got.json()


@pytest.mark.parametrize(
    ("asked", "says"),
    [
        ({"field": "eye_colour"}, "is not a field of the breakdowns"),
        ({"field": "sex", "value": "X"}, "is not a value Sex gives"),
        ({"field": "onset", "value": "soon"}, "is not a value"),
        ({"field": "duplicates", "value": "maybe"}, "is not a value"),
        ({"value": "F"}, "name the field as field"),
        ({"period": "after"}, "Name the period as before or window"),
        ({"event": []}, "Name the event of the breakdowns as event"),
        ({"product": []}, "A breakdown needs a drug"),
    ],
)
def test_a_breakdown_count_the_breakdowns_do_not_know_is_refused(asked, says, bweb):
    assert says in cases_of(bweb, 400, **asked)["problem"]


def test_literature_lists_each_value_and_is_refused_where_the_release_cannot_give_it(
    bweb, ask, explorer_app, no_literature_release
):
    got = ask(bweb, "/api/breakdowns", product=BREAKDOWN_DRUG, reaction=BREAKDOWN_EVENT)
    [line] = [line for line in got["lines"] if line["field"] == "literature"]
    assert {v["value"] for v in line["values"] if v["window"]["cases"]} == {"cites", "_none"}
    for value in line["values"]:
        found = cases_of(bweb, field="literature", value=str(value["value"]))
        assert len(found["cases"]) == value["window"]["cases"]
    assert len(cases_of(bweb, field="literature")["cases"]) == line["window"]["given"]
    assert (
        "is not a value Literature gives"
        in cases_of(bweb, 400, field="literature", value="x")["problem"]
    )
    unread = TestClient(explorer_app(no_literature_release))
    assert "literature reference" in cases_of(unread, 400, field="literature")["problem"]


def test_any_serious_outcome_lists_each_case_of_its_outcomes_once_and_none_without_one(bweb, ask):
    """Every outcome code in the invented release is one of rule serious-outcomes'."""
    got = ask(bweb, "/api/breakdowns", product=BREAKDOWN_DRUG, reaction=BREAKDOWN_EVENT)
    [line] = [line for line in got["lines"] if line["field"] == "seriousness"]
    answers = over_http(bweb)
    for p in PERIODS:
        by = {v["value"]: listed(answers, v[p]["cases_query"]) for v in line["values"]}
        serious, none = by.pop(SERIOUS), by.pop(NOT_GIVEN)
        [gathered] = [v for v in line["values"] if v["value"] == SERIOUS]
        assert len(serious) == len(set(serious)) == gathered[p]["cases"] > 0
        assert set(serious) == set().union(*by.values())
        assert not set(serious) & set(none)
        assert set(serious) | set(none) == set(listed(answers, line[p]["given_query"]))


def test_a_field_without_a_period_is_refused_never_read_as_every_case(bweb, ask):
    got = ask(bweb, "/api/cases", 400, product=BREAKDOWN_DRUG, event=BREAKDOWN_EVENT, field="sex")
    assert "Name the period" in got["problem"]


def test_a_value_is_read_as_its_line_counts_it(bweb, ask):
    got = ask(bweb, "/api/breakdowns", product=BREAKDOWN_DRUG, reaction=BREAKDOWN_EVENT)
    [indication] = [line for line in got["lines"] if line["field"] == "indication"]
    [onset] = [line for line in got["lines"] if line["field"] == "onset"]
    for line in (indication, onset):
        value = next(v for v in line["values"] if any(v[p]["cases"] for p in PERIODS))
        period = next(p for p in PERIODS if value[p]["cases"])
        found = cases_of(bweb, field=line["field"], value=str(value["value"]), period=period)
        assert len(found["cases"]) == value[period]["cases"], line["field"]
