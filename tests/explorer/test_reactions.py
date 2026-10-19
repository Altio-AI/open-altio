"""Reactions counted and found by their current PT where the release holds MedDRA, for everyone,
and by FDA's text where it holds none (src/open_altio/explorer/reactions.py, rule meddra-terms).

In the invented MedDRA 29.1 (open_altio.testing.fakemeddra) FDA's Arrhythmia is a lower level
term of the PT Heart rhythm abnormal, and FDA's Lactic acidosis an older name of the PT Acidosis
lactic. The text to PT link itself, the current PT beside FDA's text in the case list and a
case, is given only to a viewer with MedDRA's licensed part.
"""

from __future__ import annotations

import pytest


def kept_cases(rel, *texts: str) -> int:
    """Kept cases with a reaction FDA wrote as one of `texts`, whatever its capitals."""
    marks = ", ".join("?" for _ in texts)
    named = f"lower(r.pt) IN ({marks})"
    reacs = f"EXISTS (SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')} AND {named})"
    return len(rel.case_keys(reacs, *[t.lower() for t in texts]))


def test_a_pt_counts_every_case_fda_wrote_under_an_older_term(licensed_client, rel, ask):
    want = kept_cases(rel, "Arrhythmia")
    assert want > 0
    assert ask(licensed_client, "/api/summary", pt="Heart rhythm abnormal")["cases"] == want
    assert ask(licensed_client, "/api/summary", reaction="heart RHYTHM abnormal")["cases"] == want
    reported = dict(map(tuple, ask(licensed_client, "/api/summary")["reactions"]))
    assert reported["Heart rhythm abnormal"] == want and "Arrhythmia" not in reported


def test_the_reaction_search_finds_the_pt_and_not_the_older_term(licensed_client, rel, ask):
    found = ask(licensed_client, "/api/terms", q="heart rhythm")["terms"]
    assert found == [["Heart rhythm abnormal", kept_cases(rel, "Arrhythmia")]]
    # an older term is found only as a lower level term, by a viewer who may see them
    assert ask(licensed_client, "/api/terms", q="arrhythm")["terms"] == []
    llts = ask(licensed_client, "/api/terms", q="arrhythm", meddra="1")["llts"]
    assert [x[:2] for x in llts] == [["Arrhythmia", "Heart rhythm abnormal"]]
    counted = ask(licensed_client, "/api/termcounts", pt=["heart rhythm abnormal"])["terms"]
    assert counted == [["Heart rhythm abnormal", kept_cases(rel, "Arrhythmia")]]


def test_a_text_that_is_no_current_pt_still_matches_what_fda_wrote(licensed_client, rel, ask):
    assert ask(licensed_client, "/api/summary", pt="Arrhythmia")["cases"] == kept_cases(
        rel, "Arrhythmia"
    )


def test_a_statistics_pair_opens_as_many_cases_as_its_row_counts(licensed_client, ask):
    [row] = ask(licensed_client, "/api/statistics?ingredient=metformin&find=acidosis")["rows"]
    asked = ask(licensed_client, "/api/summary", product="metformin", pt=row["term"])
    assert asked["cases"] == row["cases"] > 0


def test_without_meddra_reactions_are_fdas_text_as_today(client, rel, ask):
    assert ask(client, "/api/summary", pt="Arrhythmia")["cases"] == kept_cases(rel, "Arrhythmia")
    assert ask(client, "/api/summary", pt="Heart rhythm abnormal")["cases"] == 0
    assert ask(client, "/api/terms", q="arrhyth")["terms"][0][0] == "Arrhythmia"
    assert ask(client, "/api/release")["reactions"] == {
        "counted_by": "fda_text",
        "meddra_version": None,
    }


@pytest.mark.parametrize("who", ["ann", "ann+meddra"])
def test_everyone_counts_by_the_pt_whether_or_not_they_see_meddra(
    people, licensed_release, rel, ask, who
):
    web = people(licensed_release)
    seen = {"X-Viewer": who}
    assert ask(web, "/api/release", headers=seen)["reactions"] == {
        "counted_by": "current_pt",
        "meddra_version": "29.1",
    }
    got = ask(web, "/api/summary", headers=seen, pt="Heart rhythm abnormal")["cases"]
    assert got == kept_cases(rel, "Arrhythmia")
    listed = ask(web, "/api/cases", headers=seen, pt="Heart rhythm abnormal")
    one = ask(web, "/api/case/legacy/5100009", headers=seen)
    if who == "ann":  # no MedDRA: FDA's text alone, never the PT it reads to
        assert "current_pts_T" not in listed["cases"][0] and "meddra_version" not in listed
        assert "current_pt_T" not in one["reac"][0] and "meddra_version" not in one
    else:
        assert listed["meddra_version"] == one["meddra_version"] == "29.1"
        assert one["reac"][0]["current_pt_T"] == {
            "name": "Heart rhythm abnormal",
            "matched_as": "llt",
        }
    assert {t for c in listed["cases"] for t in c["reactions"]} <= {
        "ARRHYTHMIA",
        "Arrhythmia",
    }


def test_a_case_shows_meddras_spelling_of_an_old_term_and_reads_every_column(licensed_client, ask):
    legacy = ask(licensed_client, "/api/case/legacy/5100009")
    assert [(r["pt"], r["pt_T"]) for r in legacy["reac"]] == [("ARRHYTHMIA", "Arrhythmia")]
    assert [(i["indi_pt"], i["indi_pt_T"]) for i in legacy["indi"]] == [("PAIN", "Pain")]
    assert legacy["indi"][0]["current_pt_T"] is None  # Pain is a PT: nothing to show beside
    again = ask(licensed_client, "/api/case/faers/9013013")["reac"][0]
    # FDA writes an apostrophe in drug_rec_act as ^, so the PT is another name for the text
    assert (again["drug_rec_act"], again["rec_act_current_pt_T"]) == (
        "Parkinson^s disease",
        {"name": "Parkinson's disease", "matched_as": "pt"},
    )
    free = ask(licensed_client, "/api/case/faers/9005005")["indi"]
    shown = [(i["indi_pt"], i["current_pt_T"]) for i in free]
    assert shown == [("Pain", None), ("Dyspepsia", None)]  # Dyspepsia: free text, as written
