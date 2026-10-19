"""FDA's columns per table, the one place their names are unified across eras, and the check
that everything else is named as derived (rules/transformed-suffix-T.md).

A raw table in a release has exactly these columns, in this order, then its
provenance columns.
"""

from __future__ import annotations

from collections.abc import Iterable

import duckdb

from open_altio import rulebook

TABLES = ("demo", "drug", "reac", "outc", "rpsr", "ther", "indi")
CHILD_TABLES = TABLES[1:]

# FDA's own columns per file: the union of the legacy AERS and the FAERS
# layouts. A column one era does not publish is empty (NULL) in its rows.
RAW_COLUMNS: dict[str, tuple[str, ...]] = {
    "demo": (
        "primaryid",
        "caseid",
        "caseversion",
        "i_f_code",
        "event_dt",
        "mfr_dt",
        "init_fda_dt",
        "fda_dt",
        "rept_cod",
        "auth_num",
        "mfr_num",
        "mfr_sndr",
        "lit_ref",
        "age",
        "age_cod",
        "age_grp",
        "sex",
        "e_sub",
        "wt",
        "wt_cod",
        "rept_dt",
        "to_mfr",
        "occp_cod",
        "reporter_country",
        "occr_country",
        "foll_seq",
        "image",
        "death_dt",
        "confid",
    ),
    "drug": (
        "primaryid",
        "caseid",
        "drug_seq",
        "role_cod",
        "drugname",
        "prod_ai",
        "val_vbm",
        "route",
        "dose_vbm",
        "cum_dose_chr",
        "cum_dose_unit",
        "dechal",
        "rechal",
        "lot_num",
        "exp_dt",
        "nda_num",
        "dose_amt",
        "dose_unit",
        "dose_form",
        "dose_freq",
    ),
    "reac": ("primaryid", "caseid", "pt", "drug_rec_act"),
    "outc": ("primaryid", "caseid", "outc_cod"),
    "rpsr": ("primaryid", "caseid", "rpsr_cod"),
    "ther": ("primaryid", "caseid", "dsg_drug_seq", "start_dt", "end_dt", "dur", "dur_cod"),
    "indi": ("primaryid", "caseid", "indi_drug_seq", "indi_pt"),
    "deleted": ("caseid",),
}

# The provenance columns we add to every raw row: which quarter's file it
# came from and which era's layout it was published in. The deleted-case
# lists have no era: they are FDA's nullification lists, keyed by caseid.
PROVENANCE: dict[str, tuple[str, ...]] = {t: ("quarter_T", "era_T") for t in TABLES}
PROVENANCE["deleted"] = ("quarter_T",)

ERAS = ("legacy", "faers")  # era_T values: legacy = AERS 2004Q1 to 2012Q3
# country_source_T values: the case's own version gave country_T, or an earlier version of the
# case did (rules/eu-member-state.md)
AS_PUBLISHED, EARLIER_VERSION = "as published", "earlier version"

# The only renames we make. A header is first trimmed and lower-cased; then a
# name on the left becomes the name on the right. Legacy AERS keys reports
# by ISR and CASE; FAERS by primaryid and caseid. In legacy THER and INDI the
# drug sequence is DRUG_SEQ; FAERS calls it dsg_drug_seq and indi_drug_seq.
# 2012Q4 spelled lot_num and outc_cod as lot_nbr and outc_code.
COLUMN_UNIFICATION: dict[str, dict[str, str]] = {
    "*": {"isr": "primaryid", "case": "caseid"},
    "demo": {"i_f_cod": "i_f_code", "gndr_cod": "sex"},
    "drug": {"lot_nbr": "lot_num"},
    "outc": {"outc_code": "outc_cod"},
    "ther": {"drug_seq": "dsg_drug_seq"},
    "indi": {"drug_seq": "indi_drug_seq"},
}


def normal_header(header: str) -> str:
    """One header field of an FDA file, trimmed and lower-cased, a byte order mark dropped."""
    return header.replace("\ufeff", "").strip().lower()


def unified_name(table: str, header: str) -> str:
    """The release column name for one header field of an FDA file."""
    name = normal_header(header)
    return COLUMN_UNIFICATION.get(table, {}).get(name) or COLUMN_UNIFICATION["*"].get(name, name)


def columns(table: str) -> tuple[str, ...]:
    """Every column of a raw release table: FDA's, then the provenance."""
    return RAW_COLUMNS[table] + PROVENANCE[table]


def derived_suffix() -> str:
    return rulebook.value("transformed-suffix-T", "derived_suffix")


def table_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    """The columns of a table or view on `con`, in order."""
    return [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]


def misnamed(
    con: duckdb.DuckDBPyConnection, derived: Iterable[str], raw: Iterable[str] = ()
) -> list[str]:
    """Every name on `con` that breaks rules/transformed-suffix-T.md, one sentence each: a
    derived table or view, or a column of it that is not FDA's, without the derived suffix, and a
    column of a raw table that is neither FDA's nor suffixed."""
    suffix = derived_suffix()
    fda = {c for cols in RAW_COLUMNS.values() for c in cols}
    problems = [
        f"raw table {table}: column {c} is not FDA's and does not end in {suffix}"
        for table in raw
        for c in table_columns(con, table)
        if c not in RAW_COLUMNS[table] and not c.endswith(suffix)
    ]
    for table in derived:
        if not table.endswith(suffix):
            problems.append(f"derived table or view {table} does not end in {suffix}")
        problems += [
            f"{table}.{c} is derived and does not end in {suffix}"
            for c in table_columns(con, table)
            if c not in fda and not c.endswith(suffix)
        ]
    return problems
