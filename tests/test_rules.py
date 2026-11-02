"""The rules folder is the single source of every limit and policy.

These tests fail when a rule file is malformed, when the index and the files
disagree, when a rule names code that does not exist, or when code reads or
types a rule value other than through the loader (open_altio.testing.rulecheck).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from open_altio import rulebook
from open_altio.faers.funnel import FUNNEL_STEPS
from open_altio.testing.rulecheck import RuleTree

ROOT = Path(__file__).resolve().parents[1]  # the repository
# the loader (its docstrings show how to read a rule) and the test helpers are not enforcing code
TREE = RuleTree(
    root=ROOT,
    folder=ROOT / "rules",
    not_enforcing=("src/open_altio/rulebook/", "src/open_altio/testing/"),
    # these read scratch rules a test writes, not the rules in rules/
    loader_tests=("tests/rulebook/", "tests/contract/test_rules_folders.py"),
)
RULE_FILES = TREE.rule_files()
# what a public rule's front-matter may hold; who decided a rule, and when, is history
FRONT_MATTER = {
    "rule",
    "values",
    "enforced_in",
    "line",
    "always_on",
    "why_locked",
    "settable",
    "placeholder",
}


def _front_matter(path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])


def test_there_are_rules():
    assert RULE_FILES


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.stem)
def test_rule_file_parses_with_required_front_matter(path):
    assert TREE.malformed(path) == []


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.stem)
def test_front_matter_holds_the_rule_and_how_people_see_it_and_nothing_else(path):
    assert set(_front_matter(path)) <= FRONT_MATTER


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.stem)
def test_a_placeholder_is_true_and_names_its_evidence_notebook(path):
    assert TREE.placeholder_problems(path) == []


def _scratch_rule(root: Path, front: str, text: str) -> Path:
    (root / "rules").mkdir(exist_ok=True)
    path = root / "rules" / "widget-cap.md"
    path.write_text(
        f"---\nrule: widget-cap\nvalues: {{cap: 1}}\nenforced_in: not yet built\n{front}---\n"
        f"# Widgets\n\n{text}\n",
        encoding="utf-8",
    )
    return path


def test_a_placeholder_that_is_not_true_or_names_no_written_or_listed_notebook_is_found(
    tmp_path,
):
    """A placeholder waits on its evidence notebook: the notebook is written, or listed in
    notebooks/README.md as To write until it is."""
    tree = RuleTree(root=tmp_path, folder=tmp_path / "rules")
    (tmp_path / "notebooks" / "faers").mkdir(parents=True)
    (tmp_path / "notebooks" / "faers" / "12_widgets.ipynb").write_text("{}", encoding="utf-8")
    (tmp_path / "notebooks" / "README.md").write_text(
        "| Notebook | What it finds | The rules it backs |\n|---|---|---|\n"
        "| `faers/13_gadgets` | To write: how many gadgets | `widget-cap` |\n",
        encoding="utf-8",
    )
    said = {
        "placeholder: soon\n": "never 'soon'",
        "placeholder: true\n": "names its evidence notebook",
    }
    for front, problem in said.items():
        [found] = tree.placeholder_problems(_scratch_rule(tmp_path, front, "Waits."))
        assert problem in found
    waits = "placeholder: true\n"
    missing = _scratch_rule(tmp_path, waits, "Waits on notebooks/faers/14_nothing.")
    assert tree.placeholder_problems(missing) == [
        "widget-cap.md: notebook 14_nothing is not in notebooks/faers/ nor listed in "
        "notebooks/README.md as To write"
    ]
    for named in ("12_widgets", "13_gadgets"):
        found = _scratch_rule(tmp_path, waits, f"Waits on notebooks/faers/{named}.")
        assert tree.placeholder_problems(found) == []
    assert tree.placeholder_problems(_scratch_rule(tmp_path, "", "Decided.")) == []


def test_readme_index_lists_every_rule_file_and_nothing_else():
    assert TREE.index_problems() == []


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.stem)
def test_enforced_in_names_code_that_exists(path):
    assert TREE.enforced_in_problems(path) == []


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.stem)
def test_enforcing_code_reads_the_rule_by_name(path):
    """An enforced rule must be read, by name, by at least one file it lists."""
    if not rulebook.parse_rule_file(path).enforced:
        pytest.skip("not yet built")
    assert TREE.unread(path) is None


def test_every_rule_read_in_code_names_a_real_rule_and_value():
    assert TREE.unknown_reads() == []


def test_code_that_reads_a_rule_is_listed_in_its_enforced_in():
    assert TREE.unlisted_reads() == []


def test_distinctive_rule_values_are_not_typed_into_code_that_reads_the_rule():
    """Code and tests read rule values through rulebook, never as literals."""
    assert TREE.typed_literals() == []


def test_loader_reads_values_from_the_real_rules():
    raw = _front_matter(ROOT / "rules" / "sql-limits.md")
    assert rulebook.value("sql-limits", "timeout_seconds") == raw["values"]["timeout_seconds"]
    assert set(rulebook.rule_names()) == {p.stem for p in RULE_FILES}


def test_dose_strength_measures_each_unit_it_reads_once_and_no_other():
    """A product reads what each strength unit measures from the rule file, so every unit in
    `units` is in exactly one of `measures`, and every unit measured is in `units`."""
    values = _front_matter(ROOT / "rules" / "dose-strength.md")["values"]
    measured = [unit for sizes in values["measures"].values() for unit in sizes]
    assert sorted(measured) == sorted(values["units"])
    assert all(size > 0 for sizes in values["measures"].values() for size in sizes.values())


def test_every_data_rule_is_whole_and_in_a_step_of_the_build():
    """The catalogue checks each data rule as it reads it: a heading, a line, a first
    paragraph, a reason for an always-on rule, and labelled settable values."""
    names = [info.name for info in rulebook.catalogue()]
    assert len(names) == len(set(names))
    assert {s["id"] for s in FUNNEL_STEPS} <= {s.id for s in rulebook.steps()}


def test_a_value_typed_into_code_that_reads_its_rule_is_found_and_elsewhere_it_is_not(tmp_path):
    name = "widget-cap"
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / f"{name}.md").write_text(
        f"---\nrule: {name}\nvalues: {{cap: 250}}\nenforced_in: not yet built\n---\n# Widgets\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "reads.py").write_text(f'cap = value({name!r}, "cap")\nassert cap == 250\n')
    (tmp_path / "src" / "unrelated.py").write_text("dose_mg = 250\n")
    tree = RuleTree(root=tmp_path, folder=tmp_path / "rules")
    with rulebook.use_rules_dirs([tmp_path / "rules"]):
        assert tree.typed_literals() == [
            "src/reads.py:2: 250 typed in; read it with rulebook.value"
        ]
