"""The explorer's questions about the live release: counts, charts and one case. The case list
is caselist.py's, and the searches for products, drugs and reactions are search.py's.

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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date
from typing import Any
from urllib.parse import urlencode

from open_altio.faers.dates import received_day
from open_altio.faers.derive import direct_report
from open_altio.rulebook import value

from . import classes, drugs, labels, recordfilters, socs
from .answers import Problem, cases_query
from .classes import NOT_HELD, Choice, Layer
from .drugs import Unit
from .facts import Facts
from .filters import DEDUP_CHOICES, DIRECT, ERA_T, NOT_GIVEN, OUTCOMES_GIVEN, Filters, parse
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

    def remember(self, name: str, query: Query, make: Callable[[], Any]) -> Any:
        """An answer that takes a while, kept per release by its question; the MedDRA version
        that names its reactions, and whether this person may see SMQs and WHO's classes, are
        part of the key."""
        meddra = "meddra" if self.meddra is not None else "-"
        who = "classes" if self.classes is not None else "-"
        pairs = sorted(((k, v) for k, vs in query.items() for v in vs), key=lambda pair: pair[0])
        key = f"{name}|{self.opened.name}|{self.reactions.version or '-'}|{meddra}|{who}"
        return self.facts.remember(f"{key}|{urlencode(pairs)}", make)

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
    """The drug whose page this is, as the page counts it: the one way a question names a
    product, by its settings `product`, `prole`, `unit`, `include`, `exclude` and `dedup`
    (docs/reference/api.md, A product). A setting that is not one of its choices is refused."""
    name = value_of(query, "product").strip()
    if not name:
        return None
    try:
        roles = drugs.chosen_roles(query.get("prole", []))
        exact = drugs.chosen_unit(value_of(query, "unit")) == "exact"
    except ValueError as exc:
        raise Problem(400, str(exc)) from None
    dedup = value_of(query, "dedup").strip()
    if dedup and dedup not in DEDUP_CHOICES:
        raise Problem(400, f"Deduplication is {' or '.join(DEDUP_CHOICES)}.")
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
        records = recordfilters.Records.of(self.product)
        for more_sql, more in recordfilters.where(filters, records, self.reactions):
            sql += f" AND {more_sql}"
            params += more
        return sql, params


def scope(data: Data, query: Query) -> Scope:
    """The Scope a page's query string asks for (the names are in this module's docstring)."""
    product = product_unit(data, query)
    return Scope(
        filters=recordfilters.resolved(data, labels.narrowed(data, parse(query), product)),
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
    "year": "date_trunc('year', {})",
    "month": "date_trunc('month', {})",
    "week": "date_trunc('week', {})",
    "day": "{}",
}
# what a timeline counts by: the day its group was first received, or with `by=event` the day the
# event began as the event date filter reads it, FDA's full dates only, so each case counted there
# is one `event_from` and `event_to` can pick
TIMELINE_BY = {"received": "c.group_first_dt_T", "event": "c.event_dt_T"}


def timeline(data: Data, query: Query) -> dict:
    """Cases by the period FDA first received them, at the grain asked for; with `by=event`, by
    the period the event began, a case with no full event date undated."""
    sql, params = scope(data, query).where()
    grain = value_of(query, "grain", "year")
    grain = grain if grain in GRAINS else "year"
    by = value_of(query, "by", "received")
    if by not in TIMELINE_BY:
        raise Problem(400, f"Count the timeline by {' or '.join(TIMELINE_BY)}.")
    period = GRAINS[grain].format(TIMELINE_BY[by])
    got = data.rows(
        f"SELECT CAST({period} AS DATE) AS k, count(*) AS n FROM explorer_case_T c "
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
            f"SELECT year(c.{received_day()}) AS k, count(*) AS n FROM explorer_case_T c WHERE "
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
        f"SELECT o AS k, count(*) AS n FROM (SELECT unnest({OUTCOMES_GIVEN}) AS o "
        f"FROM explorer_case_T c WHERE {sql}) GROUP BY 1 ORDER BY 2 DESC, 1",
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
        # ordered, so the same question gives the same answer
        f"SELECT c.era_T AS k, count(*) AS n FROM explorer_case_T c WHERE {sql} "
        "GROUP BY 1 ORDER BY 2 DESC, 1",
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
    result["reactions"] = [
        [data.pt_name(k), n, cases_query(query, event=[k])] for k, n in result["reactions"]
    ]
    # the companies that sent the most cases with the direct reports' bar, most first, then
    # Not given
    senders = result["sender"]
    companies = [r for r in senders if r[0] not in (None, DIRECT)]
    shown = companies[: list_length("companies_charted")] + [r for r in senders if r[0] == DIRECT]
    result["sender"] = sorted(shown, key=lambda r: -r[1]) + [r for r in senders if r[0] is None]
    if "drugs" in result:
        result["drugs"] = [
            [k, n, drugs.title(k), cases_query(query, "drole", dprod=[k])]
            for k, n in result["drugs"]
        ]
    return _bars_queried(result, asked.filters, query)


# the filter each chart's bar sets: its cases are the question's with the bar's value as the filter
BAR_FILTERS = {
    "sex": "sex",
    "age": "age",
    "reporter": "reporter",
    "country": "country",
    "sender": "sender",
    "outcome": "outcome",
    "soc": "soc",
}
ERA_NAMES = {t: e for e, t in ERA_T.items()}


def days_query(first: date, last: date, filters: Filters, query: Query, *left_out: str) -> str:
    """The question narrowed to the received days from `first` to `last` that it takes in (rule
    received-day), less the names `left_out`: answers.cases_query."""
    first = max(first, filters.received_from or date.min)
    last = min(last, filters.received_to or date.max)
    return cases_query(
        query, *left_out, received_from=[first.isoformat()], received_to=[last.isoformat()]
    )


def _year_query(year: int | None, filters: Filters, query: Query) -> str | None:
    """The question narrowed to the received days of `year` it takes in; None for the cases with
    no full date, which no filter picks."""
    if year is None:
        return None
    return days_query(date(year, 1, 1), date(year, 12, 31), filters, query)


def _bars_queried(result: dict[str, Any], filters: Filters, query: Query) -> dict[str, Any]:
    """The count line's and each chart's bar with, last, the /api/cases question that lists its
    cases (`cases_query`)."""
    result["cases_query"] = cases_query(query)
    for chart, name in BAR_FILTERS.items():
        if chart in result:
            result[chart] = [
                [k, n, cases_query(query, **{name: [NOT_GIVEN if k is None else k]})]
                for k, n in result[chart]
            ]
    result["era"] = [[k, n, cases_query(query, era=[ERA_NAMES[k]])] for k, n in result["era"]]
    result["years"] = [[y, n, _year_query(y, filters, query)] for y, n in result["years"]]
    return result


# the filtered export --------------------------------------------------------------------------


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
    "days_query",
    "export_size",
    "list_length",
    "product_unit",
    "scope",
    "summary",
    "tidy",
    "timeline",
    "value_of",
]
