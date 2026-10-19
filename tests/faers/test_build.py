"""The one build `open-altio build`, `demo` and the explorer's rebuild share."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.faers import SourceError, build, read_manifest, release
from open_altio.testing import fakefda


def test_the_build_is_held_to_the_build_memory_rule(fake_input, tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(release, "build_release", lambda *a, **kw: seen.update(kw) or tmp_path)
    build.build_release(fake_input, tmp_path)
    memory = rulebook.value("explorer-build-memory", "memory_limit_gb")
    assert seen["memory_limit"] == f"{memory}GB"
    assert seen["threads"] == rulebook.value("explorer-build-memory", "threads")
    assert seen["overwrite"] is True


def test_exactly_the_quarters_asked_for_are_built(fake_input, tmp_path):
    built = build.build_release(fake_input, tmp_path, quarters=["2018Q1", "2026q2"])
    assert built == tmp_path / "2026Q2"
    assert read_manifest(built)["quarters"] == ["2018q1", "2026q2"]


def test_a_quarter_not_in_the_input_is_refused_by_name(fake_input, tmp_path):
    with pytest.raises(SourceError, match=r"\['2027q1'\] are not in the input"):
        build.build_release(fake_input, tmp_path, quarters=["2026q2", "2027q1"])
    assert list(tmp_path.iterdir()) == []


def test_progress_runs_through_every_step_in_order(fake_input, tmp_path):
    seen = []
    build.build_release(fake_input, tmp_path, progress=lambda *step: seen.append(step))
    total = len(fakefda.QUARTERS) + 4
    assert [done for _, done, _ in seen] == list(range(total + 1))
    assert {steps for _, _, steps in seen} == {total}
    titles = [title for title, _, _ in seen]
    assert titles[0] == "Reading FDA's files for 2012Q2"
    assert titles[-5:] == [
        "Working out the cases",
        "Writing the release",
        "Counting the statistics",
        "Building the explorer's database",
        "Release built",
    ]


def test_no_rules_file_means_altio_s_standard_rules(tmp_path):
    assert build.user_rules_beside(tmp_path) is None
