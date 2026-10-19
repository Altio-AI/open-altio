"""The access hook, the one question the explorer asks about people: who is
viewing and what they may see. LocalAccess is one person on their own
machine; a host hands create_app its own hook (conftest `hooked`).
"""

from __future__ import annotations

import io
import json
import re
import zipfile

from fastapi import HTTPException

from open_altio.explorer.access import LOCAL, LocalAccess, Viewer
from open_altio.explorer.context import explorer_of
from open_altio.rulebook import value


def smqs_found(client) -> list:
    return client.get("/api/terms?q=&kind=smq&meddra=1").json()["smqs"]


def manifest_of(export) -> dict:
    assert export.status_code == 200, export.text
    z = zipfile.ZipFile(io.BytesIO(export.content))
    [name] = [
        n for n in z.namelist() if n.endswith(value("filtered-vs-full-export", "filtered_manifest"))
    ]
    return json.loads(z.read(name))


def files_in(folder) -> dict:
    return {p.relative_to(folder).as_posix(): p.stat().st_mtime_ns for p in folder.rglob("*")}


# LocalAccess -------------------------------------------------------------------------------------


def test_locally_the_licensed_meddra_part_is_seen_when_the_release_has_one(licensed_client, ask):
    assert ask(licensed_client, "/api/me")["tiers"]["meddra"] is True
    assert len(smqs_found(licensed_client)) == 3
    assert licensed_client.get("/api/smq?code=96000001").status_code == 200


def test_locally_a_release_without_a_licensed_part_shows_none(client, ask):
    assert ask(client, "/api/me")["tiers"]["meddra"] is False
    assert smqs_found(client) == []
    assert client.get("/api/terms?q=head&kind=all&meddra=1").json()["llts"] == []


def test_locally_an_smq_asked_for_without_meddra_says_how_to_add_it(client):
    """A link with an SMQ in it, opened on a copy whose release holds no MedDRA."""
    assert "open-altio serve --meddra" in LOCAL.why_no_smqs
    for path in ("/api/smq?code=96000001", "/api/summary?smq=96000001:narrow"):
        got = client.get(path)
        assert (got.status_code, got.json()) == (403, {"problem": LOCAL.why_no_smqs}), path


def test_locally_whos_classes_are_wherever_the_release_holds_them(licensed_client, ask):
    assert LOCAL.who is True and LOCAL.who_files is True
    assert ask(licensed_client, "/api/me")["tiers"]["who"] is True


def test_locally_the_page_loads_no_module_of_a_host(client):
    assert re.findall(r'<script type="module" src="([^"]+)"', client.get("/").text) == [
        "/ui/app.js"
    ]


def test_locally_nothing_is_recorded(client, release):
    before = files_in(release)
    access = explorer_of(client.app).access
    assert isinstance(access, LocalAccess)
    assert client.get("/api/export?format=csv&sex=F").status_code == 200
    assert client.post("/api/sql", json={"sql": "SELECT 1"}).status_code == 200
    assert (
        client.post("/api/sql/download", json={"sql": "SELECT 1", "format": "csv"}).status_code
        == 200
    )
    # nothing kept, nothing written beside the release
    assert vars(access) == {} and files_in(release) == before


# a host's hook ------------------------------------------------------------------------------------


def test_a_recording_hook_hears_every_export_and_query_with_its_details(hooked, rel, clock):
    web = hooked(viewer=Viewer(id="ann", meddra=False, who=False))
    assert web.get("/api/export?format=parquet&sex=M").status_code == 200
    assert web.post("/api/sql", json={"sql": "SELECT 42 AS x"}).status_code == 200
    assert (
        web.post("/api/sql/download", json={"sql": "DROP TABLE demo", "format": "csv"}).status_code
        == 400
    )
    export, query, download = web.hook.events
    assert {k: export[k] for k in ("kind", "viewer", "release", "query", "format", "at")} == {
        "kind": "filtered_export",
        "viewer": "ann",
        "release": rel.manifest["release"],
        "query": "sex=M",
        "format": "parquet",
        "at": clock.now(),
    }
    assert (
        any(line.startswith("Sex: M") for line in export["described"])
        and export["rows"]["cases"] > 0
    )
    assert (query["kind"], query["viewer"], query["sql"], query["outcome"], query["rows"]) == (
        "sql",
        "ann",
        "SELECT 42 AS x",
        "ok",
        1,
    )
    assert (download["sql"], download["download"], download["outcome"]) == (
        "DROP TABLE demo",
        "csv",
        "refused",
    )
    assert all(isinstance(e["seconds"], float) for e in (query, download))


