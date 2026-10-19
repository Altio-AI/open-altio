"""Probable duplicates across cases: the build step that flags them, and the plain words that say
why a case is shown or set aside.

Two rules make groups (rules/dedup-default.md), and groups that share a case are linked into one:

1. AEOLUS (Banda et al. 2016): two cases agreeing on event date, age, age unit, sex, country, the
   normalised drug set and the reaction (PT) set. The key is FDA's raw text across eras, none of it
   Not given (rules/not-given.md: blank, says unknown or a filler, such as an age of 999), except
   that sex is sex_T, F or M (rules/sex-codes.md), so NS or UNK is never compared, and reaction
   terms are compared in capitals (rules/reaction-term-case.md).
   Country is country_T, the occurrence country, else the reporter country: legacy AERS publishes
   no occurrence country, so a legacy case matches on its reporter country, read as its ISO code
   (rules/legacy-country.md), and a legacy quarter in the 2004Q1 layout (no REPORTER_COUNTRY) is
   never compared. FDA's words for no country are none (rules/country-not-given.md), and an EU
   case is compared as EU even where an earlier version gave its member state
   (rules/eu-member-state.md). A group of min_group_size or more whose shared event date is padded
   (1 January, or a month or year only) and whose cases all come from one sender sets nothing aside
   (rules/dup-padded-event-dates.md).
2. The same manufacturer case number from the same sender, trimmed and in capitals, where a number
   without its country code joins the one coded form of it; a number group whose cases clash on
   sex or on age is skipped (rules/dup-manufacturer-number.md).

Each group shows one copy, chosen by rules/dup-shown-copy.md, and is dated by its earliest
receipt. A case with no group under either rule is kept. Nothing is deleted.

    from open_altio.faers.duplicates import reason_lines
    reason_lines(case)      # a row of case_latest_T or explorer_case_T, as a mapping

The reason lines are the rule's own sentences, so the screens and the rule cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import date
from typing import Any

import duckdb

from open_altio import rulebook

from . import not_given
from .reader import quoted, sql_in
from .schema import EARLIER_VERSION

# One build step: SQL text, or a callable taking the connection where a step loops.
Statement = str | Callable[[duckdb.DuckDBPyConnection], None]

SHOWN_RULE = "dup-shown-copy"

# The drug set and the reaction set of each case, as the key spells them: distinct values,
# sorted, joined with '|', and whether any value is usable (rules/no-drug-or-reaction.md). Built
# one quarter at a time (a case's rows all carry its quarter_T), because DuckDB holds an ordered
# aggregate's state in memory: over all 90 quarters at once it needs more than 16 GB, a quarter
# at a time a few hundred MB. Scratch tables, dropped once case_dup_T is built.
DUP_SETS = {
    "dup_drugs_T": ("drugs", "drug_latest_T", "drugname_norm_T", "unusable_drug_names"),
    "dup_pts_T": ("pts", "reac_latest_T", "pt_norm_T", "no_event_terms"),
}

# The case's own fields the AEOLUS key compares; one that reads Not given (rule not-given) leaves
# the case with no key, like a blank. Sex is sex_T (rules/sex-codes.md), so a sex not known is
# never compared.
KEY_FIELDS = ("event_dt", "age", "age_cod", "sex_T", "country_T")

# One row per case with what both rules compare (scratch). The country is country_T as the case's
# own version gives it: a member state taken from an earlier version (rules/eu-member-state.md)
# is compared as the EU it was published as, so that taking it never splits a group.
DUP_KEYS_T = """
CREATE TABLE dup_keys_T AS
SELECT c.era_T, c.case_key_T, c.caseid, c.primaryid, c.quarter_T, c.first_fda_dt_T, c.event_dt,
       c.age_years_T,
       CASE WHEN {clashing_sex} THEN upper(trim(c.sex)) END AS sex_T,
       CASE WHEN NOT {key_not_given} AND d.drugs IS NOT NULL AND r.pts IS NOT NULL
            THEN concat_ws('|', c.event_dt, c.age, c.age_cod, c.sex_T, {country}, d.drugs, r.pts)
            END AS dup_key_T,
       nullif(upper(trim(c.mfr_sndr)), '') AS sender_T,
       nullif(upper(trim(c.mfr_num)), '') AS number_T,
       {no_drug_or_reaction} AS no_drug_or_reaction_T
