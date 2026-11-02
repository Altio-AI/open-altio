"""A drug's events (eventlist.py), asked through /api/events: one row per event the drug's
counted cases name, by today's term where the release holds MedDRA, its cases by quarter and
year, its serious, fatal, life-threatening and fatal or life-threatening cases (rule
serious-outcomes), the day each case is dated by (rule received-day) and its label answer; and a
group of reactions counted as one event, asked through /api/events/group, with the same figures.

What each answer should hold is read apart from the explorer: from the release's own Parquet
through a ReleaseReader, or from the explorer's database by a query written here.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from open_altio.explorer.access import Viewer
from open_altio.explorer.eventlist import FIGURES
from open_altio.faers.explorer_db import reaction_term
from open_altio.faers.medical_events import add_medical_events
from open_altio.rulebook import value
from open_altio.testing.fakemedicalevents import DME_TERMS, write_dme
from open_altio.testing.releasereader import ReleaseReader
from open_altio.testing.rules import rules_with

ASPIRIN = "acetylsalicylic acid"
SUSPECT = "d.role_cod IN ('PS', 'SS')"
SERIOUS = "serious-outcomes"


def events(ask, client: TestClient, status: int = 200, **query) -> dict:
    return ask(client, "/api/events", status, **query)


def rows_of(answer: dict) -> dict[str, dict]:
    """Each row of an answer by its PT, as a dict of its columns."""
    return {r[0]: dict(zip(answer["columns"], r, strict=True)) for r in answer["rows"]}


def named(reader: ReleaseReader, ingredient: str) -> dict[str, set[str]]:
    """Each event as the explorer keys FDA's text -> era/case_key of the kept cases naming the
    ingredient as a primary or secondary suspect, from the release's own files."""
    found: dict[str, set[str]] = {}
    for pt, era, key in reader.rows(
        "SELECT DISTINCT r.pt, c.era_T, c.case_key_T FROM case_latest_T c "
        "JOIN drug_latest_T d USING (era_T, primaryid, quarter_T) "
        "JOIN drug_substance_T s USING (era_T, primaryid, quarter_T, drug_seq) "
        f"JOIN reac_latest_T r ON {reader.case_join('r')} "
        f"WHERE c.dup_kept_T AND {SUSPECT} "
        "AND list_contains(string_split(s.substance_T, ';'), ?)",
        ingredient,
    ):
        found.setdefault(reaction_term(pt), set()).add(f"{era}/{key}")
    return found


def explorer_count(release: Path, ingredient: str, event: str, where: str, *params) -> int:
    """Kept cases naming the ingredient as a suspect and the event as FDA wrote it, matching
    `where` over explorer_case_T c: a query over the explorer's database written apart."""
    con = duckdb.connect(str(release / "explorer.duckdb"), read_only=True)
    try:
        return con.execute(
            "SELECT count(DISTINCT c.case_id_T) FROM explorer_case_T c "
            "JOIN explorer_drug_T d USING (case_id_T) JOIN explorer_reac_T r USING (case_id_T) "
            f"WHERE c.dup_kept_T AND {SUSPECT} "
            "AND list_contains(string_split(d.substance_T, ';'), ?) AND lower(r.pt) = ? "
            f"AND ({where})",
            [ingredient, event, *params],
        ).fetchone()[0]
    finally:
        con.close()


@pytest.fixture
def events_client(explorer_app, events_release) -> TestClient:
    return TestClient(explorer_app(events_release))


# one row per event ------------------------------------------------------------------------------


def test_each_event_counts_the_drugs_cases_that_name_it(client, rel, ask):
    got = events(ask, client, product=ASPIRIN)
    assert got["columns"] == [
        "pt",
        "cases",
        "newest",
        "prior",
        "recent",
        "years",
        "busiest_year",
        "serious",
        "death",
        "life_threatening",
        "death_or_life_threatening",
        "label",
        "dme",
        "ime",
        "cases_query",
    ]
    counted = {reaction_term(pt): row["cases"] for pt, row in rows_of(got).items()}
    assert counted == {k: len(cases) for k, cases in named(rel, ASPIRIN).items()}


