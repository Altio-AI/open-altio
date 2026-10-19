"""The ingredients of each drug record (rule drug-names).

    from open_altio.faers.drugnames import substances
    entry = substances.build(con, dictionary_path)   # after the derive steps, on the build's con

A drug record is one drug of one report in `drug_latest_T`, keyed by
(era_T, primaryid, quarter_T, drug_seq); since 2024Q4 FDA can write one record
on several rows, one per dosage regimen, and they share its name. Two tables:

    drug_substance_T   one row per drug record:
                       substance_T         its ingredients, sorted, joined with ';', NULL if none
                       substance_source_T  where they came from (SOURCES)
                       diana_trial_T       DiAna marks it a trial product (a named study drug,
                                           placebo, or a blinded drug)
    drug_ingredient_T  one row per drug record and ingredient: ingredient_T

The record's drug name is looked up by DiAna's key. Where the name has no
substance, FDA's `prod_ai` is looked up the same way, whole, else split on
FDA's `\\` with every part found; a part that is itself a combination adds all
its ingredients. FDA's `drugname` and `prod_ai` are never changed.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from open_altio import rulebook

from ..reader import quoted
from . import dictionary
from .dictionary import RULE, SEPARATOR, TABLE, key_sql

SUBSTANCES = "drug_substance_T"
INGREDIENTS = "drug_ingredient_T"
TABLES = (SUBSTANCES, INGREDIENTS)
# Where a record's ingredients came from: DiAna by its drug name, DiAna by FDA's
# prod_ai, our reviewed correction of DiAna's answer, or nowhere (UNMAPPED).
UNMAPPED = "none"
SOURCES = ("diana_name", "diana_prod_ai", "correction", UNMAPPED)
PROD_AI_SEPARATOR = "\\"  # FDA's, between the ingredients of prod_ai: SACUBITRIL\VALSARTAN

_SEP, _PROD_AI_SEP = quoted(SEPARATOR), quoted(PROD_AI_SEPARATOR)  # as SQL string literals
_KEY = "era_T, primaryid, quarter_T, drug_seq"

# The answer for each distinct drug name, then for each distinct prod_ai.
_BY_NAME = f"""
CREATE TEMP TABLE drug_names_by_name_T AS
SELECT s.drugname, d.substance_T, d.trial_T, d.corrected_T
FROM (SELECT DISTINCT drugname FROM drug_latest_T WHERE drugname IS NOT NULL) s
JOIN {TABLE} d ON d.key_T = {key_sql("s.drugname")}
"""

_BY_PROD_AI = f"""
CREATE TEMP TABLE drug_names_by_prod_ai_T AS
WITH p AS (SELECT DISTINCT prod_ai FROM drug_latest_T WHERE prod_ai IS NOT NULL),
whole AS (
  SELECT p.prod_ai, d.substance_T, d.trial_T, d.corrected_T
  FROM p JOIN {TABLE} d ON d.key_T = {key_sql("p.prod_ai")}),
parts AS (
  SELECT x.prod_ai,
         array_to_string(
           list_sort(list_distinct(flatten(list(string_split(d.substance_T, {_SEP}))))),
           {_SEP}) AS substance_T,
         bool_or(d.trial_T) AS trial_T, bool_or(d.corrected_T) AS corrected_T,
         count(*) FILTER (WHERE d.key_T IS NULL) AS misses_T
  FROM (SELECT prod_ai, unnest(string_split(prod_ai, {_PROD_AI_SEP})) AS part_T FROM p) x
  LEFT JOIN {TABLE} d ON d.key_T = {key_sql("x.part_T")}
  GROUP BY 1)
SELECT p.prod_ai, coalesce(w.substance_T, s.substance_T) AS substance_T,
       coalesce(w.trial_T, s.trial_T) AS trial_T,
       coalesce(w.corrected_T, s.corrected_T) AS corrected_T
FROM p LEFT JOIN whole w USING (prod_ai)
LEFT JOIN (SELECT * FROM parts WHERE misses_T = 0) s USING (prod_ai)
WHERE w.prod_ai IS NOT NULL OR s.prod_ai IS NOT NULL
"""

# One row per record, the dose rows of a record collapsed first (they share its
# name and prod_ai); its answer by its name, else by its prod_ai, else none.
_SUBSTANCES = f"""
CREATE TABLE {SUBSTANCES} AS
WITH r AS (SELECT {_KEY}, min(drugname) AS drugname, min(prod_ai) AS prod_ai
           FROM drug_latest_T GROUP BY ALL)
SELECT r.era_T, r.primaryid, r.quarter_T, r.drug_seq,
       coalesce(n.substance_T, p.substance_T) AS substance_T,
       CASE WHEN n.substance_T IS NOT NULL
              THEN CASE WHEN n.corrected_T THEN 'correction' ELSE 'diana_name' END
            WHEN p.substance_T IS NOT NULL
              THEN CASE WHEN p.corrected_T THEN 'correction' ELSE 'diana_prod_ai' END
            ELSE 'none' END AS substance_source_T,
       coalesce(n.trial_T, p.trial_T, false) AS diana_trial_T
FROM r LEFT JOIN drug_names_by_name_T n USING (drugname)
LEFT JOIN drug_names_by_prod_ai_T p USING (prod_ai)
"""

_INGREDIENTS = f"""
CREATE TABLE {INGREDIENTS} AS
SELECT {_KEY}, unnest(string_split(substance_T, {_SEP})) AS ingredient_T
FROM {SUBSTANCES} WHERE substance_T IS NOT NULL
"""

# Drug records, never rows: FDA writes some records on one row per dose.
_COUNTS = f"SELECT substance_source_T, count(*) FROM {SUBSTANCES} GROUP BY 1"


def build(con: duckdb.DuckDBPyConnection, dictionary_path: str | Path | None) -> dict:
    """Write the two tables on `con` and return the manifest entry; without a
    dictionary, write nothing and say why. A refused dictionary or mapping raises
    dictionary.DictionaryRefused."""
    if not rulebook.is_on(RULE):
        return {"present": False, "reason": f"rule {RULE} is off"}
    if dictionary_path is None:
        return {"present": False, "reason": "no DiAna dictionary given"}
    facts = dictionary.load(con, dictionary_path)
    for statement in (_BY_NAME, _BY_PROD_AI, _SUBSTANCES, _INGREDIENTS):
        con.execute(statement)
    for scratch in (TABLE, "drug_names_by_name_T", "drug_names_by_prod_ai_T"):
        con.execute(f"DROP TABLE {scratch}")
    records = {source: 0 for source in SOURCES} | dict(con.execute(_COUNTS).fetchall())
    total = sum(records.values())
    return {
        "present": True,
        "dictionary": facts,
        "tables": list(TABLES),
        "drug_records": int(total),
        "records_by_source": {k: int(v) for k, v in records.items()},
        "unmapped_records": int(records[UNMAPPED]),
        "unmapped_share": round(100.0 * records[UNMAPPED] / total, 2) if total else 0.0,
        "unused_corrections": [f for f in facts["corrections"] if not f["keys"]],
    }


__all__ = ["INGREDIENTS", "SOURCES", "SUBSTANCES", "TABLES", "UNMAPPED", "build"]
