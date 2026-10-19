"""Read rules from `rules/*.md` front-matter, with a person's own choices on top when a build
runs under them (`use_user_rules`)."""

from __future__ import annotations

import contextlib
import copy
import os
from collections.abc import Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from .choices import UserRules

NOT_YET_BUILT = "not yet built"
REQUIRED_KEYS = ("rule", "values", "enforced_in")
ENV_VAR = "OPEN_ALTIO_RULES_DIR"

_override: Path | None = None  # in place of rules/, while use_rules_dir is in force
_extra: list[Path] = []  # folders added by packages with rules of their own
_replaced: list[Path] | None = None  # in place of every folder, while use_rules_dirs is in force
# A context variable, not a global: the explorer rebuilds in a background thread while it keeps
# answering requests under Altio's standard, and each thread starts with its own context.
_in_force: ContextVar[UserRules | None] = ContextVar("user_rules", default=None)


class RuleError(Exception):
    """A rule file is missing, malformed or inconsistent."""


class UnknownRule(RuleError, KeyError):
    """No rule file with that name."""


class UnknownValue(RuleError, KeyError):
    """The rule exists but has no value with that key."""


@dataclass(frozen=True)
class Rule:
    name: str
    values: Mapping[str, Any]
    enforced_in: tuple[str, ...]
    title: str  # the file's '# ' heading
    text: str  # the first paragraph under the heading
    path: Path
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def enforced(self) -> bool:
        return bool(self.enforced_in)

    def value(self, key: str) -> Any:
        try:
            return self.values[key]
        except KeyError:
            raise UnknownValue(
                f"rule {self.name!r} has no value {key!r} (has: {sorted(self.values)})"
            ) from None


def data_root() -> Path:
    """The folder holding rules/ and mappings/. An installed package carries them inside
    itself; a checkout keeps them at the top of the repository, where people read them."""
    package = Path(__file__).resolve().parents[1]
    return package if (package / "rules").is_dir() else package.parents[1]


def rules_dir() -> Path:
    """The public rules folder, `rules/` unless a test or OPEN_ALTIO_RULES_DIR says otherwise."""
    if _override is not None:
        return _override
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env)
    return data_root() / "rules"


def rules_dirs() -> list[Path]:
    """Every folder rules are read from, in the order a name is looked up."""
    if _replaced is not None:
        return list(_replaced)
    return [rules_dir(), *_extra]


def add_rules_dir(path: str | os.PathLike[str]) -> None:
    """Read rules from `path` too, after rules/."""
    folder = Path(path)
    if folder not in _extra:
        _extra.append(folder)


@contextlib.contextmanager
def use_rules_dir(path: str | os.PathLike[str]) -> Iterator[Path]:
    """Read another folder in place of rules/ for the duration of a block; added folders stay."""
    global _override
    previous = _override
    _override = Path(path)
    try:
        yield _override
    finally:
        _override = previous


@contextlib.contextmanager
def use_rules_dirs(paths: list[Path]) -> Iterator[list[Path]]:
    """Read only these folders, in this order, for the duration of a block."""
    global _replaced
    previous = _replaced
    _replaced = [Path(p) for p in paths]
    try:
        yield list(_replaced)
    finally:
        _replaced = previous


@contextlib.contextmanager
def use_user_rules(rules: UserRules) -> Iterator[UserRules]:
    """Read every value through a person's choices for the duration of a block: a value they
    changed is theirs, every other value is Altio's standard, and `is_on` is false for a rule
    they switched off."""
    token = _in_force.set(rules)
    try:
        yield rules
    finally:
        _in_force.reset(token)


def _normalise_enforced_in(raw: Any, path: Path) -> tuple[str, ...]:
    if raw is None:
        raise RuleError(
            f"{path.name}: enforced_in is empty; use '{NOT_YET_BUILT}' or a list of paths"
        )
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list) and all(isinstance(i, str) for i in raw):
        items = raw
    else:
        raise RuleError(f"{path.name}: enforced_in must be a string or a list of paths")
    items = [i.strip() for i in items if i.strip()]
    if items == [NOT_YET_BUILT]:
        return ()
    if NOT_YET_BUILT in items:
        raise RuleError(f"{path.name}: enforced_in mixes '{NOT_YET_BUILT}' with paths")
    return tuple(items)