def test_rows_come_most_cases_first_then_by_name(client, ask):
    rows = events(ask, client, product=ASPIRIN)["rows"]
    assert len(rows) > 2
    assert rows == sorted(rows, key=lambda r: (-r[1], r[0].lower()))


def test_a_question_with_no_drug_is_refused(client, ask):
    assert events(ask, client, 400)["problem"]


def test_each_drug_is_asked_alone_so_a_case_naming_two_counts_on_each(
    events_client, events_release, ask
):
    reader = ReleaseReader(events_release)
    both = named(reader, ASPIRIN)["haemorrhage"] & named(reader, "warfarin")["haemorrhage"]
    assert both
    for drug in (ASPIRIN, "warfarin"):
        rows = rows_of(events(ask, events_client, product=drug))
        assert rows["Haemorrhage"]["cases"] == len(named(reader, drug)["haemorrhage"])


def test_the_events_follow_the_questions_filters(client, rel, ask):
    every = rows_of(events(ask, client, product=ASPIRIN))
    hospital = rows_of(events(ask, client, product=ASPIRIN, outcome="HO"))
    assert hospital and set(hospital) < set(every)
    kept = rel.case_keys(
        f"EXISTS (SELECT 1 FROM outc_latest_T o WHERE {rel.case_join('o')} AND o.outc_cod = 'HO')"
    )
    for pt, row in hospital.items():
        assert row["cases"] == len(named(rel, ASPIRIN)[reaction_term(pt)] & kept)


# by quarter and year, dated by the received day ---------------------------------------------


def test_the_years_add_up_to_the_cases_and_newest_counts_the_newest_quarter(
    events_client, events_release, ask
):
    got = events(ask, events_client, product=ASPIRIN)
    quarter = ReleaseReader(events_release).manifest["quarters"][-1]
    year, n = int(quarter[:4]), int(quarter[-1])
    assert got["newest_quarter"] == f"{year} Q{n}"
    day = value("received-day", "column")
    first = f"{year}-{3 * n - 2:02d}-01"
    newest = (
        f"(date_trunc('quarter', c.{day}) = CAST(? AS DATE) "
        f"OR (c.{day} IS NULL AND c.quarter_T = ?))"
    )
    for pt, row in rows_of(got).items():
        assert sum(cases for _, cases in row["years"]) == row["cases"], pt
        apart = explorer_count(events_release, ASPIRIN, pt.lower(), newest, first, quarter)
        assert row["newest"] == apart, pt
        assert row["busiest_year"] == min(row["years"], key=lambda y: (-y[1], y[0]))[0]
    # a case in the newest quarter's file that FDA first received in an earlier year
    nausea = rows_of(got)["Nausea"]
    assert nausea["newest"] < nausea["cases"]
    assert nausea["years"][0][0] < year == nausea["years"][-1][0]


def test_the_received_window_dates_a_case_by_its_received_day(events_client, events_release, ask):
    quarter = ReleaseReader(events_release).manifest["quarters"][-1]
    since = f"{quarter[:4]}-01-01"
    day = value("received-day", "column")
    nausea = rows_of(events(ask, events_client, product=ASPIRIN, received_from=since))["Nausea"]
    assert nausea["cases"] == explorer_count(
        events_release, ASPIRIN, "nausea", f"c.{day} >= CAST(? AS DATE)", since
    )
    assert nausea["cases"] == nausea["newest"]


