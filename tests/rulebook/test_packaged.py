"""The rules and mappings ship inside the package: a wheel built from this checkout, installed
into a fresh environment, reads its rules and builds a release with no checkout in sight."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from open_altio import rulebook

ROOT = Path(__file__).resolve().parents[2]  # the repository
INSTALLED = """
import sys
from pathlib import Path
from open_altio import rulebook
from open_altio.faers import build_release
from open_altio.testing import fakefda
assert Path(rulebook.data_root()).is_relative_to(Path(sys.prefix)), rulebook.data_root()
print(rulebook.value("sql-limits", "timeout_seconds"))
work = Path(sys.argv[1])
print(build_release(fakefda.write_input(work / "zips"), work / "releases").name)
"""


@pytest.fixture(scope="module")
def uv() -> str:
    found = shutil.which("uv") or str(Path("~/.local/bin/uv").expanduser())
    if not Path(found).exists():
        pytest.skip("no uv to build and install a wheel")
    return found


def test_the_wheel_carries_every_rule_file_and_mapping(uv, tmp_path):
    subprocess.run(
        [uv, "build", "-q", "--wheel", "--out-dir", str(tmp_path), str(ROOT)], check=True
    )
    names = set(zipfile.ZipFile(next(tmp_path.glob("*.whl"))).namelist())
    shipped = {
        f"open_altio/{p.relative_to(ROOT).as_posix()}"
        for folder in ("rules", "mappings")
        for p in (ROOT / folder).rglob("*")
        if p.is_file()
    }
    assert shipped and shipped <= names


def test_an_installed_wheel_reads_its_rules_and_builds_a_release(uv, tmp_path):
    subprocess.run(
        [uv, "build", "-q", "--wheel", "--out-dir", str(tmp_path / "dist"), str(ROOT)], check=True
    )
    env = tmp_path / "env"
    subprocess.run(
        [
            uv,
            "venv",
            "-q",
            "--python",
            f"{sys.version_info.major}.{sys.version_info.minor}",
            str(env),
        ],
        check=True,
    )
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "-q",
            "--python",
            str(python),
            str(next((tmp_path / "dist").glob("*.whl"))),
        ],
        check=True,
    )
    clean = {k: v for k, v in os.environ.items() if k not in (rulebook.ENV_VAR, "PYTHONPATH")}
    done = subprocess.run(
        [str(python), "-c", INSTALLED, str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=clean,
    )
    assert done.returncode == 0, done.stderr
    timeout, release = done.stdout.split()
    assert float(timeout) == rulebook.value("sql-limits", "timeout_seconds")
    assert (tmp_path / "releases" / release / "manifest.json").is_file()
