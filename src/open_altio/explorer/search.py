"""Finding drugs and reactions: what the search boxes offer as a person types, each with its
cases under the page's other filters, and the spellings a product page counts. Lower-level terms
and SMQs only for a viewer who may see MedDRA's licensed part. How a drug counts is drugs.py's."""

from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import replace

from open_altio.faers.drugnames.dictionary import SEPARATOR
from open_altio.faers.explorer_db import drug_term

from . import classes, drugs
from .answers import Problem
from .explore import Data, Query, list_length, product_unit, scope, tidy, value_of
from .found import found_order


def _found(data: Data, q: str) -> list[dict]:
    """Drugs whose name or a spelling they are reported under holds what was typed: one named
    so first, then those starting with it, then the rest, most cases first within each."""
    most = list_length("products_found")
    found: list[list[dict]] = [[], [], []]
    for d, names in _searched(data):
        at = found_order(q, *names)
        if at is not None:
            found[at].append(d)
    return [d for group in found for d in group][:most]


def _searched(data: Data) -> list[tuple[dict, list[str]]]:
    """Each drug with the names a search reads, in lower case: its own, its title and the
    spellings it is reported under most; made once."""
    return data.facts.once(
        "drug_names_searched",
        lambda: [
            (d, [d["name"], d["title"].lower()] + [n.lower() for n in d["reported"]])
            for d in data.facts.drugs
        ],
    )


def _roles_sql(roles: tuple[str, ...]) -> str:
    return f"role_T IN ({', '.join('?' for _ in roles)})"


def _spellings(data: Data, roles: tuple[str, ...], sql: str, params: list) -> dict[str, int]:
    """FDA's spellings with no ingredient that have cases in these roles under the filters `sql`
    names, with their cases, read once and kept, so each search reads them from memory."""

    def made() -> dict[str, int]:
        return {
            r["k"]: r["n"]
            for r in data.rows(
                "SELECT spelling_T AS k, count(DISTINCT case_id_T) AS n FROM "
                f"explorer_no_ingredient_T WHERE {_roles_sql(roles)} AND case_id_T IN "
                f"(SELECT c.case_id_T FROM explorer_case_T c WHERE {sql}) GROUP BY 1",
                list(roles) + params,
            )
        }

    return data.facts.remember(f"spellings|{roles}|{sql}|{params}", made)


def _every_spelling(data: Data) -> list[str]:
    """Every one of FDA's spellings with no ingredient, with cases or none, in alphabetical
    order, so those starting with what was typed are found by bisection."""
    return data.facts.once(
        "spellings_with_no_ingredient",
        lambda: sorted(
            r["k"]
            for r in data.rows(
                "SELECT DISTINCT spelling_T AS k FROM explorer_no_ingredient_T "
                "WHERE spelling_T IS NOT NULL"
            )
        ),
    )


def _by_cases(data: Data, roles: tuple[str, ...], sql: str, params: list) -> list[str]:
    """Every spelling with no ingredient, most cases first under these filters, then by name."""
    cases = _spellings(data, roles, sql, params)

    def made() -> list[str]:
        return sorted(cases, key=lambda k: (-cases[k], k)) + [
            k for k in _every_spelling(data) if k not in cases
        ]

    return data.facts.remember(f"spellings_by_cases|{roles}|{sql}|{params}", made)


def _unmapped(data: Data, typed: str, roles: tuple[str, ...], sql: str, params: list) -> list:
    """FDA's spellings with no ingredient that hold what was typed, with their cases in these
    roles under the filters `sql` names: the one typed first, then those starting with it, then
    the rest, most cases first within each."""
    most = list_length("unmapped_found")
    cases, every = _spellings(data, roles, sql, params), _every_spelling(data)
    ordered = _by_cases(data, roles, sql, params)
    if not typed:
        return [[k, cases.get(k, 0)] for k in ordered[:most]]
    at = bisect.bisect_left(every, typed)
    named = [typed] if at < len(every) and every[at] == typed else []
    after = bisect.bisect_left(every, typed[:-1] + chr(ord(typed[-1]) + 1))
    starting = sorted(every[at + len(named) : after], key=lambda k: (-cases.get(k, 0), k))
    found = (named + starting)[:most]
    for k in ordered:  # the rest holding it, most cases first, until the list is full
        if len(found) >= most:
            break
        if typed in k and not k.startswith(typed):
            found.append(k)
    return [[k, cases.get(k, 0)] for k in found]


