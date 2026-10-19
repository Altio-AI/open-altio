"""WHO's drug classes in the explorer: the class filter, the classes it offers, the breakdown on
All cases' Overview, and each drug record's class on the case list and in a case. All of it
reads the release's classes layer through the explorer database (CLASS_TABLES in
src/open_altio/faers/explorer_db.py). A release built without the layer, or a viewer the access
hook does not show it to, has no classes: the filter is not offered and nothing else changes.

Query parameters, beside explore.py's:

    atc     a class at any level, by its code (repeated): a case counts when a drug record in a
            counted role has that class or one under it. A record whose class is a broader one
            (a class its possible codes share, or a class-level code) counts when that class is
            at or under the chosen one.
    atc_out a class under a chosen one left out of it (repeated): the chosen class counts its
            records less those at or under this one. A class chosen under a left-out one
            counts again, so a record counts when the nearest chosen or left-out class at or
            above its class is a chosen one.
    arole   the roles counted, FDA's codes (repeated); rule explorer-drug-counts' default roles
            when none are named
    could   1: also the records that could be the chosen class: those whose class is not one
            exact code and whose possible codes hold it

Counts are of cases, never of drug records. Each record has one class, the most exact one the
release knows; its other possible codes show only in the case window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from open_altio.faers.explorer_db import CLASS_TABLES

from . import drugs
from .answers import Problem
from .classnames import abbreviations, shown
from .found import found_order, found_order_sql

if TYPE_CHECKING:
    from .explore import Data, Query

# The length of an ATC code at each level, 1 to 5.
LENGTHS = (1, 3, 4, 5, 7)
NOT_HELD = "This release holds no drug classes."
NOT_OPEN = "WHO's drug classes are not open to you here."


@dataclass(frozen=True)
class Layer:
    """A release's drug classes: the year of WHO's index they come from and WHO's citation, to
    show wherever a class is shown."""

    index_year: int
    citation: str

    def words(self) -> dict[str, Any]:
        return {"index_year": self.index_year, "citation": self.citation}


def layer_of(manifest: dict) -> Layer | None:
    """The classes a release's manifest says it carries, when its explorer database has them."""
    entry = manifest.get("classes") or {}
    built = (manifest.get("explorer") or {}).get("tables") or {}
    if not entry.get("present") or not all(t in built for t in CLASS_TABLES):
        return None
    return Layer(int(entry["index_year"]), str(entry["citation"]))


def _marks(values: tuple | list) -> str:
    return ", ".join("?" for _ in values)


def roles_of(query: Query) -> tuple[str, ...]:
    """The roles the class filter counts."""
    try:
        return drugs.chosen_roles(query.get("arole", []))
    except ValueError as exc:
        raise Problem(400, str(exc)) from None


def level_of(code: str) -> int:
    return LENGTHS.index(len(code)) + 1 if len(code) in LENGTHS else 0


