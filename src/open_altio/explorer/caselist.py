"""The case list (/api/cases) and one case (/api/case/{era}/{key}). The list is one page of the
cases a question asks for, each with its drugs and reactions, and lists the cases behind any
count another question answers, as that count's `cases_query` asks for them
(answers.cases_query).

    cases(data, query)   the filters, `page` and `sort` (casecolumns.py); and

    event                a reaction (repeated): only the cases naming any of them, counted as
                         one event, as a drug's events and a group of reactions count them
    case_number          the first digits of a case number: only the cases whose number starts
                         with them
    detail               `columns`: on a product's page, more of each case about the drug
                         (casecolumns.columns)
    period               before or window: the question is an event's breakdowns, the event
                         named as `event` (breakdowns.case_filter), and the list its cases
                         counted in that period
    field, value         a breakdown line's field: of those, the cases that give it, and with
                         `value` the cases that give that value

    case(data, era, key) one case with every row the release holds for it

No value from the query is put into SQL text.
"""

from __future__ import annotations

from open_altio.faers import not_given
from open_altio.faers.derive import direct_report
from open_altio.faers.duplicates import reason_lines
from open_altio.faers.explorer_db import CHILD_ORDER
from open_altio.faers.schema import RAW_COLUMNS
from open_altio.rulebook import value

from . import breakdowns, casecolumns, classes, drugs
from .answers import Problem
from .casecolumns import CASE_ORDER
from .explore import Data, Query, Scope, scope, value_of
from .reactions import TERMS
from .release import OpenRelease

BREAKDOWN = ("period", "field", "value")
NO_EVENT = "Name the event of the breakdowns as event, one or more."


# the list's own parameters, which are not the question's
OWN = ("page", "sort", "event", "case_number", "detail")


def _picked(data: Data, query: Query) -> tuple[str, list, Scope | None]:
    """The condition over `explorer_case_T c` for the cases the question lists, and the
    question's Scope (none for a breakdown's count)."""
    events = query.get("event", [])
    sc = None
    if any(query.get(name) for name in BREAKDOWN):
        if not any(e.strip() for e in events):
            raise Problem(400, NO_EVENT)
        # the breakdowns name their event as reaction, and have no one-reaction filter
        asked = {k: v for k, v in query.items() if k not in OWN}
        sql, params = breakdowns.case_filter(data, asked | {"reaction": events})
    else:
        sc = scope(data, query)
        sql, params = sc.where()
        if events:
            sql += (
                f" AND c.case_id_T IN (SELECT case_id_T FROM {TERMS} "
                "WHERE term_T IN (SELECT unnest(?::VARCHAR[])))"
            )
            params.append(data.reactions.texts(sorted(_event_keys(data, query))))
    digits = "".join(ch for ch in value_of(query, "case_number") if ch.isdigit())
    if digits:
        sql += " AND starts_with(c.case_key_T, ?)"
        params.append(digits)
    return sql, params, sc


def _event_keys(data: Data, query: Query) -> set[str]:
    return {k for k in map(data.reactions.key, query.get("event", [])) if k}


def cases(data: Data, query: Query) -> dict:
    """One page of matching cases (rule explorer-page-size), each with its
    drugs and reactions, and how many cases match (`total`)."""
    sql, params, sc = _picked(data, query)
    try:
        page = max(1, int(value_of(query, "page", "1")))
    except ValueError:
        page = 1
    size = int(value("explorer-page-size", "cases_per_page"))
    # a breakdown's count is listed by its drug's own settings and filters
    asked = sc or scope(data, {k: v for k, v in query.items() if k not in (*OWN, *BREAKDOWN)})
    join, join_params, order, order_params = casecolumns.order(query, asked, (sql, params))
    found = data.rows(
        "SELECT c.case_id_T, c.era_T, c.case_key_T, c.first_fda_dt_T, c.group_first_dt_T, "
        "c.event_dt, c.event_dt_T, c.event_dt_prec_T, c.age, c.age_cod, c.age_years_T, c.sex_T, "
        "c.wt_kg_T, c.country_T, c.occp_cod, c.reporter_type_T, c.rept_cod, c.company_T, "
        f"{direct_report('c.rept_cod')} AS direct_T, c.outcomes_T, c.dup_kept_T, "
        "c.probable_duplicate_T, c.dup_shown_case_T, c.dup_other_cases_T, "
        f"c.serious_no_drug_or_reaction_T FROM explorer_case_T c {join} WHERE {sql} "
        f"ORDER BY {order} LIMIT ? OFFSET ?",
        join_params + params + order_params + [size, (page - 1) * size],
    )
    total = data.rows(f"SELECT count(*) AS n FROM explorer_case_T c WHERE {sql}", params)[0]["n"]
    if found:
        ids = [c["case_id_T"] for c in found]
        marks = ", ".join("?" for _ in ids)
        # each drug with its one class when the person sees classes: [code, name, broader]
        their_classes = classes.on_list(data, ids) if data.classes else {}
        their_drugs: dict[int, list] = {}
        for d in data.rows(
            f"SELECT case_id_T, drug_seq, drugname, prod_ai_norm_T, role_T FROM explorer_drug_T "
            f"WHERE case_id_T IN ({marks}) ORDER BY drug_seq",
            ids,
        ):
            their_drugs.setdefault(d["case_id_T"], []).append(
                [
                    d["drugname"],
                    d["prod_ai_norm_T"],
                    d["role_T"],
                    their_classes.get((d["case_id_T"], d["drug_seq"])),
                ]
            )
        reacs: dict[int, list] = {}
        for r in data.rows(
            f"SELECT case_id_T, pt FROM explorer_reac_T WHERE case_id_T IN ({marks})", ids
        ):
            reacs.setdefault(r["case_id_T"], []).append(r["pt"])
        for c in found:
            c["drugs"] = their_drugs.get(c["case_id_T"], [])
            c["reactions"] = reacs.get(c["case_id_T"], [])  # FDA's text, exactly as written
            if data.meddra is not None:
                c["current_pts_T"] = [data.meddra.current("pt", t) for t in c["reactions"]]
                c["socs_T"] = list(
                    dict.fromkeys(
                        s for t in c["reactions"] if (s := data.meddra.soc_of("pt", t)) is not None
                    )
                )
    if value_of(query, "detail") == "columns":
        casecolumns.columns(data, asked, found, set(asked.terms) | _event_keys(data, query))
    shown = {"meddra_version": data.meddra.version} if data.meddra is not None else {}
    return {"page": page, "size": size, "total": total, "cases": found} | shown


