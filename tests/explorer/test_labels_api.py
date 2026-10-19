"""The label flags the explorer reads from a release (open_altio.explorer.labels), over the
fake release with invented flags (open_altio.testing.fakelabelflags) and over one without them.

The invented flags give acetylsalicylic acid's Headache two forms that disagree (Forms differ), a
Vomiting a model suggested (shown as Uncertain), a trial product with no flag and records with
no RxNorm code; the page tests are test_labels_page.py's.
"""

from __future__ import annotations

import itertools
import json
import random
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import urlencode

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from open_altio.explorer import labels
from open_altio.explorer.filters import label_words, parse
from open_altio.explorer.labels import own_code, product_flag, tiebreak
from open_altio.rulebook import value
from open_altio.testing.fakelabelflags import FLAGS, LABELS, LABELS_AS_OF

OUTCOMES = value("explorer-label-flags", "outcomes")
UNEXPECTED = value("explorer-label-flags", "unexpected_only")
WORDS = value("explorer-label-words", "words")
REASONS = value("explorer-label-words", "reasons")
ASPIRIN = {"product": "acetylsalicylic acid"}
ASPIRIN_ALONE = {**ASPIRIN, "unit": "exact"}
VALSARTAN, ENTRESTO = "valsartan", "sacubitril;valsartan"


def at(path: str, **query) -> str:
    """An address with its query string."""
    return f"{path}?{urlencode(query, doseq=True)}" if query else path


def keys(ask, client, **query) -> set[str]:
    return {c["case_key_T"] for c in ask(client, at("/api/cases", **query))["cases"]}


# a release without the flags -------------------------------------------------------------------


def test_a_release_without_the_flags_shows_none_and_fails_nowhere(ask, client):
    assert ask(client, "/api/release")["labels"] is None
    assert ask(client, at("/api/labels/product", **ASPIRIN)) == {}
    assert ask(client, at("/api/labels/cases", **ASPIRIN)) == {"cases": {}}
    assert ask(client, "/api/labels/case/faers/9021021") == {}
    # a Label status in the address is no filter there: every case shows
    everything = ask(client, at("/api/summary", **ASPIRIN))["cases"]
    assert ask(client, at("/api/summary", **ASPIRIN, label="not_on_label"))["cases"] == everything


# what the page is told -------------------------------------------------------------------------


def test_the_release_tells_the_page_the_flags_order_and_unexpected_only(ask, label_client):
    assert ask(label_client, "/api/release")["labels"] == {
        "outcomes": OUTCOMES,
        "unexpected_only": UNEXPECTED,
        "nothing_ticked": value("explorer-label-flags", "nothing_ticked"),
        "words": WORDS,
        "reasons": REASONS,
        # when the labels are checked against DailyMed each day, for each label link's tip, and
        # the day they are as of, for each flag's tip
        "checked_at_utc": value("label-refresh", "checked_at_utc"),
        "as_of": LABELS_AS_OF.isoformat(),
    }
    assert set(UNEXPECTED) < set(OUTCOMES) == set(label_words()) == set(WORDS)
    # a flag not compared with the label has a reason; no flag's word says "related"
    assert set(REASONS) < set(OUTCOMES)
    assert not any("related" in w.lower() for w in label_words().values())


def test_the_datas_unexpected_flags_are_exactly_what_unexpected_only_keeps(labelled_release):
    """label_flags_T's expectedness_T and the one-click Unexpected only count the same pairs:
    the flags the data reads as unexpected are the ones the button ticks (rules label-flags,
    expectedness, and explorer-label-flags, unexpected_only)."""
    expectedness = value("label-flags", "expectedness")
    assert {k for k, e in expectedness.items() if e == "unexpected"} == set(UNEXPECTED)
    assert expectedness["procedure"] == "unexpected"  # not compared with the label, yet unexpected
    flags = pq.read_table(labelled_release / "parquet" / "label_flags_T.parquet").to_pylist()
    assert all(
        (f["expectedness_T"] == "unexpected") == (f["outcome_T"] in UNEXPECTED) for f in flags
    )


# a product's reactions -------------------------------------------------------------------------