@dataclass(frozen=True)
class Choice:
    """The classes chosen in the filter, the classes under them left out, the roles it counts,
    and whether the records that could be one of them count too."""

    codes: tuple[str, ...]
    roles: tuple[str, ...]
    could: bool = False
    out: tuple[str, ...] = ()

    def _matched(self, column: str, *, broader: bool) -> tuple[str, list]:
        each, params = [], []
        for code in self.codes:
            under = [o for o in self.out if o.startswith(code) and o != code]
            less = "".join(f" AND NOT starts_with({column}, ?)" for _ in under)
            each.append(f"(starts_with({column}, ?){less})")
            params += [code, *under]
        if broader:  # a possible code that is itself a class above the chosen one
            each += [f"starts_with(?, {column})" for _ in self.codes]
            params += list(self.codes)
        return "(" + " OR ".join(each) + ")", params

    def counted(self) -> tuple[str, list]:
        """The cases with a record whose class is a chosen one or under it."""
        match, params = self._matched("atc_code_T", broader=False)
        return (
            "SELECT case_id_T FROM explorer_atc_term_T "
            f"WHERE role_T IN ({_marks(self.roles)}) AND {match}",
            list(self.roles) + params,
        )

    def could_be(self) -> tuple[str, list]:
        """The cases with a record that could be a chosen class: its class is not one exact code,
        and one of its possible codes is a chosen class, under one, or a class above one."""
        match, params = self._matched("atc_code_T", broader=True)
        return (
            "SELECT case_id_T FROM explorer_atc_could_T "
            f"WHERE role_T IN ({_marks(self.roles)}) AND {match}",
            list(self.roles) + params,
        )

    def cases(self) -> tuple[str, list]:
        """A query for the case ids the filter keeps, and its parameters."""
        sql, params = self.counted()
        if self.could:
            more, more_params = self.could_be()
            sql, params = f"{sql} UNION ALL {more}", params + more_params
        return sql, params

    def described(self, names: dict[str, str]) -> str:
        """The filter in plain words, for an export's manifest and the log."""

        def named(codes: tuple[str, ...]) -> str:
            return ", ".join(f"{c} {names[c]}" if c in names else c for c in codes)

        less = f", leaving out {named(self.out)}" if self.out else ""
        words = f"{named(self.codes)}{less}, as {drugs.roles_words(self.roles)}"
        return words + (", and the drugs that could be in it" if self.could else "")

    def manifest(self) -> dict:
        return {
            "classes": list(self.codes),
            "left_out": list(self.out),
            "roles": list(self.roles),
            "could": self.could,
        }


def choice_of(data: Data, query: Query) -> Choice | None:
    """The class filter a query names, or None; refused when this viewer has no classes, or
    when a class left out is under no chosen one."""

    def named(name: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(c.strip().upper() for c in query.get(name, []) if c.strip()))

    codes, out = named("atc"), named("atc_out")
    if not codes and not out:
        return None
    data.need_classes()
    for code in out:
        if not any(code.startswith(c) and code != c for c in codes):
            raise Problem(400, f"{code} is left out of a class, but no class above it is chosen.")
    return Choice(codes, roles_of(query), (query.get("could") or [""])[0] == "1", out)


def names_of(data: Data, codes: list[str]) -> dict[str, str]:
    """WHO's name for each code the release holds."""
    rows = data.rows(
        "SELECT atc_code_T AS k, atc_name_T AS n FROM explorer_atc_class_T "
        "WHERE list_contains(?::VARCHAR[], atc_code_T)",
        [codes],
    )
    return {r["k"]: r["n"] for r in rows}


def shown_names(data: Data, codes: list[str]) -> dict[str, str]:
    """names_of, as a screen reads them."""
    abbr = abbreviations(data.opened)
    return {c: shown(n, abbr) or n for c, n in names_of(data, codes).items()}


def _shown_rows(data: Data, rows: list[dict]) -> list[dict]:
    abbr = abbreviations(data.opened)
    return [r | {"name": shown(r["name"], abbr)} for r in rows]


# the classes the filter offers ----------------------------------------------------------------

_MORE = (
    "EXISTS (SELECT 1 FROM explorer_atc_class_T b WHERE b.atc_level_T = a.atc_level_T + 1 "
    "AND starts_with(b.atc_code_T, a.atc_code_T)) AS more"
)
_LISTED = f"SELECT a.atc_code_T AS code, a.atc_name_T AS name, a.atc_level_T AS level, {_MORE}"


def cases_of(
    data: Data, codes: list[str], roles: tuple[str, ...], where: tuple[str, list]
) -> dict[str, int]:
    """Cases with a record in `roles` whose class is each code or under it, under `where`."""
    every = data.facts.remember(
        f"class_cases|{roles}|{where[0]}|{where[1]}", lambda: _every_count(data, roles, where)
    )
    return {c: every[c] for c in codes if c in every}


