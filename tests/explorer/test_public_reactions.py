"""Reactions as FDA wrote them, for a viewer the access hook does not give today's MedDRA names
(Viewer.todays_names False and no `meddra`): the release is shown to them as one built without
MedDRA, everywhere, while a subscriber, and every viewer a host gives today's names, sees it as
before (src/open_altio/explorer/reactions.py, rule meddra-terms).

The release (seizure_release) is built from fakefda.SEIZURE_STORY with the invented MedDRA
29.1, where FDA's Convulsion is a lower level term of the PT Seizure: three cases FDA wrote as
Convulsion (one in capitals), two as Seizure, all on aspirin (acetylsalicylic acid).
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from open_altio.explorer.access import LOCAL, Viewer
from open_altio.faers.statistics import by_current_pt
from open_altio.rulebook import value

ASA = "acetylsalicylic acid"  # the ingredient the invented dictionary reads ASPIRIN to
LINE = "Reactions as FDA wrote them here."
FDA_TEXT = Viewer(id="ann", meddra=False, who=False, todays_names=False, fda_text_line=LINE)
SUBSCRIBER = Viewer(id="sue", meddra=True, who=False)
TODAYS = Viewer(id="tom", meddra=False, who=False)  # a host that gives everyone today's names


@pytest.fixture
def web(hooked, seizure_release):
    return lambda viewer: hooked(viewer=viewer, release_dir=seizure_release)


def reported(ask, client) -> dict[str, int]:
    return dict(map(tuple, ask(client, "/api/summary")["reactions"]))


def test_fda_text_viewer_sees_convulsion_and_seizure_as_two_where_a_subscriber_sees_one(web, ask):
    ann, sue = web(FDA_TEXT), web(SUBSCRIBER)
    assert {k: n for k, n in reported(ask, ann).items() if k != "Headache"} == {
        "Convulsion": 3,
        "Seizure": 2,
    }
    assert {k: n for k, n in reported(ask, sue).items() if k != "Headache"} == {"Seizure": 5}
    # the filter and the search count FDA's text alone for them, today's PT for a subscriber
    assert ask(ann, "/api/summary", pt="Seizure")["cases"] == 2
    assert ask(ann, "/api/summary", pt="convulsion")["cases"] == 3
    assert ask(sue, "/api/summary", pt="Seizure")["cases"] == 5
    assert ask(ann, "/api/terms", q="seiz")["terms"] == [["Seizure", 2]]
    assert ask(ann, "/api/terms", q="convul")["terms"] == [["Convulsion", 3]]
    assert ask(sue, "/api/terms", q="seiz")["terms"] == [["Seizure", 5]]
    assert ask(sue, "/api/terms", q="convul")["terms"] == []
    assert ask(ann, "/api/termcounts", pt=["seizure", "convulsion"])["terms"] == [
        ["Convulsion", 3],
        ["Seizure", 2],
    ]


def test_the_page_says_so_only_to_the_viewer_shown_fdas_text(web, ask):
    assert ask(web(FDA_TEXT), "/api/release")["reactions"] == {
        "counted_by": "fda_text",
        "meddra_version": None,
        "line": LINE,
    }
    for viewer in (SUBSCRIBER, TODAYS):
        assert ask(web(viewer), "/api/release")["reactions"] == {
            "counted_by": "current_pt",
            "meddra_version": "29.1",
        }
    assert "line" not in ask(web(SUBSCRIBER), "/api/statistics/about")
    assert ask(web(FDA_TEXT), "/api/statistics/about")["line"] == LINE


def test_their_case_list_and_case_carry_no_current_pt(web, ask):
    ann = web(FDA_TEXT)
    listed = ask(ann, "/api/cases", pt="convulsion")
    assert len(listed["cases"]) == 3 and "meddra_version" not in listed
    assert all("current_pts_T" not in c for c in listed["cases"])
    one = ask(ann, "/api/case/faers/7803001")
    assert [r["pt"] for r in one["reac"]] == ["Convulsion"]
    assert "meddra_version" not in one and "current_pt_T" not in one["reac"][0]


def test_their_statistics_rows_are_keyed_by_fdas_text(web, ask):
    ann, sue = web(FDA_TEXT), web(SUBSCRIBER)
    about = ask(ann, "/api/statistics/about")
    assert about["reaction_key"] == "fda_text" and about["meddra_version"] is None
    theirs = ask(ann, "/api/statistics?ingredient=acetylsalicylic%20acid")["rows"]
    assert {r["reaction"]: r["cases"] for r in theirs if r["reaction"] != "Headache"} == {
        "Convulsion": 3,
        "Seizure": 2,
    }
    assert {r["term"] for r in theirs} >= {"convulsion", "seizure"}
    strata = ask(ann, "/api/statistics/strata", ingredient=ASA, reaction="convulsion")
    assert strata["reaction"] == "Convulsion" and strata["cases"] == 3
    by_sex = next(p for p in strata["parts"] if p["by"] == "sex")
    assert sum(s["cases"] for s in by_sex["strata"]) == 3
    mine = ask(sue, "/api/statistics?ingredient=acetylsalicylic%20acid")["rows"]
    assert {r["reaction"]: r["cases"] for r in mine if r["reaction"] != "Headache"} == {
        "Seizure": 5
    }
    assert ask(sue, "/api/statistics/about")["reaction_key"] == "meddra_pt"


def test_their_sql_and_tables_give_the_statistics_by_fdas_text_alone(web, ask):
    ann, sue = web(FDA_TEXT), web(SUBSCRIBER)
    by_text = "SELECT reaction_T, cases_T FROM statistics_as_published_T WHERE ingredient_T = "
    got = ann.post("/api/sql", json={"sql": by_text + "'acetylsalicylic acid' ORDER BY 1"})
    assert got.status_code == 200, got.text
    assert ["convulsion", 3] in got.json()["rows"]
    for table in ("statistics_T", "statistics_strata_T"):
        assert ann.post("/api/sql", json={"sql": f"SELECT * FROM {table}"}).status_code == 400
        assert sue.post("/api/sql", json={"sql": f"SELECT * FROM {table}"}).status_code == 200
    theirs = {t["name"] for t in ask(ann, "/api/manifest")["tables"]}
    assert "statistics_as_published_T" in theirs and "statistics_T" not in theirs
    assert "statistics_T" not in {t["name"] for t in ask(ann, "/api/schema")}
    assert "statistics_T" in {t["name"] for t in ask(sue, "/api/manifest")["tables"]}


def test_their_export_holds_fdas_text_and_says_how_it_was_counted(web):
    got = web(FDA_TEXT).get("/api/export", params={"format": "csv", "pt": "convulsion"})
    assert got.status_code == 200, got.text
    files = {n.split("/", 1)[1]: z for n, z in _unzipped(got.content).items()}
    manifest = json.loads(files[value("filtered-vs-full-export", "filtered_manifest")])
    assert manifest["filters"]["reactions_counted"] == {
        "counted_by": "fda_text",
        "meddra_version": None,
        "line": LINE,
    }
    assert "current PT" not in str(manifest["described"])
    reactions = next(v for k, v in files.items() if k.startswith("reactions."))
    assert b"Convulsion" in reactions and b"Seizure" not in reactions


def _unzipped(content: bytes) -> dict[str, bytes]:
    z = zipfile.ZipFile(io.BytesIO(content))
    return {n: z.read(n) for n in z.namelist()}


def test_a_viewer_given_todays_names_without_meddra_counts_by_the_pt_as_before(web, ask):
    tom = web(TODAYS)
    assert {k: n for k, n in reported(ask, tom).items() if k != "Headache"} == {"Seizure": 5}
    about = ask(tom, "/api/statistics/about")
    assert about["reaction_key"] == "meddra_pt" and "line" not in about


def test_the_local_explorer_with_meddra_files_names_them_by_todays_version(web, ask):
    local = web(LOCAL)
    assert {k: n for k, n in reported(ask, local).items() if k != "Headache"} == {"Seizure": 5}
    assert "line" not in ask(local, "/api/release")["reactions"]


def test_the_build_writes_the_second_set_beside_the_first(seizure_release):
    manifest = json.loads((seizure_release / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["statistics"]
    assert entry["reaction_key"] == "meddra_pt"
    second = entry["as_published"]
    assert second["reaction_key"] == "fda_text" and "meddra_version" not in second
    assert second["table"] == "statistics_as_published_T"
    assert second["ror_strata"]["table"] == "statistics_strata_as_published_T"
    assert second["counted"]["reactions"] == entry["counted"]["reactions"] + 1
    for name in ("statistics_as_published_T", "statistics_strata_as_published_T"):
        assert (seizure_release / manifest["tables"][name]["path"]).is_file()
        assert (
            name.replace("statistics", "explorer_statistics", 1) in (manifest["explorer"]["tables"])
        )


def test_a_release_without_meddra_writes_one_set(release):
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["statistics"]["reaction_key"] == "fda_text"
    assert "as_published" not in manifest["statistics"]
    assert "statistics_as_published_T" not in manifest["tables"]


def test_they_are_given_no_class_statistics_counted_by_current_pt(hooked, ask, seizure_release):
    """The class statistics are counted by current PT alone, with no set by FDA's text: a viewer
    shown FDA's text sees none of them, on the tab or in the files a host offers them
    (statistics.by_current_pt), where one given today's names sees them."""
    manifest = json.loads((seizure_release / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["class_statistics"]["reaction_key"] == "meddra_pt"
    ann = hooked(
        viewer=Viewer(id="ann", meddra=False, who=True, todays_names=False, fda_text_line=LINE),
        release_dir=seizure_release,
    )
    tom = hooked(viewer=Viewer(id="tom", meddra=False, who=True), release_dir=seizure_release)
    assert ask(ann, "/api/statistics/about")["classes"] is None
    assert ask(tom, "/api/statistics/about")["classes"]["levels"]
    ask(ann, "/api/statistics", 404, by="class")
    assert "class" not in ask(ann, "/api/statistics", ingredient=ASA)
    assert set(manifest["class_statistics"]["tables"]) <= set(by_current_pt(manifest))
