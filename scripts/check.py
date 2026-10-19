"""The checks every change passes before it merges.

    python scripts/check.py          # the text and code gates only (fast, no tools needed)
    python scripts/check.py --all    # plus ruff, ruff format, mypy, the docs site and the fast
                                     # suite, and the same for the service where it is present

Written in Python rather than shell so it runs the same on Windows, macOS and Linux.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "service"

# The public tree. The private service lives in service/ until it moves to its own repository.
SCANNED = ["src", "tests", "rules", "mappings", "notebooks", "docs", "scripts", ".github"]
ROOT_FILES = [
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "NOTICE",
    "CITATION.cff",
    "mkdocs.yml",
    "pyproject.toml",
    "Dockerfile",
]
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".js",
    ".css",
    ".html",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".txt",
    ".cff",
    ".ipynb",
    ".gs",
    ".sh",
    ".svg",
    ".csv",
    "",
}


@dataclass(frozen=True)
class Gate:
    name: str
    pattern: re.Pattern[str]
    why: str
    suffixes: frozenset[str] | None = None  # None means every text file


def _gate(name: str, pattern: str, why: str, suffixes: set[str] | None = None) -> Gate:
    return Gate(name, re.compile(pattern), why, frozenset(suffixes) if suffixes else None)


PEOPLE_TEXT = {".md", ".html", ".js", ".yml", ".yaml", ".cff", ".ipynb", ""}

GATES = [
    # Process history belongs in the changelog and the issue tracker, not in the code.
    _gate(
        "issue number",
        r"(?<![\w&#/'\"])#\d{1,3}\b(?![0-9a-fA-F])",
        "issue references are process history",
        TEXT_SUFFIXES - {".css", ".svg"},
    ),
    _gate("ticket", r"(?i)\btickets?\b", "process history"),
    _gate("walk", r"(?i)\bwalk \d", "internal review rounds are process history"),
    _gate("ruling", r"(?i)\brulings?\b|\bruled\b", "process history"),
    _gate("date", r"\b\d{1,2} Oct\b|\b2026-10-", "dated notes are process history"),
    # Private places and names.
    _gate("private path", r"~/Documents|/Users/", "a path on one person's machine"),
    _gate(
        "tailnet address",
        r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b",
        "a private network address",
    ),
    # Text people read.
    _gate("em dash", "—", "reads as machine-written", PEOPLE_TEXT | {".py"}),
]


def _private_gates() -> list[Gate]:
    """The names to keep out: people, private systems, an invented client and the project's
    earlier names. They are private themselves, so they live with the private service, one gate a
    line as its name, why and pattern between tabs; a checkout without the service has none."""
    words = SERVICE / "check-words.txt"
    if not words.is_file():
        return []
    lines = words.read_text(encoding="utf-8").splitlines()
    rows = [line.split("\t", 2) for line in lines if line.strip() and not line.startswith("#")]
    return [_gate(name, pattern, why) for name, why, pattern in rows]


GATES += _private_gates()

# Deliberate exceptions: (path glob, gate name, why). Keep this list short and every reason true.
ALLOWED: list[tuple[str, str, str]] = [
    ("scripts/check.py", "*", "the gates name what they look for"),
    ("CHANGELOG.md", "date", "each release is dated"),
    ("CITATION.cff", "date", "the citation format requires the release date"),
    (
        "notebooks/faers/10_label_flags.ipynb",
        "em dash",
        "an FDA label sentence, quoted as FDA wrote it",
    ),
    (
        "src/open_altio/faers/formats.py",
        "old name",
        "releases built before the rename carry the earlier format names",
    ),
]


def _allowed(rel: str, gate: str) -> bool:
    return any(Path(rel).match(glob) and name in ("*", gate) for glob, name, _ in ALLOWED)


def _files() -> Iterator[Path]:
    """Only what git tracks ships, so only that is checked."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", *ROOT_FILES, *SCANNED],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for rel in sorted(filter(None, listed.split("\0"))):
        path = ROOT / rel
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path


def text_gates() -> list[str]:
    failures = []
    for path in _files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for gate in GATES:
            if gate.suffixes is not None and path.suffix not in gate.suffixes:
                continue
            if _allowed(rel, gate.name):
                continue
            for number, line in enumerate(lines, 1):
                if gate.pattern.search(line):
                    failures.append(
                        f"{rel}:{number}: {gate.name} ({gate.why}): {line.strip()[:120]}"
                    )
    return failures


# What the package's code may not do on any platform. Windows makes links only with extra rights,
# and a file path built by joining text around a typed "/" or "\\" is wrong on one platform or
# the other: a path given to a call that takes one is built with pathlib's `/`.
LINK_CALLS = ("symlink", "symlink_to", "link", "hardlink_to")
PATH_CALLS = (
    "open",
    "Path",
    "os.path.join",
    "os.makedirs",
    "os.remove",
    "shutil.copy",
    "shutil.copytree",
    "shutil.move",
    "shutil.rmtree",
    "duckdb.connect",
)


def _typed_separator(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(v, ast.Constant) and ("/" in v.value or "\\" in v.value) for v in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return any(
            isinstance(side, ast.Constant)
            and isinstance(side.value, str)
            and ("/" in side.value or "\\" in side.value)
            for side in (node.left, node.right)
        )
    return False


def code_gates() -> list[str]:
    """The package's own code, read as Python: no links made, no file path typed with a
    separator."""
    failures = []
    for path in _files():
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix != ".py" or not rel.startswith("src/open_altio/"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if name.rsplit(".", 1)[-1] in LINK_CALLS:
                failures.append(f"{rel}:{node.lineno}: link (Windows needs extra rights): {name}")
            elif name in PATH_CALLS and any(_typed_separator(arg) for arg in node.args):
                failures.append(
                    f"{rel}:{node.lineno}: typed path separator (use pathlib's /): "
                    f"{ast.unparse(node)[:120]}"
                )
    return failures


def _run(step: list[str], cwd: Path) -> bool:
    print("$", *step, f"(in {cwd.relative_to(ROOT)})", flush=True)
    return subprocess.run([sys.executable, "-m", *step], cwd=cwd).returncode == 0


def tool_gates() -> bool:
    """Every step runs, even after one fails, so one run shows everything to fix. The service
    has its own configuration in service/pyproject.toml, as it will in its own repository."""
    with tempfile.TemporaryDirectory() as site:
        public = [
            ["ruff", "check", "--extend-exclude", "service", "."],
            ["ruff", "format", "--check", "--extend-exclude", "service", "."],
            ["mypy", "src"],
            ["mkdocs", "build", "--strict", "--quiet", "--site-dir", site],
            ["pytest", "-q"],
        ]
        service = [
            ["ruff", "check", "."],
            ["ruff", "format", "--check", "."],
            ["mypy", "src"],
            ["pytest", "-q"],
        ]
        runs = [(step, ROOT) for step in public]
        if SERVICE.is_dir():
            runs += [(step, SERVICE) for step in service]
        return all([_run(step, cwd) for step, cwd in runs])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--all", action="store_true", help="also lint, types, the docs site and the tests"
    )
    args = parser.parse_args()
    failures = text_gates()
    for failure in failures:
        print(failure)
    print(f"text gates: {len(failures)} finding(s)")
    in_code = code_gates()
    for failure in in_code:
        print(failure)
    print(f"code gates: {len(in_code)} finding(s)")
    ok = not failures and not in_code
    if args.all:
        ok = tool_gates() and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
