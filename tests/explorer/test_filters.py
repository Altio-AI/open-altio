"""The filters (filters.py), and the reactions a page adds to them (explore.py's Scope), each
asked through the count line and the case list the page reads. How the product and drugs a page
adds count is test_drugs.py's.

What each filter should return is read from the release's own Parquet through `rel`,
written here as plain SQL over `case_latest_T` and its child tables, so the explorer is
checked against the release and not against itself. Defaults come from rules era-filter,
dedup-default and age-bands.
"""

from __future__ import annotations

import pytest

from open_altio.explorer.filters import DIRECT_WORDS, parse
from open_altio.faers.derive import direct_report
from open_altio.rulebook import value
from open_altio.testing import fakefda
from open_altio.testing.releasereader import ReleaseReader

# Canada as FAERS codes it, or as legacy AERS names it (rules/legacy-country.md)
CANADA = "coalesce(c.occr_country, c.reporter_country) IN ('CA', 'CANADA')"


def drug_where(cond: str) -> str:
    return (
        f"EXISTS (SELECT 1 FROM drug_latest_T d WHERE {ReleaseReader.case_join('d')} AND ({cond}))"
    )


def era_value(era: str) -> str:
    """The era as rule era-filter names it."""
    return {"legacy": "AERS", "faers": "FAERS"}[era]


@pytest.fixture
def listed(ask):
    """listed(client, **filters): era/case_key of every case the list holds, page after page."""

    def every_page(client, **params) -> list[str]:
        out, page = [], 1
        while True:
            got = ask(client, "/api/cases", page=page, **params)
            out += [f"{c['era_T']}/{c['case_key_T']}" for c in got["cases"]]
            if len(got["cases"]) < got["size"]:
                return out
            page += 1

    return every_page


@pytest.fixture
def check(ask, listed):
    """check(client, want, **filters): the count line and the case list both hold `want`."""

    def holds(client, want: set[str], **params) -> None:
        assert ask(client, "/api/summary", **params)["cases"] == len(want)
        assert set(listed(client, **params)) == want

    return holds


# defaults: both eras, kept cases only ---------------------------------------------------


def test_default_view_is_every_kept_case_of_both_eras(client, rel, ask, check):
    check(client, rel.case_keys())
    assert (
        ask(client, "/api/summary")["cases"] == rel.step("kept_after_duplicates")["count"]["total"]
    )
    assert set(ask(client, "/api/summary")["by_era"]) == {"legacy", "faers"}


def test_kept_cases_only_is_the_default_dedup_choice(client, ask):
    assert value("dedup-default", "explorer_default") == "kept_only"
    assert ask(client, "/api/summary")["kept_only"] is True


def test_including_flagged_duplicates_counts_every_case(client, rel, ask, check):
    want = rel.case_keys(duplicates=True)
    check(client, want, dedup="all")
    every = rel.step("after_deleted_lists")["count"]["total"]
    assert ask(client, "/api/summary", dedup="all")["cases"] == every
    set_aside = rel.case_keys("NOT c.dup_kept_T", duplicates=True)
    assert set_aside and set_aside <= want
    rows = {
        f"{c['era_T']}/{c['case_key_T']}": c
        for c in ask(client, "/api/cases", dedup="all")["cases"]
    }
    for case in set_aside & set(rows):
        assert rows[case]["dup_kept_T"] is False


def test_counts_say_how_many_duplicates_were_set_aside(client, rel, ask):
    set_aside = rel.case_keys("NOT c.dup_kept_T", duplicates=True)
    assert ask(client, "/api/summary")["set_aside"] == len(set_aside)


@pytest.mark.parametrize("era", ["legacy", "faers"])
def test_one_era_alone_holds_only_that_eras_cases(client, rel, check, era):
    check(client, rel.case_keys(eras=(era,)), f="1", era=era_value(era))


def test_no_era_ticked_finds_nothing(client, ask):
    assert ask(client, "/api/summary", f="1")["cases"] == 0


# each filter narrows ---------------------------------------------------------------


def test_drug_matches_the_name_or_the_active_ingredient_however_typed(client, rel, check):
    want = rel.case_keys(
        drug_where("d.drugname_norm_T = 'ASPIRIN' OR d.prod_ai_norm_T = 'ASPIRIN'")
    )
    check(client, want, drug=" aspirin. ")
    assert "faers/9004004" in want  # named BAYER LOW DOSE, active ingredient ASPIRIN