def test_a_products_reactions_each_carry_one_flag_furthest_from_the_label_first(ask, label_client):
    got = ask(label_client, at("/api/labels/product", **ASPIRIN_ALONE))
    flags = dict((pt, f) for pt, f in got["reactions"])
    # by mouth the label lists Headache; two records' forms are not known to be by mouth alone,
    # so they are judged against both labels
    assert flags["Headache"]["outcome"] == "forms_differ"
    assert flags["Headache"]["families"] == [["by_mouth", "on_label"], ["skin", "not_on_label"]]
    assert flags["Headache"]["judged_on"] == ["by_mouth", "skin"]
    # a model's suggestion nobody has checked shows as Uncertain, with no section
    assert flags["Vomiting"]["outcome"] == "uncertain" and flags["Vomiting"]["section"] is None
    assert flags["Hepatic enzyme INCREASED"] | {"families": None, "label": None} == {
        "outcome": "related",
        "section": None,
        "setid": "aspirin-by-mouth",
        "date": LABELS["aspirin-by-mouth"].isoformat(),
        "decided_by": "model_reviewed",
        "forms": ["by_mouth"],  # the forms of the reports that gave it
        "judged_on": ["by_mouth"],
        "families": None,
        "label": None,
        "row": True,
        "others": [],
    }
    ranks = [OUTCOMES.index(f["outcome"]) for _, f in got["reactions"]]
    assert ranks == sorted(ranks)
    # within a form, the drug's own label first, then the newer; each named by its product and
    # ingredients, with no forms, since each code has one label (rule explorer-label-names)
    assert got["labels"] == [
        {
            "setid": "aspirin-by-mouth",
            "version": 1,  # the version the flags were read from, which its link opens
            "date": LABELS["aspirin-by-mouth"].isoformat(),
            "product": "Aspirinex",
            "ingredients": ["aspirin"],
            "forms": [],
        },
        {
            "setid": "aspirin-combination",
            "version": 1,  # the version the flags were read from, which its link opens
            "date": LABELS["aspirin-combination"].isoformat(),
            "product": None,  # a generic's label: its ingredients name it
            "ingredients": ["aspirin", "caffeine"],
            "forms": [],
        },
    ]
    # a flag read on one label carries it, named; Forms differ was read on no one label
    assert flags["Nausea"]["label"] == got["labels"][0]
    assert flags["Headache"]["label"] is None


def test_a_drug_with_no_flags_and_no_drug_answer_nothing_to_flag(ask, label_client):
    # omeprazole is only ever concomitant; a spelling with no ingredient is no drug of its own
    assert ask(label_client, at("/api/labels/product", product="omeprazole")) == {
        "labels": [],
        "reactions": [],
    }
    assert ask(label_client, at("/api/labels/product", product="VALSARTAN TEVA")) == {}
    assert ask(label_client, "/api/labels/product") == {}


def flags_of(ask, client, drug: str, unit: str = "any") -> list[tuple[str, str]]:
    got = ask(client, at("/api/labels/product", product=drug, unit=unit))
    return [(pt, f["outcome"]) for pt, f in got["reactions"]]


def test_counting_any_product_a_combinations_reactions_are_read_on_the_ingredients_own_label(
    ask, label_client
):
    """Entresto's record (sacubitril and valsartan) counts for valsartan, and its Headache is
    judged against valsartan's own label, which does not list it, not Entresto's, which does."""
    got = ask(label_client, at("/api/labels/product", product=VALSARTAN))
    assert [(pt, f["outcome"]) for pt, f in got["reactions"]] == [("Headache", "not_on_label")]
    assert [(x["setid"], x["product"]) for x in got["labels"]] == [("valsartan-by-mouth", "Diovan")]
    assert got["reactions"][0][1]["label"] == got["labels"][0]
    # every case the page counts, Entresto's included, counts under the flag
    page = {"product": VALSARTAN}
    cases = ask(label_client, at("/api/summary", **page))["cases"]
    assert ask(label_client, at("/api/labels/cases", **page))["cases"] == {"not_on_label": cases}
    assert "9210003" in keys(ask, label_client, **page, label="not_on_label")
    (row,) = ask(label_client, at("/api/statistics", ingredient=VALSARTAN))["rows"]
    assert (row["reaction"], row["label"]["outcome"]) == ("Headache", "not_on_label")


