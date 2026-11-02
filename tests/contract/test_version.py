"""The written contract has one version, two whole numbers joined by a dot, and every page of
it, the CHANGELOG too, names that version, so a page and the code cannot disagree on it."""

from __future__ import annotations

import re
from pathlib import Path

from open_altio import CONTRACT_VERSION

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "docs" / "reference"
INDEX = REFERENCE / "contract.md"
VERSION = re.compile(r"\d+\.\d+")
NAMED = re.compile(r"Contract version (\d+(?:\.\d+)*)")


def pages() -> list[Path]:
    """The contract's index and every reference page it links to."""
    linked = re.findall(r"\]\(([a-z-]+\.md)[)#]", INDEX.read_text(encoding="utf-8"))
    return [INDEX, *(REFERENCE / name for name in dict.fromkeys(linked))]


def version_named(page: str) -> str | None:
    """The contract version a page names on its second line, the one after the line saying who
    the page is for; None when that line names none."""
    lines = [line for line in page.splitlines() if line.strip()][1:]  # after the title
    found = NAMED.search(lines[1]) if len(lines) > 1 else None
    return found.group(1) if found else None


def test_the_contract_version_is_two_whole_numbers_joined_by_a_dot():
    assert VERSION.fullmatch(CONTRACT_VERSION)
    for wrong in ("1", "1.0.0", "v1.0", "1.x", ""):
        assert not VERSION.fullmatch(wrong), wrong


def test_every_page_of_the_contract_names_its_version_on_its_second_line():
    named = {page.name: version_named(page.read_text(encoding="utf-8")) for page in pages()}
    assert {
        "contract.md",
        "data-dictionary.md",
        "api.md",
        "access-hook.md",
        "page-extension.md",
        "rules.md",
    } <= set(named)
    assert named == dict.fromkeys(named, CONTRACT_VERSION)


def test_a_page_naming_another_version_or_none_is_found():
    assert version_named("# A page\n\nFor anyone.\n\nContract version 0.9.\n") == "0.9"
    assert version_named("# A page\n\nFor anyone.\n\nThis page lists things.\n") is None
    assert version_named("# A page\n\nContract version 1.0, before who it is for.\n") is None


def test_the_changelog_names_the_contract_version():
    assert f"Contract version {CONTRACT_VERSION}" in (ROOT / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
