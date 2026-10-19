"""A person's own rules: reading and writing rules.toml, the checks a build runs on them, and a
build's view of the rules while they are in force."""

from __future__ import annotations

import re
import threading
import tomllib

import pytest

from open_altio import rulebook
from open_altio.rulebook import (
    UserRules,
    check_user_rules,
    load_user_rules,
    rules_toml,
    save_user_rules,
)

GAP = rulebook.value("dup-manufacturer-number", "max_age_gap_years")
MINE = UserRules(
    off=frozenset({"deleted-cases", "dup-padded-event-dates"}),
    values={"dup-manufacturer-number": {"max_age_gap_years": GAP + 3}},
)


# ------------------------------------------------------------- the file
def test_no_file_means_altio_standard(tmp_path):
    assert load_user_rules(tmp_path / rulebook.FILE_NAME) == UserRules()


def test_saved_choices_read_back_the_same(tmp_path):
    path = tmp_path / rulebook.FILE_NAME
    save_user_rules(path, MINE)
    assert load_user_rules(path) == MINE
    assert [p.name for p in tmp_path.iterdir()] == [rulebook.FILE_NAME]


def test_the_file_lists_every_data_rule_and_writes_out_only_what_differs():
    text = rules_toml(MINE)
    doc = tomllib.loads(text)
    for info in rulebook.catalogue():
        assert f"# {info.title}\n" in text
        own_switch = not info.always_on and info.step.switch in (None, info.name)
        assert (info.name in doc) == (own_switch or bool(info.values))
    assert doc["deleted-cases"] == {"on": False}
    assert doc["dup-manufacturer-number"] == {"on": True, "max_age_gap_years": GAP + 3}
    assert f"max_age_gap_years = {GAP + 3}    # yours; Altio standard: {GAP}\n" in text
    assert f"# max_age_gap_years = {GAP}    # Altio standard" not in text
    # a rule that is always on has no switch to write, only its values
    assert "on" not in doc["latest-version"]


def test_altio_standard_written_out_reads_back_as_the_standard(tmp_path):
    path = tmp_path / rulebook.FILE_NAME
    path.write_text(rules_toml(UserRules()), encoding="utf-8")
    assert load_user_rules(path) == UserRules()


def test_a_commented_value_used_by_removing_its_first_hash_stays_valid_toml(tmp_path):
    path = tmp_path / rulebook.FILE_NAME
    standard = f"# max_age_gap_years = {GAP}    # Altio standard; remove the first # to change"
    text = rules_toml(UserRules())
    assert standard in text
    path.write_text(
        text.replace(standard, standard[2:].replace(str(GAP), str(GAP + 1), 1)), encoding="utf-8"
    )
    assert load_user_rules(path).values == {
        "dup-manufacturer-number": {"max_age_gap_years": GAP + 1}
    }


@pytest.mark.parametrize(
    "text, said",
    [
        ("[deleted-cases\non = false\n", "is not a valid rules file"),
        ("on = false\n", "on is not under a rule"),
        ('[deleted-cases]\non = "no"\n', "on must be true or false"),
    ],
)
def test_a_file_that_cannot_be_read_is_refused_in_plain_words(tmp_path, text, said):
    path = tmp_path / rulebook.FILE_NAME
    path.write_text(text, encoding="utf-8")
    with pytest.raises(rulebook.UserRulesError, match=re.escape(said)):
        load_user_rules(path)


def test_choices_a_build_would_refuse_are_never_saved(tmp_path):
    path = tmp_path / rulebook.FILE_NAME
    with pytest.raises(rulebook.UserRulesError, match="always on"):
        save_user_rules(path, UserRules(off=frozenset({"latest-version"})))
    assert not path.exists()


# ------------------------------------------------------------- the checks
def test_altio_standard_and_sensible_choices_pass():
    assert check_user_rules(UserRules()) == []
    assert check_user_rules(MINE) == []


