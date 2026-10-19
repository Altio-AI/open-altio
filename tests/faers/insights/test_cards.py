"""The insight cards: as the release carries them in methods.json, and as the notebooks compute
them from a release folder with the same functions."""

from __future__ import annotations

import warnings
from pathlib import Path

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers.insights.cards import (
    CARDS,
    LICENSED,
    MissingDataWarning,
    card_ids,
    compute_cards,
    empty_fields,
    rule_charts,
)
from open_altio.faers.insights.source import connect

ROOT = Path(__file__).resolve().parents[3]
CARD_IDS = {
    "sender_names_unstable",
    "rechal_filler",
    "occupation_code_changes",
    "deleted_lists_unpublished",
    "rept_cod_combination_products",
    "country_empty_rising",
    "carried_cases_counted_twice",
    "deleted_lists_name_aers_cases",
    "eras_write_countries_and_terms_differently",
    "same_event_several_cases",
    "one_case_two_numbers",
    "padded_dates_join_different_patients",
    "duplicate_check_needs_fields",
    "no_adverse_event_serious_outcome",
    "one_medicine_many_spellings",
    "background_drugs_counted_every_role",
    "brand_changes_ingredient",
    "unknown_written_two_ways",
    "to_mfr_filler_on_company_reports",
    "who_reported_lost_on_company_reports",
    "completeness_depends_on_sender",
    "european_union_for_member_state",
    "sex_not_specified_for_empty",
    "ages_without_a_unit",
    "older_meddra_terms_missed",
    "quarterly_files_keep_their_meddra_version",
    "unknown_indication_placeholder",
    "aspirin_dose_tells_the_use",
    "two_use_drug_use_not_said",
    "event_dates_padded",
    "padding_puts_reactions_before_drug",
    "no_outcome_not_non_serious",
    "drug_seq_repeated",
}
CARD_IDS |= {
    fn.__name__ for fn in rule_charts.CARDS
}  # the charts of the rules no notebook measured
# Notebook 02: the card behind each step its rules changed that removes cases.
NOTEBOOK_02 = {
    "carried_cases_counted_twice": "latest_versions",
    "deleted_lists_name_aers_cases": "after_deleted_lists",
    "eras_write_countries_and_terms_differently": "kept_after_duplicates",
}
# Notebook 04: three cards behind the duplicates step, two documented.
NOTEBOOK_04 = {
    "same_event_several_cases": "kept_after_duplicates",
    "one_case_two_numbers": "kept_after_duplicates",
    "padded_dates_join_different_patients": "kept_after_duplicates",
    "duplicate_check_needs_fields": None,
    "no_adverse_event_serious_outcome": None,
}

# Notebook 03: four cards behind rule not-given, which acts as FDA's rows are read.
NOTEBOOK_03 = [
    "unknown_written_two_ways",
    "to_mfr_filler_on_company_reports",
    "who_reported_lost_on_company_reports",
    "completeness_depends_on_sender",
]

# Notebook 08: three cards behind the dates and codes steps, which remove no case, three documented.
NOTEBOOK_08 = {
    "event_dates_padded": "dates",
    "padding_puts_reactions_before_drug": "dates",
    "occupation_code_changes": "codes",
    "rept_cod_combination_products": None,
    "no_outcome_not_non_serious": None,
    "drug_seq_repeated": None,
}


# Notebook 09: the cards behind the drug classes step.
NOTEBOOK_09 = ("aspirin_dose_tells_the_use", "two_use_drug_use_not_said")


def _card(methods: dict, card_id: str) -> dict:
    return next(c for c in methods["insights"] if c["id"] == card_id)


def test_every_card_is_in_the_release(methods):
    assert {c["id"] for c in methods["insights"]} == CARD_IDS - LICENSED


def test_card_ids_are_unique_and_named_by_their_function():
    assert len(set(card_ids())) == len(CARDS) == len(CARD_IDS)


