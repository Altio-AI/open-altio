"""The statistics counted by FDA's text in a release that holds MedDRA (statistics.as_published):
written by the build, and added to a release built before the build wrote them by
`python -m open_altio.faers statistics --reactions as-published`, which takes the build's own
step. The two give the same tables, manifest entries and explorer copies, and a second run of
the command gives the same again (rules statistics-cases and meddra-terms)."""

from __future__ import annotations

import shutil

import duckdb
import pytest

from open_altio.faers import read_manifest
from open_altio.faers.__main__ import main
from open_altio.faers.explorer_db import STATISTICS_TABLES
from open_altio.faers.reader import EXPLORER_FILE, write_manifest
from open_altio.faers.statistics import AS_PUBLISHED, add_as_published

SECOND = tuple(AS_PUBLISHED.values())
COPIES = tuple(n for n, (t, _) in STATISTICS_TABLES.items() if t in SECOND)


def as_built_before(release, folder):
    """A copy of `release` as a build before the second set left it: no second set's files,
    manifest entries or explorer copies, and nothing else changed."""
    copy = folder / release.name
    shutil.copytree(release, copy)
    manifest = read_manifest(copy)
    for name in SECOND:
        (copy / manifest["tables"].pop(name)["path"]).unlink()
    del manifest["statistics"]["as_published"]
    for name in COPIES:
        del manifest["explorer"]["tables"][name]
    con = duckdb.connect(str(copy / EXPLORER_FILE))
    for name in COPIES:
        con.execute(f"DROP TABLE {name}")
    con.close()
    write_manifest(copy, manifest)
    return copy


def held(release) -> dict:
    """What the second set is in a release: its rows, its manifest entries (but how long it took
    and how many bytes the database's file holds) and its explorer copies."""
    manifest = read_manifest(release)
    entry = dict(manifest["statistics"]["as_published"])
    entry.pop("seconds")
    out = {
        "entry": entry,
        "first": {k: v for k, v in manifest["statistics"].items() if k not in ("as_published",)},
        "tables": {n: manifest["tables"][n] for n in SECOND},
        "explorer": {n: manifest["explorer"]["tables"][n] for n in COPIES},
    }
    out["first"].pop("seconds")
    con = duckdb.connect(str(release / EXPLORER_FILE), read_only=True)
    for name in SECOND:
        path = release / manifest["tables"][name]["path"]
        out[name] = con.execute(f"SELECT * FROM read_parquet('{path}') ORDER BY ALL").fetchall()
    for name in COPIES:
        out[name] = con.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall()
    con.close()
    return out


@pytest.fixture(scope="module")
def built(seizure_release) -> dict:
    return held(seizure_release)


def test_the_build_writes_both_sets(built):
    assert built["first"]["reaction_key"] == "meddra_pt"
    assert built["entry"]["reaction_key"] == "fda_text"
    assert built["statistics_as_published_T"] and built["explorer_statistics_as_published_T"]


def test_the_command_on_a_release_built_before_gives_what_the_build_gives(
    seizure_release, built, tmp_path, capsys
):
    copy = as_built_before(seizure_release, tmp_path)
    assert "as_published" not in read_manifest(copy)["statistics"]
    assert main(["statistics", "--release", str(copy), "--reactions", "as-published"]) == 0
    assert "statistics_as_published_T and statistics_strata_as_published_T written" in (
        capsys.readouterr().out
    )
    assert held(copy) == built
    # run again: the same, and nothing left beside the files it wrote
    add_as_published(copy)
    assert held(copy) == built
    assert not [p.name for p in copy.rglob("*") if ".writing" in p.name or "spill" in p.name]


def test_a_release_counted_by_fdas_text_is_left_as_it_is(release, tmp_path):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    before = (copy / "manifest.json").read_bytes()
    assert add_as_published(copy) is None
    assert (copy / "manifest.json").read_bytes() == before
