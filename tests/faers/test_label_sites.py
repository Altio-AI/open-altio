"""A site phrase governing a list codes each listed term to the site's own term (rule
label-dictionary, site_lists). The terms are made up here; the lines are FDA label lines."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.faers.labeldict.coding import Coded, LabelCoder, LabelInfo, SectionRow
from open_altio.faers.labeldict.terms import Term
from open_altio.testing.rules import rules_with

TERMS = [  # llt code, llt name, pt code, pt name
    ("1", "Pruritus", "1", "Pruritus"),
    ("2", "Itching", "1", "Pruritus"),
    ("3", "Pain", "3", "Pain"),
    ("4", "Erythema", "4", "Erythema"),
    ("5", "Swelling", "5", "Swelling"),
    ("6", "Hemorrhage", "6", "Haemorrhage"),
    ("7", "Injection site pruritus", "7", "Injection site pruritus"),
    ("8", "Injection site itching", "7", "Injection site pruritus"),
    ("9", "Injection site pain", "9", "Injection site pain"),
    ("10", "Injection site erythema", "10", "Injection site erythema"),
    ("11", "Injection site swelling", "11", "Injection site swelling"),
    ("12", "Injection site reaction", "12", "Injection site reaction"),
    ("13", "Asthenia", "13", "Asthenia"),
    ("14", "Pyrexia", "14", "Pyrexia"),
    ("15", "Fever", "14", "Pyrexia"),
    ("16", "Nausea", "16", "Nausea"),
    ("17", "Phlebitis", "17", "Phlebitis"),
]


@pytest.fixture(scope="module")
def coder() -> LabelCoder:
    return LabelCoder([Term(*t) for t in TERMS], [])


def coded(coder, line, section="adverse_reactions"):
    out = Coded()
    coder.code(
        [SectionRow("set-x", section, 1, False, line)], {"set-x": LabelInfo("1", "x", "")}, out
    )
    return {(r["matched_text"].lower(), r["pt_name"], r["kept"]) for r in out.terms}


def test_a_site_phrase_codes_its_list_to_the_site_terms(coder):
    line = "Injection site reactions (erythema and/or itching, hemorrhage, pain or swelling)"
    assert coded(coder, line) == {
        ("injection site reactions", "Injection site reaction", True),
        ("erythema", "Injection site erythema", True),
        ("itching", "Injection site pruritus", True),
        ("hemorrhage", "Injection site reaction", True),  # no site term: the umbrella
        ("pain", "Injection site pain", True),
        ("swelling", "Injection site swelling", True),
    }
    assert "(" in rulebook.value("label-dictionary", "site_lists")["starts"]


def test_the_list_may_follow_including_or_manifested_by(coder):
    line = (
        "EGRIFTA SV treatment may cause injection site reactions, including injection site "
        "erythema, pruritus, pain, irritation, and bruising."
    )
    assert ("pain", "Injection site pain", True) in coded(coder, line)
    assert ("pruritus", "Injection site pruritus", True) in coded(coder, line)
    line = "Injection site reactions are most commonly manifested by pain, erythema and pruritus."
    assert {pt for _, pt, _ in coded(coder, line)} == {
        "Injection site reaction",
        "Injection site pain",
        "Injection site erythema",
        "Injection site pruritus",
    }


def test_terms_outside_the_list_or_after_no_site_phrase_are_read_as_written(coder):
    assert coded(coder, "General Disorders and Administration Site Conditions: Asthenia") == {
        ("asthenia", "Asthenia", True)
    }
    line = "Injection/infusion site reactions (phlebitis, pain), pyrexia"
    assert ("pyrexia", "Pyrexia", True) in coded(coder, line)
    line = "The most common adverse reactions were fatigue, infusion site reaction, nausea"
    assert ("nausea", "Nausea", True) in coded(coder, line)
    line = "Local injection site reactions may be accompanied by systemic reactions like fever"
    assert ("fever", "Pyrexia", True) in coded(coder, line)
    line = "Serious injection site reactions (ISRs), including pain, have been reported"
    assert ("pain", "Injection site pain", True) in coded(coder, line)


def test_a_listed_term_with_no_site_term_and_no_umbrella_is_kept_off(tmp_path):
    terms = [t for t in TERMS if t[1] != "Injection site reaction"]
    coder = LabelCoder([Term(*t) for t in terms], [])
    assert ("phlebitis", "Phlebitis", False) in coded(coder, "Infusion site reactions (phlebitis)")


def test_switched_off_the_list_is_read_as_written(tmp_path):
    with rules_with(
        tmp_path,
        {
            "label-dictionary": {
                "site_lists": {**rulebook.value("label-dictionary", "site_lists"), "read": False}
            }
        },
    ):
        coder = LabelCoder([Term(*t) for t in TERMS], [])
        assert ("pain", "Pain", True) in coded(coder, "Injection site reactions (pain)")