def test_each_insight_has_two_sentences_and_a_tag(methods):
    labels = {
        "changed_pipeline": "Changed our pipeline",
        "documented": "Documented, not transformed",
    }
    for card in methods["insights"]:
        assert card["two_sentences"].count(". ") + 1 == 2, card["id"]
        assert card["tag"]["label"] == labels[card["tag"]["kind"]]
        assert (ROOT / card["notebook"]).is_file(), card["notebook"]


def test_changed_pipeline_tags_point_at_a_step_that_links_back(methods):
    steps = {s["id"]: s for s in methods["steps"]}
    changed = [c for c in methods["insights"] if c["tag"]["kind"] == "changed_pipeline"]
    assert changed, "at least one card changed the pipeline"
    for card in changed:
        assert card["tag"]["step"] in steps
        assert card["id"] in steps[card["tag"]["step"]]["insights"]
    insight_ids = {c["id"] for c in methods["insights"]}
    for step in methods["steps"]:
        for linked in step["insights"]:
            assert linked in insight_ids
            card = _card(methods, linked)
            assert card["tag"]["step"] == step["id"]
            assert card["tag"]["label"] == "Changed our pipeline"


def test_every_card_that_changed_the_pipeline_names_the_rules_it_is_evidence_for(methods):
    """The rules page shows a card under the rules it names, so each names at least one, and
    every name is a rule file."""
    names = set(rulebook.rule_names())
    for card in methods["insights"]:
        if card["tag"]["kind"] == "changed_pipeline":
            assert card["tag"]["rules"], card["id"]
            assert set(card["tag"]["rules"]) <= names, card["id"]
        else:
            assert "rules" not in card["tag"], card["id"]


def test_charts_have_one_value_per_x_in_every_series(methods):
    for card in methods["insights"]:
        chart = card["chart"]
        # a card the release has no data for (no MedDRA) has no x values and no series
        assert chart["series"] or chart["x"]["values"] == [], card["id"]
        for s in chart["series"]:
            assert len(s["values"]) == len(chart["x"]["values"]), (card["id"], s["name"])


def test_deleted_lists_card_counts_the_release_lists_and_changed_their_step(rel, methods):
    card = _card(methods, "deleted_lists_unpublished")
    assert card["tag"]["step"] == "after_deleted_lists"
    total = sum(v or 0 for s in card["chart"]["series"] for v in s["values"])
    assert total == rel.funnel["deleted_lists"]["caseids_listed"]
    published = sum(v or 0 for v in card["chart"]["series"][0]["values"])
    in_files = rel.rows(
        "SELECT count(*) FROM deleted_cases_T WHERE caseid IN (SELECT caseid FROM demo_T)"
    )[0][0]
    assert published == in_files  # AERS and FAERS files alike: both eras' listed cases leave
    assert published == rel.step("after_deleted_lists")["removed"]["total"]
    assert f"{rel.funnel['deleted_lists']['caseids_listed']:,} case ids" in card["two_sentences"]


def test_notebook_02_cards_are_why_its_steps_remove_cases(methods):
    for card_id, step_id in NOTEBOOK_02.items():
        step = next(s for s in methods["steps"] if s["id"] == step_id)
        assert card_id in step["insights"]
        assert _card(methods, card_id)["notebook"] == "notebooks/faers/02_case_versions.ipynb"


def test_notebook_02_charts_ask_their_question_and_label_what_matters(methods):
    for card_id in NOTEBOOK_02:
        chart = _card(methods, card_id)["chart"]
        assert chart["question"].endswith("?"), card_id
        assert chart["x"]["label"] and chart["y"]["label"]
        if "note" in chart:
            assert chart["note"]["x"] in chart["x"]["values"], card_id


def test_notebook_08_cards_link_the_steps_that_read_dates_and_codes(rel, methods):
    """The dates and codes steps take no case out, yet each links back to the cards that are
    its evidence; the documented cards link to no step."""
    for card_id, step_id in NOTEBOOK_08.items():
        card = _card(methods, card_id)
        assert card["notebook"] == "notebooks/faers/08_dates_and_codes.ipynb"
        assert card["chart"]["question"].endswith("?"), card_id
        assert card["chart"]["x"]["label"] and card["chart"]["y"]["label"], card_id
        if step_id is None:
            assert card["tag"]["kind"] == "documented", card_id
            continue
        step = next(s for s in methods["steps"] if s["id"] == step_id)
        assert card_id in step["insights"]
        assert step["removed"]["total"] == 0
        assert rel.step(step_id)["count"] == rel.step("kept_after_duplicates")["count"]