FROM case_latest_T c
LEFT JOIN dup_drugs_T d USING (era_T, primaryid, quarter_T)
LEFT JOIN dup_pts_T r USING (era_T, primaryid, quarter_T)
"""

# The manufacturer number as compared, for every case with a number and a sender (scratch). A
# number without the country code takes the coded form when the sender wrote it with exactly one
# code. The join is on equalities only, so DuckDB hash-joins it; a one-sided condition in the ON
# clause of a LEFT JOIN makes it a nested loop over millions of rows.
DUP_NUMBERS_T = """
CREATE TABLE dup_numbers_T AS
WITH n AS (
  SELECT era_T, case_key_T, sender_T, number_T, regexp_matches(number_T, {code}) AS coded_T
  FROM dup_keys_T WHERE sender_T IS NOT NULL AND number_T IS NOT NULL),
coded AS (
  SELECT sender_T, regexp_replace(number_T, {code}, '') AS bare_T,
         min(number_T) AS number_T, count(DISTINCT number_T) AS codes_T
  FROM n WHERE coded_T GROUP BY ALL)
SELECT n.era_T, n.case_key_T,
       concat_ws('|', n.sender_T,
                 CASE WHEN NOT n.coded_T AND c.codes_T = 1 THEN c.number_T ELSE n.number_T END)
         AS dup_number_key_T,
       coalesce(NOT n.coded_T AND c.codes_T = 1, false) AS code_added_T
FROM n LEFT JOIN coded c ON c.sender_T = n.sender_T AND c.bare_T = n.number_T
"""

# Every case in a group of two or more under either rule, with the key under which it groups
# after each rule's guard (scratch). A padded AEOLUS group from one sender (a blank sender counts
# as another) or a guarded number group gives no key, and a rule switched off makes no groups.
DUP_MEMBERS_T = """
CREATE TABLE dup_members_T AS
WITH k AS (
  SELECT d.era_T, d.case_key_T, d.caseid, d.first_fda_dt_T, d.event_dt, d.age_years_T, d.sex_T,
         d.dup_key_T, d.sender_T, n.dup_number_key_T, n.code_added_T
  FROM dup_keys_T d LEFT JOIN dup_numbers_T n USING (era_T, case_key_T)),
a AS (
  SELECT dup_key_T,
         {padded_on} AND count(*) >= {min_size} AND (length(any_value(event_dt)) < {full_length}
             OR (length(any_value(event_dt)) = {full_length}
                 AND right(any_value(event_dt), {md_length}) = {month_day}))
           AND ({any_sender} OR (count(sender_T) = count(*) AND min(sender_T) = max(sender_T)))
           AS padded_T
  FROM k WHERE {aeolus_on} AND dup_key_T IS NOT NULL GROUP BY 1 HAVING count(*) > 1),
m AS (
  SELECT dup_number_key_T, bool_or(code_added_T) AS code_added_T,
         count(DISTINCT sex_T) > 1
           OR coalesce(max(age_years_T) - min(age_years_T) > {max_gap}, false) AS guarded_T
  FROM k WHERE {number_on} AND dup_number_key_T IS NOT NULL GROUP BY 1 HAVING count(*) > 1)
SELECT k.era_T, k.case_key_T, k.caseid, k.first_fda_dt_T,
       CASE WHEN NOT a.padded_T THEN k.dup_key_T END AS aeolus_key_T,
       coalesce(a.padded_T, false) AS padded_T,
       CASE WHEN NOT m.guarded_T THEN k.dup_number_key_T END AS number_key_T,
       coalesce(m.code_added_T, false) AS code_added_T
FROM k LEFT JOIN a USING (dup_key_T) LEFT JOIN m USING (dup_number_key_T)
WHERE a.dup_key_T IS NOT NULL OR m.dup_number_key_T IS NOT NULL
"""

# Linking: each case starts with its own number as its label; each step gives every case the
# lowest label in either of its two groups. When no label changes, cases with the same label are
# one group (scratch).
DUP_LINKS_T = """
CREATE TABLE dup_links_T AS
WITH m AS (
  SELECT era_T, case_key_T, aeolus_key_T, number_key_T,
         row_number() OVER (ORDER BY era_T, case_key_T) AS node_T
  FROM dup_members_T WHERE aeolus_key_T IS NOT NULL OR number_key_T IS NOT NULL)
SELECT era_T, case_key_T, node_T, node_T AS label_T,
       CASE WHEN aeolus_key_T IS NOT NULL THEN min(node_T) OVER (PARTITION BY aeolus_key_T)
            ELSE -node_T END AS a_T,
       CASE WHEN number_key_T IS NOT NULL THEN min(node_T) OVER (PARTITION BY number_key_T)
            ELSE -node_T END AS m_T
FROM m
"""

DUP_LINK_STEP = """
UPDATE dup_links_T SET label_T = s.label_T
FROM (SELECT node_T, least(min(label_T) OVER (PARTITION BY a_T),
                           min(label_T) OVER (PARTITION BY m_T)) AS label_T
      FROM dup_links_T) s
