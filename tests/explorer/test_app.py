"""The explorer as one web app: the headers every answer carries, what it says while no
release is live, and a release built with someone's own rules read under them."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from open_altio.explorer.app import HEADERS
from open_altio.faers.build import build_release
from open_altio.rulebook import UserRules, value


def test_every_answer_is_never_framed_and_leaks_no_address(client):
    for path in ("/", "/ui/app.js", "/api/me", "/api/summary", "/api/no-such-thing", "/nothing"):
        got = client.get(path, follow_redirects=False)
        for name, header in HEADERS.items():
            assert got.headers[name] == header, (path, name)
    assert HEADERS == {"X-Frame-Options": "DENY", "Referrer-Policy": "same-origin"}


def test_with_no_release_live_the_page_loads_and_the_data_says_so(explorer_app, tmp_path):
    for folder in (None, tmp_path):  # no folder named, and a folder that holds no release
        web = TestClient(explorer_app(folder))
        assert web.get("/").status_code == 200
        for path in ("/api/release", "/api/summary", "/api/schema", "/api/downloads"):
            got = web.get(path)
            assert (got.status_code, got.json()) == (503, {"problem": "No release is live yet."}), (
                path
            )
        assert web.post("/api/sql", json={"sql": "SELECT 1"}).status_code == 503


@pytest.fixture(scope="module")
def duplicates_in(fake_input, tmp_path_factory):
    """A release built to show probable duplicates when a page opens, unlike Altio's standard."""
    chosen = UserRules(values={"dedup-default": {"explorer_default": "all"}})
    return build_release(fake_input, tmp_path_factory.mktemp("mine"), user_rules=chosen)


def test_a_release_is_read_under_the_rules_it_was_built_with(explorer_app, duplicates_in, client):
    """Whether probable duplicates show when a page opens is one of a person's values; their
    release opens with it, and the release built with Altio's standard keeps Altio's, in the same
    process."""
    standard = value("dedup-default", "explorer_default")
    assert standard == "kept_only"
    mine = TestClient(explorer_app(duplicates_in))
    assert mine.get("/api/release").json()["dedup"] == "all"
    opened = mine.get("/api/summary").json()
    assert opened["kept_only"] is False
    assert opened["cases"] == mine.get("/api/release").json()["all_cases"]
    assert mine.get("/api/summary?dedup=kept_only").json()["kept_only"] is True
    assert client.get("/api/release").json()["dedup"] == standard
    assert client.get("/api/summary").json()["kept_only"] is True
    assert value("dedup-default", "explorer_default") == standard  # nothing outlives the request
