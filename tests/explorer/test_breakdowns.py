"""A drug and event pair's breakdowns (/api/breakdowns): each field's values, each share among
only the reports that give the field, in the window and before it. Each count is checked against
the release's own tables or against /api/events on the same question, and a share whose period
has no report giving the field is null, never 0.

Run over `breakdown_release` (open_altio.testing.fakefda.BREAKDOWN_STORY: valsartan and Headache,
before the newest quarter and in it, with the invented MedDRA 29.1).
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from open_altio import rulebook
from open_altio.explorer.access import LOCAL, Viewer
from open_altio.explorer.answers import answer
from open_altio.explorer.breakdowns import fields, lines
from open_altio.explorer.filters import NOT_GIVEN
from open_altio.explorer.meddra import ServedMeddra
from open_altio.explorer.questions import ask as ask_in_process
from open_altio.explorer.questions import open_release_data
from open_altio.faers import literature
from open_altio.faers.dates import received_day
from open_altio.testing.releasereader import ReleaseReader
from open_altio.testing.rules import rules_with

DRUG, EVENT = "valsartan", "Headache"
NEWEST = {"received_from": "2026-04-01", "received_to": "2026-06-30"}  # 2026q2, the newest quarter
PERIODS = ("before", "window")


@pytest.fixture(scope="module")
def brel(breakdown_release):
    return ReleaseReader(breakdown_release)


@pytest.fixture
def web(explorer_app, breakdown_release) -> TestClient:
    return TestClient(explorer_app(breakdown_release))


@pytest.fixture
def breakdowns(web, ask):
    return lambda status=200, **params: ask(
        web, "/api/breakdowns", status, **({"product": DRUG, "reaction": EVENT} | params)
    )


def line_of(got: dict, name: str) -> dict:
    [found] = [line for line in got["lines"] if line["field"] == name]
    return found


def value_in(line: dict, value: object) -> dict:
    [found] = [v for v in line["values"] if v["value"] == value]
    return found


def of_the_pair(rel: ReleaseReader) -> tuple[str, list]:
    """The condition over case_latest_T c for the drug and event's cases, kept or not, from the
    release's own tables: a reaction written as the event, and a drug record of the drug in the
    roles a product counts by default."""
    roles = list(rulebook.value("explorer-drug-counts", "default_roles"))
    return (
        f"EXISTS (SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')} AND lower(r.pt) = ?) "
        f"AND EXISTS (SELECT 1 FROM drug_latest_T d WHERE {rel.case_join('d')} "
        "AND upper(d.drugname) = ? AND list_contains(?, d.role_cod))",
        [EVENT.lower(), DRUG.upper(), roles],
    )


def kept_cases(rel: ReleaseReader, *, before: date) -> dict[str, list[dict]]:
    """The kept cases of the drug and event by period: in the newest quarter, or received before
    `before`."""
    pair, params = of_the_pair(rel)
    found = rel.dicts(
        f"SELECT c.*, c.{received_day()} AS day FROM case_latest_T c WHERE c.dup_kept_T AND {pair}",
        *params,
    )
    window = date.fromisoformat(NEWEST["received_from"])
    return {
        "before": [c for c in found if c["day"] < before],
        "window": [c for c in found if c["day"] >= window],
    }


def shares(cases: list[dict], column: str) -> tuple[int, dict]:
    """The cases giving `column` and each value's share of them."""
    given = [c[column] for c in cases if c[column] is not None]
    return len(given), {v: given.count(v) / len(given) for v in set(given)}


# each share among the reports that give the field ----------------------------------------------


def test_each_share_is_of_the_reports_that_give_the_field(breakdowns, brel):
    got = breakdowns()
    cases = kept_cases(brel, before=date.fromisoformat(NEWEST["received_from"]))
    for field, column in (
        ("sex", "sex_T"),
        ("age", "age_band_T"),
        ("country", "country_T"),
        ("reporter", "reporter_type_T"),
    ):
        line = line_of(got, field)
        for p in PERIODS:
            given, expected = shares(cases[p], column)
            assert line[p]["cases"] == len(cases[p]) and line[p]["given"] == given, (field, p)
            assert line[p]["given_share"] == given / len(cases[p]), (field, p)
            if given:
                found = {v["value"]: v[p]["share"] for v in line["values"] if v[p]["cases"]}
                assert found == expected, (field, p)


def test_a_period_no_report_gives_the_field_has_no_share_and_no_change_never_0(breakdowns):
    age = line_of(breakdowns(), "age")
    assert age["window"]["cases"] > 0 and age["window"]["given"] == 0
    assert age["window"]["given_share"] == 0  # the reports are there; none gives an age
    assert age["values"] and all(v["window"]["share"] is None for v in age["values"])
    assert all(v["change"] is None for v in age["values"])
    assert all(v["before"]["share"] for v in age["values"])
    # a window with no report at all has no Given in share either
    empty = breakdowns(received_from="2025-01-01", received_to="2025-03-31")
    for line in empty["lines"]:
        assert line["window"]["cases"] == 0 and line["window"]["given_share"] is None
        assert all(v["window"]["share"] is None and v["change"] is None for v in line["values"])


