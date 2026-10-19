"""Checks that a rules folder and the code that reads it agree, for any
repository with a rules folder: each runs them from its tests/test_rules.py.

    tree = RuleTree(root=..., folder=root / "rules")
    tree.malformed(path), tree.index_problems(), tree.unknown_reads(), ...

Each check returns the problems it found, in words, so a test asserts there
are none. Rules from every folder the rulebook reads are known, so code may
read another folder's rule; only this folder's rules must list the code that
reads them.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import yaml

from open_altio import rulebook

LITERAL_OK = "# rule-literal-ok"
_CALL = re.compile(
    r"""(?:(?<![\w.])|rulebook\.)(value|rule|is_on)\(\s*["']([a-z0-9][a-z0-9-]*[A-Za-z0-9-]*)["']"""
    r"""(?:\s*,\s*["'](\w+)["'])?"""
)


@dataclass(frozen=True)
class RuleTree:
    root: Path  # the repository
    folder: Path  # its rules folder
    code: tuple[str, ...] = ("src", "scripts", "tests")  # folders whose code may read rules
    enforcing: tuple[str, ...] = ("src",)  # folders whose code enforces them
    not_enforcing: tuple[str, ...] = ()  # path prefixes that read rules without enforcing them
    loader_tests: tuple[str, ...] = ("tests/rulebook/",)  # read scratch rules, not these

    def rule_files(self) -> list[Path]:
        return sorted(p for p in self.folder.glob("*.md") if p.name != "README.md")

    def python_files(self, dirs: tuple[str, ...] | None = None) -> list[Path]:
        return sorted(
            p
            for d in (dirs or self.code)
            for p in (self.root / d).rglob("*.py")
            if ".venv" not in p.parts
        )

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def malformed(self, path: Path) -> list[str]:
        meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
        problems = [f"{path.name} lacks {key}" for key in rulebook.REQUIRED_KEYS if key not in meta]
        parsed = rulebook.parse_rule_file(path)
        if parsed.name != path.stem:
            problems.append(f"{path.name} says it is rule {parsed.name!r}")
        if not parsed.title:
            problems.append(f"{path.name} has no '# ' heading")
        return problems

    def index_problems(self) -> list[str]:
        readme = (self.folder / "README.md").read_text(encoding="utf-8")
        listed = set(re.findall(r"\]\(([^)#]+\.md)\)", readme))
        problems = [
            f"README.md lists {name}, which does not exist"
            for name in sorted(listed)
            if not (self.folder / name).is_file()
        ]
        missing = {p.name for p in self.rule_files()} - listed
        return problems + [f"missing from README.md: {name}" for name in sorted(missing)]

    def enforced_in_problems(self, path: Path) -> list[str]:
        problems = []
        for named in rulebook.parse_rule_file(path).enforced_in:
            if Path(named).is_absolute():
                problems.append(
                    f"{path.name}: enforced_in path {named} must be relative to the repository"
                )
            elif not (self.root / named).exists():
                problems.append(f"{path.name}: enforced_in names {named}, which does not exist")
        return problems

    def unread(self, path: Path) -> str | None:
        """Why an enforced rule is read by none of the files it lists, or None when one reads it."""
        parsed = rulebook.parse_rule_file(path)
        texts = [
            (self.root / p).read_text(encoding="utf-8")
            for p in parsed.enforced_in
            if (self.root / p).is_file()
        ]
        quoted = re.compile(rf"""["']{re.escape(parsed.name)}["']""")
        if any(quoted.search(t) for t in texts):
            return None
        listed = list(parsed.enforced_in)
        return f"{path.name}: none of {listed} reads rule {parsed.name!r} through rulebook"

    def _reads(self, path: Path) -> Iterator[tuple[str, str, str | None]]:
        for m in _CALL.finditer(path.read_text(encoding="utf-8")):
            yield m.group(1), m.group(2), m.group(3)

    def unknown_reads(self) -> list[str]:
        known = {r.name: r for r in rulebook.all_rules()}
        problems = []
        for path in self.python_files():
            if self._rel(path).startswith(self.loader_tests):
                continue
            for fn, name, key in self._reads(path):
                if name not in known:
                    problems.append(f"{self._rel(path)}: {fn}({name!r}) is not a rule")
                elif key is not None and fn == "value" and key not in known[name].values:
                    problems.append(
                        f"{self._rel(path)}: value({name!r}, {key!r}) is not in {name}.md"
                    )
        return problems

    def unlisted_reads(self) -> list[str]:
        mine = {
            rulebook.parse_rule_file(p).name: rulebook.parse_rule_file(p) for p in self.rule_files()
        }
        problems = set()
        for path in self.python_files(self.enforcing):
            rel = self._rel(path)
            if rel.startswith(self.not_enforcing):
                continue
            for _, name, _ in self._reads(path):
                if name in mine and rel not in mine[name].enforced_in:
                    problems.add(
                        f"{rel} reads rule {name!r} but {name}.md enforced_in does not list it"
                    )
        return sorted(problems)

    def typed_literals(self) -> list[str]:
        """Integers of 100 or more and email addresses from a rule, typed into code that reads
        that rule (names it in quotes). Code that applies or tests a rule reads its values, so a
        change to the rule reaches it; other code may write the same number for its own reasons.
        A line with a reason to hold one carries the comment `# rule-literal-ok`."""
        by_rule = {
            r.name: [(lit, _pattern(lit)) for lit in _distinctive_literals(r)]
            for r in rulebook.all_rules()
        }
        problems = []
        for path in self.python_files():
            text = path.read_text(encoding="utf-8")
            patterns = [
                p
                for name, pats in by_rule.items()
                if re.search(rf"""["']{re.escape(name)}["']""", text)
                for p in pats
            ]
            for n, line in enumerate(text.splitlines(), 1):
                if LITERAL_OK in line:
                    continue
                problems += [
                    f"{self._rel(path)}:{n}: {lit} typed in; read it with rulebook.value"
                    for lit, pat in patterns
                    if pat.search(line)
                ]
        return problems


def _pattern(lit: str) -> re.Pattern[str]:
    if lit.lstrip("-").isdigit():
        digits = r"_?".join(re.escape(d) for d in lit)
        return re.compile(rf"(?<![\w.]){digits}(?![\w])")
    return re.compile(re.escape(lit), re.IGNORECASE)


def _distinctive_literals(found_in: rulebook.Rule) -> set[str]:
    found: set[str] = set()

    def walk(v: object) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, int) and abs(v) >= 100:
            found.add(str(v))
        elif isinstance(v, str) and "@" in v:
            found.add(v)
        elif isinstance(v, list):
            for i in v:
                walk(i)
        elif isinstance(v, dict):
            for i in v.values():
                walk(i)

    walk(dict(found_in.values))
    return found