@pytest.mark.parametrize(
    "rules, said",
    [
        (
            UserRules(off=frozenset({"latest-version"})),
            "Newest version of each case is always on. "
            "Without it, every version of a case would count",
        ),
        (UserRules(off=frozenset({"no-such-rule"})), "There is no data rule called no-such-rule."),
        (
            UserRules(values={"sql-limits": {"timeout_seconds": 1}}),
            "sql-limits is a limit of the explorer",
        ),
        (
            UserRules(values={"dup-manufacturer-number": {"country_code": "^X"}}),
            "Same company case number has no value country_code to set; "
            "it has max_age_gap_years, clashing_sexes.",
        ),
        (
            UserRules(values={"overlong-lines": {"split": False}}),
            "it can only be switched on or off",
        ),
        (
            UserRules(values={"dup-manufacturer-number": {"max_age_gap_years": "2"}}),
            "max_age_gap_years must be a number",
        ),
        (
            UserRules(values={"dup-manufacturer-number": {"max_age_gap_years": True}}),
            "max_age_gap_years must be a number",
        ),
        (
            UserRules(values={"dup-manufacturer-number": {"max_age_gap_years": -1}}),
            "max_age_gap_years must be 0 or more",
        ),
        (
            UserRules(values={"dup-padded-event-dates": {"min_group_size": 2.5}}),
            "min_group_size must be a whole number",
        ),
        (
            UserRules(values={"dup-padded-event-dates": {"one_sender_only": "yes"}}),
            "one_sender_only must be true or false",
        ),
        (
            UserRules(values={"deleted-cases": {"eras": ["aers"]}}),
            'eras must be ["legacy", "faers"] or ["faers"]',
        ),
        (
            UserRules(values={"no-drug-or-reaction": {"no_event_terms": "NONE"}}),
            "no_event_terms must be a list of words",
        ),
    ],
)
def test_each_choice_a_build_would_refuse_is_said_in_one_plain_sentence(rules, said):
    [problem] = check_user_rules(rules)
    assert said in problem


def test_a_step_with_one_switch_is_switched_by_that_rule_alone():
    """The drug classes go on and off together, by the switch of rule atc-index: the file
    writes that one switch, and switching another of their rules off alone is refused."""
    [step] = [s for s in rulebook.steps() if s.switch]
    rules = [i for i in rulebook.catalogue() if i.step.id == step.id]
    assert step.switch == "atc-index" and len(rules) == 5
    doc = tomllib.loads(rules_toml(UserRules(off=frozenset({step.switch}))))
    assert doc[step.switch] == {"on": False}
    for info in rules:
        if info.name == step.switch:
            continue
        assert info.name not in doc
        [problem] = check_user_rules(UserRules(off=frozenset({info.name})))
        assert problem == (
            f"{info.title} goes on and off with all of {step.title}; "
            f"switch {step.switch} off instead."
        )
    assert check_user_rules(UserRules(off=frozenset({step.switch}))) == []


# ------------------------------------------------------------- what a release records
def test_differences_list_the_rules_off_in_build_order_and_only_values_that_differ():
    same = rulebook.value("dup-padded-event-dates", "min_group_size")
    rules = UserRules(
        off=MINE.off, values={**MINE.values, "dup-padded-event-dates": {"min_group_size": same}}
    )
    assert rulebook.differences(rules) == {
        "off": ["deleted-cases", "dup-padded-event-dates"],
        "changed": [
            {
                "rule": "dup-manufacturer-number",
                "key": "max_age_gap_years",
                "standard": GAP,
                "value": GAP + 3,
            }
        ],
    }
    assert rulebook.from_differences(rulebook.differences(MINE)) == MINE


# ------------------------------------------------------------- rules in force
def test_a_build_reads_the_persons_values_and_switches_only_while_they_are_in_force():
    assert rulebook.is_on("deleted-cases")
    with rulebook.use_user_rules(MINE):
        assert rulebook.value("dup-manufacturer-number", "max_age_gap_years") == GAP + 3
        assert not rulebook.is_on("deleted-cases") and rulebook.is_on("latest-version")
        assert (
            rulebook.value("dup-manufacturer-number", "clashing_sexes")
            == rulebook.rule("dup-manufacturer-number").values["clashing_sexes"]
        )
    assert rulebook.value("dup-manufacturer-number", "max_age_gap_years") == GAP


def test_another_thread_keeps_altio_standard_while_a_build_runs_under_a_persons_rules():
    """The explorer rebuilds in the background while it answers requests."""
    seen = []
    with rulebook.use_user_rules(MINE):
        other = threading.Thread(target=lambda: seen.append(rulebook.is_on("deleted-cases")))
        other.start()
        other.join()
    assert seen == [True]


def test_is_on_fails_loudly_on_a_name_that_is_not_a_rule():
    with pytest.raises(rulebook.UnknownRule):
        rulebook.is_on("no-such-rule")
