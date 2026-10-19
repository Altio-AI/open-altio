"""The live release made ready before anyone asks: opened, with what a first page asks of it
already worked out, so the first page after the explorer starts is quick.

    seconds = warm(explorer, viewers)    # None when no release is live yet

What it makes is what Home and All cases ask first: the release's facts (its drugs, most cases
first, which also open Home), each of Home's first products' counts, and the All cases overview
and its timeline, for each kind of viewer in `viewers` (what they may see changes the answers).
Each answer is kept as the page's own question keeps it (api.remembered), so the page finds it
made; a page that asks while it is still being made waits for it rather than making it again.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from functools import partial
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode

from . import explore
from .access import Viewer
from .api import remembered
from .release import NotLive

if TYPE_CHECKING:
    from .context import Explorer

TIMELINE = "grain=year"  # the grain All cases opens on


def warm(explorer: Explorer, viewers: Sequence[Viewer]) -> float | None:
    """Make the live release's first answers for each of `viewers`; the seconds it took, or None
    when no release is live."""
    t0 = time.monotonic()
    try:
        opened = explorer.release.current()
    except NotLive:
        return None
    facts = explorer.facts.of(opened)
    _ = facts.info  # what /api/release answers, made now
    tiles = [d["name"] for d in facts.drugs[: explore.list_length("home_tiles")]]
    asked = [("summary", urlencode({"product": name})) for name in tiles]
    asked += [("summary", ""), ("timeline", TIMELINE)]
    for viewer in viewers:
        data = explorer.data(viewer)
        for name, question in asked:
            how = explore.timeline if name == "timeline" else explore.summary
            remembered(name, data, question, partial(how, data, parse_qs(question)))
    return time.monotonic() - t0


__all__ = ["warm"]
