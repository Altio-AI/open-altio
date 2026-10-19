"""The /api routes the page reads its data from. Who may ask is the access
hook's to say (context.viewer); filters are those of explore.py."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode

from fastapi import APIRouter, Depends, Request, Response
from starlette.concurrency import run_in_threadpool

from open_altio.faers import FUNNEL_FILE
from open_altio.rulebook import value

from . import classes, explore, labels, search, statistics, tables
from .access import Viewer
from .answers import answer, json_body, problem
from .context import Explorer, explorer, viewer
from .drugs import words as drug_words
from .explore import Data

router = APIRouter(prefix="/api")


def query_of(request: Request) -> explore.Query:
    return parse_qs(request.url.query)


def remembered(name: str, data: Data, query: str, make: Callable[[], Any]) -> Any:
    """Answers that take a while are kept per release, by the question (`query`, an address's
    query string, read as a page writes it or not); the MedDRA version that names its
    reactions, and whether this person may see SMQs and WHO's classes, are part of the key."""
    meddra = "meddra" if data.meddra is not None else "-"
    who = "classes" if data.classes is not None else "-"
    asked = urlencode(sorted(parse_qsl(query), key=lambda pair: pair[0]))
    key = f"{name}|{data.reactions.version or '-'}|{meddra}|{who}|{asked}"
    return data.facts.remember(key, make)


def _result(
    request: Request,
    ex: Explorer,
    v: Viewer,
    how: Callable[[Data, explore.Query], Any],
    name: str = "",
) -> Any:
    data = ex.data(v)
    query = query_of(request)
    if name:
        return remembered(name, data, request.url.query, lambda: how(data, query))
    return how(data, query)


def _ask(
    request: Request,
    ex: Explorer,
    v: Viewer,
    how: Callable[[Data, explore.Query], Any],
    name: str = "",
) -> Response:
    return answer(_result(request, ex, v, how, name))


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
        ex.access.record(v, "search", search=what, words=found["q"], results=results)
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


@router.get("/release")
def release(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    def info(data: Data, query: explore.Query) -> dict:
        shown = data.classes.words() if data.classes else None
        return data.facts.info | {
            "drugs": drug_words(),
            "reactions": data.reactions.about(),
            "classes": shown,
            "class_statistics": statistics.classes_held(data),
            "labels": labels.screens(data.opened),
            # a MedDRA part an older Open Altio added, not served: how to add it again
            "meddra_older": ex.meddra.older(),
        }

    return _ask(request, ex, v, info)


@router.get("/products")
def products(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _search(request, ex, v, search.products, "products")


@router.get("/product")
def product(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    found = search.product(ex.data(v), (query_of(request).get("product") or [""])[0])
    return answer(found) if found else problem(404, "not found")


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


@router.get("/cases")
def cases(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, explore.cases)


@router.get("/case/{era}/{key:path}")
def one_case(era: str, key: str, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    found = explore.case(ex.data(v), era, key)
    return answer(found) if found else problem(404, "not found")


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


@router.get("/classes")
def drug_classes(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    def listing(data: Data, query: explore.Query) -> dict:
        other = replace(explore.scope(data, query), classes=None).where()
        return classes.listing(data, query, other, limit=explore.list_length("classes_found"))

    return _search(request, ex, v, listing, "classes", "classes")


@router.get("/exportsize")
def exportsize(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    """The export dialog's rows per file: an export started, told to the access hook."""
    rows = _result(request, ex, v, explore.export_size)
    ex.access.record(v, "export_started", rows=rows)
    return answer(rows)


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


# the label flags: {} where the release holds none (labels.py) ------------------------------------


def _label_product(data: Data, query: explore.Query) -> dict:
    """The labels a product page's drug is read against, and each of its reactions' flag."""
    unit = explore.product_unit(data, query)
    return labels.product_flags(data, unit.substance, unit.exact) if unit and unit.substance else {}


@router.get("/labels/product")
def label_product(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, _label_product)


def _label_counts(data: Data, query: explore.Query) -> dict:
    """Label status's counts: cases under every filter but Label status itself."""
    sc = explore.scope(data, query)
    if not (sc.product and sc.product.substance):
        return {}
    sql, params = sc.where(labels=None, label_cases=None)
    counts = labels.label_counts(data, sc.product.substance, sql, params, sc.product.exact)
    return {"cases": counts}


@router.get("/labels/cases")
def label_cases(request: Request, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return _ask(request, ex, v, _label_counts, "labelcounts")


@router.get("/labels/case/{era}/{key:path}")
def label_case(era: str, key: str, ex: Explorer = Ex, v: Viewer = Who) -> Response:
    return answer(labels.case_flags(ex.data(v), era, key))


# tables and SQL ----------------------------------------------------------------------------------


@router.get("/schema")
def schema(ex: Explorer = Ex, v: Viewer = Who) -> Response:
    data = ex.data(v)
    db = ex.sql.current(classes=v.who_files, by_pt=v.named_by_meddra)
    return answer(tables.schema(db, data.opened.manifest))


@router.get("/manifest")
def manifest(ex: Explorer = Ex, v: Viewer = Who) -> Response:
    opened = ex.data(v).opened
    funnel = json.loads((opened.folder / FUNNEL_FILE).read_text(encoding="utf-8"))
    return answer(
        tables.manifest_summary(
            opened.manifest, funnel, classes=v.who_files, by_pt=v.named_by_meddra
        )
    )


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


__all__ = ["query_of", "remembered", "router"]
