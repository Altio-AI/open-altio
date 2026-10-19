"""The class statistics' counts (rule statistics-classes): the cases cases.count counted, with
each suspect drug record's WHO class in place of its ingredients, one level of the class at a
time. On the connection cases.count counted on, which also holds the release's atc_drug_T (and
atc_drug_codes_T, where the rule counts the classes a record could be).

    prepare(con)                        # each counted case's suspect records and their classes
    found, links, cases = at_level(con, counts, 4)  # Counts with classes in place of ingredients,
                                        # each ingredient's classes at that level (LINK_COLUMNS),
                                        # and how many counted cases name a class there
"""

from __future__ import annotations

from typing import Any

import duckdb
import numpy as np

from open_altio import rulebook

from ..atc.whofile import LEVELS
from .cases import Counts, ints, roles_sql

RULE = "statistics-classes"
TABLE = "atc_statistics_T"
INGREDIENTS_TABLE = "atc_statistics_ingredients_T"
TABLES = (TABLE, INGREDIENTS_TABLE)
LINK_COLUMNS = ("ingredient", "level", "class", "cases")
LENGTH = {level: n for n, level in LEVELS.items()}  # an ATC level -> its code's length
RECORD = "era_T, primaryid, quarter_T, drug_seq"

# The suspect drug records of the counted cases, numbered by their case, with the one class each
# has (atc_drug_T); `level` is how deep that class reaches.
CERTAIN = f"""
CREATE TEMP TABLE class_suspect AS
SELECT DISTINCT k.cid, s.era_T, s.primaryid, s.quarter_T, s.drug_seq
FROM (SELECT DISTINCT {RECORD} FROM drug_latest_T WHERE upper(trim(role_cod)) IN ({{roles}})) s
JOIN kept_case k USING (era_T, primaryid, quarter_T)
SEMI JOIN counted_case c ON c.cid = k.cid;
CREATE TEMP TABLE class_code AS
SELECT s.cid, s.drug_seq, a.atc_code_T AS code, a.atc_level_T AS level
FROM class_suspect s JOIN atc_drug_T a USING ({RECORD})
WHERE a.atc_code_T IS NOT NULL
"""
# Each of those records' possible codes (atc_drug_codes_T), with how deep its one class reaches
# (0 for none), for the levels its class does not reach.
COULD_BE = f"""
CREATE TEMP TABLE class_could AS
SELECT s.cid, s.drug_seq, p.atc_code_T AS code, p.atc_level_T AS level,
       coalesce(a.atc_level_T, 0) AS reached
FROM class_suspect s JOIN atc_drug_codes_T p USING ({RECORD})
LEFT JOIN atc_drug_T a USING ({RECORD})
"""
# One level's class of each record, once per record and class; then each counted case's classes,
# numbered, with its stratum.
AT_LEVEL = """
CREATE OR REPLACE TEMP TABLE class_record AS
SELECT DISTINCT cid, drug_seq, left(code, {length}) AS name FROM class_code WHERE level >= {level}
{could_be};
CREATE OR REPLACE TEMP TABLE class_id AS
SELECT row_number() OVER (ORDER BY name) - 1 AS iid, name
FROM (SELECT DISTINCT name FROM class_record);
CREATE OR REPLACE TEMP TABLE counted_class AS
SELECT DISTINCT r.cid, g.iid, c.sid
FROM class_record r JOIN class_id g USING (name) JOIN counted_case c USING (cid)
"""
COULD_BE_AT_LEVEL = """UNION
SELECT DISTINCT cid, drug_seq, left(code, {length}) FROM class_could
WHERE reached < {level} AND level >= {level}"""

PAIRS = """SELECT iid, eid, count(*) AS n FROM counted_class JOIN counted_reaction USING (cid)
GROUP BY ALL ORDER BY iid, eid"""
CLASS_STRATA = "SELECT iid, sid, count(*) FROM counted_class GROUP BY ALL ORDER BY 1, 2"
# Each ingredient's classes at the level: the cases in which a record of the ingredient counted
# under the class.
LINKS = """SELECT i.name AS ingredient, r.name AS class, count(DISTINCT r.cid) AS cases
FROM suspect_drug s JOIN class_record r USING (cid, drug_seq) JOIN ingredient_id i USING (iid)
GROUP BY ALL ORDER BY ingredient, class"""


def levels() -> list[dict[str, Any]]:
    """The levels the rule counts, each with its WHO name, broadest first."""
    return sorted((dict(v) for v in rulebook.value(RULE, "levels")), key=lambda v: v["level"])


def could_be() -> bool:
    """Whether a record also counts under the classes it could be (rule statistics-classes)."""
    return bool(rulebook.value(RULE, "could_be"))


def needs() -> tuple[str, ...]:
    """The classes layer's tables the count reads."""
    return ("atc_drug_T", "atc_drug_codes_T") if could_be() else ("atc_drug_T",)


def prepare(con: duckdb.DuckDBPyConnection) -> None:
    """The counted cases' suspect records and their classes, once for every level."""
    con.execute(CERTAIN.format(roles=roles_sql()))
    if could_be():
        con.execute(COULD_BE)


def at_level(
    con: duckdb.DuckDBPyConnection, counts: Counts, level: int
) -> tuple[Counts, dict[str, np.ndarray], int]:
    """The counts at one level, with each class's code in place of an ingredient, on the cases,
    reactions and strata of `counts`; each ingredient's classes there with their cases; and the
    counted cases that name a class there."""
    length = LENGTH[level]
    more = COULD_BE_AT_LEVEL.format(length=length, level=level) if could_be() else ""
    con.execute(AT_LEVEL.format(length=length, level=level, could_be=more))
    names = [r[0] for r in con.execute("SELECT name FROM class_id ORDER BY iid").fetchall()]
    found = Counts(
        ingredients=np.asarray(names, dtype=object),
        reactions=counts.reactions,
        strata=counts.strata,
        pairs=ints(con, PAIRS, ("product", "event", "n")),
        ingredient_strata=ints(con, CLASS_STRATA, ("product", "stratum", "n")),
        reaction_strata=counts.reaction_strata,
    )
    got = con.execute(LINKS).fetchnumpy()
    links = {
        "ingredient": np.asarray(got["ingredient"], dtype=object),
        "level": np.full(len(got["cases"]), level, dtype=np.int64),
        "class": np.asarray(got["class"], dtype=object),
        "cases": np.asarray(got["cases"], dtype=np.int64),
    }
    [(named,)] = con.execute("SELECT count(DISTINCT cid) FROM counted_class").fetchall()
    return found, links, int(named)
