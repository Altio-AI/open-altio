"""The data rules as people see them: in the order the build applies them, each with its plain
title and line, its step, whether it is always on, and the values a person may set.

A data rule is one that `rules/steps.yaml` places in a step of the build; every other rule is a
limit of the explorer and is not set by people. A step may have one switch for all its rules
(`switch`, the name of one of them): its other rules are not switched alone. A data rule's
front-matter adds to the values:

    line        one plain sentence under its title
    always_on   true when the build cannot run without it, with why_locked saying why
    settable    the values a person may set, each with a plain label (and, for a choice, its
                options as [value, label] pairs, or for a number its minimum)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from .loader import Rule, RuleError, rule, rules_dirs

STEPS_FILE = "steps.yaml"


class NotADataRule(RuleError):
    """The rule exists but limits the explorer; people do not set it."""


@dataclass(frozen=True)
class Step:
    id: str  # as the release's funnel names it
    title: str
    sentence: str  # one plain sentence on what the step does
    switch: str | None = None  # the one rule whose switch turns all the step's rules on and off


@dataclass(frozen=True)
class RuleValue:
    key: str
    label: str
    standard: Any  # Altio's value, from the rule file
    type: str  # bool, number, choice, list or text
    options: tuple[tuple[Any, str], ...] = ()  # a choice's (value, plain words), in order
    minimum: float | None = None  # a number's lowest


@dataclass(frozen=True)
class RuleInfo:
    name: str
    title: str
    line: str
    text: str  # what it does and why, in two or three plain sentences
    step: Step
    always_on: bool
    why_locked: str | None  # for a rule that is always on
    values: list[RuleValue]
    file: str  # the rule file, relative to the repository


def _steps_file() -> list[dict]:
    for folder in rules_dirs():
        path = folder / STEPS_FILE
        if path.is_file():
            return yaml.safe_load(path.read_text(encoding="utf-8"))
    raise RuleError(f"no {STEPS_FILE} in {[str(d) for d in rules_dirs()]}")


def _step(entry: dict) -> Step:
    switch = entry.get("switch")
    if switch is not None and switch not in entry["rules"]:
        raise RuleError(f"{STEPS_FILE}: step {entry['id']} is switched by {switch}, not its rule")
    return Step(entry["id"], entry["title"], entry["sentence"], switch)


def steps() -> list[Step]:
    """The build's steps, in order."""
    return [_step(s) for s in _steps_file()]


def _kind(standard: Any, spec: dict) -> str:
    if "options" in spec:
        return "choice"
    if isinstance(standard, bool):
        return "bool"
    if isinstance(standard, int | float):
        return "number"
    if isinstance(standard, list):
        return "list"
    return "text"


def _value(found: Rule, key: str, spec: dict) -> RuleValue:
    where = f"{found.path.name}: settable {key}"
    if key not in found.values:
        raise RuleError(f"{where} is not one of its values")
    if not spec.get("label"):
        raise RuleError(f"{where} has no label")
    standard = found.values[key]
    options = tuple((v, label) for v, label in spec.get("options", []))
    if options and standard not in [v for v, _ in options]:
        raise RuleError(f"{where}: the standard value is not one of its options")
    return RuleValue(
        key, spec["label"], standard, _kind(standard, spec), options, spec.get("minimum")
    )


def _info(found: Rule, step: Step) -> RuleInfo:
    meta = found.extra
    if not meta.get("line") or not found.title or not found.text:
        raise RuleError(
            f"{found.path.name}: a data rule needs a heading, a line and a first paragraph"
        )
    always_on = bool(meta.get("always_on"))
    if always_on and not meta.get("why_locked"):
        raise RuleError(f"{found.path.name}: always_on needs why_locked")
    if always_on and step.switch is not None:
        raise RuleError(f"{found.path.name}: a rule of a step with one switch cannot be always on")
    settable = meta.get("settable") or {}
    return RuleInfo(
        name=found.name,
        title=found.title,
        line=meta["line"],
        text=found.text,
        step=step,
        always_on=always_on,
        why_locked=meta.get("why_locked") if always_on else None,
        values=[_value(found, key, spec) for key, spec in settable.items()],
        file=f"rules/{found.path.name}",
    )


def catalogue() -> list[RuleInfo]:
    """Every data rule, in the order the build applies them."""
    return [_info(rule(name), _step(s)) for s in _steps_file() for name in s["rules"]]


def data_rule(name: str) -> RuleInfo:
    """One data rule. Raises UnknownRule for no rule at all, NotADataRule for an explorer limit."""
    for s in _steps_file():
        if name in s["rules"]:
            return _info(rule(name), _step(s))
    rule(name)
    raise NotADataRule(f"{name} limits the explorer; it is not a data rule")
