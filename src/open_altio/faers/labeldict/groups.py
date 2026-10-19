"""The licensed file of MedDRA groups the label rules read (rule label-groups): which groups hold
terms that are not medical events, which body-system class holds procedures, and which groups
are catch-alls that never make a pair related. A person supplies it from their own MedDRA files;
it is never in the repository. The labels step checks it against the release's MedDRA version
and writes it beside that version's tables.

    from open_altio.faers.labeldict.groups import install_groups
    install_groups("releases/2026Q2", "~/meddra/label_groups.json")
"""

from __future__ import annotations

import json
from pathlib import Path

from open_altio import rulebook

from ..meddra import LABEL_GROUPS_FILE, MEDDRA_DIR, licensed_dir
from .release_io import LabelRefused, held_version, licensed, rows

RULE = "label-groups"


def group_keys() -> dict[str, bool]:
    """The file's keys, as the rules that read them name them, and whether each may name high
    level terms only."""
    return {
        rulebook.value("label-not-a-medical-event", "groups_key"): False,
        rulebook.value("label-procedure", "groups_key"): False,
        rulebook.value("label-flags", "catch_all_key"): rulebook.value(RULE, "catch_all_hlt_only"),
    }


def _levels(release_dir: Path, entry: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Every group name and code of the version, lower case, to its name as MedDRA writes it:
    at every level, and of the high level terms alone."""
    paths = rows(
        "SELECT DISTINCT soc_code, soc_name, hlgt_code, hlgt_name, hlt_code, hlt_name FROM "
        f"{licensed(release_dir, entry, 'meddra_mdhier')}"
    )
    every: dict[str, str] = {}
    hlt: dict[str, str] = {}
    for soc_code, soc, hlgt_code, hlgt, hlt_code, hlt_name in paths:
        for code, name in ((soc_code, soc), (hlgt_code, hlgt), (hlt_code, hlt_name)):
            every[code] = every[name.lower()] = name
        hlt[hlt_code] = hlt[hlt_name.lower()] = hlt_name
    return every, hlt


def install_groups(release_dir: str | Path, path: str | Path) -> dict:
    """Check the groups file at `path` against the release's MedDRA version and write it, each
    group as MedDRA names it, into the version's licensed folder. Raises LabelRefused, saying
    why, when the file is not a mapping of exactly the rules' keys to lists of group names or
    codes, or names a group the version does not hold."""
    release_dir = Path(release_dir).expanduser()
    path = Path(path).expanduser()
    _, version, entry = held_version(release_dir)
    try:
        given = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LabelRefused(f"{path}: not a readable JSON file ({exc})") from exc
    keys = group_keys()
    if not isinstance(given, dict) or set(given) != set(keys):
        found = sorted(given) if isinstance(given, dict) else type(given).__name__
        raise LabelRefused(f"{path}: needs exactly the keys {sorted(keys)}, not {found}")
    every, hlts = _levels(release_dir, entry)
    out: dict[str, list[str]] = {}
    for key, hlt_only in keys.items():
        names = given[key]
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise LabelRefused(f"{path}: {key} must be a list of group names or codes")
        known = hlts if hlt_only else every
        missing = [n for n in names if n.strip().lower() not in known]
        if missing:
            where = "high level terms" if hlt_only else "groups"
            raise LabelRefused(
                f"{path}: {key} names {len(missing)} {where} MedDRA {version} does not hold,"
                f" such as {missing[:3]}"
            )
        out[key] = sorted({known[n.strip().lower()] for n in names})
    target = licensed_dir(release_dir) / MEDDRA_DIR / version / LABEL_GROUPS_FILE
    target.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return {"version": version, "groups": {k: len(v) for k, v in out.items()}}


__all__ = ["RULE", "group_keys", "install_groups"]
