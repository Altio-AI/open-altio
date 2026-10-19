"""Sex, age, weight, age band and country as a release reads them, built from
fakefda.DEMOGRAPHICS_STORY and read from the release folder only: rules sex-codes, age-in-years,
weight-in-kg, age-bands, country-not-given and eu-member-state. FDA's own values stay as
published beside each one."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.faers import build_release
from open_altio.rulebook import UserRules
from open_altio.testing import fakefda
from open_altio.testing.releasereader import ReleaseReader

COUNTRY_RULES = frozenset({"country-not-given", "eu-member-state"})


# demo_rel, the release with every rule on, is open_altio.testing.fixtures'.
def _built(tmp_path_factory, rules: UserRules | None = None) -> ReleaseReader:
    zips = fakefda.write_input(
        tmp_path_factory.mktemp("demographics_zips"),
        quarters=fakefda.DUP_QUARTERS,
        story=fakefda.DEMOGRAPHICS_STORY,
    )
    return ReleaseReader(
        build_release(zips, tmp_path_factory.mktemp("demographics"), user_rules=rules)
    )


@pytest.fixture(scope="module")
def country_off_rel(tmp_path_factory) -> ReleaseReader:
    return _built(tmp_path_factory, UserRules(off=COUNTRY_RULES))


def _by_case(rel: ReleaseReader) -> dict[str, dict]:
    return {r["caseid"]: r for r in rel.dicts("SELECT * FROM case_latest_T")}


@pytest.fixture(scope="module")
def case(demo_rel):
    """case(what): the latest version of the DEMOGRAPHICS case that shows `what`."""
    rows = _by_case(demo_rel)
    return lambda what: rows[fakefda.DEMOGRAPHICS[what].caseid]


def _years(number: float, unit: str) -> float:
    times, over = rulebook.value("age-in-years", "units")[unit]
    return number * times / over


def test_sex_is_f_or_m_and_every_other_code_is_not_known(case):
    known = rulebook.value("sex-codes", "known")
    assert case("sex F")["sex_T"] == "F" and "F" in known
    assert case("sex m with spaces")["sex_T"] == "M"
    for what in ("sex NS", "sex UNK", "sex P", "sex empty"):
        assert case(what)["sex_T"] is None, what
    assert case("sex NS")["sex"] == "NS"  # FDA's code stays


def test_age_is_read_in_years_exactly_from_every_unit(case):
    assert case("age with no unit")["age_years_T"] == 45.0
    assert rulebook.value("age-in-years", "no_unit") == "YR"
    assert case("age with no unit")["age_cod"] is None  # FDA's unit stays empty
    assert case("age in minutes")["age_years_T"] == _years(30, "MIN")
    assert case("age in seconds")["age_years_T"] == _years(3600, "SEC")
    assert case("23 months")["age_years_T"] == _years(23, "MON")  # never rounded
    top = rulebook.value("age-in-years", "max_years")
    assert case("age at the top")["age_years_T"] == top
    for what in ("age over the top", "age in decades over the top", "age negative"):
        assert case(what)["age_years_T"] is None, what


def test_numbers_are_read_with_a_leading_or_trailing_point_and_spaces(case):
    assert case("age .8")["age_years_T"] == 0.8
    assert case("age 60.")["age_years_T"] == 60.0
    assert case("age with spaces")["age_years_T"] == 60.0
    assert case("weight .9")["wt_kg_T"] == 0.9
    assert case("age not a number")["age_years_T"] is None
    assert case("age in an unknown unit")["age_years_T"] is None


def test_weight_is_read_in_kilograms_and_impossible_weights_are_none(case):
    units = rulebook.value("weight-in-kg", "units")
    times, over = units["LBS"]
    assert case("weight in pounds")["wt_kg_T"] == 154 * times / over
    assert case("weight in grams")["wt_kg_T"] == 3.5
    assert case("weight at the top")["wt_kg_T"] == rulebook.value("weight-in-kg", "max_kg")
    for what in (
        "weight zero",
        "weight over the top",
        "weight with no unit",
        "weight in an unknown unit",
    ):
        assert case(what)["wt_kg_T"] is None, what


def test_each_age_falls_in_its_band_and_its_edges_hold(case):
    bands = [b["id"] for b in rulebook.value("age-bands", "bands")]
    newborn, infant, under_one = bands[:3]
    assert rulebook.value("age-bands", "zero_age_band") == under_one
    want = {
        "0 days": newborn,
        "27 days": newborn,
        "28 days": infant,
        "4 weeks": infant,
        "672 hours": infant,
        "23 months": infant,
        "1.9 years": infant,
        "24 months": bands[3],
        "85 years": bands[-1],
        "age in an unknown unit": None,
    }
    assert {what: case(what)["age_band_T"] for what in want} == want
    assert case("age with no unit")["age_band_T"] == case("age 60.")["age_band_T"] is not None


def test_an_age_of_0_years_goes_by_the_senders_age_group(case):
    newborn, infant, under_one = [b["id"] for b in rulebook.value("age-bands", "bands")[:3]]
    assert case("0 years, neonate")["age_band_T"] == newborn
    assert case("0 years, infant")["age_band_T"] == infant
    assert case("0 years, no group")["age_band_T"] == under_one
    assert case("0 decades, adult")["age_band_T"] == under_one
    assert case("0 with no unit, neonate")["age_band_T"] == newborn


def test_the_three_youngest_bands_together_are_every_case_under_2(demo_rel):
    young = [b["id"] for b in rulebook.value("age-bands", "bands")[:3]]
    marks = ", ".join(f"'{b}'" for b in young)
    banded = {
        k for (k,) in demo_rel.rows(f"SELECT caseid FROM demo_T WHERE age_band_T IN ({marks})")
    }
    under = {k for (k,) in demo_rel.rows("SELECT caseid FROM demo_T WHERE age_years_T < 2")}
    assert banded == under and len(under) > 10
    assert demo_rel.rows(
        "SELECT count(*) FROM demo_T WHERE age_years_T IS NOT NULL AND age_band_T IS NULL"
    ) == [(0,)]


def test_no_country_words_are_no_country_and_a1_falls_back_to_the_reporter(case):
    assert (case("occurrence A1")["country_T"], case("occurrence A1")["occr_country"]) == (
        "FR",
        "A1",
    )
    assert case("occurrence A1")["country_source_T"] == "as published"
    no = case("country not specified")
    assert (no["country_T"], no["country_source_T"]) == (None, None)
    assert no["reporter_country"] == "COUNTRY NOT SPECIFIED"  # FDA's text stays


def test_an_eu_case_takes_its_member_state_from_the_latest_earlier_version(case):
    code = rulebook.value("eu-member-state", "code")
    got = {
        what: (case(what)["country_T"], case(what)["country_source_T"])
        for what in (
            "EU, earlier version DE",
            "EU, two earlier versions",
            "EU, earlier version not an ISO code",
            "EU alone",
        )
    }
    assert got == {
        "EU, earlier version DE": ("DE", "earlier version"),
        "EU, two earlier versions": ("IT", "earlier version"),
        "EU, earlier version not an ISO code": (code, "as published"),
        "EU alone": (code, "as published"),
    }
    assert case("EU, earlier version DE")["occr_country"] == code  # FDA's value stays


def test_duplicates_never_match_on_no_country_and_borrowing_never_splits_a_group(demo_rel):
    cases = _by_case(demo_rel)
    none = [cases[r.caseid] for r in fakefda.DEMOGRAPHICS_PAIRS["no country"]]
    assert [c["dup_group_T"] for c in none] == [None, None]
    eu = [cases[r.caseid] for r in fakefda.DEMOGRAPHICS_PAIRS["EU"]]
    assert [c["country_T"] for c in eu] == ["DE", rulebook.value("eu-member-state", "code")]
    assert eu[0]["dup_group_T"] is not None and eu[0]["dup_group_T"] == eu[1]["dup_group_T"]


def test_switched_off_no_country_words_are_countries_and_eu_stays(country_off_rel):
    cases = _by_case(country_off_rel)
    code = rulebook.value("eu-member-state", "code")
    assert set(country_off_rel.manifest["user_rules"]["off"]) == COUNTRY_RULES
    eu = cases[fakefda.DEMOGRAPHICS["EU, earlier version DE"].caseid]
    assert (eu["country_T"], eu["country_source_T"]) == (code, "as published")
    a1 = cases[fakefda.DEMOGRAPHICS["occurrence A1"].caseid]
    assert a1["country_T"] == "A1"
    none = [cases[r.caseid] for r in fakefda.DEMOGRAPHICS_PAIRS["no country"]]
    assert none[0]["country_T"] == "COUNTRY NOT SPECIFIED"
    assert none[0]["dup_group_T"] is not None and none[0]["dup_group_T"] == none[1]["dup_group_T"]
