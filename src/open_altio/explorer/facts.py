"""What the pages need from a release that does not depend on the filters,
worked out once per release from its explorer database and kept in memory.

    facts = explorer.facts.of(opened)     # opened: the live OpenRelease
    facts.drugs                           # every ingredient and combination, most cases first
    facts.name_of("HUMIRA")               # ("ingredient", "adalimumab"): what a name opens
    facts.pt_name("NAUSEA")               # the spelling to show for a reaction term
    facts.info                            # what /api/release answers
    facts.once(name, make)                # a fact made once and kept while the release is live
    facts.remember(key, make)             # a bounded cache of answers for this release

A drug is an ingredient or a combination as the release names them (rule drug-names), counted
as rule explorer-drug-counts says when a page opens: kept cases naming it in the default roles,
in any product containing it. On FAERS 2026Q2 the whole set takes a few seconds; it is worked
out on first use, and again when the live release changes, or in the background as the release
opens when the explorer warms (`open-altio serve` and the hosted service do).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from open_altio.faers.drugnames.dictionary import SEPARATOR
from open_altio.faers.explorer_db import drug_term
from open_altio.rulebook import rule, value

from . import drugs
from .filters import NOT_GIVEN, age_bands, default_dedup, not_given_label
from .release import OpenRelease

_ANSWERS_KEPT = 512  # answers remembered per release (summary, timeline)

# Every drug a page can open: each combination as the release names it and each ingredient,
# with every combination holding all of its ingredients (joined on its first, so each drug
# reads only the combinations that may hold it).
_HOLDERS = f"""
WITH units AS (
  SELECT DISTINCT substance_T AS unit_T FROM explorer_ingredient_T
  UNION SELECT DISTINCT ingredient_T FROM explorer_ingredient_T),
held AS (SELECT DISTINCT ingredient_T, substance_T FROM explorer_ingredient_T)
SELECT u.unit_T, h.substance_T AS holder_T FROM units u
JOIN held h ON h.ingredient_T = split_part(u.unit_T, '{SEPARATOR}', 1)
WHERE list_has_all(string_split(h.substance_T, '{SEPARATOR}'),
                   string_split(u.unit_T, '{SEPARATOR}'))
