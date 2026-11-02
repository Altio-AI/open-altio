"""Every way the data leaves the explorer as a file: the filtered export, a
SQL result whole, and what the Tables page says about downloading whole
tables. Each file made is told to the access hook with what was taken.

The filtered export (rules export-csv-row-cap, filtered-vs-full-export) uses
the filters of explore.py, product and reactions included, so it holds the
cases /api/exportsize counted. CSV is refused when the largest of the three
files, header line included, is over the cap.

A SQL result (rule sql-result-download) is run again in full, under rule
sql-limits, and refused past its row limit with a pointer to the tables.

Whole tables are the release's own Parquet files. Here they are on the
machine the explorer runs on, so the page says where; a host that offers
them for download answers /api/downloads itself.
"""

from __future__ import annotations

import shutil
import time
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from open_altio import scratch

from . import classes, explore
from . import export as filtered
from .access import Viewer
from .answers import answer, json_body, problem
from .api import named, query_of
from .context import Explorer, explorer, viewer
from .described import described as describe
from .sql import Busy, LimitHit, Refused
from .sql_files import TooLarge, download_rows
from .tables import database

router = APIRouter(prefix="/api")

MEDIA = {"csv": "text/csv", "parquet": "application/vnd.apache.parquet"}


def limits() -> dict[str, int]:
    """What the page needs to know before it offers CSV or a SQL result's download."""
    return {"csv_row_cap": filtered.csv_row_cap(), "sql_download_rows": download_rows()}


def tables_here(data: explore.Data, query: explore.Query) -> dict:
    """Where the release's whole tables are: on this computer, so the page says where."""
    folder = data.opened.folder / "parquet"
    why = f"The release's tables are on this computer, as Parquet files in {folder}."
    return {"on": False, "why": why, "release": data.opened.name, **limits()}


@router.get("/downloads")
def downloads(
    request: Request, ex: Explorer = Depends(explorer), v: Viewer = Depends(viewer)
) -> Response:
    data = ex.data(v)
    return answer(named(tables_here(data, query_of(request)), data))


# the filtered export ---------------------------------------------------------------------------


@router.get("/export")
def export(
    request: Request, ex: Explorer = Depends(explorer), v: Viewer = Depends(viewer)
) -> Response:
    if not v.exports:
        return problem(403, "Exports are not open to you here.")
    data = ex.data(v)
    query = query_of(request)
    fmt = (query.pop("format", None) or [""])[0]
    if fmt not in filtered.FORMATS:
        return problem(400, "Choose CSV or Parquet for the export.")
    asked = explore.scope(data, query)
    rows = explore.export_size(data, query)
    if fmt == "csv" and not filtered.csv_fits(max(rows.values())):
        cap = filtered.csv_row_cap()
        return problem(
            409,
            f"Too large for CSV: the largest file would have {max(rows.values()) + 1:,} lines with "
            f"its header, and Excel opens {cap:,}. Choose Parquet.",
        )
    sql, params = asked.where()
    described = describe(data, query, asked)
    # a filter by class names WHO's codes, so WHO's citation goes with it, the files' classes or not
    chosen = asked.classes.manifest() | data.need_classes().words() if asked.classes else None
    machine = asked.filters.manifest()["filters"] | {
        "product": asked.product.manifest() if asked.product else None,
        "reactions": [t.strip() for t in query.get("pt", []) if t.strip()],
        "reactions_counted": data.reactions.about(),
        "smqs": query.get("smq", []),
        "reactions_left_out": [t.strip() for t in query.get("pt_out", []) if t.strip()],
        "drugs": [u.manifest() for u in asked.drugs],
        "classes": chosen,
    }
    text = urlencode(query, doseq=True)
    at = ex.clock.now()
    # each drug's class goes in the files only where this viewer may take WHO's classes away
    layer = classes.layer_of(data.opened.manifest) if v.who_files else None
    written = filtered.write_export(
        data.opened,
        filtered.selection(sql),
        params,
        fmt,
        at,
        {"query": text, "filters": machine, "described": described},
        dict(ex.access.terms),
        layer.words() if layer else None,
    )
    ex.announce(
        v,
        "filtered_export",
        release=data.opened.name,
        query=text,
        described=described,
        format=fmt,
        rows=written.rows,
        at=at,
    )
    return filtered.send(written)


# a SQL result's download -----------------------------------------------------------------------


def _sql_download(ex: Explorer, v: Viewer, text: str, fmt: str) -> Response:
    started = time.monotonic()
    db = database(ex, v)
    stamp = ex.clock.now().strftime("%Y%m%dT%H%M%SZ")
    work = scratch.make("open-altio-sql-download-")
    target = work / f"sql-result-{db.name}-{stamp}.{fmt}"
    status, outcome, rows, message = 200, "ok", 0, ""
    try:
        with ex.sql.slot(v.id):
            rows = db.write(text, fmt, target)
    except (Busy, Refused, LimitHit, TooLarge) as exc:
        status, outcome, message = exc.status, exc.outcome, str(exc)
    ex.announce(
        v,
        "sql",
        sql=text,
        outcome=outcome,
        rows=rows,
        seconds=round(time.monotonic() - started, 3),
        download=fmt,
    )
    if status != 200:
        shutil.rmtree(work, ignore_errors=True)
        return problem(status, message)
    return FileResponse(
        target,
        media_type=MEDIA[fmt],
        filename=target.name,
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True),
    )


@router.post("/sql/download")
async def sql_download(
    request: Request, ex: Explorer = Depends(explorer), v: Viewer = Depends(viewer)
) -> Response:
    if not v.sql:
        return problem(403, "SQL is not open to you here.")
    asked: Any = await json_body(request)
    if isinstance(asked, Response):
        return asked
    fmt = str(asked.get("format") or "")
    if fmt not in filtered.FORMATS:
        return problem(400, "Choose CSV or Parquet.")
    return await run_in_threadpool(_sql_download, ex, v, str(asked.get("sql") or ""), fmt)


__all__ = ["limits", "router", "tables_here"]
