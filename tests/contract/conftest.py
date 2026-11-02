"""The contract's checks, over the invented release (open_altio.testing.fixtures), with the
explorer's clock held still, so a file answer names the same moment each time it is asked.

    contract_app    contract_app(release_dir): the explorer over that folder, its clock still
    web             a TestClient of the explorer over `labelled_release`, the release
                    scripts/contract_snapshot.py takes the snapshot on
    site            the explorer over `licensed_release`, served on this machine for the browser
    hosted          hosted(js): the same with a host's page module holding `js`, served by a host
                    app in front of the explorer (`host`); yields its address
    opened          opened(address, width=1440, ...): the page there in `chromium`, drawn and
                    settled (open_altio.testing.browser.open_page), closed after the test
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from open_altio.explorer.access import LocalAccess
from open_altio.explorer.app import create_app, host
from open_altio.testing.browser import open_page, served

MODULE = "/acme-ui/page.js"


class StillClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


@pytest.fixture
def contract_app():
    def make(release_dir: str | Path | None) -> FastAPI:
        return create_app(release_dir, clock=StillClock())

    return make


@pytest.fixture
def web(contract_app, labelled_release) -> TestClient:
    return TestClient(contract_app(labelled_release))


@pytest.fixture(scope="session")
def site(licensed_release) -> Iterator[str]:
    with served(create_app(licensed_release, clock=StillClock())) as base:
        yield base


class WithModule(LocalAccess):
    modules = (MODULE,)


@pytest.fixture
def hosted(licensed_release) -> Iterator[Callable[[str], str]]:
    with ExitStack() as stack:

        def serve(js: str) -> str:
            app = FastAPI()
            app.add_api_route(MODULE, lambda: Response(js, media_type="text/javascript"))
            explorer = create_app(licensed_release, access=WithModule(), clock=StillClock())
            return stack.enter_context(served(host(app, explorer)))

        yield serve


@pytest.fixture
def opened(chromium) -> Iterator[Callable[..., Any]]:
    pages: list[Any] = []

    def make(address: str, **how: Any) -> Any:
        page = open_page(chromium, address, **how)
        pages.append(page)
        return page

    yield make
    for page in pages:
        page.context.close()
