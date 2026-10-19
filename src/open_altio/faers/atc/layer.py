"""The drug classes layer of a release: WHO's ATC codes per drug record.

    from open_altio.faers.atc import layer
    entry = layer.build(con)        # on the release build's connection, after the derive steps

The layer reads our drug-to-class table (rule atc-index) and the substance each
drug record names, `drug_substance_T`: one row per drug record of
`drug_latest_T` (`era_T`, `primaryid`, `quarter_T`, `drug_seq`, unique) with
`substance_T`, one ingredient in lower case as the DiAna dictionary writes it,
or a combination's ingredients sorted and joined with `;`, NULL where the record
names none. A record's route is the one the route step reads for it, `route_T`
of `drug_route_T` (rule drug-route). A record is matched to the table by its
substance; one whose substance has no code, or that has none, by FDA's own words
on it, its drug name and then its active ingredient, each as a whole name and
read exactly as the RxNorm step reads them (`rxnorm.layer.FDA_WORDS`), so the
two never take a record's words differently; else a group word gets its group
class (rule atc-group-classes). It writes three tables, all named with the
rule's prefix so the whole layer can be left out or hidden at once:

    atc_index_T       every code the table holds, at every level, with WHO's name and the index year
    atc_drug_T        one row per drug record with a possible code: its one class, the broadest
                      class its possible codes share, or "can't tell", how it was chosen and from
                      how many possible codes (rule atc-class-choice)
    atc_drug_codes_T  every possible code of every such record, and which one was chosen

Switched off in a person's rules, or without the table, `drug_substance_T` or
`drug_route_T`, it writes nothing and says why. Every count it reports is of
cases (case_latest_T), never of rows.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import duckdb

from open_altio import rulebook

from ..drugnames.substances import PROD_AI_SEPARATOR
from ..rxnorm.layer import FDA_WORDS
from . import choice
from .choice import RECORD, SPLIT
from .table import COLUMNS, COMBINATION_NAME, SEPARATOR, TableRefused, read_groups, repo_path

SUBSTANCES = "drug_substance_T"
TABLES = ("atc_index_T", "atc_drug_T", "atc_drug_codes_T")
_KEY = ", ".join(RECORD)
_RECORD_OF_R = ", ".join(f"r.{c}" for c in RECORD)
_SCRATCH = ("atc_classes_T", "atc_records_T", "atc_possible_T", "atc_fda_T", "atc_groups_T")


class LayerRefused(Exception):
    """The class table cannot be joined as it stands; the message says why."""


def _text(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _groups_table(con: duckdb.DuckDBPyConnection, group_classes: dict[str, str]) -> None:
    con.execute("CREATE TEMP TABLE atc_groups_T (substance_T VARCHAR, atc_code_T VARCHAR)")
    if group_classes:
        con.executemany("INSERT INTO atc_groups_T VALUES (?, ?)", list(group_classes.items()))


# where each record's possible codes come from (rule atc-index); the choice's steps follow
MATCH = (
    # the table, read as text; a row with no ingredient names a class. mix_T marks a code
    # WHO names after one substance under a class it reserves for mixes, which a single
    # ingredient never takes; a code WHO names after the whole product is not one
    f"""CREATE TABLE atc_classes_T AS
       SELECT nullif(ingredient, '') AS ingredient_T, atc_code AS atc_code_T,
              who_name AS atc_name_T, level::INTEGER AS atc_level_T,
              index_year::INTEGER AS atc_index_year_T,
              EXISTS (SELECT 1 FROM atc_mix_T m WHERE starts_with(atc_code, m.prefix_T))
                AND NOT regexp_matches(lower(who_name), '{COMBINATION_NAME}') AS mix_T
       FROM read_csv({{table}}, header = true, all_varchar = true, quote = '"')""",
    """CREATE TABLE atc_index_T AS
       SELECT DISTINCT atc_code_T, atc_level_T, atc_name_T, atc_index_year_T
       FROM atc_classes_T ORDER BY atc_code_T""",
    # a number per record keeps the joins below small
    f"""CREATE TABLE atc_records_T AS
       SELECT row_number() OVER () AS record_T, {_KEY}, substance_T FROM {SUBSTANCES}""",
    # the whole substance or ingredient set first; a combination it misses, ingredient by ingredient
    f"""CREATE TABLE atc_possible_T AS
       WITH whole AS (
         SELECT r.record_T, c.ingredient_T, c.atc_code_T,
                CASE WHEN contains(r.substance_T, '{SEPARATOR}') THEN 'ingredient_set'
                     ELSE 'substance' END AS atc_matched_on_T
         FROM atc_records_T r JOIN atc_classes_T c ON c.ingredient_T = r.substance_T
         WHERE NOT c.mix_T OR contains(c.ingredient_T, '{SEPARATOR}')),
       parts AS (
         SELECT r.record_T,
                trim(unnest(string_split(r.substance_T, '{SEPARATOR}'))) AS ingredient_T
         FROM atc_records_T r ANTI JOIN whole USING (record_T)
         WHERE contains(r.substance_T, '{SEPARATOR}'))
       SELECT *, FALSE AS group_T FROM whole
       UNION ALL
       SELECT p.record_T, p.ingredient_T, c.atc_code_T, 'each_ingredient', FALSE
       FROM parts p JOIN atc_classes_T c USING (ingredient_T)""",
    # FDA's own words on a record its substance did not code, as one row per record
    f"""CREATE TABLE atc_fda_T AS
       SELECT r.record_T, w.drug_name_T AS name_T, w.prod_ai_T AS active_T
       FROM atc_records_T r ANTI JOIN atc_possible_T USING (record_T)
       JOIN ({FDA_WORDS}) w USING ({_KEY})""",
    # each as a whole name: the drug name, else the active ingredient, else the active
    # ingredient's parts as a set, only when every part is a name the table holds; never a part
    f"""INSERT INTO atc_possible_T
       WITH single AS (
         SELECT ingredient_T, atc_code_T FROM atc_classes_T
         WHERE ingredient_T IS NOT NULL AND (NOT mix_T OR contains(ingredient_T, '{SEPARATOR}'))),
       named AS (
         SELECT f.record_T, c.ingredient_T, c.atc_code_T, 'drug_name' AS atc_matched_on_T
         FROM atc_fda_T f JOIN single c ON c.ingredient_T = f.name_T),
       active AS (
         SELECT f.record_T, c.ingredient_T, c.atc_code_T, 'active_ingredient'
         FROM atc_fda_T f ANTI JOIN named USING (record_T)
         JOIN single c ON c.ingredient_T = f.active_T),
       parts AS (
         SELECT record_T, ingredient_T FROM (
           SELECT f.record_T,
                  trim(unnest(string_split(f.active_T, '{PROD_AI_SEPARATOR}'))) AS ingredient_T
           FROM atc_fda_T f ANTI JOIN named USING (record_T) ANTI JOIN active USING (record_T)
           WHERE contains(f.active_T, '{PROD_AI_SEPARATOR}'))
         WHERE ingredient_T <> ''),
       known AS (
         SELECT DISTINCT ingredient_T FROM atc_classes_T
         WHERE ingredient_T IS NOT NULL AND NOT contains(ingredient_T, '{SEPARATOR}')),
       sets AS (
         SELECT p.record_T,
                array_to_string(list_sort(list_distinct(list(p.ingredient_T))), '{SEPARATOR}')
                  AS set_T
         FROM parts p LEFT JOIN known k ON k.ingredient_T = p.ingredient_T
         GROUP BY p.record_T
         HAVING count(k.ingredient_T) = count(*) AND count(DISTINCT p.ingredient_T) > 1),
       whole AS (
         SELECT s.record_T, c.ingredient_T, c.atc_code_T, 'active_ingredient_set'
         FROM sets s JOIN atc_classes_T c ON c.ingredient_T = s.set_T)
       SELECT *, FALSE FROM named
       UNION ALL SELECT *, FALSE FROM active
       UNION ALL SELECT *, FALSE FROM whole
       UNION ALL
       SELECT DISTINCT p.record_T, p.ingredient_T, c.atc_code_T, 'each_active_ingredient', FALSE
       FROM parts p SEMI JOIN sets USING (record_T) ANTI JOIN whole USING (record_T)
       JOIN atc_classes_T c USING (ingredient_T)""",
    # else a group word's class, marked as a group class (rule atc-group-classes)
    f"""INSERT INTO atc_possible_T
       SELECT r.record_T, r.substance_T, g.atc_code_T,
              CASE WHEN contains(r.substance_T, '{SEPARATOR}') THEN 'ingredient_set'
                   ELSE 'substance' END, TRUE
       FROM atc_records_T r ANTI JOIN atc_possible_T USING (record_T)
       JOIN atc_groups_T g USING (substance_T)""",
)
# the layer's own tables, from the choice
WRITE = (
    f"""CREATE TABLE atc_drug_T AS
       SELECT {_RECORD_OF_R}, coalesce(c.atc_code_T, s.atc_code_T) AS atc_code_T, i.atc_level_T,
              y.year_T AS atc_index_year_T,
              CASE WHEN s.atc_code_T IS NULL THEN c.chosen_by_T ELSE 'shared_class' END
                AS atc_chosen_by_T,
              c.codes_T AS atc_possible_codes_T, c.matched_on_T AS atc_matched_on_T
       FROM atc_choice_T c JOIN atc_records_T r USING (record_T)
       LEFT JOIN atc_shared_T s USING (record_T)
       LEFT JOIN atc_index_T i ON i.atc_code_T = coalesce(c.atc_code_T, s.atc_code_T)
       CROSS JOIN (SELECT max(atc_index_year_T) AS year_T FROM atc_index_T) y""",
    f"""CREATE TABLE atc_drug_codes_T AS
       SELECT {_RECORD_OF_R}, p.ingredient_T AS atc_ingredient_T, p.atc_code_T,
              i.atc_level_T, i.atc_index_year_T,
              p.atc_code_T IS NOT DISTINCT FROM c.atc_code_T AS atc_chosen_T
       FROM atc_possible_T p JOIN atc_records_T r USING (record_T)
       JOIN atc_choice_T c USING (record_T)
       JOIN atc_index_T i ON i.atc_code_T = p.atc_code_T""",
)

CASES = """
WITH coded AS (SELECT era_T, primaryid, quarter_T, bool_or(atc_code_T IS NOT NULL) AS chosen_T,
                      bool_or(atc_chosen_by_T = 'shared_class') AS shared_T,
                      bool_or(atc_chosen_by_T = 'cannot_tell') AS cannot_tell_T
               FROM atc_drug_T GROUP BY ALL)
