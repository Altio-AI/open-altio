"""What one drug's count is, on a product page and in All cases' Drugs filter (rule
explorer-drug-counts): the drug records of an ingredient or a combination, in any product
containing it or in that product alone, in the roles ticked, less the spellings unticked, plus
FDA's spellings with no ingredient that were added. Its SQL over the explorer's database, read
from the query string, and the words a page shows for it.

A drug is named by the release's own ingredients (rule drug-names): `valsartan`, or
`sacubitril;valsartan` for a combination. A page of FDA's spelling with no ingredient
(`VALSARTAN TEVA`) counts that spelling's records that have none.
"""

from __future__ import annotations

from dataclasses import dataclass

from open_altio.faers.drugnames.dictionary import SEPARATOR
from open_altio.rulebook import value

from .filters import ROLES

UNIT_WORDS = {"any": "Any product containing", "exact": "Exact product"}


def roles() -> list[str]:
    """FDA's role codes the tick boxes offer, in their order."""
    return list(value("explorer-drug-counts", "roles"))


def default_roles() -> tuple[str, ...]:
    return tuple(value("explorer-drug-counts", "default_roles"))


def default_unit() -> str:
    return str(value("explorer-drug-counts", "default_unit"))


def _named(name: str) -> str:
    """A drug's ingredients in words: `sacubitril;valsartan` is sacubitril and valsartan."""
    parts = name.split(SEPARATOR)
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def title(name: str) -> str:
    """How a page names a drug: Sacubitril and valsartan."""
    words = _named(name)
    return words[:1].upper() + words[1:]


def about(name: str) -> str:
    """What a drug is, under its title: an ingredient, or a combination of which."""
    return "Ingredient" if SEPARATOR not in name else f"Combination of {_named(name)}"


def roles_words(chosen: tuple[str, ...]) -> str:
    """The roles a count covers, as FDA codes them: `PS or SS`."""
    return chosen[0] if len(chosen) == 1 else f"{', '.join(chosen[:-1])} or {chosen[-1]}"


def words() -> dict:
    """What a page needs to draw the drug choices: each role with FDA's name for it, each unit,
    and which are chosen when a page opens."""
    chosen = default_roles()
    return {
        "roles": [[code, ROLES[code]] for code in roles()],
        "default_roles": list(chosen),
        "units": [[unit, UNIT_WORDS[unit]] for unit in value("explorer-drug-counts", "units")],
        "default_unit": default_unit(),
    }


def chosen_roles(values: list[str]) -> tuple[str, ...]:
    """The roles a query names, in the tick boxes' order; the default roles when it names none.
    ValueError for a code that is not one of them."""
    asked = {v.strip().upper() for v in values if v.strip()}
    if not asked:
        return default_roles()
    offered = roles()
    if asked - set(offered):
        raise ValueError(f"Drug roles are FDA's codes: {', '.join(offered)}.")
    return tuple(r for r in offered if r in asked)


def chosen_unit(text: str) -> str:
    if not text:
        return default_unit()
    if text not in UNIT_WORDS:
        raise ValueError(f"A drug counts as {' or '.join(UNIT_WORDS)}.")
    return text


@dataclass(frozen=True)
class Unit:
    """One drug as it is counted. `substance` is its ingredients as the release names them,
    or None for FDA's spellings with no ingredient alone; `excluded` are its spellings left
    out, `included` FDA's spellings with no ingredient counted with it."""

    substance: str | None
    roles: tuple[str, ...]
    exact: bool = False
    excluded: tuple[str, ...] = ()
    included: tuple[str, ...] = ()

    @property
    def parts(self) -> list[str]:
        return self.substance.split(SEPARATOR) if self.substance else []

    def match(self) -> tuple[str, list]:
        """The condition on `explorer_ingredient_T` for this drug's records in any role and
        spelling; it reads only its first ingredient's rows."""
        sql = "ingredient_T = ?"
        params: list[object] = [self.parts[0]]
        if self.exact:
            sql += " AND substance_T = ?"
            params.append(self.substance)
        elif len(self.parts) > 1:
            sql += f" AND list_has_all(string_split(substance_T, '{SEPARATOR}'), ?::VARCHAR[])"
            params.append(self.parts)
        return sql, params

    def cases(self) -> tuple[str, list]:
        """A query for the case ids of the records it counts, and its parameters."""
        marks = ", ".join("?" for _ in self.roles)
        parts: list[str] = []
        params: list[object] = []
        if self.substance:
            sql, match = self.match()
            if self.excluded:
                sql += " AND (spelling_T IS NULL OR NOT list_contains(?::VARCHAR[], spelling_T))"
                match.append(list(self.excluded))
            parts.append(
                f"SELECT case_id_T FROM explorer_ingredient_T WHERE {sql} AND role_T IN ({marks})"
            )
            params += match + list(self.roles)
        if self.included:
            spelled = ", ".join("?" for _ in self.included)
            parts.append(
                "SELECT case_id_T FROM explorer_no_ingredient_T "
                f"WHERE spelling_T IN ({spelled}) AND role_T IN ({marks})"
            )
            params += list(self.included) + list(self.roles)
        return " UNION ALL ".join(parts), params

    def described(self) -> str:
        """The drug as counted, in plain words, for an export's manifest and the log."""
        if self.substance:
            unit = UNIT_WORDS["exact" if self.exact else "any"].lower()
            words = f"{title(self.substance)}, {unit} it"
        else:
            words = f"{', '.join(self.included)}, FDA's spelling with no ingredient"
        named = [f"{r} ({ROLES[r]})" for r in self.roles]
        words += f", as {roles_words(tuple(named))}"
        if self.excluded:
            words += f"; spellings left out: {', '.join(self.excluded)}"
        if self.included and self.substance:
            words += f"; spellings with no ingredient added: {', '.join(self.included)}"
        return words

    def manifest(self) -> dict:
        """The drug as counted, for an export's manifest."""
        return {
            "drug": self.substance,
            "unit": "exact" if self.exact else "any",
            "roles": list(self.roles),
            "spellings_left_out": list(self.excluded),
            "spellings_added": list(self.included),
        }


def cases_of(units: list[Unit]) -> tuple[str, list]:
    """A query for the case ids that any of these drugs counts."""
    queries = [u.cases() for u in units]
    return " UNION ALL ".join(q for q, _ in queries), [p for _, ps in queries for p in ps]


__all__ = [
    "about",
    "UNIT_WORDS",
    "Unit",
    "cases_of",
    "chosen_roles",
    "chosen_unit",
    "default_roles",
    "default_unit",
    "roles",
    "roles_words",
    "title",
    "words",
]