def test_half_the_reporters_blank_keeps_the_same_shares(breakdowns):
    every = line_of(breakdowns(), "reporter")
    assert every["window"]["given"] * 2 == every["window"]["cases"]
    given = sorted({v["value"] for v in every["values"]})
    only = line_of(breakdowns(reporter=given), "reporter")  # the blanks left out
    assert only["window"]["given_share"] == 1 and every["window"]["given_share"] == 0.5
    for v in every["values"]:
        assert value_in(only, v["value"])["window"]["share"] == v["window"]["share"]
        assert value_in(only, v["value"])["before"]["share"] == v["before"]["share"]


def outcome_codes(rel: ReleaseReader) -> dict[tuple, set[str]]:
    """Each case's outcome codes, from FDA's outcome rows, by era, primaryid and quarter."""
    codes: dict[tuple, set[str]] = defaultdict(set)
    for era, primaryid, quarter, code in rel.rows(
        "SELECT era_T, primaryid, quarter_T, outc_cod FROM outc_latest_T"
    ):
        codes[(era, primaryid, quarter)].add(code)
    return codes


def test_any_serious_outcome_counts_each_case_giving_an_outcome_once_and_none_the_rest(
    breakdowns, brel
):
    """FDA writes outcome rows only for serious outcomes, each one a code of rule
    serious-outcomes, so every report is either serious or gives no serious outcome."""
    cases = kept_cases(brel, before=date.fromisoformat(NEWEST["received_from"]))
    codes, serious = outcome_codes(brel), set(rulebook.value("serious-outcomes", "serious"))
    line = line_of(breakdowns(), "seriousness")
    gathered, none = value_in(line, fields.SERIOUS), value_in(line, NOT_GIVEN)
    for p in PERIODS:
        given = [codes[(c["era_T"], c["primaryid"], c["quarter_T"])] for c in cases[p]]
        assert (
            gathered[p]["cases"]
            == sum(bool(g) for g in given)
            == sum(bool(g & serious) for g in given)
        )
        assert none[p]["cases"] == sum(not g for g in given)
        assert gathered[p]["cases"] + none[p]["cases"] == line[p]["given"] == len(cases[p])
        assert gathered[p]["share"] + none[p]["share"] == pytest.approx(1)
    # a case with two outcomes counts once, under each of its codes and once as serious
    before = [codes[(c["era_T"], c["primaryid"], c["quarter_T"])] for c in cases["before"]]
    assert any(len(g) > 1 for g in before)
    each = sum(v["before"]["cases"] for v in line["values"] if v["value"] in serious)
    assert gathered["before"]["cases"] < each == sum(len(g) for g in before)


def test_dechallenge_u_and_rechallenge_d_in_the_filler_quarters_are_not_given(breakdowns, brel):
    filler = rulebook.value("not-given", "fields")["rechal"]["codes_in_quarters"]
    records = brel.dicts(
        "SELECT c.quarter_T, d.dechal, d.rechal FROM case_latest_T c JOIN drug_latest_T d "
        f"ON {brel.case_join('d')} WHERE c.dup_kept_T AND upper(d.drugname) = ? "
        f"AND d.role_cod = 'PS' AND c.{received_day()} < ?",
        DRUG.upper(),
        date.fromisoformat(NEWEST["received_from"]),
    )
    assert any(r["dechal"] == "U" for r in records)
    assert any(
        r["rechal"] == "D" and filler["from"] <= r["quarter_T"] <= filler["to"] for r in records
    )
    assert any(r["rechal"] == "D" and r["quarter_T"] > filler["to"] for r in records)
    got = breakdowns()
    dechal, rechal = line_of(got, "dechal"), line_of(got, "rechal")
    assert "U" not in {v["value"] for v in dechal["values"] + rechal["values"]}
    assert dechal["before"]["given"] == sum(r["dechal"] != "U" for r in records)
    real_d = sum(r["rechal"] == "D" and r["quarter_T"] > filler["to"] for r in records)
    assert value_in(rechal, "D")["before"]["cases"] == real_d
    assert rechal["before"]["given"] == sum(
        r["rechal"] in ("Y", "N") or (r["rechal"] == "D" and r["quarter_T"] > filler["to"])
        for r in records
    )