def _spelled(
    data: Data, names: list[str], roles: tuple[str, ...], sql: str, params: list
) -> dict[str, int]:
    """Cases of each of FDA's spellings with no ingredient, in these roles under the filters."""
    if not names:
        return {}
    cases, every = _spellings(data, roles, sql, params), _every_spelling(data)

    def held(k: str) -> bool:
        at = bisect.bisect_left(every, k)
        return at < len(every) and every[at] == k

    return {k: cases.get(k, 0) for k in names if held(k)}


def products(data: Data, query: Query) -> dict:
    """Drugs found by their name or a spelling they are reported under, and FDA's spellings with
    no ingredient that hold what was typed and have cases; the drugs with the most cases when
    nothing is."""
    q = tidy(value_of(query, "q")).lower()
    if not q:
        return {"q": "", "drugs": data.facts.drugs[: list_length("products_found")], "unmapped": []}
    typed = drug_term(q) or ""
    kept = "c.dup_kept_T"
    return {
        "q": q,
        "drugs": _found(data, q),
        "unmapped": [u for u in _unmapped(data, typed, drugs.default_roles(), kept, []) if u[1]],
    }


def product(data: Data, name: str) -> dict | None:
    """What a product page opens for a name: its drug with its ingredients, or FDA's spelling
    with no ingredient, with its cases as a page opens and how many spellings it has."""
    found = data.facts.name_of(name)
    if found is None:
        return None
    kind, key = found
    if kind == "ingredient":
        return data.facts.drug_named[key] | {
            "kind": kind,
            "about": drugs.about(key),
            "ingredients": key.split(SEPARATOR),
        }
    cases = _spelled(data, [key], drugs.default_roles(), "c.dup_kept_T", [])
    return {
        "name": key,
        "title": key,
        "kind": kind,
        "about": "FDA's spelling with no ingredient",
        "ingredients": [],
        "cases": cases.get(key, 0),
        "reported": [],
        "spellings": {"any": 1, "exact": 1},
    }


def _drug_counts(
    data: Data, names: list[str], roles: tuple[str, ...], sql: str, params: list
) -> dict[str, int]:
    """Cases of each drug, as the Drugs filter counts it, under the filters `sql` names."""
    held = (
        "i.substance_T = u.unit_T"
        if drugs.default_unit() == "exact"
        else f"list_has_all(string_split(i.substance_T, '{SEPARATOR}'), "
        f"string_split(u.unit_T, '{SEPARATOR}'))"
    )
    return {
        r["k"]: r["n"]
        for r in data.rows(
            "WITH u AS (SELECT unnest(?::VARCHAR[]) AS unit_T) "
            "SELECT u.unit_T AS k, count(DISTINCT i.case_id_T) AS n FROM u JOIN "
            f"explorer_ingredient_T i ON i.ingredient_T = split_part(u.unit_T, '{SEPARATOR}', 1) "
            f"AND {held} WHERE i.{_roles_sql(roles)} AND i.case_id_T IN (SELECT c.case_id_T "
            f"FROM explorer_case_T c WHERE {sql}) GROUP BY 1",
            [names] + list(roles) + params,
        )
    }


def drug_search(data: Data, query: Query) -> dict:
    """Drugs found by what was typed, and FDA's spellings with no ingredient, with their cases
    in the roles `drole` names under the other filters (not the drugs)."""
    q = tidy(value_of(query, "q"))
    found = products(data, {"q": [q]}) if q else {"drugs": [], "unmapped": []}
    asked = scope(data, query)
    try:
        roles = drugs.chosen_roles(query.get("drole", []))
    except ValueError as exc:
        raise Problem(400, str(exc)) from None
    names = [d["name"] for d in found["drugs"]]
    unmapped = found["unmapped"]
    if (
        roles != drugs.default_roles()
        or asked.terms
        or asked.product
        or not asked.filters.is_default
    ):
        sql, params = replace(asked, drugs=[]).where()
        counts = _drug_counts(data, names, roles, sql, params) if names else {}
        unmapped = _unmapped(data, drug_term(q) or "", roles, sql, params) if q else []
    else:
        counts = data.facts.drug_cases
    return {
        "q": q.lower(),
        "drugs": [d | {"cases": counts.get(d["name"], 0)} for d in found["drugs"]],
        "unmapped": unmapped,
    }


