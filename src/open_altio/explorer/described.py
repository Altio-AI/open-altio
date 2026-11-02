"""A question in plain words, as a filtered export's manifest and a counted question's answer say
it: the product, reactions, SMQs, drugs and drug classes it names, then each filter in force, and
each value the filters left out (filters.left_out)."""

from __future__ import annotations

from . import classes
from .explore import Data, Query, Scope
from .filters import left_out


def _scope_words(data: Data, query: Query, asked: Scope) -> list[str]:
    """The product, reactions, SMQs, drugs and drug classes of the question, in plain words."""
    lines = [f"Product: {asked.product.described()}"] if asked.product else []
    pts = [t.strip() for t in query.get("pt", []) if t.strip()]
    if pts:
        counted = data.reactions.version
        how = f", each by its current PT in MedDRA {counted}" if counted else ""
        lines.append(f"Reactions: {', '.join(pts)}{how}")
    for item in query.get("smq", []):  # each one known: explore.scope has refused any other
        code, _, scope = item.partition(":")
        name = data.served_meddra().smqs()[code]["name"]
        lines.append(f"SMQ: {name} ({code}), {scope or 'narrow'}")
    out = [t.strip() for t in query.get("pt_out", []) if t.strip()]
    if out:
        lines.append(f"Reactions left out: {', '.join(out)}")
    if asked.drugs:
        lines.append(f"Drugs: {'; '.join(u.described() for u in asked.drugs)}")
    if asked.classes:
        names = classes.names_of(data, [*asked.classes.codes, *asked.classes.out])
        lines.append(f"Drug class (ATC): {asked.classes.described(names)}")
    return lines


def described(data: Data, query: Query, asked: Scope) -> list[str]:
    """The whole question in plain words: what it names, each filter in force, then each value the
    filters left out and why."""
    lines = _scope_words(data, query, asked)
    lines += [f"{label}: {words}" for label, words in asked.filters.described()]
    return lines + [f"Left out: {name} {given}, {why}" for name, given, why in left_out(query)]


__all__ = ["described"]
