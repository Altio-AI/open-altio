"""The methods-page document of each fake release, read the way the page reads it: through the
release folder and its manifest."""

from __future__ import annotations

import json

import pytest


@pytest.fixture(scope="session")
def methods(rel) -> dict:
    return json.loads((rel.path / rel.manifest["methods"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def dup_methods(dup_rel) -> dict:
    return json.loads((dup_rel.path / dup_rel.manifest["methods"]).read_text(encoding="utf-8"))