def test_counting_the_product_alone_its_records_are_read_on_their_own_codes(ask, label_client):
    """Valsartan's own records have no RxNorm code here, so alone its Headache is No label
    found, and Entresto's case is not counted; Entresto's own page reads Entresto's label."""
    assert flags_of(ask, label_client, VALSARTAN, "exact") == [("Headache", "no_label")]
    assert "9210003" not in keys(ask, label_client, product=VALSARTAN, unit="exact")
    for unit in ("any", "exact"):
        got = ask(label_client, at("/api/labels/product", product=ENTRESTO, unit=unit))
        assert [(pt, f["outcome"]) for pt, f in got["reactions"]] == [("Headache", "on_label")]
        assert [x["setid"] for x in got["labels"]] == ["entresto-by-mouth"]


def test_an_ingredient_with_no_label_of_its_own_shows_no_label_found(ask, label_client):
    """Sacubitril has a code of its own but no label: Entresto's Headache, counted for it, finds
    no label, never Entresto's flag. Sacubitril alone has no records."""
    got = ask(label_client, at("/api/labels/product", product="sacubitril"))
    assert ([(pt, f["outcome"]) for pt, f in got["reactions"]], got["labels"]) == (
        [("Headache", "no_label")],
        [],
    )
    assert flags_of(ask, label_client, "sacubitril", "exact") == []


def test_where_the_ingredient_has_no_label_a_record_of_it_alone_keeps_its_own(
    ask, explorer_app, labelled_release, tmp_path
):
    """Metformin given no code of its own: its own records, coded with metformin's label, keep
    that label's flag on a page counting any product containing it, unless the code names another
    drug; a combination's record holding an ingredient with no label (Entresto's, for
    sacubitril) still finds none."""
    copy = tmp_path / labelled_release.name
    shutil.copytree(labelled_release, copy)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    path = copy / manifest["tables"]["ingredient_rxnorm_T"]["path"]
    sql = "SELECT * REPLACE (if(ingredient_T = 'metformin', NULL, rxcui_T) AS rxcui_T) FROM "
    pq.write_table(duckdb.sql(f"{sql} read_parquet('{path}')").to_arrow_table(), path)
    # case 9023023's record, its code listed as naming another drug, never keeps that code
    tables = manifest["tables"]
    drugs = pq.read_table(copy / tables["drug_latest_T"]["path"]).to_pylist()
    names = ("era_T", "primaryid", "quarter_T", "drug_seq")
    key = next({k: d[k] for k in names} for d in drugs if d["primaryid"] == "90230231")
    pq.write_table(pa.Table.from_pylist([key]), copy / "parquet" / "label_other_drug_T.parquet")
    tables["label_other_drug_T"] = {"path": "parquet/label_other_drug_T.parquet", "rows": 1}
    flags = pq.read_table(copy / tables["label_flags_T"]["path"])
    blank = dict.fromkeys(flags.column_names) | {"route_families_T": "by_mouth"}
    row = blank | {"pt_T": "Lactic acidosis", "outcome_T": "no_label", "decided_by_T": "rule"}
    row["expectedness_T"] = "unexpected"
    joined = pa.concat_tables([flags, pa.Table.from_pylist([row], schema=flags.schema)])
    pq.write_table(joined, copy / tables["label_flags_T"]["path"])
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    client = TestClient(explorer_app(copy))
    assert flags_of(ask, client, "metformin") == [("Lactic acidosis", "on_label")]
    assert flags_of(ask, client, "sacubitril") == [("Headache", "no_label")]
    page = {"product": "metformin"}
    assert keys(ask, client, **page) == {"9023023"}  # the page's one case
    assert keys(ask, client, **page, label="no_label") == {"9023023"}
    assert keys(ask, client, **page, label="on_label") == set()


def test_the_case_window_keeps_each_drugs_own_product_flag(ask, label_client):
    (entresto,) = ask(label_client, "/api/labels/case/faers/9210003")["drugs"]
    assert entresto["name"] == "ENTRESTO" and entresto["label"]["setid"] == "entresto-by-mouth"
    assert entresto["flags"]["Headache"]["outcome"] == "on_label"


def test_counting_any_product_a_record_coded_as_another_product_is_read_on_its_ingredients(
    ask, label_client
):
    """Case 9026026's aspirin record was read to a combination's code: counting any product
    containing aspirin, it is read on aspirin's own label, so that label alone is named."""
    got = ask(label_client, at("/api/labels/product", **ASPIRIN))
    assert [x["setid"] for x in got["labels"]] == ["aspirin-by-mouth"]
    alone = ask(label_client, at("/api/labels/product", **ASPIRIN_ALONE))
    assert [x["setid"] for x in alone["labels"]] == ["aspirin-by-mouth", "aspirin-combination"]