def _every_count(data: Data, roles: tuple[str, ...], where: tuple[str, list]) -> dict[str, int]:
    """cases_of for every class at once, read in one pass over the records' classes, so each
    search in the filter after the first reads them from memory."""
    sql, params = where
    prefixes = ", ".join(f"left(atc_code_T, {n})" for n in LENGTHS)
    rows = data.rows(
        f"SELECT k, count(DISTINCT case_id_T) AS n FROM (SELECT case_id_T, unnest([{prefixes}]) "
        f"AS k FROM explorer_atc_term_T WHERE role_T IN ({_marks(roles)}) AND case_id_T IN "
        f"(SELECT c.case_id_T FROM explorer_case_T c WHERE {sql})) GROUP BY 1",
        [*roles, *params],
    )
    return {r["k"]: r["n"] for r in rows}


def held_at(data: Data) -> frozenset[str]:
    """The classes some record is classed at itself, in any role and any case: a substance's code,
    or a broader class (one its codes share, or a group's, as a report naming only an ACE
    inhibitor has). A class above that holds records of its own is more than the classes under
    it, so the page never takes them all ticked for it."""
    return data.facts.once(
        "class_held_at",
        lambda: frozenset(
            r["k"] for r in data.rows("SELECT DISTINCT atc_code_T AS k FROM explorer_atc_term_T")
        ),
    )


def _found(data: Data, q: str, limit: int) -> list[dict]:
    """The classes whose code starts with what was typed or whose name holds it, and the
    classes above them, so the page can draw them as a tree: the class whose code or name is
    what was typed first, then those starting with it, then the rest, each by level and code; a
    class above others comes where the first of them does."""
    typed = q.lower()
    first, first_params = found_order_sql(typed, "lower(a.atc_code_T)", "lower(a.atc_name_T)")
    hits = data.rows(
        f"{_LISTED} FROM explorer_atc_class_T a WHERE starts_with(a.atc_code_T, upper(?)) "
        "OR contains(lower(a.atc_name_T), lower(?)) "
        f"ORDER BY {first}, a.atc_level_T, a.atc_code_T LIMIT ?",
        [q, q, *first_params, limit],
    )
    above = sorted({h["code"][:n] for h in hits for n in LENGTHS if n < len(h["code"])})
    known = {h["code"] for h in hits}
    rows = data.rows(
        f"{_LISTED} FROM explorer_atc_class_T a WHERE list_contains(?::VARCHAR[], a.atc_code_T)",
        [[c for c in above if c not in known]],
    )
    at: dict[str, int] = {}  # each class's place: the first of the classes found at or under it
    for h in hits:
        place = found_order(typed, h["code"].lower(), (h["name"] or "").lower()) or 0
        for code in {h["code"][:n] for n in LENGTHS} | {h["code"]}:
            at[code] = min(at.get(code, place), place)
    listed = [h | {"hit": True} for h in hits] + [r | {"hit": False} for r in rows]
    return sorted(listed, key=lambda r: (at[r["code"]], r["level"], r["code"]))


