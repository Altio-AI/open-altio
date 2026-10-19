"""The one coding question, its reasons for none and the page to read (rule label-coding)."""

from __future__ import annotations

import re

from open_altio import rulebook
from open_altio.labelreview import coding


def test_the_question_asks_for_preferred_terms_or_none():
    assert "preferred term" in coding.question()


def test_every_reason_for_none_has_a_name_a_definition_and_examples():
    reasons = coding.reasons()
    assert set(reasons) == {
        "states_no_reaction",
        "population",
        "did_not_happen",
        "not_studied_or_unknown",
        "not_with_this_drug",
        "other",
    }
    for r in reasons.values():
        assert r.name and r.definition and r.examples
    assert [k for k, r in reasons.items() if r.needs_note] == rulebook.value(
        "label-coding", "needs_note"
    )


def test_examples_name_preferred_terms_only_never_codes_or_the_hierarchy():
    rule = rulebook.rule("label-coding")
    texts = [e["label"] + " " + " ".join(e["pts"]) for e in rule.value("stated_examples")]
    texts += [x for r in coding.reasons().values() for x in r.examples]
    for text in texts:
        assert not re.search(r"\d{8}", text), text
        assert not re.search(r"\b(LLT|HLT|HLGT|SOC|SMQ)\b", text), text


def test_the_page_to_read_carries_the_question_the_rules_and_the_faers_line():
    page = coding.as_markdown()
    rule = rulebook.rule("label-coding")
    assert coding.question() in page
    assert " ".join(rule.value("stated").split()) in page
    assert "postmarketing" in page or "after approval" in page
    assert rule.value("faers_line") in page
    for r in coding.reasons().values():
        assert r.name in page and r.definition in page