def test_a_record_whose_code_names_another_drug_is_read_on_its_counted_ingredients_label_only(
    ask, explorer_app, labelled_release, tmp_path
):
    """Case 9026026's aspirin record listed in label_other_drug_T, with the rows the label flags
    step writes for it by no code: alone, aspirin's page and the case window never read it on its
    code's label (the combination's), and it finds none; counting any product containing
    aspirin, it is judged on aspirin's own label."""
    copy = tmp_path / labelled_release.name
    shutil.copytree(labelled_release, copy)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    tables = manifest["tables"]
    drugs = pq.read_table(copy / tables["drug_latest_T"]["path"]).to_pylist()
    names = ("era_T", "primaryid", "quarter_T", "drug_seq")
    key = next(
        {k: d[k] for k in names}
        for d in drugs
        if d["drugname"] == "ASPIRIN" and d["primaryid"] == "90260261"
    )
    other = "parquet/label_other_drug_T.parquet"
    pq.write_table(pa.Table.from_pylist([key]), copy / other)
    tables["label_other_drug_T"] = {"path": other, "kind": "derived", "rows": 1}
    flags = pq.read_table(copy / tables["label_flags_T"]["path"])
    found = flags.filter(pa.compute.equal(flags.column("rxcui_T"), "999901")).to_pylist()
    blank = dict.fromkeys(flags.column_names)
    rows = [
        blank
        | {
            "rxcui_T": None,
            "route_families_T": "by_mouth",
            "pt_T": f["pt_T"],
            "outcome_T": "no_label",
            "expectedness_T": "unexpected",
            "decided_by_T": "rule",
        }
        for f in found
    ]
    joined = pa.concat_tables([flags, pa.Table.from_pylist(rows, schema=flags.schema)])
    pq.write_table(joined, copy / tables["label_flags_T"]["path"])
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    client = TestClient(explorer_app(copy))
    alone = ask(client, at("/api/labels/product", **ASPIRIN_ALONE))
    assert [x["setid"] for x in alone["labels"]] == ["aspirin-by-mouth"]  # never the code's
    drugs = ask(client, "/api/labels/case/faers/9026026")["drugs"]
    (aspirin,) = [d for d in drugs if d["name"] == "ASPIRIN"]
    assert (aspirin["coded"], aspirin["label"]) == (False, None)
    assert aspirin["flags"]["Haemorrhage"]["outcome"] == "no_label"
    assert "9026026" in keys(ask, client, **ASPIRIN_ALONE, label="no_label")
    assert "9026026" not in keys(ask, client, **ASPIRIN_ALONE, label="on_label")
    # counting any product containing aspirin: aspirin's own label, which lists Haemorrhage
    assert "9026026" in keys(ask, client, **ASPIRIN, label="on_label")
    assert "9026026" not in keys(ask, client, **ASPIRIN, label="no_label")


@pytest.mark.parametrize(
    "flags, expected",
    [
        # one form, or forms that agree: that flag
        ([("by_mouth", "on_label", "expected")], "on_label"),
        ([("by_mouth", "related", "unexpected"), ("skin", "related", "unexpected")], "related"),
        # one form's label lists it and another's does not: Forms differ
        (
            [("by_mouth", "on_label", "expected"), ("skin", "not_on_label", "unexpected")],
            "forms_differ",
        ),
        # they differ but all read unexpected: the one closest to the label, as the comparison
        (
            [("by_mouth", "related", "unexpected"), ("skin", "not_on_label", "unexpected")],
            "related",
        ),
        # a report that found no label (no RxNorm code) decides only when no report found one
        (
            [("by_mouth", "on_label", "expected"), ("by_mouth", "no_label", "unexpected")],
            "on_label",
        ),
        ([("", "no_label", "unexpected"), ("by_mouth", "no_label", "unexpected")], "no_label"),
        (
            [("by_mouth", "not_on_label", "unexpected"), ("skin", "uncertain", "unexpected")],
            "uncertain",
        ),
    ],
)
def test_a_products_row_resolves_its_reports_as_the_comparison_resolves_forms(flags, expected):
    got = product_flag(
        [
            {
                "forms": f,
                "judged_on": f if o != "no_label" else None,
                "outcome": o,
                "expectedness": e,
                "section": None,
                "setid": None,
                "date": None,
                "decided_by": "rule",
                "families": None,
            }
            for f, o, e in flags
        ]
    )
    assert got["outcome"] == expected
    if expected == "forms_differ":
        assert got["families"] == [["by_mouth", "on_label"], ["skin", "not_on_label"]]
    else:  # the other outcomes, for its tip; a report that found no label is not one of them
        assert got["others"] == sorted({o for _, o, _ in flags} - {expected, "no_label"})


