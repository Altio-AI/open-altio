"""What every explorer route works with: one `Explorer`, built once by `create_app`, and the
person asking, each handed to a route as a FastAPI dependency."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from fastapi import Depends, FastAPI, Request

from open_altio import rulebook

from . import classes, search
from .access import Access, Viewer
from .explore import Data
from .facts import LiveFacts
from .meddra import LicensedMeddra
from .reactions import Reactions
from .rebuild import Rebuild
from .release import LiveRelease
from .sql import SqlService

if TYPE_CHECKING:
    from .outbox import Outbox


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """The current time, timezone-aware, in UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class Asking:
    """The questions the explorer is answering now, so the warming can wait for a quiet
    moment."""

    def __init__(self) -> None:
        self._changed = threading.Condition()
        self._now = 0
        self._asked = 0  # every question so far

    @contextmanager
    def one(self) -> Iterator[None]:
        with self._changed:
            self._now += 1
            self._asked += 1
        try:
            yield
        finally:
            with self._changed:
                self._now -= 1
                self._changed.notify_all()

    def quiet(self, seconds: float) -> None:
        """Returns once no question has been asked or answered for `seconds`."""
        while True:
            with self._changed:
                while self._now:
                    self._changed.wait()
                asked = self._asked
            time.sleep(seconds)
            with self._changed:
                if not self._now and self._asked == asked:
                    return


@dataclass(frozen=True)
class Explorer:
    release: LiveRelease
    sql: SqlService
    facts: LiveFacts
    meddra: LicensedMeddra
    access: Access
    clock: Clock
    rebuild: Rebuild
    outbox: Outbox | None = None  # Improve this, on a copy run on someone's own machine
    asking: Asking = field(default_factory=Asking)

    def data(self, viewer: Viewer) -> Data:
        """What one request reads: the live release, its facts, its MedDRA version when this
        viewer may see it, its reactions, named by that version for each viewer the access hook
        gives it to and as FDA wrote them for any other, and the release's drug classes when it
        carries them and this viewer may see them."""
        opened = self.release.current()
        facts = self.facts.of(opened)
        served = self.meddra.served()
        shown = served if viewer.meddra else None
        named = served if viewer.named_by_meddra else None
        line = viewer.fda_text_line if served is not None and named is None else ""
        layer = classes.layer_of(opened.manifest)
        why = classes.NOT_HELD if layer is None else classes.NOT_OPEN
        return Data(
            opened,
            facts,
            shown,
            viewer.why_no_smqs,
            Reactions(facts, named, line),
            layer if viewer.who else None,
            why,
        )

    def warm(self) -> None:
        """What the search boxes read under no filter, worked out in the background when a
        release opens (search.warm), each part in a quiet moment (rule explorer-read-memory);
        should it fail, the first search works it out instead."""
        try:
            seconds = float(rulebook.value("explorer-read-memory", "warm_after_quiet_seconds"))
            with rulebook.use_user_rules(self.release.user_rules()):
                search.warm(self.data(WARMING), lambda: self.asking.quiet(seconds))
        except Exception:  # the release went, or is not live yet: nothing is lost
            logging.getLogger(__name__).warning("The explorer was not warmed.", exc_info=True)


# who warms the explorer: everything a page may read, so every fact a search reads is made
WARMING = Viewer(id="warm-up", meddra=True, who=True)


def explorer_of(app: FastAPI) -> Explorer:
    return app.state.explorer


def explorer(request: Request) -> Explorer:
    return explorer_of(request.app)


def viewer(request: Request, ex: Explorer = Depends(explorer)) -> Viewer:
    return ex.access.viewer(request)


__all__ = ["Clock", "Explorer", "SystemClock", "explorer", "explorer_of", "viewer"]
