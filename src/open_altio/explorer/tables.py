"""Tables and SQL: the live release's tables and views as a person meets
them, and read-only SQL over them.

    schema(db, manifest)   every table and view, in the order a person should meet them
    manifest_summary(m, f) what the Tables page says about the release as a whole, and its funnel
    run_sql(ex, v, ...)    one page of a query's rows, within rule sql-limits

SQL runs through `open_altio.explorer.sql`: one SELECT only, the release's
files only, its timeout, memory, threads and one query at a time per viewer.
A page holds `rows_shown` rows; `total` says how many the whole query gives.
Every query is told to the access hook, for a host that keeps a usage log.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from .access import Viewer
from .sql import Busy, LimitHit, Refused, SqlDatabase, withheld

if TYPE_CHECKING:
    from .context import Explorer

# The layers, and the order of their tables and views on the page.
GROUPS = [
    (
        "start",
        [
            "case_dedup_T",
            "drug_dedup_T",
            "reac_dedup_T",
            "outc_dedup_T",
            "rpsr_dedup_T",
            "ther_dedup_T",
            "indi_dedup_T",
        ],
    ),
    (
        "latest",
        [
            "case_latest_T",
            "drug_latest_T",
            "drug_onset_T",
            "drug_route_T",
            "reac_latest_T",
            "outc_latest_T",
            "rpsr_latest_T",
            "ther_latest_T",
            "indi_latest_T",
            "case_dup_T",
            "deleted_cases_T",
            "quarters_T",
        ],
    ),
    ("versions", ["demo_T", "demo_latest_T"]),
    ("raw", ["demo", "drug", "reac", "outc", "rpsr", "ther", "indi", "deleted"]),
]

# What the page calls each layer (GROUP_WORDS in ui/tablewords.js), for a host that names a layer
# in words of its own, such as its usage log.
LAYER_WORDS = {
    "start": "Start here",
    "latest": "Every case, duplicates flagged",
    "versions": "Every version of every report",
    "raw": "As FDA published them",
}


def schema(db: SqlDatabase, manifest: dict) -> list[dict]:
    """Every table and view of the release by layer, with rows, size and columns."""
    rows_of = {k: v.get("rows") for k, v in manifest["tables"].items()}
    rows_of |= {k: v.get("rows") for k, v in manifest["views"]["views"].items()}
    bytes_of = {k: v.get("bytes") for k, v in manifest["tables"].items()}
    columns = {r.name: r.columns for r in db.schema}
    out = []
    # a table a later step adds beside FDA's (the drug ingredients) goes with every case's tables
    named = {n for _, names in GROUPS for n in names}
    added = [n for n in manifest["tables"] if n not in named]
    for group, names in [*GROUPS, ("latest", added)]:
        for name in names:
            if name in columns:
                out.append(
                    {
                        "name": name,
                        "group": group,
                        "view": name not in bytes_of,
                        "rows": rows_of.get(name),
                        "bytes": bytes_of.get(name),
                        "columns": [[c, t] for c, t in columns[name]],
                    }
                )
    return out


def manifest_summary(m: dict, funnel: dict, *, classes: bool = True, by_pt: bool = True) -> dict:
    """The release as a whole: its manifest, and its case funnel's steps (funnel.json) in its own
    words; without the tables a viewer is not given (sql.withheld)."""
    hidden = set(withheld(m, classes=classes, by_pt=by_pt))
    return {
        "release": m["release"],
        "built_at": m["built_at"],
        "quarters": [m["quarters"][0], m["quarters"][-1]],
        "release_bytes": m["release_bytes"],
        "funnel": [
            {"label": s["label"], "table": s["table"], "cases": s["count"]["total"]}
            for s in funnel["steps"]
        ],
        "tables": [
            {"name": k, "kind": v.get("kind"), "rows": v.get("rows"), "bytes": v.get("bytes")}
            for k, v in m["tables"].items()
            if k not in hidden
        ],
        "views": [{"name": k, "rows": v.get("rows")} for k, v in m["views"]["views"].items()],
    }


# SQL --------------------------------------------------------------------------------------------


def run_sql(ex: Explorer, viewer: Viewer, text: str, page: int) -> tuple[int, dict]:
    """(HTTP status, answer) for one query: the page asked for, or a problem."""
    started = time.monotonic()
    answer: dict
    status, outcome, shown = 200, "ok", 0
    try:
        db = ex.sql.current(classes=viewer.who_files, by_pt=viewer.named_by_meddra)
        with ex.sql.slot(viewer.id):
            result = db.run(text, page=page)
        shown = len(result.rows)
        answer = {
            "columns": result.columns,
            "rows": [list(r) for r in result.rows],
            "total": result.total,
            "page": result.page,
            "size": result.size,
            "seconds": result.seconds,
        }
    except (Busy, Refused, LimitHit) as exc:
        status, outcome, answer = exc.status, exc.outcome, {"problem": str(exc)}
    ex.access.record(
        viewer,
        "sql",
        sql=text,
        outcome=outcome,
        rows=shown,
        seconds=round(time.monotonic() - started, 3),
    )
    return status, answer


__all__ = ["GROUPS", "LAYER_WORDS", "manifest_summary", "run_sql", "schema"]
