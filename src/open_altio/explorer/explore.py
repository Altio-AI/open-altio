"""The explorer's questions about the live release: counts, charts, the case list and one
case. The searches for products, drugs and reactions are search.py's.

Every function takes the request's `Data` and its query string as a dict of
lists (urllib's parse_qs) and returns what /api answers, as plain values.

Filters are the app's own (`open_altio.explorer.filters.parse`), plus the drugs, counted as
rule explorer-drug-counts says (drugs.py):

    product          the drug whose page this is: an ingredient or a combination as the
                     release names it (`valsartan`, `sacubitril;valsartan`), or FDA's spelling
                     with no ingredient; any other of FDA's names opens the drug it is read to
    unit             any (any product containing it) or exact (that product alone)
    prole            the roles counted, FDA's codes PS, SS, I and C (repeated)
    exclude          a spelling of the drug left out (repeated)
    include          FDA's spelling with no ingredient counted with it (repeated)
    dprod, drole     All cases' drug filter: drugs or FDA's spellings with no ingredient,
                     and the roles counted
    pt               reactions, any case-insensitive spelling: with MedDRA, current PTs, each
                     counting every text FDA wrote that reads to it (reactions.py)
    label            a product's Label status (filters.py), kept only on a product's page of a
                     release that holds the label flags (labels.py)
    smq              code:narrow or code:broad, expanded to the SMQ's preferred terms
                     (only for a viewer who may see MedDRA's licensed part)
    pt_out           a preferred term left out of the chosen ones (repeated), such as one
                     term of a chosen SMQ
    soc              a MedDRA system organ class name (repeated): cases with any reaction in it
                     (only for a viewer who may see MedDRA's licensed part)
    atc, atc_out, arole, could  the drug class filter (classes.py; only where the release
                     carries WHO's classes and the viewer may see them)

Reactions chosen through `pt` and `smq` count a case when it has any of
them, less those in `pt_out`. No value from the query is ever put into SQL text.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any

from open_altio.faers import not_given
from open_altio.faers.derive import direct_report
from open_altio.faers.duplicates import reason_lines
from open_altio.faers.explorer_db import CHILD_ORDER
from open_altio.faers.schema import RAW_COLUMNS
from open_altio.rulebook import value

from . import classes, drugs, labels, socs
from .answers import Problem
from .classes import NOT_HELD, Choice, Layer
from .drugs import Unit
from .facts import Facts
from .filters import DIRECT, NOT_GIVEN, Filters, parse
from .meddra import ServedMeddra
from .reactions import Reactions
from .release import OpenRelease

Query = dict[str, list[str]]
# a page's questions, side by side
POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="explore")


@dataclass(frozen=True)
class Data:
    """What one request reads: the live release, its facts, the MedDRA version served when the
    person may see SMQs, lower-level terms and the text to PT link, the access hook's words for
    when not, and how reactions are named for this person (reactions.py); the release's drug
    classes when it carries them and the person may see them, and why not."""

    opened: OpenRelease
    facts: Facts
    meddra: ServedMeddra | None
    why_no_smqs: str
    reactions: Reactions
    classes: Layer | None = None
    why_no_classes: str = NOT_HELD

    def rows(self, sql: str, params: list | None = None) -> list[dict[str, Any]]:
        return self.opened.rows(sql, params)

    def pt_name(self, term: str | None) -> str | None:
        return self.reactions.name(term)

    def served_meddra(self) -> ServedMeddra:
        """The MedDRA version this person's SMQs come from; refused when there is none."""
        if self.meddra is None:
            raise Problem(403, self.why_no_smqs)
        return self.meddra

    def need_classes(self) -> Layer:
        """The drug classes this person sees; refused when there are none."""
        if self.classes is None:
            held = self.why_no_classes != NOT_HELD
            raise Problem(403 if held else 404, self.why_no_classes)
        return self.classes


def value_of(query: Query, name: str, default: str = "") -> str:
    """The first value the query string gives `name`."""
    return (query.get(name) or [default])[0]


def tidy(text: str) -> str:
    """Typed text with its runs of spaces made one."""
    return re.sub(r"\s+", " ", text).strip()


def list_length(name: str) -> int:
    """How long a list or a search's answers are (rule explorer-lists)."""
    return int(value("explorer-lists", name))


# what a question is asked of: the app's own Filters, plus the product, reactions and drugs -----