def test_a_drug_is_found_by_its_brand_name(client, check):
    check(client, {"faers/9004004"}, drug="Bayer Low Dose")


@pytest.mark.parametrize(
    "drug, roles, want",
    [
        ("ASPIRIN", ["I"], {"faers/9006006"}),
        ("IBUPROFEN", ["SS"], {"faers/9006006"}),
        ("IBUPROFEN", ["PS"], {"legacy/5100005"}),
        ("OMEPRAZOLE", ["C"], {"faers/9005005"}),
        ("OMEPRAZOLE", ["PS", "SS"], set()),
    ],
)
def test_drug_role_narrows_the_drug(client, check, drug, roles, want):
    check(client, want, drug=drug, role=roles)


def test_role_alone_means_any_drug_in_that_role(client, rel, check):
    check(client, rel.case_keys(drug_where("d.role_cod IN ('SS', 'I')")), role=["SS", "I"])


def test_reaction_term_matches_regardless_of_case(client, check):
    check(client, {"faers/9007007"}, reaction="hepatic enzyme INCREASED")
    check(client, {"faers/9007007"}, reaction="HEPATIC ENZYME increased")


def test_chosen_preferred_terms_count_a_case_with_any_of_them(client, rel, check):
    want = rel.case_keys(
        f"EXISTS (SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')} "
        "AND lower(r.pt) IN ('nausea', 'vomiting'))",
    )
    check(client, want, pt=["NAUSEA", "vomiting"])


def test_reaction_matches_only_the_latest_version_of_a_case(client, rel, check):
    want = rel.case_keys(
        f"EXISTS (SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')} AND r.pt = 'Nausea')",
    )
    check(client, want, reaction="Nausea")
    assert "faers/9005005" not in want  # Nausea in 2019q1, Vomiting in the version kept


def test_received_dates_are_the_groups_first_receipt(client, rel, check, listed):
    in_2019 = {"received_from": "2019-01-01", "received_to": "2019-12-31"}
    check(
        client,
        rel.case_keys("c.group_first_dt_T BETWEEN DATE '2019-01-01' AND DATE '2019-12-31'"),
        **in_2019,
    )
    # 9021021 was received in 2026, but it is the shown copy of a group first received in 2019
    assert "faers/9021021" in listed(client, **in_2019)


def test_event_date_range_leaves_out_partial_dates(client, rel, check):
    want = rel.case_keys("c.event_dt_T BETWEEN DATE '2012-01-01' AND DATE '2018-12-31'")
    check(client, want, event_from="2012-01-01", event_to="2018-12-31")
    assert "legacy/5100002" not in want  # event date given as the year 2012 only


def test_country_is_the_occurrence_country_else_the_reporters_a_legacy_name_as_its_code(
    client, rel, check
):
    check(client, rel.case_keys(CANADA), country="CA")
    every = rel.case_keys(CANADA, duplicates=True)
    # reported from CANADA in legacy AERS, set aside for its FAERS copy
    assert "legacy/5100008" in every
    check(client, every, country="CA", dedup="all")
    # group B shows its later caseid; 9130013's event country is not specified, so its reporter's
    # stands in (rule country-not-given)
    check(client, {"faers/9023023", "faers/9130013"}, country="GB")


def test_not_given_finds_the_cases_with_no_country(client, rel, check):
    check(
        client,
        rel.case_keys("coalesce(c.occr_country, c.reporter_country) IS NULL"),
        country="_none",
    )


def test_sex_is_f_or_m_and_not_given_is_a_choice(client, rel, check):
    check(client, rel.case_keys("c.sex_T = 'M'"), sex="M")
    not_given = rel.case_keys("c.sex_T IS NULL")
    # a blank sex and NS both read Not given; NS is no choice of its own
    assert {"faers/9026026", "faers/9130013"} <= not_given
    check(client, not_given, sex="_none")
    check(client, set(), sex="NS")
    check(client, rel.case_keys("c.sex_T IS NOT NULL"), sex=["F", "M"])


