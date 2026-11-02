"""No MedDRA group, class or SMQ name, and no MedDRA code, in any file of the repository: they are
licensed (rule meddra-licensed-tier), and live only in the licensed part of a release.

The names are read from the licensed part of the release named by OPEN_ALTIO_REAL_RELEASE, so
nothing here holds one; without it the test skips, saying it could not check. A finding names a
file, a line, a level and the first eight hex digits of the sha256 of the lower-case name, never
the name.

Matching: a name of two or more words matches in any capitals, whole words. A one-word name is an
ordinary word ("headaches"), so it matches only with MedDRA's capitals and standing alone as a list
item or a quoted string. A code is eight digits that MedDRA holds, standing alone.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import duckdb
import pytest

from open_altio.faers.meddra import licensed_dir, newest, read_licensed_manifest

pytestmark = pytest.mark.slow

REPO = Path(__file__).parent.parent
RELEASE = os.environ.get("OPEN_ALTIO_REAL_RELEASE")
LEVELS = {"soc": "class", "hlgt": "group", "hlt": "group"}
CODES = ("soc", "hlgt", "hlt", "pt", "llt")
ANY_FILE = "*"

# Words that are the same as a name and are not MedDRA's, each with why: (file, id) -> why.
ALLOWED = {
    (ANY_FILE, "68263f94"): "a label's everyday words for a kind of reaction at the injection site",
    (ANY_FILE, "3bbc9d20"): "a label's everyday words for a kind of reaction at the infusion site",
    ("mappings/faers/atc/classes.csv", "8e82d13f"): "WHO's own class name",
    ("rules/atc-class-choice.md", "c2ed40e0"): "FDA's reported indication, in FDA's words",
    ("rules/atc-class-choice.md", "9827f1ba"): "FDA's reported indication, in FDA's words",
    ("rules/atc-class-choice.md", "255a0687"): "FDA's reported indication, in FDA's words",
    ("notebooks/faers/10_label_flags.hand_check.judged.jsonl", "870d23b4"): "a label's heading",
    ("notebooks/faers/10_label_flags.ipynb", "c0c15e51"): "a label's heading",
}
# Eight digits that are no MedDRA code here, though MedDRA holds the same number: (file, id).
NOT_CODES = {
    ("notebooks/faers/02_case_versions.ipynb", "cd2b6387"): "a case number",
    ("notebooks/faers/02_case_versions.ipynb", "4b4cd3c7"): "a case number",
    ("notebooks/faers/02_case_versions.ipynb", "2f0ad4e6"): "a case number",
    ("rules/rxnorm-ingredients.md", "d668227e"): "an RxNorm code",
    ("uv.lock", "e762a99d"): "a package's size",
    ("uv.lock", "ae44244e"): "a package's size",
    ("uv.lock", "5ef3ea41"): "a package's size",
}


def short(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:8]


@pytest.fixture(scope="module")
def licensed() -> tuple[dict[str, tuple[str, str]], set[str]]:
    """Each name in lower case -> (its level, as MedDRA writes it), and every code."""
    folder = Path(RELEASE).expanduser() if RELEASE else None
    if folder is None or not (folder / "manifest.json").is_file():
        pytest.skip("could not check: set OPEN_ALTIO_REAL_RELEASE to a release holding MedDRA")
    manifest = read_licensed_manifest(folder)
    if not manifest:
        pytest.skip("could not check: this release holds no MedDRA")
    versions = manifest["meddra"]["versions"]
    tables = licensed_dir(folder) / "meddra" / str(newest(versions))
    names: dict[str, tuple[str, str]] = {}
    codes: set[str] = set()
    for level in CODES:
        path = (tables / f"meddra_{level}.parquet").as_posix()
        rows = duckdb.execute(f"SELECT {level}_code, {level}_name FROM read_parquet(?)", [path])
        for code, name in rows.fetchall():
            codes.add(code)
            if level in LEVELS:
                names.setdefault(name.lower(), (LEVELS[level], name))
    path = (tables / "meddra_smq_list.parquet").as_posix()
    for code, name in duckdb.execute(
        "SELECT smq_code, smq_name FROM read_parquet(?)", [path]
    ).fetchall():
        codes.add(code)
        names.setdefault(name.lower(), ("smq", name))
    return names, codes


def findings(names: dict[str, tuple[str, str]], codes: set[str]) -> tuple[list[str], set[tuple]]:
    """Each finding not allowed, and the allowances used."""
    long = [n for n in names if " " in n]
    one = {names[n][1] for n in names if " " not in n}
    many = re.compile(
        r"(?<![\w-])("
        + "|".join(map(re.escape, sorted(long, key=len, reverse=True)))
        + r")(?![\w-])",
        re.IGNORECASE,
    )
    alone = re.compile(r"""(?:^\s*-\s+|["'])([A-Z][a-z]+)(?:\s*$|["'])""")
    code = re.compile(r"(?<![\d.\-_a-zA-Z])(1\d{7})(?![\d.\-_a-zA-Z])")
    listed = subprocess.run(
        ["git", "ls-files"], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout.split("\n")
    found: list[str] = []
    used: set[tuple] = set()

    def judge(path: str, number: int, kind: str, key: str, allowed: dict) -> None:
        for place in ((path, key), (ANY_FILE, key)):
            if place in allowed:
                used.add(place)
                return
        found.append(f"{path}:{number} {kind} {key}")

    for path in filter(None, listed):
        try:
            text = (REPO / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.split("\n"), 1):
            for m in many.finditer(line):
                judge(
                    path, number, names[m.group(1).lower()][0], short(m.group(1).lower()), ALLOWED
                )
            for m in alone.finditer(line):
                if m.group(1) in one:
                    level = names[m.group(1).lower()][0]
                    judge(path, number, level, short(m.group(1).lower()), ALLOWED)
            for m in code.finditer(line):
                if m.group(1) in codes:
                    judge(path, number, "code", short(m.group(1)), NOT_CODES)
    return found, used


def test_no_file_holds_a_meddra_group_class_or_smq_name_or_code(licensed):
    found, used = findings(*licensed)
    assert not found, f"{len(found)} MedDRA names or codes in the repository:\n" + "\n".join(found)
    stale = (set(ALLOWED) | set(NOT_CODES)) - used
    assert not stale, f"allowed but no longer found, so take them out: {sorted(stale)}"
