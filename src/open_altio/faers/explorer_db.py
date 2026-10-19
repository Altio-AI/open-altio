"""The explorer's database: one DuckDB file in the release folder, built from
the release's own Parquet, laid out so case-level filters stay fast on the
full 20 million cases on one small box.

    from open_altio.faers import build_explorer_db
    build_explorer_db("releases/2026Q2")     # writes releases/2026Q2/explorer.duckdb

    python -m open_altio.faers explorer releases/2026Q2

The release build calls it last (src/open_altio/faers/release.py). Its tables:

- `explorer_case_T`: one row per case in `case_latest_T` (every case; the
  duplicate flags are columns), numbered `case_id_T` in (era_T, case_key_T)
  order and stored in that order, with the typed columns the filters use; sex,
  age, weight and country are the release's own, read by their rules.
  Received-date filters and sorting use `group_first_dt_T`, the earliest
  receipt of the case's duplicate group (rules/dup-shown-copy.md).
- `explorer_sender_T`: each sender spelling and company name, in capitals and trimmed, with the
  `company_T` it names (rule company-names), so the sender filter finds a company by either.
- `explorer_drug_term_T`, `explorer_reac_term_T`: (term, case) pairs sorted
  by term, so an equality filter on a drug or reaction reads only the row
  groups holding that term (DuckDB's min/max zone maps), then joins to the
  cases by `case_id_T`.
- `explorer_ingredient_T`, `explorer_no_ingredient_T`: the same for a drug's
  ingredients (rule drug-names), sorted by ingredient, with each record's
  spelling and role; and the spellings of the records with none, sorted by
  spelling. `explorer_drug_name_T` holds each of FDA's names (`drugname`,
  `prod_ai`) with the ingredients its records were read to, sorted by name.
- `explorer_drug_T`, `explorer_reac_T`, `explorer_outc_T`, `explorer_ther_T`,
  `explorer_indi_T`: the child `_latest_T` rows with FDA's columns verbatim,
  keyed and sorted by `case_id_T`, for the case list and drill-in. A drug row
  carries its record's time to onset and why it has none (`drug_onset_T`), a
  therapy row its clean dates and duration.
- `explorer_statistics_T`, `explorer_statistics_strata_T`: the release's `statistics_T` and
  `statistics_strata_T`, where it has them, sorted by ingredient and reaction, for the
  Statistics tab and a pair's ROR by age band and by sex; with `explorer_statistics_as_published_T`
  and `explorer_statistics_strata_as_published_T`, the same counted by FDA's text, where the
  release holds MedDRA. `replace_statistics` puts recounted ones in a release already built
  (statistics.recount).
- `explorer_atc_class_T`, `explorer_atc_drug_T`, `explorer_atc_term_T`,
  `explorer_atc_could_T`: WHO's drug classes, where the release carries its classes
  layer (`CLASS_TABLES`): the classes; each drug record's one class and its possible
  codes, by case; (class, role, case) for the records with a class, sorted by class;
  and (possible code, the record's class, role, case) for the records whose class is
  not one exact code, sorted by code, for the class filter's "could be".
- `explorer_atc_statistics_T`, `explorer_atc_statistics_ingredients_T`: the release's class
  statistics (`atc_statistics_T`, `atc_statistics_ingredients_T`), where it has them beside
  its classes layer, sorted by level and class, and by ingredient: the Statistics tab's list by
  class and a drug's class beside its own. `replace_statistics` puts them in a release already
  built (statistics.add_classes).
- `explorer_release_T`: which release the file was built from.

Nothing here changes a value: FDA's columns are copied as published, and
every column we derive ends in `_T`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import duckdb

from open_altio import rulebook

from . import spelling
from .atc import layer as classes_layer
from .dates import ONSET_TABLE
from .drugnames.dictionary import SEPARATOR
from .drugnames.substances import SUBSTANCES
from .reader import EXPLORER_FILE, MANIFEST_FILE, read_manifest, register_release, write_manifest
from .schema import RAW_COLUMNS, misnamed

# The child rows the drill-in shows: table -> FDA columns kept (the case keys
# become case_id_T) and their order within a case.
CHILD_ORDER = {
    "drug": "try_cast(d.drug_seq AS BIGINT), d.drug_seq",
    "reac": "d.pt",
    "outc": "d.outc_cod",
    "ther": "try_cast(d.dsg_drug_seq AS BIGINT), d.dsg_drug_seq, d.start_dt",
    "indi": "try_cast(d.indi_drug_seq AS BIGINT), d.indi_drug_seq, d.indi_pt",
}
_KEYS = ("primaryid", "caseid", "era_T", "quarter_T")


def reaction_key(column: str) -> str:
    """SQL: the reaction text in `column` as the explorer matches it, case-blind: lower case,
    runs of whitespace as one space, trimmed, empty as NULL. `reaction_term` does the same to
    what a person types."""
    return rf"nullif(trim(regexp_replace(lower({column}), '\s+', ' ', 'g')), '')"


# Every case's number: one per case in (era_T, case_key_T) order. Only the keys are sorted, so the
# number costs little memory however many cases the release holds.
KEYS_TABLE = """
CREATE TEMP TABLE case_keys AS
SELECT row_number() OVER (ORDER BY era_T, case_key_T) AS case_id_T, era_T, primaryid, quarter_T
FROM case_latest_T
"""

# The tables kept in case order are written a part of the cases at a time, in order: each part's
# rows are joined and sorted alone, so the build's memory and spill do not grow with the release
# (rule explorer-build-memory), and the table holds the rows one pass in case order would.
PART = "part_keys"
PART_KEYS = (
    f"CREATE OR REPLACE TEMP TABLE {PART} AS SELECT * FROM case_keys "
    "WHERE case_id_T BETWEEN ? AND ?"
)


def in_part(table: str) -> str:
    """SQL: `table`'s rows of the part's cases only, so a join reads no other case's rows."""
    return f"(SELECT t.* FROM {table} t SEMI JOIN {PART} USING (era_T, primaryid, quarter_T))"


