"""Each statistic at the end of every quarter (src/open_altio/explorer/quarterly.py): the newest
quarter end is the pair's own statistics, each quarter end agrees with a count made apart from
the explorer on the release's own tables, a pair first reported later has no value before, the
prior is the release's and never fitted again, screens are judged whole and give since when a
pair has been past, rising reads the series and never says false for an empty value, and what
cannot be answered is refused in plain words."""

from __future__ import annotations

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from open_altio.explorer import quarterly
from open_altio.explorer.access import LOCAL, Viewer
from open_altio.explorer.eventstats import statistics_of
from open_altio.explorer.grouped import statistics as group_statistics
from open_altio.explorer.quarterly import BEFORE, COLUMNS, SERIES, series, since
from open_altio.explorer.questions import open_release_data
from open_altio.faers import read_manifest
from open_altio.faers.dates import received_day
from open_altio.rulebook import value
from open_altio.stats import disproportionality as dp
from open_altio.stats import ebgm, screen
from open_altio.testing.releasereader import ReleaseReader

PATH = "/api/statistics/quarters"
MATHS = {
    "prr": "PRR",
    "chi_square_yates": "chi_square_yates",
    "ror": "ROR",
    "ror_lower": "ROR_lower",
    "ic025": "IC025",
}


def same(got, want) -> bool:
    """Equal within a relative 1e-9, an empty value (null, or NaN in a table) only to one."""
    if want is None or (isinstance(want, float) and math.isnan(want)):
        return got is None
    return got is not None and got == pytest.approx(want, rel=1e-9)


def by_column(row: list) -> dict:
    return dict(zip(COLUMNS, row, strict=True))


def newest_qnum(release) -> int:
    newest = read_manifest(release)["quarters"][-1]
    return int(newest[:4]) * 10 + int(newest[-1])


# the newest quarter end -------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", ["stats_release", "release", "licensed_release"])
def test_the_newest_quarter_end_is_each_pairs_own_row_of_the_releases_statistics(request, fixture):
    release = request.getfixturevalue(fixture)
    data = open_release_data(release, LOCAL)
    own = {
        (r["ingredient_T"], r["reaction_T"]): r
        for r in ReleaseReader(release).dicts("SELECT * FROM statistics_T")
    }
    compared = 0
    for drug in sorted({ingredient for ingredient, _ in own}):
        got = series(data, {"product": [drug]})
        assert got["columns"] == ["qnum", *SERIES] and got["reactions"] is None
        assert [e["term"] for e in got["events"]] == [
            r[1] for r in statistics_of(data, {"product": [drug]})["rows"]
        ]
        for event in got["events"]:
            newest = by_column(event["series"][-1])
            assert newest["qnum"] == newest_qnum(release)
            row = own[(drug, event["term"])]
            for name in SERIES:
                assert same(newest[name], row[f"{name}_T"]), (drug, event["term"], name)
            compared += 1
    assert compared == len(own) > 10


def test_a_viewer_shown_fdas_text_reads_the_statistics_counted_by_it(licensed_release):
    data = open_release_data(
        licensed_release, Viewer(id="ann", meddra=False, who=False, todays_names=False)
    )
    rel = ReleaseReader(licensed_release)
    own = rel.dicts("SELECT * FROM statistics_as_published_T WHERE ingredient_T = 'metformin'")
    assert {r["reaction_T"] for r in own} >= {"lactic acidosis"}
    got = {e["term"]: e for e in series(data, {"product": ["metformin"]})["events"]}
    assert set(got) == {r["reaction_T"] for r in own}
    for row in own:
        newest = by_column(got[row["reaction_T"]]["series"][-1])
        for name in SERIES:
            assert same(newest[name], row[f"{name}_T"]), (row["reaction_T"], name)


