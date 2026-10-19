"""Pairs of PTs the label rules read by name (rule label-flags): the PT a label keeps in place
of the reported one. The comparison is a plain function, so the tests give it invented codes."""

from __future__ import annotations

from datetime import date

from open_altio.faers.labeldict.flags import Label, Meddra, compare

LABELS = {("1", "by_mouth"): Label("set-a", date(2025, 6, 1))}
REACTIONS = {"reported": "P1", "twin": "P2", "other": "P3"}


def term(pt, section="adverse_reactions", kept=True):
    return {
        "set_id": "set-a",
        "section": section,
        "pt_code": pt,
        "kept": kept,
        "decided_by": "rule",
    }


def outcome(reaction, terms, **meddra):
    given = dict(primary_hlt={}, umbrella_hlt={}, severe=(), not_medical=(), procedures=()) | meddra
    meddra = Meddra(reaction_pt=REACTIONS, **given)
    got = compare([("1", "by_mouth", reaction)], labels=LABELS, terms=terms, meddra=meddra)
    return got[0]


def test_a_label_keeping_the_pt_that_means_the_same_lists_the_reported_one():
    flag = outcome("Reported", [term("P2", "warnings")], same_meaning={"P1": {"P2"}})
    assert (flag["outcome"], flag["section"], flag["expectedness"]) == (
        "on_label",
        "warnings",
        "expected",
    )


def test_the_pair_reads_one_way_and_a_kept_off_or_other_pt_is_not_the_twin():
    twins = {"P1": {"P2"}}
    assert outcome("Twin", [term("P1")], same_meaning=twins)["outcome"] == "not_on_label"
    assert (
        outcome("Reported", [term("P2", kept=False)], same_meaning=twins)["outcome"]
        == "not_on_label"
    )
    assert outcome("Reported", [term("P3")], same_meaning=twins)["outcome"] == "not_on_label"
    assert outcome("Reported", [term("P2")])["outcome"] == "not_on_label"  # no pair, no twin


def test_a_group_whose_kept_pts_are_all_the_opposite_direction_is_not_related():
    group = {"P1": "H1", "P2": "H1", "P3": "H1"}
    rise, fall = ("up", "platelets"), ("down", "platelets")
    direction = {"P1": rise, "P2": fall, "P3": ("down", "sugar")}
    given = {"primary_hlt": group, "direction": direction}
    assert outcome("Reported", [term("P2")], **given)["outcome"] == "not_on_label"
    # one neighbour that is no opposite, or an opposite of another measure, keeps it related
    assert outcome("Reported", [term("P2"), term("P3")], **given)["outcome"] == "related"
    assert outcome("Reported", [term("P3")], **given)["outcome"] == "related"
    assert outcome("Reported", [term("P2")], primary_hlt=group)["outcome"] == "related"


def test_an_exact_term_is_listed_or_not_listed_and_never_related_or_set_aside():
    given = {"exact": {"P1"}, "primary_hlt": {"P1": "H1", "P2": "H1"}}
    assert outcome("Reported", [term("P1", "warnings")], **given)["outcome"] == "on_label"
    flag = outcome("Reported", [term("P2")], **given)  # a neighbour in the group
    assert (flag["outcome"], flag["expectedness"]) == ("not_on_label", "unexpected")
    assert outcome("Reported", [term("P1")], not_medical={"P1"})["outcome"] == "not_a_medical_event"
