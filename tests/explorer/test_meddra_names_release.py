"""Every rule that names MedDRA's terms, read against the MedDRA a real release holds.

The invented MedDRA carries the rules' own words, so only a real one can show that a name has
moved. Slow: reads the licensed part of the release named by OPEN_ALTIO_REAL_RELEASE (a release
folder, as for tests/faers/test_parity.py), in seconds, without writing to it. A failure names the
rule and the names; MedDRA changes twice a year, so rerun this on the release of each new version.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from open_altio.explorer.eventfacts import _not_medical, _set_aside, pregnancy_terms
from open_altio.explorer.meddra import ServedMeddra
from open_altio.faers.meddra import LABEL_GROUPS_FILE, licensed_dir, newest, read_licensed_manifest
from open_altio.faers.meddra.rulenames import GROUPS_RULE, Held, missing_names

pytestmark = pytest.mark.slow

RELEASE = os.environ.get("OPEN_ALTIO_REAL_RELEASE")


@pytest.fixture(scope="module")
def release() -> Path:
    folder = Path(RELEASE).expanduser() if RELEASE else None
    if folder is None or not (folder / "manifest.json").is_file():
        pytest.skip("set OPEN_ALTIO_REAL_RELEASE to a release folder")
    return folder


@pytest.fixture(scope="module")
def entry(release: Path) -> dict:
    versions = read_licensed_manifest(release)["meddra"]["versions"]
    chosen = newest(versions)
    if chosen is None:
        pytest.fail(f"{release} holds no MedDRA to check the rules against")
    return versions[chosen]


@pytest.fixture(scope="module")
def meddra(release: Path, entry: dict) -> ServedMeddra:
    return ServedMeddra(licensed_dir(release), entry)


@pytest.fixture(scope="module")
def groups_file(release: Path, meddra: ServedMeddra) -> dict[str, list[str]]:
    path = licensed_dir(release) / "meddra" / meddra.version / LABEL_GROUPS_FILE
    if not path.is_file():
        pytest.fail(f"this release's MedDRA {meddra.version} holds no {LABEL_GROUPS_FILE}")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def missing(meddra: ServedMeddra, groups_file: dict[str, list[str]]) -> dict:
    """What the build says of this version, from what the served version holds."""
    paths = meddra.primary_paths().values()
    held = Held(
        groups=frozenset(name.lower() for path in paths for name in path),
        hlts=frozenset(str(n).lower() for (n,) in meddra._run("SELECT hlt_name FROM meddra_hlt")),
        pts=frozenset(meddra.pt_names()),
        smqs=frozenset(q["name"].lower() for q in meddra.smqs().values()),
    )
    return missing_names(held, groups_file)


def test_rule_not_a_medical_event_names_only_what_the_version_holds(meddra):
    """The check a viewer's question runs. A person's page no longer refuses on it, so this test
    is what catches a name that moved."""
    groups, pts = _set_aside(meddra)
    assert groups, f"no list of groups for rule not-a-medical-event in MedDRA {meddra.version}"
    assert pts


def test_each_group_of_rule_not_a_medical_event_sets_aside_a_term(meddra):
    """A group held only off a primary path would pass the check and mark nothing."""
    groups, pts = _set_aside(meddra)
    assert groups
    paths = meddra.primary_paths()
    for key in ("groups", "pts"):
        names = {"groups": groups, "pts": pts}[key]
        for name in names:
            under = [pt for pt, path in paths.items() if name in {n.lower() for n in path}]
            under += [name] if key == "pts" else []
            assert under, f"no PT sits under a name of {key}"
            marks, _ = _not_medical(meddra, under, "")
            assert all(marks.values())


def test_rule_pregnancy_cases_finds_its_smq_with_terms_in_it(meddra):
    """Breakdown-lines' Pregnancy line and the event facts both read this SMQ."""
    assert pregnancy_terms(meddra)


@pytest.mark.parametrize(
    "rule",
    [
        "not-a-medical-event",
        "label-not-a-medical-event",
        "label-flags",
        "label-coding",
        GROUPS_RULE,
    ],
)
def test_the_rule_names_only_what_the_version_holds(rule, missing):
    """A name in the label rules matches nothing and refuses nothing: the build sets aside less
    with only its warning, so here it fails."""
    assert not missing.get(rule), f"Rule {rule}: {missing[rule]}"
