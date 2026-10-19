"""What a reaction is on the explorer's pages, the one place that says it (rule meddra-terms):
where the release holds MedDRA, the preferred term FDA's text reads to today, named as MedDRA
writes it; without, FDA's text, matched whatever its capitals and spacing. A viewer counts and
finds reactions by it, so a search for a PT finds the cases FDA wrote under its older terms too.
The access hook says whose reactions are named so (Viewer.todays_names): any other viewer is
given the release as one without MedDRA, FDA's text, and the line that says so. The text to PT
link itself is shown only where the access hook allows MedDRA's licensed part.

    reactions = Reactions(facts, served)   # served: the MedDRA version reactions are named by
    reactions.key(" Seizure ")             # "seizure": a chosen reaction, as it is matched
    reactions.texts(["seizure"])           # FDA's texts it counts (explorer_reac_term_T.term_T)
    reactions.name("seizure")              # "Seizure", as a page shows it
    reactions.counts                       # key -> kept cases naming it
    reactions.keyed(["seizure"])           # a FROM item of (case_id_T, k), to count per key

A chosen reaction that is no current PT, such as one in an older address, matches FDA's texts
equal to it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from open_altio.faers.explorer_db import reaction_term

from .facts import Facts
from .meddra import ServedMeddra

TERMS = "explorer_reac_term_T"  # (FDA's text as the explorer matches it, case) pairs


class Reactions:
    """Reactions as one release names them, with its MedDRA version or without one."""

    def __init__(self, facts: Facts, meddra: ServedMeddra | None, line: str = "") -> None:
        self.facts = facts
        self.meddra = meddra
        self.line = line  # where FDA's text is shown though the release holds MedDRA

    @property
    def version(self) -> str | None:
        return self.meddra.version if self.meddra else None

    def about(self) -> dict[str, Any]:
        """How the pages count reactions: by current PT in the release's MedDRA version, or by
        FDA's text, with the line the pages show where that is the viewer's and not the
        release's."""
        return {
            "counted_by": "current_pt" if self.meddra else "fda_text",
            "meddra_version": self.version,
            **({"line": self.line} if self.line else {}),
        }

    @staticmethod
    def key(text: str) -> str | None:
        """A chosen or typed reaction as it is matched: lower case, runs of spaces made one."""
        return reaction_term(text)

    def texts(self, keys: Iterable[str]) -> list[str]:
        """FDA's reaction texts the keys count: each key's own, and with MedDRA every text read
        to it as its current PT."""
        found = set()
        for key in keys:
            found.add(key)
            if self.meddra:
                found.update(self.meddra.texts_of().get(key, ()))
        return sorted(found)

    def name(self, key: str | None) -> str | None:
        """A key as a page shows it: the PT as MedDRA writes it, else FDA's own spelling."""
        if key and self.meddra:
            named = self.meddra.pt_names().get(key)
            if named:
                return named
        return self.facts.pt_name(key)

    def keyed(self, keys: list[str] | None = None) -> tuple[str, list[Any]]:
        """A FROM item of (case_id_T, k): each case's reactions by key, only these keys when
        given, with its parameters."""
        if self.meddra is None:
            if keys is None:
                return f"(SELECT case_id_T, term_T AS k FROM {TERMS})", []
            return (
                f"(SELECT case_id_T, term_T AS k FROM {TERMS} "
                "WHERE term_T IN (SELECT unnest(?::VARCHAR[])))",
                [keys],
            )
        if keys is None:  # every text, by its current PT; a text MedDRA does not name, as itself
            read = self.meddra.read("pt")
            texts = sorted(read)
            return (
                f"(SELECT r.case_id_T, coalesce(m.k, r.term_T) AS k FROM {TERMS} r LEFT JOIN "
                "(SELECT unnest(?::VARCHAR[]) AS term_T, unnest(?::VARCHAR[]) AS k) m "
                "USING (term_T))",
                [texts, [read[t][0].lower() for t in texts]],
            )
        texts, named = [], []
        for key in keys:
            for text in self.texts([key]):
                texts.append(text)
                named.append(key)
        return (
            f"(SELECT r.case_id_T, m.k FROM {TERMS} r JOIN (SELECT unnest(?::VARCHAR[]) AS "
            "term_T, unnest(?::VARCHAR[]) AS k) m USING (term_T))",
            [texts, named],
        )

    @property
    def counts(self) -> dict[str, int]:
        """Each key -> the kept cases naming it; worked out once per release and MedDRA version."""

        def make() -> dict[str, int]:
            sql, params = self.keyed()
            return {
                r["k"]: r["n"]
                for r in self.facts.opened.rows(
                    f"SELECT r.k, count(DISTINCT r.case_id_T) AS n FROM {sql} r "
                    "JOIN explorer_case_T c USING (case_id_T) WHERE c.dup_kept_T GROUP BY 1",
                    params,
                )
            }

        return self.facts.once(f"reaction_counts|{self.version or '-'}", make)


__all__ = ["Reactions"]