def reaction_terms(data: Data, query: Query) -> list[str]:
    """The chosen reactions as keys (reactions.py): typed terms and the person's own queries
    arrive as `pt`, SMQs as `smq=code:narrow|broad`, the terms left out of them as `pt_out`."""
    terms = {k for k in map(data.reactions.key, query.get("pt", [])) if k}
    out = {k for k in map(data.reactions.key, query.get("pt_out", [])) if k}
    chosen = query.get("smq", [])
    if chosen:
        meddra = data.served_meddra()
        for item in chosen:
            code, _, scope = item.partition(":")
            q = meddra.smqs().get(code)
            if q is None:
                raise Problem(400, f"{code} is not an SMQ in MedDRA {meddra.version}.")
            terms |= q["broad"] if scope == "broad" else q["narrow"]
    if out and not terms - out:
        raise Problem(400, "Every chosen reaction is left out: choose one, or clear the filter.")
    return sorted(terms - out)


def _unit(data: Data, name: str, roles: tuple[str, ...], exact: bool) -> Unit:
    """A drug as a name opens it; a name the release does not hold counts nothing."""
    found = data.facts.name_of(name)
    if found and found[0] == "ingredient":
        return Unit(found[1], roles, exact)
    return Unit(None, roles, included=(found[1] if found else name.strip().upper(),))


def product_unit(data: Data, query: Query) -> Unit | None:
    """The drug whose page this is, as the page counts it."""
    name = value_of(query, "product").strip()
    if not name:
        return None
    try:
        roles = drugs.chosen_roles(query.get("prole", []))
        exact = drugs.chosen_unit(value_of(query, "unit")) == "exact"
    except ValueError as exc:
        raise Problem(400, str(exc)) from None
    unit = _unit(data, name, roles, exact)
    spelled = [s.strip().upper() for s in query.get("include", []) if s.strip()]
    if unit.substance is None:
        return Unit(None, roles, included=tuple(dict.fromkeys(unit.included + tuple(spelled))))
    excluded = sorted({s.strip().upper() for s in query.get("exclude", []) if s.strip()})
    return Unit(unit.substance, roles, exact, tuple(excluded), tuple(dict.fromkeys(spelled)))


def drug_choice(data: Data, query: Query) -> list[Unit]:
    """All cases' chosen drugs, each counted in any product containing it (or as the rule's
    default unit says), in the roles `drole` names; FDA's spellings with no ingredient as one."""
    names = sorted({d.strip() for d in query.get("dprod", []) if d.strip()})
    if not names:
        return []
    try:
        roles = drugs.chosen_roles(query.get("drole", []))
    except ValueError as exc:
        raise Problem(400, str(exc)) from None
    exact = drugs.default_unit() == "exact"
    units = [_unit(data, n, roles, exact) for n in names]
    spelled = tuple(s for u in units if u.substance is None for s in u.included)
    found = [u for u in units if u.substance is not None]
    return found + ([Unit(None, roles, included=spelled)] if spelled else [])


@dataclass(frozen=True)
class Scope:
    """What a question is asked of: the filters; the drug whose page it is, as the page counts it
    (`product`); the chosen reactions as keys, and how the release names them; All cases' chosen
    drugs; and the drug class filter."""

    filters: Filters
    product: Unit | None
    terms: list[str]
    drugs: list[Unit]
    reactions: Reactions
    classes: Choice | None = None
    soc_texts: tuple[str, ...] = ()  # the reaction texts that read to the chosen SOCs

    def where(self, **changed: Any) -> tuple[str, list]:
        """The WHERE condition over `explorer_case_T c` and its parameters; `changed` sets filters
        for this question alone (a chart of one filter counts under all the others)."""
        filters = self.filters.with_(**changed)
        # the filters' one reaction is matched as the chosen ones are
        clause = filters.with_(reaction="").where()
        sql, params = clause.sql, list(clause.params)
        one = self.reactions.key(filters.reaction) if filters.reaction else None
        for keys in ([one] if one else [], self.terms):
            if keys:
                sql += (
                    " AND c.case_id_T IN (SELECT case_id_T FROM explorer_reac_term_T "
                    "WHERE term_T IN (SELECT unnest(?::VARCHAR[])))"
                )
                params.append(self.reactions.texts(keys))
        for units in (self.drugs, [self.product] if self.product else []):
            if units:
                cases, more = drugs.cases_of(units)
                sql += f" AND c.case_id_T IN ({cases})"
                params += more
        if self.soc_texts:
            sql += (
                " AND c.case_id_T IN (SELECT case_id_T FROM explorer_reac_term_T "
                "WHERE term_T IN (SELECT unnest(?::VARCHAR[])))"
            )
            params.append(list(self.soc_texts))
        if self.classes:
            cases, more = self.classes.cases()
            sql += f" AND c.case_id_T IN ({cases})"
            params += more
        return sql, params