def test_pregnancy_has_no_given_in_share_and_is_not_available_without_meddra(
    breakdowns, breakdown_release
):
    pregnancy = line_of(breakdowns(), "pregnancy")
    assert [pregnancy[p]["given_share"] for p in PERIODS] == [None, None]
    assert value_in(pregnancy, "yes")["window"]["cases"] == 1  # the case naming Pregnancy
    data = open_release_data(breakdown_release, Viewer(id=LOCAL.id, meddra=False, who=False))
    got = ask_in_process("GET /api/breakdowns", data, {"product": [DRUG], "reaction": [EVENT]})
    assert got["not_available"]["pregnancy"] == data.why_no_smqs
    assert line_of(got, "pregnancy")["values"] == []
    assert line_of(got, "pregnancy")["window"]["given"] is None


def test_an_indication_counts_under_todays_term_once_a_case(breakdowns):
    taken = line_of(breakdowns(), "indication")
    headache = value_in(taken, "headache")  # FDA's Head pain and Headache, one term today
    assert headache["name"] == "Headache"
    assert headache["window"]["cases"] == 1  # one case gives both, on two of its records
    assert headache["before"]["cases"] == 1  # Head pain alone
    assert taken["before"]["given"] < taken["before"]["cases"]  # a case gives none


def test_a_record_field_is_read_from_the_products_records_and_others_are_other_drugs(
    breakdowns, brel
):
    got = breakdowns()
    onset = brel.rows(
        "SELECT o.time_to_onset_T FROM drug_onset_T o JOIN drug_latest_T d USING "
        "(era_T, primaryid, quarter_T, drug_seq) WHERE upper(d.drugname) = ? "
        "AND o.time_to_onset_T IS NOT NULL",
        DRUG.upper(),
    )
    days = line_of(got, "onset")
    assert sorted(v["value"] for v in days["values"]) == sorted(r[0] for r in onset)
    assert all(isinstance(v["value"], int) for v in days["values"])
    others = line_of(got, "other_drugs")
    assert value_in(others, "ibuprofen")["name"] == "Ibuprofen"
    assert value_in(others, "_none")["before"]["cases"] < others["before"]["cases"]
    assert DRUG not in {v["value"] for v in others["values"]}


def test_literature_counts_a_report_from_a_file_before_the_field_as_not_given(breakdowns, brel):
    """A report cites an article where FDA's literature reference is given; one from FDA's files
    before the field is Not given, so it lowers the Given in share and never counts as citing
    no article (rule literature-reference)."""
    first = literature.first_quarter()
    cases = kept_cases(brel, before=date.fromisoformat(NEWEST["received_from"]))
    assert any(c["quarter_T"] < first for c in cases["before"])
    line = line_of(breakdowns(), "literature")
    for p in PERIODS:
        given = [c for c in cases[p] if c["quarter_T"] >= first]
        cite = [c for c in given if c["lit_ref"]]
        assert line[p]["given"] == len(given), p
        found = {v["value"]: v[p]["cases"] for v in line["values"]}
        assert found.get(literature.CITES, 0) == len(cite), p
        assert found.get(literature.NO_ARTICLE, 0) == len(given) - len(cite), p
    assert line["before"]["given"] < line["before"]["cases"]
    assert value_in(line, literature.CITES)["window"]["cases"] == 1
    [pick] = [f.pick for f in fields.lines() if f.field == "literature"]
    assert pick == {"value": literature.CITES}  # the rule's pick is a value the line gives


def test_a_release_built_without_the_literature_reference_answers_it_not_available(
    breakdowns, no_literature_release
):
    """An explorer database built before its case table held lit_ref: the Literature line is Not
    available with the reason, shows no value and is never an alarm, and every other line is as
    on a release that holds it."""
    query = {"product": [DRUG], "reaction": [EVENT]}
    data = open_release_data(no_literature_release, LOCAL)
    got = ask_in_process("GET /api/breakdowns", data, query)
    assert got["not_available"]["literature"] == fields.NO_LITERATURE
    line = line_of(got, "literature")
    assert line["values"] == [] and line["window"]["given"] is None
    assert line["shown"] is None and line["alarm"] is None
    assert line["window"]["cases"] == got["cases"]["window"]
    held = breakdowns()
    assert "literature" not in held["not_available"]
    assert [x for x in got["lines"] if x["field"] != "literature"] == [
        x for x in held["lines"] if x["field"] != "literature"
    ]


def test_duplicates_count_the_copies_set_aside_over_every_case(breakdowns, brel):
    got = line_of(breakdowns(), "duplicates")
    before = date.fromisoformat(NEWEST["received_from"])
    pair, params = of_the_pair(brel)
    every = brel.rows(
        "SELECT count(*), count(*) FILTER (WHERE NOT c.dup_kept_T) FROM case_latest_T c "
        f"WHERE c.{received_day()} < ? AND {pair}",
        before,
        *params,
    )[0]
    assert (got["before"]["cases"], value_in(got, "set_aside")["before"]["cases"]) == every
    assert every[1] > 0


# the window and before -------------------------------------------------------------------------


