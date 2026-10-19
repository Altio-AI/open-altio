"""The review page for the one reviewer, served on their own machine (rule label-review)."""

from __future__ import annotations

from dataclasses import asdict
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from open_altio import rulebook

from . import batches, coding, decisions, redo, rulecheck, suggest
from .items import Item, read_items
from .store import Clock, Folder, Refused, utc_now

RULE = "label-review"
GATES = "label-review-gates"
UI = resources.files(__package__).joinpath("ui")
FILES = {
    "review.js": "text/javascript",
    "check.js": "text/javascript",
    "review.css": "text/css",
}
QUEUES = ("phrases", "redo")


class DecideBody(BaseModel):
    item_id: str
    verdict: str
    pts: list[str] = []
    none_reason: str = ""
    note: str = ""


class RedoBody(BaseModel):
    item_id: str
    pts: list[str] = []
    none_reason: str = ""
    note: str = ""


class CheckBody(BaseModel):
    flag: str
    verdict: str
    right_outcome: str | None = None
    note: str = ""


def create_app(
    folder: Folder, reviewer: str, clock: Clock = utc_now, release: Path | None = None
) -> FastAPI:
    """Three queues: uncertain phrases (`/`), blind redo (`/?queue=redo`), rule check (`/check`)."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    hosts = {str(rulebook.value(RULE, "page_host")), "localhost"}

    def same_machine(request: Request) -> None:
        # Another site open in the browser could otherwise post decisions to this page.
        if request.url.hostname not in hosts:
            raise HTTPException(403, "This page answers only on this machine.")
        if request.method == "POST" and request.headers.get("content-type") != "application/json":
            raise HTTPException(415, "Decisions are sent as JSON.")

    guard = [Depends(same_machine)]

    @app.get("/", response_class=HTMLResponse, dependencies=guard)
    def page() -> str:
        return UI.joinpath("review.html").read_text(encoding="utf-8")

    @app.get("/check", response_class=HTMLResponse, dependencies=guard)
    def check_page() -> str:
        return UI.joinpath("check.html").read_text(encoding="utf-8")

    @app.get("/ui/{name}", dependencies=guard)
    def ui_file(name: str) -> Response:
        if name not in FILES:
            raise HTTPException(404)
        return Response(UI.joinpath(name).read_text(encoding="utf-8"), media_type=FILES[name])

    @app.get("/api/state", dependencies=guard)
    def read_state(queue: str = "phrases") -> Any:
        if queue not in QUEUES:
            raise HTTPException(404)
        try:
            return state(folder, reviewer, queue == "redo")
        except Refused as why:
            return _refused(str(why))

    @app.post("/api/decide", dependencies=guard)
    def post_decide(body: DecideBody) -> Any:
        try:
            decisions.decide(
                folder,
                body.item_id,
                body.verdict,
                body.pts,
                body.none_reason,
                body.note,
                reviewer,
                clock,
                release,
            )
        except Refused as why:
            return _refused(str(why))
        return state(folder, reviewer, False)

    @app.post("/api/redo", dependencies=guard)
    def post_redo(body: RedoBody) -> Any:
        try:
            redo.answer(
                folder,
                body.item_id,
                body.pts,
                body.none_reason,
                body.note,
                reviewer,
                clock,
                release,
            )
        except Refused as why:
            return _refused(str(why))
        return state(folder, reviewer, True)

    @app.get("/api/check", dependencies=guard)
    def read_check() -> Any:
        try:
            return check_state(folder, reviewer)
        except Refused as why:
            return _refused(str(why))

    @app.post("/api/check", dependencies=guard)
    def post_check(body: CheckBody) -> Any:
        try:
            rulecheck.check(
                folder,
                body.flag,
                body.verdict,
                body.right_outcome,
                body.note,
                reviewer,
                clock,
            )
        except Refused as why:
            return _refused(str(why))
        return check_state(folder, reviewer)

    return app


def _refused(message: str) -> JSONResponse:
    return JSONResponse({"refused": message}, status_code=409)


def state(folder: Folder, reviewer: str, redo_mode: bool) -> dict[str, Any]:
    items = read_items(folder)
    out: dict[str, Any] = {
        "mode": "redo" if redo_mode else "review",
        "reviewer": reviewer,
        "question": coding.question(),
        "reasons": [asdict(r) for r in coding.reasons().values()],
    }
    if redo_mode:
        # Neither the first answer nor the agent's suggestion is sent: the redo is blind.
        answered = redo.answers(folder)
        ids = redo.item_ids(folder)
        out["items"] = [{**_item(items[i]), "answer": answered.get(i)} for i in ids]
        out["redo"] = {"items": len(ids), "answered": sum(i in answered for i in ids)}
        return out
    batch = batches.current(folder)
    if batch is None:
        out.update(batch=None, items=[], gates=None)
        return out
    said = suggest.latest(folder)
    made = decisions.latest(folder)
    digest = suggest.prompt_digest()
    out["batch"] = {"number": batch.number, "size": len(batch.item_ids)}
    out["items"] = [
        {
            **_item(items[i]),
            "suggestion": _suggestion(said[i], digest) if i in said else None,
            "decision": asdict(made[i]) if i in made else None,
        }
        for i in batch.item_ids
    ]
    result = batches.check(folder, batch)
    out["gates"] = {
        "items": result.items,
        "decided": result.decided,
        "other": result.other,
        "other_share": result.other_share,
        "other_share_below": rulebook.value(GATES, "other_share_below"),
        "agreed": result.agreed,
        "agreement": result.agreement,
        "agreement_at_least": rulebook.value(GATES, "agreement_at_least"),
        "stale": result.stale,
        "no_answer": result.no_answer,
        "reason_only": result.reason_only,
        "passed": result.passed,
        "reasons": result.reasons,
        "next_size": batches.size_for(batch.number + 1),
    }
    return out


def check_state(folder: Folder, reviewer: str) -> dict[str, Any]:
    done = rulecheck.checks(folder)
    names = rulecheck.outcomes()
    flags = [
        {
            **f,
            "flag": rulecheck.flag_key(f),
            "label_date": _date(f.get("label_date", "")),
            "check": done.get(rulecheck.flag_key(f)),
        }
        for f in rulecheck.sample(folder)
    ]
    rates = [
        {
            "outcome": r.outcome,
            "name": names[r.outcome],
            "drawn": r.drawn,
            "checked": r.checked,
            "wrong": r.wrong,
            "rate": r.rate,
            "low": r.low,
            "high": r.high,
        }
        for r in rulecheck.error_rates(folder)
    ]
    return {
        "reviewer": reviewer,
        "outcomes": [{"key": k, "name": v} for k, v in names.items()],
        "confidence": rulebook.value(rulecheck.RULE, "confidence"),
        "flags": flags,
        "rates": rates,
    }


def _date(raw: str) -> str:
    date = raw.replace("-", "")
    return f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 and date.isdigit() else raw


def _item(item: Item) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "drug": item.drug or f"RxNorm {item.rxcui}",
        "set_id": item.set_id,
        "section": item.section,
        "label_date": _date(item.label_date),
        "sentence": item.sentence,
        "rules_guess": item.candidate_pt,
        "why_uncertain": item.why_uncertain,
    }


def _suggestion(row: dict[str, Any], digest: str) -> dict[str, Any]:
    keep = (
        "pts",
        "none_reason",
        "evidence",
        "reason",
        "note",
        "by",
        "status",
        "instructions_version",
    )
    return {**{k: row[k] for k in keep}, "current": suggest.is_current(row, digest)}