CASE_TABLE = f"""
WITH o AS (
  SELECT era_T, primaryid, quarter_T, list_sort(list_distinct(list(outc_cod))) AS outcomes_T
  FROM {in_part("outc_latest_T")} WHERE outc_cod IS NOT NULL GROUP BY ALL)
SELECT k.case_id_T,
  c.era_T, c.case_key_T, c.caseid, c.primaryid, c.quarter_T, c.caseversion, c.i_f_code, c.rept_cod,
  c.first_fda_dt_T, c.init_fda_dt, c.fda_dt, c.event_dt, c.event_dt_T, c.event_dt_prec_T,
  c.age, c.age_cod, c.age_years_T, c.age_band_T, c.sex, c.sex_T, c.wt, c.wt_cod, c.wt_kg_T,
  c.occr_country, c.reporter_country, c.country_T, c.country_source_T,
  c.occp_cod, c.reporter_type_T, c.mfr_sndr, c.company_T,
  c.dup_kept_T, c.probable_duplicate_T, c.dup_group_T, c.group_first_dt_T, c.dup_rule_T,
  c.dup_shown_case_T, c.dup_other_cases_T, c.no_drug_or_reaction_T,
  c.serious_no_drug_or_reaction_T,
  coalesce(o.outcomes_T, []::VARCHAR[]) AS outcomes_T
FROM case_latest_T c JOIN {PART} k USING (era_T, primaryid, quarter_T)
LEFT JOIN o USING (era_T, primaryid, quarter_T)
ORDER BY k.case_id_T
"""


def parts(cases: int) -> list[tuple[int, int]]:
    """The (first, last) case numbers of each part of `cases` cases, in order; one part, empty
    or not, for a release with few."""
    size = int(rulebook.value("explorer-build-memory", "cases_per_part"))
    return [(first, first + size - 1) for first in range(1, max(cases, 1) + 1, size)]


def by_parts(
    con: duckdb.DuckDBPyConnection, table: str, select: str, ranges: list[tuple[int, int]]
) -> None:
    """Write `table` from `select` (over PART, the part's case keys) one part at a time."""
    for i, (first, last) in enumerate(ranges):
        con.execute(PART_KEYS, [first, last])
        con.execute((f"CREATE TABLE {table} AS " if i == 0 else f"INSERT INTO {table} ") + select)
    con.execute(f"DROP TABLE {PART}")