@pytest.mark.parametrize(
    ("fixture", "drug", "terms"),
    [
        ("stats_release", "warfarin", ["haemorrhage", "nausea"]),
        ("stats_release", "acetylsalicylic acid", ["headache"]),
        ("release", "acetylsalicylic acid", ["headache", "nausea", "haemorrhage"]),
        ("licensed_release", "metformin", ["Acidosis lactic", "nausea"]),
    ],
)
def test_a_groups_newest_quarter_end_is_its_statistics_as_a_group(request, fixture, drug, terms):
    data = open_release_data(request.getfixturevalue(fixture), LOCAL)
    query = {"product": [drug], "reaction": terms}
    got = series(data, query)
    want = group_statistics(data, query)
    assert got["reactions"] == want["reactions"]
    [event] = got["events"]
    assert (event["pt"], event["term"]) == (None, None)
    newest = by_column(event["series"][-1])
    for name in SERIES:
        assert same(newest[name], want[name]), name


# every quarter end, counted apart ---------------------------------------------------------------


def apart(release, ingredient: str, terms: list[str], quarter: int, by: str = "received") -> dict:
    """The table of cases received by the end of `quarter` (yyyyq), worked out apart from the
    explorer from the release's own tables as rule statistics-cases words it: kept cases naming
    an ingredient of a drug in a suspect role and a reaction (FDA's text, case-blind), each in
    the quarter of its received day or, with none, of its own file, in strata of age band, sex
    and the year FDA first received it; then E over the strata and the statistics' formulas
    under the prior the manifest records. By `event`: only the cases giving the full date the
    reaction started, each in that date's quarter."""
    rel = ReleaseReader(release)
    day = f"c.{received_day()}"
    placed = (
        f"coalesce(year({day}) * 10 + quarter({day}), "
        "CAST(left(c.quarter_T, 4) AS INTEGER) * 10 + CAST(right(c.quarter_T, 1) AS INTEGER))"
    )
    if by == "event":
        placed = "year(c.event_dt_T) * 10 + quarter(c.event_dt_T)"
    text = "nullif(trim(regexp_replace(lower(r.pt), '\\s+', ' ', 'g')), '')"
    suspect = (
        "FROM drug_latest_T d JOIN drug_ingredient_T i USING (era_T, primaryid, quarter_T, "
        "drug_seq) WHERE d.era_T = c.era_T AND d.primaryid = c.primaryid "
        "AND d.quarter_T = c.quarter_T AND list_contains($roles, upper(trim(d.role_cod)))"
    )
    named = (
        "FROM reac_latest_T r WHERE r.era_T = c.era_T AND r.primaryid = c.primaryid "
        f"AND r.quarter_T = c.quarter_T AND {text} IS NOT NULL"
    )
    sql = f"""
    WITH counted AS (
      SELECT coalesce(c.age_band_T, $unknown) AS age, coalesce(c.sex_T, $unknown) AS sex,
        coalesce(CAST(c.init_year_T AS VARCHAR), $unknown) AS year,
        EXISTS (SELECT 1 {suspect} AND i.ingredient_T = $ingredient) AS hi,
        EXISTS (SELECT 1 {named} AND list_contains($terms, {text})) AS hg
      FROM case_latest_T c
      WHERE c.dup_kept_T AND {placed} <= $quarter
        AND EXISTS (SELECT 1 {suspect}) AND EXISTS (SELECT 1 {named}))
    SELECT count(*), count(*) FILTER (WHERE hi), count(*) FILTER (WHERE hg),
      count(*) FILTER (WHERE hi AND hg)
    FROM counted GROUP BY age, sex, year"""
    given = {
        "roles": list(value("statistics-cases", "product_roles")),
        "unknown": value("statistics-cases", "unknown"),
        "ingredient": ingredient,
        "terms": terms,
        "quarter": quarter,
    }
    strata = np.array(rel.con.execute(sql, given).fetchall(), dtype=float).reshape(-1, 4)
    n, ni, ng, both = strata.T
    a, total = int(both.sum()), int(n.sum())
    if a == 0:  # no case of the pair yet: the series holds no row
        return {"cases": 0}
    e = float((ni * ng / n).sum())
    maths = dp.measures(**dp.table([a], [int(ni.sum())], [int(ng.sum())], total))
    fit = rel.manifest["statistics"]["ebgm"]
    if fit["fitted"]:
        maths |= ebgm.score(ebgm.Prior(**fit["prior"]), [a], [e])
    out = {"cases": a, **{name: float(maths[source][0]) for name, source in MATHS.items()}}
    for name, source in (("ebgm", "EBGM"), ("eb05", "EB05")):
        out[name] = float(maths[source][0]) if source in maths else None
    return out


