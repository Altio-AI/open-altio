"""The cleaned route of each drug record (rule drug-route): `drug_route_T`.

    from open_altio.faers.route import clean
    clean.build(con)   # a derive step: reads drug_latest_T, writes drug_route_T

One row per drug record (era_T, primaryid, quarter_T, drug_seq), however many
rows FDA wrote for it. On each row, each source that says something about the
route gives the set of families the drug can be in: FDA's `route` and
`dose_form`, and each form word of the drug name. The row could be in the
families every source allows; when they allow none in common, the sources
contradict each other and the row could be in any family one of them names.
FDA writes one row per dosage regimen, so the record could be in every family
one of its rows could be in.
"""

from __future__ import annotations

import duckdb

from open_altio import rulebook

from .tables import KEY_SQL, RULE, RouteTables, families

TABLE = "drug_route_T"
KEY = ("era_T", "primaryid", "quarter_T", "drug_seq")
# FDA's fields the families are read from, as route_source_T names them.
SOURCES = ("route", "dose_form", "drugname")
_SCRATCH = (
    "drug_route_values_T",
    "drug_route_by_route_T",
    "drug_route_by_form_T",
    "drug_route_by_name_T",
)


def _text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _mask(names: frozenset[str], order: tuple[str, ...]) -> int:
    """A set of families as a number, one bit per family in the rule's order, so the
    families every source allows are a bitwise and and those any source names a bitwise or."""
    return sum(1 << i for i, f in enumerate(order) if f in names)


def _decode(mask: str) -> str:
    """A mask as its family names, sorted and joined with ';'."""
    names = ", ".join(_text(f) for f in families()[:-1])
    pick = f"list_filter([{names}], lambda x, i: ({mask} >> (i - 1)) & 1 = 1)"
    return f"array_to_string(list_sort({pick}), ';')"


def _load(con: duckdb.DuckDBPyConnection, t: RouteTables) -> None:
    """Each distinct value of FDA's fields with the families it allows, and for the
    route its E2B code. Keyed on FDA's value as written, so the drug rows join on it
    directly; a value that says nothing allows no family (a NULL mask)."""
    con.execute(
        f"CREATE TEMP TABLE {_SCRATCH[0]} (source_T VARCHAR, key_T VARCHAR, code_T VARCHAR, "
        "mask_T INTEGER)"
    )
    order = families()[:-1]
    rows: list[tuple[str, str, str | None, int | None]] = [
        (s, v, None, _mask(fs, order) or None) for (s, v), fs in t.sets.items() if s in SOURCES[:2]
    ]
    rows += [("route", v, c, None) for v, c in t.routes.items()]
    con.executemany(f"INSERT INTO {_SCRATCH[0]} VALUES (?, ?, ?, ?)", rows)
    for scratch, column in ((_SCRATCH[1], "route"), (_SCRATCH[2], "dose_form")):
        con.execute(f"""
CREATE TEMP TABLE {scratch} AS
SELECT v.raw_T, max(w.code_T) AS code_T, max(w.mask_T) AS mask_T
FROM (SELECT DISTINCT {column} AS raw_T FROM drug_latest_T WHERE {column} IS NOT NULL) v
JOIN {_SCRATCH[0]} w ON w.source_T = '{column}' AND w.key_T = {KEY_SQL.format(col="v.raw_T")}
GROUP BY v.raw_T""")
    words = {v.upper(): _mask(fs, order) for (s, v), fs in t.sets.items() if s == "drugname" and fs}
    hits = ", ".join(
        f"CASE WHEN regexp_matches(raw_T, {_text(rf'\b{w}\b')}) THEN {m} END"
        for w, m in sorted(words.items())
    )
    # A name's form words each say something: they intersect like any other source.
    con.execute(f"""
CREATE TEMP TABLE {_SCRATCH[3]} AS
SELECT raw_T, bit_and(m) AS i_T, bit_or(m) AS u_T
FROM (SELECT raw_T, unnest(list_filter([{hits or "NULL"}], lambda x: x IS NOT NULL)) AS m
      FROM (SELECT DISTINCT drugname_norm_T AS raw_T FROM drug_latest_T
            WHERE drugname_norm_T IS NOT NULL))
GROUP BY raw_T""")


