"""Fixtures for the pipeline's tests; the session's fake releases are in tests/conftest.py."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def release_copy(release: Path, tmp_path: Path) -> Path:
    """A copy of the session's fake release, for a test that changes it."""
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    return copy
