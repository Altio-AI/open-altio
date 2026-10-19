"""Run code under a copy of the rules folders with some values changed.

    with rules_with(tmp_path, {"sql-limits": {"timeout_seconds": 1}}):
        ...   # rulebook.value("sql-limits", "timeout_seconds") is 1 here

The copy keeps every other value as the real rules folders have it, so tests
still read the real limits; only the named values differ. Every folder the
rulebook reads is copied, rules/ and any a package added, so a rule changes
wherever it lives.
"""

from __future__ import annotations

import contextlib
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml

from open_altio import rulebook


@contextlib.contextmanager
def rules_with(scratch: Path, changes: Mapping[str, Mapping[str, Any]]) -> Iterator[list[Path]]:
    root = Path(scratch) / "rules-override"
    if root.exists():
        shutil.rmtree(root)
    copies = []
    for i, folder in enumerate(rulebook.rules_dirs()):
        copy = root / f"{i}-{folder.name}"
        shutil.copytree(folder, copy)
        copies.append(copy)
    for name, values in changes.items():
        path = next(c / f"{name}.md" for c in copies if (c / f"{name}.md").is_file())
        text = path.read_text(encoding="utf-8")
        _, front, body = text.split("---", 2)
        meta = yaml.safe_load(front)
        meta["values"].update(values)
        path.write_text(f"---\n{yaml.safe_dump(meta, sort_keys=False)}---{body}", encoding="utf-8")
    with rulebook.use_rules_dirs(copies):
        yield copies