WHERE dup_links_T.node_T = s.node_T AND s.label_T < dup_links_T.label_T
"""

# The order that picks the shown copy (rules/dup-shown-copy.md).
SHOWN_ORDER = {
    "latest_received": (
        "first_fda_dt_T DESC NULLS LAST, caseid DESC NULLS LAST, era_T ASC, case_key_T DESC"
    ),
    "earliest_received": (
        "first_fda_dt_T ASC NULLS LAST, caseid ASC NULLS LAST, era_T ASC, case_key_T ASC"
    ),
}

# One row per case in case_latest_T. dup_rule_T names the rules that put the case in its group;
# the shown copy carries the others, earliest received first. The serious-outcome flag is
# rules/no-drug-or-reaction.md.
CASE_DUP_T = """
CREATE TABLE case_dup_T AS
WITH s AS (
  SELECT l.era_T, l.case_key_T, l.label_T AS dup_group_T,
         list_filter([CASE WHEN m.aeolus_key_T IS NOT NULL THEN 'aeolus' END,
                      CASE WHEN m.number_key_T IS NULL THEN NULL
                           WHEN m.code_added_T THEN 'manufacturer_number_country_code'
                           ELSE 'manufacturer_number' END], lambda x: x IS NOT NULL) AS dup_rule_T,
         min(m.first_fda_dt_T) OVER (PARTITION BY l.label_T) AS group_first_dt_T,
         row_number() OVER (PARTITION BY l.label_T ORDER BY {shown_order}) AS shown_pos_T
  FROM dup_links_T l JOIN dup_members_T m USING (era_T, case_key_T)),
g AS (
  SELECT dup_group_T, arg_min(case_key_T, shown_pos_T) AS dup_shown_case_T,
         list(case_key_T ORDER BY shown_pos_T DESC) FILTER (WHERE shown_pos_T > 1) AS others_T
  FROM s GROUP BY 1),
serious AS (
  SELECT DISTINCT era_T, primaryid, quarter_T FROM outc_latest_T WHERE {serious})
SELECT k.era_T, k.case_key_T, k.caseid, k.dup_key_T, n.dup_number_key_T, s.dup_group_T,
       s.dup_group_T IS NOT NULL AS probable_duplicate_T,
       coalesce(s.shown_pos_T = 1, true) AS dup_kept_T,
       coalesce(s.group_first_dt_T, k.first_fda_dt_T) AS group_first_dt_T,
       s.dup_rule_T, g.dup_shown_case_T,
       CASE WHEN s.shown_pos_T = 1 THEN g.others_T END AS dup_other_cases_T,
       coalesce(m.padded_T, false) AS dup_padded_date_T,
       k.no_drug_or_reaction_T,
       k.no_drug_or_reaction_T AND o.primaryid IS NOT NULL AS serious_no_drug_or_reaction_T
