"""MedDRA's licensed part as the explorer serves it: SMQs and lower-level
terms in the reaction search, an SMQ's terms, an SMQ as a filter, and the
release's one version served whatever the day (rule meddra-version), MedDRA added to the
live release, whose statistics are then counted by its PTs, and a MedDRA part an older version
of Open Altio added, which is left out with a word on how to add it again.

Run over `licensed_release`, the fake release built with the invented MedDRA
29.1 (open_altio.testing.fakemeddra), released 1 September 2026.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from open_altio.cli.serve import add_meddra
from open_altio.explorer.context import explorer_of
from open_altio.faers.meddra import build_licensed, older_part, read_licensed_manifest
from open_altio.testing.fakemeddra import write_meddra


def test_the_reaction_search_finds_smqs_and_lower_level_terms(licensed_client, ask):
    got = ask(licensed_client, "/api/terms?q=head&kind=all&meddra=1")
    assert got["llts"][0][:2] == ["Head pain", "Headache"]
    smqs = ask(licensed_client, "/api/terms?q=bleeding&kind=all&meddra=1")["smqs"]
    assert [s[:2] for s in smqs] == [["96000001", "Invented bleeding events (SMQ)"]]
    assert ask(licensed_client, "/api/terms?q=&kind=smq&meddra=1")["totals"]["smq"] == 3


def test_an_smqs_terms_come_narrow_first_with_sub_smqs_folded_in(licensed_client, ask):
    got = ask(licensed_client, "/api/smq?code=96000001")
    # Headache is in the SMQ but inactive
    assert [t[:2] for t in got["terms"]] == [["Haemorrhage", "narrow"], ["Nausea", "broad"]]
    assert [t[:2] for t in ask(licensed_client, "/api/smq?code=96000002")["terms"]] == [
        ["Vomiting", "narrow"]
    ]
    assert ask(licensed_client, "/api/smq?code=99999999", status=404)["problem"]


def cases_with(rel, *pts: str) -> int:
    """The kept cases with any of these reactions, from the release's own tables."""
    marks = ", ".join("?" for _ in pts)
    named = f"lower(r.pt) IN ({marks})"
    reacs = f"EXISTS (SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')} AND {named})"
    return len(rel.case_keys(reacs, *[p.lower() for p in pts]))


def test_an_smq_filters_the_cases_by_its_scope(licensed_client, rel, ask):
    narrow = ask(licensed_client, "/api/summary", smq="96000001:narrow")["cases"]
    assert narrow == cases_with(rel, "Haemorrhage")
    broad = ask(licensed_client, "/api/summary", smq="96000001:broad")["cases"]
    assert broad == cases_with(rel, "Haemorrhage", "Nausea")
    assert ask(licensed_client, "/api/summary?smq=99999999:narrow", status=400)["problem"]


def test_a_term_left_out_of_a_chosen_smq_or_query_takes_only_its_cases_out(
    licensed_client, rel, ask
):
    def counted(**params) -> int:
        return ask(licensed_client, "/api/summary", **params)["cases"]

    headache = cases_with(rel, "Headache")
    assert headache < cases_with(rel, "Headache", "Haemorrhage")
    # an SMQ's term left out, beside a term chosen on its own
    asked = {"smq": "96000001:narrow", "pt": "Headache"}
    assert counted(**asked) == cases_with(rel, "Headache", "Haemorrhage")
    assert counted(**asked, pt_out="Haemorrhage") == headache
    # a query's terms come as pt; a term left out may be spelled any way
    assert counted(pt=["Headache", "Haemorrhage"], pt_out="HAEMORRHAGE") == headache
    # the counts of an SMQ's terms are under the other filters, whatever is left out
    terms = ask(licensed_client, "/api/smq", code="96000001", pt_out="Nausea")["terms"]
    assert terms == ask(licensed_client, "/api/smq", code="96000001")["terms"]


def test_every_chosen_term_left_out_is_refused(licensed_client, ask):
    for wrong in ({"smq": "96000001:narrow", "pt_out": "Haemorrhage"}, {"pt_out": "Nausea"}):
        problem = ask(licensed_client, "/api/summary", 400, **wrong)["problem"]
        assert "left out" in problem, wrong


def test_the_version_served_is_the_one_the_release_was_built_with(licensed_client, clock, ask):
    def named() -> str:  # an unknown SMQ is refused in the words of the version served
        return ask(licensed_client, "/api/summary?smq=99999999:narrow", status=400)["problem"]

    assert "MedDRA 29.1" in named()
    clock.advance(days=400)  # no change-over date: the day never moves it
    assert "MedDRA 29.1" in named()


def test_meddra_added_to_the_live_release_names_its_statistics_by_pt(
    explorer_app, own_release, tmp_path, ask
):
    web = TestClient(explorer_app(own_release))
    assert ask(web, "/api/statistics/about")["reaction_key"] == "fda_text"
    # the explorer lets go of the database first: Windows replaces no file a program holds open
    explorer_of(web.app).release.current().close()
    build_licensed(own_release, write_meddra(tmp_path / "meddra", "29.1"))
    about = ask(web, "/api/statistics/about")
    assert (about["reaction_key"], about["meddra_version"]) == ("meddra_pt", "29.1")
    [row] = ask(web, "/api/statistics?ingredient=metformin&find=acidosis")["rows"]
    assert row["reaction"] == "Acidosis lactic"
    assert ask(web, "/api/summary", product="metformin", pt=row["term"])["cases"] == row["cases"]


def test_a_meddra_part_an_older_version_added_is_left_out_saying_how_to_add_it(
    explorer_app, older_release, licensed_client, ask
):
    web = TestClient(explorer_app(older_release))
    got = ask(web, "/api/release")
    assert got["reactions"] == {"counted_by": "fda_text", "meddra_version": None}
    assert "MedDRA 29.1 was added to this release by an older version" in got["meddra_older"]
    assert "open-altio serve --meddra <folder>" in got["meddra_older"]
    assert ask(web, "/api/me")["tiers"]["meddra"] is False
    assert ask(web, "/api/summary")["cases"] == ask(licensed_client, "/api/summary")["cases"]
    assert "MedDRA" in ask(web, "/api/summary?smq=99999999:narrow", status=403)["problem"]
    assert ask(licensed_client, "/api/release")["meddra_older"] is None


def test_adding_the_same_version_again_writes_an_older_part_anew(older_release, tmp_path):
    add_meddra(older_release, write_meddra(tmp_path / "meddra", "29.1"))
    assert not older_part(read_licensed_manifest(older_release)["meddra"]["versions"]["29.1"])
