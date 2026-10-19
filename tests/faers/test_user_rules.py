"""A release built under a person's own rules (rules.toml): every data rule that can be switched
off leaves the data as if it were not there, every value they set reaches the build, and the
release records what differs from Altio's standard."""

from __future__ import annotations

import json

import pytest

from open_altio import rulebook
from open_altio.faers import ReleaseError, build_release
from open_altio.rulebook import UserRules
from open_altio.testing import fakefda
from open_altio.testing.releasereader import ReleaseReader

# a rule of a step with one switch goes on and off with that switch, not alone
SWITCHABLE = [
    info.name
    for info in rulebook.catalogue()
    if not info.always_on and info.step.switch in (None, info.name)
]
ALWAYS_ON = [info.name for info in rulebook.catalogue() if info.always_on]


@pytest.fixture(scope="module")
def dup_input(tmp_path_factory):
    return fakefda.write_input(
        tmp_path_factory.mktemp("dup_zips"), quarters=fakefda.DUP_QUARTERS, story=fakefda.DUP_STORY
    )


def _built(input_dir, tmp_path_factory, rules: UserRules) -> ReleaseReader:
    return ReleaseReader(
        build_release(input_dir, tmp_path_factory.mktemp("releases"), user_rules=rules)
    )


@pytest.fixture(scope="module")
def off_rel(fake_input, tmp_path_factory):
    return _built(fake_input, tmp_path_factory, UserRules(off=frozenset(SWITCHABLE)))


@pytest.fixture(scope="module")
def dup_off_rel(dup_input, tmp_path_factory):
    return _built(dup_input, tmp_path_factory, UserRules(off=frozenset(SWITCHABLE)))


def _cases(rel) -> dict:
    return {r["case_key_T"]: r for r in rel.dicts("SELECT * FROM case_latest_T")}


def _grouped(cases: dict, *keys: str) -> bool:
    groups = {cases[k]["dup_group_T"] for k in keys}
    return len(groups) == 1 and None not in groups


# ------------------------------------------------------------- the rules that are always on
def test_the_rules_the_build_cannot_run_without_the_readings_and_the_statistics_are_on():
    cleaning = [i.name for i in rulebook.catalogue() if i.always_on and i.step.id != "statistics"]
    readings = ["age-bands", "age-in-years", "sex-codes", "weight-in-kg"]
    assert sorted(cleaning) == sorted(
        [
            "dup-shown-copy",
            "latest-version",
            "meddra-terms",  # one MedDRA version reads every term FDA wrote
            "not-given",
            "transformed-suffix-T",
            *readings,
        ]
    )
    assert all(i.always_on for i in rulebook.catalogue() if i.step.id == "statistics")


@pytest.mark.parametrize("name", ALWAYS_ON)
def test_switching_off_a_rule_that_is_always_on_is_refused_before_anything_is_built(
    name, fake_input, tmp_path
):
    with pytest.raises(ReleaseError, match="always on") as refused:
        build_release(fake_input, tmp_path, user_rules=UserRules(off=frozenset({name})))
    assert rulebook.data_rule(name).why_locked in str(refused.value)
    assert list(tmp_path.iterdir()) == []


def test_a_value_of_the_wrong_kind_is_refused_in_plain_words(fake_input, tmp_path):
    rules = UserRules(values={"dup-manufacturer-number": {"max_age_gap_years": "five"}})
    with pytest.raises(ReleaseError, match="max_age_gap_years must be a number"):
        build_release(fake_input, tmp_path, user_rules=rules)


# ------------------------------------------------------------- every switchable rule, off
def test_every_rule_but_the_three_can_be_switched_off(off_rel):
    assert off_rel.manifest["user_rules"] == {"off": SWITCHABLE, "changed": []}


def test_with_run_on_lines_off_a_glued_line_keeps_its_first_record_and_records_the_rest(off_rel):
    assert not rulebook.data_rule("overlong-lines").always_on
    assert off_rel.rows("SELECT drug_seq, drugname FROM drug WHERE primaryid = '4100010'") == [
        ("1", "BLEOMYCIN SULFATE")
    ]
    [line] = next(
        i for i in off_rel.manifest["inputs"] if (i["table"], i["quarter"]) == ("drug", "2012q3")
    )["overlong_lines"]
    assert line["records"] == 1 and "DOXORUBICIN" in line["dropped"]


