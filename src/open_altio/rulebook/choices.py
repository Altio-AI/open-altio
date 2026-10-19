"""A person's own rules: the data rules they switched off and the values they changed, kept in a
`rules.toml` beside their release. A build given them records its differences from Altio's
standard; every value they leave alone follows the standard, including later updates."""

from __future__ import annotations

import json
import os
import textwrap
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .catalogue import NotADataRule, RuleInfo, RuleValue, catalogue, data_rule
from .loader import RuleError, UnknownRule

FILE_NAME = "rules.toml"
WIDTH = 100
KEEP_HINT = "Altio standard; remove the first # to change"

HEADER = """\
# Your rules for building Open Altio releases.
#
# One section per data rule, in the order the build applies them; rules/<name>.md explains each.
# Switch a rule off with on = false. A line starting with # holds Altio's standard value: remove
# that first # and change the value to use your own. Values you leave alone follow Altio's
# standard, including later updates. Build the release again for a change to take effect.
"""


class UserRulesError(RuleError):
    """A rules file that cannot be read, or choices a build would refuse, said plainly."""


@dataclass(frozen=True)
class UserRules:
    off: frozenset[str] = frozenset()
    values: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # rule -> key -> value


def differences(rules: UserRules) -> dict:
    """What a release built with these rules records: the rules off and the values that differ
    from Altio's standard, in the order the build applies them."""
    infos = catalogue()
    changed = [
        {
            "rule": info.name,
            "key": v.key,
            "standard": v.standard,
            "value": rules.values[info.name][v.key],
        }
        for info in infos
        for v in info.values
        if v.key in rules.values.get(info.name, {}) and rules.values[info.name][v.key] != v.standard
    ]
    return {"off": [info.name for info in infos if info.name in rules.off], "changed": changed}


def from_differences(recorded: Mapping) -> UserRules:
    """The rules a release was built with, from the differences it recorded."""
    values: dict[str, dict[str, Any]] = {}
    for change in recorded.get("changed", []):
        values.setdefault(change["rule"], {})[change["key"]] = change["value"]
    return UserRules(frozenset(recorded.get("off", [])), values)


def load_user_rules(path: str | os.PathLike[str]) -> UserRules:
    """The choices in a rules file; Altio's standard when there is no file. Raises UserRulesError
    when the file is not TOML or a section is not shaped as a rule."""
    path = Path(path)
    if not path.is_file():
        return UserRules()
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise UserRulesError(f"{path.name} is not a valid rules file: {exc}.") from None
    off, values = set(), {}
    for name, section in doc.items():
        if not isinstance(section, dict):
            raise UserRulesError(
                f"{path.name}: {name} is not under a rule; "
                "each setting goes under its rule's [name]."
            )
        settings = dict(section)
        on = settings.pop("on", True)
        if not isinstance(on, bool):
            raise UserRulesError(f"{path.name}: [{name}] on must be true or false.")
        if not on:
            off.add(name)
        if settings:
            values[name] = settings
    return UserRules(frozenset(off), values)


def save_user_rules(path: str | os.PathLike[str], rules: UserRules) -> None:
    """Write the choices as a rules file, with every rule and Altio's standard as comments.
    Raises UserRulesError, and writes nothing, when a build would refuse them."""
    problems = check_user_rules(rules)
    if problems:
        raise UserRulesError(" ".join(problems))
    path = Path(path)
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(rules_toml(rules), encoding="utf-8")
    os.replace(partial, path)


