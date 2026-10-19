"""The one set of cases every statistic counts (rule statistics-cases), counted on a DuckDB
connection that holds the release's tables. Cases, ingredients, reactions and strata are
numbered first, so the counting joins integers and FAERS counts in a few GB.

    counts = count(con)    # Counts: the cases per pair, per ingredient and stratum,
                           # per reaction and stratum, and per stratum
    counts = count(con, "meddra_pt")   # reactions by current preferred term: con also holds
                                       # the licensed reac_meddra_T and meddra_pt
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np

from open_altio import rulebook

from ..drugnames.substances import INGREDIENTS
from ..explorer_db import reaction_key
from ..meddra.terms import key_sql

RULE = "statistics-cases"

# The cases the release keeps, numbered, with the parts of their stratum.
KEPT = """
CREATE TEMP TABLE kept_case AS
SELECT row_number() OVER () AS cid, era_T, primaryid, quarter_T, {parts}
FROM case_latest_T WHERE dup_kept_T
"""

# Each kept case's suspect drug records with their ingredients, once each: every ingredient of a
# drug record the case names in one of the roles, however many of FDA's rows the record takes;
# then each case's ingredients, once each. The drug records stay for the time to onset
# (onset.py), which counts drugs.
DRUGS = f"""
CREATE TEMP TABLE ingredient_id AS
SELECT row_number() OVER (ORDER BY name) - 1 AS iid, name
FROM (SELECT DISTINCT ingredient_T AS name FROM {INGREDIENTS});
CREATE TEMP TABLE suspect_drug AS
WITH suspect AS (
  SELECT DISTINCT era_T, primaryid, quarter_T, drug_seq FROM drug_latest_T
  WHERE upper(trim(role_cod)) IN ({{roles}}))
SELECT DISTINCT k.cid, g.iid, s.drug_seq
FROM {INGREDIENTS} i
JOIN suspect s USING (era_T, primaryid, quarter_T, drug_seq)
JOIN kept_case k USING (era_T, primaryid, quarter_T)
JOIN ingredient_id g ON g.name = i.ingredient_T;
CREATE TEMP TABLE case_ingredient AS SELECT DISTINCT cid, iid FROM suspect_drug
"""

# What a reaction is, the one place that says it, by the key a release counts with: with
# MedDRA, FDA's text read through the licensed mapping (keyed by the text as the explorer
# matches it) to its current preferred term, named as MedDRA writes it; without, FDA's text
# matched whatever its capitals and spacing, as the explorer matches it.
REACTION_NAMES = {
    "meddra_pt": f"""
SELECT DISTINCT r.era_T, r.primaryid, r.quarter_T, p.pt_name AS name
FROM reac_latest_T r JOIN reac_meddra_T m ON m.reac_term_T = {key_sql("pt", "r.pt")}
JOIN meddra_pt p ON p.pt_code = m.pt_code_T""",
    "fda_text": f"""