def listing(data: Data, query: Query, where: tuple[str, list], *, limit: int) -> dict[str, Any]:
    """What the filter offers: the classes under `parent` (the main groups when none), or those
    found by `q` and the classes above them; the chosen classes and those left out of them; each
    with its cases in the counted roles under every other filter (`where`) and whether records
    are classed at it itself (`own`, held_at); and the cases the "could be" tick adds."""
    layer = data.need_classes()
    roles = roles_of(query)
    q = " ".join((query.get("q") or [""])[0].split())
    parent = (query.get("parent") or [""])[0].strip().upper()
    if q:
        listed = _shown_rows(data, _found(data, q, limit))
    else:
        listed = data.rows(
            f"{_LISTED} FROM explorer_atc_class_T a WHERE a.atc_level_T = ? "
            "AND starts_with(a.atc_code_T, ?) ORDER BY a.atc_code_T",
            [level_of(parent) + 1, parent],
        )
        listed = [r | {"hit": True} for r in _shown_rows(data, listed)]
    chosen = choice_of(data, query)
    picked = list(chosen.codes) if chosen else []
    out = list(chosen.out) if chosen else []
    counts = cases_of(data, [r["code"] for r in listed] + picked + out, roles, where)
    names = shown_names(data, picked + out)
    own = held_at(data)

    def named(c: str) -> dict:
        level, cases = level_of(c), counts.get(c, 0)
        return {"code": c, "name": names.get(c), "level": level, "cases": cases, "own": c in own}

    could = None
    if chosen:
        more, more_params = chosen.could_be()
        held, held_params = chosen.counted()
        sql, params = where
        could = data.rows(
            f"SELECT count(*) AS n FROM explorer_case_T c WHERE {sql} AND c.case_id_T IN ({more}) "
            f"AND c.case_id_T NOT IN ({held})",
            params + more_params + held_params,
        )[0]["n"]
    return {
        **layer.words(),
        "q": q,
        "parent": parent,
        "classes": [
            r | {"cases": counts.get(r["code"], 0), "own": r["code"] in own} for r in listed
        ],
        "chosen": [named(c) for c in picked],
        "left_out": [named(c) for c in out],
        "could": could,
    }


# the breakdown on All cases' Overview ---------------------------------------------------------


def breakdown_parent(chosen: Choice | None) -> str:
    """The class the breakdown splits: the one chosen class, when it has classes under it; the
    main groups otherwise."""
    if chosen and len(chosen.codes) == 1 and len(chosen.codes[0]) < LENGTHS[-1]:
        return chosen.codes[0]
    return ""


def breakdown_jobs(
    parent: str, roles: tuple[str, ...], where: tuple[str, list], limit: int
) -> dict[str, tuple[str, list]]:
    """The queries of the breakdown: cases by the class one level under `parent` of their records
    in `roles`, and the cases with a record that could be several of them, counted once."""
    n = LENGTHS[level_of(parent)]
    sql, params = where
    picked = f"(SELECT c.case_id_T FROM explorer_case_T c WHERE {sql})"
    return {
        "class_rows": (
            f"SELECT b.k, coalesce(k.atc_name_T, b.k) AS name, b.n FROM ("
            f"SELECT left(atc_code_T, {n}) AS k, count(DISTINCT case_id_T) AS n "
            f"FROM explorer_atc_term_T WHERE role_T IN ({_marks(roles)}) "
            f"AND starts_with(atc_code_T, ?) AND length(atc_code_T) >= {n} "
            f"AND case_id_T IN {picked} GROUP BY 1) b "
            "LEFT JOIN explorer_atc_class_T k ON k.atc_code_T = b.k ORDER BY b.n DESC, b.k LIMIT ?",
            list(roles) + [parent] + params + [limit],
        ),
        "class_several": (
            "SELECT count(DISTINCT case_id_T) AS n FROM explorer_atc_could_T "
            f"WHERE role_T IN ({_marks(roles)}) AND starts_with(atc_code_T, ?) "
            f"AND (atc_class_T IS NULL OR length(atc_class_T) < {n}) AND case_id_T IN {picked}",
            list(roles) + [parent] + params,
        ),
    }


def coverage_job(roles: tuple[str, ...], where: tuple[str, list]) -> tuple[str, list]:
    """The cases under `where`, and how many of them have a record in `roles` with a class chosen
    or one it could be."""
    sql, params = where
    return (
        "SELECT count(*) AS n, count(*) FILTER (WHERE c.case_id_T IN ("
        f"SELECT case_id_T FROM explorer_atc_term_T WHERE role_T IN ({_marks(roles)}) UNION "
        f"SELECT case_id_T FROM explorer_atc_could_T WHERE role_T IN ({_marks(roles)}))) AS g "
        f"FROM explorer_case_T c WHERE {sql}",
        list(roles) * 2 + params,
    )


