"""Every rule's version in methods.json (methods.rule_versions): a short hash of its file's
front-matter values and its text, and its values as the release was built with them, so the
next release can say which rules are new or changed."""

from __future__ import annotations

import re

from open_altio import rulebook
from open_altio.faers.insights.methods import rule_hash, rule_versions

RULE = """---
rule: example
values:
  limit: 3
enforced_in: not yet built
---

# An example

It does one thing.
"""


def test_the_release_records_every_rule_with_its_hash_and_values(methods):
    got = methods["rule_versions"]
    assert sorted(got) == sorted(rulebook.rule_names())
    for name, version in got.items():
        assert re.fullmatch("[0-9a-f]{12}", version["hash"])
        assert sorted(version["values"]) == sorted(rulebook.rule(name).values)
    some = next(n for n in got if got[n]["values"])
    key = next(iter(got[some]["values"]))
    assert got[some]["values"][key] == rulebook.value(some, key)
    assert len({v["hash"] for v in got.values()}) == len(got)


def test_a_rules_hash_changes_with_its_values_or_text_and_not_with_its_layout(tmp_path):
    path = tmp_path / "example.md"
    path.write_text(RULE, encoding="utf-8")
    first = rule_hash(path)
    path.write_text(RULE.replace("limit: 3", "limit:   3   # the same value"), encoding="utf-8")
    assert rule_hash(path) == first
    path.write_text(RULE.replace("limit: 3", "limit: 4"), encoding="utf-8")
    assert rule_hash(path) != first
    path.write_text(RULE.replace("one thing.", "one other thing."), encoding="utf-8")
    assert rule_hash(path) != first


def test_the_values_are_the_ones_the_release_was_built_with():
    name = next(n for n in rulebook.rule_names() if isinstance(_first(n), int | float))
    key = next(iter(rulebook.rule(name).values))
    mine = _first(name) + 1
    with rulebook.use_user_rules(rulebook.UserRules(values={name: {key: mine}})):
        got = rule_versions()[name]
    assert got["values"][key] == mine
    assert got["hash"] == rule_versions()[name]["hash"]  # the file is the same


def _first(name: str):
    values = rulebook.rule(name).values
    return next(iter(values.values())) if values else None