def test_a_recording_hook_hears_each_search_with_its_words_and_how_many_it_found(hooked):
    web = hooked(viewer=Viewer(id="ann", meddra=False, who=False))
    name = web.get("/api/products").json()["drugs"][0]["name"]  # a list, not a search
    typed = name[:3].lower()
    shown = {
        "products": web.get(f"/api/products?q={typed}").json(),
        "drugs": web.get(f"/api/drugs?q={typed}").json(),
        "reactions": web.get("/api/terms?q=zzqqzz").json(),
    }
    assert [(e["kind"], e["viewer"], e["search"], e["words"]) for e in web.hook.events] == [
        ("search", "ann", "products", typed),
        ("search", "ann", "drugs", typed),
        ("search", "ann", "reactions", "zzqqzz"),
    ]
    found = [e["results"] for e in web.hook.events]
    assert found[0] == len(shown["products"]["drugs"]) + len(shown["products"]["unmapped"]) > 0
    assert found[1] == len(shown["drugs"]["drugs"]) + len(shown["drugs"]["unmapped"]) > 0
    assert found[2] == 0


def test_a_recording_hook_hears_each_export_started_with_its_rows(hooked):
    web = hooked(viewer=Viewer(id="ann", meddra=False, who=False))
    sizes = web.get("/api/exportsize?sex=F").json()
    assert web.hook.events == [{"kind": "export_started", "viewer": "ann", "rows": sizes}]
    assert sizes["cases"] > 0


def test_a_viewer_shown_no_smqs_is_told_why_in_the_hooks_words(hooked, licensed_release):
    told = Viewer(id="ann", meddra=False, who=False, why_no_smqs="Ask us for MedDRA.")
    silent = Viewer(id="bo", meddra=False, who=False)
    # a host that says nothing is not told to start the explorer with MedDRA files
    assert silent.why_no_smqs != LOCAL.why_no_smqs
    for viewer in (told, silent):
        got = hooked(viewer=viewer, release_dir=licensed_release).get("/api/smq?code=96000001")
        assert (got.status_code, got.json()) == (403, {"problem": viewer.why_no_smqs})


def test_a_viewer_who_may_not_use_sql_or_exports_is_refused_them(hooked, ask):
    web = hooked(viewer=Viewer(id="ann", meddra=False, who=False, sql=False, exports=False))
    mine = ask(web, "/api/me")
    assert (mine["sql"], mine["exports"]) == (False, False)
    refused = [
        web.post("/api/sql", json={"sql": "SELECT 1"}),
        web.post("/api/sql/download", json={"sql": "SELECT 1", "format": "csv"}),
        web.get("/api/export?format=csv"),
    ]
    assert [r.status_code for r in refused] == [403, 403, 403]
    assert all(r.json()["problem"] for r in refused)
    assert web.get("/api/summary").status_code == 200  # the counts stay open to them
    assert web.hook.events == []


def test_a_hook_that_refuses_the_viewer_gets_the_json_problem_and_the_page_still_loads(hooked):
    def nobody(request):
        raise HTTPException(401, "Sign in first.")

    web = hooked(viewer=nobody)
    for path in (
        "/api/me",
        "/api/summary",
        "/api/case/faers/9001001",
        "/api/downloads",
        "/api/export?format=csv",
    ):
        got = web.get(path)
        assert (got.status_code, got.json()) == (401, {"problem": "Sign in first."}), path
    assert web.post("/api/sql", json={"sql": "SELECT 1"}).status_code == 401
    assert web.get("/").status_code == 200  # the page holds no data


def test_the_page_loads_the_modules_the_hook_names_after_its_own(hooked):
    web = hooked(modules=("/host-ui/host.js", "/host-ui/more.js"))
    for address in ("/", "/all/cases"):
        scripts = re.findall(r'<script type="module" src="([^"]+)"', web.get(address).text)
        assert scripts == ["/ui/app.js", "/host-ui/host.js", "/host-ui/more.js"], address


def test_me_adds_what_the_hook_says_about_the_viewer(hooked, ask):
    web = hooked(about={"email": "ann@example.org", "tiers": {"meddra": True, "who": True}})
    got = ask(web, "/api/me")
    assert got["email"] == "ann@example.org" and got["sql"] is True
    assert got["tiers"] == {"meddra": True, "who": True}  # the hook's word wins where both speak


def test_a_filtered_export_carries_the_hooks_terms(hooked):
    web = hooked(terms={"licence_version": "3"})
    assert manifest_of(web.get("/api/export?format=csv&sex=F"))["licence_version"] == "3"
