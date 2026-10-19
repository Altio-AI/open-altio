"""What reads Not given (rule not-given), asked of one value at a time: blank, values that say
unknown and filler numbers do; real values, the codes kept on purpose and FDA's other quarters
do not."""

from __future__ import annotations

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers import not_given
from open_altio.faers.reader import quoted
from open_altio.faers.schema import RAW_COLUMNS


def reads(field: str, text: str | None, **context: str) -> bool:
    value = "NULL::VARCHAR" if text is None else quoted(text)
    return duckdb.sql(f"SELECT {not_given.check(field, value, **context)}").fetchone()[0]


@pytest.mark.parametrize(
    "field, text",
    [
        ("sex", None),
        ("sex", " \t"),
        ("mfr_sndr", "Unknown manufacturer"),
        ("mfr_sndr", "UNKNOWN"),
        ("mfr_sndr", "Unknown labeler, Inc."),
        ("indi_pt", "Product used for unknown indication"),
        ("dechal", "U"),
        ("route", "UNKNOWN"),
        ("route", "Route of administration: unknown"),
        ("lot_num", "N/A"),
        ("dose_freq", "NA"),
        ("drugname", "UNKNOWN DRUG"),
        ("age", "999"),
        ("wt", "0"),
        ("wt", "0.0"),
        ("nda_num", "99999"),
        ("caseid", ""),
    ],
)
def test_blank_unknown_and_filler_values_read_not_given(field, text):
    assert reads(field, text)


@pytest.mark.parametrize(
    "field, text",
    [
        ("sex", "F"),
        ("occr_country", "NI"),
        ("occr_country", "NA"),
        ("reporter_country", "US"),
        ("dechal", "D"),
        ("route", "ORAL"),
        ("lot_num", "NASAL 12"),
        ("drugname", "ASPIRIN"),
        ("mfr_sndr", "Generics [UK] Ltd"),
        ("mfr_sndr", "GENERICUS"),
        ("mfr_sndr", "ACME PHARMA, INC."),
        ("age", "0"),
        ("age", "45"),
        ("wt", "70"),
        ("caseid", "UNKNOWN"),
    ],
)
def test_real_values_and_the_codes_kept_on_purpose_do_not(field, text):
    assert not reads(field, text)


def test_sex_and_country_codes_are_left_to_their_own_rules():
    # sex-codes and country-not-given give sex_T and country_T; this rule reads only a blank there
    for field, text in (("sex", "NS"), ("sex", "UNK"), ("occr_country", "COUNTRY NOT SPECIFIED")):
        assert field not in not_given.fields() and not reads(field, text), (field, text)


def test_rechallenge_d_reads_not_given_only_in_the_quarters_it_was_a_filler():
    within = rulebook.value("not-given", "fields")["rechal"]["codes_in_quarters"]
    for quarter in (within["from"], within["to"]):
        assert reads("rechal", "D", quarter=quoted(quarter))
        assert not reads("rechal", "Y", quarter=quoted(quarter))
        assert not reads("dechal", "D", quarter=quoted(quarter))
    for quarter in ("2004q1", "2012q3", "2015q4", "2026q2"):
        assert not reads("rechal", "D", quarter=quoted(quarter))


def test_to_mfr_is_read_only_on_direct_reports():
    assert not reads("to_mfr", "N", report="'DIR'")
    assert not reads("to_mfr", "Y", report="'DIR'")
    assert reads("to_mfr", "N", report="'EXP'")
    assert reads("to_mfr", "Y", report="NULL")


def test_given_keeps_a_real_value_and_clears_one_that_reads_not_given():
    got = duckdb.sql(
        f"SELECT {not_given.given('route', quoted('UNKNOWN'))}, "
        f"{not_given.given('route', quoted('ORAL'))}, "
        f"{not_given.given('age', quoted('999'), '999.0')}"
    ).fetchone()
    assert got == (None, "ORAL", None)


def test_named_lists_the_fields_that_read_not_given_and_skips_fields_the_rule_does_not_read():
    got = duckdb.sql(
        f"SELECT {not_given.named(['route', 'wt', 'sex', 'caseid'], 'r')} FROM "
        "(SELECT 'UNKNOWN' AS route, NULL AS wt, 'UNK' AS sex, NULL AS caseid) r"
    ).fetchone()[0]
    assert got == ["route", "wt"]


def test_every_field_the_rule_reads_is_fdas_and_each_entry_is_one_it_knows():
    fda = {c for columns in RAW_COLUMNS.values() for c in columns}
    kinds = {
        "codes",
        "words",
        "glue",
        "no_drug_names",
        "filler",
        "codes_in_quarters",
        "only_report_types",
    }
    fillers = rulebook.value("not-given", "fillers")
    for field, how in not_given.fields().items():
        assert field in fda, field
        assert set(how) <= kinds, field
        assert how.get("filler", "nines") in fillers, field
        assert isinstance(rulebook.value("not-given", how.get("glue", "glue_words")), list), field


def test_a_filler_age_or_weight_gives_no_age_or_weight_in_any_unit():
    from open_altio.faers import derive

    rows = "VALUES ('999', 'MON', '999', 'LBS'), ('83', 'YR', '70', 'KG'), ('0', 'YR', '0', 'KG')"
    got = duckdb.sql(
        f"SELECT {derive._age_years()}, {derive._wt_kg()} FROM ({rows}) v(age, age_cod, wt, wt_cod)"
    ).fetchall()
    assert got == [(None, None), (83.0, 70.0), (0.0, None)]
