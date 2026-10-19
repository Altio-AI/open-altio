"""The reviewed route tables (rule drug-route), read and checked.

    from open_altio.faers.route.tables import RouteTables
    t = RouteTables.read()
    t.code("Intravenous drip")                       # '041', the E2B route code
    t.families("dose_form", "Film-coated tablet")    # frozenset({'by_mouth', 'vaginal'})
    t.label_families(["ORAL", "SUBLINGUAL"])         # every family a label's routes allow
    t.atc_group("041")                               # 'injection'

`families_table` gives every value FDA writes, by where it is written (`route`,
`dose_form`, a form word in the drug name `drugname`, or a route name on a
label `label`), the set of route families a drug given that way can be in; an
empty set says nothing about the route. `route_table` reads a route word as one
E2B route code (`e2b_table`), and `atc_group_table` gives a code its drug-class
group.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass

from open_altio import rulebook

RULE = "drug-route"
SOURCES = ("route", "dose_form", "drugname", "label")  # where a value is written
_SPACES = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9-]+")


class RouteTableError(ValueError):
    """A route table the build will not read, said by name."""


def key(value: str | None) -> str:
    """A value as the tables compare it: lower case, spaces collapsed, spaces and
    double quotes trimmed from both ends."""
    return _SPACES.sub(" ", (value or "").lower()).strip(' "')


# The same reading in DuckDB, for FDA's columns.
KEY_SQL = "trim(regexp_replace(lower({col}), '\\s+', ' ', 'g'), '\" ')"


def families() -> tuple[str, ...]:
    """The values of route_family_T: the families, then the unknown one."""
    return (*rulebook.value(RULE, "families"), rulebook.value(RULE, "unknown"))


def _read(name: str) -> tuple[str, list[dict[str, str]]]:
    rel = rulebook.value(RULE, name)
    with (rulebook.data_root() / rel).open(encoding="utf-8", newline="") as f:
        return rel, list(csv.DictReader(f))


def _pairs(name: str, first: str, second: str) -> dict[str, str]:
    rel, rows = _read(name)
    out: dict[str, str] = {}
    for r in rows:
        if r[first] in out:
            raise RouteTableError(f"{rel}: {r[first]!r} is listed twice")
        out[r[first]] = r[second]
    return out


def _families_table() -> dict[tuple[str, str], frozenset[str]]:
    rel, rows = _read("families_table")
    known = set(families()[:-1])
    out: dict[tuple[str, str], frozenset[str]] = {}
    bad = []
    for r in rows:
        source, value = r["source"], key(r["value"])
        fams = frozenset(f for f in r["families"].split(";") if f)
        if source not in SOURCES:
            bad.append(f"{r['value']!r} has source {source!r}, not one of {', '.join(SOURCES)}")
        elif not fams <= known:
            bad.append(f"{r['value']!r} names {sorted(fams - known)}, not families of the rule")
        elif source == "drugname" and not _WORD.fullmatch(value):
            bad.append(f"{r['value']!r} is not one word")
        elif (source, value) in out:
            bad.append(f"{source} {r['value']!r} is listed twice")
        out[(source, value)] = fams
    if bad:
        raise RouteTableError(f"{rel}: " + "; ".join(bad))
    return out


@dataclass(frozen=True)
class RouteTables:
    routes: dict[str, str]  # route word -> E2B code
    e2b: dict[str, str]  # E2B code -> E2B's name for it
    atc_groups: dict[str, str]  # E2B code -> drug-class group
    sets: dict[tuple[str, str], frozenset[str]]  # (source, value) -> its families

    @classmethod
    def read(cls) -> RouteTables:
        t = cls(
            _pairs("route_table", "route", "code"),
            _pairs("e2b_table", "code", "e2b_route"),
            _pairs("atc_group_table", "code", "group"),
            _families_table(),
        )
        bad = [
            f"route_table: {w!r} reads as {c!r}, not an E2B code"
            for w, c in t.routes.items()
            if c not in t.e2b
        ]
        bad += [
            f"route_table: {w!r} is not written as the table compares it"
            for w in t.routes
            if w != key(w)
        ]
        bad += [f"atc_group_table: {c} is not an E2B code" for c in t.atc_groups if c not in t.e2b]
        if bad:
            raise RouteTableError("rule drug-route: " + "; ".join(bad))
        return t

    def code(self, route: str | None) -> str | None:
        """The E2B code a route word (FAERS's or a label's) reads as, or None."""
        return self.routes.get(key(route))

    def atc_group(self, code: str | None) -> str | None:
        """The drug-class group of an E2B code, or None when it is in no group."""
        return self.atc_groups.get(code or "")

    def families(self, source: str, value: str | None) -> frozenset[str] | None:
        """The families a value allows: None when the table does not hold it, an empty
        set when it says nothing about the route."""
        return self.sets.get((source, key(value)))

    def label_families(self, routes: Iterable[str]) -> frozenset[str]:
        """Every family a label can be in: the union of the sets of its route names.
        A route name with no label row reads as the FAERS route word of the same name."""
        out: frozenset[str] = frozenset()
        for r in routes:
            found = self.families("label", r)
            if found is None:
                found = self.families("route", r)
            out |= found or frozenset()
        return out


def label_families(routes: Iterable[str]) -> frozenset[str]:
    """The families a label with these route names can be in (RouteTables.label_families).
    A report matches a label when their families overlap."""
    return RouteTables.read().label_families(routes)
