"""The /api routes the page reads its data from. Who may ask is the access
hook's to say (context.viewer); filters are those of explore.py. Each question a route answers
is a function of (Data, Query), which questions.py publishes; a route's path parameters join
its query under their own names."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, Response
from starlette.concurrency import run_in_threadpool

from open_altio.faers import FUNNEL_FILE
from open_altio.rulebook import value

from . import (
    breakdowns,
    caselist,
    classes,
    counted,
    eventfacts,
    eventlist,
    eventstats,
    explore,
    grouped,
    labelquery,
    labels,
    quarterly,
    search,
    statistics,
    tables,
)
from .access import Viewer
from .answers import Problem, answer, counted_on, json_body, problem
from .context import Explorer, explorer, viewer
from .drugs import words as drug_words
from .explore import Data
from .meddra import older_in

router = APIRouter(prefix="/api")


def query_of(request: Request) -> explore.Query:
    return parse_qs(request.url.query)


def remembered(name: str, data: Data, query: str, make: Callable[[], Any]) -> Any:
    """Answers that take a while are kept per release, by the question (`query`, an address's
    query string, read as a page writes it or not): Data.remember."""
    return data.remember(name, parse_qs(query), make)


def named(found: Any, data: Data) -> Any:
    """An answer that is a dict, naming the release it was counted on (`counted_on`)."""
    if not isinstance(found, dict):
        return found
    return found | {"counted_on": counted_on(data.opened.manifest)}


def _result(
    request: Request,
    ex: Explorer,
    v: Viewer,
    how: Callable[[Data, explore.Query], Any],
    name: str = "",
    **path: str,
) -> Any:
    data = ex.data(v)
    query = query_of(request) | {k: [given] for k, given in path.items()}
    if name:
        return named(remembered(name, data, request.url.query, lambda: how(data, query)), data)
    return named(how(data, query), data)


def _ask(
    request: Request,
    ex: Explorer,
    v: Viewer,
    how: Callable[[Data, explore.Query], Any],
    name: str = "",
    **path: str,
) -> Response:
    return answer(_result(request, ex, v, how, name, **path))


# Each search a person types into, and the lists of its answer that hold what it found.
FOUND = {
    "products": ("drugs", "unmapped"),
    "drugs": ("drugs", "unmapped"),
    "spellings": ("spellings", "unmapped"),
    "reactions": ("terms", "llts", "smqs"),
    "classes": ("classes",),
}


def _search(
    request: Request,
    ex: Explorer,
    v: Viewer,
    how: Callable[[Data, explore.Query], Any],
    what: str,
    name: str = "",
) -> Response:
    """A search's answer, told to the access hook with its words and how many results it
    shows; a list asked for with no words is not a search."""
    found = _result(request, ex, v, how, name)
    if found.get("q"):
        results = sum(len(found[k]) for k in FOUND[what])
        ex.announce(v, "search", search=what, words=found["q"], results=results)
    return answer(found)


Ex = Depends(explorer)
Who = Depends(viewer)


# who is asking -----------------------------------------------------------------------------------


@router.get("/me")
def me(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    served = ex.meddra.served() if v.meddra else None
    mine = {
        "tiers": {"meddra": served is not None, "who": v.who},
        "sql": v.sql,
        "exports": v.exports,
        "statistics": v.statistics,
        "sql_seconds": value("sql-limits", "timeout_seconds"),
    }
    return answer(mine | ex.access.about(request, v))


def release_info(data: Data, query: explore.Query) -> dict:
    """What the release holds and how its pages name things."""
    shown = data.classes.words() if data.classes else None
    return data.facts.info | {
        "drugs": drug_words(),
        "reactions": data.reactions.about(),
        "classes": shown,
        "class_statistics": statistics.classes_held(data),
        "labels": labels.screens(data.opened),
        # a MedDRA part an older Open Altio added, not served: how to add it again
        "meddra_older": older_in(data.opened.folder),
    }


@router.get("/release")
def release(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, release_info)


@router.get("/products")
def products(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _search(request, ex, v, search.products, "products")


def product_named(data: Data, query: explore.Query) -> dict:
    """What a product page opens for the name `product`; not found when there is none."""
    found = search.product(data, explore.value_of(query, "product"))
    if not found:
        raise Problem(404, "not found")
    return found


@router.get("/product")
def product(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, product_named)


@router.get("/spellings")
def spellings(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _search(request, ex, v, search.spellings, "spellings")


# counts, charts and cases ------------------------------------------------------------------------


@router.get("/summary")
def summary(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, explore.summary, "summary")


@router.get("/timeline")
def timeline(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, explore.timeline, "timeline")


@router.get("/events")
def events(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, eventlist.events, "events")


@router.get("/events/group")
def event_group(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, eventlist.group, "eventgroup")


@router.get("/cases")
def cases(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, caselist.cases)


@router.get("/count")
def count(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, counted.count, "count")


def case_asked(data: Data, query: explore.Query) -> dict:
    """One case, by its `era` and `key`; not found when there is none."""
    found = caselist.case(data, explore.value_of(query, "era"), explore.value_of(query, "key"))
    if not found:
        raise Problem(404, "not found")
    return found


@router.get("/case/{era}/{key:path}")
def one_case(request: Request, era: str, key: str, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, case_asked, era=era, key=key)


@router.get("/terms")
def terms(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _search(request, ex, v, search.term_search, "reactions")


@router.get("/smq")
def smq(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, search.smq_terms)


@router.get("/termcounts")
def termcounts(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, search.term_counts)


@router.get("/drugs")
def drugs(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _search(request, ex, v, search.drug_search, "drugs")


def class_listing(data: Data, query: explore.Query) -> dict:
    """WHO's drug classes a search finds, each counted under every filter but the classes'."""
    other = replace(explore.scope(data, query), classes=None).where()
    return classes.listing(data, query, other, limit=explore.list_length("classes_found"))


@router.get("/classes")
def drug_classes(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _search(request, ex, v, class_listing, "classes", "classes")


@router.get("/exportsize")
def exportsize(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    """The export dialog's rows per file: an export started, told to the access hook."""
    data = ex.data(v)
    rows = explore.export_size(data, query_of(request))
    ex.announce(v, "export_started", rows=rows)
    return answer(named(rows, data))


