"""The questions a product built on Open Altio may ask, and the routes that answer them: part of
Open Altio's written contract (docs/reference/api.md).

    data = open_release_data(folder, viewer)        # any finished release folder, read only
    data = explorer_of(app).data(viewer)            # or the live release of an app
    ask("GET /api/summary", data, {"product": ["acetylsalicylic acid"]})

`PUBLISHED` maps each published route to the function of (Data, Query) that answers it, or to
None for a route whose answer needs more than a release's data (who is asking, SQL, a file),
which a product asks over HTTP. A route's path parameters join its query under their own names.
`INTERNAL` lists the explorer's own routes, which may change in any release.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from open_altio import rulebook
from open_altio.faers import read_manifest

from . import (
    api,
    breakdowns,
    caselist,
    counted,
    downloads,
    eventfacts,
    eventlist,
    eventstats,
    explore,
    grouped,
    labelquery,
    quarterly,
    search,
    statistics,
)
from .access import Viewer
from .context import read_as
from .explore import Data, Query
from .facts import Facts
from .meddra import LicensedMeddra
from .release import LiveRelease

Question = Callable[[Data, Query], Any]

PUBLISHED: dict[str, Question | None] = {
    "GET /api/me": None,
    "GET /api/release": api.release_info,
    "GET /api/products": search.products,
    "GET /api/product": api.product_named,
    "GET /api/spellings": search.spellings,
    "GET /api/summary": explore.summary,
    "GET /api/timeline": explore.timeline,
    "GET /api/events": eventlist.events,
    "GET /api/events/group": eventlist.group,
    "GET /api/events/prior-quarter": quarterly.prior_quarter,
    "GET /api/cases": caselist.cases,
    "GET /api/count": counted.count,
    "GET /api/case/{era}/{key}": api.case_asked,
    "GET /api/terms": search.term_search,
    "GET /api/smq": search.smq_terms,
    "GET /api/termcounts": search.term_counts,
    "GET /api/drugs": search.drug_search,
    "GET /api/classes": api.class_listing,
    "GET /api/exportsize": explore.export_size,
    "GET /api/statistics/about": statistics.about,
    "GET /api/statistics": statistics.pairs,
    "GET /api/statistics/strata": statistics.strata,
    "GET /api/statistics/group": grouped.statistics,
    "GET /api/statistics/quarters": quarterly.series,
    "GET /api/events/statistics": eventstats.statistics_of,
    "GET /api/events/facts": eventfacts.facts,
    "GET /api/breakdowns": breakdowns.breakdowns,
    "GET /api/labels/product": api.label_product,
    "GET /api/labels/cases": api.label_counts,
    "GET /api/labels/query": labelquery.label_query,
    "GET /api/labels/case/{era}/{key}": api.label_case,
    "GET /api/schema": None,
    "GET /api/manifest": None,
    "POST /api/sql": None,
    "GET /api/downloads": downloads.tables_here,
    "GET /api/export": None,
    "POST /api/sql/download": None,
}

# The rules page and the notes outbox: the explorer's own.
INTERNAL = (
    "GET /api/rules",
    "PUT /api/rules",
    "GET /api/rules/rebuild",
    "POST /api/rules/rebuild",
    "GET /api/notes/outbox",
    "POST /api/notes/outbox",
    "DELETE /api/notes/outbox/{note_id}",
)


def open_release_data(folder: str | Path, viewer: Viewer) -> Data:
    """A finished release folder as `viewer` reads it, read only and apart from the live
    pointer, so a product that keeps an earlier release folder gets that release's own counts
    after a newer one is live. NotARelease for anything else. Keep the Data while you ask: it
    holds the release open and remembers what it has worked out."""
    read_manifest(folder)
    fixed = LiveRelease(folder)
    opened = fixed.current()
    return read_as(viewer, opened, Facts(opened), LicensedMeddra(fixed))


def ask(route: str, data: Data, query: Query) -> Any:
    """What `route` answers to `query`, as the route answers it: counted under the rules the
    release was built with, and naming the release it was counted on."""
    how = PUBLISHED[route]
    if how is None:
        raise ValueError(f"{route} is answered over HTTP only.")
    with rulebook.use_user_rules(data.opened.user_rules):
        return api.named(how(data, query), data)


__all__ = ["INTERNAL", "PUBLISHED", "Question", "ask", "open_release_data"]
