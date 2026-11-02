"""Label status counted a second way, for recount.py: the cases a drug's ticked label flags keep,
read from the release's label flag tables as rule explorer-label-flags says, apart from labels.py.

    kept(opened, asked, values)   (its WITH items, a SELECT of the keys of the cases kept), or None
                                  where Label status keeps every case

A drug's flags belong to its suspect records (rule label-flags' `suspect_roles`, by FDA's role
code as published) that are no trial product, each with every reaction of its case. Counting any
product containing a single ingredient where the release holds each ingredient's own code
(`ingredient_rxnorm_T`), every record holding it is read on the ingredient's own label, but a
record of the ingredient alone keeps its own code where the ingredient's code finds no label;
otherwise the records of exactly that product, each by its own code. A record whose code names
another drug (`label_other_drug_T`) is read by its own code as one with none. Its forms are its
route families (`drug_route_T`), empty without the table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from open_altio.faers.drugnames.dictionary import SEPARATOR
from open_altio.rulebook import value

from .recountquery import RECORD, Asked
from .release import OpenRelease

if TYPE_CHECKING:
    from .recount import Values

NEEDED = ("label_flags_T", "drug_rxnorm_T", "drug_substance_T", "label_candidates_T")


def _same(a: str, b: str, key: tuple[str, ...] = RECORD) -> str:
    return " AND ".join(f"{a}.{k} = {b}.{k}" for k in key)


def kept(opened: OpenRelease, asked: Asked, v: Values) -> tuple[str, str] | None:
    """The WITH items that read the product's flags, and a SELECT of the keys of the cases with
    a reaction of a ticked flag; None without ticks, a product with ingredients or the flags."""
    tables = opened.manifest["tables"]
    product = asked.product
    if asked.labels is None or not product or not product.substance:
        return None
    if not all(t in tables for t in NEEDED):
        return None
    drug = product.substance
    own = not product.exact and SEPARATOR not in drug and "ingredient_rxnorm_T" in tables
    if own:
        chosen = (
            f"EXISTS (SELECT 1 FROM drug_ingredient_T i WHERE {_same('i', 'd')} "
            f"AND i.ingredient_T = {v.one(drug)})"
        )
    else:
        chosen = f"s.substance_T = {v.one(drug)}"
    suspect = v.among("d.role_cod", value("label-flags", "suspect_roles"))
    items = [
        "label_records AS (SELECT DISTINCT d.era_T, d.primaryid, d.quarter_T, d.drug_seq, "
        f"s.substance_T FROM drug_latest_T d JOIN drug_substance_T s ON {_same('s', 'd')} "
        f"WHERE {suspect} AND NOT coalesce(s.diana_trial_T, FALSE) AND {chosen})"
    ]
    other = "label_other_drug_T" in tables
    by_own_code = "CASE WHEN od.drug_seq IS NULL THEN x.rxcui_T END" if other else "x.rxcui_T"
    joins = "LEFT JOIN drug_rxnorm_T x ON " + _same("x", "r")
    if other:
        joins += " LEFT JOIN label_other_drug_T od ON " + _same("od", "r")
    if own:
        items.append(
            "label_own AS (SELECT rxcui_T, coalesce(rxcui_T IN (SELECT rxcui_T FROM "
            "label_candidates_T), FALSE) AS labelled FROM ingredient_rxnorm_T "
            f"WHERE ingredient_T = {v.one(drug)} ORDER BY rxcui_T LIMIT 1)"
        )
        alone = f"NOT coalesce(o.labelled, FALSE) AND r.substance_T = {v.one(drug)}"
        code = f"CASE WHEN {alone} THEN {by_own_code} ELSE o.rxcui_T END"
        joins += " LEFT JOIN label_own o ON TRUE"
    else:
        code = by_own_code
    if "drug_route_T" in tables:
        forms = "coalesce(ro.route_families_T, '')"
        joins += " LEFT JOIN drug_route_T ro ON " + _same("ro", "r")
    else:
        forms = "''"
    items.append(
        f"label_coded AS (SELECT r.*, {code} AS rxcui_T, {forms} AS forms_T "
        f"FROM label_records r {joins})"
    )
    uncertain = v.among("f.decided_by_T", value("explorer-label-flags", "shown_as_uncertain"))
    items.append(
        "label_pairs AS (SELECT DISTINCT r.era_T, r.primaryid, r.quarter_T, "
        f"CASE WHEN {uncertain} THEN 'uncertain' ELSE f.outcome_T END AS outcome "
        f"FROM label_coded r JOIN reac_latest_T x ON {_same('x', 'r', RECORD[:3])} "
        "AND x.pt IS NOT NULL JOIN label_flags_T f ON f.rxcui_T IS NOT DISTINCT FROM r.rxcui_T "
        "AND f.route_families_T = r.forms_T AND f.pt_T = x.pt)"
    )
    flags = v.among("outcome", asked.labels)
    return ", ".join(items), f"SELECT era_T, primaryid, quarter_T FROM label_pairs WHERE {flags}"


__all__ = ["kept"]
