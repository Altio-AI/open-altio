"""The choice of one class per drug record (rule atc-class-choice), as steps of the
classes layer (`layer`), which runs them after it has found each record's possible codes.

    rule_tables(con)        # the rule's values as scratch tables, before the layer's steps
    for step in STEPS: ...  # on atc_possible_T, atc_records_T and the release's drug rows

Each record with two or more possible codes is chosen by its dose, then its route, then the
indication the report gives for it, among the codes dose and route leave open; a record none
decides gets the deepest class its codes share, or none. `atc_choice_T` holds what was chosen
and `atc_shared_T` the shared classes.
"""

from __future__ import annotations

import duckdb

from open_altio import rulebook

from ..route import TABLE as ROUTES
from ..route import RouteTables
from .whofile import LEVELS

RECORD = ("era_T", "primaryid", "quarter_T", "drug_seq")
_KEY = ", ".join(RECORD)
# what found a record's codes; a split combination's class is always "can't tell"
SPLIT = ("each_ingredient", "each_active_ingredient")
_SPLIT = ", ".join(f"'{m}'" for m in SPLIT)
SCRATCH = (
    "atc_facts_T",
    "atc_fit_codes_T",
    "atc_fits_T",
    "atc_doses_T",
    "atc_open_codes_T",
    "atc_indicated_T",
    "atc_choice_T",
    "atc_shared_T",
)
# the rule's values, as scratch tables dropped with the others
RULE_SCRATCH = (
    "atc_routes_T",
    "atc_group_codes_T",
    "atc_dose_rules_T",
    "atc_eye_and_ear_T",
    "atc_mix_T",
    "atc_shared_levels_T",
    "atc_indication_rules_T",
)


def _term(text: str) -> str:
    """An indication as it is matched: the whole term in lower case, without edge spaces,
    read the same way in SQL (`lower(trim(indi_pt))`)."""
    return text.strip().lower()


def _prefixes(con: duckdb.DuckDBPyConnection, table: str, prefixes: list[str]) -> None:
    con.execute(f"CREATE TEMP TABLE {table} (prefix_T VARCHAR)")
    if prefixes:
        con.executemany(f"INSERT INTO {table} VALUES (?)", [(p,) for p in prefixes])


def unfitted_groups() -> list[str]:
    """The route step's drug-class groups the rule gives no codes for; the layer refuses them."""
    groups = rulebook.value("atc-class-choice", "route_groups")
    return sorted(set(RouteTables.read().atc_groups.values()) - set(groups))


def rule_tables(con: duckdb.DuckDBPyConnection) -> None:
    """The route step's drug-class groups (rule drug-route), and the rule's fits, dose bounds,
    eye-and-ear codes, mix classes, indication rules and the levels a shared class may have, as
    scratch tables."""
    choice = rulebook.rule("atc-class-choice").values
    groups = choice["route_groups"]
    # each E2B route code in a group, as the route step reads a record's route
    con.execute("CREATE TEMP TABLE atc_routes_T (route_T VARCHAR, group_T VARCHAR)")
    con.executemany(
        "INSERT INTO atc_routes_T VALUES (?, ?)", sorted(RouteTables.read().atc_groups.items())
    )
    # the codes a group fits: its own, or every code but the local ones and its own exceptions
    con.execute(
        "CREATE TEMP TABLE atc_group_codes_T (group_T VARCHAR, prefix_T VARCHAR, fits_T BOOLEAN)"
    )
    con.executemany(
        "INSERT INTO atc_group_codes_T VALUES (?, ?, ?)",
        [(g, p, True) for g, spec in groups.items() for p in spec.get("codes", [])]
        + [
            (g, p, False)
            for g, spec in groups.items()
            if "codes" not in spec
            for p in choice["local_codes"] + spec.get("not_codes", [])
        ],
    )
    con.execute(
        "CREATE TEMP TABLE atc_dose_rules_T (substance_T VARCHAR, unit_T VARCHAR, "
        "at_most_T DOUBLE, at_least_T DOUBLE, freq_T VARCHAR[], atc_code_T VARCHAR)"
    )
    con.executemany(
        "INSERT INTO atc_dose_rules_T VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                d["substance"],
                d["unit"],
                d.get("at_most"),
                d.get("at_least"),
                d.get("freq"),
                d["code"],
            )
            for d in choice["dose_rules"]
        ],
    )
    _prefixes(con, "atc_eye_and_ear_T", choice["eye_and_ear_codes"])
    _prefixes(con, "atc_mix_T", choice["mix_classes"])
    length = {lvl: n for n, lvl in LEVELS.items()}  # an ATC level -> its code's length
    con.execute("CREATE TEMP TABLE atc_shared_levels_T (level_T INTEGER, length_T INTEGER)")
    con.executemany(
        "INSERT INTO atc_shared_levels_T VALUES (?, ?)",
        [(lvl, length[lvl]) for lvl in choice["shared_class_levels"]],
    )
    # an indication rule's terms, each a whole term, matched by equality in SQL
    con.execute(
        "CREATE TEMP TABLE atc_indication_rules_T (substance_T VARCHAR, term_T VARCHAR, "
        "atc_code_T VARCHAR)"
    )
    indications = sorted(
        {
            (r["substance"], _term(w), r["code"])
            for r in choice["indication_rules"]
            for w in r["indications"]
        }
    )
    if indications:
        con.executemany("INSERT INTO atc_indication_rules_T VALUES (?, ?, ?)", indications)


