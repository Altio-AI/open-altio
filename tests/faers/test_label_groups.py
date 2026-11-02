"""The groups file a person makes from their own MedDRA release (rule label-groups): checked
against the release's MedDRA version, written beside its tables, refused when it is wrong.

Built on a copy of the session release with the invented MedDRA 29.1 (fakemeddra)."""

from __future__ import annotations

import json
import shutil

import pytest

from open_altio import rulebook
from open_altio.faers.__main__ import main
from open_altio.faers.labeldict import LabelRefused
from open_altio.faers.labeldict.groups import file_keys, install_groups
from open_altio.testing import fakemeddra
from open_altio.testing.fakelabeltables import add_labels
from open_altio.testing.fakemeddra import PREGNANCY_SMQ

SOC = fakemeddra.SOCS["91000002"][0]
HLT_CODE, HLT = "93000006", fakemeddra.HLTS["93000006"][0]


@pytest.fixture
def release(licensed_release, tmp_path):
    copy = tmp_path / licensed_release.name
    shutil.copytree(licensed_release, copy)
    return add_labels(copy)


def groups_file(tmp_path, **given):
    data = {k: [] for k in file_keys()} | given
    path = tmp_path / "groups.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def installed(release):
    return json.loads((release / "licensed" / "meddra" / "29.1" / "label_groups.json").read_text())


def test_a_good_file_is_written_beside_the_version_with_each_group_as_meddra_names_it(
    release, tmp_path
):
    procedure, catch_all = rulebook.value("label-procedure", "groups_key"), "catch_all"
    path = groups_file(tmp_path, **{procedure: [SOC.upper()], catch_all: [HLT_CODE]})
    done = install_groups(release, path)
    assert done["version"] == "29.1"
    assert installed(release)[procedure] == [SOC]
    assert installed(release)[catch_all] == [HLT]  # a code becomes its name
    assert rulebook.value("label-groups", "catch_all_hlt_only") is True


def test_the_pregnancy_smq_is_checked_against_the_versions_smqs(release, tmp_path):
    path = groups_file(tmp_path, pregnancy_smq=[PREGNANCY_SMQ.upper()])
    install_groups(release, path)
    assert installed(release)["pregnancy_smq"] == [PREGNANCY_SMQ]
    with pytest.raises(LabelRefused, match="SMQs"):
        install_groups(release, groups_file(tmp_path, pregnancy_smq=["No such SMQ"]))


def test_a_file_with_other_keys_or_values_is_refused(release, tmp_path):
    path = tmp_path / "groups.json"
    path.write_text(json.dumps({"procedure": []}), encoding="utf-8")
    with pytest.raises(LabelRefused, match="needs exactly the keys"):
        install_groups(release, path)
    with pytest.raises(LabelRefused, match="must be a list"):
        install_groups(release, groups_file(tmp_path, catch_all="not a list"))
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(LabelRefused, match="not a readable JSON file"):
        install_groups(release, path)


def test_a_group_the_version_does_not_hold_is_refused(release, tmp_path):
    procedure = rulebook.value("label-procedure", "groups_key")
    with pytest.raises(LabelRefused, match="does not hold"):
        install_groups(release, groups_file(tmp_path, **{procedure: ["Invented nonsense"]}))
    # catch-alls are high level terms: a body-system class is refused there
    with pytest.raises(LabelRefused, match="high level terms"):
        install_groups(release, groups_file(tmp_path, catch_all=[SOC]))
    assert not (release / "licensed" / "meddra" / "29.1" / "label_groups.json").exists()


def test_the_command_takes_the_file_and_runs_the_step_from_it(release, tmp_path, capsys):
    path = groups_file(tmp_path, catch_all=[HLT])
    assert main(["labels", "--release", str(release), "--groups", str(path)]) == 0
    done = json.loads(capsys.readouterr().out)
    assert done["groups"]["groups"]["catch_all"] == 1 and done["coded"]["version"] == "29.1"
    bad = groups_file(tmp_path, catch_all=["Invented nonsense"])
    assert main(["labels", "--release", str(release), "--groups", str(bad)]) == 2


def test_groups_only_installs_the_file_and_stops_before_the_labels(release, tmp_path, capsys):
    """A list added to a release already flagged needs no labels coded again."""
    path = groups_file(tmp_path, procedure=[SOC])
    flags = release / "parquet" / "label_flags_T.parquet"
    assert not flags.exists()
    code = main(["labels", "--release", str(release), "--groups", str(path), "--groups-only"])
    assert code == 0
    assert installed(release)["procedure"] == [SOC]
    assert not flags.exists()
    assert main(["labels", "--release", str(release), "--groups-only"]) == 2
