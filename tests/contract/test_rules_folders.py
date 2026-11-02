"""Rules from other folders: a product adds its own folder of rule files with
`rulebook.add_rules_dir(path, prefix)`, and every rule name there carries the product's prefix, so
a product's rule can never take a name Open Altio may use later (docs/reference/rules.md)."""

from __future__ import annotations

import inspect

import pytest

from open_altio import rulebook
from open_altio.rulebook import loader


def rule_file(name: str, **front: object) -> str:
    extra = "".join(f"{key}: {value}\n" for key, value in front.items())
    return (
        f"---\nrule: {name}\nline: A product's own rule.\nvalues: {{cap: 3}}\n"
        f"enforced_in: not yet built\n{extra}---\n# A product's rule\n\nWaits on its notebook.\n"
    )


@pytest.fixture
def product_rules(tmp_path):
    """A product's folder, added with prefix `p-`, holding `p-a.md` and `b.md`; taken away after."""
    (tmp_path / "p-a.md").write_text(rule_file("p-a", placeholder="true"), encoding="utf-8")
    (tmp_path / "b.md").write_text(rule_file("b"), encoding="utf-8")
    before = list(loader._extra)
    rulebook.add_rules_dir(tmp_path, prefix="p-")
    yield tmp_path
    loader._extra[:] = before


def test_add_rules_dir_takes_a_folder_and_a_prefix():
    params = inspect.signature(rulebook.add_rules_dir).parameters
    assert list(params) == ["path", "prefix"] and params["prefix"].default is None


def test_a_products_rule_is_read_like_any_other_after_open_altios_own(product_rules):
    assert rulebook.rules_dirs()[0] == rulebook.rules_dir()
    assert rulebook.rules_dirs()[-1] == product_rules
    assert rulebook.value("p-a", "cap") == 3 and rulebook.is_placeholder("p-a")
    assert rulebook.rule("p-a").extra["line"] == "A product's own rule."


def test_a_rule_without_the_prefix_is_refused_naming_its_file_and_the_prefix(product_rules):
    for name in ("b", "p-b"):
        with pytest.raises(rulebook.RuleError, match=r"b\.md.*'p-'"):
            rulebook.rule(name)
    with pytest.raises(rulebook.RuleError, match=r"b\.md.*'p-'"):
        rulebook.all_rules()


def test_a_name_in_two_folders_is_refused_as_before(tmp_path):
    """Added without a prefix, a folder may hold any name, but never one Open Altio's holds."""
    taken = min(p.stem for p in rulebook.rules_dir().glob("*.md") if p.stem != "README")
    (tmp_path / f"{taken}.md").write_text(rule_file(taken), encoding="utf-8")
    before = list(loader._extra)
    try:
        rulebook.add_rules_dir(tmp_path)
        with pytest.raises(rulebook.RuleError, match="more than one rules folder"):
            rulebook.rule(taken)
    finally:
        loader._extra[:] = before
