"""The `_T` objects: typed demographics, the latest version of each case, FDA's deleted cases,
the analysis grain and its child rows, the duplicate flags (src/open_altio/faers/duplicates.py)
and the deduplicated views.

Nothing is deleted: every object is a new table built from the raw ones. Each data rule is read
through the rulebook, so a build under a person's own rules (rulebook.use_user_rules) takes their
values and leaves out the rules they switched off.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

import duckdb

from open_altio import rulebook

from . import dates, duplicates, not_given, route, spelling
from .dates import full_date, number, precision
from .duplicates import Statement
from .reader import quoted, sql_in
from .schema import AS_PUBLISHED, CHILD_TABLES, EARLIER_VERSION, ERAS


# A number in its unit, converted: times the unit's first number, divided by its second
# (rules/age-in-years.md, rules/weight-in-kg.md). A unit `units` does not hold gives nothing.
def _converted(number: str, unit: str, units: dict[str, list[float]]) -> str:
    whens = " ".join(
        f"WHEN {quoted(u)} THEN {number} * {float(times)!r}::DOUBLE / {float(over)!r}::DOUBLE"
        for u, (times, over) in units.items()
    )
    return f"CASE {unit} {whens} END"


# The normalised drug name: upper case, whitespace collapsed to one space and
# trimmed, trailing periods removed, an empty result read as nothing.
def _norm(col: str) -> str:
    return (
        f"nullif(trim(regexp_replace(trim(regexp_replace(upper({col}), '\\s+', ' ', 'g')), "
        f"'\\.+$', '')), '')"
    )


DATE_COLUMNS = ("fda_dt", "init_fda_dt", "rept_dt", "mfr_dt", "event_dt", "death_dt")

# Legacy AERS names the reporter's country (UNITED STATES); FAERS gives the
# ISO 3166-1 code (US). The reviewed mapping (rules/legacy-country.md) is read
# into a scratch table for the build; it is not part of the release.
LEGACY_COUNTRY_TABLE = "legacy_country_T"


def legacy_country_table() -> str:
    """The mapping as a scratch table. With the rule off, every legacy name maps to itself, so
    country_T keeps it as FDA wrote it and no name is refused."""
    mapping = rulebook.data_root() / rulebook.value("legacy-country", "mapping")
    if not rulebook.is_on("legacy-country"):
        return (
            f"CREATE TEMP TABLE {LEGACY_COUNTRY_TABLE} AS SELECT DISTINCT "
            "reporter_country AS fda_value, reporter_country AS iso2 "
            "FROM demo WHERE era_T = 'legacy' AND reporter_country IS NOT NULL"
        )
    return (
        f"CREATE TEMP TABLE {LEGACY_COUNTRY_TABLE} AS SELECT fda_value, iso2 FROM "
        f"read_csv({quoted(mapping.as_posix())}, header=true, all_varchar=true)"
    )


# FDA's reporter codes (occp_cod) read as the ICH E2B(R3) reporter qualification
# (rules/reporter-type.md), through the reviewed mapping, into a scratch table for the build.
REPORTER_TYPE_TABLE = "reporter_type_map_T"


def reporter_type_table() -> str:
    """The mapping as a scratch table. With the rule off, every code maps to itself, so
    reporter_type_T keeps occp_cod as FDA wrote it."""
    if not rulebook.is_on("reporter-type"):
        return (
            f"CREATE TEMP TABLE {REPORTER_TYPE_TABLE} AS SELECT DISTINCT "
            "occp_cod AS fda_value, occp_cod AS e2b_code FROM demo WHERE occp_cod IS NOT NULL"
        )
    mapping = rulebook.data_root() / rulebook.value("reporter-type", "mapping")
    return (
        f"CREATE TEMP TABLE {REPORTER_TYPE_TABLE} AS SELECT fda_value, e2b_code FROM "
        f"read_csv({quoted(mapping.as_posix())}, header=true, all_varchar=true)"
    )


# Legacy country names the mapping does not hold: the build refuses them.
UNMAPPED_LEGACY_COUNTRIES = f"""
SELECT DISTINCT reporter_country FROM demo
WHERE era_T = 'legacy' AND reporter_country IS NOT NULL
  AND reporter_country NOT IN (SELECT fda_value FROM {LEGACY_COUNTRY_TABLE})