def scope(data: Data, query: Query) -> Scope:
    """The Scope a page's query string asks for (the names are in this module's docstring)."""
    product = product_unit(data, query)
    return Scope(
        filters=labels.narrowed(data, parse(query), product),
        product=product,
        terms=reaction_terms(data, query),
        drugs=drug_choice(data, query),
        reactions=data.reactions,
        classes=classes.choice_of(data, query),
        soc_texts=tuple(socs.chosen_texts(data, query)),
    )


def _together(data: Data, jobs: dict[str, tuple[str, list]]) -> dict[str, list[dict]]:
    """Run several queries side by side; their rows by name."""
    futures = {k: POOL.submit(data.rows, sql, params) for k, (sql, params) in jobs.items()}
    return {k: f.result() for k, f in futures.items()}


# the counts and charts ------------------------------------------------------------------------

# A case is dated by its duplicate group's first receipt, group_first_dt_T
# (rules/dup-shown-copy.md), so an event keeps its timing whichever copy is shown. The smallest unit
# FDA records is a day: its receipt dates carry no time. A case whose date FDA gave only as a month
# or a year has no date, so it cannot be placed and is counted apart.
GRAINS = {
    "year": "date_trunc('year', c.group_first_dt_T)",
    "month": "date_trunc('month', c.group_first_dt_T)",
    "week": "date_trunc('week', c.group_first_dt_T)",
    "day": "c.group_first_dt_T",
}


def timeline(data: Data, query: Query) -> dict:
    """Cases by the period FDA first received them, at the grain asked for."""
    sql, params = scope(data, query).where()
    grain = value_of(query, "grain", "year")
    grain = grain if grain in GRAINS else "year"
    got = data.rows(
        f"SELECT CAST({GRAINS[grain]} AS DATE) AS k, count(*) AS n FROM explorer_case_T c "
        f"WHERE {sql} GROUP BY 1 ORDER BY 1 NULLS LAST",
        params,
    )
    return {
        "grain": grain,
        "rows": [[str(r["k"]), r["n"]] for r in got if r["k"] is not None],
        "undated": sum(r["n"] for r in got if r["k"] is None),
    }


