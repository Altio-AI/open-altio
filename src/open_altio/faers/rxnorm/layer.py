"""`drug_rxnorm_T`, each drug record's RxNorm code, built with the release
(rule rxnorm-ingredients).

    from open_altio.faers.rxnorm import layer
    entry = layer.build(con, rxnorm_dir)   # on the build's connection, after the derive steps

One row per row of `drug_substance_T` (the drug names step: one per drug
record of `drug_latest_T`, keyed by `era_T`, `primaryid`, `quarter_T` and
`drug_seq`, with the record's ingredient `substance_T`), beside that
ingredient:

    rxcui_T            the record's RxNorm code, NULL where it has none
    rxnorm_name_T      RxNorm's name for the code, as RxNorm writes it
    tty_T              IN (one ingredient) or MIN (a set of ingredients)
    matched_by_T       drug_name: FDA's drug name is itself an RxNorm name;
                       prod_ai: FDA's active ingredient is; substance: found from
                       the record's ingredient; none
    no_code_reason_T   why it has no code, NULL where it has one

`ingredient_rxnorm_T` has one row per ingredient a record is counted under (`ingredient_T`:
`substance_T` split at ";", so a combination counts for each of its ingredients), with the
code the ingredient's own reading gives it (`Matcher.match`, as a record falls back to its
ingredient): `rxcui_T`, `rxnorm_name_T`, `tty_T` and `no_code_reason_T` as above. The label
flags read an ingredient's own label by it.

The drug name comes first, matched exactly (`Matcher.drug_name`), so a brand
gives its precise ingredient (Lantus: insulin glargine) while the record is
still counted under the dictionary's ingredient (insulin). FDA's active
ingredient comes second, matched the same way (`Matcher.prod_ai`), so KCL with
FDA's potassium chloride is coded potassium chloride, not the dictionary's
potassium. Only a record whose two FDA fields give no code falls back to the
ingredient (`Matcher.match`).

It returns the release's manifest entry: the RxNorm release read (NLM's file
date, which the rule pins), the source, each file's SHA-256 and the counts.
Switched off in a person's rules, without an RxNorm folder, or without
`drug_substance_T`, it writes nothing and says why; a folder holding another
release than the rule pins is refused.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb

from open_altio import rulebook

from .match import DIFFERENT_PARENT, NO_NAME, SEPARATOR, Match, Matcher
from .rrf import CONSO_FILE, REL_FILE, RULE, read_rxnorm

TABLE = "drug_rxnorm_T"
INGREDIENTS = "ingredient_rxnorm_T"  # each ingredient's own code, by the ingredient reading
TABLES = (TABLE, INGREDIENTS)
SUBSTANCES = "drug_substance_T"
RECORD = ("era_T", "primaryid", "quarter_T", "drug_seq")
COLUMNS = ("rxcui_T", "rxnorm_name_T", "tty_T", "matched_by_T", "no_code_reason_T")
DRUG_NAME, PROD_AI, SUBSTANCE, NONE = "drug_name", "prod_ai", "substance", "none"
# scratch tables: the codes of each distinct drug name, active ingredient and ingredient,
# dropped once joined
_NAMES, _PROD_AI, _INGREDIENTS = "rxnorm_names_T", "rxnorm_prod_ai_T", "rxnorm_ingredients_T"
_CODE = ("rxcui_T", "rxnorm_name_T", "tty_T", "reason_T")
# the record's sources in order (scratch table alias, matched_by_T); the first with a code wins
_SOURCES = (("n", DRUG_NAME), ("p", PROD_AI), ("i", SUBSTANCE))
# each ingredient a record is counted under: a combination counts for each of its ingredients
_COUNTED = f"""SELECT DISTINCT unnest(string_split(substance_T, '{SEPARATOR}')) AS ingredient_T
       FROM {SUBSTANCES} WHERE substance_T IS NOT NULL"""
# FDA's own words on each drug record, as the steps that code a drug match them whole: its drug
# name and active ingredient as derive normalised them, in lower case. FDA repeats a record's key
# on several rows, one per dose, always with one drug name and active ingredient; they are read
# once per key, so each row of the ingredients table stays one row
FDA_WORDS = f"""SELECT {", ".join(RECORD)}, min(lower(drugname_norm_T)) AS drug_name_T,
         min(lower(prod_ai_norm_T)) AS prod_ai_T
       FROM drug_latest_T GROUP BY {", ".join(RECORD)}"""


def _scratch(con: duckdb.DuckDBPyConnection, table: str, key: str, rows: list[tuple]) -> None:
    con.execute(f"CREATE TABLE {table} ({key} VARCHAR, {', '.join(f'{c} VARCHAR' for c in _CODE)})")
    if rows:  # DuckDB refuses an empty executemany
        con.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?)", rows)


def _code(m: Match) -> tuple[str | None, ...]:
    return (m.rxcui, m.rxnorm_name, m.tty, m.reason)


def _text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _first(column: str) -> str:
    whens = " ".join(f"WHEN {a}.rxcui_T IS NOT NULL THEN {a}.{column}" for a, _ in _SOURCES)
    return f"CASE {whens} END AS {column}"


def _records() -> str:
    keys = ", ".join(f"s.{c}" for c in RECORD)
    on = ", ".join(RECORD)
    by = " ".join(f"WHEN {a}.rxcui_T IS NOT NULL THEN '{how}'" for a, how in _SOURCES)
    coded = " OR ".join(f"{a}.rxcui_T IS NOT NULL" for a, _ in _SOURCES)
    other = _text(DIFFERENT_PARENT)
    return f"""CREATE TABLE {TABLE} AS
       WITH d AS ({FDA_WORDS})
       SELECT {keys}, {_first("rxcui_T")}, {_first("rxnorm_name_T")}, {_first("tty_T")},
              CASE {by} ELSE '{NONE}' END AS matched_by_T,
              CASE WHEN {coded} THEN NULL
                   WHEN {other} IN (n.reason_T, p.reason_T) THEN {other}
                   ELSE coalesce(i.reason_T, {_text(NO_NAME)}) END AS no_code_reason_T
       FROM {SUBSTANCES} s
       LEFT JOIN d USING ({on})
       LEFT JOIN {_NAMES} n ON n.drug_name_T = d.drug_name_T
       LEFT JOIN {_PROD_AI} p ON p.prod_ai_T = d.prod_ai_T
       LEFT JOIN {_INGREDIENTS} i ON i.substance_T = s.substance_T"""


def _ingredients() -> str:
    """Each ingredient a record is counted under, with the code its ingredient reading gives."""
    return f"""CREATE TABLE {INGREDIENTS} AS
       SELECT substance_T AS ingredient_T, rxcui_T, rxnorm_name_T, tty_T,
              reason_T AS no_code_reason_T
       FROM {_INGREDIENTS} WHERE substance_T IN (SELECT ingredient_T FROM ({_COUNTED}))
       ORDER BY ingredient_T"""


def _file(root: Path, name: str) -> dict:
    path = root / name
    return {
        "file": name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _suspect(con: duckdb.DuckDBPyConnection) -> dict:
    """The suspect drug records (rule label-flags' roles) and how many have a code, as
    distinct records, never rows: FDA repeats a record's key on a row per dose."""
    roles = list(rulebook.value("label-flags", "suspect_roles"))
    on = ", ".join(RECORD)
    keys = ", ".join(f"r.{c}" for c in RECORD)
    records, coded = con.execute(
        f"""SELECT count(DISTINCT ({keys})),
                   count(DISTINCT ({keys})) FILTER (WHERE r.rxcui_T IS NOT NULL) FROM {TABLE} r
            JOIN (SELECT {on} FROM drug_latest_T
                  WHERE upper(trim(role_cod)) IN (SELECT unnest(?::VARCHAR[])) GROUP BY ALL) d
            USING ({on})""",
        [roles],
    ).fetchone() or (0, 0)
    share = round(100.0 * coded / records, 2) if records else 0.0
    return {"roles": roles, "records": records, "coded": coded, "coded_share": share}


def build(con: duckdb.DuckDBPyConnection, rxnorm_dir: str | Path | None) -> dict:
    """Write `drug_rxnorm_T` on `con` and return its manifest entry."""
    release = str(rulebook.value(RULE, "release"))
    source = rulebook.value(RULE, "source")
    absent = {"present": False, "source": source, "release": release}
    if not rulebook.is_on(RULE):
        return {**absent, "reason": "switched off in your rules"}
    if rxnorm_dir is None:
        return {**absent, "reason": "no RxNorm folder given"}
    root = Path(rxnorm_dir).expanduser()
    matcher = Matcher(read_rxnorm(root))
    have = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    if SUBSTANCES not in have:
        return {**absent, "reason": f"no substance per drug record ({SUBSTANCES})"}
    names = con.execute(
        "SELECT DISTINCT lower(drugname_norm_T) FROM drug_latest_T "
        "WHERE drugname_norm_T IS NOT NULL"
    ).fetchall()
    # only a drug name RxNorm holds can give a code or a refusal, so only those are kept
    coded = [(n, matcher.drug_name(n)) for (n,) in names if n in matcher.rx.by_name]
    _scratch(con, _NAMES, "drug_name_T", [(n, *_code(m)) for n, m in coded])
    held = con.execute(
        "SELECT DISTINCT lower(prod_ai_norm_T) FROM drug_latest_T WHERE prod_ai_norm_T IS NOT NULL"
    ).fetchall()
    # likewise only an active ingredient that gives a code or a refusal of its own is kept
    given = [(a, matcher.prod_ai(a)) for (a,) in held]
    kept = [(a, *_code(m)) for a, m in given if m.rxcui or m.reason == DIFFERENT_PARENT]
    _scratch(con, _PROD_AI, "prod_ai_T", kept)
    found = con.execute(
        f"SELECT DISTINCT substance_T FROM {SUBSTANCES} WHERE substance_T IS NOT NULL "
        f"UNION SELECT ingredient_T FROM ({_COUNTED})"
    )
    _scratch(
        con,
        _INGREDIENTS,
        "substance_T",
        [(s, *_code(matcher.match(s))) for (s,) in found.fetchall()],
    )
    con.execute(_records())
    con.execute(_ingredients())
    for scratch in (_NAMES, _PROD_AI, _INGREDIENTS):
        con.execute(f"DROP TABLE {scratch}")
    by = con.execute(
        f"SELECT matched_by_T, count(*) FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    why = con.execute(
        f"SELECT no_code_reason_T, count(*) FROM {TABLE} WHERE no_code_reason_T IS NOT NULL "
        "GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    ingredients, coded = con.execute(
        f"SELECT count(*), count(rxcui_T) FROM {INGREDIENTS}"
    ).fetchone() or (0, 0)
    return {
        "present": True,
        "source": source,
        "release": release,
        "download": rulebook.value(RULE, "download").format(release=release),
        "files": [_file(root, name) for name in (CONSO_FILE, REL_FILE)],
        "table": TABLE,
        "ingredients": {"table": INGREDIENTS, "ingredients": ingredients, "coded": coded},
        "records_by_how": dict(by),
        "records_without_code": dict(why),
        "suspect_records": _suspect(con),
        "unused_name_pairs": matcher.unused_pairs,
    }


__all__ = [
    "COLUMNS",
    "DRUG_NAME",
    "FDA_WORDS",
    "INGREDIENTS",
    "NONE",
    "PROD_AI",
    "RECORD",
    "SUBSTANCE",
    "SUBSTANCES",
    "TABLE",
    "TABLES",
    "build",
]
