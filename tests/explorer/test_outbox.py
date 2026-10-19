"""Improve this on a copy run on someone's own machine (outbox.py, rule improve-this).

A note is kept in the copy's outbox, in Open Altio's data folder, holding exactly what the page
then sends to Altio; the page crosses it off once Altio has it. The page's own sending, offline
and online, is checked in a browser against a fake service (test_outbox_browser.py).
"""

from __future__ import annotations

import json
import re

from open_altio.explorer.outbox import SEND_TO, Outbox, send_to
from open_altio.paths import DATA_ENV
from open_altio.rulebook import value

NOTE = {
    "page": "How we clean FAERS",
    "route": "/methods",
    "part": "Same manufacturer case number",
    "where": "main > section:nth-of-type(2) > ul > li",
    "text": "It would help to see how many groups the age guard skipped.",
}
WHAT_GOES = {"id", "text", "page", "route", "part", "where", "email"}
MODULE = '<script type="module" src="/ui/outbox.js">'


def keep(client, **overrides):
    return client.post("/api/notes/outbox", json={**NOTE, **overrides})


def waiting(client) -> list[dict]:
    got = client.get("/api/notes/outbox")
    assert got.status_code == 200, got.text
    return got.json()["notes"]


# a note holds exactly what goes -----------------------------------------------------------------


def test_a_note_is_kept_holding_exactly_what_goes_and_where_it_goes(copy_client, outbox):
    got = keep(
        copy_client,
        email=" jane@example.org ",
        release="2026Q2",
        filters="sex=F",
        who="local",
        sql="SELECT 1",
    )
    assert got.status_code == 201
    answer = got.json()
    assert answer["send_to"] == outbox.url
    note = answer["note"]
    assert set(note) == WHAT_GOES
    assert {k: note[k] for k in NOTE} == NOTE and note["email"] == "jane@example.org"
    assert re.fullmatch(r"[0-9a-f]{32}", note["id"])
    assert waiting(copy_client) == [note]
    [kept] = (outbox.folder / "outbox").glob("*.json")
    assert json.loads(kept.read_text(encoding="utf-8")) == note


def test_the_email_is_optional(copy_client):
    assert keep(copy_client).json()["note"]["email"] == ""


def test_a_note_needs_its_words_and_a_real_email_if_any(copy_client):
    for wrong, said in (
        ({"text": "  "}, "Write what was confusing, slow or missing."),
        ({"email": "jane at example"}, "Check your email address, or leave it empty."),
    ):
        got = keep(copy_client, **wrong)
        assert (got.status_code, got.json()) == (400, {"problem": said}), wrong
    assert copy_client.post("/api/notes/outbox", data=NOTE).status_code == 415
    assert waiting(copy_client) == []


# a note's id, and nothing else that would tell notes apart -------------------------------------


def test_each_note_has_its_own_random_id_and_nothing_names_the_copy(copy_client, outbox):
    first, second = keep(copy_client).json()["note"], keep(copy_client).json()["note"]
    assert first.pop("id") != second.pop("id")
    assert first == second  # nothing but the id differs, so nothing ties notes to one copy
    assert sorted(p.name for p in outbox.folder.iterdir()) == ["outbox"]


def test_nothing_is_written_until_a_note_is(copy_client, outbox):
    assert copy_client.get("/").status_code == 200
    assert waiting(copy_client) == []
    assert not outbox.folder.exists()


# waiting and crossed off --------------------------------------------------------------------------


def test_notes_wait_oldest_first_until_each_is_crossed_off(copy_client):
    ids = [keep(copy_client, text=f"Note {n}").json()["note"]["id"] for n in range(3)]
    assert [n["id"] for n in waiting(copy_client)] == ids
    got = copy_client.delete(f"/api/notes/outbox/{ids[1]}")
    assert (got.status_code, got.json()) == (200, {"waiting": 2})
    assert [n["text"] for n in waiting(copy_client)] == ["Note 0", "Note 2"]
    # sent and crossed off already
    assert copy_client.delete(f"/api/notes/outbox/{ids[1]}").status_code == 404


def test_a_note_crossed_off_while_the_list_is_read_is_left_out(copy_client, outbox, monkeypatch):
    """The page may cross a note off while it, or another tab, asks what is waiting."""
    kept = keep(copy_client).json()["note"]
    listed = outbox._files()
    monkeypatch.setattr(outbox, "_files", lambda: [*listed, listed[0].with_name("0-gone.json")])
    assert outbox.waiting() == [kept]
    assert outbox.cross_off(kept["id"]) and outbox.waiting() == []


def test_only_a_notes_own_id_crosses_it_off(copy_client, outbox):
    keep(copy_client)
    for wrong in ("..%2Foutbox", "0" * 32, "*"):
        assert copy_client.delete(f"/api/notes/outbox/{wrong}").status_code == 404, wrong
    assert len(waiting(copy_client)) == 1 and (outbox.folder / "outbox").is_dir()


# a copy with an outbox, and a host without one ----------------------------------------------------


def test_a_copy_with_an_outbox_adds_its_module_to_the_page(copy_client):
    page = copy_client.get("/").text
    assert page.index('<script type="module" src="/ui/app.js">') < page.index(MODULE)
    assert copy_client.get("/ui/outbox.js").status_code == 200


def test_an_explorer_without_an_outbox_takes_no_notes(client, hooked):
    """A host that keeps notes itself, such as Altio's service, adds no outbox."""
    for web in (client, hooked(modules=("/host/page.js",))):
        assert MODULE not in web.get("/").text
        assert web.get("/api/notes/outbox").status_code == 404
        assert web.post("/api/notes/outbox", json=NOTE).status_code == 404


# where notes go, and where they wait ----------------------------------------------------------


def test_notes_go_to_altios_service_unless_a_setting_names_another(monkeypatch):
    monkeypatch.delenv(SEND_TO, raising=False)
    assert send_to() == f"{value('improve-this', 'send_to')}/api/notes/local"
    monkeypatch.setenv(SEND_TO, "http://127.0.0.1:8771/")
    assert send_to() == "http://127.0.0.1:8771/api/notes/local"
    monkeypatch.setenv(DATA_ENV, "/somewhere")
    box = Outbox.on_this_machine()
    assert box.url == "http://127.0.0.1:8771/api/notes/local"
    assert box.folder.as_posix() == "/somewhere"