# one case ------------------------------------------------------------------------------------

ROUTE = "drug_route_T"


def drug_routes(opened: OpenRelease, c: dict) -> dict[str, dict] | None:
    """Each drug record of case `c` by its drug_seq: the route families it could be in, sorted
    (`route_families_T`, empty when nothing is known), and which of FDA's fields said so
    (`route_source_T`), as rule drug-route reads them; None when the release has no routes."""
    tables = opened.manifest["tables"]
    if ROUTE not in tables:
        return None
    found = opened.rows(
        "SELECT drug_seq, route_families_T, route_source_T FROM read_parquet(?) "
        "WHERE era_T = ? AND primaryid = ? AND quarter_T = ?",
        [str(opened.folder / tables[ROUTE]["path"]), c["era_T"], c["primaryid"], c["quarter_T"]],
    )
    return {
        r["drug_seq"]: {
            "route_families_T": r["route_families_T"].split(";") if r["route_families_T"] else [],
            "route_source_T": r["route_source_T"],
        }
        for r in found
    }


def case(data: Data, era: str, key: str) -> dict | None:
    """One case with every child row as the release holds it; `pt_T` and
    `indi_pt_T` are the spellings shown (rule legacy-term-spelling), a drug's
    `ingredient_T` its ingredients in words; for a viewer who may see MedDRA's
    licensed part, `current_pt_T` (on reactions and indications) and
    `rec_act_current_pt_T` name the current PT a text reads to where it is not
    the text itself, in `meddra_version`; a drug's `route_families_T` and
    `route_source_T` are its route families (drug_routes), where the release has
    them; `not_given_T` on the case and on each child row names the fields that
    read Not given (rule not-given); `direct_T`
    is true for a report sent straight to FDA (rule company-names); `reasons`
    says why a probable duplicate is shown or set aside, one sentence a line,
    and `group` lists its group's other copies with their own receipt. None
    when there is no such case."""
    found = data.rows(
        "SELECT * FROM explorer_case_T WHERE era_T = ? AND case_key_T = ?", [era, key]
    )
    if not found:
        return None
    c = found[0]
    cid = c["case_id_T"]
    marks = data.rows(
        f"SELECT {not_given.named(c, 'c')} AS f, {direct_report('c.rept_cod')} AS direct "
        "FROM explorer_case_T c WHERE case_id_T = ?",
        [cid],
    )[0]
    c["not_given_T"], c["direct_T"] = marks["f"], marks["direct"]
    # a child row's quarter and report type are its case's
    context = {"quarter": "k.quarter_T", "report": "k.rept_cod"}
    for child in ("drug", "reac", "outc", "ther", "indi"):
        c[child] = data.rows(
            f"SELECT d.*, {not_given.named(RAW_COLUMNS[child], 'd', **context)} AS not_given_T "
            f"FROM explorer_{child}_T d, (SELECT quarter_T, rept_cod FROM explorer_case_T "
            f"WHERE case_id_T = ?) k WHERE d.case_id_T = ? ORDER BY {CHILD_ORDER[child]}",
            [cid, cid],
        )
    routes = drug_routes(data.opened, c)
    for d in c["drug"]:
        d["ingredient_T"] = drugs.title(d["substance_T"]) if d.get("substance_T") else None
        if routes is not None:
            d |= routes.get(d["drug_seq"], {"route_families_T": [], "route_source_T": "none"})
    for r in c["reac"]:
        r["pt_T"] = r["pt_spelling_T"]
    for i in c["indi"]:
        i["indi_pt_T"] = i["indi_pt_spelling_T"]
    if data.meddra is not None:
        c["meddra_version"] = data.meddra.version
        for r in c["reac"]:
            r["current_pt_T"] = data.meddra.current("pt", r["pt"])
            r["rec_act_current_pt_T"] = data.meddra.current("drug_rec_act", r["drug_rec_act"])
            r["soc_T"] = data.meddra.soc_of("pt", r["pt"])
        for i in c["indi"]:
            i["current_pt_T"] = data.meddra.current("indi_pt", i["indi_pt"])
    c["reasons"] = reason_lines(c)
    if data.classes:
        c["classes"] = classes.in_case(data, cid)
    c["group"] = []
    if c["dup_group_T"] is not None and c["probable_duplicate_T"]:
        c["group"] = data.rows(
            "SELECT era_T, case_key_T, dup_kept_T, first_fda_dt_T FROM explorer_case_T WHERE "
            "dup_group_T = ? AND NOT (era_T = ? AND case_key_T = ?) ORDER BY era_T, case_key_T",
            [c["dup_group_T"], era, key],
        )
    return c


__all__ = ["CASE_ORDER", "case", "cases", "drug_routes"]
