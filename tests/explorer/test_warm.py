"""The live release made ready before anyone asks: once warmed, Home's first products, the All
cases overview and its timeline answer from what the warm-up made, as the page asks for them."""

from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from open_altio.explorer import explore
from open_altio.explorer.access import LOCAL
from open_altio.explorer.context import explorer_of
from open_altio.explorer.warm import warm
from open_altio.rulebook import value


@pytest.fixture
def warmed(explorer_app, release):
    app = explorer_app(release)
    assert warm(explorer_of(app), [LOCAL]) is not None
    return app


def never(*args, **kwargs):
    raise AssertionError("worked out again after the warm-up")


def test_the_first_pages_answers_are_made_before_anyone_asks(warmed, monkeypatch, ask):
    client = TestClient(warmed)
    tiles = [d["name"] for d in ask(client, "/api/products")["drugs"]]
    tiles = tiles[: int(value("explorer-lists", "home_tiles"))]
    assert tiles
    monkeypatch.setattr(explore, "summary", never)
    monkeypatch.setattr(explore, "timeline", never)
    # as the page writes its questions (home.js, the overview's), the trailing & included
    for name in tiles:
        assert ask(client, f"/api/summary?product={quote(name)}")["cases"] > 0
    assert ask(client, "/api/summary?")["cases"] > 0
    assert ask(client, "/api/timeline?grain=year&")


def test_one_question_written_two_ways_is_made_once(warmed, monkeypatch, ask):
    client = TestClient(warmed)
    first = ask(client, "/api/summary?sex=F&role=PS")
    monkeypatch.setattr(explore, "summary", never)
    assert ask(client, "/api/summary?role=PS&sex=F&") == first


def test_with_no_release_live_there_is_nothing_to_warm(explorer_app):
    assert warm(explorer_of(explorer_app(None)), [LOCAL]) is None
