"""The label cards count the pairs the cases people see use, on small invented tables: a case
set aside as a duplicate, a trial product and a record whose code names another drug change
nothing a card counts wrongly, and the licensed table-rows card reads its own table."""

from __future__ import annotations

import duckdb
import pytest

from open_altio.faers.insights.cards import RULES_OF, rule_charts

K = "era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR"


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute(f"CREATE TABLE case_latest_T ({K}, dup_kept_T BOOLEAN)")
    c.execute(
        "INSERT INTO case_latest_T VALUES ('f','1','q',true), ('f','2','q',true), "
        "('f','3','q',false)"
    )
    c.execute(f"CREATE TABLE drug_latest_T ({K}, drug_seq VARCHAR, role_cod VARCHAR)")
    c.execute(
        "INSERT INTO drug_latest_T VALUES ('f','1','q','1','PS'), ('f','1','q','2','PS'), "
        "('f','2','q','1','SS'), ('f','2','q','2','PS'), ('f','3','q','1','PS')"
    )
    c.execute(f"CREATE TABLE drug_substance_T ({K}, drug_seq VARCHAR, diana_trial_T BOOLEAN)")
    c.execute(
        "INSERT INTO drug_substance_T VALUES ('f','1','q','1',false), ('f','1','q','2',false), "
        "('f','2','q','1',false), ('f','2','q','2',true), ('f','3','q','1',false)"
    )
    c.execute(f"CREATE TABLE drug_rxnorm_T ({K}, drug_seq VARCHAR, rxcui_T VARCHAR)")
    c.execute(
        "INSERT INTO drug_rxnorm_T VALUES ('f','1','q','1','10'), ('f','1','q','2','11'), "
        "('f','2','q','1','10'), ('f','2','q','2','12'), ('f','3','q','1','13')"
    )
    c.execute(f"CREATE TABLE drug_route_T ({K}, drug_seq VARCHAR, route_families_T VARCHAR)")
    c.execute(
        "INSERT INTO drug_route_T VALUES ('f','1','q','1','by_mouth'), ('f','1','q','2',NULL), "
        "('f','2','q','1','by_mouth'), ('f','2','q','2','by_mouth'), ('f','3','q','1','by_mouth')"
    )
    c.execute(f"CREATE TABLE label_other_drug_T ({K}, drug_seq VARCHAR)")
    c.execute("INSERT INTO label_other_drug_T VALUES ('f','2','q','1')")  # code names another drug
    c.execute(f"CREATE TABLE reac_latest_T ({K}, pt VARCHAR)")
    c.execute(
        "INSERT INTO reac_latest_T VALUES ('f','1','q','Headache'), ('f','1','q','Dialysis'), "
        "('f','2','q','Headache'), ('f','2','q','Rash'), ('f','3','q','Cough')"
    )
    c.execute(
        "CREATE TABLE label_flags_T (rxcui_T VARCHAR, route_families_T VARCHAR, pt_T VARCHAR, "
        "outcome_T VARCHAR, decided_by_T VARCHAR, section_T VARCHAR)"
    )
    c.execute(
        "INSERT INTO label_flags_T VALUES "
        "('10','by_mouth','Headache','on_label','rule','adverse_reactions'), "
        "('10','by_mouth','Dialysis','procedure','rule',NULL), "
        "('10','by_mouth','Rash','no_label','rule',NULL), "
        "('11','','Headache','treated_disease','rule',NULL), "
        "('11','','Dialysis','not_a_medical_event','rule',NULL), "
        "('','by_mouth','Headache','not_on_label','rule',NULL), "
        "('','by_mouth','Rash','on_label','rule: umbrella',NULL), "
        "('13','by_mouth','Cough','no_label','rule',NULL), "
        "('12','by_mouth','Rash','no_label','rule',NULL)"
    )
    return c


def test_pairs_are_those_of_shown_cases_without_trial_products(con):
    card = rule_charts.label_flags_given(con)
    # shown: case 1 (drugs 10 and 11, two reactions each) and case 2 (a record whose code names
    # another drug, read as no code; its trial product leaves out); case 3 is set aside
    assert card["numbers"] == {"pairs": 6, "on_label": 2, "umbrella": 1, "set_aside": 3}
    [line] = card["chart"]["series"]
    assert sum(line["values"]) == 6


def test_every_shown_pair_finds_its_flag(con):
    rule_charts._shown_pairs(con)
    assert con.execute("SELECT count(*) FROM shown_pairs_T WHERE outcome_T IS NULL").fetchone() == (
        0,
    )


def test_the_set_aside_cards_name_their_ten_commonest_reactions(con):
    for fn, pt in (
        (rule_charts.label_treated_disease, "Headache"),
        (rule_charts.label_not_a_medical_event, "Dialysis"),
        (rule_charts.label_procedure, "Dialysis"),
        (rule_charts.label_umbrella, "Rash"),
    ):
        card = fn(con)
        assert card["numbers"] == {"pairs": 1, "top_pairs": 1}, fn.__name__
        assert card["chart"]["x"]["values"] == [pt], fn.__name__


def test_the_dictionary_card_counts_listed_pairs_by_section_and_those_with_none(con):
    card = rule_charts.label_dictionary(con)
    assert card["numbers"] == {"pairs": 2, "no_section": 1}
    values = dict(
        zip(card["chart"]["x"]["values"], card["chart"]["series"][0]["values"], strict=True)
    )
    assert values["Adverse reactions"] == 1


def test_the_table_rows_card_counts_what_the_rule_did(con):
    con.execute("CREATE TABLE label_terms_T (rule_T VARCHAR, kept_T BOOLEAN)")
    con.execute(
        "INSERT INTO label_terms_T VALUES ('label-table-rows', true), ('label-table-rows', true), "
        "('label-table-rows', false), ('label-table-rows', NULL), ('label-dictionary', true)"
    )
    card = rule_charts.label_table_rows(con)
    assert card["numbers"] == {"kept": 2, "left_out": 1, "sent_to_person": 1}


def test_each_new_card_serves_exactly_its_own_rule():
    assert RULES_OF["label_flags_given"] == ["label-flags", "label-negation", "label-population"]
    assert RULES_OF["label_sections_read"] == ["label-sections"]
    for fn, rule in (
        ("label_treated_disease", "label-treated-disease"),
        ("label_not_a_medical_event", "label-not-a-medical-event"),
        ("label_procedure", "label-procedure"),
        ("label_umbrella", "label-umbrella"),
        ("label_dictionary", "label-dictionary"),
        ("label_table_rows", "label-table-rows"),
    ):
        assert RULES_OF[fn] == [rule]
