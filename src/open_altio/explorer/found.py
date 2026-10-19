"""Where a search's finds come in its list, in every search box (rule explorer-lists): the
name typed first, then the names starting with it, then the rest holding it, each in the list's
own order. An empty box lists in that order alone."""

from __future__ import annotations


def found_order(q: str, *names: str | None) -> int | None:
    """Where something a search found comes in its list (rule explorer-lists): 0 when one of
    its names is what was typed (`q`), 1 when one starts with it, 2 when one holds it, None when
    none does. The caller gives `q` and the names in the same case."""
    held = [n for n in names if n]
    if q in held:
        return 0
    for n in held:  # loops, not any(): a search reads every drug and spelling
        if n.startswith(q):
            return 1
    for n in held:
        if q in n:
            return 2
    return None


def found_order_sql(q: str, *columns: str) -> tuple[str, list]:
    """found_order over SQL `columns`, for an ORDER BY, with its parameters."""
    exact = " OR ".join(f"{c} = ?" for c in columns)
    starts = " OR ".join(f"starts_with({c}, ?)" for c in columns)
    return f"CASE WHEN {exact} THEN 0 WHEN {starts} THEN 1 ELSE 2 END", [q] * (2 * len(columns))


__all__ = ["found_order", "found_order_sql"]