FROM dup_keys_T k
LEFT JOIN dup_numbers_T n USING (era_T, case_key_T)
LEFT JOIN dup_members_T m USING (era_T, case_key_T)
LEFT JOIN s USING (era_T, case_key_T)
LEFT JOIN g USING (dup_group_T)
LEFT JOIN serious o USING (era_T, primaryid, quarter_T)
"""

DUP_SCRATCH = (*DUP_SETS, "dup_keys_T", "dup_numbers_T", "dup_members_T", "dup_links_T")

DUP_FLAGS = (
    "probable_duplicate_T",
    "dup_group_T",
    "dup_kept_T",
    "group_first_dt_T",
    "dup_rule_T",
    "dup_shown_case_T",
    "dup_other_cases_T",
    "no_drug_or_reaction_T",
    "serious_no_drug_or_reaction_T",
)

# The flags also go onto the case table itself, so the explorer filters one table
# (WHERE dup_kept_T) with no join; every case stays.
CASE_LATEST_FLAGGED = (
    "CREATE TABLE case_latest_flagged_T AS SELECT c.*, "
    + ", ".join(f"k.{f}" for f in DUP_FLAGS)
    + " FROM case_latest_T c JOIN case_dup_T k USING (era_T, case_key_T)",
    "DROP TABLE case_latest_T",
    "ALTER TABLE case_latest_flagged_T RENAME TO case_latest_T",
)


def _sql_bool(flag: bool) -> str:
    return "true" if flag else "false"


def _sets_for(quarter: str) -> Iterator[str]:
    """Fill the set tables for one quarter_T."""
    for table, (_, source, value, unusable) in DUP_SETS.items():
        usable = sql_in(f"upper({value})", rulebook.value("no-drug-or-reaction", unusable))
        yield (
            f"INSERT INTO {table} SELECT era_T, primaryid, quarter_T, "
            f"string_agg(DISTINCT {value}, '|' ORDER BY {value}), bool_or(NOT ({usable})) "
            f"FROM {source} WHERE {value} IS NOT NULL AND quarter_T = {quoted(quarter)} "
            "GROUP BY era_T, primaryid, quarter_T"
        )


def link_groups(con: duckdb.DuckDBPyConnection) -> None:
    """Run the linking step until no label changes."""
    changed = True
    while changed:
        changed = con.execute(DUP_LINK_STEP).fetchall()[0][0] > 0


def statements(quarters: Sequence[str]) -> Iterator[Statement]:
    """The duplicate step in order, over case_latest_T and its child tables: SQL text, and the
    linking loop as a callable taking the connection. Leaves the flags on case_latest_T."""
    for table, (column, _, _, _) in DUP_SETS.items():
        yield (
            f"CREATE TABLE {table} (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
            f"{column} VARCHAR, usable_T BOOLEAN)"
        )
    for quarter in quarters:
        yield from _sets_for(quarter)
    number = {
        k: rulebook.value("dup-manufacturer-number", k)
        for k in ("clashing_sexes", "max_age_gap_years", "country_code")
    }
    padded = {
        k: rulebook.value("dup-padded-event-dates", k)
        for k in ("min_group_size", "full_date_length", "padded_month_day", "one_sender_only")
    }
    shown = rulebook.value(SHOWN_RULE, "shown_copy")
    if shown not in SHOWN_ORDER:
        raise ValueError(
            f"rules/dup-shown-copy.md: shown_copy must be one of {list(SHOWN_ORDER)}, not {shown!r}"
        )
    marks = "NOT (coalesce(d.usable_T, false) AND coalesce(r.usable_T, false))"
    eu = quoted(rulebook.value("eu-member-state", "code"))
    yield DUP_KEYS_T.format(
        country=f"(CASE WHEN c.country_source_T = {quoted(EARLIER_VERSION)} THEN {eu} "
        "ELSE c.country_T END)",
        clashing_sex=sql_in("upper(trim(c.sex))", number["clashing_sexes"]),
        no_drug_or_reaction=marks if rulebook.is_on("no-drug-or-reaction") else "false",
        key_not_given="(" + " OR ".join(not_given.check(f, f"c.{f}") for f in KEY_FIELDS) + ")",
    )
    yield DUP_NUMBERS_T.format(code=quoted(number["country_code"]))
    yield DUP_MEMBERS_T.format(
        min_size=int(padded["min_group_size"]),
        full_length=int(padded["full_date_length"]),
        md_length=len(padded["padded_month_day"]),
        month_day=quoted(padded["padded_month_day"]),
        any_sender="false" if padded["one_sender_only"] else "true",
        max_gap=float(number["max_age_gap_years"]),
        padded_on=_sql_bool(rulebook.is_on("dup-padded-event-dates")),
        aeolus_on=_sql_bool(rulebook.is_on("dedup-default")),
        number_on=_sql_bool(rulebook.is_on("dup-manufacturer-number")),
    )
    yield DUP_LINKS_T
    yield link_groups
    serious = rulebook.value("no-drug-or-reaction", "serious_outcome_codes")
    yield CASE_DUP_T.format(
        shown_order=SHOWN_ORDER[shown], serious=sql_in("upper(trim(outc_cod))", serious)
    )
    for table in DUP_SCRATCH:
        yield f"DROP TABLE {table}"
    yield from CASE_LATEST_FLAGGED


def _cases(keys: Sequence[str]) -> str:
    """case 1; cases 1 and 2; cases 1, 2 and 3."""
    keys = list(keys)
    if len(keys) == 1:
        return f"case {keys[0]}"
    return "cases " + ", ".join(keys[:-1]) + f" and {keys[-1]}"


def _month(day: date | None) -> str:
    return f"{day:%B %Y}" if day else "on a date FDA did not give"


def reason_lines(case: Mapping[str, Any]) -> list[str]:
    """Why a case is shown or set aside, one sentence a line. A set-aside copy gets the line
    naming the shown copy, then one line per rule that grouped it; the shown copy gets one line
    naming the copies set aside and the month its group was first received; a case in no group
    gets none."""
    if not case.get("probable_duplicate_T"):
        return []
    if case["dup_kept_T"]:
        return [
            rulebook.value(SHOWN_RULE, "shown_line").format(
                other_cases=_cases(case["dup_other_cases_T"]),
                first_received=_month(case["group_first_dt_T"]),
            )
        ]
    per_rule = rulebook.value(SHOWN_RULE, "rule_lines")
    aside = rulebook.value(SHOWN_RULE, "set_aside_line").format(shown_case=case["dup_shown_case_T"])
    return [aside] + [per_rule[r] for r in case["dup_rule_T"]]


__all__ = ["CASE_DUP_T", "DUP_FLAGS", "Statement", "reason_lines", "statements"]
