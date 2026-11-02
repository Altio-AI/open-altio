"""An event's facts (/api/events/facts): ages against the drug's own cases, pregnancy cases,
whether the term is a medical event at all, the condition the drug treats and whether the
indication reported is the event. Each fact is checked against the release's own tables, and a
fact the release cannot give is null with its reason, never 0 and never false.

Run over `facts_release` (open_altio.testing.fakefda.FACTS_STORY: digoxin alone, with MedDRA 29.1
and label flags), `label_client`'s release for a drug with several labels, and the release without
MedDRA.
"""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.explorer.access import LOCAL, Viewer
from open_altio.explorer.meddra import ServedMeddra
from open_altio.testing import fakemeddra
from open_altio.testing.releasereader import ReleaseReader
from open_altio.testing.rules import rules_with

DRUG = "digoxin"
EVENT = "Heart rhythm abnormal"  # FDA's Arrhythmia, read to today's term
HLT = fakemeddra.HLTS["93000008"][0]


def event_of(got: dict, name: str) -> dict:
    [found] = [e for e in got["events"] if e["event"] == name]
    return found


def kept_cases(rel: ReleaseReader, *pts: str) -> list[dict]:
    """The kept cases naming any of FDA's reaction texts, with their age bands, from the
    release's own tables."""
    marks = ", ".join("?" for _ in pts)
    return rel.dicts(
        "SELECT c.age_band_T FROM case_latest_T c WHERE c.dup_kept_T AND EXISTS "
        f"(SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')} AND lower(r.pt) IN ({marks}))",
        *[p.lower() for p in pts],
    )


@pytest.fixture(scope="module")
def facts_rel(facts_release):
    return ReleaseReader(facts_release)


@pytest.fixture
def facts(facts_client, ask):
    return lambda status=200, **params: ask(
        facts_client, "/api/events/facts", status, product=DRUG, **params
    )


def share(bands: list[str | None], among: list[str]) -> float | None:
    given = [b for b in bands if b is not None]
    return sum(b in among for b in given) / len(given) if given else None


# ages ---------------------------------------------------------------------------------------


def test_an_events_older_and_children_shares_are_of_the_cases_giving_an_age(facts, facts_rel):
    older, children = (
        rulebook.value("age-groups", "older"),
        rulebook.value("age-groups", "children"),
    )
    got = event_of(facts(), EVENT)
    bands = [c["age_band_T"] for c in kept_cases(facts_rel, "arrhythmia")]
    assert got["cases"] == len(bands) > 0
    assert got["aged"] == len([b for b in bands if b])
    assert got["older"] == share(bands, older) and got["older"] not in (None, 0)
    assert got["children"] == share(bands, children) and got["children"] not in (None, 0)


def test_the_drug_header_gives_the_same_shares_over_all_its_counted_cases(facts, facts_rel):
    older, children = (
        rulebook.value("age-groups", "older"),
        rulebook.value("age-groups", "children"),
    )
    everyone = facts_rel.dicts("SELECT age_band_T FROM case_latest_T WHERE dup_kept_T")
    bands = [c["age_band_T"] for c in everyone]
    drug = facts()["drug"]
    assert drug["cases"] == len(bands)
    assert (drug["aged"], drug["older"], drug["children"]) == (
        len([b for b in bands if b]),
        share(bands, older),
        share(bands, children),
    )


def test_an_event_with_no_case_giving_an_age_has_null_shares_and_says_why(facts, facts_rel):
    got = event_of(facts(), "Congenital anomaly")
    assert [c["age_band_T"] for c in kept_cases(facts_rel, "congenital anomaly")] == [None]
    assert (got["aged"], got["older"], got["children"]) == (0, None, None)
    assert set(got["why"]) >= {"older", "children"}


def test_a_group_naming_a_band_the_age_bands_do_not_hold_refuses_naming_the_rule(facts, tmp_path):
    with rules_with(tmp_path, {"age-groups": {"older": ["65-74", "no-such-band"]}}):
        problem = facts(status=400)["problem"]
    assert "age-groups" in problem and "no-such-band" in problem


def test_events_asked_for_are_the_only_ones_answered(facts):
    got = facts(event=[EVENT, "heart RHYTHM abnormal ", "Nausea"])
    assert [e["event"] for e in got["events"]] == [EVENT]  # Nausea is no digoxin case here
    assert len(facts()["events"]) > 1


def test_a_question_without_a_drug_is_refused(facts_client, ask):
    assert ask(facts_client, "/api/events/facts", status=400)["problem"]


# pregnancy ----------------------------------------------------------------------------------