def test_the_window_and_before_never_share_a_case(breakdowns, web, ask):
    got = breakdowns()
    assert got["window"] == {"from": NEWEST["received_from"], "to": NEWEST["received_to"]}
    day_before = date.fromisoformat(NEWEST["received_from"]) - timedelta(days=1)
    assert got["before"] == {"from": None, "to": day_before.isoformat()}
    events = ask(web, "/api/events", product=DRUG)
    [row] = [r for r in events["rows"] if r[0] == EVENT]
    assert got["cases"]["before"] + got["cases"]["window"] == row[1]
    # a case received the day before the window is before it; one received on its first day in it
    earlier = breakdowns(before_to=(day_before - timedelta(days=1)).isoformat())
    assert earlier["cases"] == {
        "before": got["cases"]["before"] - 1,
        "window": got["cases"]["window"],
    }
    later = breakdowns(received_from=(day_before + timedelta(days=2)).isoformat())
    assert later["cases"]["window"] == got["cases"]["window"] - 1
    for overlap in (NEWEST["received_from"], NEWEST["received_to"]):
        assert "no case is in both" in breakdowns(400, before_to=overlap)["problem"]


@pytest.mark.parametrize(
    "settings",
    [{}, {"sex": "M"}, {"country": "GB"}, {"prole": "SS"}, {"dedup": "all"}, {"unit": "exact"}],
)
def test_settings_and_filters_change_the_counts_as_they_change_events(
    settings, breakdowns, web, ask
):
    got = breakdowns(**settings)

    def cases(**more: str) -> int:
        rows = ask(web, "/api/events", product=DRUG, **settings, **more)["rows"]
        return next((r[1] for r in rows if r[0] == EVENT), 0)

    assert got["cases"]["window"] == cases(**NEWEST)
    assert got["cases"]["before"] + got["cases"]["window"] == cases()
    for line in got["lines"]:
        reports = line["window"]["cases"]
        assert reports == got["cases"]["window"] or line["field"] == "duplicates", line["field"]


def test_the_same_question_asked_twice_gives_the_same_answer(web, breakdown_release):
    address = f"/api/breakdowns?product={DRUG}&reaction={EVENT}&reaction=Nausea&sex=F"
    first, again = web.get(address).json(), web.get(address).json()
    assert first == again
    query = {"product": [DRUG], "reaction": [EVENT, "Nausea"], "sex": ["F"]}
    for _ in range(2):  # each time from a fresh read of the release
        data = open_release_data(breakdown_release, LOCAL)
        assert json.loads(answer(ask_in_process("GET /api/breakdowns", data, query)).body) == first


# the rule --------------------------------------------------------------------------------------


def test_every_field_of_the_rule_has_a_reader_and_every_reader_a_field(breakdowns):
    named = [line.field for line in fields.lines()]
    assert set(named) == set(fields.READERS) and len(named) == len(set(named))
    got = breakdowns()
    assert [line["field"] for line in got["lines"]] == named
    assert [g["group"] for g in got["groups"]] == [g["group"] for g in fields.groups()]
    assert {line["group"] for line in got["lines"]} <= {g["group"] for g in got["groups"]}


def test_the_default_window_is_the_rules_newest_quarters(breakdowns, tmp_path):
    more = rulebook.value("breakdown-lines", "default_window_quarters") + 1
    assert breakdowns()["window"]["from"] == NEWEST["received_from"]
    with rules_with(tmp_path, {"breakdown-lines": {"default_window_quarters": more}}):
        # another question, so not the answer kept from the one above
        start = date.fromisoformat(breakdowns(sex="F")["window"]["from"])
    newest = date.fromisoformat(NEWEST["received_from"])
    assert (newest.year * 12 + newest.month) - (start.year * 12 + start.month) == 3 * (more - 1)


def test_an_smq_the_version_does_not_hold_leaves_only_the_pregnancy_line_not_available(
    breakdowns, monkeypatch
):
    """A person's page is never refused for a name."""
    monkeypatch.setattr(ServedMeddra, "named_groups", lambda self, key: ["No such SMQ"])
    got = breakdowns()
    assert "pregnancy-cases" in got["not_available"]["pregnancy"]
    assert "No such SMQ" in got["not_available"]["pregnancy"]
    assert "sex" not in got["not_available"]


@pytest.mark.parametrize(
    ("rule", "values", "named"),
    [
        ("rechallenge-correction", {"correction": "swap"}, "rechallenge-correction"),
        (
            "breakdown-lines",
            {"groups": [{"group": "clinical", "name": "Clinical"}]},
            "breakdown-lines",
        ),
    ],
)
def test_a_rule_the_breakdowns_cannot_read_refuses_the_question(
    rule, values, named, breakdowns, tmp_path
):
    with rules_with(tmp_path, {rule: values}):
        assert named in breakdowns(400)["problem"]