def test_age_bands_follow_the_rule(client, rel, check):
    for band in value("age-bands", "bands"):
        check(client, rel.case_keys(f"c.age_band_T = '{band['id']}'"), age=band["id"])


def test_age_bands_combine_and_not_given_is_a_band(client, rel, check):
    young = [b["id"] for b in value("age-bands", "bands")[:3]]
    want = rel.case_keys("c.age_years_T < 2")
    check(client, want, age=young)
    assert "legacy/5100002" in want  # 18 months
    not_given = rel.case_keys("c.age_years_T IS NULL")
    check(client, not_given, age="_none")
    assert "faers/9130013" in not_given  # a filler age of 999 reads Not given


def test_any_chosen_outcome_counts_a_case(client, check):
    check(client, {"faers/9013013"}, outcome="DE")
    check(client, {"faers/9013013", "faers/9005005"}, outcome=["HO", "DE"])


def test_reporter_type_is_the_e2b_qualification_and_not_given_is_a_choice(client, rel, check):
    type_of = dict(rel.rows("SELECT DISTINCT occp_cod, reporter_type_T FROM case_latest_T"))
    check(client, {"faers/9110011"}, reporter=type_of["CN"])
    check(client, {"legacy/5100005"}, reporter=type_of["LW"])
    # FDA's OT before 2020, HP after and RN are one type; a code FDA does not list has none
    check(client, rel.case_keys("c.occp_cod IN ('OT', 'HP', 'RN')"), reporter=type_of["HP"])
    check(client, {"faers/9120012", "faers/9007007"}, reporter="_none")
    check(client, rel.case_keys("c.occp_cod = 'MD'"), reporter=type_of["MD"])
    check(client, set(), reporter="MD")  # FDA's own code is not a type


def test_sender_matches_regardless_of_case(client, check):
    check(client, {"faers/9110011"}, sender="  beta labs ltd ")


def test_a_sender_finds_every_case_of_its_company_by_name_or_any_of_fdas_spellings(
    client, rel, check
):
    [(company,)] = rel.rows("SELECT company_T FROM case_latest_T WHERE case_key_T = '9120012'")
    lilly = rel.case_keys("c.company_T = ?", company)
    # the legacy case sent under one of its spellings counts under the company too
    assert lilly == {"faers/9002002", "faers/9120012", "legacy/5100002"}
    check(client, lilly, sender=company.lower())
    check(client, lilly, sender=fakefda.LILLY[1])
    check(client, lilly, sender=fakefda.LILLY[0])
    direct_sql = direct_report("c.rept_cod")
    check(client, rel.case_keys(f"c.company_T IS NULL AND NOT {direct_sql}"), sender="_none")
    # the reports sent straight to FDA, whatever FDA wrote as their sender
    direct = rel.case_keys(direct_sql)
    assert direct == {"faers/9004004"}
    check(client, direct, sender="_direct")
    # typed as FDA's own intake or as the words the explorer shows for them, case-blind
    check(client, direct, sender=f" {value('company-names', 'fda_sender').lower()} ")
    check(client, direct, sender=DIRECT_WORDS.upper())
    typed = parse({"sender": [value("company-names", "fda_sender")]})
    assert ("Company", DIRECT_WORDS) in typed.described()
    check(client, set(), sender="unknown manufacturer")


def test_filters_combine_and_each_narrows_the_others(client, rel, check):
    want = rel.case_keys(
        drug_where("d.drugname_norm_T = 'ASPIRIN' OR d.prod_ai_norm_T = 'ASPIRIN'")
        + " AND c.sex = 'F' AND c.group_first_dt_T >= DATE '2019-01-01'",
        eras=("faers",),
    )
    check(client, want, drug="aspirin", sex="F", received_from="2019-01-01", era=["FAERS"], f="1")
    assert want and want < rel.case_keys(eras=("faers",))


def test_a_value_that_is_not_a_date_is_ignored(client, rel, check):
    check(client, rel.case_keys(), received_from="2019-13-45")


def test_typed_text_is_only_ever_a_value(client, rel, check):
    check(client, set(), drug="x' OR 1=1 --", sender="'; DROP TABLE explorer_case_T; --")
    check(client, set(), pt="x' OR 1=1 --")
    check(client, rel.case_keys())