def consecutive(qnums: list[int]) -> bool:
    """Every calendar quarter once, in order."""
    counted = [(q // 10) * 4 + q % 10 for q in qnums]
    return counted == list(range(counted[0], counted[0] + len(counted)))


@pytest.mark.parametrize(
    ("fixture", "drug", "terms"),
    [
        ("stats_release", "warfarin", ["haemorrhage"]),
        ("stats_release", "warfarin", ["haemorrhage", "nausea"]),
        ("stats_release", "digoxin", ["nausea"]),
        ("release", "acetylsalicylic acid", ["headache"]),
        ("release", "warfarin", ["haemorrhage", "nausea"]),
    ],
)
def test_each_quarter_end_agrees_with_a_count_made_apart(request, fixture, drug, terms):
    release = request.getfixturevalue(fixture)
    data = open_release_data(release, LOCAL)
    query = {"product": [drug], "reaction": terms}
    [event] = series(data, query)["events"]
    rows = [by_column(row) for row in event["series"]]
    assert len(rows) > 1 and consecutive([r["qnum"] for r in rows])
    assert rows[-1]["qnum"] == newest_qnum(release)
    for row in rows:
        want = apart(release, drug, terms, row["qnum"])
        for name in SERIES:
            assert same(row[name], want[name]), (row["qnum"], name)
    # before the first row, no case of the group with the drug had been received
    first = rows[0]["qnum"]
    before = first - 1 if first % 10 > 1 else (first // 10 - 1) * 10 + 4
    assert apart(release, drug, terms, before)["cases"] == 0 < rows[0]["cases"]


def test_a_pair_first_reported_later_has_no_value_before(stats_release):
    """In the invented release a case is received in the first quarter of one of four years, so
    every pair starts at one of them; some start in a later year than the release's first."""
    data = open_release_data(stats_release, LOCAL)
    rel = ReleaseReader(stats_release)
    [(first,)] = rel.rows("SELECT min(qnum_T) FROM quarter_strata_T")
    got = series(data, {"product": ["warfarin"]})["events"]
    starts = {e["term"]: e["series"][0][0] for e in got}
    later = [term for term, start in starts.items() if start > first]
    assert later and any(start == first for start in starts.values())
    for event in got:
        if event["term"] in later:
            start = starts[event["term"]]
            earlier = apart(stats_release, "warfarin", [event["term"]], start - 10)
            assert earlier["cases"] == 0 and event["series"][0][1] > 0
            assert consecutive([row[0] for row in event["series"]])


def test_the_prior_is_the_releases_own_and_never_fitted_again(stats_release, monkeypatch):
    def no_fit(*args, **kwargs):
        raise AssertionError("the series fitted a prior")

    monkeypatch.setattr(ebgm, "fit_prior", no_fit)
    data = open_release_data(stats_release, LOCAL)
    [event] = series(data, {"product": ["warfarin"], "reaction": ["nausea"]})["events"]
    assert len(event["series"]) > 1
    for row in event["series"]:
        want = apart(stats_release, "warfarin", ["nausea"], row[0])  # under the manifest's prior
        assert row[COLUMNS.index("ebgm")] == pytest.approx(want["ebgm"], rel=1e-9)


def test_a_release_whose_prior_did_not_fit_gives_ebgm_empty_with_its_reason(ask, client, release):
    reason = read_manifest(release)["statistics"]["ebgm"]["reason"]
    got = ask(client, PATH, product="acetylsalicylic acid")
    assert got["not_available"] == dict.fromkeys(("ebgm", "eb05", "eb95"), reason)
    rows = [by_column(row) for e in got["events"] for row in e["series"]]
    assert rows and all(r["ebgm"] is None and r["eb05"] is None for r in rows)
    assert any(r["prr"] is not None for r in rows)


def test_a_group_never_reported_with_the_drug_has_no_value_at_any_quarter_end(ask, client):
    """Omeprazole is named only as a concomitant drug in the invented release."""
    got = ask(client, PATH, product="omeprazole", reaction="headache", rising="prr")
    assert got["events"] == [{"pt": None, "term": None, "series": [], "rising": None}]
    assert ask(client, PATH, product="omeprazole")["events"] == []


# questions side by side ----------------------------------------------------------------------


def test_questions_differing_only_in_their_screens_count_the_series_once(
    stats_release, monkeypatch
):
    """As a host's rows ask: every threshold together, then each alone, at the same moment."""
    data = open_release_data(stats_release, LOCAL)
    screens = [
        [json.dumps([{"column": "cases", "at_least": 2}])],
        [json.dumps([{"column": "prr", "at_least": 2}])],
        [
            json.dumps([{"column": "cases", "at_least": 2}]),
            json.dumps([{"column": "prr", "at_least": 2}]),
        ],
    ]
    questions = [{"product": ["warfarin"], "screen": s, "rising": ["prr"]} for s in screens]
    # each worked out on its own first, on a release opened apart
    alone = [series(open_release_data(stats_release, LOCAL), q) for q in questions]
    calls = []
    real = quarterly._work_out
    together = threading.Barrier(len(questions))

    def counted(*given):
        calls.append(1)
        return real(*given)

    def side_by_side(question):
        together.wait()
        return series(data, question)

    monkeypatch.setattr(quarterly, "_work_out", counted)
    with ThreadPoolExecutor(len(questions)) as pool:
        got = list(pool.map(side_by_side, questions))
    assert got == alone
    assert len(calls) == 1
    # the other date, a group and another drug are other workings
    series(data, {"product": ["warfarin"], "by": ["event"]})
    series(data, {"product": ["warfarin"], "reaction": ["nausea"]})
    series(data, {"product": ["digoxin"]})
    assert len(calls) == 4


# counted by the date the reaction started ---------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "drug", "terms"),
    [
        ("stats_release", "warfarin", ["haemorrhage"]),
        ("stats_release", "warfarin", ["haemorrhage", "nausea"]),
        ("stats_release", "digoxin", ["nausea"]),
        ("release", "warfarin", ["haemorrhage", "nausea"]),
    ],
)
def test_each_quarter_end_by_event_agrees_with_a_count_made_apart(request, fixture, drug, terms):
    release = request.getfixturevalue(fixture)
    data = open_release_data(release, LOCAL)
    got = series(data, {"product": [drug], "reaction": terms, "by": ["event"]})
    assert got["by"] == "event"
    [event] = got["events"]
    rows = [by_column(row) for row in event["series"]]
    assert rows and consecutive([r["qnum"] for r in rows])
    assert rows[-1]["qnum"] == newest_qnum(release)
    for row in rows:
        want = apart(release, drug, terms, row["qnum"], by="event")
        for name in SERIES:
            assert same(row[name], want[name]), (row["qnum"], name)
    first = rows[0]["qnum"]
    before = first - 1 if first % 10 > 1 else (first // 10 - 1) * 10 + 4
    assert apart(release, drug, terms, before, by="event")["cases"] == 0 < rows[0]["cases"]


@pytest.mark.parametrize(
    ("fixture", "drug", "todays_names"),
    [
        ("stats_release", "warfarin", True),
        ("licensed_release", "metformin", True),
        ("licensed_release", "metformin", False),
    ],
)
def test_every_events_series_by_event_agrees_with_its_own_group_of_one(
    request, fixture, drug, todays_names
):
    """The two ways the series is counted, the release's every event and one group, agree, by
    today's terms and by FDA's text."""
    viewer = Viewer(id="ann", meddra=todays_names, who=False, todays_names=todays_names)
    data = open_release_data(request.getfixturevalue(fixture), viewer)
    every = series(data, {"product": [drug], "by": ["event"]})["events"]
    assert any(e["series"] for e in every)
    for event in every:
        query = {"product": [drug], "reaction": [event["term"]], "by": ["event"]}
        [alone] = series(data, query)["events"]
        assert alone["undated"] == event["undated"], event["term"]
        assert len(alone["series"]) == len(event["series"]), event["term"]
        for mine, theirs in zip(event["series"], alone["series"], strict=True):
            for got, want in zip(mine, theirs, strict=True):
                assert same(got, want), (event["term"], mine[0])


def test_by_event_reads_other_quarters_than_by_receipt_and_says_what_it_leaves_out(stats_release):
    data = open_release_data(stats_release, LOCAL)
    query = {"product": ["warfarin"], "reaction": ["haemorrhage"]}
    [received] = series(data, query)["events"]
    [asked] = series(data, query | {"by": ["received"]})["events"]
    assert asked == received and "undated" not in received
    [event] = series(data, query | {"by": ["event"]})["events"]
    assert event["series"] != received["series"]
    # every case of the pair is either at the newest quarter end by its date, or left out
    assert event["undated"] > 0
    assert event["series"][-1][1] + event["undated"] == received["series"][-1][1]


def test_since_by_event_is_the_stretch_on_those_dates(ask, stats_client):
    when = [{"column": "cases", "at_least": 2}]
    got = ask(
        stats_client,
        PATH,
        product="warfarin",
        reaction="haemorrhage",
        screen=json.dumps(when),
        by="event",
    )
    [event] = got["events"]
    assert got["by"] == "event"
    assert event["past"] == [row[1] >= 2 for row in event["series"]]
    assert event["since"] == next(row[0] for row in event["series"] if row[1] >= 2)


def test_a_by_that_is_neither_date_is_refused(ask, stats_client):
    problem = ask(stats_client, PATH, 400, product="warfarin", by="onset")["problem"]
    assert "received" in problem and "event" in problem


# screens and since ------------------------------------------------------------------------------


def test_since_is_the_start_of_the_unbroken_stretch_up_to_the_newest_quarter_end():
    quarters = [20241, 20242, 20243, 20244, 20251, 20252]
    assert since(quarters, [True, True, False, True, True, True]) == 20244
    assert since(quarters, [True, True, False, True, True, False]) is None
    assert since(quarters, [True] * 6) == 20241
    assert since([], []) is None


def test_past_is_each_quarter_ends_screen_and_since_its_stretch(ask, stats_client):
    """Cases only grow, so past a number of cases holds from the first quarter end that reaches
    it to the newest; a screen of a statistic can fall back and start again."""
    plain = ask(stats_client, PATH, product="warfarin")["events"]
    event = max(plain, key=lambda e: e["series"][-1][1])
    cases = [row[1] for row in event["series"]]
    middle = cases[len(cases) // 2]
    when = [{"column": "cases", "at_least": middle}]
    got = ask(stats_client, PATH, product="warfarin", screen=json.dumps(when))
    judged = next(e for e in got["events"] if e["term"] == event["term"])
    assert judged["series"] == event["series"]
    assert judged["past"] == [n >= middle for n in cases]
    assert judged["since"] == next(row[0] for row in event["series"] if row[1] >= middle)
    for other in got["events"]:
        past = [screen.meets(screen.check(when, SERIES), by_column(r)) for r in other["series"]]
        assert other["past"] == past
        assert other["since"] == since([r[0] for r in other["series"]], past)


def test_a_screen_is_judged_whole_and_an_event_is_past_when_it_meets_any_one(ask, stats_client):
    """The PRR preset names chi-square and cases beside PRR; an event that meets PRR alone at a
    quarter end but not the others is not past it there."""
    evans = next(p for p in screen.presets("PRR") if p.get("default"))["when"]
    prr_alone = [c for c in evans if c["column"] == "prr"]
    whole = ask(stats_client, PATH, product="warfarin", screen=json.dumps(evans))["events"]
    alone = ask(stats_client, PATH, product="warfarin", screen=json.dumps(prr_alone))["events"]
    either = ask(
        stats_client, PATH, product="warfarin", screen=[json.dumps(evans), json.dumps(prr_alone)]
    )["events"]
    flat = {name: [p for e in got for p in e["past"]] for name, got in [("w", whole), ("a", alone)]}
    assert any(a and not w for w, a in zip(flat["w"], flat["a"], strict=True))
    assert all(a for w, a in zip(flat["w"], flat["a"], strict=True) if w)
    assert [p for e in either for p in e["past"]] == flat["a"]


def test_an_empty_value_is_never_past(ask, client):
    """The invented release's prior did not fit, so EB05 is empty at every quarter end."""
    ebgm_screen = json.dumps(screen.start("EBGM"))
    got = ask(client, PATH, product="acetylsalicylic acid", screen=ebgm_screen)["events"]
    assert got and all(not any(e["past"]) and e["since"] is None for e in got)


@pytest.mark.parametrize(
    "given",
    [
        "eb05 at least 2",  # not JSON
        '{"column": "eb05", "at_least": 2}',  # not a list
        "[]",  # no condition
        '["eb05"]',
        '[{"column": "eb95", "at_least": 2}]',  # a statistic the series does not give
        '[{"column": "expected", "above": 1}]',
        '[{"column": "eb05", "more_than": 2}]',
        '[{"column": "eb05", "at_least": "2"}]',
    ],
)
def test_a_screen_that_cannot_be_read_is_refused_and_no_event_is_judged(ask, stats_client, given):
    got = ask(stats_client, PATH, 400, product="warfarin", screen=[given])
    assert set(got) == {"problem"} and got["problem"].endswith(("}", "."))
    if "eb95" in given or "expected" in given:
        assert "eb95" in got["problem"] or "expected" in got["problem"]


# rising ----------------------------------------------------------------------------------------


def test_rising_compares_the_newest_quarter_end_with_the_rules_quarters_back(ask, stats_client):
    back = value("trend-rising", "quarters_back")
    got = ask(stats_client, PATH, product="warfarin", rising="eb05")
    assert got["rising"] == {"column": "eb05", "quarters_back": back}
    at = COLUMNS.index("eb05")
    answered = set()
    for event in got["events"]:
        values = [row[at] for row in event["series"]]
        if len(values) <= back:
            assert event["rising"] is None
        else:
            assert event["rising"] is (values[-1] > values[-1 - back])
        answered.add(event["rising"])
    assert answered == {True, False, None}
    assert "past" not in got["events"][0]
    assert ask(stats_client, PATH, product="warfarin")["rising"] is None


def test_rising_is_never_false_for_an_empty_value(ask, client):
    got = ask(client, PATH, product="acetylsalicylic acid", rising="ebgm")["events"]
    assert got and all(e["rising"] is None for e in got)


def test_rising_reads_only_a_column_of_the_series(ask, stats_client):
    got = ask(stats_client, PATH, 400, product="warfarin", rising="eb95")
    assert "eb05" in got["problem"] and got["problem"].endswith(".")


# refusals ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "status"),
    [
        ({}, 400),  # no drug
        ({"product": "no such drug"}, 404),
        ({"product": "sacubitril;valsartan"}, 400),  # a combination
        ({"product": "acetylsalicylic acid", "reaction": " "}, 400),
    ],
)
def test_what_cannot_be_counted_is_refused_in_plain_words(ask, client, query, status):
    problem = ask(client, PATH, status, **query)["problem"]
    assert problem.endswith(".") and "_T" not in problem


def test_a_viewer_the_access_hook_does_not_open_statistics_to_is_refused(
    ask, hooked, stats_release
):
    closed = hooked(
        viewer=Viewer(id="ann", meddra=False, who=False, statistics=False),
        release_dir=stats_release,
    )
    assert "not open" in ask(closed, PATH, 403, product="warfarin")["problem"]


def test_a_release_built_before_the_quarter_counts_says_so(ask, explorer_app, own_release):
    from fastapi.testclient import TestClient

    manifest = json.loads((own_release / "manifest.json").read_text())
    del manifest["quarter_statistics"]
    (own_release / "manifest.json").write_text(json.dumps(manifest))
    web = TestClient(explorer_app(own_release))
    assert ask(web, PATH, 404, product="valsartan")["problem"] == BEFORE


def test_scoring_the_quarter_ends_a_slice_at_a_time_gives_the_same_answer(
    stats_release, monkeypatch
):
    """A drug of many events over many quarters is scored a few quarter ends at a time; the
    invented release fits in one slice, so here every quarter end is a slice of its own."""
    query = {"product": ["warfarin"], "rising": ["prr"]}
    whole = series(open_release_data(stats_release, LOCAL), query)
    monkeypatch.setattr(quarterly, "CELLS_AT_ONCE", 1)
    assert series(open_release_data(stats_release, LOCAL), query) == whole
