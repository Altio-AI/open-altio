"""Windows, simulated on macOS and Linux: every module imports without the Unix-only modules.
That nothing makes a link and no file path is typed with a separator is a code gate in
scripts/check.py."""

from __future__ import annotations

import subprocess
import sys

UNIX_ONLY = ("resource", "fcntl", "pwd", "grp", "termios")

# Runs in a fresh interpreter in which the Unix-only modules cannot be imported, as on Windows.
WITHOUT_UNIX = f"""
import importlib, importlib.abc, pkgutil, sys

for name in {UNIX_ONLY!r}:
    sys.modules.pop(name, None)

class WindowsHasNone(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {UNIX_ONLY!r}:
            raise ImportError(f"No module named {{name!r}} on Windows")
        return None

sys.meta_path.insert(0, WindowsHasNone())
import open_altio
for module in pkgutil.walk_packages(open_altio.__path__, "open_altio."):
    if module.name.startswith("open_altio.testing") or module.name.endswith(".__main__"):
        continue  # test helpers, which need pytest, and the commands, which run when imported
    importlib.import_module(module.name)
print("imported")
"""


def test_every_module_imports_without_the_unix_only_modules():
    done = subprocess.run([sys.executable, "-c", WITHOUT_UNIX], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "imported"