# A drug row's ingredients, from the release's drug-name step when it has one, and its record's
# time to onset.
_SUBSTANCE_JOIN = (
    f" LEFT JOIN {in_part(SUBSTANCES)} s ON s.era_T = d.era_T AND s.primaryid = d.primaryid"
    " AND s.quarter_T = d.quarter_T AND s.drug_seq = d.drug_seq"
)
_ONSET_JOIN = (
    f" LEFT JOIN {in_part(ONSET_TABLE)} o ON o.era_T = d.era_T AND o.primaryid = d.primaryid"
    " AND o.quarter_T = d.quarter_T AND o.drug_seq = d.drug_seq"
)
# The clean columns a child row carries beside FDA's.
_CLEAN = {
    "drug": ("o.time_to_onset_T", "o.time_to_onset_reason_T"),
    "ther": ("d.start_dt_T", "d.start_dt_prec_T", "d.end_dt_T", "d.end_dt_prec_T", "d.dur_days_T"),
}


def child_table(child: str, *, substances: bool = False) -> str:
    """The child table's rows of the part's cases (PART), in order; the drug table carries
    each row's ingredients (`substance_T`) and where they came from (`substance_source_T`),
    empty when the release has no drug-name step (`substances`), and the clean columns of
    _CLEAN."""
    extra, join = "", ""
    if child in spelling.COLUMNS:
        extra = f", d.{spelling.COLUMNS[child][1]}"
    if child == "drug":
        extra = (
            ", d.drugname_norm_T, d.prod_ai_norm_T, nullif(upper(trim(d.role_cod)), '') AS role_T, "
            + (
                "s.substance_T, s.substance_source_T"
                if substances
                else "NULL::VARCHAR AS substance_T, NULL::VARCHAR AS substance_source_T"
            )
        )
        join = (_SUBSTANCE_JOIN if substances else "") + _ONSET_JOIN
    fda = [c for c in RAW_COLUMNS[child] if c not in _KEYS]
    return (
        "SELECT k.case_id_T, "
        + ", ".join(f"d.{c}" for c in fda)
        + extra
        + "".join(f", {c}" for c in _CLEAN.get(child, ()))
        + f" FROM {child}_latest_T d JOIN {PART} k USING (era_T, primaryid, quarter_T)"
        + join
        + f" ORDER BY k.case_id_T, {CHILD_ORDER[child]}"
    )


DRUG_TERMS = """
CREATE TABLE explorer_drug_term_T AS
SELECT DISTINCT term_T, role_T, case_id_T FROM (
  SELECT drugname_norm_T AS term_T, role_T, case_id_T FROM explorer_drug_T
  UNION ALL
  SELECT prod_ai_norm_T AS term_T, role_T, case_id_T FROM explorer_drug_T)
WHERE term_T IS NOT NULL
ORDER BY term_T, case_id_T
"""

INGREDIENT_TERMS = f"""
CREATE TABLE explorer_ingredient_T AS
SELECT DISTINCT unnest(string_split(substance_T, '{SEPARATOR}')) AS ingredient_T, substance_T,
  drugname_norm_T AS spelling_T, role_T, case_id_T
FROM explorer_drug_T WHERE substance_T IS NOT NULL
ORDER BY ingredient_T, case_id_T
"""

NO_INGREDIENT_TERMS = """
CREATE TABLE explorer_no_ingredient_T AS
SELECT DISTINCT drugname_norm_T AS spelling_T, role_T, case_id_T FROM explorer_drug_T
WHERE substance_T IS NULL AND drugname_norm_T IS NOT NULL
ORDER BY spelling_T, case_id_T
"""

DRUG_NAMES = """
CREATE TABLE explorer_drug_name_T AS
SELECT name_T, field_T, substance_T, count(*) AS rows_T FROM (
  SELECT drugname_norm_T AS name_T, 'drugname' AS field_T, substance_T FROM explorer_drug_T
  UNION ALL
  SELECT prod_ai_norm_T AS name_T, 'prod_ai' AS field_T, substance_T FROM explorer_drug_T)
WHERE name_T IS NOT NULL
GROUP BY ALL
ORDER BY name_T, field_T, substance_T
"""

# A sender as typed finds its company: every spelling FDA sent the company's cases under, and the
# company's own name. A sender that reads Not given names no company.
SENDERS = """
CREATE TABLE explorer_sender_T AS
SELECT DISTINCT unnest([upper(trim(mfr_sndr)), upper(company_T)]) AS spelling_T, company_T
FROM explorer_case_T WHERE company_T IS NOT NULL
ORDER BY spelling_T, company_T
"""

REAC_TERMS = f"""
CREATE TABLE explorer_reac_term_T AS
SELECT DISTINCT {reaction_key("pt")} AS term_T, case_id_T FROM explorer_reac_T
WHERE {reaction_key("pt")} IS NOT NULL
ORDER BY term_T, case_id_T
"""

