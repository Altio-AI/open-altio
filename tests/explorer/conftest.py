"""The explorer run on its own, as one person runs it on their own machine:
no sign-in, LocalAccess, over the fake release (open_altio.testing.fixtures).

    clock           a clock the test controls, frozen at START
    explorer_app    explorer_app(release_dir, access=None): the app over that folder, on `clock`
    client          a TestClient of the explorer over `release`
    licensed_client the same over `licensed_release`, whose licensed part holds MedDRA 29.1
    label_client    the same over `labelled_release`, which also holds invented label flags
    dup_client      the same over `dup_rel`, the release of the duplicate rules' own cases
    hooked          hooked(viewer=, about=, modules=, terms=, edits_rules=, release_dir=): a
                    TestClient of the explorer with a Hook so shaped (LocalAccess otherwise), the
                    hook as `.hook`
    people          people(release_dir=release): a hooked TestClient whose viewer is named by the
                    X-Viewer header (see by_header), so one app serves several people
    ask             ask(client, path, status=200, headers=None, **params): the JSON an address
                    answers with `params` as its query string, after checking its status
    parquet_rows    parquet_rows(data): the rows of a Parquet file's bytes, as dicts
    own_release     a copy of `release` in a folder of its own, beside which a test may write
    own_client      a TestClient over `own_release`, told where the fake FDA files are, so it
                    rebuilds
    older_release   a copy of `licensed_release` whose MedDRA part an older Open Altio added
    site            the explorer over `licensed_release`, served on this machine for the browser
    label_site      the explorer over `labelled_release`, served the same way
    early_site      the explorer over a release built only up to 2019Q1, served the same way
    dup_site        the explorer over `dup_rel`, served the same way
    stats_client    a TestClient of the explorer over `stats_release`, whose EBGM prior fits
    stats_site      the explorer over `stats_release`, served for the browser
    classes_site    the explorer over `classes_release`, whose drugs carry invented WHO classes
    group_release   a copy of `release` with those classes and a class above one class only that
                    holds records of its own (fakeclasses.GROUP_CLASS)
    group_site      the explorer over `group_release`, served for the browser
    bare_site       the explorer over `bare_release`, built without the classes
    opened          opened(path, width=1440, ...): the page at that address of `site` in `chromium`,
                    drawn and settled (open_altio.testing.browser.open_page), closed after the test
    outbox          a copy's outbox in a fresh data folder, sending to a service that is not there
    copy_client     a TestClient of the explorer over `release` with that outbox, as
                    `open-altio serve` runs it

Every test runs on a machine with room for a rebuild (`room_to_rebuild`): a rebuild starts only
where the disk has the room rule machine-needs asks for, which the test machine's own disk may
not have. test_rebuild.py's tests of that check give the machine the room they test.

What each answer should hold is read from the release's own files through `rel`.
"""

from __future__ import annotations

import io
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pyarrow.parquet as pq
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from open_altio.explorer import rebuild
from open_altio.explorer.access import LOCAL, LocalAccess, Viewer
from open_altio.explorer.app import create_app
from open_altio.explorer.outbox import Outbox
from open_altio.faers.build import Inputs
from open_altio.testing import fakeclasses
from open_altio.testing.browser import open_page, served
from open_altio.testing.fakemeddra import as_an_older_version_wrote_it

START = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self, at: datetime = START) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at

    def set(self, at: datetime) -> None:
        self.at = at

    def advance(self, **step: float) -> datetime:
        self.at += timedelta(**step)
        return self.at


class Hook(LocalAccess):
    """LocalAccess, except for what a test sets: the viewer (or a function of the
    request that names one), what /api/me adds, the page modules, the export's
    terms, whether the rules can be edited; and every event it hears is kept in
    `events`."""

    def __init__(
        self,
        viewer: Viewer | Callable[[Request], Viewer] = LOCAL,
        *,
        about: dict | None = None,
        modules: tuple[str, ...] = (),
        terms: dict | None = None,
        edits_rules: bool = True,
    ) -> None:
        self._viewer = viewer
        self._about = about or {}
        self.modules = modules
        self.terms = terms or {}
        self.edits_rules = edits_rules
        self.events: list[dict[str, Any]] = []

    def viewer(self, request: Request) -> Viewer:
        return self._viewer(request) if callable(self._viewer) else self._viewer

    def about(self, request: Request, viewer: Viewer) -> dict[str, Any]:
        return dict(self._about)

    def record(self, viewer: Viewer, kind: str, **event: Any) -> None:
        self.events.append({"kind": kind, "viewer": viewer.id, **event})


def by_header(request: Request) -> Viewer:
    """A viewer named by the request's X-Viewer header, so one app holds several people.
    `X-Viewer: ann` sees no licensed part; `X-Viewer: ann+meddra` does."""
    name, _, part = request.headers.get("X-Viewer", "local").partition("+")
    return Viewer(id=name, meddra=part == "meddra", who=False)