def breakdown(data: Data, parent: str, roles: tuple[str, ...], out: dict) -> dict:
    """The breakdown, from the answers of breakdown_jobs (taken out of `out`)."""
    rows = out.pop("class_rows")
    abbr = abbreviations(data.opened)
    shown_rows = [shown(r["name"], abbr) for r in rows]
    return {
        "parent": parent,
        "parent_name": shown_names(data, [parent]).get(parent) if parent else None,
        "roles": list(roles),
        "rows": [[r["k"], n, r["n"]] for r, n in zip(rows, shown_rows, strict=True)],
        "several": out.pop("class_several")[0]["n"],
    }


# each record's class ---------------------------------------------------------------------------

# A code's name as a record shows it: a substance code by the class it sits in (B01AC06 by
# "Platelet aggregation inhibitors excl. heparin"), any other by its own.
_SHOWN = "coalesce(g.atc_name_T, k.atc_name_T)"
_GROUP = (
    "LEFT JOIN explorer_atc_class_T g ON k.atc_level_T = 5 AND g.atc_code_T = left(k.atc_code_T, 5)"
)
_OF_RECORD = f"LEFT JOIN explorer_atc_class_T k ON k.atc_code_T = a.atc_code_T {_GROUP}"


def on_list(data: Data, ids: list[int]) -> dict[tuple[int, str], list]:
    """Each record's one class on the case list: [code, name, broader], by (case id, drug_seq)."""
    rows = data.rows(
        f"SELECT a.case_id_T, a.drug_seq, a.atc_code_T, a.atc_level_T, {_SHOWN} AS name "
        f"FROM explorer_atc_drug_T a {_OF_RECORD} "
        f"WHERE a.case_id_T IN ({_marks(ids)}) AND a.atc_code_T IS NOT NULL",
        ids,
    )
    abbr = abbreviations(data.opened)
    return {
        (r["case_id_T"], r["drug_seq"]): [
            r["atc_code_T"],
            shown(r["name"], abbr),
            r["atc_level_T"] < 5,
        ]
        for r in rows
    }


def _split(code: str, record: dict) -> str:
    """The class a possible code names a record by: the one just under the record's broader
    class, where its possible codes part (the substance under a shared level 4 class); under
    none, the class the code sits in."""
    if record["code"] and record["level"] < 5:
        return code[: LENGTHS[record["level"]]]
    return code[: LENGTHS[3]] if len(code) > LENGTHS[3] else code


def in_case(data: Data, case_id: int) -> list[dict]:
    """Each record's class in a case: its code and name (None when it can't tell), whether it is
    a broader class, how it was chosen, and its possible codes, each named by the class where
    they part."""
    records = data.rows(
        f"SELECT a.drug_seq, a.atc_code_T AS code, a.atc_level_T AS level, {_SHOWN} AS name, "
        "a.atc_chosen_by_T AS chosen_by, a.atc_codes_T AS codes "
        f"FROM explorer_atc_drug_T a {_OF_RECORD} WHERE a.case_id_T = ?",
        [case_id],
    )
    splits = sorted({_split(c, r) for r in records for c in r["codes"] or []})
    named = shown_names(data, splits)
    abbr = abbreviations(data.opened)
    return [
        {
            "drug_seq": r["drug_seq"],
            "code": r["code"],
            "name": shown(r["name"], abbr) if r["code"] else None,
            "broader": r["code"] is not None and r["level"] < 5,
            "chosen_by": r["chosen_by"],
            "possible": [[c, named.get(_split(c, r))] for c in r["codes"] or []],
        }
        for r in records
    ]


__all__ = [
    "LENGTHS",
    "NOT_HELD",
    "NOT_OPEN",
    "Choice",
    "Layer",
    "breakdown",
    "breakdown_jobs",
    "cases_of",
    "breakdown_parent",
    "choice_of",
    "held_at",
    "layer_of",
    "level_of",
    "listing",
    "names_of",
    "in_case",
    "on_list",
    "roles_of",
]
