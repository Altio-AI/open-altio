"""Improve this on a copy someone runs on their own machine (rule improve-this): each note waits
in this copy's outbox, in Open Altio's data folder, until the page has sent it to Altio.

The page sends the note itself, from the browser, so it goes out through the same connection and
proxy as every other page the person opens. Kept before it is sent and crossed off once Altio has
it, a note outlives a closed tab, a lost connection or a crash; the page sends what is waiting
whenever it opens and whenever the browser is back online. A note holds exactly what goes: the
person's words, the page, the part they pointed at, the email they gave if any, and a random id of
its own, so that Altio keeps a note sent twice only once.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from open_altio import paths
from open_altio.rulebook import value

from .answers import Problem, answer, json_body, problem
from .context import Explorer, explorer

SEND_TO = "OPEN_ALTIO_IMPROVE_URL"
# Where Altio's service takes notes from copies.
NOTES_FROM_COPIES = "/api/notes/local"
# What a note carries besides its own id.
FIELDS = ("text", "page", "route", "part", "where", "email")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_ID = re.compile(r"[0-9a-f]{32}")


def send_to() -> str:
    """Where notes go: Altio's improvements board, or the service OPEN_ALTIO_IMPROVE_URL names."""
    base = os.environ.get(SEND_TO) or str(value("improve-this", "send_to"))
    return base.rstrip("/") + NOTES_FROM_COPIES


class Outbox:
    """The notes this copy has written and not yet sent, one file each, oldest first."""

    def __init__(self, folder: Path, url: str) -> None:
        self.folder = Path(folder)
        self.url = url

    @classmethod
    def on_this_machine(cls) -> Outbox:
        return cls(paths.data_folder(), send_to())

    @property
    def _waiting(self) -> Path:
        return self.folder / "outbox"

    def write(self, asked: dict) -> dict:
        """Keep a new note and return it as it will be sent. Raises Problem for a note that
        cannot go: one with no words, or an email that is not one."""
        note = {k: str(asked.get(k) or "").strip() for k in FIELDS}
        if not note["text"]:
            raise Problem(400, "Write what was confusing, slow or missing.")
        if note["email"] and not _EMAIL.fullmatch(note["email"]):
            raise Problem(400, "Check your email address, or leave it empty.")
        note = {"id": uuid4().hex, **note}
        self._waiting.mkdir(parents=True, exist_ok=True)
        # named to list oldest first; written whole, then put in place, so none is ever half there
        name = f"{time.time_ns():020d}-{note['id']}.json"
        part = self._waiting / f"{name}.part"
        part.write_text(json.dumps(note), encoding="utf-8")
        os.replace(part, self._waiting / name)
        return note

    def waiting(self) -> list[dict]:
        notes = []
        for path in self._files():
            try:
                notes.append(json.loads(path.read_text(encoding="utf-8")))
            except FileNotFoundError:  # sent and crossed off by another request meanwhile
                continue
        return notes

    def cross_off(self, note_id: str) -> bool:
        """Take a sent note out of the outbox; False when it is not there."""
        for path in self._files():
            if path.stem.endswith(f"-{note_id}"):
                path.unlink(missing_ok=True)  # another request may have just done it
                return True
        return False

    def _files(self) -> list[Path]:
        return sorted(self._waiting.glob("*.json")) if self._waiting.is_dir() else []


# the page's side -------------------------------------------------------------------------------

router = APIRouter(prefix="/api/notes/outbox")


Ex = Depends(explorer)


def outbox(ex: Explorer = Ex) -> Outbox:
    """This copy's outbox. A host that keeps notes itself has none, and these addresses are not
    found there."""
    if ex.outbox is None:
        raise HTTPException(404)
    return ex.outbox


Box = Depends(outbox)


@router.get("")
def waiting(box: Outbox = Box) -> Response:
    return answer({"send_to": box.url, "notes": box.waiting()})


@router.post("")
async def keep(request: Request, box: Outbox = Box) -> Response:
    asked = await json_body(request)
    if isinstance(asked, Response):
        return asked
    return answer({"send_to": box.url, "note": box.write(asked)}, 201)


@router.delete("/{note_id}")
def sent(note_id: str, box: Outbox = Box) -> Response:
    if not _ID.fullmatch(note_id) or not box.cross_off(note_id):
        return problem(404, "not found")
    return answer({"waiting": len(box.waiting())})


__all__ = ["SEND_TO", "Outbox", "router", "send_to"]
