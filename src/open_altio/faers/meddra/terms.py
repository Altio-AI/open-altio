"""FDA's MedDRA terms read to one MedDRA version (rule meddra-terms), for the licensed part.

FAERS holds MedDRA terms as text in three columns: a reaction (`reac.pt`), the reaction that
came back when the drug was given again (`reac.drug_rec_act`, FAERS only) and an indication
(`indi.indi_pt`). Each distinct text is compared the way the explorer compares reaction text
(lower case, runs of spaces made one; in `drug_rec_act`, where FDA writes an apostrophe as `^`,
read as an apostrophe first) to the version's names, in this order: a PT; else a lower level
term, a current one first; else a name MedDRA used for a term before renaming it, from its
history file. The match gives the text its code and its current PT. FDA's text is never changed.

    map_terms(con, "29.1")   # con holds MedDRA's tables (licensed.load) and FDA's reac and indi

writes, in `con`:

- `meddra_term_T`: every PT and lower level term name of the version, and every former name,
  normalised, with its code, its PT and whether it is current.
- `reac_meddra_T`, `drug_rec_act_meddra_T`, `indi_meddra_T`: one row per distinct text of
  that column, keyed `<prefix>_term_T` (the text as `term_key` reads it), with `pt_code_T`,
  `llt_code_T`, `matched_as_T` (pt, llt or former_name; none when nothing matches),
  `llt_current_T` and `pt_current_T` (true when the text is a PT of this version). The same
  SQL makes all three.

The report says, per column, how many texts there are, how many only the history file
places, and how many (and on how many rows) match nothing; and which quarters fit no single
MedDRA version. FAERS's reaction field holds only MedDRA terms, so a reaction text that
matches nothing means the MedDRA file is older than the data, and the caller refuses it.
"""

from __future__ import annotations

from typing import NamedTuple

import duckdb

from open_altio import rulebook

from ..explorer_db import reaction_key, reaction_term
from ..reader import quoted

RULE = "meddra-terms"


class Column(NamedTuple):
    source: str  # FDA's table
    table: str  # the mapping table written
    term: str  # its key column


COLUMNS = {
    "pt": Column("reac", "reac_meddra_T", "reac_term_T"),
    "drug_rec_act": Column("reac", "drug_rec_act_meddra_T", "drug_rec_act_term_T"),
    "indi_pt": Column("indi", "indi_meddra_T", "indi_term_T"),
}
MAPPING_TABLES = ("meddra_term_T",) + tuple(c.table for c in COLUMNS.values())


def _read(column: str, text_sql: str) -> str:
    """FDA's text as it is matched: an apostrophe FDA writes as ^ read as one."""
    if column in rulebook.value(RULE, "apostrophe_as_caret"):
        return f"replace({text_sql}, '^', '''')"
    return text_sql


def key_sql(column: str, text_sql: str | None = None) -> str:
    """SQL for the key of FDA's `column` (text_sql, else the column itself) in its table."""
    return reaction_key(_read(column, text_sql or column))


def term_key(column: str, text: str) -> str | None:
    """FDA's text in `column` as its mapping table keys it."""
    if column in rulebook.value(RULE, "apostrophe_as_caret"):
        text = text.replace("^", "'")
    return reaction_term(text)


# A name in use now always wins over a former one, so a former name is kept only when it is
# no name of the version.
TERM_TABLE = f"""
CREATE OR REPLACE TABLE meddra_term_T AS
WITH named AS (
  SELECT {reaction_key("pt_name")} AS term_key_T, 'pt' AS level_T, pt_code AS code_T,
         pt_code AS pt_code_T, TRUE AS current_T FROM meddra_pt
  UNION ALL
  SELECT {reaction_key("llt_name")}, 'llt', llt_code, pt_code, llt_currency = 'Y' FROM meddra_llt)
SELECT * FROM named
UNION ALL
SELECT DISTINCT {reaction_key("h.term_name")}, 'former_name', h.term_code, l.pt_code, FALSE
FROM meddra_history h JOIN meddra_llt l ON l.llt_code = h.term_code
WHERE h.term_type IN ('PT', 'LLT')
  AND {reaction_key("h.term_name")} NOT IN
      (SELECT term_key_T FROM named WHERE term_key_T IS NOT NULL)
ORDER BY term_key_T, level_T DESC, code_T
"""