# The release's statistics, where it has them, sorted by ingredient so a product's page reads
# only its own row groups: each explorer table, the release table it copies and its order. The
# class statistics (rule statistics-classes) are sorted by level and class, and come with the
# classes layer.
STATISTICS = "explorer_statistics_T"
STATISTICS_STRATA = "explorer_statistics_strata_T"
# the release's own, and the two counted by FDA's text in a release that holds MedDRA
STATISTICS_TABLES = {
    f"explorer_{name}": (name, "ingredient_T, reaction_T")
    for name in (
        "statistics_T",
        "statistics_strata_T",
        "statistics_as_published_T",
        "statistics_strata_as_published_T",
    )
}
CLASS_STATISTICS = "explorer_atc_statistics_T"
CLASS_INGREDIENTS = "explorer_atc_statistics_ingredients_T"
CLASS_STATISTICS_TABLES = {
    CLASS_STATISTICS: ("atc_statistics_T", "level_T, class_T, reaction_T"),
    CLASS_INGREDIENTS: ("atc_statistics_ingredients_T", "ingredient_T, level_T, class_T"),
}


def explorer_statistics(table: str) -> str:
    """The explorer database's copy of the release's statistics table `table`."""
    return f"explorer_{table}"


def statistics_table(name: str, copies: dict[str, tuple[str, str]]) -> str:
    """The statement that copies the release's table into explorer table `name` of `copies`."""
    source, order = copies[name]
    return f"CREATE TABLE {name} AS SELECT * FROM {source} ORDER BY {order}"


def _statistics(
    con: duckdb.DuckDBPyConnection, tables: dict, copies: dict[str, tuple[str, str]]
) -> tuple[str, ...]:
    """The explorer's copies of those of `copies` the release holds, by name."""
    made = tuple(name for name, (source, _) in copies.items() if source in tables)
    for name in made:
        con.execute(statistics_table(name, copies))
    return made


# WHO's drug classes, from the release's classes layer (src/open_altio/faers/README.md). A drug
# record written on several rows keeps every role it has.
CLASS_LAYER = classes_layer.TABLES
CLASS_TABLES = (
    "explorer_atc_class_T",
    "explorer_atc_drug_T",
    "explorer_atc_term_T",
    "explorer_atc_could_T",
)
CLASS_CODES = (
    """CREATE TABLE explorer_atc_class_T AS
       SELECT atc_code_T, atc_level_T, atc_name_T FROM atc_index_T ORDER BY atc_code_T""",
    # every possible code of every record, by case: the codes table joined to the cases once,
    # keys and codes only, stored by quarter so each quarter's part reads only its own rows
    """CREATE TEMP TABLE record_codes AS
       SELECT k.quarter_T, k.case_id_T, p.drug_seq, p.atc_code_T
       FROM atc_drug_codes_T p JOIN case_keys k USING (era_T, primaryid, quarter_T)
       ORDER BY k.quarter_T""",
    "CREATE TEMP TABLE record_lists (case_id_T BIGINT, drug_seq VARCHAR, codes_T VARCHAR[])",
)
# A record's possible codes as one list, one quarter's cases at a time: DuckDB cannot spill a list
# aggregate's state, and over every record at once it outgrows the build's memory.
CLASS_LISTS = """INSERT INTO record_lists
   SELECT case_id_T, drug_seq, list_sort(list_distinct(list(atc_code_T)))
   FROM record_codes WHERE quarter_T = ?
   GROUP BY ALL HAVING count(DISTINCT atc_code_T) > 1"""
