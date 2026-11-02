"""The access hook's closed lists (docs/reference/access-hook.md): the server announces only the
kinds `RECORDED` lists, each with its fields, through `Explorer.announce`; the page reports only
the kinds `REPORTED` lists; and viewing a published question announces nothing."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from open_altio.explorer import access
from open_altio.explorer.access import (
    LOCAL,
    OPTIONAL,
    RECORDED,
    REPORTED,
    ContractError,
    LocalAccess,
    Viewer,
)
from open_altio.explorer.app import create_app
from open_altio.explorer.context import explorer_of
from open_altio.testing.contract import CASE, PRODUCT

PACKAGE = Path(access.__file__).resolve().parents[1]
EXPLORER = PACKAGE / "explorer"
UI = EXPLORER / "ui"


class Recording(LocalAccess):
    """LocalAccess that keeps every event it hears."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, viewer: Viewer, kind: str, **event: Any) -> None:
        self.events.append({"kind": kind, **event})


@pytest.fixture
def heard(release) -> tuple[TestClient, list[dict[str, Any]]]:
    hook = Recording()
    return TestClient(create_app(release, access=hook)), hook.events


def calls(path: Path, attr: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
    ]


def announced() -> list[tuple[str, str, set[str]]]:
    """Every announce call in the explorer's modules: (module, kind, fields)."""
    found = []
    for path in sorted(EXPLORER.glob("*.py")):
        for call in calls(path, "announce"):
            kind = call.args[1]
            assert isinstance(kind, ast.Constant) and isinstance(kind.value, str), path.name
            fields = {k.arg for k in call.keywords if k.arg is not None}
            found.append((path.name, kind.value, fields))
    return found


def test_every_announce_names_a_listed_kind_with_its_fields():
    found = announced()
    assert found
    for module, kind, fields in found:
        assert kind in RECORDED, (module, kind)
        listed = set(RECORDED[kind])
        assert listed - set(OPTIONAL.get(kind, ())) <= fields <= listed, (module, kind)


def test_every_listed_kind_is_announced_and_every_optional_field_is_listed():
    assert {kind for _, kind, _ in announced()} == set(RECORDED)
    for kind, fields in OPTIONAL.items():
        assert set(fields) <= set(RECORDED[kind]), kind


def test_only_announce_calls_the_hooks_record():
    """No module tells the hook anything except through Explorer.announce."""
    callers = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for call in calls(path, "record"):
            target = call.func.value  # type: ignore[attr-defined]
            if (isinstance(target, ast.Attribute) and target.attr == "access") or (
                isinstance(target, ast.Name) and target.id == "access"
            ):
                callers.append(path.relative_to(PACKAGE).as_posix())
    assert callers == ["explorer/context.py"]


def test_announce_refuses_a_kind_or_field_the_list_does_not_hold(release):
    ex = explorer_of(create_app(release, access=Recording()))
    for kind, fields in (
        ("downloaded_tables", {"rows": 1}),  # a kind not listed
        ("export_started", {"rows": 1, "who": "ann"}),  # a field not listed
        ("search", {"search": "drugs", "words": "asp"}),  # a field it needs, missing
    ):
        with pytest.raises(ContractError, match=kind):
            ex.announce(LOCAL, kind, **fields)
    assert ex.access.events == []  # type: ignore[attr-defined]


def test_a_hook_hears_each_listed_kind_with_exactly_its_fields(heard):
    web, events = heard
    name = web.get("/api/products").json()["drugs"][0]["name"]
    assert web.get(f"/api/products?q={name[:3].lower()}").status_code == 200
    assert web.get("/api/exportsize?sex=F").status_code == 200
    assert web.get("/api/export?format=csv&sex=F").status_code == 200
    assert web.post("/api/sql", json={"sql": "SELECT 1"}).status_code == 200
    assert web.post("/api/sql/download", json={"sql": "SELECT 1", "format": "csv"}).status_code == (
        200
    )
    kinds = [e["kind"] for e in events]
    assert kinds == ["search", "export_started", "filtered_export", "sql", "sql"]
    for event, optional in zip(events, (set(), set(), set(), set(), {"download"}), strict=True):
        listed = set(RECORDED[event["kind"]]) - set(OPTIONAL.get(event["kind"], ()))
        assert set(event) - {"kind"} == listed | optional, event["kind"]


def test_viewing_a_published_question_announces_nothing(heard):
    web, events = heard
    for path in (
        "/api/me",
        "/api/release",
        f"/api/product?{PRODUCT}",
        f"/api/summary?{PRODUCT}",
        f"/api/timeline?{PRODUCT}",
        f"/api/cases?{PRODUCT}",
        f"/api/case/{CASE}",
        "/api/terms",
        "/api/drugs",
        "/api/statistics/about",
        "/api/downloads",
    ):
        assert web.get(path).status_code == 200, path
    assert events == []


# what the page reports ---------------------------------------------------------------------------


def page_text() -> dict[str, str]:
    return {p.relative_to(UI).as_posix(): p.read_text(encoding="utf-8") for p in UI.rglob("*.js")}


def test_the_pages_list_of_reported_kinds_is_the_servers():
    found = re.search(r"export const REPORTED = \[([^\]]*)\]", page_text()["host.js"])
    assert found, "host.js names no REPORTED list"
    assert re.findall(r"'([^']+)'", found.group(1)) == list(REPORTED)


def test_every_kind_the_page_reports_is_listed_and_every_listed_kind_is_reported():
    reported = set()
    for name, text in page_text().items():
        reported |= set(re.findall(r"\breport\('([^']+)'", text))
        if name != "host.js" and re.search(r"\bpicked\(", text):
            reported.add("pick")  # picked() reports a search's result picked
    assert reported == set(REPORTED)
