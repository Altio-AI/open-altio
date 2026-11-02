"""The loader, driven against a scratch rules folder."""

from __future__ import annotations

import os
import time
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


def settled(path: Path) -> Path:
    """The file as an installed rule file is: changed longer ago than any file system's clock
    keeps a time coarsely, so its time and size alone say whether it changed."""
    long_ago = time.time_ns() - 2 * loader.SETTLE_NS
    os.utime(path, ns=(long_ago, long_ago))
    return path


def counting_reads(monkeypatch) -> list[Path]:
    reads: list[Path] = []
    read_text = Path.read_text

    def read(self, *args, **kwargs):
        reads.append(self)
        return read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    return reads


def test_a_value_read_twice_reads_its_file_once(rules, monkeypatch):
    """A page reads its rules thousands of times: after the first read a value is a lookup, and
    each reader still gets its own copy to change."""
    path = settled(rules / "widget-cap.md")
    reads = counting_reads(monkeypatch)
    assert rulebook.value("widget-cap", "cap") == 7
    rulebook.value("widget-cap", "kinds").append("changed by its reader")
    assert rulebook.value("widget-cap", "kinds") == ["a", "b"]
    assert rulebook.rule("widget-cap").title == "Widgets stop at seven"
    assert rulebook.is_on("widget-cap") and not rulebook.is_placeholder("widget-cap")
    assert reads.count(path) == 1


def test_a_rule_file_changed_on_disk_is_read_again(rules):
    """A rule changed on disk is seen at its next read: one changed long after it was read, one
    rewritten at once keeping its time and size as a coarse clock does, and one made malformed."""
    path = settled(rules / "widget-cap.md")
    assert rulebook.value("widget-cap", "cap") == 7
    write_rule(rules, "widget-cap", path.read_text(encoding="utf-8").replace("cap: 7", "cap: 9"))
    assert rulebook.value("widget-cap", "cap") == 9

    write_rule(rules, "listed", "---\nrule: listed\nvalues: {n: 1}\nenforced_in: x.py\n---\n")
    assert rulebook.value("listed", "n") == 1
    was = (rules / "listed.md").stat()
    write_rule(rules, "listed", "---\nrule: listed\nvalues: {n: 2}\nenforced_in: x.py\n---\n")
    os.utime(rules / "listed.md", ns=(was.st_atime_ns, was.st_mtime_ns))
    now = (rules / "listed.md").stat()
    assert (now.st_mtime_ns, now.st_size, now.st_ino) == (was.st_mtime_ns, was.st_size, was.st_ino)
    assert rulebook.value("listed", "n") == 2

    write_rule(rules, "widget-cap", "---\nrule: widget-cap\nvalues: [a]\nenforced_in: x.py\n---\n")
    with pytest.raises(rulebook.RuleError):
        rulebook.value("widget-cap", "cap")


def test_a_new_folder_is_seen_at_once_after_rules_were_kept(rules, tmp_path_factory):
    """add_rules_dir and use_rules_dirs change what is read at the next read, however many rules
    were read before them, and a name the new folder shares is refused as ever."""
    settled(rules / "widget-cap.md")
    assert rulebook.value("widget-cap", "cap") == 7
    extra, other, twice = (tmp_path_factory.mktemp(n) for n in ("new", "other", "shared"))
    write_rule(extra, "door-cap", door_rule("door-cap"))
    write_rule(other, "widget-cap", door_rule("widget-cap"))
    write_rule(twice, "widget-cap", door_rule("widget-cap"))
    before = list(loader._extra)
    try:
        rulebook.add_rules_dir(extra)
        assert rulebook.value("door-cap", "cap") == 3
        with rulebook.use_rules_dirs([other]):
            assert rulebook.value("widget-cap", "cap") == 3
            with pytest.raises(rulebook.UnknownRule):
                rulebook.value("door-cap", "cap")
        assert rulebook.value("widget-cap", "cap") == 7
        rulebook.add_rules_dir(twice)
        with pytest.raises(rulebook.RuleError, match="more than one rules folder"):
            rulebook.value("widget-cap", "cap")
    finally:
        loader._extra[:] = before


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


def test_a_placeholder_rule_says_so_and_a_decided_one_does_not(rules):
    write_rule(
        rules,
        "waiting",
        "---\nrule: waiting\nvalues:\n  cap: 3\nenforced_in: not yet built\nplaceholder: true\n"
        "---\n# Waiting\n\nWaits on notebooks/faers/12_widgets.\n",
    )
    assert rulebook.is_placeholder("waiting") and rulebook.value("waiting", "cap") == 3
    assert not rulebook.is_placeholder("widget-cap")
    with pytest.raises(rulebook.UnknownRule):
        rulebook.is_placeholder("no-such-rule")


# a folder added with a prefix --------------------------------------------------------------------


def door_rule(name: str) -> str:
    return f"---\nrule: {name}\nvalues: {{cap: 3}}\nenforced_in: not yet built\n---\n# Doors\n"


def test_a_prefixed_folder_reads_its_prefixed_rules_and_refuses_the_rest(rules, tmp_path_factory):
    extra = tmp_path_factory.mktemp("prefixed")
    write_rule(extra, "p-a", door_rule("p-a"))
    write_rule(extra, "b", door_rule("b"))
    with rulebook.use_rules_dirs([rules, (extra, "p-")]):
        assert rulebook.value("p-a", "cap") == 3
        assert rulebook.value("widget-cap", "cap") == 7  # the folder without a prefix: any name
        with pytest.raises(rulebook.RuleError, match=r"b\.md.*'p-'"):
            rulebook.rule("b")
        with pytest.raises(rulebook.RuleError, match=r"b\.md.*'p-'"):
            rulebook.rule("p-b")  # the file was written without its prefix: said so
        with pytest.raises(rulebook.RuleError, match=r"b\.md.*'p-'"):
            rulebook.all_rules()
        with pytest.raises(rulebook.UnknownRule):
            rulebook.rule("p-c")


def test_a_folder_added_twice_keeps_its_first_prefix(rules, tmp_path_factory):
    extra = tmp_path_factory.mktemp("twice-added")
    before = list(loader._extra)
    try:
        rulebook.add_rules_dir(extra, prefix="p-")
        rulebook.add_rules_dir(extra)
        assert rulebook.rules_folders() == [(rules, None), (extra, "p-")]
    finally:
        loader._extra[:] = before


def test_rules_with_keeps_each_folders_prefix(rules, tmp_path_factory):
    from open_altio.testing.rules import rules_with

    extra = tmp_path_factory.mktemp("prefixed-copy")
    write_rule(extra, "p-a", door_rule("p-a"))
    write_rule(extra, "b", door_rule("b"))
    scratch = tmp_path_factory.mktemp("scratch")
    with (
        rulebook.use_rules_dirs([rules, (extra, "p-")]),
        rules_with(scratch, {"p-a": {"cap": 4}}),
    ):
        assert rulebook.value("p-a", "cap") == 4
        assert [prefix for _, prefix in rulebook.rules_folders()] == [None, "p-"]
        with pytest.raises(rulebook.RuleError, match="'p-'"):
            rulebook.rule("b")
