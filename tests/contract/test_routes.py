"""Server routes (docs/reference/contract.md, Server routes): `host(host_app, explorer_app)` puts a
host's own routes first and the explorer behind them, and refuses a host route at any path the
explorer answers (`RESERVED`), naming it."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from open_altio.explorer import pages
from open_altio.explorer.access import ContractError
from open_altio.explorer.app import HEADERS, RESERVED, create_app, host


def host_app(*paths: str) -> FastAPI:
    """A host's app with one route at each path, each answering which route it is."""
    app = FastAPI()
    for path in paths:
        app.add_api_route(path, lambda path=path: {"host": path}, methods=["GET"])
    return app


@pytest.fixture
def explorer(release) -> FastAPI:
    return create_app(release)


def test_a_hosts_routes_answer_first_and_the_explorer_answers_the_rest(explorer):
    web = TestClient(host(host_app("/thing", "/api/acme/things"), explorer))
    assert web.get("/thing").json() == {"host": "/thing"}
    assert web.get("/api/acme/things").json() == {"host": "/api/acme/things"}
    assert web.get("/api/release").json()["counted_on"]["source"] == "faers"
    assert web.get("/").status_code == 200 and '"/ui/app.js"' in web.get("/").text
    # an address no one answers still goes home, as the explorer alone sends it
    gone = web.get("/no-such-page", follow_redirects=False)
    assert (gone.status_code, gone.headers["location"]) == (302, "/")


def test_every_answer_the_hosts_too_carries_the_explorers_headers(explorer):
    web = TestClient(host(host_app("/thing"), explorer))
    for path in ("/thing", "/api/release"):
        answer = web.get(path)
        assert {name: answer.headers[name] for name in HEADERS} == HEADERS, path


def test_a_hosts_own_address_serves_the_page_through_pages_index(explorer):
    app = FastAPI()
    app.add_api_route("/acme-admin", pages.index, methods=["GET"])
    web = TestClient(host(app, explorer))
    assert '"/ui/app.js"' in web.get("/acme-admin").text


@pytest.mark.parametrize(
    "path",
    [
        "/api/cases",  # one of the explorer's questions
        "/api/acme",  # the explorer's /api, not under a prefix of the host's own
        "/api/{anything}/x",  # a prefix that is a path parameter takes every one
        "/api/rules/thing",  # under one of the explorer's own /api parts
        "/",  # Home: a host draws its own there with host.routes on the page
        "/{rest:path}",  # a route that takes every path
        "/product/{name}",
        "/all/overview",  # one the explorer answers through /all/{tab}
        *(entry for entry in RESERVED if entry != "/"),
        *(f"{entry}/more" for entry in RESERVED if entry not in ("/", "/api")),
    ],
)
def test_a_host_route_at_a_path_the_explorer_answers_is_refused_naming_it(explorer, path):
    with pytest.raises(ContractError, match=path.replace("{", r"\{").replace("}", r"\}")):
        host(host_app("/thing", path), explorer)


def test_a_router_a_host_includes_is_read_route_by_route(explorer):
    """FastAPI keeps an included router's routes behind one route: each is still checked."""
    mine = APIRouter(prefix="/api/acme")
    mine.add_api_route("/things", lambda: {"host": "things"}, methods=["GET"])
    app = FastAPI()
    app.include_router(mine)
    assert TestClient(host(app, explorer)).get("/api/acme/things").json() == {"host": "things"}
    theirs = APIRouter(prefix="/api")
    theirs.add_api_route("/cases", lambda: {}, methods=["GET"])
    taken = FastAPI()
    taken.include_router(theirs)
    with pytest.raises(ContractError, match="/api/cases"):
        host(taken, explorer)


def test_reserved_lists_the_explorers_paths():
    assert RESERVED == (
        "/",
        "/api",
        "/ui",
        "/all",
        "/product",
        "/release",
        "/sql",
        "/downloads",
        "/methods",
        "/rules",
    )


def test_a_path_that_only_starts_like_a_reserved_one_is_the_hosts(explorer):
    web = TestClient(host(host_app("/released-notes", "/allowed"), explorer))
    assert web.get("/released-notes").json() == {"host": "/released-notes"}
    assert web.get("/allowed").json() == {"host": "/allowed"}