def test_one_change_of_the_rule_dates_the_events_and_the_window_again(
    explorer_app, events_release, ask, tmp_path
):
    """Dated by a day the invented cases leave empty, every case falls in the quarter of its own
    file, and a window on that day keeps none."""
    with rules_with(tmp_path, {"received-day": {"column": "event_dt_T"}}):
        web = TestClient(explorer_app(events_release))
        rows = rows_of(events(ask, web, product=ASPIRIN))
        quarter = ReleaseReader(events_release).manifest["quarters"][-1]
        assert rows["Nausea"]["newest"] == rows["Nausea"]["cases"]
        assert rows["Nausea"]["years"] == [[int(quarter[:4]), rows["Nausea"]["cases"]]]
        since = f"{quarter[:4]}-01-01"
        assert events(ask, web, product=ASPIRIN, received_from=since)["rows"] == []


# serious, fatal and life-threatening (rule serious-outcomes) ---------------------------------


def outcomes_of(reader: ReleaseReader, case: str) -> set[str]:
    return {
        code
        for (code,) in reader.rows(
            "SELECT o.outc_cod FROM case_latest_T c JOIN outc_latest_T o "
            f"ON {reader.case_join('o')} WHERE c.caseid = ?",
            case,
        )
    }


@pytest.mark.parametrize("case", ["7602001", "7603001", "7604001"])
def test_a_case_counts_as_serious_fatal_or_life_threatening_by_its_outcome_codes(
    events_client, events_release, ask, case
):
    """Asked on one case's received day alone: hospitalization only is serious and neither fatal
    nor life-threatening; no outcome row is none of them."""
    reader = ReleaseReader(events_release)
    [(day,)] = reader.rows("SELECT group_first_dt_T FROM case_latest_T WHERE caseid = ?", case)
    one = {"received_from": day.isoformat(), "received_to": day.isoformat()}
    row = rows_of(events(ask, events_client, product=ASPIRIN, **one))["Headache"]
    codes = outcomes_of(reader, case)
    assert row["cases"] == 1
    assert row["serious"] == int(bool(codes & set(value(SERIOUS, "serious"))))
    assert row["death"] == int(value(SERIOUS, "death") in codes)
    assert row["life_threatening"] == int(value(SERIOUS, "life_threatening") in codes)
    either = {value(SERIOUS, "death"), value(SERIOUS, "life_threatening")}
    assert row["death_or_life_threatening"] == int(bool(codes & either))
    if not codes:
        assert (row["serious"], row["death"], row["life_threatening"]) == (0, 0, 0)
        assert row["death_or_life_threatening"] == 0


def codes_by_case(reader: ReleaseReader) -> dict[str, set[str]]:
    """Each case, era/case_key, -> FDA's outcome codes for it, from the release's own files."""
    return {
        f"{e}/{k}": set(c or [])
        for e, k, c in reader.rows(
            "SELECT c.era_T, c.case_key_T, list(o.outc_cod) FROM case_latest_T c "
            f"LEFT JOIN outc_latest_T o ON {reader.case_join('o')} GROUP BY 1, 2"
        )
    }


def test_the_outcome_counts_are_each_events_cases_with_the_rules_codes(client, rel, ask):
    codes = codes_by_case(rel)
    for pt, row in rows_of(events(ask, client, product=ASPIRIN)).items():
        cases = named(rel, ASPIRIN)[reaction_term(pt)]
        serious = set(value(SERIOUS, "serious"))
        assert row["serious"] == sum(1 for c in cases if codes[c] & serious), pt
        assert row["death"] == sum(1 for c in cases if value(SERIOUS, "death") in codes[c]), pt
        lt = value(SERIOUS, "life_threatening")
        assert row["life_threatening"] == sum(1 for c in cases if lt in codes[c]), pt
        either = {value(SERIOUS, "death"), lt}
        assert row["death_or_life_threatening"] == sum(1 for c in cases if codes[c] & either), pt