ORDER BY 1
"""

# Sender spellings as company names (rules/company-names.md), in either era: the reviewed
# mapping, read into a scratch table for the build. With the rule off it is empty, so every
# sender stays as FDA wrote it.
COMPANY_TABLE = "sender_company_T"


def company_table() -> str:
    """The mapping as a scratch table; empty with the rule off."""
    mapping = rulebook.data_root() / rulebook.value("company-names", "mapping")
    on = "" if rulebook.is_on("company-names") else " WHERE false"
    return (
        f"CREATE TEMP TABLE {COMPANY_TABLE} AS SELECT fda_value, company FROM "
        f"read_csv({quoted(mapping.as_posix())}, header=true, all_varchar=true){on}"
    )


_QNUM = "CAST(substr(quarter_T, 1, 4) AS INTEGER) * 10 + CAST(substr(quarter_T, 6, 1) AS INTEGER)"


def direct_report(rept_cod: str) -> str:
    """SQL: true when the report type in `rept_cod` is one sent straight to FDA, by no company
    (rule company-names)."""
    return sql_in(f"upper(trim({rept_cod}))", rulebook.value("company-names", "direct_reports"))


def no_company(mfr_sndr: str, rept_cod: str) -> str:
    """SQL: true when a report names no company (rule company-names): its sender reads Not given
    (rule not-given) or, with the rule on, is FDA's own intake, or it was sent straight to FDA."""
    out = not_given.check("mfr_sndr", mfr_sndr)
    if rulebook.is_on("company-names"):
        fda = quoted(rulebook.value("company-names", "fda_sender"))
        out += f" OR upper(trim({mfr_sndr})) = {fda} OR {direct_report(rept_cod)}"
    return out


def company(mfr_sndr: str, rept_cod: str, mapped: str) -> str:
    """SQL: a report's company_T (rule company-names), `mapped` being the company COMPANY_TABLE
    gives its sender's exact spelling: none where the report names no company, else that company,
    else the sender as written."""
    none = no_company(mfr_sndr, rept_cod)
    return f"CASE WHEN {none} THEN NULL ELSE coalesce({mapped}, trim({mfr_sndr})) END"


def _sex() -> str:
    """sex_T (rules/sex-codes.md): FDA's code trimmed and in capitals when it is a known one."""
    known = sql_in("upper(trim(sex))", rulebook.value("sex-codes", "known"))
    return f"CASE WHEN {known} THEN upper(trim(sex)) END"


def _age_unit() -> str:
    """The unit an age is read in: FDA's, else the rule's unit for an age with none."""
    return f"coalesce(age_cod, {quoted(rulebook.value('age-in-years', 'no_unit'))})"


def _age_years() -> str:
    """age_years_T (rules/age-in-years.md): exact years, none over the rule's maximum, none where
    the age reads Not given (rules/not-given.md: a filler such as 999)."""
    years = _converted(number("age"), _age_unit(), rulebook.value("age-in-years", "units"))
    top = float(rulebook.value("age-in-years", "max_years"))
    return not_given.given("age", value=f"CASE WHEN {years} <= {top!r}::DOUBLE THEN {years} END")


def _wt_kg() -> str:
    """wt_kg_T (rules/weight-in-kg.md): kilograms above zero, none over the rule's maximum."""
    kg = _converted(number("wt"), "wt_cod", rulebook.value("weight-in-kg", "units"))
    top = float(rulebook.value("weight-in-kg", "max_kg"))
    return not_given.given(
        "wt", value=f"CASE WHEN {kg} > 0 AND {kg} <= {top!r}::DOUBLE THEN {kg} END"
    )


