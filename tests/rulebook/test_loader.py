"""The loader, driven against a scratch rules folder."""

from __future__ import annotations

from pathlib import Path

import pytest

from open_altio import rulebook
from open_altio.rulebook import loader


def write_rule(folder, name, body):
    (folder / f"{name}.md").write_text(body, encoding="utf-8")


@pytest.fixture
def rules(tmp_path):
    write_rule(
        tmp_path,
        "widget-cap",
        "---\nrule: widget-cap\nvalues:\n  cap: 7\n  kinds: [a, b]\n"
        "enforced_in: not yet built\n---\n# Widgets stop at seven\n\n"
        "At most seven widgets,\nso the shelf holds.\n\nMore below.\n",
    )
    write_rule(
        tmp_path,
        "listed",
        "---\nrule: listed\nvalues:\n  on: true\n"
        "enforced_in:\n  - src/open_altio/x.py\n  - tests/test_x.py\n---\n# Listed\n",
    )
    with rulebook.use_rules_dir(tmp_path):
        yield tmp_path


def test_value_by_rule_and_key(rules):
    assert rulebook.value("widget-cap", "cap") == 7
    assert rulebook.value("widget-cap", "kinds") == ["a", "b"]


def test_a_rule_file_is_parsed_again_only_when_it_changes(rules, monkeypatch):
    """A page reads its rules thousands of times; each read of an unchanged file is the copy
    parsed before, its own to change, and an edited file is read anew."""
    parsed, parse = [], loader.parse_rule_file
    monkeypatch.setattr(loader, "parse_rule_file", lambda path: parsed.append(path) or parse(path))
    for _ in range(3):
        rulebook.value("widget-cap", "kinds").append("changed by its reader")
    assert rulebook.value("widget-cap", "kinds") == ["a", "b"] and len(parsed) <= 1
    write_rule(
        rules,
        "widget-cap",
        "---\nrule: widget-cap\nvalues:\n  cap: 8\n  kinds: [a]\n"
        "enforced_in: not yet built\n---\n# Widgets stop at eight\n",
    )
    assert rulebook.value("widget-cap", "cap") == 8


def test_rule_carries_metadata(rules):
    r = rulebook.rule("widget-cap")
    assert r.title == "Widgets stop at seven"
    assert r.text == "At most seven widgets, so the shelf holds."
    assert r.enforced_in == () and not r.enforced
    assert r.value("cap") == 7


def test_enforced_in_list_is_kept(rules):
    assert rulebook.rule("listed").enforced_in == ("src/open_altio/x.py", "tests/test_x.py")


def test_enforced_in_single_path_string_is_normalised(rules):
    write_rule(
        rules,
        "one",
        "---\nrule: one\nvalues: {a: 1}\nenforced_in: src/open_altio/a.py\n---\n# One\n",
    )
    assert rulebook.rule("one").enforced_in == ("src/open_altio/a.py",)


def test_unknown_rule_and_value_fail_loudly(rules):
    with pytest.raises(rulebook.UnknownRule):
        rulebook.value("no-such-rule", "cap")
    with pytest.raises(rulebook.UnknownValue):
        rulebook.value("widget-cap", "no_such_key")
    with pytest.raises(KeyError):
        rulebook.value("widget-cap", "no_such_key")


def test_rule_name_must_match_file(rules):
    write_rule(
        rules,
        "misnamed",
        "---\nrule: other\nvalues: {a: 1}\nenforced_in: not yet built\n---\n# M\n",
    )
    with pytest.raises(rulebook.RuleError):
        rulebook.rule("misnamed")


@pytest.mark.parametrize(
    "front",
    [
        "rule: bad\nvalues: {a: 1}\n",  # no enforced_in
        "rule: bad\nvalues: [a]\nenforced_in: not yet built\n",  # values not a mapping
        "rule: bad\nvalues: {a: 1}\nenforced_in: [not yet built, a.py]\n",
        "rule: bad\nvalues: [a\n",  # not YAML
    ],
)
def test_malformed_front_matter_is_refused(rules, front):
    write_rule(rules, "bad", f"---\n{front}---\n# Bad\n")
    with pytest.raises(rulebook.RuleError):
        rulebook.rule("bad")


def test_override_is_undone_after_the_block(rules):
    assert rulebook.rules_dir() == rules
    with rulebook.use_rules_dir(rules / "elsewhere"):
        assert rulebook.rule_names() == []
    assert rulebook.rules_dir() == rules


def test_default_folder_is_rules_at_the_top_of_a_checkout(monkeypatch):
    monkeypatch.delenv(rulebook.ENV_VAR, raising=False)
    assert rulebook.data_root() == Path(__file__).resolve().parents[2]
    assert rulebook.rules_dir() == rulebook.data_root() / "rules"


def test_an_added_folder_is_read_after_rules(rules, tmp_path_factory):
    extra = tmp_path_factory.mktemp("extra-rules")
    write_rule(
        extra,
        "door-cap",
        "---\nrule: door-cap\nvalues: {cap: 3}\nenforced_in: not yet built\n---\n# Doors\n",
    )
    before = list(loader._extra)
    try:
        rulebook.add_rules_dir(extra)
        rulebook.add_rules_dir(extra)  # adding it again changes nothing
        assert rulebook.rules_dirs() == [rules, extra]
        assert rulebook.value("door-cap", "cap") == 3
        assert rulebook.value("widget-cap", "cap") == 7
        assert {"door-cap", "widget-cap"} <= set(rulebook.rule_names())
    finally:
        loader._extra[:] = before


def test_a_rule_in_two_folders_is_refused(rules, tmp_path_factory):
    extra = tmp_path_factory.mktemp("twice")
    write_rule(
        extra,
        "widget-cap",
        "---\nrule: widget-cap\nvalues: {cap: 8}\nenforced_in: not yet built\n---\n# W\n",
    )
    with rulebook.use_rules_dirs([rules, extra]), pytest.raises(rulebook.RuleError):
        rulebook.rule("widget-cap")


def test_replacing_every_folder_is_undone_after_the_block(rules, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    with rulebook.use_rules_dirs([elsewhere]):
        assert rulebook.rules_dirs() == [elsewhere]
        assert rulebook.rule_names() == []
    assert rulebook.rules_dirs()[0] == rules


def test_rules_with_changes_a_rule_in_whichever_folder_holds_it(rules, tmp_path_factory):
    from open_altio.testing.rules import rules_with

    extra = tmp_path_factory.mktemp("extra")
    write_rule(
        extra,
        "door-cap",
        "---\nrule: door-cap\nvalues: {cap: 3, keep: 1}\nenforced_in: not yet built\n---\n# D\n",
    )
    with rulebook.use_rules_dirs([rules, extra]):
        with rules_with(
            tmp_path_factory.mktemp("scratch"), {"door-cap": {"cap": 4}, "widget-cap": {"cap": 9}}
        ):
            assert rulebook.value("door-cap", "cap") == 4
            assert rulebook.value("door-cap", "keep") == 1
            assert rulebook.value("widget-cap", "cap") == 9
        assert rulebook.value("door-cap", "cap") == 3
