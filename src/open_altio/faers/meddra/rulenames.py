"""Every rule that names MedDRA's terms, read against one MedDRA version.

A new version enters a release only at a build (rule meddra-version), so a name it no longer
holds is said loudly there and kept in the licensed manifest. The build goes on: a name is the
rule's to correct, and a person asking meanwhile gets that one fact empty, with the reason.

    missing_names(held, groups)      {rule: {list: [names it does not hold]}}
    warning_lines(version, missing)  what the build says of them
"""

from __future__ import annotations

from dataclasses import dataclass

from open_altio import rulebook

GROUPS_RULE = "label-groups"


@dataclass(frozen=True)
class Held:
    """What one version holds, in lower case: its groups at every level on a primary path, its
    high level terms on any path, its PTs and its active SMQs."""

    groups: frozenset[str]
    hlts: frozenset[str]
    pts: frozenset[str]
    smqs: frozenset[str]


def group_keys() -> dict[str, bool]:
    """The licensed groups file's keys, as the rules that read them name them, and whether each
    may name high level terms only."""
    return {
        rulebook.value("not-a-medical-event", "groups_key"): False,
        rulebook.value("label-not-a-medical-event", "groups_key"): False,
        rulebook.value("label-procedure", "groups_key"): False,
        rulebook.value("label-flags", "catch_all_key"): rulebook.value(
            GROUPS_RULE, "catch_all_hlt_only"
        ),
    }


def smq_key() -> str:
    """The licensed groups file's key for the SMQ rule pregnancy-cases reads."""
    return str(rulebook.value("pregnancy-cases", "smq_key"))


def file_keys() -> list[str]:
    """Every key of the licensed groups file."""
    return [*group_keys(), smq_key()]


def words(rule: str, key: str, version: str, names: list[str]) -> str:
    """A rule's list naming what a version does not hold, as a page and a build both say it."""
    return f"Rule {rule} names {key} that MedDRA {version} does not hold: {names}."


def _named() -> dict[str, dict[str, tuple[list[str], str]]]:
    """Each rule's lists of MedDRA's names, each with the level the rule reads them at."""
    flags = rulebook.value("label-flags", "same_meaning")
    examples = rulebook.value("label-coding", "stated_examples")
    return {
        "not-a-medical-event": {"pts": (list(rulebook.value("not-a-medical-event", "pts")), "pts")},
        "label-not-a-medical-event": {
            key: (list(rulebook.value("label-not-a-medical-event", key)), "pts")
            for key in ("pts", "compared_pts")
        },
        "label-flags": {"same_meaning": ([n for pair in flags for n in pair], "pts")},
        "label-coding": {"stated_examples": ([p for e in examples for p in e["pts"]], "pts")},
    }


def missing_names(held: Held, groups: dict[str, list[str]] | None) -> dict[str, dict[str, list]]:
    """Each rule's names the version does not hold, in lower case, by the rule and its list; for
    rule label-groups, a list `groups` does not give at all is there and empty."""
    missing: dict[str, dict[str, list]] = {}
    for rule, lists in _named().items():
        for key, (names, level) in lists.items():
            known = getattr(held, level)
            if lost := sorted({str(n).lower() for n in names} - known):
                missing.setdefault(rule, {})[key] = lost
    levels = {k: held.hlts if hlt_only else held.groups for k, hlt_only in group_keys().items()}
    for key, known in (levels | {smq_key(): held.smqs}).items():
        given = (groups or {}).get(key)
        if given is None:
            missing.setdefault(GROUPS_RULE, {})[key] = []
        elif lost := sorted({n.lower() for n in given} - known):
            missing.setdefault(GROUPS_RULE, {})[key] = lost
    return missing


def warning_lines(version: str, missing: dict[str, dict[str, list]]) -> list[str]:
    """What the build says of `missing_names`' answer, one line a list."""
    lines = []
    for rule, lists in missing.items():
        for key, names in lists.items():
            lines.append(
                f"WARNING: {words(rule, key, version, names)}"
                if names
                else f"WARNING: MedDRA {version} has no list {key} in its licensed part: give it "
                f"with `labels --groups` (rule {GROUPS_RULE})."
            )
    return lines


__all__ = [
    "GROUPS_RULE",
    "Held",
    "file_keys",
    "group_keys",
    "missing_names",
    "smq_key",
    "warning_lines",
    "words",
]