def test_every_pick_of_the_rule_has_a_function_and_every_function_a_pick(breakdowns):
    kinds = [lines.kind(line.pick) for line in fields.lines()]
    assert set(kinds) == set(lines.PICKS)
    got = breakdowns()
    shown = {line["field"]: line["shown"] for line in got["lines"]}
    for line in fields.lines():
        if line.field in got["not_available"]:
            assert shown[line.field] is None
        else:
            assert shown[line.field]["pick"] == lines.kind(line.pick), line.field


def test_a_pick_no_function_makes_refuses_the_question(breakdowns, tmp_path):
    found = [dict(f) for f in rulebook.value("breakdown-lines", "fields")]
    found[0]["pick"] = "loudest"
    with rules_with(tmp_path, {"breakdown-lines": {"fields": found}}):
        problem = breakdowns(400)["problem"]
    assert "breakdown-lines" in problem and found[0]["field"] in problem


def test_a_field_no_reader_reads_refuses_the_question(breakdowns, tmp_path):
    lines = [*rulebook.value("breakdown-lines", "fields")]
    lines.append({"field": "weight", "name": "Weight", "group": "clinical", "pick": "rose_most"})
    with rules_with(tmp_path, {"breakdown-lines": {"fields": lines}}):
        problem = breakdowns(400)["problem"]
    assert "breakdown-lines" in problem and "weight" in problem


@pytest.mark.parametrize(
    ("params", "says"),
    [
        ({"product": ""}, "name it as product"),
        ({"reaction": ""}, "Name the event as reaction"),
        ({"received_from": "2026-4-1"}, "yyyy-mm-dd"),
        ({"before_to": "2026-02-30"}, "yyyy-mm-dd"),
        ({"received_from": "2026-06-01", "received_to": "2026-05-01"}, "ends before it starts"),
        ({"before_from": "2019-01-01", "before_to": "2018-01-01"}, "ends before it starts"),
    ],
)
def test_a_question_that_cannot_be_answered_is_refused(params, says, breakdowns):
    assert says in breakdowns(400, **params)["problem"]


# the value each line shows ---------------------------------------------------------------------


def fresh(release, **params: object) -> dict:
    """The answer from a fresh read of the release, so under the rules in use now."""
    data = open_release_data(release, LOCAL)
    query = {"product": [DRUG], "reaction": [EVENT]}
    query |= {k: v if isinstance(v, list) else [str(v)] for k, v in params.items()}
    return json.loads(answer(ask_in_process("GET /api/breakdowns", data, query)).body)


def test_a_rise_that_fails_the_chance_test_did_not_rise(breakdowns, breakdown_release, tmp_path):
    at_least = rulebook.value("breakdown-rose", "points_at_least")
    gb = value_in(line_of(breakdowns(), "country"), "GB")  # none before, half the window
    assert gb["change"] >= at_least and gb["p"] >= rulebook.value("chance-test", "alpha")
    assert gb["rose"] is False
    with rules_with(tmp_path, {"breakdown-rose": {"chance_test": False}}):
        assert value_in(line_of(fresh(breakdown_release), "country"), "GB")["rose"] is True
    with rules_with(tmp_path, {"breakdown-rose": {"points_at_least": gb["change"] + 1}}):
        assert value_in(line_of(fresh(breakdown_release), "country"), "GB")["rose"] is False
    # no window report gives an age: nothing to compare, neither risen nor not
    age = line_of(breakdowns(), "age")
    assert all(v["rose"] is None and v["p"] is None for v in age["values"])


def test_a_share_up_by_exactly_the_points_rose_however_floats_round(tmp_path):
    """Compared exactly, never as floats or after rounding."""
    at_least = rulebook.value("breakdown-rose", "points_at_least")
    given = {"before": 100, "window": 100}
    up = lines.Shares({"before": 10, "window": 10 + at_least}, given)
    assert ((10 + at_least) / 100 - 10 / 100) * 100 < at_least  # as floats, short of it
    with rules_with(tmp_path, {"breakdown-rose": {"chance_test": False}}):
        assert lines._rose(up, lines.rise()) is True
        short = lines.Shares({"before": 10, "window": 9 + at_least}, given)
        assert lines._rose(short, lines.rise()) is False


