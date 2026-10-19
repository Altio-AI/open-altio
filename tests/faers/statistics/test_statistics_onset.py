"""Each pair's time to onset (src/open_altio/faers/statistics/onset.py, rule time-to-onset),
worked by hand on five cases: the median over the drugs with a value, how many have one, and how
many have none by why."""

from __future__ import annotations

import math

import numpy as np
import pytest

from open_altio import rulebook
from open_altio.faers.dates import ONSET_REASONS
from open_altio.faers.statistics import cases, onset
from open_altio.rulebook import UserRules

PADDED, INEXACT, NO_DOSE, BEFORE = ONSET_REASONS
CASES = [(str(i), "18-64", "F", 2026, True) for i in range(1, 6)]
DRUGS = [
    ("1", "1", "PS"), ("1", "2", "SS"),  # two records of one ingredient: two drugs
    ("2", "1", "PS"), ("2", "1", "PS"), ("2", "2", "C"),  # a record on two of FDA's rows
    ("3", "1", "PS"), ("3", "2", "PS"),
    ("4", "1", "PS"),  # a case with no reaction is not counted
    ("5", "1", "PS"),  # a combination: a drug of each of its ingredients
]  # fmt: skip
INGREDIENTS = [
    ("1", "1", "aspirin"), ("1", "2", "aspirin"), ("2", "1", "aspirin"), ("2", "2", "ibuprofen"),
    ("3", "1", "aspirin"), ("3", "2", "ibuprofen"), ("4", "1", "aspirin"),
    ("5", "1", "sacubitril"), ("5", "1", "valsartan"),
]  # fmt: skip
REACTIONS = [("1", "Headache"), ("1", "Nausea"), ("2", "Headache"), ("3", "Headache"),
             ("5", "Cough")]  # fmt: skip
ONSETS = [
    ("1", "1", 5, None), ("1", "2", 9, None), ("2", "1", None, PADDED),
    ("2", "2", 2, None),  # concomitant: never counted
    ("3", "1", 20, None), ("3", "2", None, BEFORE), ("4", "1", 1, None), ("5", "1", 3, None),
]  # fmt: skip
NO_VALUE = dict.fromkeys(onset.REASON_COLUMNS, 0)
WANT = {  # (ingredient, reaction): (median days, drugs with a value, drugs with none by why)
    ("aspirin", "headache"): (9, 3, NO_VALUE | {f"no_onset_{PADDED}": 1}),
    ("aspirin", "nausea"): (7, 2, NO_VALUE),
    ("ibuprofen", "headache"): (None, 0, NO_VALUE | {f"no_onset_{BEFORE}": 1}),
    ("sacubitril", "cough"): (3, 1, NO_VALUE),
    ("valsartan", "cough"): (3, 1, NO_VALUE),
}


def summarised(small_release) -> dict:
    con = small_release(
        case_latest_T=CASES,
        drug_latest_T=DRUGS,
        drug_ingredient_T=INGREDIENTS,
        reac_latest_T=REACTIONS,
        drug_onset_T=ONSETS,
    )
    counts = cases.count(con)
    got = onset.summary(con, counts)
    out = {}
    for i, (p, e) in enumerate(zip(counts.pairs["product"], counts.pairs["event"], strict=True)):
        days = got["onset_days"][i]
        out[(counts.ingredients[p], counts.reactions[e])] = (
            None if math.isnan(days) else days,
            int(got["onset_drugs"][i]),
            {name: int(got[name][i]) for name in onset.REASON_COLUMNS},
        )
    return out


def test_each_pair_has_the_median_of_its_drugs_with_a_value_and_counts_those_without(
    small_release,
):
    got = summarised(small_release)
    assert got == WANT


def test_the_columns_are_the_median_the_drugs_with_a_value_and_one_count_for_each_reason():
    assert (
        "onset_days",
        "onset_drugs",
        *(f"no_onset_{reason}" for reason in ONSET_REASONS),
    ) == onset.COLUMNS


def test_switched_off_every_pair_has_its_columns_empty(small_release):
    off = UserRules(off=frozenset({onset.RULE}))
    with rulebook.use_user_rules(off):
        con = small_release(
            case_latest_T=CASES,
            drug_latest_T=DRUGS,
            drug_ingredient_T=INGREDIENTS,
            reac_latest_T=REACTIONS,
            drug_onset_T=[replace_none(row) for row in ONSETS],
        )
        counts = cases.count(con)
        got = onset.summary(con, counts)
    assert set(got) == set(onset.COLUMNS)
    assert all(np.ma.getmaskarray(column).all() for column in got.values())
    assert all(len(column) == len(counts.pairs["n"]) for column in got.values())


def replace_none(row: tuple) -> tuple:
    """A drug_onset_T row as the rule switched off writes it: no value and no reason."""
    return (*row[:2], None, None)


@pytest.mark.parametrize("values", [[4], [4, 8], [1, 2, 30], [3, 3, 9, 10]])
def test_the_median_is_the_middle_value_or_the_mean_of_the_two_middle_ones(small_release, values):
    rows = [("1", str(n), "PS") for n in range(len(values))]
    con = small_release(
        case_latest_T=CASES[:1],
        drug_latest_T=rows,
        drug_ingredient_T=[("1", str(n), "aspirin") for n in range(len(values))],
        reac_latest_T=[("1", "Headache")],
        drug_onset_T=[("1", str(n), v, None) for n, v in enumerate(values)],
    )
    got = onset.summary(con, cases.count(con))
    assert got["onset_days"][0] == np.median(values) and got["onset_drugs"][0] == len(values)