def test_with_deleted_cases_off_no_listed_case_is_taken_out(off_rel):
    assert "deleted-cases" in off_rel.manifest["user_rules"]["off"]
    kept = {k for (k,) in off_rel.rows("SELECT caseid FROM case_latest_T WHERE caseid IS NOT NULL")}
    assert {"9008008", "9009009", "9010010", "5100007"} <= kept
    assert off_rel.step("after_deleted_lists")["removed"]["total"] == 0


def test_with_the_aeolus_rule_off_it_groups_no_cases(off_rel):
    assert rulebook.is_on("dedup-default")  # outside a build, Altio's standard
    assert off_rel.rows("SELECT count(*) FROM case_latest_T WHERE probable_duplicate_T") == [(0,)]
    assert off_rel.step("kept_after_duplicates")["removed"]["total"] == 0


def test_with_legacy_countries_off_a_legacy_name_stays_as_fda_wrote_it(off_rel):
    assert "legacy-country" in off_rel.manifest["user_rules"]["off"]
    assert dict(
        off_rel.rows(
            "SELECT DISTINCT reporter_country, country_T FROM demo_T "
            "WHERE era_T = 'legacy' AND reporter_country IS NOT NULL"
        )
    ) == {name: name for name in fakefda.LEGACY_COUNTRY.values()}


def test_with_company_names_off_each_sender_stays_as_fda_wrote_it(off_rel):
    assert "company-names" in off_rel.manifest["user_rules"]["off"]
    got = dict(off_rel.rows("SELECT case_key_T, company_T FROM case_latest_T"))
    assert (got["9002002"], got["9120012"]) == fakefda.LILLY
    assert got["9004004"] == "FDA-CTU"


def test_with_reporter_types_off_reporter_type_t_is_fdas_code(off_rel):
    assert "reporter-type" in off_rel.manifest["user_rules"]["off"]
    assert off_rel.rows(
        "SELECT count(*) FROM demo_T WHERE reporter_type_T IS DISTINCT FROM occp_cod"
    ) == [(0,)]
    assert off_rel.rows("SELECT count(*) FROM demo_T WHERE occp_cod = 'HP'")[0][0]


def test_with_reaction_terms_off_they_are_compared_as_written(off_rel):
    assert "reaction-term-case" in off_rel.manifest["user_rules"]["off"]
    assert off_rel.rows(
        "SELECT count(*) FROM reac_latest_T WHERE pt_norm_T IS DISTINCT FROM pt"
    ) == [(0,)]
    assert off_rel.rows("SELECT count(*) FROM reac_latest_T WHERE pt <> upper(pt)")[0][0] > 0


def test_with_legacy_spelling_off_legacy_terms_show_as_fda_wrote_them(off_rel):
    assert "legacy-term-spelling" in off_rel.manifest["user_rules"]["off"]
    assert off_rel.rows(
        "SELECT count(*) FROM reac_latest_T WHERE pt_spelling_T IS DISTINCT FROM pt"
    ) == [(0,)]
    assert off_rel.rows(
        "SELECT count(*) FROM indi_latest_T WHERE indi_pt_spelling_T IS DISTINCT FROM indi_pt"
    ) == [(0,)]


def test_with_the_manufacturer_number_off_it_groups_no_cases(dup_off_rel):
    cases = _cases(dup_off_rel)
    assert "dup-manufacturer-number" in dup_off_rel.manifest["user_rules"]["off"]
    assert not any(
        cases[k]["probable_duplicate_T"] for k in ("7701001", "7701002", "7711001", "7711002")
    )


def test_with_no_usable_drug_or_reaction_off_no_report_is_marked(dup_off_rel):
    assert "no-drug-or-reaction" in dup_off_rel.manifest["user_rules"]["off"]
    assert dup_off_rel.rows(
        "SELECT count(*) FROM case_latest_T WHERE no_drug_or_reaction_T "
        "OR serious_no_drug_or_reaction_T"
    ) == [(0,)]


def test_with_padded_dates_off_a_padded_date_counts_like_any_other(dup_input, tmp_path_factory):
    rel = _built(dup_input, tmp_path_factory, UserRules(off=frozenset({"dup-padded-event-dates"})))
    cases = _cases(rel)
    january = [r.caseid for r in fakefda.PADDED_GROUPS["january"]]
    assert _grouped(cases, *january)
    assert rel.rows("SELECT count(*) FROM case_dup_T WHERE dup_padded_date_T") == [(0,)]