def test_each_shown_value_counts_what_its_pick_gathers(breakdowns, brel):
    got = breakdowns()
    reporter = line_of(got, "reporter")
    health = rulebook.value("breakdown-lines", "health_professionals")
    assert reporter["shown"]["value"] == "health_professionals"  # no lawyer reported
    for p in PERIODS:
        gathered = sum(v[p]["cases"] for v in reporter["values"] if v["value"] in health)
        assert reporter["shown"][p]["cases"] == gathered
    seriousness = line_of(got, "seriousness")["shown"]  # nothing rose: the first, death
    assert seriousness["value"] == rulebook.value("serious-outcomes", "serious")[0]
    onset = line_of(got, "onset")
    for p in PERIODS:
        days = [d["value"] for d in onset["values"] for _ in range(d[p]["cases"])]
        assert onset["shown"][p] == {"cases": len(days), "days": statistics.median(days)}
    duplicates = line_of(got, "duplicates")
    # the shown value counts what the value counts; only the value carries its cases' question
    assert (
        duplicates["shown"]["before"].items() <= value_in(duplicates, "set_aside")["before"].items()
    )
    [details] = [f for f in fields.lines() if f.field == fields.KEY_DETAILS]
    every = len(details.pick["all_given"])
    assert line_of(got, "key_details")["shown"]["value"] == every
    cites = line_of(got, "literature")
    assert cites["shown"]["value"] == literature.CITES
    for p in PERIODS:
        assert cites["shown"][p].items() <= value_in(cites, literature.CITES)[p].items()


# before the window, 2019: one case of two gives no serious outcome; in the window, none
IN_2019 = {"before_from": "2019-01-01", "before_to": "2019-12-31"}


def test_any_serious_outcome_rises_where_no_single_outcome_did_and_alarms_where_picked(
    breakdown_release, tmp_path
):
    line = line_of(fresh(breakdown_release, **IN_2019), "seriousness")
    gathered = value_in(line, fields.SERIOUS)
    assert gathered["change"] >= rulebook.value("breakdown-alarm", "points")
    assert gathered["rose"] is False  # by chance, under the rule
    alpha = {"chance-test": {"alpha": (gathered["p"] + 1) / 2}}
    picked = [dict(f) for f in rulebook.value("breakdown-lines", "fields")]
    for f in picked:
        if f["field"] == "seriousness":
            f["pick"] = {"value": fields.SERIOUS}  # as a person's own rules may pick it
    with rules_with(tmp_path, alpha):
        planted = line_of(fresh(breakdown_release, **IN_2019), "seriousness")
    with rules_with(tmp_path / "picked", alpha | {"breakdown-lines": {"fields": picked}}):
        shown = line_of(fresh(breakdown_release, **IN_2019), "seriousness")
        higher = fresh(breakdown_release, **IN_2019, points=gathered["change"] + 1)
    assert [v["value"] for v in planted["values"] if v["rose"]] == [fields.SERIOUS]
    # the rule's pick is the most severe outcome that rose, else death, as before
    assert planted["shown"]["value"] == rulebook.value("serious-outcomes", "serious")[0]
    assert (shown["shown"]["value"], shown["shown"]["rose"]) == (fields.SERIOUS, True)
    for p in PERIODS:
        assert shown["shown"][p].items() <= value_in(shown, fields.SERIOUS)[p].items()
    assert shown["alarm"] is True and line_of(higher, "seriousness")["alarm"] is False


def test_what_any_serious_outcome_gathers_changes_no_other_line_or_value(
    breakdown_release, tmp_path
):
    death = rulebook.value("serious-outcomes", "serious")[0]
    standard = fresh(breakdown_release)
    with rules_with(tmp_path, {"serious-outcomes": {"serious": [death]}}):
        narrowed = fresh(breakdown_release)
    assert [line["field"] for line in standard["lines"]] == [f.field for f in fields.lines()]
    for was, now in zip(standard["lines"], narrowed["lines"], strict=True):
        if was["field"] != "seriousness":
            assert was == now, was["field"]
    was, now = line_of(standard, "seriousness"), line_of(narrowed, "seriousness")
    assert [v for v in was["values"] if v["value"] != fields.SERIOUS] == [
        v for v in now["values"] if v["value"] != fields.SERIOUS
    ]
    for p in PERIODS:
        counted = {k: value_in(now, death)[p][k] for k in ("cases", "share")}
        assert {k: value_in(now, fields.SERIOUS)[p][k] for k in counted} == counted
        assert value_in(was, fields.SERIOUS)[p]["cases"] > counted["cases"]


def test_not_given_is_never_an_alarm(breakdowns, breakdown_release, tmp_path):
    gb = value_in(line_of(breakdowns(), "country"), "GB")
    points = gb["change"] - 1
    with rules_with(tmp_path, {"chance-test": {"alpha": (gb["p"] + 1) / 2}}):
        got = fresh(breakdown_release, points=points)
    assert line_of(got, "country")["shown"]["value"] == "GB"
    assert line_of(got, "country")["alarm"] is True
    age = line_of(got, "age")  # no window report gives an age
    assert age["shown"]["window"]["share"] is None and age["alarm"] is None
    # the reports from FDA's files before the literature reference are in neither share
    cites = line_of(got, "literature")
    assert cites["before"]["given"] < cites["before"]["cases"]
    assert cites["shown"]["before"]["share"] == 0 and cites["alarm"] is not None
    assert line_of(fresh(breakdown_release, points=points), "country")["alarm"] is False