@pytest.fixture(autouse=True)
def room_to_rebuild(monkeypatch):
    monkeypatch.setattr(rebuild, "free_disk", lambda folder: 10**15)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def explorer_app(clock):
    def make(
        release_dir: str | Path | None,
        access=None,
        fda_dir: str | Path | None = None,
        inputs: Inputs | None = None,
    ):
        return create_app(release_dir, access=access, clock=clock, fda_dir=fda_dir, inputs=inputs)

    return make


@pytest.fixture
def client(explorer_app, release) -> TestClient:
    return TestClient(explorer_app(release))


@pytest.fixture
def outbox(tmp_path) -> Outbox:
    return Outbox(tmp_path / "data", "http://127.0.0.1:9/api/notes/local")


@pytest.fixture
def copy_client(release, clock, outbox) -> TestClient:
    return TestClient(create_app(release, clock=clock, outbox=outbox))


@pytest.fixture
def licensed_client(explorer_app, licensed_release) -> TestClient:
    return TestClient(explorer_app(licensed_release))


@pytest.fixture
def label_client(explorer_app, labelled_release) -> TestClient:
    return TestClient(explorer_app(labelled_release))


@pytest.fixture
def dup_client(explorer_app, dup_rel) -> TestClient:
    return TestClient(explorer_app(dup_rel.path))


@pytest.fixture
def hooked(explorer_app, release):
    def make(*, release_dir: str | Path | None = None, **shape: Any) -> TestClient:
        hook = Hook(**shape)
        web = TestClient(explorer_app(release_dir or release, access=hook))
        web.hook = hook  # type: ignore[attr-defined]
        return web

    return make


@pytest.fixture
def people(hooked):
    return lambda release_dir=None: hooked(viewer=by_header, release_dir=release_dir)


@pytest.fixture
def ask():
    def answer(
        client: TestClient,
        path: str,
        status: int = 200,
        headers: dict[str, str] | None = None,
        **params: Any,
    ) -> Any:
        query = urlencode(params, doseq=True)
        got = client.get(f"{path}?{query}" if query else path, headers=headers)
        assert got.status_code == status, got.text
        return got.json()

    return answer


@pytest.fixture
def parquet_rows():
    return lambda data: pq.read_table(io.BytesIO(data)).to_pylist()


@pytest.fixture(scope="session")
def site(licensed_release):
    with served(create_app(licensed_release, clock=Clock())) as base:
        yield base


@pytest.fixture(scope="session")
def label_site(labelled_release):
    with served(create_app(labelled_release, clock=Clock())) as base:
        yield base


@pytest.fixture(scope="session")
def early_site(fake_input, tmp_path_factory):
    from open_altio.faers import build_release

    release = build_release(fake_input, tmp_path_factory.mktemp("early"), quarter="2019q1")
    with served(create_app(release, clock=Clock())) as base:
        yield base


@pytest.fixture(scope="session")
def dup_site(dup_rel):
    with served(create_app(dup_rel.path, clock=Clock())) as base:
        yield base


@pytest.fixture(scope="session")
def demo_site(demo_rel):
    with served(create_app(demo_rel.path, clock=Clock())) as base:
        yield base


@pytest.fixture
def stats_client(explorer_app, stats_release) -> TestClient:
    return TestClient(explorer_app(stats_release))


@pytest.fixture(scope="session")
def stats_site(stats_release):
    with served(create_app(stats_release, clock=Clock())) as base:
        yield base


@pytest.fixture(scope="session")
def classes_site(classes_release):
    with served(create_app(classes_release, clock=Clock())) as base:
        yield base


@pytest.fixture(scope="session")
def group_release(release, tmp_path_factory) -> Path:
    copy = tmp_path_factory.mktemp("group_class") / release.name
    shutil.copytree(release, copy)
    fakeclasses.add_classes(copy, fakeclasses.GROUP_CLASS)
    return copy


@pytest.fixture(scope="session")
def group_site(group_release):
    with served(create_app(group_release, clock=Clock())) as base:
        yield base


@pytest.fixture(scope="session")
def bare_site(bare_release):
    with served(create_app(bare_release, clock=Clock())) as base:
        yield base


@pytest.fixture
def opened(chromium, site):
    pages: list[Any] = []

    def make(path: str, *, base: str = "", **how: Any) -> Any:
        page = open_page(chromium, (base or site) + path, **how)
        pages.append(page)
        return page

    yield make
    for page in pages:
        page.context.close()


@pytest.fixture
def own_release(release, tmp_path) -> Path:
    copy = tmp_path / "releases" / release.name
    shutil.copytree(release, copy)
    return copy


@pytest.fixture
def older_release(licensed_release, tmp_path) -> Path:
    copy = tmp_path / "older" / licensed_release.name
    shutil.copytree(licensed_release, copy)
    return as_an_older_version_wrote_it(copy)


@pytest.fixture
def own_client(explorer_app, own_release, fake_input) -> TestClient:
    return TestClient(explorer_app(own_release, fda_dir=fake_input))
