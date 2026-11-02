"""The questions and their answers: every /api route is published or the explorer's own, each
published route answers what the snapshot lists, the same as its function, naming the release
it was counted on; and the same question gives the same answer, on the live release and on an
earlier folder a product keeps."""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from open_altio import CONTRACT_VERSION
from open_altio.explorer.access import LOCAL
from open_altio.explorer.answers import answer
from open_altio.explorer.questions import INTERNAL, PUBLISHED, ask, open_release_data
from open_altio.explorer.release import point_live
from open_altio.faers import NotARelease, read_manifest
from open_altio.testing.contract import (
    ASKED,
    SnapshotRefused,
    answered,
    keys_of,
    query_of,
    renewed,
)

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = json.loads((Path(__file__).parent / "snapshots" / "api.json").read_text("utf-8"))
API_PAGE = (ROOT / "docs" / "reference" / "api.md").read_text(encoding="utf-8")
ASKED_BY_FUNCTION = [route for route, how in PUBLISHED.items() if how is not None]
NOT_ON_A_RELEASE = {"GET /api/me"}  # who is asking: answered with no release live


def routes_of(app) -> set[str]:
    """Every /api route an app serves, as "METHOD /path"."""
    paths = app.openapi()["paths"]
    return {f"{m.upper()} {p}" for p, ops in paths.items() if p.startswith("/api") for m in ops}


# every route is listed --------------------------------------------------------------------------


def test_every_api_route_is_published_or_the_explorers_own(contract_app, release):
    served = routes_of(contract_app(release))
    assert served - set(PUBLISHED) - set(INTERNAL) == set()
    assert set(PUBLISHED) | set(INTERNAL) <= served
    assert not set(PUBLISHED) & set(INTERNAL)


def test_every_published_route_is_asked_and_in_the_snapshot_and_on_the_page():
    assert set(ASKED) == set(PUBLISHED) == set(SNAPSHOT["routes"])
    assert SNAPSHOT["version"] == CONTRACT_VERSION
    sections = dict(re.findall(r"^### `([^`]+)`\n(.*?)(?=^#|\Z)", API_PAGE, re.M | re.S))
    assert set(sections) == set(PUBLISHED)
    for route, keys in SNAPSHOT["routes"].items():
        answers = re.search(r"^- Answers: (.*)$", sections[route], re.M)
        listed = set(re.findall(r"`(\w+)`", answers.group(1))) if answers else set()
        assert listed == set(keys), f"{route}: its answer's keys on docs/reference/api.md"


# what each answers -------------------------------------------------------------------------------


def test_each_published_route_answers_every_key_the_snapshot_lists_and_no_other(web):
    """A key that goes, or a route that answers no more, fails here before a product finds out;
    a new key is listed by running scripts/contract_snapshot.py."""
    for route, keys in SNAPSHOT["routes"].items():
        got = answered(web, route)
        assert got.status_code == 200, (route, got.text[:200])
        assert keys_of(got) == keys, f"{route}: run scripts/contract_snapshot.py"


def test_each_answer_counted_on_a_release_names_it(web, labelled_release):
    manifest = read_manifest(labelled_release)
    named = {
        "release": manifest["release"],
        "source": "faers",
        "first_quarter": manifest["quarters"][0],
        "last_quarter": manifest["quarters"][-1],
    }
    for route in PUBLISHED:
        got = answered(web, route)
        found = got.json() if keys_of(got) else None  # a file has no keys
        if route in NOT_ON_A_RELEASE or not isinstance(found, dict):
            continue  # a list or a file: /api/manifest names the release they come from
        assert found["counted_on"] == named, route
    assert "counted_on" not in answered(web, "GET /api/me").json()


@pytest.mark.parametrize("route", ASKED_BY_FUNCTION)
def test_a_route_and_its_function_answer_the_same(route, web, labelled_release):
    data = open_release_data(labelled_release, LOCAL)
    assert json.loads(answer(ask(route, data, query_of(route))).body) == answered(web, route).json()


def test_a_route_answered_over_http_only_is_not_asked_in_process(labelled_release):
    data = open_release_data(labelled_release, LOCAL)
    with pytest.raises(ValueError, match="over HTTP only"):
        ask("POST /api/sql", data, {})
    with pytest.raises(KeyError):
        ask("GET /api/rules", data, {})


# the same question, the same answer --------------------------------------------------------------


def same_bytes(route: str, got: Response) -> object:
    """What two asks of a question must hold byte for byte: a JSON answer's body, but for how
    long a query ran (`seconds`); a zip's files, not the times it stamps on them."""
    kind = got.headers.get("content-type", "")
    if kind.startswith("application/json"):
        found = got.json()
        return json.dumps(
            {k: v for k, v in found.items() if k != "seconds"}
            if route == "POST /api/sql"
            else found
        )
    if kind.startswith("application/zip"):
        with zipfile.ZipFile(io.BytesIO(got.content)) as z:
            return {name: z.read(name) for name in z.namelist()}
    return got.content