def check_user_rules(rules: UserRules) -> list[str]:
    """Every reason a build would refuse these choices, one plain sentence each; none means fine."""
    problems = []
    for name in sorted(set(rules.off) | set(rules.values)):
        try:
            info = data_rule(name)
        except NotADataRule:
            problems.append(
                f"{name} is a limit of the explorer, not a data rule, "
                "so a rules file cannot change it."
            )
            continue
        except UnknownRule:
            problems.append(f"There is no data rule called {name}.")
            continue
        if name in rules.off and info.always_on:
            problems.append(f"{info.title} is always on. {info.why_locked}")
        if name in rules.off and info.step.switch not in (None, name):
            problems.append(
                f"{info.title} goes on and off with all of {info.step.title}; "
                f"switch {info.step.switch} off instead."
            )
        settable = {v.key: v for v in info.values}
        for key, chosen in rules.values.get(name, {}).items():
            if key in settable:
                problems += _value_problems(info, settable[key], chosen)
            elif settable:
                problems.append(
                    f"{info.title} has no value {key} to set; it has {', '.join(settable)}."
                )
            else:
                problems.append(
                    f"{info.title} has no values to set; it can only be switched on or off."
                )
    return problems


def _value_problems(info: RuleInfo, v: RuleValue, chosen: Any) -> list[str]:
    said = f"{info.title}: {v.key}"
    if v.type == "choice":
        allowed = [value for value, _ in v.options]
        if chosen not in allowed:
            return [f"{said} must be {' or '.join(_toml(a) for a in allowed)}."]
    elif v.type == "bool":
        if not isinstance(chosen, bool):
            return [f"{said} must be true or false."]
    elif v.type == "number":
        if isinstance(chosen, bool) or not isinstance(chosen, int | float):
            return [f"{said} must be a number, such as {_toml(v.standard)}."]
        if isinstance(v.standard, int) and chosen != int(chosen):
            return [f"{said} must be a whole number, such as {_toml(v.standard)}."]
        if v.minimum is not None and chosen < v.minimum:
            return [f"{said} must be {_toml(v.minimum)} or more."]
    elif v.type == "list":
        if not isinstance(chosen, list) or not all(isinstance(i, str) for i in chosen):
            return [f"{said} must be a list of words in quotes, such as {_toml(v.standard[:2])}."]
    elif not isinstance(chosen, str):
        return [f"{said} must be words in quotes."]
    return []


def _toml(value: Any) -> str:
    """One value as TOML writes it; the settable values are booleans, numbers, words and lists."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml(i) for i in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)  # JSON's string escapes are TOML's


def _comment(text: str) -> list[str]:
    return textwrap.wrap(text, WIDTH, initial_indent="# ", subsequent_indent="# ") or ["#"]


def _label(v: RuleValue) -> str:
    if v.type != "choice":
        return v.label
    options = " or ".join(f"{_toml(value)} ({words})" for value, words in v.options)
    return f"{v.label}: {options}"


def _section(info: RuleInfo, rules: UserRules) -> list[str]:
    lines = _comment(info.title) + _comment(info.line)
    switch = info.step.switch
    if switch == info.name:
        lines += _comment(f"Switches all of {info.step.title} on or off.")
    # a rule that is always on, or goes on and off with its step's switch, has no switch of its own
    own_switch = not info.always_on and switch in (None, info.name)
    if info.always_on:
        lines += _comment(f"Always on. {info.why_locked}")
    elif not own_switch:
        lines += _comment(f"On or off with [{switch}].")
    if not own_switch and not info.values:
        return lines
    lines.append(f"[{info.name}]")
    if own_switch:
        lines.append(f"on = {_toml(info.name not in rules.off)}")
    chosen = rules.values.get(info.name, {})
    for v in info.values:
        lines += _comment(_label(v))
        if v.key in chosen and chosen[v.key] != v.standard:
            lines.append(
                f"{v.key} = {_toml(chosen[v.key])}    # yours; Altio standard: {_toml(v.standard)}"
            )
        else:
            lines.append(f"# {v.key} = {_toml(v.standard)}    # {KEEP_HINT}")
    return lines


def rules_toml(rules: UserRules) -> str:
    """The text of a rules file holding these choices: every data rule under its step, with
    Altio's standard as comments and only what differs from it written as a setting."""
    out = [HEADER]
    step = None
    for info in catalogue():
        if info.step != step:
            step = info.step
            out.append(
                "\n".join(_comment(f"---- {step.title} ----") + _comment(step.sentence)) + "\n"
            )
        out.append("\n".join(_section(info, rules)) + "\n")
    return "\n".join(out)
