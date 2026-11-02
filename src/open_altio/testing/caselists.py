"""The cases a count's question lists in /api/cases, for the tests that check every count carries
the question for exactly its cases (`cases_query`).

    answers = over_http(web)                  # or any function of a query to /api/cases's answer
    listed(answers, query)                    # every case it lists, page by page, as era/key
    each_lists(answers, [(cases, query)])     # each lists exactly that many, each once; how many
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi.testclient import TestClient

Answers = Callable[[dict[str, list[str]]], dict[str, Any]]


def over_http(web: TestClient) -> Answers:
    """/api/cases's answer to a question, asked of `web`."""

    def answers(query: dict[str, list[str]]) -> dict[str, Any]:
        got = web.get(f"/api/cases?{urlencode(query, doseq=True)}")
        assert got.status_code == 200, (query, got.text[:300])
        return got.json()

    return answers


def listed(answers: Answers, query: str) -> list[str]:
    """Every case /api/cases lists for `query`, page by page, as era/key."""
    found: list[str] = []
    page = 1
    while True:
        got = answers(parse_qs(query) | {"page": [str(page)]})
        found += [f"{c['era_T']}/{c['case_key_T']}" for c in got["cases"]]
        if len(got["cases"]) < got["size"]:
            return found
        page += 1


def each_lists(answers: Answers, counts: Iterable[tuple[int, str]]) -> int:
    """Each count with its question lists exactly that many cases, each once; how many counts."""
    checked = 0
    for n, query in counts:
        found = listed(answers, query)
        assert (len(found), len(set(found))) == (n, n), query
        checked += 1
    return checked


__all__ = ["Answers", "each_lists", "listed", "over_http"]