def test_the_same_question_asked_twice_gives_the_same_answer(web):
    for route in PUBLISHED:
        first, again = answered(web, route), answered(web, route)
        assert (first.status_code, same_bytes(route, first)) == (
            again.status_code,
            same_bytes(route, again),
        ), route


def test_an_earlier_folder_a_product_keeps_answers_its_own_counts_after_another_is_live(
    contract_app, labelled_release, dup_rel, tmp_path
):
    earlier, later = tmp_path / "earlier", tmp_path / "later"
    shutil.copytree(labelled_release, earlier)
    shutil.copytree(dup_rel.path, later)
    live = tmp_path / "live"
    point_live(live, earlier)
    web = TestClient(contract_app(live))
    before = {route: answered(web, route).json() for route in ASKED_BY_FUNCTION}
    point_live(live, later)
    assert answered(web, "GET /api/summary").json()["cases"] != before["GET /api/summary"]["cases"]
    data = open_release_data(earlier, LOCAL)
    for route in ASKED_BY_FUNCTION:
        assert json.loads(answer(ask(route, data, query_of(route))).body) == before[route], route
    with pytest.raises(NotARelease):
        open_release_data(live, LOCAL)  # the live pointer is not a release folder


# any drug, counted the same way -------------------------------------------------------------

# an ingredient reported alone, and one the invented release holds only inside a combination
ALONE, INSIDE = "acetylsalicylic acid", "sacubitril"
COMBINATION = "sacubitril;valsartan"
ANALYSES = [
    route
    for route, how in PUBLISHED.items()
    if how is not None and "product" in query_of(route) and route not in NOT_ON_A_RELEASE
]


def for_drug(data, route: str, drug: str, **settings: str):
    """`route`'s question, as ASKED puts it, about `drug` with these settings."""
    query = query_of(route) | {"product": [drug]} | {k: [v] for k, v in settings.items()}
    return ask(route, data, query)


def cases_of(data, drug: str, **settings: str) -> set[str]:
    listed = for_drug(data, "GET /api/cases", drug, **settings)["cases"]
    return {f"{c['era_T']}/{c['case_key_T']}" for c in listed}


def test_every_analysis_answers_the_same_keys_for_any_drug(labelled_release):
    data = open_release_data(labelled_release, LOCAL)
    assert cases_of(data, INSIDE) and not cases_of(data, INSIDE, unit="exact")
    assert "GET /api/events" in ANALYSES and len(ANALYSES) > 3
    for route in ANALYSES:
        alone, inside = for_drug(data, route, ALONE), for_drug(data, route, INSIDE)
        assert sorted(alone) == sorted(inside), route
        if "columns" in alone:
            assert alone["columns"] == inside["columns"], route


def test_with_any_product_an_ingredient_counts_every_case_of_a_combination_holding_it(
    labelled_release,
):
    data = open_release_data(labelled_release, LOCAL)
    combined = cases_of(data, COMBINATION, unit="exact")
    assert combined
    for part in COMBINATION.split(";"):
        assert combined <= cases_of(data, part, unit="any"), part
        counts = for_drug(data, "GET /api/summary", part, unit="any")["cases"]
        assert counts >= len(combined), part
        theirs = for_drug(data, "GET /api/events", part, unit="any")
        ours = for_drug(data, "GET /api/events", COMBINATION, unit="exact")
        by_pt = {r[0]: r[1] for r in theirs["rows"]}
        for row in ours["rows"]:
            assert by_pt.get(row[0], 0) >= row[1], (part, row[0])


# the snapshot keeps every name ----------------------------------------------------------------


def test_the_snapshot_refuses_to_drop_a_name_unless_the_major_version_rises():
    old = {"version": "1.2", "routes": {"GET /api/a": ["cases", "release"], "GET /api/b": []}}
    added = {"GET /api/a": ["cases", "release", "rows"], "GET /api/b": [], "GET /api/c": []}
    assert renewed(old, added, "1.2") == {"version": "1.2", "routes": added}
    for dropped in (
        {"GET /api/a": ["cases"], "GET /api/b": []},
        {"GET /api/a": old["routes"]["GET /api/a"]},
    ):
        with pytest.raises(SnapshotRefused, match="raise CONTRACT_VERSION's major"):
            renewed(old, dropped, "1.3")
        assert renewed(old, dropped, "2.0")["routes"] == dropped
    assert renewed(None, added, "1.0")["version"] == "1.0"
