"""More of each case on a page of the case list (/api/cases, casecolumns.py), and its orders: with
`detail=columns`, what each case gives about the drug, checked against the same case read whole
(/api/case), apart from the code under test; `total` is every case the question lists, over all
its pages; `case_number` lists only the cases whose number starts with its digits; and every
order puts the cases in its order both ways, a case that gives no value last both ways.

Run over `breakdown_release` (open_altio.testing.fakefda.BREAKDOWN_STORY: valsartan and
Headache, its fields filled before the newest quarter and in it).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from open_altio.rulebook import value

DRUG, EVENT = "valsartan", "Headache"
# every case of the drug, kept or set aside, and every role, so each field is given somewhere
EVERY = {"product": DRUG, "pt": EVENT, "dedup": "all", "prole": ["PS", "SS", "I", "C"]}


@pytest.fixture
def bweb(explorer_app, breakdown_release) -> TestClient:
    return TestClient(explorer_app(breakdown_release))


def listed(ask: Any, web: TestClient, **question: Any) -> list[dict]:
    """Every case the question lists, page after page."""
    out: list[dict] = []
    page = 1
    while True:
        got = ask(web, "/api/cases", page=page, **question)
        out += got["cases"]
        if len(out) >= got["total"] or not got["cases"]:
            return out
        page += 1


def whole(ask: Any, web: TestClient, c: dict) -> dict:
    return ask(web, f"/api/case/{c['era_T']}/{c['case_key_T']}")


# what a case gives about the drug, read from the whole case ------------------------------------

ROLES = ["PS", "SS", "I", "C"]
UNKNOWN = "U"  # FDA's unknown dechallenge or rechallenge reads Not given (rule not-given)


def own_records(case: dict, drug: str = DRUG) -> list[dict]:
    """The drug's records of the case (any product containing it), in the roles asked, by FDA's
    role order then sequence."""
    mine = [
        d
        for d in case["drug"]
        if drug in (d["substance_T"] or "").split(";") and d["role_T"] in ROLES
    ]
    return sorted(mine, key=lambda d: (ROLES.index(d["role_T"]), int(d["drug_seq"])))


def first_given(records: list[dict], field: str, case: dict) -> Any:
    for d in records:
        v = d[field]
        if v is None or str(v).strip() == "" or field in d["not_given_T"]:
            continue
        return str(v).strip().upper() if field in ("dechal", "rechal") else v
    return None


def test_each_case_gives_the_drugs_own_values_as_the_whole_case_reads(bweb, ask):
    cases = listed(ask, bweb, detail="columns", **EVERY)
    assert len(cases) >= 8
    seen = set()
    for c in cases:
        case = whole(ask, bweb, c)
        mine, got = own_records(case), c["columns_T"]
        assert got["role"] == (mine[0]["role_T"] if mine else None), c["case_key_T"]
        for field in ("dechal", "rechal"):
            assert got[field] == first_given(mine, field, case), (c["case_key_T"], field)
        assert got["onset"] == first_given(mine, "time_to_onset_T", case), c["case_key_T"]
        doses = [
            d["dose_vbm"] for d in mine if d["dose_vbm"] and "dose_vbm" not in d["not_given_T"]
        ]
        assert got["dose"] == list(dict.fromkeys(" ".join(x.split()) for x in doses))
        seqs = {d["drug_seq"] for d in mine}
        said = {
            i["indi_pt_T"]
            for i in case["indi"]
            if i["indi_drug_seq"] in seqs and "indi_pt" not in i["not_given_T"] and i["indi_pt"]
        }
        assert set(got["indication"]) == said, c["case_key_T"]
        starts = [t["start_dt_T"] for t in case["ther"] if t["dsg_drug_seq"] in seqs]
        assert (got["start"] or [None])[0] == min(filter(None, starts), default=None)
        others = {r["pt_T"] for r in case["reac"] if r["pt_T"].lower() != EVENT.lower()}
        assert set(got["other_reaction"]) == others, c["case_key_T"]
        assert [s for s in got["suspects"] if s[2]] == [
            [d["drugname"], d["role_T"], True] for d in mine
        ]
        seen |= {f for f in ("dechal", "rechal", "onset", "start") if got[f]}
        seen |= {f for f in ("dose", "indication", "other_reaction") if got[f]}
    # the story gives each of these on some case, so each was checked with a value
    assert {"dechal", "rechal", "onset", "start", "indication", "other_reaction"} <= seen


def test_a_value_that_reads_not_given_is_none(bweb, ask):
    """8101001 gives a dechallenge of U and, in 2012q4, a rechallenge of D: both Not given."""
    [c] = ask(bweb, "/api/cases", detail="columns", case_number="8101001", **EVERY)["cases"]
    assert c["columns_T"]["dechal"] is None and c["columns_T"]["rechal"] is None


def test_columns_are_null_off_a_products_page_and_absent_unless_asked(bweb, ask):
    got = ask(bweb, "/api/cases", detail="columns", pt=EVENT)["cases"]
    assert got and all(c["columns_T"] is None for c in got)
    assert all("columns_T" not in c for c in ask(bweb, "/api/cases", **EVERY)["cases"])


# total and case_number ---------------------------------------------------------------------------


def test_total_is_every_case_the_question_lists(bweb, ask):
    for question in (EVERY, {"product": DRUG}, {"product": DRUG, "sex": "M"}, {"pt": "Nothing"}):
        got = ask(bweb, "/api/cases", **question)
        assert got["total"] == len(listed(ask, bweb, **question))
        assert got["total"] == ask(bweb, "/api/summary", **question)["cases"]


def test_a_case_number_lists_only_the_cases_whose_number_starts_with_its_digits(bweb, ask):
    every = {c["case_key_T"] for c in listed(ask, bweb, **EVERY)}
    for typed in ("810", "8106", " 81 07 ", "8106001", "9"):
        digits = typed.replace(" ", "")
        got = listed(ask, bweb, case_number=typed, **EVERY)
        assert {c["case_key_T"] for c in got} == {k for k in every if k.startswith(digits)}
    # no digits typed is no narrowing
    assert len(listed(ask, bweb, case_number="x", **EVERY)) == len(every)


# the orders ---------------------------------------------------------------------------------------

SERIOUS = list(value("serious-outcomes", "serious"))


def worst(c: dict) -> int | None:
    return min((SERIOUS.index(o) for o in c["outcomes_T"]), default=None)


# each order: the value a case sorts by, read from its page's own fields or its whole case, and
# whether the first choice puts the largest first
def _onset(c: dict, case: dict) -> Any:
    return first_given(own_records(case), "time_to_onset_T", case)


def _dechal(c: dict, case: dict) -> Any:
    code = first_given(own_records(case), "dechal", case)
    return None if code is None else ["Y", "N", "D", "U"].index(code)


ORDERS: dict[str, tuple[Any, bool]] = {
    "case": (lambda c, case: int(c["case_key_T"]), True),
    "age": (lambda c, case: c["age_years_T"], True),
    "sex": (lambda c, case: {"F": 0, "M": 1}.get(c["sex_T"] or ""), False),
    "weight": (lambda c, case: c["wt_kg_T"], True),
    "reporter": (lambda c, case: c["reporter_type_T"], False),
    "serious": (lambda c, case: worst(c), False),
    "event": (lambda c, case: c["event_dt_T"], True),
    "onset": (_onset, True),
    "role": (lambda c, case: min((ROLES.index(d["role_T"]) for d in own_records(case)), default=None), False),  # noqa: E501
    "dechal": (_dechal, False),
}  # fmt: skip


# the orders read over `release`, whose cases give them: weights on aspirin's cases, and valsartan
# as a secondary suspect in a case of its own
ON_RELEASE = {
    "role": EVERY | {"pt": []},
    "weight": EVERY | {"product": "acetylsalicylic acid", "pt": []},
}


@pytest.mark.parametrize("sort", sorted(ORDERS))
def test_each_order_sorts_both_ways_with_not_given_last(sort, bweb, client, ask):
    read, largest_first = ORDERS[sort]
    web, question = (client, ON_RELEASE[sort]) if sort in ON_RELEASE else (bweb, EVERY)
    for way, own in ((sort, True), (f"{sort}-asc", False)):
        got = listed(ask, web, sort=way, **question)
        values = [read(c, whole(ask, web, c)) for c in got]
        given = [v for v in values if v is not None]
        assert values[: len(given)] == given, (way, values)  # Not given last both ways
        assert len(set(given)) > 1, (way, values)
        if sort == "dechal" and not own:
            given = [{1: 0, 0: 1}.get(v, v) for v in given]  # negative first
            largest = False
        else:
            largest = largest_first == own
        assert given == sorted(given, reverse=largest), (way, values)


def test_an_order_from_the_drugs_records_off_a_products_page_is_newest_first(bweb, ask):
    newest = [c["case_key_T"] for c in ask(bweb, "/api/cases", pt=EVENT)["cases"]]
    for sort in ("onset", "role", "dechal-asc", "nothing"):
        got = ask(bweb, "/api/cases", pt=EVENT, sort=sort)["cases"]
        assert [c["case_key_T"] for c in got] == newest