CLASS_FROM_LISTS = (
    """CREATE TABLE explorer_atc_drug_T AS
       SELECT k.case_id_T, a.drug_seq, a.atc_code_T, a.atc_level_T, a.atc_chosen_by_T,
              a.atc_possible_codes_T, s.codes_T AS atc_codes_T
       FROM atc_drug_T a JOIN case_keys k USING (era_T, primaryid, quarter_T)
       LEFT JOIN record_lists s ON s.case_id_T = k.case_id_T AND s.drug_seq = a.drug_seq
       ORDER BY k.case_id_T, a.drug_seq""",
    "DROP TABLE record_lists",
    """CREATE TEMP TABLE record_roles AS
       SELECT DISTINCT case_id_T, drug_seq, role_T FROM explorer_drug_T WHERE role_T IS NOT NULL""",
    """CREATE TABLE explorer_atc_term_T AS
       SELECT DISTINCT a.atc_code_T, r.role_T, a.case_id_T
       FROM explorer_atc_drug_T a JOIN record_roles r USING (case_id_T, drug_seq)
       WHERE a.atc_code_T IS NOT NULL
       ORDER BY a.atc_code_T, a.case_id_T""",
    """CREATE TABLE explorer_atc_could_T AS
       SELECT DISTINCT p.atc_code_T, a.atc_code_T AS atc_class_T, r.role_T, a.case_id_T
       FROM record_codes p
       JOIN explorer_atc_drug_T a ON a.case_id_T = p.case_id_T AND a.drug_seq = p.drug_seq
       JOIN record_roles r ON r.case_id_T = p.case_id_T AND r.drug_seq = p.drug_seq
       WHERE a.atc_code_T IS NULL OR a.atc_level_T < 5
       ORDER BY p.atc_code_T, a.case_id_T""",
    "DROP TABLE record_codes",
    "DROP TABLE record_roles",
)


def _class_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Write CLASS_TABLES from the release's classes layer, on the build's connection after the
    case keys and explorer_drug_T."""
    for statement in CLASS_CODES:
        con.execute(statement)
    quarters = con.execute("SELECT DISTINCT quarter_T FROM record_codes ORDER BY ALL").fetchall()
    for (quarter,) in quarters:
        con.execute(CLASS_LISTS, [quarter])
    for statement in CLASS_FROM_LISTS:
        con.execute(statement)


EXPLORER_TABLES = (
    "explorer_release_T",
    "explorer_case_T",
    "explorer_drug_T",
    "explorer_reac_T",
    "explorer_outc_T",
    "explorer_ther_T",
    "explorer_indi_T",
    "explorer_sender_T",
    "explorer_drug_term_T",
    "explorer_reac_term_T",
    "explorer_ingredient_T",
    "explorer_no_ingredient_T",
    "explorer_drug_name_T",
)

_SPACE = re.compile(r"[\t\n\f\r ]+")
_TRAILING_DOTS = re.compile(r"\.+$")


def drug_term(text: str) -> str | None:
    """What someone typed as a drug, normalised as `drugname_norm_T` and
    `prod_ai_norm_T` are (src/open_altio/faers/derive.py `_norm`): upper case, whitespace
    collapsed and trimmed, trailing periods removed."""
    out = _TRAILING_DOTS.sub("", _SPACE.sub(" ", text.upper()).strip()).strip()
    return out or None


def reaction_term(text: str) -> str | None:
    """What someone typed as a reaction, as `explorer_reac_term_T.term_T` holds it."""
    out = _SPACE.sub(" ", text.lower()).strip()
    return out or None


def sender_key(text: str) -> str | None:
    """What someone typed as a sender, as `explorer_sender_T.spelling_T` holds it."""
    out = text.strip().upper()
    return out or None


class ExplorerBuildError(Exception):
    """An explorer database this build will not write, said by name."""


def build_connection(path: str | Path, *, spill: str | Path) -> duckdb.DuckDBPyConnection:
    """The build's DuckDB connection, held to the memory and threads in
    rules/explorer-build-memory.md so the build fits on the service's box.
    Past the limit DuckDB spills its sorts, joins and DISTINCTs to `spill`, which holds at
    most the rule's `spill_limit_gb`."""
    con = duckdb.connect(
        str(path),
        config={
            "memory_limit": f"{rulebook.value('explorer-build-memory', 'memory_limit_gb')}GB",
            "threads": int(rulebook.value("explorer-build-memory", "threads")),
            "temp_directory": str(spill),
            "max_temp_directory_size": (
                f"{rulebook.value('explorer-build-memory', 'spill_limit_gb')}GB"
            ),
        },
    )
    con.execute("SET enable_progress_bar = false")
    return con


