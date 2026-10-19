"""The licensed MedDRA part of a release.

The licensed part is built from a tiny invented MedDRA set
(open_altio.testing.fakemeddra) into a copy of the session release, and read
back only through its files. The public part (parquet/, manifest.json,
explorer.duckdb) must hold no MedDRA hierarchy, codes or SMQs.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers import ReleaseError, build_release
from open_altio.faers.__main__ import main
from open_altio.faers.meddra import (
    DERIVED_TABLES,
    LICENSED_TABLES,
    MeddraRefused,
    add_held,
    build_licensed,
    check_ascii,
    newest,
    newest_held,
    release_date,
)
from open_altio.testing.fakemeddra import write_meddra

# Words that name MedDRA's hierarchy or SMQs; none may appear as a public table or column.
LICENSED_WORDS = ("meddra", "soc", "hlgt", "hlt", "llt", "smq", "pt_code", "pt_current")


def _licensed_manifest(folder):
    return json.loads((folder / "licensed" / "manifest.json").read_text())


def _parquet(folder, entry):
    return duckdb.sql(f"SELECT * FROM read_parquet('{folder / 'licensed' / entry['path']}')")


# the calendar (rule meddra-version) ------------------------------------------------


def test_release_dates_follow_medDRAs_numbering():
    first, second = rulebook.value("meddra-version", "release_dates")
    assert release_date("29.0").isoformat()[5:] == first
    assert release_date("29.1").isoformat()[5:] == second
    assert release_date("29.1").year == 2026
    with pytest.raises(MeddraRefused):
        release_date("twenty")


def test_the_newest_version_goes_by_medDRAs_numbers():
    assert newest(["29.0", "28.1", "29.1", "9.1"]) == "29.1"
    assert newest(["29.0", "28.1"]) == "29.0"
    assert newest([]) is None


# the licensed part -----------------------------------------------------------------


def test_licensed_part_has_its_own_manifest_with_its_one_version(licensed_release):
    m = _licensed_manifest(licensed_release)
    assert m["release"] == json.loads((licensed_release / "manifest.json").read_text())["release"]
    versions = m["meddra"]["versions"]
    assert list(versions) == ["29.1"]
    v = versions["29.1"]
    assert v["language"] == rulebook.value("meddra-version", "language")
    assert v["released"] == "2026-09-01" and "switch_on" not in v
    assert set(v["tables"]) == set(LICENSED_TABLES)
    for name in LICENSED_TABLES:
        entry = v["tables"][name]
        assert entry["path"].startswith("meddra/29.1/")
        assert (licensed_release / "licensed" / entry["path"]).is_file()
        assert _parquet(licensed_release, entry).fetchall() is not None


def test_meddra_values_are_kept_as_the_files_hold_them(licensed_release):
    v = _licensed_manifest(licensed_release)["meddra"]["versions"]["29.1"]
    rows = dict(
        _parquet(licensed_release, v["tables"]["meddra_llt"])
        .select("llt_name, llt_currency")
        .fetchall()
    )
    assert rows["Sickness"] == "N" and rows["Head pain"] == "Y"


def test_every_derived_licensed_column_ends_in_T(licensed_release):
    suffix = rulebook.value("transformed-suffix-T", "derived_suffix")
    v = _licensed_manifest(licensed_release)["meddra"]["versions"]["29.1"]
    for name in DERIVED_TABLES:
        cols = _parquet(licensed_release, v["tables"][name]).columns
        assert all(c.endswith(suffix) for c in cols), (name, cols)


# the public part holds none of it ------------------------------------------------------


def _public_problems(release):
    """Every public table, column, file or explorer column that names MedDRA's hierarchy."""
    manifest = json.loads((release / "manifest.json").read_text())
    text = json.dumps(manifest).lower()
    assert "licensed" not in text
    problems = []
    for table, entry in manifest["tables"].items():
        assert entry["path"].startswith("parquet/")
        cols = duckdb.sql(
            f"SELECT * FROM read_parquet('{release / entry['path']}') LIMIT 0"
        ).columns
        for name in [table] + list(cols):
            if any(w in name.lower() for w in LICENSED_WORDS):
                problems.append(f"{table}.{name}")
    for path in (release / "parquet").iterdir():
        if any(w in path.name.lower() for w in LICENSED_WORDS):
            problems.append(str(path))
    con = duckdb.connect(str(release / "explorer.duckdb"), read_only=True)
    for table, column in con.execute(
        "SELECT table_name, column_name FROM duckdb_columns()"
    ).fetchall():
        if any(w in f"{table}.{column}".lower() for w in LICENSED_WORDS):
            problems.append(f"explorer {table}.{column}")
    con.close()
    return problems


def test_public_part_has_no_meddra_hierarchy_tables_or_columns(licensed_release):
    assert _public_problems(licensed_release) == []


def test_a_release_built_with_meddra_has_its_licensed_part_and_a_clean_public_part(
    licensed_release,
):
    built = licensed_release  # built with the MedDRA folder given to the build
    versions = _licensed_manifest(built)["meddra"]["versions"]
    assert list(versions) == ["29.1"] and set(versions["29.1"]["tables"]) == set(LICENSED_TABLES)
    assert _public_problems(built) == []
    # the methods page counts with MedDRA but names no code, lower level term or former name
    methods = (built / "methods.json").read_text()
    for word in ("9400000", "9500000", "Head pain", "Sickness", "Lactic acidosis"):
        assert word not in methods, word


