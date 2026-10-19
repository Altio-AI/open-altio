"""Each drug, route group and reaction gets one outcome and its expectedness (rules
label-flags, label-umbrella, label-treated-disease, label-not-a-medical-event and
label-procedure). The comparison is a plain function, so these tests give it invented
codes directly."""

from __future__ import annotations

from datetime import date

from open_altio import rulebook
from open_altio.faers.labeldict.flags import FLAG_COLUMNS, Label, Meddra, compare

MOUTH, INJECTED = "by_mouth", "injected"
LABELS = {
    ("1", MOUTH): Label("set-a", date(2025, 6, 1)),
    ("1", INJECTED): Label("set-b", date(2026, 1, 15)),
    ("3", MOUTH): Label("set-c", date(2024, 2, 1)),
    ("3", INJECTED): Label("set-d", date(2024, 3, 1)),
    ("4", INJECTED): Label("set-e", date(2023, 5, 1)),
    ("5", MOUTH): Label("set-f", date(2022, 1, 1)),
    ("5", "vaginal"): Label("set-g", date(2022, 2, 1)),
    ("5", INJECTED): Label("set-h", date(2022, 3, 1)),
}
UNKNOWN = rulebook.value("label-flags", "unknown_family")
# reaction text as the explorer normalises it -> current PT code; "old term" is an LLT
# of P2 today, as reac_meddra_T maps it; "unknown" maps to nothing
REACTION_PT = {
    "nausea": "P1",
    "headache": "P2",
    "old term": "P2",
    "vomiting": "P3",
    "vomiting aggravated": "P3",
    "vomiting-related death": "P3",
    "bleeding": "P4",
    "rash": "P5",
    "site reaction": "P6",
    "site pain": "P10",
    "site necrosis": "P7",
    "liver transplant": "P8",
    "drug ineffective": "P9",
    "itch": "P12",
    "unknown": None,
}
MEDDRA = Meddra(
    reaction_pt=REACTION_PT,
    primary_hlt={
        "P1": "H1",
        "P3": "H1",
        "P2": "H2",
        "P4": "H3",
        "P5": "H4",
        "P6": "H5",
        "P7": "H5",
        "P10": "H5",
        "P12": "H4",
    },
    umbrella_hlt={"P6": "H5"},
    severe={"P7"},
    not_medical={"P9", "P8"},
    procedures={"P8"},
)


def term(set_id, section, pt, kept, decided_by="rule"):
    return {
        "set_id": set_id,
        "section": section,
        "pt_code": pt,
        "kept": kept,
        "decided_by": decided_by if kept is not None else None,
    }


TERMS = [
    term("set-a", "adverse_reactions", "P2", True),
    term("set-a", "boxed_warning", "P2", True),
    term("set-a", "adverse_reactions", "P1", True),
    term("set-a", "warnings_and_precautions", "P4", False),
    term("set-a", "contraindications", "P5", None),
    term("set-a", "indications", "P3", True),
    term("set-b", "adverse_reactions", "P5", True, "reviewer"),
    term("set-b", "adverse_reactions", "P3", True, "model suggestion"),
    term("set-b", "adverse_reactions", "P6", True),
    term("set-e", "adverse_reactions", "P2", True),
    term("set-f", "adverse_reactions", "P2", True),
    term("set-g", "adverse_reactions", "P2", True),
]


def flags(*pairs, terms=TERMS):
    got = compare(pairs, labels=LABELS, terms=terms, meddra=MEDDRA)
    return {(f["rxcui"], f["route_families"], f["pt"]): f for f in got}


def outcome(rxcui, route, pt, **kw):
    return flags((rxcui, route, pt), **kw)[(rxcui, route, pt)]


def test_on_label_names_the_first_section_in_the_rules_order_and_the_label():
    flag = outcome("1", MOUTH, "Headache")
    assert (flag["outcome"], flag["expectedness"]) == ("on_label", "expected")
    assert flag["section"] == "boxed_warning"
    assert (flag["set_id"], flag["label_date"], flag["decided_by"]) == (
        "set-a",
        date(2025, 6, 1),
        "rule",
    )
    assert rulebook.value("label-flags", "section_order")[0] == "boxed_warning"