def test_a_case_both_fatal_and_life_threatening_counts_once_in_either(
    events_client, events_release, ask
):
    """The union is never more than the fatal and life-threatening cases together, never fewer
    than either alone, and is fewer than the two together where a case is both."""
    rows = rows_of(events(ask, events_client, product=ASPIRIN)).values()
    assert rows
    for row in rows:
        either = row["death_or_life_threatening"]
        assert max(row["death"], row["life_threatening"]) <= either
        assert either <= row["death"] + row["life_threatening"]
    assert any(r["death_or_life_threatening"] < r["death"] + r["life_threatening"] for r in rows)


# a group of reactions counted as one event -------------------------------------------------------


def group(ask, client: TestClient, status: int = 200, **query) -> dict:
    return ask(client, "/api/events/group", status, **query)


def figures(answer: dict) -> dict:
    """What a group and an event's row both count, by name."""
    return {name: answer[name] for name in FIGURES}


# the drug's settings and the filters a host may pass, each one changing the drug's events
ASKED_AS = [
    (ASPIRIN, {}),
    ("valsartan", {"unit": "exact"}),
    (ASPIRIN, {"prole": ["PS", "SS", "I"]}),
    (ASPIRIN, {"exclude": "BAYER LOW DOSE"}),
    ("valsartan", {"include": "VALSARTAN TEVA"}),
    (ASPIRIN, {"dedup": "all"}),
    (ASPIRIN, {"outcome": "HO"}),
    (ASPIRIN, {"sex": "F"}),
    (ASPIRIN, {"pt": "Nausea"}),
    (ASPIRIN, {"received_from": "2019-01-01"}),
]


@pytest.mark.parametrize(
    ("drug", "asked"), ASKED_AS, ids=[f"{d}:{'&'.join(a) or 'plain'}" for d, a in ASKED_AS]
)
def test_a_group_of_one_term_is_that_terms_row_field_for_field(client, ask, drug, asked):
    """Under every setting and filter, as they change /api/events."""
    rows = rows_of(events(ask, client, product=drug, **asked))
    assert rows
    if asked:
        assert rows != rows_of(events(ask, client, product=drug)), "a setting that changes"
    for pt, row in rows.items():
        got = group(ask, client, product=drug, reaction=pt, **asked)
        assert got["reactions"] == [pt]
        assert figures(got) == figures(row), pt


def test_a_group_of_one_pt_counts_the_cases_fda_coded_with_its_old_name(licensed_client, ask):
    """In the invented MedDRA 29.1, Lactic acidosis is an old name of Acidosis lactic."""
    row = rows_of(events(ask, licensed_client, product="metformin"))["Acidosis lactic"]
    got = group(ask, licensed_client, product="metformin", reaction="acidosis LACTIC")
    assert got["reactions"] == ["Acidosis lactic"]
    assert figures(got) == figures(row)


def test_a_case_naming_two_of_the_groups_terms_counts_once(events_client, events_release, ask):
    by_event = named(ReleaseReader(events_release), ASPIRIN)
    headache, nausea = by_event["headache"], by_event["nausea"]
    assert headache & nausea
    got = group(ask, events_client, product=ASPIRIN, reaction=["Nausea", "Headache"])
    assert got["reactions"] == ["Headache", "Nausea"]
    assert got["cases"] == len(headache | nausea) < len(headache) + len(nausea)
    assert sum(cases for _, cases in got["years"]) == got["cases"]


def test_the_groups_outcome_counts_are_its_cases_with_the_rules_codes(
    events_client, events_release, ask
):
    reader = ReleaseReader(events_release)
    by_event = named(reader, ASPIRIN)
    cases = by_event["headache"] | by_event["nausea"]
    codes = codes_by_case(reader)
    got = group(ask, events_client, product=ASPIRIN, reaction=["Headache", "Nausea"])
    death, lt = value(SERIOUS, "death"), value(SERIOUS, "life_threatening")
    assert got["serious"] == sum(1 for c in cases if codes[c] & set(value(SERIOUS, "serious")))
    assert got["death"] == sum(1 for c in cases if death in codes[c])
    assert got["life_threatening"] == sum(1 for c in cases if lt in codes[c])
    either = got["death_or_life_threatening"]
    assert either == sum(1 for c in cases if codes[c] & {death, lt})
    assert max(got["death"], got["life_threatening"]) <= either
    assert either < got["death"] + got["life_threatening"]  # a case both fatal and life-threatening


