"""Which terms a label keeps, keeps off or leaves uncertain (rules label-negation,
label-population, label-table-rows, label-dictionary and label-treated-disease).

Each test codes a few invented label lines with the invented MedDRA terms of
open_altio.testing.fakemeddra and reads back each term's verdict."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.faers.labeldict.coding import (
    ITEM_FIELDS,
    Coded,
    LabelCoder,
    LabelInfo,
    SectionRow,
    item_id,
)
from open_altio.faers.labeldict.terms import Term
from open_altio.rulebook import UserRules
from open_altio.testing.fakemeddra import current_llts
from open_altio.testing.rules import rules_with

HEADING = "Invented kidney and headache disorders"
INFO = LabelInfo("900009", "inventamab", "2025-06-01")


@pytest.fixture(scope="module")
def coder() -> LabelCoder:
    return LabelCoder([Term(*t) for t in current_llts("29.1")], [HEADING])


def code(coder, *lines, section="warnings_and_precautions", table=False) -> Coded:
    rows = [SectionRow("set-x", section, n, table, text) for n, text in enumerate(lines)]
    coded = Coded()
    coder.code(rows, {"set-x": INFO}, coded)
    return coded


def verdicts(coded: Coded) -> list[tuple[str, bool | None, str]]:
    return [(r["matched_text"], r["kept"], r["rule"]) for r in coded.terms]


def test_a_term_no_rule_touches_is_kept_by_rule(coder):
    coded = code(coder, "Headache occurred in 5% of patients.")
    assert verdicts(coded) == [("Headache", True, "label-dictionary")]
    assert coded.terms[0]["decided_by"] == "rule" and coded.terms[0]["item_id"] is None


# negation ----------------------------------------------------------------------------


def test_a_phrase_before_keeps_the_whole_list_off(coder):
    coded = code(coder, "No cases of haemorrhage, headache or vomiting were reported.")
    assert [k for _, k, _ in verdicts(coded)] == [False, False, False]
    assert {r for _, _, r in verdicts(coded)} == {"label-negation"}


def test_a_phrase_after_keeps_the_terms_just_before_it_off(coder):
    assert verdicts(code(coder, "Haemorrhage was not observed.")) == [
        ("Haemorrhage", False, "label-negation")
    ]


def test_negation_stops_where_the_list_stops(coder):
    coded = code(
        coder,
        "Nausea was common, but haemorrhage was not observed.",
        "Nausea was common, haemorrhage was not observed.",
        "No cases of haemorrhage were reported, and nausea was common.",
    )
    assert [(m, k) for m, k, _ in verdicts(coded)] == [
        ("Nausea", True),
        ("haemorrhage", False),
        ("Nausea", True),
        ("haemorrhage", False),
        ("haemorrhage", False),
        ("nausea", True),
    ]


def test_a_phrase_after_keeps_a_listed_term_with_its_own_modifier_off(coder):
    coded = code(coder, "Haemorrhage, severe headache and nausea were not observed.")
    assert [k for _, k, _ in verdicts(coded)] == [False, False, False]


def test_a_phrase_too_far_from_the_term_does_not_reach_it(coder):
    window = rulebook.value("label-negation", "window_words")
    far = " ".join(["very"] * (window + 1))
    assert verdicts(code(coder, f"No cases of {far} haemorrhage were reported."))[0][1] is True


def test_an_unread_negation_word_just_before_makes_the_term_uncertain(coder):
    coded = code(coder, "Patients did not report haemorrhage, which was seen.")
    assert verdicts(coded) == [("haemorrhage", None, "label-negation")]
    (item,) = coded.items.values()
    assert item["candidate_pt"] == "Haemorrhage" and item["why_uncertain"]


# populations -------------------------------------------------------------------------


def test_a_population_phrase_keeps_the_condition_off_and_not_the_reaction(coder):
    coded = code(
        coder,
        "Contraindicated in patients with renal failure.",
        "Patients with a history of renal failure or headache developed nausea.",
    )
    assert [(m, k) for m, k, _ in verdicts(coded)] == [
        ("renal failure", False),
        ("renal failure", False),
        ("headache", False),
        ("nausea", True),
    ]


def test_a_term_describing_the_people_and_a_test_for_a_condition_are_kept_off(coder):
    coded = code(
        coder,
        "Nausea occurred in 3% of headache patients.",
        "Patients should be tested for renal failure before use.",
    )
    assert [(m, k) for m, k, _ in verdicts(coded)] == [
        ("Nausea", True),
        ("headache", False),
        ("renal failure", False),
    ]


def test_modifiers_within_the_window_still_count(coder):
    assert verdicts(code(coder, "Monitor patients with severe renal failure."))[0][1] is False


def test_a_term_after_a_bare_comma_is_uncertain_unless_the_list_goes_on(coder):
    coded = code(
        coder,
        "In patients with renal failure, nausea may be reported.",
        "In patients with renal failure, headache, or nausea, monitor closely.",
    )
    assert [(m, k) for m, k, _ in verdicts(coded)] == [
        ("renal failure", False),
        ("nausea", None),
        ("renal failure", False),
        ("headache", False),
        ("nausea", False),
    ]


def test_every_contraindication_hit_is_a_population_and_never_uncertain(coder):
    coded = code(
        coder,
        "Severe nausea.",
        "Patients did not report haemorrhage, which was seen.",
        "Lead was measured.",
        section="contraindications",
    )
    assert [(m, k, r) for m, k, r in verdicts(coded)] == [
        ("nausea", False, "label-population"),
        ("haemorrhage", False, "label-population"),
        ("Lead", False, "label-population"),
    ]
    assert coded.items == {}
    table = code(
        coder,
        *TABLE,
        "Headache | 12 (3%) | 4 (1%)",
        section="contraindications",
        table=True,
    )
    assert [k for _, k, _ in verdicts(table)] == [False]
    assert rulebook.value("label-population", "population_sections") == ["contraindications"]


# the term's own words ----------------------------------------------------------------


def test_boilerplate_and_headings_are_kept_off(coder):
    llts = current_llts("29.1") + [("97000020", "Adverse reaction", "97000020", "Adverse reaction")]
    coded = Coded()
    LabelCoder([Term(*t) for t in llts], [HEADING]).code(
        [
            SectionRow("s", "adverse_reactions", 1, False, "Adverse reaction rates vary."),
            SectionRow("s", "adverse_reactions", 2, False, f"Under {HEADING.lower()} we list."),
        ],
        {},
        coded,
    )
    assert [(r["matched_text"], r["kept"]) for r in coded.terms] == [
        ("Adverse reaction", False),
        ("headache", False),
    ]


def test_a_cross_reference_names_another_part_of_the_label(coder):
    coded = code(coder, "Nausea occurred [see Headache and Vomiting (5.1)] in 2%.")
    assert [(m, k) for m, k, _ in verdicts(coded)] == [
        ("Nausea", True),
        ("Headache", False),
        ("Vomiting", False),
    ]


def test_a_mark_in_a_name_must_be_in_the_text_and_a_one_letter_name_never_matches():
    terms = [
        Term("97000030", "Mg++", "97000031", "Blood magnesium"),
        Term("97000032", "K", "97000033", "Blood potassium"),
    ]
    coder = LabelCoder(terms, [])
    assert code(coder, "Take 10 mg daily with vitamin K.").terms == []
    assert len(code(coder, "Mg++ was low.").terms) == 1
    assert rulebook.value("label-dictionary", "shortest_name") > 1


def test_an_everyday_word_is_kept_off_in_its_everyday_sense_and_uncertain_otherwise(
    coder,
):
    coded = code(coder, "Renal failure may lead to dialysis.", "Lead was measured.")
    assert [(m, k) for m, k, _ in verdicts(coded)] == [
        ("Renal failure", True),
        ("lead", False),
        ("Lead", None),
    ]


# tables ------------------------------------------------------------------------------

TABLE = [" | Drug 10 mg | Placebo"]


def table_verdicts(coder, *rows):
    coded = code(coder, *TABLE, *rows, section="adverse_reactions", table=True)
    return [(r["matched_text"], r["kept"]) for r in coded.terms], coded


def test_a_row_where_the_drug_has_it_is_kept(coder):
    assert table_verdicts(coder, "Headache | 12 (3%) | 4 (1%)", "Nausea | <1 | 0")[0] == [
        ("Headache", True),
        ("Nausea", True),
    ]


def test_a_row_where_only_placebo_has_it_is_kept_off(coder):
    got, coded = table_verdicts(coder, "Vomiting | 0 | 2 (0.5%)")
    assert got == [("Vomiting", False)] and coded.terms[0]["rule"] == "label-table-rows"


def test_a_row_that_cannot_be_read_is_uncertain(coder):
    got, coded = table_verdicts(coder, "Nausea | 3% | 0 | 1%", "Vomiting | 0 | 0")
    assert got == [("Nausea", None), ("Vomiting", None)]
    assert len(coded.items) == 2


def test_a_row_with_every_value_above_zero_is_kept_however_it_lines_up(coder):
    assert table_verdicts(coder, "Nausea | 3%", "Headache | 2 | 1 | 4")[0] == [
        ("Nausea", True),
        ("Headache", True),
    ]


def test_a_table_with_no_comparator_keeps_every_row(coder):
    coded = code(
        coder,
        " | 10 mg | 20 mg",
        "Vomiting | 0 | 2",
        section="adverse_reactions",
        table=True,
    )
    assert verdicts(coded) == [("Vomiting", True, "label-table-rows")]


def test_a_row_with_no_values_is_read_as_a_sentence(coder):
    got, _ = table_verdicts(coder, "No cases of haemorrhage were seen in the trial.")
    assert got == [("haemorrhage", False)]


def test_a_row_naming_no_term_is_an_uncertain_item_with_no_candidate(coder):
    _, coded = table_verdicts(coder, "Injection site wheal | 20% | 14%")
    (item,) = coded.items.values()
    assert item["candidate_pt"] is None and item["sentence"].startswith("Injection site wheal")
    assert coded.terms == []


# indications -------------------------------------------------------------------------


def test_indications_name_the_disease_treated_without_population_rules(coder):
    coded = code(
        coder,
        "Indicated for the treatment of headache in adults with nausea.",
        "Not indicated for the treatment of vomiting.",
        section=rulebook.value("label-treated-disease", "indications_section"),
    )
    assert verdicts(coded) == [
        ("headache", True, "label-treated-disease"),
        ("nausea", True, "label-treated-disease"),
        ("vomiting", False, "label-negation"),
    ]
    assert coded.items == {}


def test_nothing_in_the_indications_is_left_uncertain_or_taken_as_the_disease_on_a_guess(coder):
    indications = rulebook.value("label-treated-disease", "indications_section")
    coded = code(coder, "Indicated for headache.", "Lead was measured.", section=indications)
    assert verdicts(coded) == [
        ("headache", True, "label-treated-disease"),
        ("Lead", False, "label-treated-disease"),
    ]
    rows = code(coder, *TABLE, "Nausea | 3% | 0 | 1%", section=indications, table=True)
    assert verdicts(rows) == [("Nausea", False, "label-treated-disease")]
    assert coded.items == rows.items == {}
    # the same lines elsewhere are uncertain items
    assert code(coder, "Lead was measured.").items
    elsewhere = code(coder, *TABLE, "Nausea | 3% | 0 | 1%", section="adverse_reactions", table=True)
    assert elsewhere.items


def test_sections_the_rules_do_not_read_are_skipped(coder):
    assert code(coder, "Headache occurred.", section="dosage_and_administration").terms == []


# uncertain items ---------------------------------------------------------------------


def test_an_uncertain_item_has_the_agreed_fields_and_a_stable_id(coder):
    first = code(coder, "Patients did not report haemorrhage, which was seen.")
    again = code(coder, "Patients did not report haemorrhage, which was seen.")
    (item,) = first.items.values()
    assert tuple(item) == ITEM_FIELDS
    assert (item["rxcui"], item["drug"], item["label_date"]) == (
        "900009",
        "inventamab",
        "2025-06-01",
    )
    assert item["rank"] is None and first.items.keys() == again.items.keys()
    assert first.terms[0]["item_id"] == item["item_id"]
    assert item_id("a", "b", "c", "d", "e") != item_id("a", "b", "c", "d", "f")


def test_a_changed_rule_value_changes_the_verdict(coder, tmp_path):
    with rules_with(tmp_path, {"label-population": {"population_sections": []}}):
        changed = LabelCoder([Term(*t) for t in current_llts("29.1")], [HEADING])
        assert verdicts(code(changed, "Severe nausea.", section="contraindications"))[0][1] is True


def test_a_rule_switched_off_keeps_nothing_off():
    off = UserRules(off=frozenset({"label-negation", "label-population", "label-treated-disease"}))
    with rulebook.use_user_rules(off):
        switched = LabelCoder([Term(*t) for t in current_llts("29.1")], [HEADING])
        coded = code(switched, "No cases of haemorrhage were reported.")
        assert verdicts(coded) == [("haemorrhage", True, "label-dictionary")]
        coded = code(
            switched, "Contraindicated in patients with renal failure.", section="contraindications"
        )
        assert verdicts(coded)[0][1] is True
        indications = rulebook.value("label-treated-disease", "indications_section")
        assert code(switched, "Indicated for headache.", section=indications).terms == []