def test_one_sentence_keeping_a_term_off_never_cancels_another_that_names_it():
    terms = TERMS + [term("set-a", "adverse_reactions", "P4", True)]
    assert outcome("1", MOUTH, "Bleeding", terms=terms)["outcome"] == "on_label"


def test_an_old_term_is_compared_as_its_current_pt():
    assert outcome("1", MOUTH, "OLD  TERM")["outcome"] == "on_label"


def test_an_umbrella_term_covers_the_milder_terms_under_it():
    flag = outcome("1", INJECTED, "Site pain")
    assert (flag["outcome"], flag["decided_by"]) == ("on_label", "rule: umbrella")
    assert flag["expectedness"] == "expected"


def test_a_severe_form_under_an_umbrella_is_related_not_on_label():
    flag = outcome("1", INJECTED, "Site necrosis")
    assert (flag["outcome"], flag["expectedness"]) == ("related", "unexpected")
    assert outcome("1", MOUTH, "Site pain")["outcome"] == "not_on_label"  # no umbrella


def test_related_when_a_kept_pt_shares_the_primary_group_and_it_names_no_group():
    flag = outcome("1", INJECTED, "Nausea")
    assert flag["outcome"] == "related" and flag["section"] is None
    assert "H1" not in flag.values() and flag["decided_by"] == "model_suggested"


def test_not_on_label_when_the_label_keeps_the_pt_off_or_never_names_it():
    assert outcome("1", MOUTH, "Bleeding")["outcome"] == "not_on_label"
    flag = outcome("1", INJECTED, "Headache")
    assert (flag["outcome"], flag["expectedness"]) == ("not_on_label", "unexpected")


def test_uncertain_when_only_an_uncoded_phrase_names_the_pt():
    flag = outcome("1", MOUTH, "Rash")
    assert (flag["outcome"], flag["expectedness"]) == ("uncertain", "unexpected")


def test_an_uncertain_pt_nearby_does_not_make_a_pair_uncertain():
    terms = [term("set-a", "adverse_reactions", "P1", None)]
    assert outcome("1", MOUTH, "Vomiting", terms=terms)["outcome"] == "not_on_label"


def test_uncertain_when_the_reaction_text_maps_to_no_pt():
    assert outcome("1", MOUTH, "Unknown")["outcome"] == "uncertain"
    assert outcome("1", MOUTH, "Never seen")["outcome"] == "uncertain"


def test_no_label_for_a_drug_without_one():
    flag = outcome("2", MOUTH, "Nausea")
    assert (flag["outcome"], flag["expectedness"]) == ("no_label", "unexpected")
    assert flag["set_id"] is None


def test_a_record_read_on_its_own_familys_label_says_so():
    flag = outcome("1", MOUTH, "Headache")
    assert (flag["judged_on"], flag["family_outcomes"]) == (MOUTH, None)


def test_a_family_with_no_label_of_its_own_is_read_like_an_unknown_family():
    flag = outcome("1", "skin", "Nausea")  # by mouth on the label, injected only nearby
    assert (flag["outcome"], flag["route_families"]) == ("forms_differ", "skin")
    assert flag["judged_on"] == "by_mouth; injected"
    assert flag["family_outcomes"] == "by_mouth: on_label; injected: related"


def test_the_one_label_of_another_family_decides_and_says_which():
    flag = outcome("4", MOUTH, "Headache")  # only an injection label: no label for tablets
    assert (flag["outcome"], flag["judged_on"], flag["set_id"]) == ("on_label", INJECTED, "set-e")
    assert flag["family_outcomes"] == "injected: on_label"


def test_an_unknown_family_takes_the_outcome_every_familys_label_agrees_on():
    terms = TERMS + [term("set-b", "adverse_reactions", "P2", True)]
    flag = outcome("1", UNKNOWN, "Headache", terms=terms)
    assert (flag["outcome"], flag["route_families"]) == ("on_label", UNKNOWN)
    assert flag["family_outcomes"] == "by_mouth: on_label; injected: on_label"
    assert flag["set_id"] is None and flag["judged_on"] == "by_mouth; injected"  # two labels