def build_explorer_db(
    release_dir: str | Path,
    *,
    tables: dict | None = None,
    release: str | None = None,
) -> dict:
    """Write `explorer.duckdb` into the release folder from its Parquet, and
    return its manifest entry ({file, bytes, tables: {name: {rows}}}).

    The release build passes the `tables` and `release` it is about to write
    into manifest.json. Called on a finished release (no `tables`), it reads
    them from manifest.json and records the new entry there."""
    release_dir = Path(release_dir)
    finished = tables is None
    if tables is None:
        manifest = read_manifest(release_dir)
        tables, release = manifest["tables"], manifest["release"]
    target = release_dir / EXPLORER_FILE
    work = release_dir / ".explorer.building"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    staged = work / EXPLORER_FILE
    con = build_connection(staged, spill=work / "spill")
    try:
        register_release(con, release_dir, tables=tables, temporary=True, with_views=False)
        con.execute(
            "CREATE TABLE explorer_release_T AS SELECT ?::VARCHAR AS release_T, "
            "current_timestamp AS built_at_T",
            [release],
        )
        con.execute(KEYS_TABLE)
        ranges = parts(con.execute("SELECT count(*) FROM case_keys").fetchall()[0][0])
        by_parts(con, "explorer_case_T", CASE_TABLE, ranges)
        for child in CHILD_ORDER:
            by_parts(
                con,
                f"explorer_{child}_T",
                child_table(child, substances=SUBSTANCES in tables),
                ranges,
            )
        for statement in (
            SENDERS,
            DRUG_TERMS,
            REAC_TERMS,
            INGREDIENT_TERMS,
            NO_INGREDIENT_TERMS,
            DRUG_NAMES,
        ):
            con.execute(statement)
        built: tuple[str, ...] = EXPLORER_TABLES + _statistics(con, tables, STATISTICS_TABLES)
        if all(t in tables for t in CLASS_LAYER):
            _class_tables(con)
            built += CLASS_TABLES + _statistics(con, tables, CLASS_STATISTICS_TABLES)
        problems = misnamed(con, built)
        if problems:
            raise ExplorerBuildError("refused: " + "; ".join(problems))
        counts = {
            t: {"rows": con.execute(f"SELECT count(*) FROM {t}").fetchall()[0][0]} for t in built
        }
        con.execute("CHECKPOINT")
    finally:
        con.close()
    os.replace(staged, target)
    shutil.rmtree(work)
    entry = {"file": EXPLORER_FILE, "bytes": target.stat().st_size, "tables": counts}
    if finished:
        manifest = read_manifest(release_dir)
        manifest["explorer"] = entry
        (release_dir / MANIFEST_FILE).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    return entry


def replace_statistics(
    release_dir: str | Path, manifest: dict, copies: dict[str, tuple[str, str]]
) -> None:
    """Put the release's recounted statistics tables, those of `copies` (STATISTICS_TABLES or
    CLASS_STATISTICS_TABLES), into its explorer database, with `manifest` (the release's, with
    the new tables and entry) written beside it; a copy whose table the release no longer holds
    goes. The database is copied, changed and renamed over the old one, the manifest written
    first: an explorer that has the old database open goes on reading it, and the next one it
    opens reads both new."""
    release_dir = Path(release_dir)
    work = release_dir / ".explorer.statistics"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    staged = work / EXPLORER_FILE
    shutil.copyfile(release_dir / EXPLORER_FILE, staged)
    con = build_connection(staged, spill=work / "spill")
    try:
        held = [s for s, _ in copies.values() if s in manifest["tables"]]
        stats = {t: manifest["tables"][t] for t in held}
        register_release(con, release_dir, tables=stats, temporary=True, with_views=False)
        for name in copies:
            con.execute(f"DROP TABLE IF EXISTS {name}")
        con.execute("CHECKPOINT")  # so the new tables reuse the old ones' room in the file
        rows = {
            name: {"rows": con.execute(f"SELECT count(*) FROM {name}").fetchall()[0][0]}
            for name in _statistics(con, stats, copies)
        }
        con.execute("CHECKPOINT")
    finally:
        con.close()
    entry = dict(manifest["explorer"])
    entry["tables"] = {k: v for k, v in entry["tables"].items() if k not in copies} | rows
    entry["bytes"] = staged.stat().st_size
    manifest["explorer"] = entry
    write_manifest(release_dir, manifest)
    os.replace(staged, release_dir / EXPLORER_FILE)
    shutil.rmtree(work)


__all__ = [
    "CLASS_INGREDIENTS",
    "CLASS_LAYER",
    "CLASS_STATISTICS",
    "CLASS_STATISTICS_TABLES",
    "CLASS_TABLES",
    "EXPLORER_FILE",
    "EXPLORER_TABLES",
    "STATISTICS",
    "STATISTICS_STRATA",
    "STATISTICS_TABLES",
    "ExplorerBuildError",
    "build_connection",
    "build_explorer_db",
    "drug_term",
    "explorer_statistics",
    "reaction_term",
    "replace_statistics",
    "sender_key",
]