# statistics -------------------------------------------------------------------------------------

NOT_OPEN = "Statistics are not open to you here."


@router.get("/statistics/about")
def statistics_about(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    if not v.statistics:
        return problem(403, NOT_OPEN)
    return _ask(request, ex, v, statistics.about)


@router.get("/statistics")
def statistics_pairs(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    if not v.statistics:
        return problem(403, NOT_OPEN)
    return _ask(request, ex, v, statistics.pairs, "statistics")


@router.get("/statistics/strata")
def statistics_strata(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    if not v.statistics:
        return problem(403, NOT_OPEN)
    return _ask(request, ex, v, statistics.strata)


@router.get("/events/statistics")
def event_statistics(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    if not v.statistics:
        return problem(403, NOT_OPEN)
    return _ask(request, ex, v, eventstats.statistics_of)


@router.get("/statistics/group")
def group_statistics(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    if not v.statistics:
        return problem(403, NOT_OPEN)
    return _ask(request, ex, v, grouped.statistics, "groupstatistics")


@router.get("/statistics/quarters")
def quarter_statistics(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    if not v.statistics:
        return problem(403, NOT_OPEN)
    return _ask(request, ex, v, quarterly.series, "quarterstatistics")


@router.get("/events/prior-quarter")
def prior_quarter(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    if not v.statistics:
        return problem(403, NOT_OPEN)
    return _ask(request, ex, v, quarterly.prior_quarter, "priorquarter")


@router.get("/events/facts")
def events_facts(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, eventfacts.facts)


@router.get("/breakdowns")
def event_breakdowns(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, breakdowns.breakdowns)


# the label flags: {} where the release holds none (labels.py) ------------------------------------


def label_product(data: Data, query: explore.Query) -> dict:
    """The labels a product page's drug is read against, and each of its reactions' flag."""
    unit = explore.product_unit(data, query)
    return labels.product_flags(data, unit.substance, unit.exact) if unit and unit.substance else {}


@router.get("/labels/product")
def labels_of_product(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, label_product)


def label_counts(data: Data, query: explore.Query) -> dict:
    """Label status's counts: cases under every filter but Label status itself."""
    sc = explore.scope(data, query)
    if not (sc.product and sc.product.substance):
        return {}
    sql, params = sc.where(labels=None, label_cases=None)
    counts = labels.label_counts(data, sc.product.substance, sql, params, sc.product.exact)
    return {"cases": counts}


@router.get("/labels/cases")
def label_cases(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, label_counts, "labelcounts")


def label_case(data: Data, query: explore.Query) -> dict:
    """One case's label flags, by its `era` and `key`."""
    return labels.case_flags(data, explore.value_of(query, "era"), explore.value_of(query, "key"))


@router.get("/labels/query")
def labels_of_query(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, labelquery.label_query)


@router.get("/labels/case/{era}/{key:path}")
def labels_of_case(
    request: Request, era: str, key: str, ex: Explorer = Ex, v: Viewer = Who
) -> Response:
    return _ask(request, ex, v, label_case, era=era, key=key)


# tables and SQL ----------------------------------------------------------------------------------


@router.get("/schema")
def schema(ex: Explorer = Ex, v: Viewer = Who) -> Response:
    data = ex.data(v)
    return answer(tables.schema(tables.database(ex, v), data.opened.manifest))


@router.get("/manifest")
def manifest(ex: Explorer = Ex, v: Viewer = Who) -> Response:
    opened = ex.data(v).opened
    funnel = json.loads((opened.folder / FUNNEL_FILE).read_text(encoding="utf-8"))
    summary = tables.manifest_summary(
        opened.manifest, funnel, classes=v.who_files, by_pt=v.named_by_meddra
    )
    return answer(summary | {"counted_on": counted_on(opened.manifest)})


@router.post("/sql")
async def sql(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    if not v.sql:
        return problem(403, "SQL is not open to you here.")
    asked = await json_body(request)
    if isinstance(asked, Response):
        return problem(asked.status_code, 'Send the query as JSON: {"sql": ..., "page": 1}.')
    try:
        text = str(asked.get("sql") or "")
        page = int(asked.get("page") or 1)
    except (ValueError, TypeError):
        return problem(400, 'Send the query as JSON: {"sql": ..., "page": 1}.')
    status, result = await run_in_threadpool(tables.run_sql, ex, v, text, page)
    return answer(result, status)


__all__ = [
    "case_asked",
    "class_listing",
    "label_case",
    "label_counts",
    "label_product",
    "named",
    "product_named",
    "query_of",
    "release_info",
    "remembered",
    "router",
]