def summary(data: Data, query: Query) -> dict:
    """The count line and every Overview chart. Each chart of one filter
    counts under every other filter, so its other bars stay to choose from."""
    asked = scope(data, query)
    full_sql, full_params = asked.where()
    nd_sql, nd_params = asked.where(dedup="all")
    reacs, reac_params = data.reactions.keyed()  # each reaction counted as the release names it

    jobs = {
        "counts": (
            f"SELECT c.era_T AS era, c.dup_kept_T AS kept, count(*) AS n FROM explorer_case_T c "
            f"WHERE {nd_sql} GROUP BY ALL",
            nd_params,
        ),
        "serious": (
            f"SELECT count(*) AS n FROM explorer_case_T c WHERE {full_sql} "
            "AND len(c.outcomes_T) > 0",
            full_params,
        ),
        "years": (
            "SELECT year(c.group_first_dt_T) AS k, count(*) AS n FROM explorer_case_T c WHERE "
            f"{full_sql} GROUP BY 1 ORDER BY 1",
            full_params,
        ),
        "reactions": (
            f"SELECT r.k, count(DISTINCT r.case_id_T) AS n FROM {reacs} r "
            f"WHERE r.case_id_T IN (SELECT c.case_id_T FROM explorer_case_T c WHERE {full_sql}) "
            f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT ?",
            reac_params + full_params + [list_length("top_reactions")],
        ),
    }
    facets: dict[str, tuple[str, dict[str, Any]]] = {
        "sex": ("c.sex_T", {"sexes": ()}),
        "age": (f"coalesce(c.age_band_T, '{NOT_GIVEN}')", {"ages": ()}),
        "reporter": ("c.reporter_type_T", {"reporters": ()}),
        "country": ("c.country_T", {"countries": ()}),
        # a direct report's sender is FDA's intake, not a company: one bar
        "sender": (
            f"CASE WHEN {direct_report('c.rept_cod')} THEN '{DIRECT}' ELSE c.company_T END",
            {"sender": ""},
        ),
    }
    for name, (expr, drop) in facets.items():
        sql, params = asked.where(**drop)
        jobs[name] = (
            f"SELECT {expr} AS k, count(*) AS n FROM explorer_case_T c WHERE {sql} "
            f"GROUP BY 1 ORDER BY 2 DESC, 1",
            params,
        )
    sql, params = asked.where(outcomes=())
    jobs["outcome"] = (
        f"SELECT o AS k, count(*) AS n FROM (SELECT unnest(CASE WHEN len(c.outcomes_T) = 0 "
        f"THEN ['{NOT_GIVEN}'] ELSE c.outcomes_T END) AS o FROM explorer_case_T c WHERE {sql}) "
        f"GROUP BY 1 ORDER BY 2 DESC, 1",
        params,
    )
    jobs["given_outcome"] = (
        f"SELECT count(*) AS n, count(*) FILTER (WHERE len(c.outcomes_T) > 0) AS g "
        f"FROM explorer_case_T c WHERE {sql}",
        params,
    )
    jobs["given_reaction"] = (
        f"SELECT count(*) AS n, count(*) FILTER (WHERE c.case_id_T IN "
        f"(SELECT r.case_id_T FROM {reacs} r)) AS g FROM explorer_case_T c WHERE {full_sql}",
        reac_params + full_params,
    )
    sql, params = asked.where(eras=("AERS", "FAERS"))
    jobs["era"] = (
        f"SELECT c.era_T AS k, count(*) AS n FROM explorer_case_T c WHERE {sql} GROUP BY 1",
        params,
    )
    product = asked.product
    if product and product.substance:
        # how many of FDA's spellings the page counts: its drug's, less those left out
        match, matched = product.match()
        jobs["spellings"] = (
            "SELECT count(DISTINCT spelling_T) AS n FROM explorer_ingredient_T "
            f"WHERE {match} AND NOT list_contains(?::VARCHAR[], spelling_T)",
            matched + [list(product.excluded)],
        )
    if not product:
        # the ingredients reported most in the default roles, under every filter but the drugs
        sql, params = replace(asked, drugs=[]).where()
        roles = drugs.default_roles()
        jobs["given_dprods"] = (
            "SELECT count(*) AS n, count(*) FILTER (WHERE c.case_id_T IN (SELECT i.case_id_T "
            f"FROM explorer_ingredient_T i WHERE i.role_T IN ({', '.join('?' for _ in roles)}))) "
            f"AS g FROM explorer_case_T c WHERE {sql}",
            list(roles) + params,
        )
        jobs["drugs"] = (
            "SELECT i.ingredient_T AS k, count(DISTINCT i.case_id_T) AS n FROM "
            f"explorer_ingredient_T i WHERE i.role_T IN ({', '.join('?' for _ in roles)}) "
            f"AND i.case_id_T IN (SELECT c.case_id_T FROM explorer_case_T c WHERE {sql}) "
            "GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT ?",
            list(roles) + params + [list_length("top_drugs")],
        )

    if data.meddra is not None:
        sql, params = replace(asked, soc_texts=()).where()
        jobs["soc"] = socs.breakdown_job(data, sql, params)
        jobs["given_soc"] = socs.coverage_job(data, sql, params)

    if data.classes and not product:
        parent = classes.breakdown_parent(asked.classes)
        roles = classes.roles_of(query)
        limit = list_length("top_classes")
        jobs |= classes.breakdown_jobs(parent, roles, (full_sql, full_params), limit)
        jobs["given_atc"] = classes.coverage_job(roles, (full_sql, full_params))

    out = _together(data, jobs)
    kept_only = asked.filters.kept_only
    counts = out.pop("counts")
    by_era: dict[str, int] = {}
    for r in counts:
        if r["kept"] or not kept_only:
            by_era[r["era"]] = by_era.get(r["era"], 0) + r["n"]
    result: dict[str, Any] = {
        "cases": sum(by_era.values()),
        "by_era": by_era,
        "all_cases": sum(r["n"] for r in counts),
        "set_aside": sum(r["n"] for r in counts if not r["kept"]),
        "serious": out.pop("serious")[0]["n"],
        "kept_only": kept_only,
    }
    # how many of each field chart's cases give its field: those not Not given (rule not-given)
    result["given"] = {}
    for name in facets:
        cases = sum(r["n"] for r in out[name])
        none = sum(r["n"] for r in out[name] if r["k"] in (None, NOT_GIVEN))
        result["given"][name] = [cases - none, cases]
    # the other charts count their cases with a reaction row, an outcome, an ingredient or a class
    for name in [k for k in out if k.startswith("given_")]:
        row = out.pop(name)[0]
        result["given"][name.removeprefix("given_")] = [row["g"], row["n"]]
    if product:
        spelled = out.pop("spellings")[0]["n"] if "spellings" in out else 0
        result["spellings"] = spelled + len(product.included)
    if "class_rows" in out:
        result["classes"] = classes.breakdown(data, parent, roles, out)
    for k, v in out.items():
        result[k] = [[r["k"], r["n"]] for r in v]
    result["reactions"] = [[data.pt_name(k), n] for k, n in result["reactions"]]
    # the companies that sent the most cases with the direct reports' bar, most first, then
    # Not given
    senders = result["sender"]
    companies = [r for r in senders if r[0] not in (None, DIRECT)]
    shown = companies[: list_length("companies_charted")] + [r for r in senders if r[0] == DIRECT]
    result["sender"] = sorted(shown, key=lambda r: -r[1]) + [r for r in senders if r[0] is None]
    if "drugs" in result:
        result["drugs"] = [[k, n, drugs.title(k)] for k, n in result["drugs"]]
    return result