def test_a_fall_counts_as_a_rise_unless_fall_is_0(breakdown_release, tmp_path):
    found = [dict(f) for f in rulebook.value("breakdown-lines", "fields")]
    for f in found:
        if f["field"] == "country":
            f["pick"] = {"value": "US"}  # every report before, half the window
    with rules_with(tmp_path, {"breakdown-lines": {"fields": found}}):
        us = line_of(fresh(breakdown_release), "country")["shown"]
        alpha = {"chance-test": {"alpha": (us["p"] + 1) / 2}}
        with rules_with(tmp_path / "and", {"breakdown-lines": {"fields": found}} | alpha):
            fell = -us["change"]
            alarm = {
                (points, fall): line_of(
                    fresh(breakdown_release, points=points, fall=fall), "country"
                )["alarm"]
                for points in (fell, fell + 1)
                for fall in ("", "0", "1")
            }
    assert us["change"] < 0
    counts = rulebook.value("breakdown-alarm", "fall_counts")
    assert alarm == {
        (fell, ""): counts,
        (fell, "0"): False,
        (fell, "1"): True,
        (fell + 1, ""): False,
        (fell + 1, "0"): False,
        (fell + 1, "1"): False,
    }


@pytest.mark.parametrize("points", ["0", "-3", "ten", "nan", "1/0"])
def test_points_that_are_not_a_positive_number_are_refused(points, breakdowns):
    assert "points" in breakdowns(400, points=points)["problem"]


@pytest.mark.parametrize("fall", ["2", "yes"])
def test_a_fall_that_is_not_0_or_1_is_refused(fall, breakdowns):
    assert "fall" in breakdowns(400, fall=fall)["problem"]


@pytest.mark.parametrize("strength", ["40", "forty mg", "2.5 mg/kg", "1,000 mg"])
def test_a_strength_that_cannot_be_read_is_refused_naming_it(strength, breakdowns):
    assert strength in breakdowns(400, strength=["40 mg", strength])["problem"]


def test_strengths_in_different_measures_are_refused(breakdowns):
    assert "strength" in breakdowns(400, strength=["40 mg", "5 mL"])["problem"]


@pytest.mark.parametrize("change", ["in no measure", "not in units", "in two measures"])
def test_a_rule_whose_units_and_measures_differ_refuses_the_question_naming_the_unit(
    change, breakdowns, tmp_path
):
    """A product checks strengths before it asks by reading the rule's units and what each
    measures, so each unit in `units` is in one measure and each unit measured is in `units`."""
    units = rulebook.value(fields.STRENGTH, "units")
    measures = rulebook.value(fields.STRENGTH, "measures")
    unit = units[0]
    other = next(m for m, sizes in measures.items() if unit not in sizes)
    changes = {
        "in no measure": {
            "measures": {m: {u: s for u, s in v.items() if u != unit} for m, v in measures.items()}
        },
        "not in units": {"units": units[1:]},
        "in two measures": {"measures": measures | {other: measures[other] | {unit: 1}}},
    }
    with rules_with(tmp_path, {fields.STRENGTH: changes[change]}):
        problem = breakdowns(400)["problem"]
    assert fields.STRENGTH in problem and repr(unit) in problem


def test_the_rule_says_what_each_unit_measures_and_its_size_there():
    """The rule's `measures`, read the way a product reads them, give the strengths a dose
    reads to: one unit's size times its amount, in the same measure."""
    measures = rulebook.value(fields.STRENGTH, "measures")
    for measure, sizes in measures.items():
        for unit, size in sizes.items():
            found = fields.strength_of(f"2 {unit}")
            assert found is not None and found.measure == measure
            assert found.size == 2 * Decimal(str(size))


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("320 MG, QD", ("320", "mg")),
        ("0.32 G", ("320", "mg")),
        ("80 MILLIGRAM", ("80", "mg")),
        ("100MG QD", ("100", "mg")),
        ("250MG/5ML BID", ("50", "mg/mL")),
        (".5 mcg", ("0.0005", "mg")),
        ("1000 IU", ("1000", "units")),
        ("2.5 MG/KG", None),
        ("1,000 MG", None),
        ("TWO TABLETS", None),
        ("10 MGS", None),
    ],
)
def test_a_strength_is_read_from_the_first_words_of_a_dose(written, read):
    found = fields.strength_of(written)
    if read is None:
        assert found is None
        return
    assert found is not None
    want = fields.strength_of(f"{read[0]} {read[1]}")
    assert want is not None and found.same(want)