# One row per distinct text: a PT of this version wins, else a lower level term (a current one
# first, then the lowest code), else a former name (the lowest code).
MAP_TABLE = """
CREATE OR REPLACE TABLE {table} AS
WITH texts AS (SELECT DISTINCT {key} AS {term} FROM {source} WHERE {key} IS NOT NULL),
pt AS (SELECT term_key_T, min(code_T) AS code_T FROM meddra_term_T WHERE level_T = 'pt' GROUP BY 1),
llt AS (SELECT term_key_T, arg_min(code_T, (NOT current_T, code_T)) AS code_T,
               arg_min(pt_code_T, (NOT current_T, code_T)) AS pt_code_T,
               bool_or(current_T) AS current_T
        FROM meddra_term_T WHERE level_T = 'llt' GROUP BY 1),
former AS (SELECT term_key_T, min(code_T) AS code_T, arg_min(pt_code_T, code_T) AS pt_code_T
           FROM meddra_term_T WHERE level_T = 'former_name' GROUP BY 1)
SELECT t.{term}, {version}::VARCHAR AS meddra_version_T,
       coalesce(pt.code_T, llt.pt_code_T, former.pt_code_T) AS pt_code_T,
       coalesce(llt.code_T, former.code_T) AS llt_code_T,
       CASE WHEN pt.code_T IS NOT NULL THEN 'pt' WHEN llt.code_T IS NOT NULL THEN 'llt'
            WHEN former.code_T IS NOT NULL THEN 'former_name' END AS matched_as_T,
       coalesce(llt.current_T, CASE WHEN former.code_T IS NOT NULL THEN FALSE END) AS llt_current_T,
       pt.code_T IS NOT NULL AS pt_current_T
FROM texts t LEFT JOIN pt ON pt.term_key_T = t.{term} LEFT JOIN llt ON llt.term_key_T = t.{term}
LEFT JOIN former ON former.term_key_T = t.{term}
ORDER BY t.{term}
"""

# Which MedDRA version each quarter's reactions fit. A code is a PT in a version when its last
# addition or demotion up to that version (the history file's A and D at PT level) added it;
# a quarter fits a version when every reaction row's term was a PT in it. FAERS's reaction field
# holds only PTs, so a quarter that fits none was coded in more than one version.
VERSION_FIT = """
WITH versions AS (
  SELECT version, row_number() OVER (ORDER BY split_part(version, '.', 1)::INT,
                                              split_part(version, '.', 2)::INT) AS n
  FROM (SELECT DISTINCT version FROM meddra_history)),
events AS (SELECT h.term_code, v.n, h.action FROM meddra_history h JOIN versions v USING (version)
           WHERE h.term_type = 'PT' AND h.action IN ('A', 'D')),
pt_in AS (SELECT e.term_code, v.n FROM versions v JOIN events e ON e.n <= v.n
          GROUP BY ALL HAVING arg_max(e.action, e.n) = 'A'),
rows_ AS (SELECT r.quarter_T, m.llt_code_T AS code, count(*) AS n_rows
          FROM reac r JOIN reac_meddra_T m ON m.reac_term_T = {key}
          GROUP BY ALL),
fit AS (SELECT r.quarter_T, v.version, v.n,
               coalesce(sum(r.n_rows) FILTER (WHERE p.term_code IS NULL), 0) AS off
        FROM rows_ r CROSS JOIN versions v LEFT JOIN pt_in p ON p.term_code = r.code AND p.n = v.n
        GROUP BY ALL)
SELECT quarter_T, arg_min(version, (off, n)) AS nearest, min(off) AS rows_off
FROM fit GROUP BY 1 HAVING min(off) > 0 ORDER BY 1
"""


def _column_report(con: duckdb.DuckDBPyConnection, column: str) -> dict:
    spec = COLUMNS[column]
    [(texts, former, unmapped)] = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE matched_as_T = 'former_name'), "
        f"count(*) FILTER (WHERE matched_as_T IS NULL) FROM {spec.table}"
    ).fetchall()
    rows, first, last = 0, None, None
    if unmapped:
        unmatched = f"SELECT {spec.term} FROM {spec.table} WHERE matched_as_T IS NULL"
        [(rows, first, last)] = con.execute(
            f"SELECT count(*), min(quarter_T), max(quarter_T) FROM {spec.source} "
            f"WHERE {key_sql(column)} IN ({unmatched})"
        ).fetchall()
    return {
        "table": spec.table,
        "texts": texts,
        "former_names": former,
        "unmapped": {
            "texts": unmapped,
            "rows": rows,
            "quarters": [first, last] if unmapped else [],
        },
    }


def map_terms(con: duckdb.DuckDBPyConnection, version: str) -> dict:
    """Write meddra_term_T and the three mapping tables in `con`, and return the report:
    {"columns": {column: {table, texts, former_names, unmapped: {texts, rows, quarters}}},
     "quarters_fitting_no_version": [{quarter, nearest, rows_off}]}."""
    con.execute(TERM_TABLE)
    for column, spec in COLUMNS.items():
        con.execute(
            MAP_TABLE.format(
                table=spec.table,
                term=spec.term,
                source=spec.source,
                key=key_sql(column),
                version=quoted(version),
            )
        )
    fit = con.execute(VERSION_FIT.format(key=key_sql("pt", "r.pt"))).fetchall()
    return {
        "columns": {column: _column_report(con, column) for column in COLUMNS},
        "quarters_fitting_no_version": [
            {"quarter": q, "nearest": v, "rows_off": int(n)} for q, v, n in fit
        ],
    }


def stopping(report: dict) -> list[str]:
    """The columns whose unmapped texts stop the build (rule meddra-terms), with any."""
    return [
        c
        for c in rulebook.value(RULE, "stops_when_unmapped")
        if report["columns"][c]["unmapped"]["texts"]
    ]


__all__ = ["COLUMNS", "MAPPING_TABLES", "Column", "key_sql", "map_terms", "stopping", "term_key"]