def _age_band() -> str:
    """age_band_T (rules/age-bands.md), over a row that has age_years_T. A bound is an age in one
    of FDA's units, read in years as an age is, so an age on a band's edge lands as it should."""
    units = rulebook.value("age-in-years", "units")

    def years(bound: list) -> str:
        number, unit = bound
        times, over = units[unit]
        return f"{number * times / over!r}::DOUBLE"

    zero_in = sql_in(_age_unit(), rulebook.value("age-bands", "zero_age_units"))
    groups = " ".join(
        f"WHEN {quoted(g)} THEN {quoted(band)}"
        for g, band in rulebook.value("age-bands", "zero_age_groups").items()
    )
    other = quoted(rulebook.value("age-bands", "zero_age_band"))
    zero = f"CASE upper(trim(age_grp)) {groups} ELSE {other} END"
    whens = [f"WHEN age_years_T = 0 AND {zero_in} THEN {zero}"]
    for band in rulebook.value("age-bands", "bands"):
        if band["from"] is None:
            continue
        upper = "" if band["to"] is None else f" AND age_years_T < {years(band['to'])}"
        whens.append(f"WHEN age_years_T >= {years(band['from'])}{upper} THEN {quoted(band['id'])}")
    return f"CASE {' '.join(whens)} END"


def _country() -> str:
    """country_T before an EU case takes its member state: the occurrence country, else the
    reporter's, a legacy name read as its ISO code (rules/legacy-country.md); a value that is no
    country counts as empty (rules/country-not-given.md)."""
    columns = [
        "d.occr_country",
        "CASE WHEN d.era_T = 'legacy' THEN m.iso2 ELSE d.reporter_country END",
    ]
    if rulebook.is_on("country-not-given"):
        nots = rulebook.value("country-not-given", "not_countries")
        columns = [f"CASE WHEN {sql_in(c, nots)} THEN NULL ELSE {c} END" for c in columns]
    return f"coalesce({', '.join(columns)})"


def demo() -> str:
    """demo_T: every report version with its typed and derived columns. Dates are read as far as
    they are known and can be true (src/open_altio/faers/dates.py); sex, age, weight, age band,
    country and reporter type are read by their rules; FDA's columns stay as they are.
    age_band_T and country_source_T read the age and country worked out before them. company_T
    is the company a sender's exact spelling names, in either era, else the sender as written;
    none where the report names no company (no_company). With rule company-names off, every
    sender as written."""
    event = dict(zip(("event_dt_T", "event_dt_prec_T"), dates.event_date(), strict=True))
    typed = ", ".join(f"{event.get(f'{c}_T', full_date(c))} AS {c}_T" for c in DATE_COLUMNS)
    known = ", ".join(
        f"{event.get(f'{c}_prec_T', precision(c))} AS {c}_prec_T" for c in DATE_COLUMNS
    )
    return f"""
CREATE TABLE demo_T AS
SELECT d.*,
  {_QNUM} AS qnum_T,
  CASE WHEN regexp_full_match(caseversion, '[0-9]+') THEN CAST(caseversion AS INTEGER) END
    AS caseversion_T,
  {typed},
  {known},
  coalesce({full_date("init_fda_dt")}, {full_date("fda_dt")}) AS first_fda_dt_T,
  CASE WHEN regexp_full_match(substr(coalesce(init_fda_dt, fda_dt), 1, 4), '[0-9]{{4}}')
       THEN CAST(substr(coalesce(init_fda_dt, fda_dt), 1, 4) AS INTEGER) END AS init_year_T,
  CASE WHEN regexp_full_match(substr(fda_dt, 1, 4), '[0-9]{{4}}')
       THEN CAST(substr(fda_dt, 1, 4) AS INTEGER) END AS fda_year_T,
  {_sex()} AS sex_T,
  {_age_years()} AS age_years_T,
  {_wt_kg()} AS wt_kg_T,
  {_age_band()} AS age_band_T,
  coalesce(caseid, 'ISR:' || primaryid) AS case_key_T,
  {_country()} AS country_T,
  CASE WHEN country_T IS NOT NULL THEN {quoted(AS_PUBLISHED)} END AS country_source_T,
  r.e2b_code AS reporter_type_T,
  {company("d.mfr_sndr", "d.rept_cod", "s.company")} AS company_T
FROM demo d LEFT JOIN {LEGACY_COUNTRY_TABLE} m
  ON d.era_T = 'legacy' AND m.fda_value = d.reporter_country
LEFT JOIN {REPORTER_TYPE_TABLE} r ON r.fda_value = d.occp_cod
LEFT JOIN {COMPANY_TABLE} s ON s.fda_value = d.mfr_sndr
"""


