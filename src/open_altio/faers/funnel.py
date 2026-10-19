"""The funnel: how many cases each step of the build leaves, per era, written as funnel.json.

A new step is one entry appended to FUNNEL_STEPS. The build refuses a step without its card in
src/open_altio/faers/insights/steps.yaml and its title in rules/steps.yaml.
"""

from __future__ import annotations

import duckdb

from open_altio import rulebook

from . import drugnames, meddra
from .schema import ERAS

# Each step's table (or view) and the plain words for it, in order.
FUNNEL_STEPS: list[dict] = [
    {"id": "report_versions", "table": "demo", "label": "Report versions FDA published"},
    {"id": "latest_versions", "table": "demo_latest_T", "label": "Latest version of each case"},
    {
        "id": "after_deleted_lists",
        "table": "case_latest_T",
        "label": "Fewer cases on FDA's deleted-case lists",
    },
    {
        "id": "kept_after_duplicates",
        "table": "case_dedup_T",
        "label": "Fewer probable duplicates across cases, one shown per group: "
        + rulebook.value("dedup-default", "cross_case_method"),
    },
    # Steps that remove no case; one with `needs` is there when the release carries that table.
    {
        "id": "dates",
        "table": "case_dedup_T",
        "label": "The same cases, each date read as far as it is known and can be true",
    },
    {
        "id": "codes",
        "table": "case_dedup_T",
        "label": "The same cases, each reporter code read as its E2B(R3) reporter type",
    },
    {
        "id": "drug_names",
        "table": "case_dedup_T",
        "needs": drugnames.TABLES[0],
        "label": "The same cases, each drug read to its ingredients",
    },
    {
        "id": "meddra_terms",
        "table": "case_dedup_T",
        "needs": meddra.COLUMNS["pt"].table,
        "label": "The same cases, each MedDRA term read to the release's MedDRA version",
    },
]

# What the duplicate step could and could not do, for the methods page (rules/dedup-default.md):
# the cases the AEOLUS rule cannot compare because a field is empty, the cases each rule sets
# aside (a case both rules group counts under both), and the groups the padded-date guard leaves
# whole.
DUPLICATES_SQL = """
SELECT count(*) AS cases,
       count(*) FILTER (WHERE dup_key_T IS NULL) AS not_compared_by_aeolus,
       count(*) FILTER (WHERE NOT dup_kept_T) AS set_aside,
       count(*) FILTER (WHERE NOT dup_kept_T AND list_contains(dup_rule_T, 'aeolus')) AS aeolus,
       count(*) FILTER (WHERE NOT dup_kept_T
                        AND (list_contains(dup_rule_T, 'manufacturer_number')
                             OR list_contains(dup_rule_T, 'manufacturer_number_country_code')))
         AS manufacturer_number,
       count(DISTINCT dup_key_T) FILTER (WHERE dup_padded_date_T) AS padded_groups,
       count(*) FILTER (WHERE dup_padded_date_T) AS padded_cases
FROM case_dup_T
"""


def _duplicates(con: duckdb.DuckDBPyConnection) -> dict:
    [r] = con.execute(DUPLICATES_SQL).fetchall()
    return {
        "cases": int(r[0]),
        "not_compared_by_aeolus": int(r[1]),
        "set_aside": int(r[2]),
        "set_aside_by_rule": {"aeolus": int(r[3]), "manufacturer_number": int(r[4])},
        "padded_date_groups": {"groups": int(r[5]), "cases": int(r[6])},
    }


def _count_by_era(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, int]:
    rows = dict(con.execute(f"SELECT era_T, count(*) FROM {table} GROUP BY era_T").fetchall())
    out = {era: int(rows.get(era, 0)) for era in ERAS}
    out["total"] = sum(out.values())
    return out


def funnel(con: duckdb.DuckDBPyConnection, release: str) -> dict:
    """The funnel document of the release being built on `con`."""
    steps = []
    previous = None
    have = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    for spec in FUNNEL_STEPS:
        if "needs" in spec and spec["needs"] not in have:
            continue
        counts = _count_by_era(con, spec["table"])
        step = {k: v for k, v in spec.items() if k != "needs"} | {"count": counts}
        if previous is not None:
            step["removed"] = {k: previous[k] - counts[k] for k in counts}
        steps.append(step)
        previous = counts
    [(listed, listings)] = con.execute(
        "SELECT count(*), coalesce(sum(n_listings_T), 0) FROM deleted_cases_T"
    ).fetchall()
    return {
        "release": release,
        "eras": {"legacy": "AERS, 2004Q1 to 2012Q3", "faers": "FAERS, 2012Q4 onward"},
        "steps": steps,
        "deleted_lists": {"caseids_listed": int(listed), "listings": int(listings)},
        "duplicates": _duplicates(con),
    }
