"""drug_route_T, the cleaned route of each drug record (rule drug-route), on hand-made drug rows.

The families each value allows come from the reviewed table, so the cases here use values whose
sets the table makes plain: Subcutaneous is injected only, Oral is by_mouth or under_tongue, a
film-coated tablet is by_mouth or vaginal, eye drops are eye only."""

from __future__ import annotations

import dataclasses

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers import derive, route
from open_altio.rulebook import UserRules
from open_altio.testing.rules import rules_with

RULE = "drug-route"
Row = tuple[int, str | None, str | None, str | None]  # record, route, dose_form, drugname
UNKNOWN = route.families()[-1]


def cleaned(rows: list[Row]) -> list[tuple[str | None, str, str, str | None]]:
    """(route_T, route_source_T, route_family_T, route_families_T) per record, for rows of
    (record, route, dose_form, drugname)."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE drug_latest_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
        "drug_seq VARCHAR, route VARCHAR, dose_form VARCHAR, drugname VARCHAR, "
        "drugname_norm_T VARCHAR)"
    )
    con.executemany(
        "INSERT INTO drug_latest_T VALUES ('faers', ?, '2026q2', '1', ?, ?, ?, upper(?))",
        [(str(k), r, f, n, n) for k, r, f, n in rows],
    )
    route.build(con)
    return con.execute(
        f"SELECT {', '.join(route.COLUMNS)} FROM drug_route_T ORDER BY primaryid::INT"
    ).fetchall()


def one_each(values: list[tuple[str | None, str | None, str | None]]) -> list:
    return cleaned([(i, *v) for i, v in enumerate(values)])


def test_a_source_that_allows_one_family_decides_it():
    got = one_each(
        [
            ("Subcutaneous", None, None),
            (None, "Eye drops", None),
            (None, None, "Humira autoinjector"),
        ]
    )
    assert got == [
        ("058", "route", "injected", "injected"),
        (None, "dose_form", "eye", "eye"),
        (None, "drugname", "injected", "injected"),
    ]


def test_the_sources_that_say_something_intersect():
    got = one_each([("Oral", "Film-coated tablet", None), (None, "Tablet", "Humira pen")])
    assert got == [
        ("048", "route+dose_form", "by_mouth", "by_mouth"),
        (None, "dose_form+drugname", "by_mouth", "by_mouth"),
    ]


def test_a_value_that_allows_several_families_lists_them_and_the_family_stays_unknown():
    got = one_each([("Oral", None, None), (None, "Solution for injection", None)])
    assert got == [
        ("048", "route", UNKNOWN, "by_mouth;under_tongue"),
        (None, "dose_form", UNKNOWN, "eye;injected"),
    ]


def test_sources_that_contradict_each_other_give_every_family_they_name():
    got = one_each([("Vaginal", "Eye drops", None), ("Subcutaneous", "Nasal spray", None)])
    disagree = rulebook.value(RULE, "disagree")
    assert got == [
        ("067", disagree, UNKNOWN, "eye;vaginal"),
        ("058", disagree, UNKNOWN, "injected;nasal"),
    ]


def test_nothing_known_lists_no_family_and_keeps_what_fdas_route_said():
    got = one_each(
        [(None, None, None), ("Unknown", "Unspecified", "Aspirin"), ("Other", None, None)]
    )
    none = rulebook.value(RULE, "none")
    assert got == [
        (None, none, UNKNOWN, None),
        ("065", none, UNKNOWN, None),
        ("050", none, UNKNOWN, None),
    ]


def test_form_words_count_only_as_whole_words():
    got = one_each([(None, None, "Tabloid"), (None, None, "Capecitabine")])
    assert [r[2:] for r in got] == [(UNKNOWN, None)] * 2


def test_each_row_is_read_alone_and_the_record_takes_every_family_one_of_its_rows_could_be():
    tables = route.RouteTables.read()
    oral, topical = tables.families("route", "Oral"), tables.families("route", "Topical")
    assert oral and topical and len(oral & topical) == 1
    got = cleaned(
        [
            (1, "Intravenous (not otherwise specified)", None, "Infliximab"),
            (1, "Subcutaneous", None, "Infliximab"),
            (2, "Oral", "Film-coated tablet", "X"),
            (2, "Oral", "Film-coated tablet", "X"),
            (3, "Subcutaneous", None, "Y"),
            (3, "Vaginal", None, "Y"),
            (4, "Oral", None, "Z"),
            (4, "Topical", None, "Z"),
            (5, "Oral", "Film-coated tablet", "X"),
            (5, None, "Film-coated tablet", "X"),
            (6, "Vaginal", "Eye drops", "W"),
            (6, "Subcutaneous", None, "W"),
        ]
    )
    unknown_code, disagree = rulebook.value(RULE, "unknown_code"), rulebook.value(RULE, "disagree")
    assert got[:3] == [
        (unknown_code, "route", "injected", "injected"),
        ("048", "route+dose_form", "by_mouth", "by_mouth"),
        (unknown_code, "route", UNKNOWN, "injected;vaginal"),
    ]
    # two regimens, by mouth and on the skin: every family either row allows, never only the
    # one family the two rows share
    assert got[3] == (unknown_code, "route", UNKNOWN, ";".join(sorted(oral | topical)))
    assert got[3][3] != next(iter(oral & topical))
    # a row that says less is not narrowed by the record's other rows
    assert got[4] == ("048", "route+dose_form", UNKNOWN, "by_mouth;vaginal")
    # a row whose sources contradict each other gives their union, and the record says so
    assert got[5] == (unknown_code, disagree, UNKNOWN, "eye;injected;vaginal")


def test_drug_route_has_one_row_per_record_and_fails_on_none_repeated():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE drug_latest_T AS SELECT 'faers' era_T, (i % 3)::VARCHAR primaryid, "
        "'2026q2' quarter_T, '1' drug_seq, 'Oral' route, NULL::VARCHAR dose_form, "
        "'X' drugname_norm_T FROM range(9) t(i)"
    )
    route.build(con)
    assert con.execute(
        "SELECT count(*), count(DISTINCT (era_T, primaryid, quarter_T, drug_seq)) FROM drug_route_T"
    ).fetchone() == (3, 3)


def test_fda_rows_stay_as_they_were_and_only_drug_route_is_added():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE drug_latest_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
        "drug_seq VARCHAR, route VARCHAR, dose_form VARCHAR, drugname_norm_T VARCHAR)"
    )
    con.execute(
        "INSERT INTO drug_latest_T VALUES ('faers', '1', '2026q2', '1', ' Oral ', 'TABLET', 'X')"
    )
    route.build(con)
    assert con.execute("SELECT route, dose_form FROM drug_latest_T").fetchall() == [
        (" Oral ", "TABLET")
    ]
    tables = {t for (t,) in con.execute("SHOW TABLES").fetchall()}
    assert tables == {"drug_latest_T", route.TABLE}
    cols = [r[0] for r in con.execute(f"DESCRIBE {route.TABLE}").fetchall()]
    assert cols == [*route.KEY, *route.COLUMNS]


def test_a_changed_table_given_to_the_build_is_read_instead_of_the_reviewed_one():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE drug_latest_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
        "drug_seq VARCHAR, route VARCHAR, dose_form VARCHAR, drugname_norm_T VARCHAR)"
    )
    con.execute("INSERT INTO drug_latest_T VALUES ('faers', '1', '2026q2', '1', 'Oral', NULL, 'X')")
    reviewed = route.RouteTables.read()
    oral = reviewed.families("route", "Oral")
    assert oral is not None and len(oral) > 1
    kept = sorted(oral)[0]
    changed = dataclasses.replace(
        reviewed, sets={**reviewed.sets, ("route", "oral"): frozenset({kept})}
    )
    route.build(con, changed)
    assert con.execute("SELECT route_families_T FROM drug_route_T").fetchall() == [(kept,)]
    assert route.RouteTables.read().families("route", "Oral") == oral


def test_the_step_is_the_last_derive_step_and_its_table_ships():
    assert list(derive.statements(["2026q2"]))[-1] is route.build
    assert route.TABLE in derive.DERIVED_TABLES


def test_the_order_of_sources_orders_only_how_they_are_named(tmp_path):
    rows = [("Oral", "Film-coated tablet", None)]
    with rules_with(tmp_path, {RULE: {"sources": ["dose_form", "route", "drugname"]}}):
        assert one_each(rows) == [("048", "dose_form+route", "by_mouth", "by_mouth")]


def test_sources_must_be_the_three_fda_fields(tmp_path):
    with (
        rules_with(tmp_path, {RULE: {"sources": ["route", "dose_form"]}}),
        pytest.raises(ValueError, match="sources must be"),
    ):
        one_each([("Oral", None, None)])


def test_with_fill_in_off_only_fdas_route_is_read():
    rows = [("Oral", "Film-coated tablet", None), (None, "Tablet", "Aspirin tablets")]
    with rulebook.use_user_rules(UserRules(values={RULE: {"fill_in": False}})):
        assert one_each(rows) == [
            ("048", "route", UNKNOWN, "by_mouth;under_tongue"),
            (None, rulebook.value(RULE, "none"), UNKNOWN, None),
        ]


def test_switched_off_every_record_is_there_with_no_cleaned_route():
    rows = [(1, "Oral", "Tablet", "X"), (1, "Oral", None, "X"), (2, None, None, "Humira pen")]
    with rulebook.use_user_rules(UserRules(off=frozenset({RULE}))):
        got = cleaned(rows)
    assert got == [(None, rulebook.value(RULE, "none"), UNKNOWN, None)] * 2


@pytest.mark.parametrize(
    "rules",
    [UserRules(), UserRules(values={RULE: {"fill_in": False}}), UserRules(off=frozenset({RULE}))],
    ids=["on", "fill_in off", "switched off"],
)
def test_the_route_columns_are_text_and_families_sorted_and_joined_in_every_build(rules):
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE drug_latest_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
        "drug_seq VARCHAR, route VARCHAR, dose_form VARCHAR, drugname_norm_T VARCHAR)"
    )
    con.execute(
        "INSERT INTO drug_latest_T VALUES ('faers', '1', '2026q2', '1', 'Topical', NULL, 'X'), "
        "('faers', '2', '2026q2', '1', NULL, NULL, 'X')"
    )
    with rulebook.use_user_rules(rules):
        route.build(con)
    types = dict(
        con.execute(f"SELECT column_name, column_type FROM (DESCRIBE {route.TABLE})").fetchall()
    )
    assert {types[c] for c in route.COLUMNS} == {"VARCHAR"}
    for (families,) in con.execute(f"SELECT route_families_T FROM {route.TABLE}").fetchall():
        assert families is None or families == ";".join(sorted(set(families.split(";"))))


def test_the_fake_release_has_one_cleaned_route_per_drug_record(rel):
    keys = ", ".join(route.KEY)
    assert rel.rows(
        f"SELECT count(*) FROM (SELECT DISTINCT {keys} FROM drug_latest_T)"
    ) == rel.rows(f"SELECT count(*) FROM {route.TABLE}")
    repeated = f"SELECT {keys}, count(*) FROM {route.TABLE} GROUP BY ALL HAVING count(*) > 1"
    assert rel.rows(repeated) == []
    # its drugs are oral tablets: by mouth or under the tongue, as the route alone allows
    got = rel.rows(f"SELECT DISTINCT route_T, route_families_T FROM {route.TABLE}")
    assert got == [("048", "by_mouth;under_tongue")]