SELECT count(*), count(*) FILTER (WHERE chosen_T), count(*) FILTER (WHERE shared_T),
       count(*) FILTER (WHERE cannot_tell_T)
FROM case_latest_T c JOIN coded USING (era_T, primaryid, quarter_T)
WHERE c.dup_kept_T
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _header(path: Path) -> tuple[str, ...]:
    with path.open(encoding="utf-8", newline="") as fh:
        return tuple(next(csv.reader(fh), ()))


def build(
    con: duckdb.DuckDBPyConnection, table: Path | None = None, groups: Path | None = None
) -> dict:
    """Write the layer's tables on `con` and return its manifest entry. When the person's rules
    switch the classes off, or the table, the substances or the routes are missing, write
    nothing and say why."""
    index = rulebook.rule("atc-index").values
    path = table or repo_path("atc-index", "table")
    absent = {"present": False, "source": index["source"]}
    if not rulebook.is_on("atc-index"):  # the one switch of all four class rules
        return {**absent, "reason": "switched off in your rules"}
    if not path.is_file():
        return {**absent, "reason": f"no class table at {rulebook.value('atc-index', 'table')}"}
    have = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM duckdb_tables() UNION SELECT view_name FROM duckdb_views()"
        ).fetchall()
    }
    if SUBSTANCES not in have:
        return {**absent, "reason": f"no substance per drug record ({SUBSTANCES})"}
    if choice.ROUTES not in have:
        return {**absent, "reason": f"no cleaned route per drug record ({choice.ROUTES})"}
    if _header(path) != COLUMNS:
        raise LayerRefused(f"{path.name} must have the columns {', '.join(COLUMNS)}")
    groups_path = groups or repo_path("atc-group-classes", "mapping")
    try:
        group_classes = read_groups(groups_path)
    except TableRefused as e:
        raise LayerRefused(str(e)) from e
    unfitted = choice.unfitted_groups()
    if unfitted:
        raise LayerRefused(
            f"rule atc-class-choice gives no codes for the route groups {', '.join(unfitted)}"
        )
    choice.rule_tables(con)
    _groups_table(con, group_classes)
    for step in MATCH[:2]:  # the table and its index, checked before any record is read
        con.execute(step.format(table=_text(path.as_posix())))
    years = [
        r[0] for r in con.execute("SELECT DISTINCT atc_index_year_T FROM atc_index_T").fetchall()
    ]
    if years != [int(index["index_year"])]:
        raise LayerRefused(
            f"{path.name} holds index years {years}; rule atc-index pins {index['index_year']}"
        )
    unheld = [
        r[0]
        for r in con.execute(
            "SELECT atc_code_T FROM atc_groups_T ANTI JOIN atc_index_T USING (atc_code_T)"
        ).fetchall()
    ]
    if unheld:
        raise LayerRefused(
            f"{groups_path.name} names {', '.join(sorted(unheld))}, which {path.name} does not"
            " hold; build the table again"
        )
    for step in MATCH[2:] + choice.STEPS + WRITE:
        con.execute(step)
    for scratch in _SCRATCH + choice.SCRATCH + choice.RULE_SCRATCH:
        con.execute(f"DROP TABLE {scratch}")
    coded, chosen, shared, cannot_tell = con.execute(CASES).fetchall()[0]
    return {
        "present": True,
        "source": index["source"],
        "index_year": int(index["index_year"]),
        "citation": index["citation"],
        "table": {"path": rulebook.value("atc-index", "table"), "sha256": _sha256(path)},
        "groups": {
            "path": rulebook.value("atc-group-classes", "mapping"),
            "sha256": _sha256(groups_path),
        },
        "prefix": index["table_prefix"],
        "tables": list(TABLES),
        "cases": {
            "with_a_coded_drug": int(coded),
            "with_a_class": int(chosen),
            "with_a_shared_class": int(shared),
            "with_cannot_tell": int(cannot_tell),
        },
    }


__all__ = ["RECORD", "SPLIT", "SUBSTANCES", "TABLES", "LayerRefused", "build"]
