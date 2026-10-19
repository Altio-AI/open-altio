"""The explorer as a web app, over one release folder.

    app = create_app(release_dir)                 # one person on this machine, who sees everything
    app = create_app(release_dir, fda_dir=zips)   # the same, rebuilt from FDA's files in zips
    app = create_app(release_dir, fda_dir=zips, inputs=Inputs(meddra=ascii))  # and its MedDRA
    app = create_app(release_dir, access=hosted)  # a host's sign-in decides who views and what
    app = create_app(release_dir, outbox=Outbox.on_this_machine())  # Improve this, to Altio

`release_dir` is a release folder, or a pointer file a rebuild or a publish repoints
(release.py): the next request opens the release it then names. A host serves its own
routes first and hands this app every request they do not answer.
"""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Route

from open_altio import rulebook
from open_altio.faers.build import Inputs

from . import api, downloads, pages, rules_api
from .access import Access, LocalAccess
from .answers import Problem, problem
from .context import Clock, Explorer, SystemClock
from .facts import LiveFacts
from .meddra import LicensedMeddra
from .outbox import Outbox
from .outbox import router as outbox_routes
from .rebuild import Rebuild
from .release import LiveRelease, NotLive
from .sql import SqlService

# Every answer, the host's too: the pages are never framed by another site, and links leak no
# address.
HEADERS = {"X-Frame-Options": "DENY", "Referrer-Policy": "same-origin"}


def create_app(
    release_dir: str | Path | None,
    *,
    access: Access | None = None,
    clock: Clock | None = None,
    fda_dir: str | Path | None = None,
    inputs: Inputs | None = None,
    outbox: Outbox | None = None,
    warm: bool = False,
) -> FastAPI:
    """`fda_dir` is the folder of FDA's quarterly files the release was built from, which a
    rebuild with the person's rules reads, and `inputs` the other files it was built from,
    which the rebuild reads again (MedDRA's, RxNorm's, FDA's labels). With an `outbox`,
    Improve this keeps each note there until the page has sent it to Altio. With `warm`, each
    release is warmed in the background as it opens (Explorer.warm), from the start on, so a
    person's first search answers at once."""
    app = FastAPI(title="Open Altio", docs_url=None, redoc_url=None, openapi_url=None)
    live = LiveRelease(release_dir)
    explorer = app.state.explorer = Explorer(
        release=live,
        sql=SqlService(live),
        facts=LiveFacts(warm=(lambda: explorer.warm()) if warm else None),
        meddra=LicensedMeddra(live),
        access=access or LocalAccess(),
        clock=clock or SystemClock(),
        rebuild=Rebuild(live, fda_dir, inputs),
        outbox=outbox,
    )
    if warm:  # the release opens now, not at the first page, and its warming begins

        def opening() -> None:
            with suppress(NotLive):
                explorer.facts.of(live.current())

        threading.Thread(target=opening, name="open-altio-open", daemon=True).start()

    @app.middleware("http")
    async def under_its_rules(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # A release built with someone's own rules answers under them: their values are the ones
        # read, such as whether probable duplicates show when a page opens (rule dedup-default).
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        with explorer.asking.one(), rulebook.use_user_rules(live.user_rules()):
            return await call_next(request)

    @app.middleware("http")
    async def headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, header in HEADERS.items():
            response.headers.setdefault(name, header)
        return response

    # Starlette's HTTPException is FastAPI's too, and the one an unknown address raises.
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if not_a_page(request, exc):
            return RedirectResponse("/", status_code=302)  # an address that is no page goes home
        words = exc.detail if isinstance(exc.detail, str) else "Something went wrong."
        if request.url.path.startswith("/api/"):
            return problem(exc.status_code, "not found" if exc.status_code == 404 else words)
        return PlainTextResponse(words, status_code=exc.status_code)

    @app.exception_handler(Problem)
    async def refused(request: Request, exc: Problem) -> Response:
        return problem(exc.status, str(exc))

    @app.exception_handler(NotLive)
    async def not_live(request: Request, exc: NotLive) -> Response:
        return problem(503, str(exc))

    app.include_router(api.router)
    app.include_router(rules_api.router)
    app.include_router(downloads.router)
    app.include_router(outbox_routes)
    app.include_router(pages.router)
    return app


def not_a_page(request: Request, exc: StarletteHTTPException) -> bool:
    """A GET for an address no route answers and not under /api. A route that answers 404
    itself (a missing file) keeps its 404, and a known address asked with the wrong method
    keeps its 405."""
    # A route that matched is in the scope; a host that only passed the request on put none there.
    matched = isinstance(request.scope.get("route"), Route)
    return (
        exc.status_code == 404
        and not matched
        and request.method in ("GET", "HEAD")
        and not request.url.path.startswith("/api/")
    )


__all__ = ["HEADERS", "create_app", "not_a_page"]