def spellings(data: Data, query: Query) -> dict:
    """The spellings a product page counts, each with its cases in the page's roles under its
    other filters: its drug's spellings in the unit chosen (most cases first, as many as rule
    explorer-lists shows, or those holding what was typed), those left out, FDA's spellings with
    no ingredient added and, as a person types, those holding what was typed."""
    unit = product_unit(data, query)
    if unit is None:
        raise Problem(400, "Name the product.")
    sql, params = replace(scope(data, query), product=None, drugs=[]).where()
    typed = drug_term(value_of(query, "q")) or ""
    own: list[list] = []
    if unit.substance:
        match, matched = drugs.Unit(unit.substance, unit.roles, unit.exact).match()
        own = data.facts.remember(  # read once for the page, then each letter typed reads it
            f"own_spellings|{unit.substance}|{unit.roles}|{unit.exact}|{sql}|{params}",
            lambda: [
                [r["k"], r["n"]]
                for r in data.rows(
                    "SELECT spelling_T AS k, count(DISTINCT case_id_T) FILTER (WHERE "
                    f"{_roles_sql(unit.roles)} AND case_id_T IN (SELECT c.case_id_T FROM "
                    f"explorer_case_T c WHERE {sql})) AS n FROM explorer_ingredient_T WHERE "
                    f"{match} AND spelling_T IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1",
                    list(unit.roles) + params + matched,
                )
            ],
        )
    added = list(unit.included)
    spelled = _spelled(data, added, unit.roles, sql, params)
    if unit.substance is None:  # a page of FDA's spelling with no ingredient: that one is its own
        own, added = [[added[0], spelled.get(added[0], 0)]], added[1:]
    shown = own
    if typed:  # the spelling typed first, then those starting with it, then the rest
        held = [s for s in own if typed in s[0]]
        shown = sorted(held, key=lambda s: found_order(typed, s[0]) or 0)
    found = _unmapped(data, typed, unit.roles, sql, params) if typed else []
    by_name = dict(own)
    return {
        "q": value_of(query, "q").strip().lower(),
        "total": len(own),
        "spellings": shown[: list_length("spellings_shown")],
        "excluded": [[k, by_name.get(k, 0)] for k in unit.excluded],
        "included": [[k, spelled.get(k, 0)] for k in added],
        "unmapped": [s for s in found if s[0] not in unit.included],
    }


def counts_for(data: Data, terms: list[str], query: Query) -> dict:
    """Cases for these reactions (keys, reactions.py) under the other filters, not the
    reactions."""
    asked = scope(data, {k: v for k, v in query.items() if k not in ("pt", "smq", "pt_out")})
    if not terms:
        return {}
    if not asked.product and not asked.drugs and asked.filters.is_default:
        return {k: data.reactions.counts.get(k, 0) for k in terms}
    sql, params = asked.where()
    reacs, reac_params = data.reactions.keyed(terms)
    return {
        r["k"]: r["n"]
        for r in data.rows(
            f"SELECT r.k, count(DISTINCT r.case_id_T) AS n FROM {reacs} r WHERE r.case_id_T IN "
            f"(SELECT c.case_id_T FROM explorer_case_T c WHERE {sql}) GROUP BY 1",
            reac_params + params,
        )
    }