def test_pregnancy_cases_are_those_naming_a_term_of_the_smq_with_its_sub_smqs_folded(facts):
    got = facts()
    assert event_of(got, EVENT)["pregnancy"] == 1  # the case that also names Pregnancy
    assert event_of(got, "Pregnancy")["pregnancy"] == 1
    # the term only the sub-SMQ holds
    assert event_of(got, "Congenital anomaly")["pregnancy"] == 1
    assert event_of(got, "Drug ineffective")["pregnancy"] == 0


def test_an_smq_the_version_does_not_hold_makes_only_the_pregnancy_fact_null(facts, monkeypatch):
    """A person's page is never refused for a name: the fact is null with the reason, and every
    other fact still answers."""
    given = ServedMeddra.named_groups
    monkeypatch.setattr(
        ServedMeddra,
        "named_groups",
        lambda self, key: ["No such SMQ"] if key == "pregnancy_smq" else given(self, key),
    )
    got = facts()
    for event in got["events"]:
        assert event["pregnancy"] is None
        assert "pregnancy-cases" in event["why"]["pregnancy"]
        assert "No such SMQ" in event["why"]["pregnancy"]
    assert event_of(got, "Drug ineffective")["not_medical"] is True
    assert event_of(got, "Headache")["not_medical"] is False


def test_a_groups_file_with_no_smq_makes_only_the_pregnancy_fact_null(facts, monkeypatch):
    """A release whose groups file came before the SMQ moved there."""
    given = ServedMeddra.named_groups
    monkeypatch.setattr(
        ServedMeddra,
        "named_groups",
        lambda self, key: None if key == "pregnancy_smq" else given(self, key),
    )
    got = facts()
    for event in got["events"]:
        assert event["pregnancy"] is None
        assert "pregnancy-cases" in event["why"]["pregnancy"]
    assert event_of(got, "Headache")["not_medical"] is False


def test_a_scope_or_sub_smqs_the_explorer_cannot_read_still_refuses(facts, tmp_path):
    """Not a name a new MedDRA version can move: these are the rule's own mistakes."""
    for values in ({"scope": "wide"}, {"sub_smqs": "apart"}):
        with rules_with(tmp_path, {"pregnancy-cases": values}):
            assert "pregnancy-cases" in facts(status=400)["problem"]


# not a medical event ------------------------------------------------------------------------


def test_a_term_is_not_a_medical_event_by_its_class_its_group_or_its_name(facts):
    got = facts()
    for name, why in {
        "Product quality issue": "its system organ class, on the licensed list",
        "Social issue": "its system organ class, on the licensed list",
        "Procedural pain": "its system organ class, on the licensed list",
        "Off label use": "its high level group term, on the licensed list",
        "Wrong drug administered": "its high level group term, on the licensed list",
        "Drug ineffective": "its name, on the public list",
    }.items():
        assert event_of(got, name)["not_medical"] is True, why
    for name in (EVENT, "Pregnancy", "Headache"):
        assert event_of(got, name)["not_medical"] is False, name


def test_a_group_of_the_licensed_list_may_be_a_high_level_term(facts, monkeypatch):
    event = "Off label use"
    monkeypatch.setattr(ServedMeddra, "named_groups", lambda self, key: [HLT])
    assert event_of(facts(), event)["not_medical"] is True
    assert event_of(facts(), "Headache")["not_medical"] is False


def test_a_lower_level_term_counts_as_the_preferred_term_that_holds_it(facts, tmp_path):
    """FDA's older wording reads to today's PT, the one the rule names; naming the lower level
    term itself is a name the version does not hold as a PT, since no event is counted under it."""
    assert event_of(facts(), "Therapeutic product effect incomplete")["not_medical"] is True
    with rules_with(tmp_path, {"not-a-medical-event": {"pts": ["Drug effect incomplete"]}}):
        why = event_of(facts(), "Headache")["why"]["not_medical"]
    assert "not-a-medical-event" in why and "drug effect incomplete" in why


def assert_only_the_mark_is_null(got: dict, whole: dict, *words: str) -> None:
    """Never "is a medical event", and never a refused page: every event's mark is null, its
    reason says why, and every other fact still answers."""
    assert got["events"]
    for event in got["events"]:
        assert event["not_medical"] is None
        assert all(w in event["why"]["not_medical"] for w in words)
    assert event_of(got, "Pregnancy")["pregnancy"] == event_of(whole, "Pregnancy")["pregnancy"]
    assert got["drug"] == whole["drug"]


def test_a_preferred_term_the_version_does_not_hold_makes_only_the_mark_null(facts, tmp_path):
    whole = facts()
    with rules_with(tmp_path, {"not-a-medical-event": {"pts": ["No such name"]}}):
        got = facts()
    assert_only_the_mark_is_null(got, whole, "not-a-medical-event", "pts", "no such name")