def test_a_group_the_drugs_cases_never_name_counts_no_case(client, ask):
    got = group(ask, client, product=ASPIRIN, reaction="Not a reaction of these cases")
    assert figures(got) == dict.fromkeys(FIGURES, 0) | {
        "recent": [0] * 8,
        "years": [],
        "busiest_year": None,
    }
    assert got["newest_quarter"]


def test_a_group_of_a_drug_class_counts_the_cases_the_class_filter_counts(
    explorer_app, classes_release, ask
):
    """A class in place of the product: the same figures, its cases those the count of the class
    finds, under the same roles."""
    classed = TestClient(explorer_app(classes_release))
    asked = {"atc": "B01ZY", "arole": ["PS", "SS"]}
    pair = group(ask, classed, 200, reaction="Headache", **asked)
    counted = classed.get("/api/count", params={"by": "year", "pt": "Headache", **asked}).json()
    assert pair["cases"] == counted["total"]
    assert group(ask, classed, 400, reaction="Headache", arole="PS")["problem"]


def test_a_group_with_no_drug_or_no_reaction_is_refused(client, ask):
    assert group(ask, client, 400, reaction="Headache")["problem"]
    assert group(ask, client, 400, product=ASPIRIN)["problem"]
    assert group(ask, client, 400, product=ASPIRIN, reaction=" ")["problem"]


def test_the_same_group_asked_twice_gives_the_same_answer(explorer_app, events_release, ask):
    """Asked of two apps, so nothing kept from the first answers the second; the group's terms
    in any order and spelling, a term named twice, are one group."""
    first = group(
        ask,
        TestClient(explorer_app(events_release)),
        product=ASPIRIN,
        reaction=["Nausea", "Headache"],
    )
    again = group(
        ask,
        TestClient(explorer_app(events_release)),
        product=ASPIRIN,
        reaction=["headache", "Nausea", " HEADACHE "],
    )
    assert json.dumps(first) == json.dumps(again)


# today's terms (rule meddra-terms) ------------------------------------------------------------


def test_a_case_fda_coded_with_an_old_name_counts_in_its_pts_row(licensed_client, rel, ask):
    """In the invented MedDRA 29.1, Lactic acidosis is an old name of Acidosis lactic."""
    rows = rows_of(events(ask, licensed_client, product="metformin"))
    assert "Lactic acidosis" not in rows
    assert rows["Acidosis lactic"]["cases"] == len(named(rel, "metformin")["lactic acidosis"])


def test_a_viewer_shown_fdas_text_counts_the_old_name_in_a_row_of_its_own(
    hooked, licensed_release, ask
):
    viewer = Viewer(id="text", meddra=False, who=False, todays_names=False)
    web = hooked(viewer=viewer, release_dir=licensed_release)
    rows = rows_of(events(ask, web, product="metformin"))
    assert "Lactic acidosis" in rows and "Acidosis lactic" not in rows


# the label answer --------------------------------------------------------------------------


def flags_by_reaction(ask, client, **query) -> dict[str, dict]:
    found = ask(client, "/api/labels/product", **query)
    return {reaction_term(name): flag for name, flag in found["reactions"]}


def test_each_event_carries_its_label_answer_and_the_label_it_was_read_on(label_client, ask):
    flags = flags_by_reaction(ask, label_client, product=ASPIRIN)
    rows = rows_of(events(ask, label_client, product=ASPIRIN))
    assert rows
    for pt, row in rows.items():
        flag = flags[reaction_term(pt)]
        read = flag.get("label") or {}
        assert row["label"] == {
            "answer": flag["outcome"],
            "setid": flag["setid"],
            "spl_version": read.get("version"),
            "forms": flag["families"],
        }, pt
    assert any(r["label"]["setid"] and r["label"]["spl_version"] for r in rows.values())


