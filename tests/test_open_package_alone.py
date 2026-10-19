"""The open package stands alone: nothing in src/open_altio imports the hosted
service, and every module imports and the explorer runs where the service is
not installed at all."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import open_altio

PACKAGE = Path(open_altio.__file__).resolve().parent
SERVICE = "open_altio_service"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def test_no_module_imports_the_service():
    found = [
        f"{path.relative_to(PACKAGE.parent)}: imports {name}"
        for path in sorted(PACKAGE.rglob("*.py"))
        for name in _imports(path)
        if name == SERVICE or name.startswith(f"{SERVICE}.")
    ]
    assert found == []


# Runs in a fresh interpreter in which the service cannot be imported, whether it is installed
# or not.
ALONE = f"""
import importlib, importlib.abc, pathlib, pkgutil, sys

class NoService(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == {SERVICE!r} or name.startswith({SERVICE!r} + "."):
            raise ImportError("the service is not here")
        return None

sys.meta_path.insert(0, NoService())
import open_altio
assert (pathlib.Path(open_altio.__file__).parent / "py.typed").is_file()  # a host's mypy reads it
for module in pkgutil.walk_packages(open_altio.__path__, "open_altio."):
    if module.name.startswith("open_altio.testing") or module.name.endswith(".__main__"):
        continue  # test helpers, which need pytest, and the commands, which run when imported
    importlib.import_module(module.name)

from fastapi.testclient import TestClient
from open_altio.explorer.app import create_app
client = TestClient(create_app(sys.argv[1]))
assert client.get("/").text.count('<script type="module"') == 1
assert client.get("/api/me").status_code == 200
assert client.get("/api/release").json()["release"]
print("alone")
"""


def test_every_module_imports_and_the_explorer_runs_without_the_service(release):
    done = subprocess.run(
        [sys.executable, "-c", ALONE, str(release)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "alone"


@pytest.mark.slow
def test_the_open_package_installs_and_runs_in_a_fresh_environment(release, tmp_path):
    """Built and installed as a user gets it, from this checkout, into a new environment with
    no service in it. Uses uv's cache, so it needs no network once the dependencies are cached."""
    uv = shutil.which("uv") or str(Path("~/.local/bin/uv").expanduser())
    if not Path(uv).exists():
        pytest.skip("no uv")
    env = tmp_path / "env"
    subprocess.run([uv, "venv", "-q", "--python", "3.12", str(env)], check=True)
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "-q",
            "--offline",
            "--python",
            str(python),
            f"{PACKAGE.parents[1]}[dev]",
        ],
        check=True,
    )
    outside = {k: v for k, v in os.environ.items() if k != "OPEN_ALTIO_RULES_DIR"}
    done = subprocess.run(
        [str(python), "-c", ALONE, str(release)],
        capture_output=True,
        text=True,
        env=outside,
        cwd=tmp_path,
    )  # the rules and mappings the wheel carries
    assert done.returncode == 0, done.stderr
    command = env / ("Scripts/open-altio.exe" if sys.platform == "win32" else "bin/open-altio")
    tasks = subprocess.run(
        [str(command)], capture_output=True, text=True, env=outside, cwd=tmp_path
    )
    assert tasks.returncode == 0 and "open-altio demo" in tasks.stdout
    absent = subprocess.run(
        [str(python), "-c", f"import {SERVICE}"], capture_output=True, text=True
    )
    assert absent.returncode != 0 and "ModuleNotFoundError" in absent.stderr