def test_a_release_build_refuses_a_meddra_file_older_than_the_data(fake_input, tmp_path):
    with pytest.raises(ReleaseError, match="older than this release's data"):
        build_release(fake_input, tmp_path / "out", meddra_dir=write_meddra(tmp_path / "m", "28.1"))
    assert not list((tmp_path / "out").iterdir())


def test_the_shared_release_never_gets_a_licensed_part(release, licensed_release):
    assert not (release / "licensed").exists()


# refusals ----------------------------------------------------------------------------


def test_refuses_a_version_already_held_unless_overwriting(release_copy, tmp_path):
    source = write_meddra(tmp_path / "m", "29.1")
    build_licensed(release_copy, source)
    with pytest.raises(MeddraRefused, match="already"):
        build_licensed(release_copy, source)
    build_licensed(release_copy, source, overwrite=True)


def test_refuses_a_release_not_in_english(release_copy, tmp_path):
    with pytest.raises(MeddraRefused, match="serves"):
        build_licensed(release_copy, write_meddra(tmp_path / "m", "29.1", language="French"))
    assert not (release_copy / "licensed" / "meddra" / "29.1").exists()


def test_refuses_a_folder_missing_a_file(release_copy, tmp_path):
    source = write_meddra(tmp_path / "m", "29.1")
    (source / "MedAscii" / "smq_content.asc").unlink()
    with pytest.raises(MeddraRefused, match="smq_content.asc"):
        build_licensed(release_copy, source)


def test_command_line_builds_and_refuses(release_copy, tmp_path, capsys):
    source = write_meddra(tmp_path / "m", "29.1")
    assert main(["meddra", "--release", str(release_copy), "--meddra", str(source)]) == 0
    assert "29.1" in capsys.readouterr().out
    assert main(["meddra", "--release", str(release_copy), "--meddra", str(source)]) == 2
    assert "refused" in capsys.readouterr().err
    assert (
        main(
            [
                "meddra",
                "--release",
                str(release_copy),
                "--meddra",
                str(source),
                "--overwrite",
                "--released",
                "2026-09-15",
            ]
        )
        == 0
    )
    assert (
        _licensed_manifest(release_copy)["meddra"]["versions"]["29.1"]["released"] == "2026-09-15"
    )


# the versions a host holds: added by every release build it makes


def _held(tmp_path, *versions):
    """A held folder as the upload in Settings leaves it: <version>/MedAscii/ for each."""
    root = tmp_path / "held"
    for version in versions:
        write_meddra(root / version, version)
    (root / ".29.2.1234.unpacking").mkdir()  # an upload in progress is not held
    return root


def test_check_ascii_reads_the_version_and_names_a_missing_or_broken_file(tmp_path):
    source = write_meddra(tmp_path / "m", "29.1")
    assert check_ascii(source) == ("29.1", "English")
    (source / "MedAscii" / "hlt_pt.asc").write_text("93000001$\n", encoding="latin-1")
    with pytest.raises(MeddraRefused, match="hlt_pt.asc line 1"):
        check_ascii(source)
    (source / "MedAscii" / "hlt_pt.asc").unlink()
    with pytest.raises(MeddraRefused, match="hlt_pt.asc"):
        check_ascii(source)


def test_another_version_replaces_the_one_a_release_held(release_copy, tmp_path):
    build_licensed(release_copy, write_meddra(tmp_path / "29.0", "29.0"))
    build_licensed(release_copy, write_meddra(tmp_path / "29.1", "29.1"))
    assert list(_licensed_manifest(release_copy)["meddra"]["versions"]) == ["29.1"]
    assert sorted(p.name for p in (release_copy / "licensed" / "meddra").iterdir()) == ["29.1"]


def test_a_host_builds_a_release_with_the_newest_version_it_holds(tmp_path):
    held = _held(tmp_path, "28.1", "29.0", "29.1")
    assert newest_held(held) == held / "29.1"  # given to build_release as meddra_dir


def test_a_built_release_is_read_to_the_newest_held_version_once(release_copy, tmp_path):
    held = _held(tmp_path, "28.1", "29.0", "29.1")
    assert add_held(release_copy, held) == ["29.1"]  # never 28.1 or 29.0 beside it
    assert list(_licensed_manifest(release_copy)["meddra"]["versions"]) == ["29.1"]
    assert add_held(release_copy, held) == []  # already there, from the same files
    (held / "29.1" / "MedAscii" / "readme.asc").write_text("not read", encoding="latin-1")
    assert add_held(release_copy, held) == []  # a file the tier does not read changes nothing
    write_meddra(held / "29.1", "29.1", language="English")
    with (held / "29.1" / "MedAscii" / "smq_list.asc").open("a", encoding="latin-1") as fh:
        fh.write("96000009$Invented later SMQ$1$Invented.$$$29.1$A$N$\n")
    assert add_held(release_copy, held) == ["29.1"]  # re-issued by MSSO: built again


def test_nothing_held_adds_nothing(release_copy, tmp_path):
    assert newest_held(tmp_path / "no-such-folder") is None
    assert add_held(release_copy, tmp_path / "no-such-folder") == []
    assert not (release_copy / "licensed").exists()


def test_command_line_reads_a_release_to_the_newest_held_version(release_copy, tmp_path, capsys):
    held = _held(tmp_path, "29.0", "29.1")
    assert main(["meddra", "--release", str(release_copy), "--held", str(held)]) == 0
    assert "MedDRA 29.1 read in" in capsys.readouterr().out
    assert main(["meddra", "--release", str(release_copy), "--held", str(held)]) == 0
    assert "already has the newest held MedDRA version" in capsys.readouterr().out
