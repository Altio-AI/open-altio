"""Cases by MedDRA system organ class (SOC), for a viewer who may see MedDRA's licensed part.

A reaction counts in the primary SOC of the current PT its text reads to (ServedMeddra.soc_of);
a case with reactions in two SOCs counts in both. The filter `soc=<name>` (repeated) keeps the
cases with any reaction in a chosen SOC.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .answers import Problem
from .reactions import TERMS

if TYPE_CHECKING:
    from .explore import Data, Query


def chosen_texts(data: Data, query: Query) -> list[str]:
    """The reaction texts that read to the SOCs the query chooses; refused for a viewer who may
    not see MedDRA, and for a name that is no SOC of the served version."""
    names = sorted({n.strip() for n in query.get("soc", []) if n.strip()})
    if not names:
        return []
    meddra = data.served_meddra()
    by_text = meddra.soc_by_text()
    known = set(by_text.values())
    for name in names:
        if name not in known:
            raise Problem(400, f"{name} is not a system organ class in MedDRA {meddra.version}.")
    return sorted(t for t, soc in by_text.items() if soc in names)


def _pairs(data: Data) -> tuple[str, list[Any]]:
    by_text = data.served_meddra().soc_by_text()
    texts = sorted(by_text)
    return (
        "(SELECT unnest(?::VARCHAR[]) AS term_T, unnest(?::VARCHAR[]) AS soc)",
        [texts, [by_text[t] for t in texts]],
    )


def breakdown_job(data: Data, sql: str, params: list) -> tuple[str, list]:
    """Each SOC with the cases of `sql` that have a reaction in it, most first."""
    pairs, more = _pairs(data)
    return (
        f"SELECT m.soc AS k, count(DISTINCT r.case_id_T) AS n FROM {TERMS} r JOIN {pairs} m "
        "USING (term_T) WHERE r.case_id_T IN "
        f"(SELECT c.case_id_T FROM explorer_case_T c WHERE {sql}) GROUP BY 1 ORDER BY 2 DESC, 1",
        more + params,
    )


def coverage_job(data: Data, sql: str, params: list) -> tuple[str, list]:
    """The cases of `sql`, and how many have a reaction whose SOC is found."""
    pairs, more = _pairs(data)
    return (
        "SELECT count(*) AS n, count(*) FILTER (WHERE c.case_id_T IN (SELECT r.case_id_T "
        f"FROM {TERMS} r JOIN {pairs} m USING (term_T))) AS g FROM explorer_case_T c WHERE {sql}",
        more + params,
    )