def statement() -> str:
    """The SQL that writes drug_route_T, sources in the rule's order; with fill_in off,
    FDA's route alone."""
    order = rulebook.value(RULE, "sources")
    if sorted(order) != sorted(SOURCES):
        raise ValueError(
            f"rule drug-route: sources must be {', '.join(SOURCES)} in some order, not {order!r}"
        )
    if not rulebook.value(RULE, "fill_in"):
        order = [s for s in order if s == SOURCES[0]]
    unknown, unknown_code = families()[-1], rulebook.value(RULE, "unknown_code")
    disagree, none = rulebook.value(RULE, "disagree"), rulebook.value(RULE, "none")
    every = (1 << len(families()[:-1])) - 1
    # A name's form words can contradict each other, so a name names more than it allows.
    allows = {"route": "am", "dose_form": "bm", "drugname": "ni"}
    names = {**allows, "drugname": "nu"}
    allowed = " & ".join(f"coalesce({allows[s]}, {every})" for s in order)
    named = " | ".join(f"coalesce({names[s]}, 0)" for s in order)
    said = " OR ".join(f"{allows[s]} IS NOT NULL" for s in order)
    each_said = ", ".join(f"bool_or({allows[s]} IS NOT NULL) AS {s}_said" for s in order)
    contributed = ", ".join(f"CASE WHEN {s}_said THEN '{s}' END" for s in order)
    key = ", ".join(KEY)
    # Each row is read alone, then the rows are joined: FDA writes one row per dosage regimen,
    # and two regimens of one drug can both be true (by mouth and on the skin).
    return f"""
CREATE TABLE {TABLE} AS
WITH r AS (
  SELECT {", ".join(f"d.{k}" for k in KEY)}, a.code_T AS code_T, a.mask_T AS am, b.mask_T AS bm,
         n.i_T AS ni, n.u_T AS nu
  FROM drug_latest_T d
  LEFT JOIN {_SCRATCH[1]} a ON a.raw_T = d.route
  LEFT JOIN {_SCRATCH[2]} b ON b.raw_T = d.dose_form
  LEFT JOIN {_SCRATCH[3]} n ON n.raw_T = d.drugname_norm_T),
o AS (
  SELECT *, ({said}) AS said_T, ({allowed}) AS i_T, ({named}) AS u_T FROM r),
k AS (
  SELECT {key}, min(code_T) AS c1, max(code_T) AS c2,
         bit_or(CASE WHEN said_T AND i_T <> 0 THEN i_T WHEN said_T THEN u_T END) AS f_T,
         bool_or(said_T AND i_T = 0) AS split_T, {each_said}
  FROM o GROUP BY {key})
SELECT {key},
       CASE WHEN c1 = c2 THEN c1 WHEN c1 IS NOT NULL THEN '{unknown_code}' END AS route_T,
       CASE WHEN f_T IS NULL THEN '{none}' WHEN split_T THEN '{disagree}'
            ELSE array_to_string(list_filter([{contributed}], lambda s: s IS NOT NULL), '+')
       END AS route_source_T,
       CASE WHEN bit_count(f_T) = 1 THEN {_decode("f_T")} ELSE '{unknown}' END AS route_family_T,
       CASE WHEN f_T IS NOT NULL THEN {_decode("f_T")} END AS route_families_T
FROM k"""


# Switched off: every drug record, with no cleaned route.
OFF = """
CREATE TABLE {table} AS
SELECT {key}, NULL::VARCHAR AS route_T, '{none}' AS route_source_T, '{unknown}' AS route_family_T,
       NULL::VARCHAR AS route_families_T
FROM drug_latest_T GROUP BY ALL"""


def build(con: duckdb.DuckDBPyConnection, tables: RouteTables | None = None) -> None:
    """Write drug_route_T from drug_latest_T; the scratch tables go once it is built.
    `tables` replaces the reviewed tables, to see what a changed table would give."""
    if not rulebook.is_on(RULE):
        none, unknown = rulebook.value(RULE, "none"), families()[-1]
        con.execute(OFF.format(table=TABLE, key=", ".join(KEY), none=none, unknown=unknown))
        return
    sql = statement()
    _load(con, tables or RouteTables.read())
    con.execute(sql)
    for t in _SCRATCH:
        con.execute(f"DROP TABLE {t}")