SELECT DISTINCT era_T, primaryid, quarter_T, {reaction_key("pt")} AS name FROM reac_latest_T""",
}

# Each kept case's reactions, once each, named by REACTION_NAMES.
EVENTS = """
CREATE TEMP TABLE case_reaction_named AS {named};
CREATE TEMP TABLE reaction_id AS
SELECT row_number() OVER (ORDER BY name) - 1 AS eid, name
FROM (SELECT DISTINCT name FROM case_reaction_named WHERE name IS NOT NULL);
CREATE TEMP TABLE case_reaction AS
SELECT DISTINCT k.cid, x.eid
FROM case_reaction_named n JOIN kept_case k USING (era_T, primaryid, quarter_T)
JOIN reaction_id x USING (name);
DROP TABLE case_reaction_named
"""

# The cases counted, those naming an ingredient and a reaction, each with its stratum; then
# the ingredients and reactions of those cases alone.
COUNTED = """
CREATE TEMP TABLE counted_case AS
SELECT cid, dense_rank() OVER (ORDER BY {parts}) - 1 AS sid, {parts}
FROM kept_case
WHERE cid IN (SELECT cid FROM case_ingredient) AND cid IN (SELECT cid FROM case_reaction);
CREATE TEMP TABLE counted_ingredient AS
SELECT i.cid, i.iid, c.sid FROM case_ingredient i JOIN counted_case c USING (cid);
CREATE TEMP TABLE counted_reaction AS
SELECT r.cid, r.eid, c.sid FROM case_reaction r JOIN counted_case c USING (cid);
DROP TABLE case_ingredient; DROP TABLE case_reaction
"""

PAIRS = """SELECT iid, eid, count(*) AS n FROM counted_ingredient JOIN counted_reaction USING (cid)
GROUP BY ALL ORDER BY iid, eid"""
INGREDIENT_STRATA = "SELECT iid, sid, count(*) FROM counted_ingredient GROUP BY ALL ORDER BY 1, 2"
REACTION_STRATA = "SELECT eid, sid, count(*) FROM counted_reaction GROUP BY ALL ORDER BY 1, 2"


@dataclass(frozen=True)
class Counts:
    """Counts of distinct cases. Ingredients and reactions are numbers into `ingredients` and
    `reactions`; strata are numbers into `strata`. The class statistics count WHO classes in
    the ingredients' place (classes.py)."""

    ingredients: np.ndarray  # name, by iid
    reactions: np.ndarray  # name, by eid
    strata: dict[str, np.ndarray]  # stratum (sid), each part, n
    pairs: dict[str, np.ndarray]  # product (iid), event (eid), n
    ingredient_strata: dict[str, np.ndarray]  # product, stratum, n
    reaction_strata: dict[str, np.ndarray]  # event, stratum, n

    @property
    def cases(self) -> int:
        return int(self.strata["n"].sum())


def _q(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def stratum_parts() -> dict[str, str]:
    """The SQL of each part a stratum may be made of, over case_latest_T: the age band and the sex
    the release gives each case (rules/age-bands.md, rules/sex-codes.md), and the receipt year."""
    unknown = _q(rulebook.value(RULE, "unknown"))
    return {
        "age_band": f"coalesce(age_band_T, {unknown})",
        "sex": f"coalesce(sex_T, {unknown})",
        "receipt_year": f"coalesce(CAST(init_year_T AS VARCHAR), {unknown})",
    }


def roles_sql() -> str:
    """The suspect roles a statistic counts, as SQL's list of FDA's codes."""
    return ", ".join(_q(r) for r in rulebook.value(RULE, "product_roles"))


def ints(con: duckdb.DuckDBPyConnection, sql: str, names: tuple[str, ...]) -> dict[str, np.ndarray]:
    """Each column of a query of whole numbers, by name."""
    got = con.execute(sql).fetchnumpy()
    return {
        name: np.asarray(col, dtype=np.int64) for name, col in zip(names, got.values(), strict=True)
    }


def count(con: duckdb.DuckDBPyConnection, by: str = "fda_text") -> Counts:
    """Count the release's cases on `con`, which holds case_latest_T, drug_latest_T,
    drug_ingredient_T and reac_latest_T, each reaction named as `by` says (REACTION_NAMES)."""
    known = stratum_parts()
    parts = list(rulebook.value(RULE, "strata"))
    con.execute(KEPT.format(parts=", ".join(f"{known[p]} AS {p}" for p in parts)))
    con.execute(DRUGS.format(roles=roles_sql()))
    con.execute(EVENTS.format(named=REACTION_NAMES[by]))
    con.execute(COUNTED.format(parts=", ".join(parts)))
    strata = con.execute(
        f"SELECT sid, {', '.join(parts)}, count(*) AS n FROM counted_case GROUP BY ALL ORDER BY sid"
    ).fetchnumpy()
    names = {
        table: np.asarray(
            [r[0] for r in con.execute(f"SELECT name FROM {table} ORDER BY 1").fetchall()],
            dtype=object,
        )
        for table in ("ingredient_id", "reaction_id")
    }
    return Counts(
        ingredients=names["ingredient_id"],
        reactions=names["reaction_id"],
        strata={
            "stratum": np.asarray(strata["sid"], dtype=np.int64),
            **{p: np.asarray(strata[p], dtype=object) for p in parts},
            "n": np.asarray(strata["n"], dtype=np.int64),
        },
        pairs=ints(con, PAIRS, ("product", "event", "n")),
        ingredient_strata=ints(con, INGREDIENT_STRATA, ("product", "stratum", "n")),
        reaction_strata=ints(con, REACTION_STRATA, ("event", "stratum", "n")),
    )
