"""The explorer ships Inter (NOTICE), so a machine without it measures words the same: each face is
served from the package with its licence beside it, and the page draws in it."""

from __future__ import annotations

from pathlib import Path

import pytest

import open_altio.explorer

UI = Path(open_altio.explorer.__file__).parent / "ui"
FACES = (
    "inter-latin-wght-normal.woff2",
    "inter-latin-ext-wght-normal.woff2",
    "inter-latin-wght-italic.woff2",
)


def test_each_face_ships_with_its_licence_and_a_notice():
    assert all((UI / "fonts" / face).stat().st_size > 1000 for face in FACES)
    licence = (UI / "fonts" / "LICENSE-Inter.txt").read_text()
    assert "SIL OPEN FONT LICENSE" in licence and "The Inter Project Authors" in licence
    theme = (UI / "css" / "theme.css").read_text()
    assert all(f"/ui/fonts/{face}" in theme for face in FACES)


@pytest.mark.parametrize("face", FACES)
def test_the_page_is_served_each_face_and_draws_in_inter(opened, face):
    page = opened("/")
    got = page.evaluate(
        """async (face) => {
      const r = await fetch(`/ui/fonts/${face}`);
      await document.fonts.load('400 13px Inter');
      const loaded = [...document.fonts].filter((f) => f.family.replaceAll('"', '') === 'Inter'
        && f.status === 'loaded');
      return { status: r.status, type: r.headers.get('content-type'), loaded: loaded.length }; }""",
        face,
    )
    assert got["status"] == 200 and got["type"] == "font/woff2", got
    assert got["loaded"] >= 1, got
