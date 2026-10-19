"""The reviewed route tables (rule drug-route): what they hold and what stops the build."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from open_altio import rulebook
from open_altio.faers.route import RouteTableError, RouteTables, families, label_families
from open_altio.faers.route.tables import SOURCES
from open_altio.testing.rules import rules_with

RULE = "drug-route"


def test_the_family_keys_are_the_ones_the_label_flags_use():
    assert families() == (
        "by_mouth",
        "under_tongue",
        "injected",
        "inhaled",
        "nasal",
        "rectal",
        "vaginal",
        "transdermal",
        "skin",
        "eye",
        "ear",
        "other",
        "unknown",
    )


def test_a_value_reads_as_its_set_in_any_case_and_spacing_and_an_unlisted_one_as_none():
    t = RouteTables.read()
    assert t.families("route", "  ORAL ") == {"by_mouth", "under_tongue"}
    assert t.families("dose_form", '"Film-coated tablet"') == {"by_mouth", "vaginal"}
    assert t.families("drugname", "PEN") == {"by_mouth", "injected"}
    assert t.families("route", "Unknown") == frozenset()  # listed, says nothing
    assert t.families("route", "by carrier pigeon") is None  # not listed


def test_every_source_has_values_and_the_label_rows_read_as_the_same_route_words():
    t = RouteTables.read()
    assert {s for s, _ in t.sets} == set(SOURCES)
    for (source, value), fams in t.sets.items():
        if source == "label":
            assert t.families("route", value) == fams, value


def test_a_label_is_in_every_family_its_routes_allow():
    t = RouteTables.read()
    assert t.label_families(["ORAL", "SUBLINGUAL"]) == {"by_mouth", "under_tongue"}
    assert t.label_families(["SUBCUTANEOUS"]) == {"injected"}
    assert t.label_families(["NOT APPLICABLE"]) == frozenset()
    assert label_families(["SUBCUTANEOUS", "INTRAVENOUS"]) == {"injected"}


def test_a_label_route_with_no_label_row_reads_as_the_route_word():
    t = RouteTables.read()
    assert t.families("label", "INTRACANALICULAR") is None
    assert t.label_families(["INTRACANALICULAR"]) == t.families("route", "intracanalicular")


def test_a_report_matches_a_label_when_their_families_overlap():
    t = RouteTables.read()
    tablet_report = t.families("dose_form", "Film-coated tablet") or frozenset()
    assert tablet_report & t.label_families(["ORAL"])
    assert not tablet_report & t.label_families(["OPHTHALMIC"])


def test_every_e2b_route_reads_as_itself_and_every_group_is_an_e2b_code():
    t = RouteTables.read()
    for code, name in t.e2b.items():
        assert t.code(name) == code, name
    assert set(t.atc_groups) <= set(t.e2b)
    assert t.atc_group(t.code("Intravenous drip")) == "injection"
    assert t.atc_group(t.code("Intrathecal")) is None


def _table(tmp_path: Path, header: str, rows: list[str]) -> Path:
    path = tmp_path / "table.csv"
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


FAMILIES_HEADER = "source,value,families,decided_by,reason"


@pytest.mark.parametrize(
    ("table", "header", "rows", "says"),
    [
        ("families_table", FAMILIES_HEADER, ["route,oral,by_mouth,,", "route,Oral,eye,,"], "twice"),
        ("families_table", FAMILIES_HEADER, ["route,oral,swallowed,,"], "not families"),
        ("families_table", FAMILIES_HEADER, ["form,tablet,by_mouth,,"], "not one of"),
        ("families_table", FAMILIES_HEADER, ["drugname,two words,by_mouth,,"], "not one word"),
        ("route_table", "route,code,evidence", ["oral,999,"], "not an E2B code"),
        ("route_table", "route,code,evidence", ["Oral,048,"], "not written as"),
    ],
)
def test_a_table_the_rule_cannot_read_stops_the_build(tmp_path, table, header, rows, says):
    bad = _table(tmp_path, header, rows)
    with (
        rules_with(tmp_path, {RULE: {table: str(bad)}}),
        pytest.raises(RouteTableError, match=says),
    ):
        RouteTables.read()


def test_the_families_table_holds_each_value_once_per_source_and_only_rule_families():
    with (rulebook.data_root() / rulebook.value(RULE, "families_table")).open(
        encoding="utf-8"
    ) as f:
        rows = list(csv.DictReader(f))
    assert rows and len({(r["source"], r["value"]) for r in rows}) == len(rows)
    named = {x for r in rows for x in r["families"].split(";") if x}
    assert named <= set(families()[:-1])