# An EU case's member state (rules/eu-member-state.md): the occurrence country of the latest
# earlier FAERS version of the same caseid that gives an ISO code, versions ordered as
# demo_latest_T orders them. Only the versions of cases with an EU version are sorted.
MEMBER_STATE = """
UPDATE demo_T SET country_T = m.member_T, country_source_T = {earlier}
FROM (
  SELECT era_T, primaryid, quarter_T, max(member_T) AS member_T FROM (
    SELECT era_T, primaryid, quarter_T, country_T,
           last_value(CASE WHEN occr_country <> {code} AND occr_country IN (
                             SELECT iso2 FROM read_csv({iso}, header=true, all_varchar=true))
                           THEN occr_country END IGNORE NULLS) OVER (
             PARTITION BY caseid
             ORDER BY caseversion_T NULLS FIRST, fda_dt NULLS FIRST, qnum_T, primaryid
             ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS member_T
    FROM demo_T
    WHERE era_T = 'faers'
      AND caseid IN (SELECT caseid FROM demo_T WHERE era_T = 'faers' AND country_T = {code}))
  WHERE country_T = {code} AND member_T IS NOT NULL
  GROUP BY ALL) m
WHERE demo_T.era_T = m.era_T AND demo_T.primaryid = m.primaryid
  AND demo_T.quarter_T = m.quarter_T
"""


def member_state() -> str:
    iso = rulebook.data_root() / rulebook.value("eu-member-state", "iso_codes")
    return MEMBER_STATE.format(
        earlier=quoted(EARLIER_VERSION),
        code=quoted(rulebook.value("eu-member-state", "code")),
        iso=quoted(iso.as_posix()),
    )


# The latest version of each case, across AERS and FAERS
# (rules/latest-version.md): FDA carried AERS cases into FAERS under the same
# case number, caseversion counting on from the AERS versions. The highest
# caseversion, then the latest fda_dt, then the latest quarter (a primaryid
# can be re-published), then the highest primaryid. Legacy: one ISR per
# report version and no caseversion, so a carried-over case keeps its FAERS
# version and an AERS-only case is ordered from fda_dt on. A legacy row with
# no CASE is its own case (case_key_T). fda_dt and primaryid are compared as
# FDA's text. With the rule's across_eras off, the partition is per era.
DEMO_LATEST_T = """
CREATE TABLE demo_latest_T AS
SELECT * EXCLUDE (rn_T) FROM (
  SELECT t.*, row_number() OVER (
    PARTITION BY {partition}
    ORDER BY caseversion_T DESC NULLS LAST, fda_dt DESC NULLS LAST,
             qnum_T DESC, primaryid DESC) AS rn_T
  FROM demo_T t) r
WHERE rn_T = 1
"""


def demo_latest() -> str:
    across = rulebook.value("latest-version", "across_eras")
    return DEMO_LATEST_T.format(partition="case_key_T" if across else "era_T, case_key_T")


# Every caseid on any of FDA's deleted-case lists, once, with the first
# quarter that listed it, how often it was listed, and whether the one-off
# whole-history list (quarter_T 'pre...') named it.
DELETED_CASES_T = """
CREATE TABLE deleted_cases_T AS
SELECT caseid,
       min(quarter_T) FILTER (WHERE quarter_T NOT LIKE 'pre%') AS first_listed_quarter_T,
       count(*) AS n_listings_T,
       bool_or(quarter_T LIKE 'pre%') AS in_all_history_list_T
FROM deleted GROUP BY caseid
"""

# The analysis grain: the latest version of every case, less the cases FDA
# deleted (rules/deleted-cases.md). A case whose number is on any list is left
# out when its latest version is in one of the rule's eras; with the rule's
# eras at faers alone, legacy AERS cases on a list stay, as before the rule.
# A legacy report with no CASE number is never matched to a list.
CASE_LATEST_T = """
CREATE TABLE case_latest_T AS
SELECT d.* FROM demo_latest_T d
WHERE NOT ({listed_era} AND coalesce(d.caseid IN (SELECT caseid FROM deleted_cases_T), false))
"""


