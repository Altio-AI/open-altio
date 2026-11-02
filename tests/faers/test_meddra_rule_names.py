"""Every rule that names MedDRA's terms, read against the version a build reads a release to
(rule meddra-version): a name it does not hold is said loudly at the build and kept in the
licensed manifest, and the build goes on.

Built on a copy of the session release with the invented MedDRA 29.1 (fakemeddra)."""

from __future__ import annotations

import pytest

from open_altio.faers.meddra import build_licensed, read_licensed_manifest
from open_altio.testing.fakelabeltables import add_label_groups
from open_altio.testing.fakemeddra import write_meddra
from open_altio.testing.rules import rules_with

OFF_LIST = "Rule not-a-medical-event names pts that MedDRA 29.1 does not hold: ['no such name']."


def test_the_invented_meddra_holds_the_names_the_explorer_reads(release_copy, tmp_path):
    entry = build_licensed(release_copy, write_meddra(tmp_path / "m", "29.1"))
    assert "not-a-medical-event" not in entry["rule_names_missing"]


def test_a_build_warns_loudly_keeps_the_names_in_the_manifest_and_finishes(
    release_copy, tmp_path, capsys
):
    source = write_meddra(tmp_path / "m", "29.1")
    with rules_with(tmp_path, {"not-a-medical-event": {"pts": ["No such name"]}}):
        entry = build_licensed(release_copy, source)
    assert entry["rule_names_missing"]["not-a-medical-event"] == {"pts": ["no such name"]}
    kept = read_licensed_manifest(release_copy)["meddra"]["versions"]["29.1"]
    assert kept["rule_names_missing"] == entry["rule_names_missing"]
    assert f"WARNING: {OFF_LIST}" in capsys.readouterr().err
    assert (release_copy / "licensed" / "meddra" / "29.1" / "meddra_mdhier.parquet").is_file()


@pytest.mark.parametrize(
    ("rule", "values", "key"),
    [
        ("label-not-a-medical-event", {"compared_pts": ["No such PT"]}, "compared_pts"),
        ("label-flags", {"same_meaning": [["Headache", "No such PT"]]}, "same_meaning"),
    ],
)
def test_a_name_any_such_rule_loses_is_named_at_the_build(
    rule, values, key, release_copy, tmp_path, capsys
):
    with rules_with(tmp_path, {rule: values}):
        entry = build_licensed(release_copy, write_meddra(tmp_path / "m", "29.1"))
    assert key in entry["rule_names_missing"][rule]
    assert f"Rule {rule} names {key}" in capsys.readouterr().err


def test_a_version_with_no_groups_list_says_so_at_the_build(release_copy, tmp_path, capsys):
    """The list is put there after a build (rule label-groups), so a first build says what to do."""
    entry = build_licensed(release_copy, write_meddra(tmp_path / "m", "29.1"))
    assert "label-groups" in entry["rule_names_missing"]
    assert "--groups" in capsys.readouterr().err


def test_a_name_the_groups_list_loses_is_named_at_the_build(release_copy, tmp_path, capsys):
    """Rebuilding a version keeps the list a person installed; a stale name is said loudly."""
    source = write_meddra(tmp_path / "m", "29.1")
    build_licensed(release_copy, source)
    held = {"event_facts_not_medical": ["No such group"], "procedure": [], "catch_all": []}
    add_label_groups(
        release_copy,
        "29.1",
        held | {"not_a_medical_event": [], "pregnancy_smq": ["No such SMQ"]},
    )
    capsys.readouterr()
    entry = build_licensed(release_copy, source, overwrite=True)
    assert entry["rule_names_missing"]["label-groups"]["event_facts_not_medical"] == [
        "no such group"
    ]
    assert entry["rule_names_missing"]["label-groups"]["pregnancy_smq"] == ["no such smq"]
    assert "no such group" in capsys.readouterr().err