"""


class Facts:
    """One release's facts, each worked out on first use. Thread-safe."""

    def __init__(self, opened: OpenRelease) -> None:
        self.opened = opened
        self._lock = threading.Lock()  # held only to look up; a fact is made outside it
        self._made: OrderedDict[str, Any] = OrderedDict()
        self._answers: OrderedDict[str, Any] = OrderedDict()
        self._making: dict[tuple, threading.Event] = {}  # facts and answers being made

    def once(self, name: str, make: Callable[[], Any]) -> Any:
        """The fact `name`, made once and kept while this release is live. A request asking
        for it while it is being made waits for that one; other facts are made meanwhile."""
        return self._kept(self._made, name, make, None)

    def _rows(self, sql: str, params: list | None = None) -> list[dict[str, Any]]:
        return self.opened.rows(sql, params)

    # the facts -----------------------------------------------------------------------

    @property
    def drugs(self) -> list[dict]:
        """Every drug a page can open, most cases first: its name and title, its cases, the
        spellings it is reported under most, of those with cases as a page counts them (how many:
        rule explorer-lists), and how many spellings it has in any product containing it and in
        that product alone."""
        return self.once("drugs", self._make_drugs)

    @property
    def drug_named(self) -> dict[str, dict]:
        return self.once("drug_named", lambda: {d["name"]: d for d in self.drugs})

    @property
    def drug_cases(self) -> dict[str, int]:
        return self.once("drug_cases", lambda: {d["name"]: d["cases"] for d in self.drugs})

    def name_of(self, name: str) -> tuple[str, str] | None:
        """What a name opens: ("ingredient", its drug) for a drug's own name, ("spelling", it)
        for FDA's spelling with no ingredient, and for any other of FDA's names (an older
        address names FDA's active ingredient, a brand works too) the drug most of its records
        were read to. None for a name the release does not hold."""
        if name.strip().lower() in self.drug_named:
            return "ingredient", name.strip().lower()
        term = drug_term(name)
        return self.remember(f"name|{term}", lambda: self._resolve(term)) if term else None

    @property
    def pt_names(self) -> dict[str, str]:
        """lower(pt) -> the spelling shown. FDA's legacy quarters wrote terms in
        capitals; the mixed-case spelling is shown where one exists."""
        return self.once(
            "pt_names",
            lambda: {
                r["k"]: r["pt"]
                for r in self._rows(
                    "SELECT lower(pt) AS k, max(pt) AS pt FROM explorer_reac_T "
                    "WHERE pt IS NOT NULL GROUP BY 1"
                )
            },
        )

    @property
    def info(self) -> dict:
        return self.once("info", self._make_info)

    def pt_name(self, term: str | None) -> str | None:
        return self.pt_names.get(term.lower(), term) if term else term

    def remember(self, key: str, make: Callable[[], Any]) -> Any:
        """The answer for `key`, made once and kept while this release is live
        (the most recent answers only). Requests asking for it while it is being made wait for
        that one, so a page's questions side by side make it once, not each."""
        return self._kept(self._answers, key, make, _ANSWERS_KEPT)

    def _kept(
        self, store: OrderedDict[str, Any], key: str, make: Callable[[], Any], most: int | None
    ) -> Any:
        """`store`'s value for `key`, made by `make` the first time; `most` keeps only the most
        recently asked for, None keeps all."""
        making_key = (id(store), key)
        while True:
            with self._lock:
                if key in store:
                    if most is not None:
                        store.move_to_end(key)
                    return store[key]
                making = self._making.get(making_key)
                if making is None:
                    making = self._making[making_key] = threading.Event()
                    break
            making.wait()  # made by another request; take it, or make it if that one failed
        try:
            answer = make()
            with self._lock:
                store[key] = answer
                while most is not None and len(store) > most:
                    store.popitem(last=False)
            return answer
        finally:
            with self._lock:
                del self._making[making_key]
            making.set()

    # how each is made ------------------------------------------------------------------

    def _make_drugs(self) -> list[dict]:
        roles = drugs.default_roles()
        marks = ", ".join("?" for _ in roles)
        holders = f"holders AS ({_HOLDERS})"
        cases = self._rows(
            f"WITH {holders}, rec AS (SELECT DISTINCT i.substance_T, i.case_id_T FROM "
            "explorer_ingredient_T i JOIN explorer_case_T c USING (case_id_T) "
            f"WHERE i.role_T IN ({marks}) AND c.dup_kept_T) "
            "SELECT h.unit_T AS name, count(DISTINCT r.case_id_T) AS cases FROM holders h "
            "LEFT JOIN rec r ON r.substance_T = h.holder_T GROUP BY 1",
            list(roles),
        )
        names = (
            f"WITH {holders}, names AS (SELECT name_T, substance_T, sum(rows_T) AS n FROM "
            "explorer_drug_name_T WHERE field_T = 'drugname' AND substance_T IS NOT NULL "
            "GROUP BY 1, 2) "
        )
        spellings = {
            r["name"]: {"any": r["any"], "exact": r["exact"]}
            for r in self._rows(
                f"{names} SELECT h.unit_T AS name, count(DISTINCT s.name_T) AS any, "
                "count(DISTINCT s.name_T) FILTER (WHERE s.substance_T = h.unit_T) AS exact "
                "FROM holders h JOIN names s ON s.substance_T = h.holder_T GROUP BY 1"
            )
        }
        # a spelling with no cases as a page counts them is no name the drug is reported under
        reported: dict[str, list[str]] = {}
        for r in self._rows(
            f"{names}, counted AS (SELECT DISTINCT i.substance_T, i.spelling_T FROM "
            "explorer_ingredient_T i JOIN explorer_case_T c USING (case_id_T) "
            f"WHERE i.role_T IN ({marks}) AND c.dup_kept_T) "
            "SELECT h.unit_T AS name, s.name_T AS spelling, sum(s.n) AS n FROM holders h "
            "JOIN names s ON s.substance_T = h.holder_T SEMI JOIN counted k "
            "ON k.substance_T = s.substance_T AND k.spelling_T = s.name_T "
            "GROUP BY 1, 2 QUALIFY row_number() OVER "
            "(PARTITION BY h.unit_T ORDER BY sum(s.n) DESC, s.name_T) <= ? ORDER BY 1, 3 DESC, 2",
            list(roles) + [int(value("explorer-lists", "names_shown"))],
        ):
            reported.setdefault(r["name"], []).append(r["spelling"])
        return sorted(
            (
                {
                    "name": r["name"],
                    "title": drugs.title(r["name"]),
                    "cases": r["cases"],
                    "reported": reported.get(r["name"], []),
                    "spellings": spellings.get(r["name"], {"any": 0, "exact": 0}),
                }
                for r in cases
            ),
            key=lambda d: (-d["cases"], d["name"]),
        )

    def _resolve(self, term: str) -> tuple[str, str] | None:
        found = self._rows(
            "SELECT field_T, substance_T, sum(rows_T) AS n FROM explorer_drug_name_T "
            "WHERE name_T = ? GROUP BY 1, 2 ORDER BY 3 DESC, 2",
            [term],
        )
        if any(r["field_T"] == "drugname" and r["substance_T"] is None for r in found):
            return "spelling", term
        read = [r["substance_T"] for r in found if r["substance_T"] is not None]
        return ("ingredient", read[0]) if read else None

    def _make_info(self) -> dict:
        meta = self._rows(
            "SELECT release_T, CAST(built_at_T AS VARCHAR) AS built_at_T FROM explorer_release_T"
        )[0]
        by = self._rows(
            "SELECT era_T AS era, dup_kept_T AS kept, count(*) AS n FROM explorer_case_T "
            "GROUP BY ALL"
        )
        quarters = self.opened.manifest["quarters"]
        return {
            "release": meta["release_T"],
            "built_at": meta["built_at_T"],
            # the first and the last of FDA's quarters it holds, and FDA's systems with the
            # quarters each published
            "quarters": [quarters[0], quarters[-1]],
            "eras": value("era-filter", "quarters"),
            "cases": sum(r["n"] for r in by if r["kept"]),
            "all_cases": sum(r["n"] for r in by),
            "set_aside": sum(r["n"] for r in by if not r["kept"]),
            "by_era": {
                e: sum(r["n"] for r in by if r["era"] == e and r["kept"])
                for e in ("faers", "legacy")
            },
            # whether a page opens with probable duplicates left out or included
            "dedup": default_dedup(),
            # the age bands in order (rule age-bands), and the word for a case with no age
            # (rule not-given)
            "ages": {b["id"]: b["label"] for b in age_bands()} | {NOT_GIVEN: not_given_label()},
            # the fields whose FDA files changed, from which quarter, and the note shown
            "field_notes": value("explorer-field-notes", "notes"),
            # how long the page's short lists are (rule explorer-lists)
            "lists": dict(rule("explorer-lists").values),
            # the country codes that name no country of today, with a note each (rule
            # legacy-country), and what FDA writes where no country is given (rule
            # country-not-given)
            "countries": {
                "noted": value("legacy-country", "noted_codes"),
                "not_given": value("country-not-given", "not_countries"),
            },
        }


class LiveFacts:
    """Keeps the facts of the live release, and starts afresh when it changes. With `warm`,
    a new release's facts are warmed by it in the background, so its first pages need not."""

    def __init__(self, warm: Callable[[], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._facts: Facts | None = None
        self._warm = warm

    def of(self, opened: OpenRelease) -> Facts:
        with self._lock:
            if self._facts is None or self._facts.opened is not opened:
                self._facts = Facts(opened)
                if self._warm is not None:
                    threading.Thread(target=self._warm, name="open-altio-warm", daemon=True).start()
            return self._facts


__all__ = ["Facts", "LiveFacts"]