# ------------------------------------------------------------- values set by the person
def test_deleted_cases_taken_out_of_faers_only_keep_listed_legacy_cases(
    fake_input, tmp_path_factory
):
    rel = _built(
        fake_input, tmp_path_factory, UserRules(values={"deleted-cases": {"eras": ["faers"]}})
    )
    kept = {k for (k,) in rel.rows("SELECT caseid FROM case_latest_T WHERE caseid IS NOT NULL")}
    assert "5100007" in kept  # a legacy AERS case on a list
    assert kept.isdisjoint({"9008008", "9009009", "9010010"})
    assert rel.manifest["user_rules"]["changed"] == [
        {
            "rule": "deleted-cases",
            "key": "eras",
            "standard": rulebook.value("deleted-cases", "eras"),
            "value": ["faers"],
        }
    ]


def test_a_case_counted_per_era_has_a_latest_version_in_each(fake_input, tmp_path_factory):
    rel = _built(
        fake_input, tmp_path_factory, UserRules(values={"latest-version": {"across_eras": False}})
    )
    assert sorted(rel.rows("SELECT era_T FROM demo_latest_T WHERE caseid = '5100010'")) == [
        ("faers",),
        ("legacy",),
    ]


def test_the_number_rule_takes_the_age_gap_and_the_sex_guard_it_is_given(
    dup_input, tmp_path_factory
):
    gap = rulebook.value("dup-manufacturer-number", "max_age_gap_years") + 1
    rules = UserRules(
        values={"dup-manufacturer-number": {"max_age_gap_years": gap, "clashing_sexes": []}}
    )
    cases = _cases(_built(dup_input, tmp_path_factory, rules))
    assert _grouped(
        cases, "7704001", "7704002"
    )  # ages one year more apart than the standard allows
    assert _grouped(cases, "7702001", "7702002")  # F and M, with sex not compared


def test_the_padded_date_guard_takes_the_group_size_and_senders_it_is_given(
    dup_input, tmp_path_factory
):
    size = rulebook.value("dup-padded-event-dates", "min_group_size")
    larger = _cases(
        _built(
            dup_input,
            tmp_path_factory,
            UserRules(values={"dup-padded-event-dates": {"min_group_size": size + 1}}),
        )
    )
    assert _grouped(larger, *[r.caseid for r in fakefda.PADDED_GROUPS["january"]])
    anyone = _cases(
        _built(
            dup_input,
            tmp_path_factory,
            UserRules(values={"dup-padded-event-dates": {"one_sender_only": False}}),
        )
    )
    assert not any(
        "aeolus" in (anyone[r.caseid]["dup_rule_T"] or [])
        for r in fakefda.PADDED_GROUPS["january_two_senders"]
    )


def test_empty_lists_of_unusable_names_and_terms_mark_nothing(dup_input, tmp_path_factory):
    rules = UserRules(
        values={"no-drug-or-reaction": {"unusable_drug_names": [], "no_event_terms": []}}
    )
    cases = _cases(_built(dup_input, tmp_path_factory, rules))
    assert not cases["7731001"][
        "no_drug_or_reaction_T"
    ]  # "No adverse event" now counts as a reaction
    assert not cases["7731003"]["no_drug_or_reaction_T"]  # and UNKNOWN as a drug


# ------------------------------------------------------------- what the release records
def test_a_release_built_with_altio_standard_records_no_differences(rel, release):
    methods = json.loads((release / "methods.json").read_text(encoding="utf-8"))
    assert rel.manifest["user_rules"] == methods["user_rules"] == {"off": [], "changed": []}


def test_the_release_records_its_differences_in_the_manifest_and_methods(
    fake_input, tmp_path_factory
):
    rules = UserRules(
        off=frozenset({"deleted-cases"}), values={"dedup-default": {"explorer_default": "all"}}
    )
    rel = _built(fake_input, tmp_path_factory, rules)
    methods = json.loads((rel.path / "methods.json").read_text(encoding="utf-8"))
    assert (
        rel.manifest["user_rules"]
        == methods["user_rules"]
        == {
            "off": ["deleted-cases"],
            "changed": [
                {
                    "rule": "dedup-default",
                    "key": "explorer_default",
                    "standard": rulebook.value("dedup-default", "explorer_default"),
                    "value": "all",
                }
            ],
        }
    )
    assert rulebook.from_differences(methods["user_rules"]) == rules
