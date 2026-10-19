"""The data rules as people see them: the real catalogue, and a scratch rules folder for what
the catalogue refuses."""

from __future__ import annotations

import pytest

from open_altio import rulebook

STEPS = """\
- id: first
  title: The first step
  sentence: It does one thing.
  rules: [widget-cap]
"""
WIDGET = """\
---
rule: widget-cap
line: Widgets stop at a number.
values: {{cap: 7, colour: blue}}
{extra}enforced_in: not yet built
---
# Widget cap

At most seven widgets, so the shelf holds.
"""


def _scratch(folder, extra: str = "") -> None:
    (folder / "steps.yaml").write_text(STEPS, encoding="utf-8")
    (folder / "widget-cap.md").write_text(WIDGET.format(extra=extra), encoding="utf-8")
    (folder / "door-limit.md").write_text(
        "---\nrule: door-limit\nvalues: {doors: 2}\nenforced_in: not yet built\n---\n# Doors\n",
        encoding="utf-8",
    )


def test_the_catalogue_lists_every_data_rule_under_its_step_in_build_order():
    infos = rulebook.catalogue()
    steps = [s.id for s in rulebook.steps()]
    positions = [steps.index(i.step.id) for i in infos]
    assert positions == sorted(positions)
    assert {i.step.id for i in infos} == set(steps)
    for info in infos:
        assert info.title and info.line and info.text and info.file == f"rules/{info.name}.md"
        assert "\u2014" not in info.title + info.line + info.text  # no em dash


def test_a_rule_that_is_always_on_says_why():
    for info in rulebook.catalogue():
        assert bool(info.why_locked) == info.always_on, info.name


def test_settable_values_carry_a_plain_label_altio_standard_and_their_kind():
    info = rulebook.data_rule("dup-manufacturer-number")
    values = {v.key: v for v in info.values}
    gap = values["max_age_gap_years"]
    assert (gap.type, gap.standard, gap.minimum) == (
        "number",
        rulebook.value(info.name, "max_age_gap_years"),
        0,
    )
    sexes = values["clashing_sexes"]
    assert sexes.type == "choice" and sexes.standard in [value for value, _ in sexes.options]
    assert [words for _, words in sexes.options] == ["Yes", "No"]
    # a value that is part of how the rule works is not offered
    assert "country_code" not in values


def test_an_explorer_limit_is_not_a_data_rule_and_an_unknown_name_is_not_a_rule():
    with pytest.raises(rulebook.NotADataRule):
        rulebook.data_rule("sql-limits")
    with pytest.raises(rulebook.UnknownRule):
        rulebook.data_rule("no-such-rule")


def test_a_scratch_rules_folder_gives_its_own_catalogue(tmp_path):
    _scratch(tmp_path, "settable:\n  cap: {label: Most widgets, minimum: 1}\n")
    with rulebook.use_rules_dirs([tmp_path]):
        [info] = rulebook.catalogue()
        assert (info.name, info.title, info.line, info.step.title) == (
            "widget-cap",
            "Widget cap",
            "Widgets stop at a number.",
            "The first step",
        )
        assert info.text == "At most seven widgets, so the shelf holds."
        assert [(v.key, v.label, v.standard, v.type) for v in info.values] == [
            ("cap", "Most widgets", 7, "number")
        ]


@pytest.mark.parametrize(
    "extra, refusal",
    [
        ("settable:\n  size: {label: Size}\n", "not one of its values"),
        ("settable:\n  cap: {minimum: 1}\n", "has no label"),
        ("settable:\n  colour: {label: Colour, options: [[red, Red]]}\n", "not one of its options"),
        ("always_on: true\n", "why_locked"),
    ],
)
def test_the_catalogue_refuses_a_data_rule_that_is_not_whole(tmp_path, extra, refusal):
    _scratch(tmp_path, extra)
    with rulebook.use_rules_dirs([tmp_path]), pytest.raises(rulebook.RuleError, match=refusal):
        rulebook.catalogue()


def test_a_data_rule_needs_its_plain_line(tmp_path):
    _scratch(tmp_path)
    path = tmp_path / "widget-cap.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("line: Widgets stop at a number.\n", ""),
        encoding="utf-8",
    )
    with (
        rulebook.use_rules_dirs([tmp_path]),
        pytest.raises(rulebook.RuleError, match="needs a heading, a line"),
    ):
        rulebook.catalogue()


@pytest.mark.parametrize(
    "switch, extra, refusal",
    [
        ("door-limit", "", "switched by door-limit, not its rule"),
        ("widget-cap", "always_on: true\nwhy_locked: Shelves need it.\n", "cannot be always on"),
    ],
)
def test_a_step_with_one_switch_names_one_of_its_rules_that_can_be_off(
    tmp_path, switch, extra, refusal
):
    _scratch(tmp_path, extra)
    steps = tmp_path / "steps.yaml"
    steps.write_text(steps.read_text(encoding="utf-8") + f"  switch: {switch}\n", encoding="utf-8")
    with rulebook.use_rules_dirs([tmp_path]), pytest.raises(rulebook.RuleError, match=refusal):
        rulebook.catalogue()