def term_search(data: Data, query: Query) -> dict:
    """What was typed, found among the reactions in the release (with MedDRA, their current
    PTs), the lower-level terms coded to one of them, and SMQs, with each kind's total.
    `kind` narrows to one kind and lists more of it; SMQs can be listed without
    typing. Counts are cases under the other filters (not the reactions).
    Lower-level terms and SMQs only for a viewer who may see MedDRA's licensed
    part (`meddra=1` asks for them)."""
    q = tidy(value_of(query, "q")).lower()
    kind = value_of(query, "kind", "all")
    meddra = data.meddra if value_of(query, "meddra") == "1" else None
    one_kind = kind != "all"
    pt_counts = data.reactions.counts
    terms, llts, smqs = [], [], []
    totals = {"pt": 0, "llt": 0, "smq": 0}
    if q and kind in ("all", "pt"):
        # the term typed first, then those starting with it, then the rest, most cases first
        found = sorted(
            (k for k in pt_counts if q in k), key=lambda k: (found_order(q, k), -pt_counts[k], k)
        )
        totals["pt"] = len(found)
        found = found[: list_length("terms_found_one_kind" if one_kind else "terms_found")]
        counts = counts_for(data, found, query)
        found.sort(key=lambda k: (found_order(q, k), -counts.get(k, 0), data.pt_name(k)))
        terms = [[data.pt_name(k), counts.get(k, 0)] for k in found]
    if meddra is not None and q and kind in ("all", "llt"):
        # a lower-level term finds the preferred term it is coded to: FAERS publishes only PTs
        hits = [x for x in meddra.llts() if q in x[0].lower() and x[1] in pt_counts]
        hits.sort(key=lambda x: (found_order(q, x[0].lower()), not x[2], -pt_counts[x[1]], x[0]))
        totals["llt"] = len(hits)
        hits = hits[: list_length("llts_found_one_kind" if one_kind else "llts_found")]
        llt_counts = counts_for(data, sorted({x[1] for x in hits}), query)
        llts = [[x[0], data.pt_name(x[1]), llt_counts.get(x[1], 0), x[2], x[3]] for x in hits]
    if meddra is not None and kind in ("all", "smq") and (q or kind == "smq"):
        for code, s in sorted(meddra.smqs().items(), key=lambda kv: kv[1]["name"].lower()):
            if not q or q in s["name"].lower():
                smqs.append([code, s["name"], len(s["narrow"]), len(s["broad"])])
        smqs.sort(key=lambda x: found_order(q, x[1].lower()) or 0)  # by name within each
        totals["smq"] = len(smqs)
        smqs = smqs[: list_length("smqs_found_one_kind" if one_kind else "smqs_found")]
    return {"q": q, "kind": kind, "terms": terms, "llts": llts, "smqs": smqs, "totals": totals}


def smq_terms(data: Data, query: Query) -> dict:
    """An SMQ's preferred terms, narrow first, each with its cases under the other filters."""
    code = value_of(query, "code")
    q = data.served_meddra().smqs().get(code)
    if not q:
        raise Problem(404, "not found")
    counts = counts_for(data, sorted(q["broad"]), query)
    terms = [
        [data.pt_name(t), "narrow" if t in q["narrow"] else "broad", counts.get(t, 0)]
        for t in q["broad"]
    ]
    terms.sort(key=lambda t: (t[1] != "narrow", -t[2], t[0]))
    return {"code": code, "name": q["name"], "terms": terms}


def term_counts(data: Data, query: Query) -> dict:
    """Cases for each chosen preferred term under the other filters."""
    terms = sorted({k for k in map(data.reactions.key, query.get("pt", [])) if k})
    counts = counts_for(data, terms, query)
    return {
        "terms": sorted(
            ([data.pt_name(t), counts.get(t, 0)] for t in terms), key=lambda t: (-t[1], t[0])
        )
    }


def warm(data: Data, pause: Callable[[], None]) -> None:
    """Works out what the search boxes read when no filter is set, so a person's first search
    answers at once: the drugs, the reactions' cases and MedDRA's terms and SMQs, FDA's
    spellings with no ingredient, each drug class's cases and the classes records are classed
    at; `pause` before each part."""
    pause()
    _searched(data)
    data.facts.pt_names  # noqa: B018 (made on first use)
    pause()
    data.reactions.counts  # noqa: B018
    if data.meddra is not None:
        data.meddra.llts()
        data.meddra.smqs()
    pause()
    roles = drugs.default_roles()
    _by_cases(data, roles, "c.dup_kept_T", [])  # as Find a drug asks
    _by_cases(data, roles, *replace(scope(data, {}), product=None, drugs=[]).where())
    if data.classes is not None:
        pause()
        where = replace(scope(data, {}), classes=None).where()
        classes.cases_of(data, [], classes.roles_of({}), where)
        classes.held_at(data)


__all__ = [
    "counts_for",
    "drug_search",
    "product",
    "products",
    "smq_terms",
    "spellings",
    "term_counts",
    "term_search",
    "warm",
]