# Label status ------------------------------------------------------------------------------------


def test_every_tick_on_is_no_filter_and_none_ticked_keeps_no_case(ask, label_client):
    everything = ask(label_client, at("/api/summary", **ASPIRIN))["cases"]
    assert everything > 0
    assert ask(label_client, at("/api/summary", **ASPIRIN, label="none"))["cases"] == 0
    # a value that is no flag is ignored, so the list keeps its true total
    assert ask(label_client, at("/api/summary", **ASPIRIN, label="bogus"))["cases"] == everything


def test_each_flags_count_is_its_cases_under_the_other_filters(ask, label_client):
    for other in ({}, {"sex": "F"}, {"outcome": "OT"}):
        counts = ask(label_client, at("/api/labels/cases", **ASPIRIN, **other, label="related"))[
            "cases"
        ]
        for flag in OUTCOMES:
            assert (
                counts.get(flag, 0)
                == ask(label_client, at("/api/summary", **ASPIRIN, **other, label=flag))["cases"]
            ), (other, flag)


def test_unexpected_only_keeps_the_cases_with_at_least_one_unexpected_reaction(ask, label_client):
    each = set().union(*(keys(ask, label_client, **ASPIRIN, label=flag) for flag in UNEXPECTED))
    assert keys(ask, label_client, **ASPIRIN, label=UNEXPECTED) == each
    assert "9013013" in each  # its Headache: Forms differ
    assert "9005005" in each  # its Vomiting: a model's suggestion, so Uncertain


def test_label_status_combines_with_the_other_filters(ask, label_client):
    picked = keys(ask, label_client, **ASPIRIN, label=["on_label", "uncertain"], outcome="OT")
    assert picked == keys(ask, label_client, **ASPIRIN, label=["on_label", "uncertain"]) & keys(
        ask, label_client, **ASPIRIN, outcome="OT"
    )
    assert picked


def test_a_trial_product_and_a_drug_in_another_role_have_no_flag(ask, label_client):
    # case 9004004 names aspirin only as BAYER LOW DOSE, marked a trial product
    flagged = set().union(*(keys(ask, label_client, **ASPIRIN, label=flag) for flag in OUTCOMES))
    assert "9004004" in keys(ask, label_client, **ASPIRIN) and "9004004" not in flagged
    assert ask(label_client, "/api/labels/case/faers/9004004") == {"drugs": []}
    # case 9006006 names aspirin only as interacting: no flag for it
    assert "9006006" not in flagged


def test_label_status_is_said_in_words_kept_in_the_address_and_never_lists_its_cases():
    filters = parse({"label": ["related", "not_on_label", "procedure", "bogus"]})
    assert filters.labels == ("related", "not_on_label", "procedure")
    # a flag not compared with the label says why, in brackets in a line of words
    procedure = f"{WORDS['procedure']} ({REASONS['procedure']})"
    said = f"{WORDS['related']}, {WORDS['not_on_label']}, {procedure}"
    assert ("Label status", said) in filters.described()
    assert filters.query() == "label=related&label=not_on_label&label=procedure"
    filters = filters.with_(label_cases=(1, 2, 3))
    assert "label_cases" not in filters.manifest()["filters"]
    assert parse({"label": ["none"]}).query() == "label=none"
    assert parse({}).labels is None


# one case --------------------------------------------------------------------------------------