def test_the_dose_line_shows_the_highest_strength_passed(breakdowns, brel):
    written = brel.rows(
        "SELECT DISTINCT upper(d.dose_vbm) FROM drug_latest_T d WHERE upper(d.drugname) = ?",
        DRUG.upper(),
    )
    [[dose]] = written  # every valsartan record writes one dose
    strength = fields.strength_of(dose)
    assert strength is not None
    taken = line_of(breakdowns(), "dose")["shown"]  # none passed: the one written
    assert taken["value"] == strength.words() and taken["values"] == [dose]
    assert taken["window"]["share"] == 1
    half = f"{strength.amount / 2} {strength.unit}"
    higher = line_of(breakdowns(strength=[half, f"{strength.size / 1000} g"]), "dose")["shown"]
    assert higher["values"] == [dose] and higher["window"]["share"] == 1
    lower = line_of(breakdowns(strength=[half]), "dose")["shown"]
    assert lower["values"] == [] and lower["window"]["share"] == 0  # a dose given, not this one
    empty = breakdowns(strength=[half], received_from="2025-01-01", received_to="2025-03-31")
    assert line_of(empty, "dose")["shown"]["window"]["share"] is None  # no report gives a dose


# each line a filter ----------------------------------------------------------------------------


def test_each_value_of_a_line_is_a_value_of_its_filter_which_keeps_exactly_its_cases(breakdowns):
    """A line's filter given one of its values, or one of the onset bands, keeps exactly that
    value's cases in each period; given Not given, exactly the reports that do not give the field:
    the line and its filter read the field one way. Drug role's filter is the roles the product
    is counted in, so only its first role, PS, is exactly its value."""
    got = breakdowns(**NEWEST)
    tried = 0
    for line in got["lines"]:
        name = line["filter"]
        if name is None:
            continue
        for each in [*line["values"], *line.get("bands", [])]:
            value = each["value"]
            if (line["field"], value) == ("seriousness", fields.SERIOUS) or (
                name == "prole" and value != "PS"
            ):
                continue  # any serious outcome: the outcome filter's serious codes
            asked = f"{value}-{value}" if isinstance(value, int) else str(value)
            narrowed = breakdowns(**NEWEST, **{name: asked})
            assert {p: narrowed["cases"][p] for p in PERIODS} == {
                p: each[p]["cases"] for p in PERIODS
            }, (line["field"], value)
            tried += 1
        if NOT_GIVEN not in [v["value"] for v in line["values"]] and name != "prole":
            narrowed = breakdowns(**NEWEST, **{name: NOT_GIVEN})
            for p in PERIODS:
                assert narrowed["cases"][p] == line[p]["cases"] - line[p]["given"], line["field"]
    assert tried > 20


def test_lines_name_their_filter_and_the_ones_with_none_say_so(breakdowns):
    got = breakdowns(**NEWEST)
    named = {line["field"]: line["filter"] for line in got["lines"]}
    assert named == {f.field: fields.FILTERS.get(f.field) for f in fields.lines()}
    assert {f for f, n in named.items() if n is None} == {
        "pregnancy",
        "literature",
        "key_details",
        "duplicates",
    }


def test_the_onset_bands_count_the_days_of_rule_breakdown_lines_bands(breakdowns):
    """Each band holds the cases of the days in it, both ends included, its share among the
    reports giving a time to onset."""
    onset = line_of(breakdowns(**NEWEST), "onset")
    bands = rulebook.value(fields.RULE, "onset_bands")
    assert [b["name"] for b in onset["bands"]] == [b["name"] for b in bands]
    for band, rule in zip(onset["bands"], bands, strict=True):
        low, high = rule["from"], rule.get("to")
        assert band["value"] == f"{low}-{'' if high is None else high}"
        for p in PERIODS:
            inside = [
                v[p]["cases"]
                for v in onset["values"]
                if v["value"] >= low and (high is None or v["value"] <= high)
            ]
            assert band[p]["cases"] == sum(inside)
            given = onset[p]["given"]
            assert band[p]["share"] == (sum(inside) / given if given else None)


def test_a_window_named_by_the_event_date_places_each_case_by_its_full_event_date(breakdowns, brel):
    """The window and before read the day the event began, as the event date filter does; a
    case with no full event date is in neither, and the received days place no case."""
    pair, params = of_the_pair(brel)
    found = brel.dicts(
        f"SELECT c.event_dt_T AS day FROM case_latest_T c WHERE c.dup_kept_T AND {pair}", *params
    )
    window = (date(2026, 3, 1), date(2026, 6, 30))
    got = breakdowns(event_from="2026-03-01", event_to="2026-06-30", before_from="2019-01-01")
    assert got["cases"] == {
        "before": sum(1 for c in found if c["day"] and date(2019, 1, 1) <= c["day"] < window[0]),
        "window": sum(1 for c in found if c["day"] and window[0] <= c["day"] <= window[1]),
    }
    assert got["window"] == {"from": "2026-03-01", "to": "2026-06-30"}
    assert got["cases"]["window"] > 0 and got["cases"]["before"] > 0
    assert got["cases"] != breakdowns(**NEWEST, before_from="2019-01-01")["cases"]
