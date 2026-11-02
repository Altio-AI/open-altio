"""A query's terms read against the label: for a drug and a group of reactions (`reaction`,
repeated), each reaction reported with the drug under the page's other filters, with its label
flag and the label read (labels.py), how many the label lists, and how many of the group were
never reported with the drug, so there was nothing to compare."""

from __future__ import annotations

from . import labels
from .answers import Problem
from .explore import Data, Query, product_unit, tidy
from .search import counts_for


def label_query(data: Data, query: Query) -> dict:
    """The group's reactions against the drug's label; {} where the release holds no flags."""
    unit = product_unit(data, query)
    if unit is None or not unit.substance:
        raise Problem(400, "Name the drug.")
    asked = list(dict.fromkeys(tidy(t) for t in query.get("reaction", []) if tidy(t)))
    if not asked:
        raise Problem(400, "Name the reactions to read against the label.")
    if not labels.held(data.opened):
        return {}
    keys = {t: data.reactions.key(t) for t in asked}
    # the reactions here are the group, not the one-reaction filter
    others = {k: v for k, v in query.items() if k != "reaction"}
    counts = counts_for(data, sorted({k for k in keys.values() if k}), others)
    flags = {
        pt.lower(): flag
        for pt, flag in labels.product_flags(data, unit.substance, unit.exact).get("reactions", [])
    }
    reported, never = [], []
    for text in asked:
        key = keys[text]
        name = data.pt_name(key) or text
        if key and counts.get(key, 0):
            flag = flags.get(name.lower())
            reported.append(
                {
                    "pt": name,
                    "cases": counts[key],
                    "label": flag,
                    "outcome": flag and flag["outcome"],
                }
            )
        else:
            never.append(text)
    reported.sort(key=lambda r: (-r["cases"], r["pt"]))
    return {
        "drug": unit.substance,
        "reactions": reported,
        "listed": sum(r["outcome"] == "on_label" for r in reported),
        "not_compared": len(never),
        "never_reported": sorted(never),
    }