# the case list and one case ------------------------------------------------------------------

# newest and oldest by the date the case is dated by, as GRAINS
CASE_ORDER = {
    "newest": "c.group_first_dt_T DESC NULLS LAST, c.case_id_T",
    "oldest": "c.group_first_dt_T ASC NULLS LAST, c.case_id_T",
    "age": "c.age_years_T DESC NULLS LAST, c.case_id_T",
    "age-asc": "c.age_years_T ASC NULLS LAST, c.case_id_T",
}


def cases(data: Data, query: Query) -> dict:
    """One page of matching cases (rule explorer-page-size), each with its
    drugs and reactions."""
    sql, params = scope(data, query).where()
    try:
        page = max(1, int(value_of(query, "page", "1")))
    except ValueError:
        page = 1
    size = int(value("explorer-page-size", "cases_per_page"))
    order = CASE_ORDER.get(value_of(query, "sort", "newest"), CASE_ORDER["newest"])
    found = data.rows(
        "SELECT c.case_id_T, c.era_T, c.case_key_T, c.first_fda_dt_T, c.group_first_dt_T, "
        "c.event_dt, c.event_dt_T, c.event_dt_prec_T, c.age, c.age_cod, c.age_years_T, c.sex_T, "
        "c.country_T, c.occp_cod, c.rept_cod, c.outcomes_T, c.dup_kept_T, c.probable_duplicate_T, "
        "c.serious_no_drug_or_reaction_T "
        f"FROM explorer_case_T c WHERE {sql} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [size, (page - 1) * size],
    )
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
    shown = {"meddra_version": data.meddra.version} if data.meddra is not None else {}
    return {"page": page, "size": size, "cases": found} | shown


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


def export_size(data: Data, query: Query) -> dict:
    """Rows in each file of a filtered export (cases, their drugs, their
    reactions); rule export-csv-row-cap counts these plus a header line."""
    sql, params = scope(data, query).where()
    picked = f"SELECT c.case_id_T FROM explorer_case_T c WHERE {sql}"
    out = _together(
        data,
        {
            "cases": (f"SELECT count(*) AS n FROM explorer_case_T c WHERE {sql}", params),
            "drugs": (
                f"SELECT count(*) AS n FROM explorer_drug_T WHERE case_id_T IN ({picked})",
                params,
            ),
            "reactions": (
                f"SELECT count(*) AS n FROM explorer_reac_T WHERE case_id_T IN ({picked})",
                params,
            ),
        },
    )
    return {k: v[0]["n"] for k, v in out.items()}


__all__ = [
    "Data",
    "Query",
    "Scope",
    "case",
    "cases",
    "export_size",
    "list_length",
    "product_unit",
    "scope",
    "summary",
    "tidy",
    "timeline",
    "value_of",
]
