"""Probable duplicates across cases, read from the release only.

The main fake release carries the AEOLUS groups in fakefda.DUPLICATES: A
within FAERS, B a tie on received date, C across AERS and FAERS, and
near-duplicates that must never be flagged (a missing sex; the 2004Q1 layout
with no country). The second fake release (`dup_rel`, fakefda.DUP_STORY)
carries the other duplicate rules: the manufacturer number with its two guards and
the missing country code, a chain across the two rules, the padded-date
guard, and reports with no usable drug or reaction.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from open_altio import rulebook
from open_altio.faers import build_release
from open_altio.faers.duplicates import reason_lines
from open_altio.faers.schema import CHILD_TABLES
from open_altio.rulebook import UserRules
from open_altio.testing import fakefda
from open_altio.testing.releasereader import ReleaseReader

README = Path(__file__).resolve().parents[2] / "src" / "open_altio" / "faers" / "README.md"
FLAGS = (
    "probable_duplicate_T",
    "dup_group_T",
    "dup_kept_T",
    "group_first_dt_T",
    "dup_rule_T",
    "dup_shown_case_T",
    "dup_other_cases_T",
    "no_drug_or_reaction_T",
    "serious_no_drug_or_reaction_T",
)

GROUPS = {
    "A": {("faers", "9020020"), ("faers", "9021021")},
    "B": {("faers", "9022022"), ("faers", "9023023")},
    "C": {("legacy", "5100008"), ("faers", "9024024"), ("faers", "9025025")},
}
# the latest received of each group; B ties on the received date, so the higher caseid
SHOWN = {("faers", "9021021"), ("faers", "9023023"), ("faers", "9025025")}
FIRST_RECEIVED = {"A": date(2019, 2, 10), "B": date(2019, 3, 5), "C": date(2012, 8, 10)}
ASIDE = {m for g in GROUPS.values() for m in g} - SHOWN


def _flags(rel) -> dict:
    return {
        (r["era_T"], r["case_key_T"]): r
        for r in rel.dicts(
            f"SELECT era_T, case_key_T, first_fda_dt_T, {', '.join(FLAGS)} FROM case_latest_T"
        )
    }


def _cases(rel) -> dict:
    """case_key_T -> its row of case_latest_T (the duplicate story is FAERS only)."""
    return {k: r for (_, k), r in _flags(rel).items()}


def _together(cases: dict, *keys: str) -> bool:
    groups = {cases[k]["dup_group_T"] for k in keys}
    return len(groups) == 1 and None not in groups


def _alone(cases: dict, *keys: str) -> bool:
    return all(
        not cases[k]["probable_duplicate_T"]
        and cases[k]["dup_kept_T"]
        and cases[k]["dup_group_T"] is None
        for k in keys
    )


# ------------------------------------------------------------- the AEOLUS rule
def test_cases_matching_on_every_field_are_flagged_as_one_group(rel):
    flags = _flags(rel)
    flagged = {k for k, r in flags.items() if r["probable_duplicate_T"]}
    assert flagged == set().union(*GROUPS.values())
    for members in GROUPS.values():
        assert len({flags[m]["dup_group_T"] for m in members}) == 1
    assert len({flags[next(iter(g))]["dup_group_T"] for g in GROUPS.values()}) == len(GROUPS)
    assert all(flags[m]["dup_rule_T"] == ["aeolus"] for m in flagged)


def test_the_latest_received_is_shown_and_the_group_dated_by_its_first(rel):
    flags = _flags(rel)
    assert {k for k in set().union(*GROUPS.values()) if flags[k]["dup_kept_T"]} == SHOWN
    # every case not set aside is shown, flagged or not
    assert {k for k, r in flags.items() if not r["dup_kept_T"]} == ASIDE
    for name, members in GROUPS.items():
        shown = next(iter(members & SHOWN))
        for m in members:
            assert flags[m]["group_first_dt_T"] == FIRST_RECEIVED[name]
            assert flags[m]["dup_shown_case_T"] == shown[1]
        assert sorted(flags[shown]["dup_other_cases_T"]) == sorted(k for _, k in members - {shown})
    # the case's own receipt is unchanged; a case in no group is dated by it
    assert flags[("faers", "9021021")]["first_fda_dt_T"] == date(2026, 5, 15)
    for r in flags.values():
        if not r["probable_duplicate_T"]:
            assert r["group_first_dt_T"] == r["first_fda_dt_T"]
            assert (r["dup_rule_T"], r["dup_shown_case_T"], r["dup_other_cases_T"]) == (
                None,
                None,
                None,
            )


def test_a_null_in_any_matching_field_is_never_compared_by_the_aeolus_rule(rel):
    flags = _flags(rel)
    # 9026026 matches group A but has no sex, and was received first
    assert flags[("faers", "9026026")]["probable_duplicate_T"] is False
    assert flags[("faers", "9026026")]["dup_group_T"] is None
    assert flags[("faers", "9026026")]["dup_kept_T"] is True
    # 5100009 matches group C in the 2004Q1 layout, which publishes no country
    assert flags[("legacy", "5100009")]["probable_duplicate_T"] is False
    assert flags[("legacy", "5100009")]["dup_kept_T"] is True
    # a case without a full key is never grouped by the AEOLUS rule
    for r in rel.dicts(
        "SELECT c.dup_rule_T FROM case_dup_T d JOIN case_latest_T c "
        "USING (era_T, case_key_T) WHERE d.dup_key_T IS NULL"
    ):
        assert "aeolus" not in (r["dup_rule_T"] or [])


# Pairs that match on every field but one, which reads Not given in both (rules not-given,
# sex-codes, country-not-given); the last pair gives every field and is one group.
_PAIR = dict(
    event_dt="20190301", age="44", age_cod="YR", sex="M", country="DE", reacs=["Dizziness"]
)
NOT_GIVEN_PAIRS = {
    "sex": {"sex": "NS"},
    "country": {"country": "COUNTRY NOT SPECIFIED"},
    "age": {"age": "999"},
    "given": {},
}
NOT_GIVEN_STORY = [
    fakefda.R(
        "2019q1",
        f"79{i}{n}1",
        f"79{i}{n}",
        f"2019031{n}",
        drugs=[fakefda.Drug(f"DRUG {i}", "")],
        **{**_PAIR, **changed},
    )
    for i, changed in enumerate(NOT_GIVEN_PAIRS.values())
    for n in (1, 2)
]


@pytest.fixture(scope="module")
def not_given_rel(tmp_path_factory: pytest.TempPathFactory) -> ReleaseReader:
    zips = fakefda.write_input(
        tmp_path_factory.mktemp("not_given_zips"), quarters=("2019q1",), story=NOT_GIVEN_STORY
    )
    return ReleaseReader(build_release(zips, tmp_path_factory.mktemp("not_given_releases")))


def test_a_value_that_reads_not_given_is_never_compared_by_the_aeolus_rule(not_given_rel):
    rows = {
        r["case_key_T"]: r
        for r in not_given_rel.dicts(
            "SELECT c.case_key_T, d.dup_key_T, c.dup_group_T FROM case_dup_T d "
            "JOIN case_latest_T c USING (era_T, case_key_T)"
        )
    }
    for i, name in enumerate(NOT_GIVEN_PAIRS):
        pair = [rows[f"79{i}{n}"] for n in (1, 2)]
        if name == "given":
            assert all(r["dup_key_T"] for r in pair)
            assert pair[0]["dup_group_T"] is not None
            assert pair[0]["dup_group_T"] == pair[1]["dup_group_T"]
        else:
            assert all(r["dup_key_T"] is None and r["dup_group_T"] is None for r in pair), name


def test_matching_works_across_aers_and_faers(rel):
    flags = _flags(rel)
    group_c = {flags[m]["dup_group_T"] for m in GROUPS["C"]}
    assert len(group_c) == 1 and None not in group_c
    assert {era for era, _ in GROUPS["C"]} == {"legacy", "faers"}


# ------------------------------------------------------------- the manufacturer number
def test_the_same_number_from_the_same_sender_is_one_group_in_any_letter_case(dup_rel):
    cases = _cases(dup_rel)
    assert _together(cases, "7701001", "7701002")
    assert cases["7701001"]["dup_rule_T"] == ["manufacturer_number"]
    assert _alone(cases, "7706001")  # the same number from another sender


def test_a_number_group_whose_cases_clash_on_sex_is_skipped(dup_rel):
    cases = _cases(dup_rel)
    assert rulebook.value("dup-manufacturer-number", "clashing_sexes") == ["M", "F"]
    assert _alone(cases, "7702001", "7702002")  # F and M
    assert _together(cases, "7703001", "7703002")  # F and UNK: UNK counts as empty


def test_a_number_group_whose_ages_differ_by_more_than_the_gap_is_skipped(dup_rel):
    cases = _cases(dup_rel)
    assert _alone(cases, "7704001", "7704002")  # the gap plus one year
    # 30 years and 360 months are one age; an empty age never triggers the guard
    assert _together(cases, "7705001", "7705002", "7705003")


def test_a_number_without_its_country_code_joins_the_coded_number(dup_rel):
    cases = _cases(dup_rel)
    assert _together(cases, "7711001", "7711002")
    assert cases["7711001"]["dup_rule_T"] == ["manufacturer_number_country_code"]
    keys = dict(
        dup_rel.rows(
            "SELECT case_key_T, dup_number_key_T FROM case_dup_T "
            "WHERE case_key_T IN ('7711001', '7711002')"
        )
    )
    assert keys["7711001"] == keys["7711002"] == "ACME PHARMA, INC.|US-ACME-P1"


def test_two_country_codes_never_match_and_a_bare_number_never_chains_them(dup_rel):
    # ACME-P2 is written by the sender as US-ACME-P2 and as CA-ACME-P2: nothing matches
    assert _alone(_cases(dup_rel), "7712001", "7712002", "7712003")


# ------------------------------------------------------------- the two rules together
def test_groups_of_the_two_rules_that_share_a_case_are_one_group(dup_rel):
    cases = _cases(dup_rel)
    # 7721001-7721002 by the AEOLUS rule, 7721002-7721003 by the number
    assert _together(cases, "7721001", "7721002", "7721003")
    assert cases["7721001"]["dup_rule_T"] == ["aeolus"]
    assert cases["7721002"]["dup_rule_T"] == ["aeolus", "manufacturer_number"]
    assert cases["7721003"]["dup_rule_T"] == ["manufacturer_number"]
    # the latest received is shown, the whole group dated by the earliest
    assert [k for k in ("7721001", "7721002", "7721003") if cases[k]["dup_kept_T"]] == ["7721003"]
    assert {cases[k]["group_first_dt_T"] for k in ("7721001", "7721002", "7721003")} == {
        date(2019, 3, 5)
    }
    assert cases["7721003"]["first_fda_dt_T"] == date(2026, 5, 1)
    assert cases["7721003"]["dup_other_cases_T"] == [
        "7721001",
        "7721002",
    ]  # earliest received first


@pytest.mark.parametrize("which", ["rel", "dup_rel"])
def test_each_group_shows_its_latest_received_and_is_dated_by_its_first(which, request):
    rel = request.getfixturevalue(which)
    groups = rel.dicts("""
        SELECT dup_group_T, count(*) FILTER (WHERE dup_kept_T) AS shown,
               arg_max(case_key_T, (first_fda_dt_T, caseid)) AS latest,
               any_value(dup_shown_case_T) AS named,
               count(DISTINCT dup_shown_case_T) AS names, min(first_fda_dt_T) AS first,
               count(DISTINCT group_first_dt_T) AS dates, any_value(group_first_dt_T) AS dated,
               arg_max(case_key_T, dup_kept_T) AS kept, count(*) AS n,
               max(len(dup_other_cases_T)) AS others
        FROM case_latest_T WHERE probable_duplicate_T GROUP BY 1""")
    assert groups
    for g in groups:
        assert g["shown"] == 1 and g["names"] == 1 and g["kept"] == g["latest"] == g["named"], g
        assert g["dates"] == 1 and g["dated"] == g["first"], g
        assert g["n"] >= 2 and g["others"] == g["n"] - 1, g


def test_the_shown_copy_changes_nothing_but_which_copy_is_shown(dup_rel, tmp_path):
    """With shown_copy: earliest_received the groups and the number set aside
    are the same; only the shown copy moves."""
    assert rulebook.value("dup-shown-copy", "shown_copy") == "latest_received"
    zips = fakefda.write_input(
        tmp_path / "zips", quarters=fakefda.DUP_QUARTERS, story=fakefda.DUP_STORY
    )
    earliest = ReleaseReader(
        build_release(
            zips,
            tmp_path / "out",
            user_rules=UserRules(values={"dup-shown-copy": {"shown_copy": "earliest_received"}}),
        )
    )

    def groups(rel):
        return {
            frozenset(m)
            for (m,) in rel.rows(
                "SELECT list(case_key_T) FROM case_latest_T WHERE probable_duplicate_T "
                "GROUP BY dup_group_T"
            )
        }

    def shown(rel):
        return {
            k
            for (k,) in rel.rows(
                "SELECT case_key_T FROM case_latest_T WHERE probable_duplicate_T AND dup_kept_T"
            )
        }

    assert groups(earliest) == groups(dup_rel)
    assert (
        earliest.step("kept_after_duplicates")["count"]
        == dup_rel.step("kept_after_duplicates")["count"]
    )
    assert shown(earliest) != shown(dup_rel)
    assert "7721001" in shown(earliest) and "7721003" in shown(dup_rel)


# ------------------------------------------------------------- padded event dates
def test_a_padded_event_date_does_not_count_in_large_groups_from_one_sender(dup_rel):
    cases = _cases(dup_rel)
    size = rulebook.value("dup-padded-event-dates", "min_group_size")
    assert rulebook.value("dup-padded-event-dates", "one_sender_only") is True
    keys = {name: [r.caseid for r in group] for name, group in fakefda.PADDED_GROUPS.items()}
    # 1 January, one case below the size: still a group
    assert len(keys["january_below"]) == size - 1 and _together(cases, *keys["january_below"])
    # the 1st of another month counts at any size
    assert len(keys["first_of_march"]) == size and _together(cases, *keys["first_of_march"])
    # 1 January at the size from two senders, or with one sender blank: several companies
    # reporting one case, so they stay one group and the copies stay set aside
    for name in ("january_two_senders", "january_blank_sender"):
        assert len(keys[name]) == size and _together(cases, *keys[name]), name
        assert all(cases[k]["dup_rule_T"] == ["aeolus"] for k in keys[name])
        assert sum(not cases[k]["dup_kept_T"] for k in keys[name]) == size - 1
    # 1 January, a year alone and a month alone, at the size, one sender: the AEOLUS rule sets
    # nothing aside
    for name in ("january", "year", "month"):
        assert len(keys[name]) == size
        assert all("aeolus" not in (cases[k]["dup_rule_T"] or []) for k in keys[name]), name
    padded = {
        k for (k,) in dup_rel.rows("SELECT case_key_T FROM case_dup_T WHERE dup_padded_date_T")
    }
    assert padded == set(keys["january"] + keys["year"] + keys["month"])
    # the manufacturer number still groups two of them
    first, second, *rest = keys["january"]
    assert _together(cases, first, second) and cases[first]["dup_rule_T"] == ["manufacturer_number"]
    assert _alone(cases, *rest, *keys["year"], *keys["month"])


# ------------------------------------------------------------- no usable drug or reaction
def test_reports_with_no_usable_drug_or_reaction_are_flagged_and_never_set_aside(dup_rel):
    cases = _cases(dup_rel)
    assert (
        cases["7731001"]["no_drug_or_reaction_T"],
        cases["7731001"]["serious_no_drug_or_reaction_T"],
    ) == (True, True)
    assert (
        cases["7731002"]["no_drug_or_reaction_T"],
        cases["7731002"]["serious_no_drug_or_reaction_T"],
    ) == (True, False)
    assert (
        cases["7731003"]["no_drug_or_reaction_T"],
        cases["7731003"]["serious_no_drug_or_reaction_T"],
    ) == (True, True)
    assert (
        cases["7731004"]["no_drug_or_reaction_T"],
        cases["7731004"]["serious_no_drug_or_reaction_T"],
    ) == (False, False)
    assert _alone(cases, "7731001", "7731002", "7731003")
    flagged = {k for k, r in cases.items() if r["serious_no_drug_or_reaction_T"]}
    assert flagged == {"7731001", "7731003"}
    assert set(rulebook.value("no-drug-or-reaction", "serious_outcome_codes")) >= {"DE", "HO"}


# ------------------------------------------------------------- reason lines
def test_reason_lines_name_the_shown_copy_and_the_rules(dup_rel):
    cases = _cases(dup_rel)
    per_rule = rulebook.value("dup-shown-copy", "rule_lines")
    aside = reason_lines(cases["7721002"])
    assert aside[0] == rulebook.value("dup-shown-copy", "set_aside_line").format(
        shown_case="7721003"
    )
    assert "case 7721003" in aside[0]
    assert aside[1:] == [per_rule["aeolus"], per_rule["manufacturer_number"]]
    assert reason_lines(cases["7711001"])[1:] == [per_rule["manufacturer_number_country_code"]]
    shown = reason_lines(cases["7721003"])
    assert shown == [
        rulebook.value("dup-shown-copy", "shown_line").format(
            other_cases="cases 7721001 and 7721002", first_received="March 2019"
        )
    ]
    assert reason_lines(cases["7701002"]) == [
        rulebook.value("dup-shown-copy", "shown_line").format(
            other_cases="case 7701001", first_received="January 2019"
        )
    ]
    assert reason_lines(cases["7731001"]) == []


# ------------------------------------------------------------- what the release carries
def test_duplicates_are_flagged_never_deleted(rel):
    # every case of the grain is still in case_latest_T and in case_dup_T, once
    grain = rel.rows("SELECT count(*) FROM case_latest_T")[0][0]
    assert grain == rel.step("after_deleted_lists")["count"]["total"]
    assert rel.rows("SELECT count(*), count(DISTINCT (era_T, case_key_T)) FROM case_dup_T") == [
        (grain, grain)
    ]
    assert rel.rows(
        "SELECT count(*) FROM case_latest_T ANTI JOIN case_dup_T USING (era_T, case_key_T)"
    ) == [(0,)]
    for era, key in ASIDE:
        assert rel.rows(
            "SELECT count(*) FROM case_latest_T WHERE era_T = ? AND case_key_T = ?", era, key
        ) == [(1,)]
        assert (
            rel.rows(
                "SELECT count(*) FROM drug_latest_T d JOIN case_latest_T c "
                "USING (era_T, primaryid, quarter_T) WHERE c.case_key_T = ?",
                key,
            )[0][0]
            > 0
        )


@pytest.mark.parametrize("which", ["rel", "dup_rel"])
def test_case_dup_table_agrees_with_the_case_table_flags(which, request):
    rel = request.getfixturevalue(which)
    differ = " OR ".join(f"d.{f} IS DISTINCT FROM c.{f}" for f in FLAGS + ("caseid",))
    assert rel.rows(
        f"SELECT count(*) FROM case_dup_T d JOIN case_latest_T c USING (era_T, case_key_T) "
        f"WHERE {differ}"
    ) == [(0,)]


def test_kept_set_is_a_funnel_step_with_its_count(rel):
    step = rel.step("kept_after_duplicates")
    later = rel.funnel["steps"][rel.funnel["steps"].index(step) + 1 :]
    assert all(set(s["removed"].values()) == {0} for s in later)  # the last step that removes cases
    assert step["table"] == "case_dedup_T"
    # group C spans the eras and shows its FAERS copy, the latest received
    assert step["count"] == {"legacy": 5, "faers": 24, "total": 29}
    assert step["removed"] == {"legacy": 1, "faers": 3, "total": 4}
    assert rulebook.value("dedup-default", "cross_case_method") in step["label"]
    assert rel.rows("SELECT count(*) FROM case_dedup_T")[0][0] == step["count"]["total"]


@pytest.mark.parametrize("which", ["rel", "dup_rel"])
def test_the_funnel_says_what_the_duplicate_step_could_not_check(which, request):
    rel = request.getfixturevalue(which)
    dup = rel.funnel["duplicates"]
    ((cases, unchecked, aside, aeolus, number, padded_groups, padded_cases),) = rel.rows("""
        SELECT count(*), count(*) FILTER (WHERE d.dup_key_T IS NULL),
               count(*) FILTER (WHERE NOT c.dup_kept_T),
               count(*) FILTER (WHERE NOT c.dup_kept_T AND list_contains(c.dup_rule_T, 'aeolus')),
               count(*) FILTER (WHERE NOT c.dup_kept_T AND list_has_any(c.dup_rule_T,
                                ['manufacturer_number', 'manufacturer_number_country_code'])),
               count(DISTINCT d.dup_key_T) FILTER (WHERE d.dup_padded_date_T),
               count(*) FILTER (WHERE d.dup_padded_date_T)
        FROM case_dup_T d JOIN case_latest_T c USING (era_T, case_key_T)""")
    assert dup["cases"] == cases == rel.step("after_deleted_lists")["count"]["total"]
    assert dup["not_compared_by_aeolus"] == unchecked > 0
    assert dup["set_aside"] == aside == rel.step("kept_after_duplicates")["removed"]["total"]
    assert dup["set_aside_by_rule"] == {"aeolus": aeolus, "manufacturer_number": number}
    assert dup["padded_date_groups"] == {"groups": padded_groups, "cases": padded_cases}
    if which == "dup_rel":
        assert number > 0 and padded_groups == 3


def test_release_carries_deduplicated_views_for_the_explorer(rel):
    views = rel.manifest["views"]
    assert (rel.path / views["file"]).is_file()
    assert set(views["views"]) == {"case_dedup_T"} | {f"{t}_dedup_T" for t in CHILD_TABLES}
    for name, entry in views["views"].items():
        assert rel.rows(f"SELECT count(*) FROM {name}")[0][0] == entry["rows"], name
    kept = {(r[0], r[1]) for r in rel.rows("SELECT era_T, case_key_T FROM case_dedup_T")}
    assert kept == {
        (r[0], r[1])
        for r in rel.rows("SELECT era_T, case_key_T FROM case_latest_T WHERE dup_kept_T")
    }
    assert kept.isdisjoint(ASIDE) and kept >= SHOWN
    for t in CHILD_TABLES:
        expected = rel.rows(
            f"SELECT count(*) FROM {t}_latest_T a SEMI JOIN case_dedup_T c "
            "USING (era_T, primaryid, quarter_T)"
        )
        assert rel.rows(f"SELECT count(*) FROM {t}_dedup_T") == expected, t
    # the views file names tables only, never a path, so it works wherever the release is
    assert "parquet" not in (rel.path / views["file"]).read_text().lower()


def test_readme_documents_the_duplicate_flag(rel):
    readme = README.read_text(encoding="utf-8")
    for name in (
        "case_dup_T",
        "case_dedup_T",
        "dup_key_T",
        "dup_number_key_T",
        "dup_padded_date_T",
        "kept_after_duplicates",
        "views.sql",
    ) + FLAGS:
        assert f"`{name}`" in readme, name