STEPS = (
    # what the records with a choice to make state: the route group of the route the route step
    # reads for the record, and the doses and frequencies of all its rows
    f"""CREATE TABLE atc_facts_T AS
       WITH open AS (
         SELECT record_T FROM atc_possible_T GROUP BY record_T
         HAVING count(DISTINCT atc_code_T) > 1
            AND any_value(atc_matched_on_T) NOT IN ({_SPLIT})),
       rows AS (
         SELECT r.record_T, upper(trim(d.dose_unit)) AS unit_T,
                CASE WHEN regexp_full_match(d.dose_amt, '[0-9]*\\.?[0-9]+')
                     THEN CAST(d.dose_amt AS DOUBLE) END AS amount_T,
                upper(trim(d.dose_freq)) AS freq_T
         FROM atc_records_T r SEMI JOIN open USING (record_T)
         JOIN drug_latest_T d USING ({_KEY})),
       doses AS (
         SELECT record_T, count(amount_T) AS doses_T,
                count(DISTINCT coalesce(unit_T, '')) FILTER (WHERE amount_T IS NOT NULL) AS units_T,
                min(unit_T) FILTER (WHERE amount_T IS NOT NULL) AS unit_T,
                min(amount_T) AS least_T, max(amount_T) AS most_T,
                list(DISTINCT freq_T) FILTER (WHERE freq_T IS NOT NULL) AS freqs_T
         FROM rows GROUP BY record_T)
       SELECT d.*, g.group_T
       FROM doses d JOIN atc_records_T r USING (record_T)
       LEFT JOIN {ROUTES} x USING ({_KEY})
       LEFT JOIN atc_routes_T g ON g.route_T = x.route_T""",
    # the codes the record's route group fits; an eye-and-ear code only when no other does
    """CREATE TABLE atc_fit_codes_T AS
       WITH fit AS (
         SELECT DISTINCT f.record_T, p.atc_code_T,
                EXISTS (SELECT 1 FROM atc_eye_and_ear_T e
                        WHERE starts_with(p.atc_code_T, e.prefix_T)) AS eye_and_ear_T
         FROM atc_facts_T f JOIN atc_possible_T p USING (record_T)
         WHERE f.group_T IS NOT NULL AND CASE
         WHEN EXISTS (SELECT 1 FROM atc_group_codes_T k WHERE k.group_T = f.group_T AND k.fits_T)
         THEN EXISTS (SELECT 1 FROM atc_group_codes_T k
                      WHERE k.group_T = f.group_T AND k.fits_T
                        AND starts_with(p.atc_code_T, k.prefix_T))
         ELSE NOT EXISTS (SELECT 1 FROM atc_group_codes_T k
                          WHERE k.group_T = f.group_T AND NOT k.fits_T
                            AND starts_with(p.atc_code_T, k.prefix_T)) END)
       SELECT record_T, atc_code_T FROM fit
       QUALIFY eye_and_ear_T = bool_and(eye_and_ear_T) OVER (PARTITION BY record_T)""",
    """CREATE TABLE atc_fits_T AS
       SELECT record_T, count(*) AS fits_T, min(atc_code_T) AS atc_code_T
       FROM atc_fit_codes_T GROUP BY record_T""",
    # the dose rule whose bound every stated dose meets, and whose frequencies, if it names any,
    # hold every frequency the record states, when its code is one of the record's
    """CREATE TABLE atc_doses_T AS
       SELECT f.record_T, min(d.atc_code_T) AS atc_code_T
       FROM atc_facts_T f JOIN atc_possible_T p USING (record_T)
       JOIN atc_dose_rules_T d ON d.substance_T = p.ingredient_T AND d.atc_code_T = p.atc_code_T
         AND d.unit_T = f.unit_T
       WHERE f.doses_T > 0 AND f.units_T = 1
         AND (f.most_T <= d.at_most_T OR f.least_T >= d.at_least_T)
         AND (d.freq_T IS NULL OR (len(f.freqs_T) > 0 AND list_has_all(d.freq_T, f.freqs_T)))
       GROUP BY f.record_T""",
    # the codes an indication may choose among, for the records dose and route leave open whose
    # substance an indication rule names: when their route is in a group, only the codes that
    # group fits (none when it fits none); otherwise all their codes
    """CREATE TABLE atc_open_codes_T AS
       SELECT p.record_T, p.ingredient_T, p.atc_code_T
       FROM atc_facts_T f ANTI JOIN atc_doses_T d USING (record_T)
       LEFT JOIN atc_fits_T t USING (record_T)
       JOIN atc_possible_T p USING (record_T)
       SEMI JOIN (SELECT DISTINCT substance_T AS ingredient_T FROM atc_indication_rules_T)
         USING (ingredient_T)
       LEFT JOIN atc_fit_codes_T k ON k.record_T = p.record_T AND k.atc_code_T = p.atc_code_T
       WHERE t.fits_T IS DISTINCT FROM 1 AND (f.group_T IS NULL OR k.record_T IS NOT NULL)""",
    # the code every indication the report gives for the drug that is a rule's whole term points
    # to, when it is one of those codes. Only the indications that are a rule's term, of only
    # those records, are read, and each is looked up by equality, so the step stays small
    f"""CREATE TABLE atc_indicated_T AS
       WITH records AS (
         SELECT {_KEY}, record_T FROM atc_records_T
         SEMI JOIN (SELECT DISTINCT record_T FROM atc_open_codes_T) USING (record_T)),
       said AS (
         SELECT DISTINCT r.record_T, lower(trim(i.indi_pt)) AS term_T
         FROM indi_latest_T i
         JOIN records r ON r.era_T = i.era_T AND r.primaryid = i.primaryid
           AND r.quarter_T = i.quarter_T AND r.drug_seq = i.indi_drug_seq
         SEMI JOIN (SELECT DISTINCT term_T FROM atc_indication_rules_T) t
           ON t.term_T = lower(trim(i.indi_pt)))
       SELECT o.record_T, min(x.atc_code_T) AS atc_code_T
       FROM said s JOIN atc_open_codes_T o USING (record_T)
       JOIN atc_indication_rules_T x ON x.substance_T = o.ingredient_T
         AND x.atc_code_T = o.atc_code_T AND x.term_T = s.term_T
       GROUP BY o.record_T
       HAVING count(DISTINCT x.atc_code_T) = 1""",
    f"""CREATE TABLE atc_choice_T AS
       WITH n AS (
         SELECT record_T, count(DISTINCT atc_code_T) AS codes_T,
                any_value(atc_matched_on_T) AS matched_on_T, min(atc_code_T) AS first_T,
                bool_or(group_T) AS group_T
         FROM atc_possible_T GROUP BY record_T)
       SELECT n.record_T, n.codes_T, n.matched_on_T,
              CASE WHEN n.matched_on_T IN ({_SPLIT}) THEN NULL
                   WHEN n.codes_T = 1 THEN n.first_T
                   WHEN d.atc_code_T IS NOT NULL THEN d.atc_code_T
                   WHEN f.fits_T = 1 THEN f.atc_code_T
                   WHEN i.atc_code_T IS NOT NULL THEN i.atc_code_T END AS atc_code_T,
              CASE WHEN n.matched_on_T IN ({_SPLIT}) THEN 'cannot_tell'
                   WHEN n.group_T THEN 'group_class'
                   WHEN n.codes_T = 1 THEN 'only_code'
                   WHEN d.atc_code_T IS NOT NULL THEN 'dose'
                   WHEN f.fits_T = 1 THEN 'route'
                   WHEN i.atc_code_T IS NOT NULL THEN 'indication'
                   ELSE 'cannot_tell' END AS chosen_by_T
       FROM n LEFT JOIN atc_doses_T d USING (record_T) LEFT JOIN atc_fits_T f USING (record_T)
       LEFT JOIN atc_indicated_T i USING (record_T)""",
    # the deepest allowed class the codes of a record it cannot tell share: the codes its route
    # group fits, when two or more do, else all its codes. Never for a split combination:
    # WHO classes a combination as a whole
    f"""CREATE TABLE atc_shared_T AS
       WITH open AS (
         SELECT record_T FROM atc_choice_T
         WHERE chosen_by_T = 'cannot_tell' AND matched_on_T NOT IN ({_SPLIT})),
       codes AS (
         SELECT record_T, atc_code_T FROM atc_fit_codes_T SEMI JOIN open USING (record_T)
         UNION ALL
         SELECT p.record_T, p.atc_code_T FROM atc_possible_T p SEMI JOIN open USING (record_T)
         ANTI JOIN atc_fit_codes_T f ON f.record_T = p.record_T),
       -- min = max rather than a distinct count, which on the full release runs out of memory
       shared AS (
         SELECT c.record_T, s.level_T, min(left(c.atc_code_T, s.length_T)) AS atc_code_T
         FROM codes c CROSS JOIN atc_shared_levels_T s
         GROUP BY c.record_T, s.level_T
         HAVING min(left(c.atc_code_T, s.length_T)) = max(left(c.atc_code_T, s.length_T)))
       SELECT record_T, arg_max(atc_code_T, level_T) AS atc_code_T FROM shared GROUP BY record_T""",
)

__all__ = [
    "RECORD",
    "ROUTES",
    "RULE_SCRATCH",
    "SCRATCH",
    "SPLIT",
    "STEPS",
    "rule_tables",
    "unfitted_groups",
]
