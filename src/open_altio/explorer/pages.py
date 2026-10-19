"""The page: one HTML file whose script (ui/app.js) draws every screen from
the /api answers, served at each address a screen has, and its files.

Addresses carry no "#": Home is "/", a product's Overview is
/product/ADALIMUMAB/overview. A reload or a link opens the screen its address
names, so every address in PAGES serves the same page; app.js decides what to
draw there. A host adds its own screens' addresses the same way, with `index`.
The page and its files hold no data, so anyone may load them.

A host's page modules (the access hook's `modules`) are written into the page
beside app.js, so the browser fetches them all at once rather than one after
another; app.js starts once every module on the page has run. A copy with an
outbox adds its own, which sends Improve this notes to Altio.

Browsers keep the files but ask each time whether they changed, so a new
version reaches everyone on their next visit.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .context import Explorer, explorer

UI = Path(__file__).resolve().parent / "ui"
REVALIDATE = {"Cache-Control": "no-cache"}

# Home, All cases and a product (each with its tabs), Tables and SQL and the old addresses of
# the last two, and How we clean FAERS (/methods; its old address /rules forwards there).
PAGES = (
    "/",
    "/all",
    "/all/{tab}",
    "/product/{name:path}",  # a product's name may hold a slash, written %2F
    "/release",
    "/sql",
    "/downloads",
    "/methods",
)

router = APIRouter()
_files = StaticFiles(directory=str(UI))


PAGE = (UI / "index.html").read_text(encoding="utf-8")
APP_SCRIPT = '<script type="module" src="/ui/app.js"></script>\n'
OUTBOX_MODULE = "/ui/outbox.js"


def index(ex: Explorer = Depends(explorer)) -> HTMLResponse:
    """The page, with the host's page modules after app.js."""
    modules = (*ex.access.modules, *([OUTBOX_MODULE] if ex.outbox else []))
    added = "".join(f'<script type="module" src="{escape(m)}"></script>\n' for m in modules)
    return HTMLResponse(PAGE.replace(APP_SCRIPT, APP_SCRIPT + added), headers=REVALIDATE)


for _address in PAGES:
    router.add_api_route(_address, index, methods=["GET"], include_in_schema=False)


@router.get("/rules", include_in_schema=False)
def old_rules_address(request: Request) -> RedirectResponse:
    """The page's old address, which the website and older links name, forwards to /methods."""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"/methods{query}", status_code=308)


@router.get("/ui/{path:path}", include_in_schema=False)
async def ui_file(request: Request, path: str) -> Response:
    if path == "index.html":
        raise HTTPException(404)
    response = await _files.get_response(path, request.scope)
    response.headers.update(REVALIDATE)
    return response


__all__ = ["PAGES", "UI", "index", "router"]
