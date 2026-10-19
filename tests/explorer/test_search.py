"""The searches (search.py): the reactions the search boxes offer, each with its cases. The
lower-level terms and SMQs a licensed viewer also finds are test_meddra.py's; the drugs and the
spellings a product page counts are test_drugs.py's. What each should count is read from the
release's own Parquet through `rel`.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import duckdb
from fastapi.testclient import TestClient

from open_altio.explorer import search
from open_altio.explorer.app import create_app
from open_altio.explorer.context import Asking
from open_altio.explorer.found import found_order, found_order_sql
from open_altio.explorer.release import OpenRelease
from open_altio.testing.rules import rules_with


def test_the_reaction_search_finds_preferred_terms_with_their_cases(client, rel, ask):
    got = ask(client, "/api/terms", q=" NAU ", kind="all")
    assert got["q"] == "nau"
    nausea = dict(map(tuple, got["terms"]))["Nausea"]
    named = f"EXISTS (SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')} AND lower(r.pt) = ?)"
    want = len(rel.case_keys(named, "nausea"))
    assert nausea == want and got["totals"]["pt"] == len(got["terms"])
    counts = dict(map(tuple, ask(client, "/api/termcounts", pt=["nausea", "VOMITING"])["terms"]))
    assert counts["Nausea"] == want


# the order every search box lists its finds in (found.py, rule explorer-lists) -------------------


def test_a_find_named_as_typed_comes_first_then_those_starting_so_then_the_rest():
    names = ["absence seizure", "seizures", "seizure", "sei"]
    assert [found_order("seizure", n) for n in names] == [2, 1, 0, None]
    assert found_order("seizure", None, "seizure cluster", "seizure") == 0
    first, params = found_order_sql("seizure", "n")
    rows = duckdb.sql(
        f"SELECT n FROM (SELECT unnest(?::VARCHAR[]) AS n) WHERE contains(n, ?) ORDER BY {first}",
        params=[names, "seizure", *params],
    ).fetchall()
    assert [n for (n,) in rows] == ["seizure", "seizures", "absence seizure"]


def test_find_a_drug_lists_the_drug_named_first_then_those_starting_so_then_the_rest():
    def drug(name: str, *reported: str) -> dict:
        return {"name": name, "title": name.capitalize(), "reported": list(reported)}

    drugs = [  # most cases first, as the release's facts list them
        drug("sacubitril;valsartan", "ENTRESTO"),
        drug("valsartan hydrochloride"),
        drug("amlodipine;valsartan"),
        drug("valsartan", "DIOVAN"),
    ]
    data = SimpleNamespace(facts=SimpleNamespace(drugs=drugs, once=lambda name, make: make()))
    assert [d["name"] for d in search._found(data, "valsartan")] == [
        "valsartan",
        "valsartan hydrochloride",
        "sacubitril;valsartan",
        "amlodipine;valsartan",
    ]
    assert [d["name"] for d in search._found(data, "diovan")] == ["valsartan"]


def test_the_reaction_search_lists_the_term_typed_then_those_starting_so_then_the_rest(client, ask):
    got = ask(client, "/api/terms", q="a", kind="all")["terms"]
    names = [t for t, _ in got]
    places = [found_order("a", t.lower()) for t in names]
    assert places == sorted(places) and None not in places and places[0] == 1
    assert names.index("Headache") > names.index("Arrhythmia")  # though it has most cases
    rest = [n for t, n in got if found_order("a", t.lower()) == 2]
    assert rest == sorted(rest, reverse=True)  # most cases first within each
    assert ask(client, "/api/terms", q="nausea", kind="all")["terms"][0][0] == "Nausea"


def test_the_spellings_a_drug_page_finds_come_named_first_then_starting_so(client, ask):
    for q in ("valsartan", "a", "o"):
        got = ask(client, "/api/spellings", product="valsartan", q=q)
        typed = q.upper()
        for found in (got["spellings"], got["unmapped"]):
            places = [found_order(typed, s) for s, _ in found]
            assert places == sorted(places) and None not in places
    assert ask(client, "/api/spellings", product="valsartan", q="valsartan")["spellings"][0][0] == (
        "VALSARTAN"
    )


def test_lower_level_terms_and_smqs_come_named_first_then_starting_so(licensed_client, ask):
    for q in ("head", "ache", "bleeding", "invented"):
        got = ask(licensed_client, "/api/terms", q=q, kind="all", meddra="1")
        for found in ([x[0] for x in got["llts"]], [x[1] for x in got["smqs"]]):
            places = [found_order(q, n.lower()) for n in found]
            assert places == sorted(places) and None not in places


# a warmed explorer -------------------------------------------------------------------------------


def test_a_warmed_explorer_answers_the_first_searches_from_what_it_worked_out(
    classes_release, clock, monkeypatch, tmp_path
):
    """Warmed as its release opens, the explorer's first searches under no filter read no
    record of a case: the drugs, the reactions' and the classes' cases are worked out already."""
    with rules_with(tmp_path, {"explorer-read-memory": {"warm_after_quiet_seconds": 0}}):
        app = create_app(classes_release, clock=clock, warm=True)
        for name in ("open-altio-open", "open-altio-warm"):
            for thread in [t for t in threading.enumerate() if t.name == name]:
                thread.join(60)
    asked: list[str] = []
    rows = OpenRelease.rows

    def counted(self, sql, params=None):
        asked.append(sql)
        return rows(self, sql, params)

    monkeypatch.setattr(OpenRelease, "rows", counted)
    web = TestClient(app)
    for path in ("/api/classes?q=a", "/api/terms?q=a&kind=all", "/api/products?q=a"):
        assert web.get(path).status_code == 200
    read = [s for s in asked if any(t in s for t in ("atc_term_T", "reac_term_T", "no_ingredient"))]
    assert asked and read == []


def test_warming_waits_for_a_moment_when_no_page_is_asking():
    asking, waited = Asking(), threading.Event()
    with asking.one():
        thread = threading.Thread(target=lambda: (asking.quiet(0.05), waited.set()))
        thread.start()
        time.sleep(0.3)
        assert not waited.is_set()  # a page is being answered
    thread.join(5)
    assert waited.is_set()