def test_carried_cases_card_counts_case_numbers_in_both_eras(rel, methods):
    both = rel.rows(
        "SELECT count(*) FROM (SELECT caseid FROM demo_T WHERE caseid IS NOT NULL "
        "GROUP BY 1 HAVING count(DISTINCT era_T) = 2)"
    )[0][0]
    assert both == 2  # the fake's two carried-over cases
    card = _card(methods, "carried_cases_counted_twice")
    assert sum(card["chart"]["series"][0]["values"]) == both
    assert f"carried {both:,} AERS cases" in card["two_sentences"]
    assert "always the FAERS one" in card["two_sentences"]


def test_deleted_aers_card_counts_the_aers_cases_the_step_removes(rel, methods):
    card = _card(methods, "deleted_lists_name_aers_cases")
    listed = sum(v for s in card["chart"]["series"] for v in s["values"])
    removed = rel.step("after_deleted_lists")["removed"]["legacy"]
    assert listed == removed == 1  # 5100007; the carried 5100011 leaves with its FAERS version
    assert all(q < "2012Q4" for q in card["chart"]["x"]["values"])


def test_eras_card_shows_the_switch_and_counts_groups_across_eras(rel, methods):
    card = _card(methods, "eras_write_countries_and_terms_differently")
    chart = card["chart"]
    code, caps = (
        dict(zip(chart["x"]["values"], s["values"], strict=True)) for s in chart["series"]
    )
    assert code["2012Q2"] is None  # the 2004Q1 layout has no country
    assert code["2012Q3"] == 0 and caps["2012Q3"] == 100
    assert code["2026Q2"] == 100 and caps["2026Q2"] == 0
    assert chart["note"] == {"x": "2012Q4", "text": "FAERS begins"}
    across = rel.rows(
        "SELECT count(*) FROM (SELECT dup_group_T FROM case_dup_T WHERE dup_group_T IS NOT NULL "
        "GROUP BY 1 HAVING count(DISTINCT era_T) = 2)"
    )[0][0]
    assert across == 1  # the fake's group C
    assert f"we now find {across:,} duplicate groups" in card["two_sentences"]
    assert "the FAERS one in 1 of them" in card["two_sentences"]