def test_a_cases_suspect_drugs_each_carry_their_flag_per_reaction_and_their_label(
    ask, label_client
):
    got = ask(label_client, "/api/labels/case/faers/9021021")
    # two warfarin records, one code and route: one line
    assert [d["name"] for d in got["drugs"]] == ["Aspirin", "warfarin"]
    aspirin, warfarin = got["drugs"]
    expected = {(f.rxcui, f.pt): f for f in FLAGS}
    for code, drug in (("1191", aspirin), ("11289", warfarin)):
        assert set(drug["flags"]) == {"Haemorrhage", "Nausea"}
        for pt, flag in drug["flags"].items():
            row = expected[(code, pt)]
            assert (flag["outcome"], flag["section"], flag["setid"]) == (
                row.outcome,
                row.section,
                row.setid,
            )
        assert (drug["label"]["setid"], drug["label"]["date"]) == (
            row.setid,
            LABELS[row.setid].isoformat(),
        )
        assert all(f["label"] == drug["label"] for f in drug["flags"].values())
    assert (aspirin["label"]["product"], warfarin["label"]["product"]) == ("Aspirinex", "Warfarex")
    assert ask(label_client, "/api/labels/case/faers/nothing") == {"drugs": []}


def test_a_flag_read_on_another_forms_label_says_which(ask, label_client):
    """Doxorubicin has an injection label only: its record taken by mouth is read on it."""
    bleomycin, doxorubicin = ask(label_client, "/api/labels/case/faers/5100010")["drugs"]
    assert doxorubicin["name"] == "DOXORUBICIN" and doxorubicin["coded"]
    flag = doxorubicin["flags"]["Headache"]
    assert (flag["outcome"], flag["forms"], flag["judged_on"]) == (
        "on_label",
        ["by_mouth"],
        ["injected"],
    )


def test_a_record_with_no_rxnorm_code_shows_no_label_found_and_never_vanishes(ask, label_client):
    bleomycin, _ = ask(label_client, "/api/labels/case/faers/5100010")["drugs"]
    assert (bleomycin["name"], bleomycin["coded"], bleomycin["label"]) == (
        "BLEOMYCIN SULFATE",
        False,
        None,
    )
    assert bleomycin["flags"]["Headache"]["outcome"] == "no_label"
    # valsartan's own records have no code: each of its cases counts under No label found
    valsartan = {"product": "valsartan", "unit": "exact"}
    assert ask(label_client, at("/api/labels/cases", **valsartan))["cases"] == {
        "no_label": ask(label_client, at("/api/summary", **valsartan))["cases"]
    }


def test_a_record_whose_code_names_another_drug_shows_no_label_found(
    ask, explorer_app, labelled_release, tmp_path
):
    """The label flags step lists such a record in label_other_drug_T; the screens then read it
    as a record with no code, never on the code's label."""
    copy = tmp_path / labelled_release.name
    shutil.copytree(labelled_release, copy)
    _, doxorubicin = ask(TestClient(explorer_app(copy)), "/api/labels/case/faers/5100010")["drugs"]
    assert doxorubicin["coded"] and doxorubicin["label"]
    manifest = json.loads((copy / "manifest.json").read_text())
    drugs = pq.read_table(copy / manifest["tables"]["drug_latest_T"]["path"]).to_pylist()
    key = next(
        {k: d[k] for k in ("era_T", "primaryid", "quarter_T", "drug_seq")}
        for d in drugs
        if d["drugname"] == "DOXORUBICIN" and d["caseid"] == "5100010"
    )
    path = "parquet/label_other_drug_T.parquet"
    pq.write_table(pa.Table.from_pylist([key]), copy / path)
    manifest["tables"]["label_other_drug_T"] = {"path": path, "kind": "derived", "rows": 1}
    (copy / "manifest.json").write_text(json.dumps(manifest))
    _, doxorubicin = ask(TestClient(explorer_app(copy)), "/api/labels/case/faers/5100010")["drugs"]
    assert (doxorubicin["coded"], doxorubicin["label"]) == (False, None)
    assert doxorubicin["flags"]["Headache"]["outcome"] == "no_label"


@pytest.mark.parametrize(
    "case, forms",
    [
        ("9110011", ["by_mouth", "skin"]),  # on the skin or by mouth
        ("9013013", []),  # nothing known of its form
        ("9001001", ["by_mouth"]),
    ],
)
def test_a_record_is_joined_by_its_route_families_as_the_route_step_writes_them(
    ask, label_client, case, forms
):
    (drug,) = ask(label_client, f"/api/labels/case/faers/{case}")["drugs"]
    flag = drug["flags"]["Headache"]
    assert flag["forms"] == forms
    assert flag["outcome"] == ("on_label" if forms == ["by_mouth"] else "forms_differ")