def test_a_group_the_version_does_not_hold_makes_only_the_mark_null(facts, monkeypatch):
    whole = facts()
    given = ServedMeddra.named_groups
    monkeypatch.setattr(
        ServedMeddra,
        "named_groups",
        lambda self, key: given(self, key) if key == "pregnancy_smq" else ["No such name"],
    )
    assert_only_the_mark_is_null(facts(), whole, "not-a-medical-event", "no such name")


def test_with_no_licensed_list_only_the_public_list_applies_and_the_answer_says_so(
    facts, monkeypatch
):
    monkeypatch.setattr(ServedMeddra, "named_groups", lambda self, key: None)
    got = facts()
    on_the_list = event_of(got, "Drug ineffective")
    assert on_the_list["not_medical"] is True
    assert "public list" in on_the_list["why"]["not_medical"]
    for name in ("Off label use", "Headache"):  # a group not read says nothing either way
        assert event_of(got, name)["not_medical"] is None, name
        assert "public list" in event_of(got, name)["why"]["not_medical"]


def test_without_meddra_only_the_public_list_applies_and_the_answer_says_so(
    hooked, facts_release, ask
):
    words = "MedDRA is not part of this plan."
    web = hooked(
        viewer=Viewer(id="v", meddra=False, who=False, why_no_smqs=words),
        release_dir=facts_release,
    )
    got = ask(web, "/api/events/facts", product=DRUG)
    on_the_list = event_of(got, "Drug ineffective")
    assert on_the_list["not_medical"] is True
    assert "public list" in on_the_list["why"]["not_medical"]
    for event in got["events"]:
        assert event["not_medical"] is not False, event["event"]
        assert words in event["why"]["not_medical"]
    assert event_of(got, "Off label use")["not_medical"] is None


# the treated condition and the indication ---------------------------------------------------


def test_an_event_the_label_flags_as_the_treated_disease_is_marked_treated(facts):
    got = facts()
    assert event_of(got, EVENT)["treated"] is True
    unflagged = event_of(got, "Drug ineffective")
    assert unflagged["treated"] is None and "no flag" in unflagged["why"]["treated"]


def test_a_drug_without_a_label_answers_null_not_false(label_client, ask):
    got = ask(label_client, "/api/events/facts", product="ibuprofen")
    assert {e["treated"] for e in got["events"]} == {None}
    assert all("no label" in e["why"]["treated"] for e in got["events"])


def test_a_drug_with_a_label_answers_false_for_an_event_its_flag_does_not_call_treated(
    label_client, ask
):
    got = ask(label_client, "/api/events/facts", product="warfarin")
    assert False in {e["treated"] for e in got["events"]}


def test_the_indication_matches_among_the_cases_that_give_one(facts):
    got = event_of(facts(), EVENT)
    # three cases: one gives the event as the indication, one another, one none
    assert (got["indication_cases"], got["indication_match"]) == (2, 0.5)


def test_an_event_not_marked_treated_has_no_indication_share(facts, tmp_path):
    with rules_with(tmp_path, {"treated-condition": {"outcome": "on_label"}}):
        got = event_of(facts(), EVENT)
    assert got["treated"] is False
    assert got["indication_match"] is None and got["indication_cases"] is None
    assert "not marked" in got["why"]["indication_match"]
    unsettled = event_of(facts(), "Drug ineffective")  # no flag at all: not compared
    assert unsettled["treated"] is None and unsettled["indication_match"] is None


def test_no_case_giving_an_indication_answers_null_not_zero(facts):
    got = event_of(facts(age="2-11"), EVENT)  # the one child's case, which gives none
    assert got["cases"] == 1
    assert (got["indication_cases"], got["indication_match"]) == (0, None)
    assert "No case gives an indication" in got["why"]["indication_match"]


# without MedDRA -----------------------------------------------------------------------------


def test_a_release_without_meddra_answers_the_licensed_facts_null_with_the_reason(client, ask):
    got = ask(client, "/api/events/facts", product="acetylsalicylic acid")
    assert got["events"]
    for event in got["events"]:
        assert event["pregnancy"] is None and event["not_medical"] is None
        assert event["why"]["pregnancy"] == LOCAL.why_no_smqs
        assert LOCAL.why_no_smqs in event["why"]["not_medical"]
        assert event["cases"] and event["aged"] is not None


def test_a_viewer_without_meddra_is_given_the_licensed_facts_null_with_the_hooks_words(
    hooked, facts_release, ask
):
    words = "MedDRA is not part of your plan."
    viewer = Viewer(id="v", meddra=False, who=False, why_no_smqs=words)
    web = hooked(viewer=viewer, release_dir=facts_release)
    got = event_of(ask(web, "/api/events/facts", product=DRUG), EVENT)
    assert (got["pregnancy"], got["not_medical"], got["indication_match"]) == (None, None, None)
    assert got["why"]["pregnancy"] == words and words in got["why"]["not_medical"]
    assert got["treated"] is True  # the label flag is not MedDRA's