def test_cards_computed_from_the_release_folder_match_the_release(release, methods):
    """The notebooks call the same card functions: computing them from the
    published Parquet gives the JSON the release carries."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", MissingDataWarning)
        cards = [c for c in compute_cards(connect(release)) if c["id"] not in LICENSED]
    carried = [
        {**c, "tag": {k: v for k, v in c["tag"].items() if k != "label"}}
        for c in methods["insights"]
    ]
    assert cards == carried


def test_cards_with_a_missing_column_show_no_data_instead_of_failing(release):
    con = connect(release)
    parquet = (release / "parquet" / "case_latest_T.parquet").as_posix()
    con.execute(
        f"CREATE OR REPLACE VIEW case_latest_T AS "
        f"SELECT * EXCLUDE (occr_country, occp_cod) FROM read_parquet('{parquet}')"
    )
    with pytest.warns(MissingDataWarning):
        cards = {c["id"]: c for c in compute_cards(con)}
    for card_id in ("country_empty_rising", "occupation_code_changes"):
        chart = cards[card_id]["chart"]
        assert chart["x"]["values"] == [] or all(
            v is None for s in chart["series"] for v in s["values"]
        )
    assert cards["deleted_lists_unpublished"]["chart"]["series"][0]["values"]


def test_notebook_04_cards_carry_their_tags_and_ask_their_question(dup_methods):
    for card_id, step in NOTEBOOK_04.items():
        card = _card(dup_methods, card_id)
        if step is None:
            assert card["tag"]["kind"] == "documented", card_id
        else:
            assert (card["tag"]["kind"], card["tag"]["step"]) == ("changed_pipeline", step), card_id
            assert card_id in next(s for s in dup_methods["steps"] if s["id"] == step)["insights"]
        assert card["chart"]["question"].endswith("?"), card_id
        assert card["notebook"] == "notebooks/faers/04_duplicates.ipynb"


def test_copies_card_counts_every_case_set_aside(dup_rel, dup_methods):
    aside = dup_rel.rows(
        "SELECT count(*) FROM case_dup_T WHERE probable_duplicate_T AND NOT dup_kept_T"
    )[0][0]
    card = _card(dup_methods, "same_event_several_cases")
    assert aside > 0
    assert sum(v for s in card["chart"]["series"] for v in s["values"]) == aside
    assert card["two_sentences"].startswith(f"{aside:,} case")


def test_number_card_counts_cases_set_aside_by_the_number(dup_rel, dup_methods):
    [(by_number,)] = dup_rel.rows(
        "SELECT count(*) FROM case_dup_T WHERE NOT dup_kept_T AND len(list_intersect(dup_rule_T, "
        "['manufacturer_number', 'manufacturer_number_country_code'])) > 0"
    )
    card = _card(dup_methods, "one_case_two_numbers")
    matched = card["chart"]["series"][0]
    assert by_number > 0
    assert sum(matched["values"]) == by_number
    assert sum(card["chart"]["series"][1]["values"]) > 0  # the fake's sex and age clashes


def test_padded_card_counts_the_cases_the_guard_leaves_shown(dup_rel, dup_methods):
    [(groups, cases)] = dup_rel.rows(
        "SELECT count(DISTINCT dup_key_T), count(*) FROM case_dup_T WHERE dup_padded_date_T"
    )
    card = _card(dup_methods, "padded_dates_join_different_patients")
    assert groups > 0
    assert f"{cases - groups:,} case" in card["two_sentences"]
    assert f"{groups:,} group" in card["two_sentences"]
    assert card["chart"]["note"]["x"] in card["chart"]["x"]["values"]


def test_no_adverse_event_card_counts_the_flagged_reports(dup_rel, dup_methods):
    [(total, serious)] = dup_rel.rows(
        "SELECT count(*) FILTER (WHERE no_drug_or_reaction_T), "
        "count(*) FILTER (WHERE serious_no_drug_or_reaction_T) FROM case_dup_T"
    )
    card = _card(dup_methods, "no_adverse_event_serious_outcome")
    with_outcome, without = card["chart"]["series"]
    assert sum(with_outcome["values"]) == serious and sum(without["values"]) == total - serious


def test_notebook_09_cards_are_documented_until_the_classes_are_a_funnel_step(methods):
    """The drug classes are a layer of their own, so their cards carry no step to link to."""
    assert "drug_classes" not in {s["id"] for s in methods["steps"]}
    for card_id in NOTEBOOK_09:
        card = _card(methods, card_id)
        assert card["tag"] == {"kind": "documented", "label": "Documented, not transformed"}
        assert card["notebook"] == "notebooks/faers/09_drug_classes.ipynb"
        assert card["chart"]["question"].endswith("?")
        assert card["chart"]["note"]["x"] in card["chart"]["x"]["values"]


def test_aspirin_card_counts_every_aspirin_record_that_states_its_dose(rel, methods):
    low = next(
        d
        for d in rulebook.value("atc-class-choice", "dose_rules")
        if d["substance"] == "acetylsalicylic acid" and d.get("at_most") is not None
    )
    [(dosed, lows)] = rel.rows(
        """WITH d AS (
             SELECT d.era_T, d.primaryid, d.quarter_T, d.drug_seq,
                    max(CAST(d.dose_amt AS DOUBLE)) AS most_T
             FROM drug_substance_T s
             JOIN drug_latest_T d USING (era_T, primaryid, quarter_T, drug_seq)
             JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
             WHERE s.substance_T = 'acetylsalicylic acid' AND c.dup_kept_T
               AND upper(d.dose_unit) = ? AND d.dose_amt <> ''
             GROUP BY ALL)
           SELECT count(*), count(*) FILTER (WHERE most_T <= ?) FROM d""",
        low["unit"],
        low["at_most"],
    )
    card = _card(methods, "aspirin_dose_tells_the_use")
    assert dosed > 0  # the fake's aspirin rows state 100 MG
    assert sum(card["chart"]["series"][0]["values"]) == dosed
    assert card["chart"]["series"][0]["values"][0] == lows
    assert f"{dosed:,} aspirin record" in card["two_sentences"]


def test_two_use_card_counts_the_records_whose_use_the_report_may_not_say(rel, methods):
    [(records, unsaid)] = rel.rows(
        """SELECT count(*),
                  count(*) FILTER (WHERE a.atc_chosen_by_T IN ('cannot_tell', 'shared_class'))
           FROM atc_drug_T a JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
           WHERE c.dup_kept_T AND a.atc_possible_codes_T > 1
             AND a.atc_matched_on_T <> 'each_ingredient'"""
    )
    card = _card(methods, "two_use_drug_use_not_said")
    assert records > unsaid > 0  # the fake's aspirin is chosen by dose, its ibuprofen is not
    assert f"of the {records:,} drug record" in card["two_sentences"]
    assert f"{100 * unsaid / records:.0f}% say none of them" in card["two_sentences"]
    assert all(0 <= v <= 100 for s in card["chart"]["series"] for v in s["values"] if v is not None)


def test_a_release_without_the_drug_classes_has_its_class_cards_say_so(dup_methods):
    for card_id in NOTEBOOK_09:
        card = _card(dup_methods, card_id)
        assert card["title"] == "This release does not give drugs their WHO class"
        assert card["chart"]["x"]["values"] == []
        assert "without the drug classes" in card["two_sentences"]


def test_notebook_03_cards_back_not_given_and_ask_their_question(methods):
    for card_id in NOTEBOOK_03:
        card = _card(methods, card_id)
        assert (card["tag"]["kind"], card["tag"]["step"]) == ("changed_pipeline", "report_versions")
        assert "not-given" in card["tag"]["rules"], card_id
        assert card["chart"]["question"].endswith("?"), card_id
        assert card["notebook"] == "notebooks/faers/03_empty_fields.ipynb"


def test_rechallenge_filler_card_backs_not_given(methods):
    card = _card(methods, "rechal_filler")
    assert (card["tag"]["kind"], card["tag"]["step"]) == ("changed_pipeline", "report_versions")
    assert card["tag"]["rules"] == ["not-given"]
    step = next(s for s in methods["steps"] if s["id"] == "report_versions")
    assert "rechal_filler" in step["insights"]


def _quarters(con: duckdb.DuckDBPyConnection, *quarters: str) -> None:
    rows = ", ".join(f"('{q}', {i})" for i, q in enumerate(quarters))
    con.execute(f"CREATE TABLE quarters_T AS SELECT * FROM (VALUES {rows}) t(quarter_T, qnum_T)")


def test_route_card_reads_blank_and_unknown_apart_and_both_as_not_given():
    con = duckdb.connect()
    _quarters(con, "2025q4", "2026q1", "2026q2")
    con.execute(
        "CREATE TABLE drug_latest_T AS SELECT * FROM (VALUES "
        "('faers', '2025q4', 'ORAL'), ('faers', '2025q4', 'UNKNOWN'), ('faers', '2025q4', 'UNK'), "
        "('faers', '2025q4', NULL), ('faers', '2026q2', 'ORAL'), ('faers', '2026q2', ' '), "
        "('faers', '2026q2', NULL), ('faers', '2026q2', 'UNKNOWN'), ('legacy', '2026q2', NULL)"
        ") t(era_T, quarter_T, route)"
    )
    card = empty_fields.unknown_written_two_ways(con)
    given, unknown, blank = (
        dict(zip(card["chart"]["x"]["values"], s["values"], strict=True))
        for s in card["chart"]["series"]
    )
    assert (given["2025Q4"], unknown["2025Q4"], blank["2025Q4"]) == (25, 50, 25)
    assert (given["2026Q2"], unknown["2026Q2"], blank["2026Q2"]) == (25, 25, 50)
    assert (given["2026Q1"], unknown["2026Q1"], blank["2026Q1"]) == (0, 0, 0)  # no rows
    assert "UNKNOWN on 25% of drug rows against 50% in 2025Q4" in card["two_sentences"]
    assert "blank rose from 25% to 50%" in card["two_sentences"]


def test_to_mfr_card_reads_company_reports_as_filler_and_direct_reports_as_given():
    con = duckdb.connect()
    _quarters(con, "2014q1", "2016q1")
    con.execute(
        "CREATE TABLE demo_T AS SELECT * FROM (VALUES "
        "('2014q1', 'DIR', 'N'), ('2014q1', 'EXP', 'N'), ('2014q1', 'PER', 'N'), "
        "('2016q1', 'DIR', 'Y'), ('2016q1', 'EXP', NULL), ('2016q1', 'DIR', NULL)"
        ") t(quarter_T, rept_cod, to_mfr)"
    )
    card = empty_fields.to_mfr_filler_on_company_reports(con)
    direct, company = (s["values"] for s in card["chart"]["series"])
    assert direct == [100, 50] and company == [100, 0]
    assert card["chart"]["note"] == {"x": "2014Q1", "text": "Company reports filled with N"}
    assert "fill it on 67% of report versions" in card["two_sentences"]
    assert "2 of them say N from 2014Q1 to 2014Q1" in card["two_sentences"]


def test_occupation_card_splits_company_from_direct_reports_from_the_noted_quarter():
    con = duckdb.connect()
    _quarters(con, "2025q2", "2025q3", "2026q2")
    con.execute(
        "CREATE TABLE demo_T AS SELECT 'faers' AS era_T, * FROM (VALUES "
        "('2025q2', 'EXP', 'CN'), ('2025q2', 'EXP', 'MD'), ('2025q2', 'DIR', 'CN'), "
        "('2025q3', 'EXP', 'MD'), ('2025q3', 'EXP', NULL), ('2025q3', 'DIR', 'CN'), "
        "('2026q2', 'EXP', NULL), ('2026q2', 'PER', NULL), ('2026q2', 'DIR', 'CN')"
        ") t(quarter_T, rept_cod, occp_cod)"
    )
    card = empty_fields.who_reported_lost_on_company_reports(con)
    company, direct = (s["values"] for s in card["chart"]["series"])
    assert company == [100, 50, 0] and direct == [100, 100, 100]
    assert card["chart"]["note"]["x"] == "2025Q3"  # where rule explorer-field-notes starts its note
    assert "on 100% of company reports in 2025Q2 and on 0% in 2026Q2" in card["two_sentences"]
    assert "consumers fell from 50% to 0%" in card["two_sentences"]


def test_sender_card_counts_a_company_under_every_spelling_and_no_unknown_sender():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE case_latest_T AS SELECT 'faers' AS era_T, * FROM (VALUES "
        "('EXP', 'ALK-ABELLO', '40', 'F', '20260101'), ('EXP', 'ALK- ABELLO', NULL, NULL, NULL), "
        "('EXP', 'AMAG', '50', 'M', NULL), ('EXP', 'Unknown Manufacturer', '60', 'F', '20260103'), "
        "('DIR', NULL, '30', 'F', '20260102')"
        ") t(rept_cod, mfr_sndr, age, sex_T, event_dt)"
    )
    card = empty_fields.completeness_depends_on_sender(con)
    chart = card["chart"]
    assert chart["x"]["values"] == ["ALK-Abello", "AMAG", "Direct reports"]
    all_three, two, one, none = (s["values"] for s in chart["series"])
    assert all_three == [50, 0, 100] and two == [0, 100, 0] and none == [50, 0, 0]
    assert chart["note"]["x"] == "AMAG"
    assert "ranges from 0% (AMAG) to 50% (ALK-Abello)" in card["two_sentences"]