def test_a_release_without_drug_route_reads_every_record_with_no_form_known(
    ask, explorer_app, labelled_release, tmp_path
):
    copy = tmp_path / labelled_release.name
    shutil.copytree(labelled_release, copy)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    del manifest["tables"]["drug_route_T"]
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    client = TestClient(explorer_app(copy))
    (drug,) = ask(client, "/api/labels/case/faers/9001001")["drugs"]
    assert (drug["flags"]["Headache"]["forms"], drug["flags"]["Headache"]["outcome"]) == (
        [],
        "forms_differ",
    )


def test_the_flags_read_drug_route_as_the_route_step_builds_it_with_the_release(
    ask, explorer_app, labelled_release, licensed_release, tmp_path
):
    """The route-families contract: the label flags query runs on the drug_route_T the build
    wrote, text sorted and joined with ";", not on an invented one."""
    copy = tmp_path / labelled_release.name
    shutil.copytree(labelled_release, copy)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    built = json.loads((licensed_release / "manifest.json").read_text(encoding="utf-8"))
    step = pq.read_table(licensed_release / built["tables"]["drug_route_T"]["path"])
    assert step.schema.field("route_families_T").type == pa.string()
    families = set(step.column("route_families_T").to_pylist()) - {None}
    assert families and all(f == ";".join(sorted(set(f.split(";")))) for f in families)
    (oral,) = families  # the fake release's drugs are all oral tablets
    pq.write_table(step, copy / manifest["tables"]["drug_route_T"]["path"])
    # the invented flags, one per drug and reaction, under the families the step wrote
    flags_path = copy / manifest["tables"]["label_flags_T"]["path"]
    flags = duckdb.sql(
        f"SELECT * REPLACE ('{oral}' AS route_families_T) FROM read_parquet('{flags_path}') "
        "QUALIFY row_number() OVER (PARTITION BY rxcui_T, pt_T ORDER BY setid_T) = 1"
    ).to_arrow_table()
    pq.write_table(flags, flags_path)
    for name, table in (("drug_route_T", step), ("label_flags_T", flags)):
        entry = manifest["tables"][name]
        entry.update(rows=table.num_rows, bytes=(copy / entry["path"]).stat().st_size)
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    client = TestClient(explorer_app(copy))
    (drug,) = ask(client, "/api/labels/case/faers/9001001")["drugs"]
    assert drug["flags"]["Headache"]["forms"] == oral.split(";")
    assert ask(client, at("/api/labels/product", **ASPIRIN))


# the Statistics tab ----------------------------------------------------------------------------


def stats(ask, client, **query) -> dict:
    return ask(client, at("/api/statistics", ingredient="acetylsalicylic acid", **query))


def test_each_statistics_row_of_a_drug_carries_its_flag_and_the_labels_read(ask, label_client):
    got = stats(ask, label_client)
    flags = {r["reaction"]: (r["label"] or {}).get("outcome") for r in got["rows"]}
    assert flags == {
        "Haemorrhage": "on_label",
        "Headache": "forms_differ",
        "Hepatic enzyme increased": "related",
        "Nausea": "not_on_label",
        "Vomiting": "uncertain",
    }
    assert (
        got["label"]["labels"] == ask(label_client, at("/api/labels/product", **ASPIRIN))["labels"]
    )
    assert got["label"]["counts"] == {f: 1 for f in flags.values()}


def test_label_status_narrows_the_statistics_list_and_sorting_puts_furthest_first(
    ask, label_client
):
    got = stats(ask, label_client, label=UNEXPECTED)
    assert got["matched"] == 4 and "Haemorrhage" not in {r["reaction"] for r in got["rows"]}
    # the counts are of every reaction, under the other choices
    assert got["label"]["counts"]["on_label"] == 1
    assert stats(ask, label_client, label="none")["matched"] == 0
    ordered = stats(ask, label_client, sort="label", dir="desc")["rows"]
    ranks = [OUTCOMES.index(r["label"]["outcome"]) for r in ordered]
    assert ranks == sorted(ranks)
    # All cases has no Label column, so it cannot be sorted by one
    assert label_client.get(at("/api/statistics", sort="label")).status_code == 400
    assert "label" not in ask(label_client, "/api/statistics")


def test_a_release_without_the_flags_gives_statistics_no_label(ask, licensed_client):
    got = ask(licensed_client, at("/api/statistics", ingredient="acetylsalicylic acid"))
    assert "label" not in got and all("label" not in r for r in got["rows"])