def test_an_events_label_answer_gathers_every_text_read_to_its_pt(label_client, ask):
    flags = flags_by_reaction(ask, label_client, product="metformin")
    row = rows_of(events(ask, label_client, product="metformin"))["Acidosis lactic"]
    assert row["label"]["answer"] == flags["lactic acidosis"]["outcome"]
    assert row["label"]["setid"] == flags["lactic acidosis"]["setid"]


def test_a_drug_with_no_label_answers_no_label_never_not_on_label(label_client, ask):
    rows = rows_of(events(ask, label_client, product="ibuprofen"))
    assert rows
    for row in rows.values():
        assert row["label"]["answer"] == "no_label"
        assert row["label"]["setid"] is None


def test_without_the_flags_or_an_ingredient_the_label_is_not_available_and_says_why(
    client, label_client, ask
):
    for web, drug in ((client, ASPIRIN), (label_client, "VALSARTAN TEVA")):
        got = events(ask, web, product=drug)
        assert got["rows"]
        assert all(dict(zip(got["columns"], r, strict=True))["label"] is None for r in got["rows"])
        assert got["not_available"]["label"]
    with_flags = events(ask, label_client, product=ASPIRIN)
    assert "label" not in with_flags["not_available"]


def test_emas_lists_are_not_available_until_the_release_holds_them(client, ask):
    got = events(ask, client, product=ASPIRIN)
    assert set(got["not_available"]) >= {"dme", "ime"}
    for r in got["rows"]:
        row = dict(zip(got["columns"], r, strict=True))
        assert row["dme"] is None and row["ime"] is None


def test_a_release_with_both_lists_marks_each_event_on_or_off_each(listed_client, ask):
    got = events(ask, listed_client, product=ASPIRIN)
    assert "dme" not in got["not_available"] and "ime" not in got["not_available"]
    marks = {pt: (r["dme"], r["ime"]) for pt, r in rows_of(got).items()}
    listed = {  # what the invented list files (open_altio.testing.fakemedicalevents) name
        "dme": {t.lower() for t in DME_TERMS},
        "ime": {"seizure", "renal failure acute", "nausea"},
    }
    assert marks and all(
        marks[pt] == (pt.lower() in listed["dme"], pt.lower() in listed["ime"]) for pt in marks
    )
    assert any(d for d, _ in marks.values()) and any(not d for d, _ in marks.values())
    assert any(i for _, i in marks.values()) and any(not i for _, i in marks.values())
    assert all(isinstance(v, bool) for pair in marks.values() for v in pair)


def test_a_list_the_release_does_not_hold_is_not_available_with_its_reason_never_false(
    explorer_app, release, tmp_path, ask
):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    add_medical_events(copy, dme=write_dme(tmp_path / "dme.xlsx"))
    got = events(ask, TestClient(explorer_app(copy)), product=ASPIRIN)
    assert got["not_available"]["ime"] == "No IME file was given."
    assert "dme" not in got["not_available"]
    for r in got["rows"]:
        row = dict(zip(got["columns"], r, strict=True))
        assert row["ime"] is None and isinstance(row["dme"], bool)


def test_a_list_that_could_not_be_read_says_so_for_every_event(
    explorer_app, release, tmp_path, ask
):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    broken = tmp_path / "dme.xlsx"
    broken.write_text("nothing", encoding="utf-8")
    add_medical_events(copy, dme=broken)
    got = events(ask, TestClient(explorer_app(copy)), product=ASPIRIN)
    assert "was not read" in got["not_available"]["dme"]
    assert all(r[got["columns"].index("dme")] is None for r in got["rows"])