def _heading_and_text(body: list[str]) -> tuple[str, str]:
    """The first '# ' heading, and the paragraph right under it joined into one line."""
    start = next((i for i, line in enumerate(body) if line.startswith("# ")), None)
    if start is None:
        return "", ""
    paragraph: list[str] = []
    for line in body[start + 1 :]:
        if line.strip():
            paragraph.append(line.strip())
        elif paragraph:
            break
    return body[start][2:].strip(), " ".join(paragraph)


def parse_rule_file(path: str | os.PathLike[str]) -> Rule:
    """Parse one rule file. Raises RuleError if the front-matter is malformed."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise RuleError(f"{path.name}: does not start with front-matter '---'")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise RuleError(f"{path.name}: front-matter is not closed with '---'") from None
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        raise RuleError(f"{path.name}: front-matter is not valid YAML: {exc}") from None
    if not isinstance(meta, dict):
        raise RuleError(f"{path.name}: front-matter is not a mapping")
    missing = [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        raise RuleError(f"{path.name}: front-matter lacks {missing}")
    # an empty mapping is a rule whose only setting is whether it is on
    if not isinstance(meta["values"], dict):
        raise RuleError(f"{path.name}: values must be a mapping")
    if not isinstance(meta["rule"], str):
        raise RuleError(f"{path.name}: rule must be a string")
    title, text = _heading_and_text(lines[end + 1 :])
    return Rule(
        name=meta["rule"],
        values=dict(meta["values"]),
        enforced_in=_normalise_enforced_in(meta["enforced_in"], path),
        title=title,
        text=text,
        path=path,
        extra={k: v for k, v in meta.items() if k not in REQUIRED_KEYS},
    )


def _rule_files() -> list[Path]:
    return sorted(
        (p for d in rules_dirs() for p in d.glob("*.md") if p.name != "README.md"),
        key=lambda p: p.name,
    )


def rule_names() -> list[str]:
    return [p.stem for p in _rule_files()]


# each rule file as last parsed, with the size and time it had then
_PARSED: dict[Path, tuple[tuple[int, int, int], Rule]] = {}


def _parsed(path: Path) -> Rule:
    """parse_rule_file, parsed again only when the file has changed: a page reads its rules
    thousands of times, and each parse reads the YAML afresh. The caller gets a copy of its own."""
    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    kept = _PARSED.get(path)
    if kept is None or kept[0] != stamp:
        kept = _PARSED[path] = (stamp, parse_rule_file(path))
    return copy.deepcopy(kept[1])


def rule(name: str) -> Rule:
    """The rule called `name` (its file is `<name>.md` in one of the rules folders)."""
    found = [d / f"{name}.md" for d in rules_dirs() if (d / f"{name}.md").is_file()]
    if name == "README" or not found:
        folders = [str(d) for d in rules_dirs()]
        raise UnknownRule(f"no rule {name!r} in {folders} (have: {rule_names()})")
    if len(found) > 1:
        raise RuleError(
            f"rule {name!r} is in more than one rules folder: {[str(p) for p in found]}"
        )
    path = found[0]
    parsed = _parsed(path)
    if parsed.name != name:
        raise RuleError(f"{path.name}: front-matter says rule {parsed.name!r}, file is {name!r}")
    return parsed


def value(rule_name: str, key: str) -> Any:
    """One value from a rule's front-matter, e.g. value("sql-limits", "timeout_seconds"), or the
    person's own when a build runs under their choices."""
    standard = rule(rule_name).value(key)
    chosen = _in_force.get()
    if chosen is not None and key in chosen.values.get(rule_name, {}):
        return chosen.values[rule_name][key]
    return standard


def is_on(rule_name: str) -> bool:
    """Whether a rule acts: every rule does, unless the person switched it off."""
    rule(rule_name)  # an unknown name fails loudly, as value() does
    chosen = _in_force.get()
    return chosen is None or rule_name not in chosen.off


def all_rules() -> list[Rule]:
    return [parse_rule_file(p) for p in _rule_files()]