def case_latest() -> str:
    """case_latest_T: with the rule switched off, no listed case is left out."""
    eras = rulebook.value("deleted-cases", "eras")
    unknown = sorted(set(eras) - set(ERAS))
    if not eras or unknown:
        raise ValueError(f"rules/deleted-cases.md: eras must be some of {list(ERAS)}, not {eras!r}")
    on = rulebook.is_on("deleted-cases")
    return CASE_LATEST_T.format(listed_era=sql_in("d.era_T", eras if on else []))


QUARTERS_T = f"""
CREATE TABLE quarters_T AS
SELECT DISTINCT quarter_T, era_T, {_QNUM} AS qnum_T FROM demo ORDER BY qnum_T
"""


# The reaction term as the duplicate key compares it (rules/reaction-term-case.md):
# legacy AERS writes terms in capitals, FAERS in MedDRA's mixed case, so
# pt_norm_T is pt in upper case; with the rule off, pt as written.
def _pt_norm() -> str:
    return "upper(a.pt)" if rulebook.is_on("reaction-term-case") else "a.pt"


def child_latest(table: str) -> str:
    """A child table's rows that belong to a case in the grain, joined on
    (era_T, primaryid, quarter_T): a re-published primaryid's rows from
    another quarter do not come along. A therapy row's dates are read against
    its case (src/open_altio/faers/dates.py). Reactions and indications also
    carry their term in MedDRA's spelling (open_altio.faers.spelling)."""
    norm = {
        "drug": (
            f", {_norm('a.drugname')} AS drugname_norm_T, {_norm('a.prod_ai')} AS prod_ai_norm_T"
        ),
        "reac": f", {_pt_norm()} AS pt_norm_T",
        "ther": f", {dates.therapy_columns()}",
    }.get(table, "")
    case = "".join(f", {c}" for c in dates.THERAPY_CASE_COLUMNS) if table == "ther" else ""
    spelled, spellings = spelling.column(table)
    return (
        f"CREATE TABLE {table}_latest_T AS SELECT a.*{norm}{spelled} FROM {table} a "
        f"JOIN (SELECT era_T, primaryid, quarter_T{case} FROM case_latest_T) c "
        f"USING (era_T, primaryid, quarter_T){spellings}"
    )


def statements(quarters: Sequence[str]) -> Iterator[Statement]:
    """Every derive step, in order, for a release of these quarters."""
    yield QUARTERS_T
    yield legacy_country_table()
    yield reporter_type_table()
    yield company_table()
    yield demo()
    if rulebook.is_on("eu-member-state"):
        yield member_state()
    yield demo_latest()
    yield DELETED_CASES_T
    yield case_latest()
    yield from spelling.spelling_tables()
    for t in CHILD_TABLES:
        yield child_latest(t)
    yield from spelling.drop_tables()
    yield from duplicates.statements(quarters)
    yield dates.onset()
    yield route.build  # rules/drug-route.md


def run(con: duckdb.DuckDBPyConnection, statement: Statement) -> None:
    """Run one derive step on `con`."""
    if callable(statement):
        statement(con)
    else:
        con.execute(statement)


DERIVED_TABLES = (
    ("quarters_T", "demo_T", "demo_latest_T", "deleted_cases_T", "case_latest_T")
    + tuple(f"{t}_latest_T" for t in CHILD_TABLES)
    + ("case_dup_T", dates.ONSET_TABLE, route.TABLE)
)


def view_statements() -> Iterator[str]:
    """The deduplicated views: the kept cases,
    then each child table cut to them. Written against table names only, so
    the same text runs in the build and over the release's Parquet once each
    table is registered under its name."""
    yield "CREATE VIEW case_dedup_T AS SELECT * FROM case_latest_T WHERE dup_kept_T"
    for t in CHILD_TABLES:
        yield (
            f"CREATE VIEW {t}_dedup_T AS SELECT a.* FROM {t}_latest_T a "
            "SEMI JOIN case_dedup_T c USING (era_T, primaryid, quarter_T)"
        )


DERIVED_VIEWS = ("case_dedup_T",) + tuple(f"{t}_dedup_T" for t in CHILD_TABLES)
