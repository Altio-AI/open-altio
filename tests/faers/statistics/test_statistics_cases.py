"""The one set of cases every statistic counts (src/open_altio/faers/statistics/cases.py,
rule statistics-cases), worked by hand on eight cases."""

from __future__ import annotations

import duckdb
import numpy as np
import pytest

from open_altio import rulebook
from open_altio.faers.statistics import cases, scored
from open_altio.stats import ebgm

KEY = "era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR"
# primaryid, age_band_T, sex_T, init_year_T, dup_kept_T; the band and sex as the release gives
# them (rules age-bands, sex-codes), whatever their names
CASES = [
    ("1", "adult", "F", 2020, True),
    ("2", "adult", "F", 2020, True),
    ("3", "older", "M", 2021, True),
    ("4", None, None, None, True),  # every part of its stratum unknown
    ("5", "adult", "F", 2020, False),  # a duplicate set aside
    ("6", "adult", "F", 2020, True),  # a concomitant drug only: no ingredient counts
    ("7", "adult", "F", 2019, True),  # a drug with no ingredient
    ("8", "oldest", "M", 2022, True),  # a combination: counts for each of its ingredients
]
# primaryid, drug_seq, role_cod; case 2's record is on two of FDA's rows
DRUGS = [
    ("1", "1", "PS"), ("1", "2", "SS"), ("1", "3", "C"), ("1", "4", "PS"),
    ("2", "1", "PS"), ("2", "1", "PS"),
    ("3", "1", "SS"), ("3", "2", " ps"),
    ("4", "1", "PS"), ("5", "1", "PS"), ("6", "1", "C"), ("7", "1", "PS"), ("8", "1", "PS"),
]  # fmt: skip
# primaryid, drug_seq, ingredient_T
INGREDIENTS = [
    ("1", "1", "aspirin"), ("1", "2", "ibuprofen"), ("1", "3", "metformin"), ("1", "4", "aspirin"),
    ("2", "1", "aspirin"), ("3", "1", "ibuprofen"), ("3", "2", "warfarin"), ("4", "1", "aspirin"),
    ("5", "1", "aspirin"), ("6", "1", "aspirin"), ("8", "1", "sacubitril"), ("8", "1", "valsartan"),
]  # fmt: skip
REACTIONS = [
    ("1", "Headache"), ("1", "Nausea"), ("2", "HEADACHE"), ("2", "headache "), ("3", "Nausea"),
    ("3", "Bleeding"), ("4", "Headache"), ("5", "Headache"), ("6", "Headache"), ("7", "Headache"),
    ("8", "Cough"),
]  # fmt: skip

# Counted: cases 1, 2, 3, 4 and 8. Strata: 1 and 2 (18 to 64, F, 2020), 3 (65 to 74, M, 2021),
# 4 (unknown three times), 8 (75 to 84, M, 2022). aspirin 1, 2, 4; ibuprofen 1, 3; warfarin 3;
# sacubitril and valsartan 8. headache 1, 2, 4; nausea 1, 3; bleeding 3; cough 8.
# E sums, over strata, the ingredient's cases times the reaction's over the stratum's.
PAIRS = {  # (ingredient, reaction): (cases, E)
    ("aspirin", "headache"): (3, 2 * 2 / 2 + 1 * 1 / 1),
    ("aspirin", "nausea"): (1, 2 * 1 / 2),
    ("ibuprofen", "headache"): (1, 1 * 2 / 2),
    ("ibuprofen", "nausea"): (2, 1 * 1 / 2 + 1 * 1 / 1),
    ("ibuprofen", "bleeding"): (1, 1 * 1 / 1),
    ("warfarin", "nausea"): (1, 1 * 1 / 1),
    ("warfarin", "bleeding"): (1, 1 * 1 / 1),
    ("sacubitril", "cough"): (1, 1.0),
    ("valsartan", "cough"): (1, 1.0),
}


@pytest.fixture(scope="module")
def counts() -> cases.Counts:
    con = duckdb.connect()
    con.execute(
        f"CREATE TABLE case_latest_T ({KEY}, age_band_T VARCHAR, sex_T VARCHAR, "
        "init_year_T INTEGER, dup_kept_T BOOLEAN)"
    )
    con.execute(f"CREATE TABLE drug_latest_T ({KEY}, drug_seq VARCHAR, role_cod VARCHAR)")
    con.execute(f"CREATE TABLE drug_ingredient_T ({KEY}, drug_seq VARCHAR, ingredient_T VARCHAR)")
    con.execute(f"CREATE TABLE reac_latest_T ({KEY}, pt VARCHAR)")
    for table, rows in (
        ("case_latest_T", CASES),
        ("drug_latest_T", DRUGS),
        ("drug_ingredient_T", INGREDIENTS),
        ("reac_latest_T", REACTIONS),
    ):
        marks = ", ".join(["?"] * len(rows[0]))
        con.executemany(f"INSERT INTO {table} VALUES ('faers', ?, '2026q2', {marks[3:]})", rows)
    return cases.count(con)


def named(counts: cases.Counts, table: dict) -> dict:
    return {
        (counts.ingredients[p], counts.reactions[e]): int(n)
        for p, e, n in zip(table["product"], table["event"], table["n"], strict=True)
    }


def test_counts_distinct_kept_cases_naming_a_suspect_ingredient_and_a_reaction(counts):
    assert counts.cases == 5
    assert named(counts, counts.pairs) == {pair: n for pair, (n, _) in PAIRS.items()}


def test_a_combination_counts_for_each_of_its_ingredients(counts):
    assert {p for p, r in named(counts, counts.pairs) if r == "cough"} == {
        "sacubitril",
        "valsartan",
    }


def test_strata_are_age_band_sex_and_receipt_year(counts):
    unknown = rulebook.value("statistics-cases", "unknown")
    got = sorted(
        zip(
            *(counts.strata[k].tolist() for k in ("age_band", "sex", "receipt_year", "n")),
            strict=True,
        )
    )
    assert got == sorted(
        [
            ("adult", "F", "2020", 2),
            ("older", "M", "2021", 1),
            (unknown, unknown, unknown, 1),
            ("oldest", "M", "2022", 1),
        ]
    )


def test_expected_counts_worked_by_hand(counts):
    strata = {"stratum": counts.strata["stratum"], "n": counts.strata["n"]}
    ne = ebgm.expected_counts(
        counts.pairs, counts.ingredient_strata, counts.reaction_strata, strata
    )
    got = {
        (counts.ingredients[p], counts.reactions[e]): x
        for p, e, x in zip(ne["product"], ne["event"], ne["E"], strict=True)
    }
    assert got == pytest.approx({pair: e for pair, (_, e) in PAIRS.items()}, rel=1e-12)


def test_every_pair_carries_its_table_and_a_fit_too_small_to_make_is_said(counts):
    columns, about = scored.score(counts)
    row = {
        (i, r): k
        for k, (i, r) in enumerate(zip(columns["ingredient"], columns["reaction"], strict=True))
    }[("ibuprofen", "nausea")]
    assert (columns["cases"][row], columns["ingredient_cases"][row]) == (2, 2)
    assert columns["reaction_cases"][row] == 2
    assert columns["rrr"][row] == pytest.approx(2 / (2 * 2 / 5))
    assert about["fitted"] is False and about["reason"]
    assert np.all(np.isnan(columns["ebgm"]))
    assert list(columns) == list(scored.COLUMNS)