def test_an_unknown_family_whose_labels_differ_is_forms_differ_with_the_split():
    flag = outcome("1", UNKNOWN, "Headache")
    assert (flag["outcome"], flag["expectedness"]) == ("forms_differ", "unexpected")
    assert flag["family_outcomes"] == "by_mouth: on_label; injected: not_on_label"


def test_an_unknown_family_whose_labels_are_all_unexpected_takes_the_closest_outcome():
    flag = outcome("1", UNKNOWN, "Itch")  # by mouth: nothing near; injected: rash nearby
    assert (flag["outcome"], flag["expectedness"]) == ("related", "unexpected")
    assert flag["family_outcomes"] == "by_mouth: not_on_label; injected: related"
    assert (flag["judged_on"], flag["set_id"]) == (INJECTED, "set-b")
    terms = [term("set-c", "adverse_reactions", "P5", None)]
    flag = outcome("3", UNKNOWN, "Rash", terms=terms)
    assert flag["outcome"] == "uncertain"
    assert flag["family_outcomes"] == "by_mouth: uncertain; injected: not_on_label"


def test_an_unknown_family_is_plain_uncertain_only_when_nothing_is_known():
    terms = [
        term("set-c", "adverse_reactions", "P5", None),
        term("set-d", "adverse_reactions", "P5", None),
    ]
    assert outcome("3", UNKNOWN, "Rash", terms=terms)["outcome"] == "uncertain"
    assert outcome("2", UNKNOWN, "Rash")["outcome"] == "no_label"
    assert outcome("2", UNKNOWN, "Drug ineffective")["outcome"] == "not_a_medical_event"


def test_a_procedure_comes_first_and_reads_as_unexpected():
    """Not compared with the label, yet unexpected: it can be the only trace of harm."""
    terms = TERMS + [term("set-a", "adverse_reactions", "P8", True)]
    flag = outcome("1", MOUTH, "Liver transplant", terms=terms)
    assert (flag["outcome"], flag["expectedness"]) == ("procedure", "unexpected")
    assert outcome("2", MOUTH, "Liver transplant")["outcome"] == "procedure"


def test_not_a_medical_event_comes_before_the_label_and_is_set_aside():
    terms = TERMS + [term("set-a", "indications", "P9", True)]
    flag = outcome("1", MOUTH, "Drug ineffective", terms=terms)
    assert (flag["outcome"], flag["expectedness"]) == (
        "not_a_medical_event",
        "set_aside",
    )
    assert outcome("2", MOUTH, "Drug ineffective")["outcome"] == "not_a_medical_event"


def test_the_disease_the_indications_name_is_its_own_outcome_never_on_label():
    terms = TERMS + [term("set-a", "adverse_reactions", "P3", True)]
    flag = outcome("1", MOUTH, "Vomiting", terms=terms)
    assert (flag["outcome"], flag["expectedness"]) == ("treated_disease", "set_aside")
    assert flag["set_id"] == "set-a" and flag["section"] is None


def test_a_worse_form_of_the_disease_treated_is_compared_like_any_other_event():
    for text in ("Vomiting aggravated", "Vomiting-related death"):
        # compared with the safety sections: nausea, in the same group, is kept there
        assert outcome("1", MOUTH, text)["outcome"] == "related", text
    assert outcome("1", MOUTH, "Vomiting")["outcome"] == "treated_disease"
    words = rulebook.value("label-treated-disease", "worsening_words")
    assert "aggravated" in words and "related death" in words


def test_the_route_picks_its_own_label():
    flag = outcome("1", INJECTED, "Rash")
    assert (flag["outcome"], flag["decided_by"]) == ("on_label", "model_reviewed")


def test_a_rule_row_wins_over_a_persons_and_a_persons_over_a_suggestion():
    terms = [
        term("set-a", "adverse_reactions", "P1", True, "model suggestion"),
        term("set-a", "adverse_reactions", "P1", True, "reviewer"),
    ]
    assert outcome("1", MOUTH, "Nausea", terms=terms)["decided_by"] == "model_reviewed"