def test_a_drugs_flags_are_read_once_while_its_page_asks_for_them_side_by_side(
    label_client, monkeypatch
):
    """The Statistics tab and Label status ask for a drug's flags at once; they are read once."""
    read, reads = labels._read, []

    def slow(*args):
        reads.append(args)
        time.sleep(0.5)  # the other question arrives while this one reads
        return read(*args)

    monkeypatch.setattr(labels, "_read", slow)
    asks = [
        at("/api/statistics", ingredient=ASPIRIN["product"]),
        at("/api/labels/cases", **ASPIRIN),
    ]
    with ThreadPoolExecutor(len(asks)) as pool:
        got = list(pool.map(label_client.get, asks))
    assert [g.status_code for g in got] == [200, 200]
    assert len(reads) == 1


def test_a_drugs_reactions_are_resolved_with_the_rule_read_once_for_them_all(
    ask, label_client, monkeypatch
):
    """Each rule read parses its file, so a big drug's thousands of reactions are resolved
    without reading the rule again for any one of them."""
    read, resolve = labels.value, labels.product_flag
    resolving, reads = [], []

    def counted(*args):
        if resolving:
            reads.append(args)
        return read(*args)

    def one(*args, **kwargs):
        resolving.append(args)
        try:
            return resolve(*args, **kwargs)
        finally:
            resolving.pop()

    monkeypatch.setattr(labels, "value", counted)
    monkeypatch.setattr(labels, "product_flag", one)
    got = ask(label_client, at("/api/labels/product", **ASPIRIN))
    assert len(got["reactions"]) > 1 and reads == []


# when labels agree -------------------------------------------------------------------------------


def agreeing(*labels: tuple[str | None, str | None, date | None]) -> list[dict]:
    """Flags of one reaction that agree, each read on its own label: (term type, set ID, date)."""
    return [
        {
            "tty": tty,
            "forms": "by_mouth",
            "outcome": "not_on_label",
            "expectedness": "unexpected",
            "section": None,
            "setid": setid,
            "date": day,
            "decided_by": "rule",
            "families": None,
            "judged_on": "by_mouth",
        }
        for tty, setid, day in labels
    ]


@pytest.mark.parametrize(
    "labels, named",
    [
        # the drug's own label first, however new the other
        ([("MIN", "newer-combination", date(2026, 5, 1)), ("IN", "own", date(2020, 1, 1))], "own"),
        # then the newest label
        ([("IN", "older", date(2020, 1, 1)), ("IN", "newer", date(2026, 1, 1))], "newer"),
        # then the lower set ID; a flag read on no one label last
        ([("IN", "b", date(2026, 1, 1)), ("IN", "a", date(2026, 1, 1)), ("IN", None, None)], "a"),
    ],
)
def test_a_drugs_row_names_one_label_whatever_order_its_flags_come_in(labels, named):
    own = own_code("acetylsalicylic acid")
    for order in itertools.permutations(agreeing(*labels)):
        assert product_flag(list(order), own=own)["setid"] == named
    assert own == "IN" and own_code("sacubitril;valsartan") == "MIN"


def test_a_cases_drug_names_its_newest_label_then_the_lower_set_id_over_shuffled_flags():
    flags = agreeing(
        ("IN", "b", date(2025, 1, 1)), ("IN", "a", date(2025, 1, 1)), ("IN", "c", date(2024, 1, 1))
    )
    best = tiebreak(None)
    rng = random.Random(0)
    for _ in range(20):
        rng.shuffle(flags)
        assert min(flags, key=best)["setid"] == "a"


def test_a_drugs_row_names_its_own_label_over_a_combinations_newer_one_on_every_run(
    ask, explorer_app, labelled_release
):
    """Case 9026026's aspirin record was read to a combination's code, whose newer label agrees
    with aspirin's own on Nausea and Haemorrhage."""
    answers = []
    for _ in range(4):  # a fresh app each time, so nothing remembered carries over
        client = TestClient(explorer_app(labelled_release))
        got = dict(ask(client, at("/api/labels/product", **ASPIRIN_ALONE))["reactions"])
        rows = {r["reaction"]: r["label"]["setid"] for r in stats(ask, client)["rows"]}
        answers.append((got, rows))
        assert got["Nausea"]["setid"] == got["Haemorrhage"]["setid"] == "aspirin-by-mouth"
        assert rows["Nausea"] == rows["Haemorrhage"] == "aspirin-by-mouth"
    assert all(a == answers[0] for a in answers)