def test_every_flag_has_the_agreed_columns_and_a_known_outcome_and_expectedness():
    every = flags(*[("1", r, p) for r in (MOUTH, INJECTED) for p in REACTION_PT])
    outcomes = set(rulebook.value("label-flags", "outcomes"))
    expectedness = rulebook.value("label-flags", "expectedness")
    deciders = set(rulebook.value("label-flags", "decided_by").values())
    assert set(expectedness) == outcomes
    for flag in every.values():
        assert tuple(flag) == FLAG_COLUMNS
        assert flag["outcome"] in outcomes and flag["decided_by"] in deciders
        assert flag["expectedness"] == expectedness[flag["outcome"]]


# a record's candidate families ------------------------------------------------------


def test_several_candidate_families_read_only_their_own_labels():
    flag = outcome("5", "by_mouth;vaginal", "Headache")  # the injected label lacks it
    assert (flag["outcome"], flag["judged_on"]) == ("on_label", "by_mouth; vaginal")
    assert flag["family_outcomes"] == "by_mouth: on_label; vaginal: on_label"


def test_several_candidates_whose_labels_differ_are_forms_differ_among_them():
    flag = outcome("5", "injected;vaginal", "Headache")
    assert (flag["outcome"], flag["judged_on"]) == ("forms_differ", "injected; vaginal")


def test_a_candidate_family_with_no_label_makes_every_label_read():
    flag = outcome("5", "by_mouth;under_tongue", "Headache")  # no label under the tongue
    assert (flag["outcome"], flag["judged_on"]) == ("forms_differ", "by_mouth; injected; vaginal")


def test_no_candidate_families_reads_every_label():
    for nothing in ("", UNKNOWN):
        flag = outcome("5", nothing, "Headache")
        assert (flag["outcome"], flag["judged_on"]) == (
            "forms_differ",
            "by_mouth; injected; vaginal",
        )
        assert flag["route_families"] == nothing


def test_one_certain_family_with_a_label_reads_only_that_label():
    flag = outcome("5", INJECTED, "Headache")
    assert (flag["outcome"], flag["judged_on"], flag["set_id"]) == (
        "not_on_label",
        INJECTED,
        "set-h",
    )
    assert flag["family_outcomes"] is None


def test_one_label_serving_several_families_is_one_label_and_names_them():
    shared = Label("set-k", date(2021, 1, 1))
    labels = {**LABELS, ("6", INJECTED): shared, ("6", "other"): shared}
    terms = TERMS + [term("set-k", "adverse_reactions", "P2", True)]
    got = compare([("6", "injected;other", "Headache")], labels=labels, terms=terms, meddra=MEDDRA)
    assert (got[0]["outcome"], got[0]["set_id"], got[0]["judged_on"]) == (
        "on_label",
        "set-k",
        "injected; other",
    )
    # a record of one of its families reads the same label
    got = compare([("6", "other", "Headache")], labels=labels, terms=terms, meddra=MEDDRA)
    assert (got[0]["set_id"], got[0]["judged_on"]) == ("set-k", "other")


def test_a_record_with_no_rxnorm_code_has_no_label_unless_its_term_decides():
    flag = outcome(None, MOUTH, "Nausea")
    assert (flag["outcome"], flag["set_id"], flag["judged_on"]) == ("no_label", None, None)
    assert outcome(None, "", "Drug ineffective")["outcome"] == "not_a_medical_event"
    assert outcome(None, MOUTH, "Unknown")["outcome"] == "uncertain"


def test_a_catch_all_group_never_makes_a_pair_related():
    catch_all = Meddra(**{**MEDDRA.__dict__, "catch_all": {"H1"}})
    got = compare([("1", INJECTED, "Nausea")], labels=LABELS, terms=TERMS, meddra=catch_all)
    assert (got[0]["outcome"], got[0]["expectedness"]) == ("not_on_label", "unexpected")
    assert outcome("1", INJECTED, "Nausea")["outcome"] == "related"  # the same pair otherwise
