"""The insight cards of notebook 02 (case versions, and the gaps between AERS and FAERS): the
findings behind the funnel steps its rules changed.

Each function is one card; its name is the card id. Only derived tables are read, so a card runs
on a release folder and on the release build's own connection alike.
"""

from __future__ import annotations

import duckdb

from open_altio import rulebook
from open_altio.faers.fda import FIRST_FAERS_QUARTER
from open_altio.faers.reader import quoted, sql_in

from . import common

NB02 = "notebooks/faers/02_case_versions.ipynb"


def carried_cases_counted_twice(con: duckdb.DuckDBPyConnection) -> dict:
    """AERS cases FDA carried into FAERS under the same case number had a
    latest version in each era. Changed our pipeline: one latest version per
    case across both eras (rules/latest-version.md)."""
    rows = common.query(
        con,
        """
        WITH carried AS (
          SELECT caseid, min(init_year_T) FILTER (WHERE era_T = 'legacy') AS year_T
          FROM demo_T WHERE caseid IS NOT NULL
          GROUP BY 1 HAVING count(DISTINCT era_T) = 2),
        latest AS (
          SELECT c.caseid, any_value(c.year_T) AS year_T, bool_and(l.era_T = 'faers') AS faers_T
          FROM carried c JOIN demo_latest_T l ON l.case_key_T = c.caseid GROUP BY 1)
        SELECT year_T, count(*), count(*) FILTER (WHERE faers_T)
        FROM latest GROUP BY 1 ORDER BY 1""",
    )
    xs = [y for y, _, _ in rows if y is not None]
    name = "Cases with versions in both AERS and FAERS"
    series = common.series([(y, name, n) for y, n, _ in rows], xs, [name])
    carried = sum(n for _, n, _ in rows)
    in_faers = sum(f for _, _, f in rows)
    peak = max(rows, key=lambda r: r[1], default=None)
    chart = common.chart(
        "stacked_bar",
        "Year FDA first received the case",
        "year",
        xs,
        "Cases with versions in both AERS and FAERS",
        "count",
        series,
        question="When did FDA first receive the cases it carried from AERS into FAERS?",
        note=(peak[0], f"{peak[1]:,} cases") if peak else None,
    )
    which = (
        "always the FAERS one" if in_faers == carried else f"the FAERS one for {in_faers:,} of them"
    )
    return common.card(
        "carried_cases_counted_twice",
        "Cases FDA carried from AERS into FAERS were counted twice",
        f"When FAERS began, FDA carried {common.plural(carried, 'AERS case')} into it under the "
        "same case number, so taking the latest version within each era counted every one of them "
        "twice. We now take one latest version per case across both eras, which for these cases is "
        f"{which}, so each counts once.",
        chart,
        common.changed("latest_versions", "latest-version"),
        NB02,
    )


def deleted_lists_name_aers_cases(con: duckdb.DuckDBPyConnection) -> dict:
    """FDA's deleted-case lists also name AERS cases, many of them direct
    reports sent electronically in 2011. Changed our pipeline: they leave the
    case set as listed FAERS cases do (rules/deleted-cases.md). Grain: cases
    whose latest version is in AERS (demo_latest_T)."""
    electronic, other = "Direct reports sent electronically", "Other reports"
    rows = common.query(
        con,
        f"""
        SELECT quarter_T,
               CASE WHEN rept_cod = 'DIR' AND e_sub = 'Y' THEN {quoted(electronic)}
                    ELSE {quoted(other)} END,
               count(*)
        FROM demo_latest_T
        WHERE era_T = 'legacy' AND caseid IN (SELECT caseid FROM deleted_cases_T)
        GROUP BY ALL""",
    )
    xs = [q for q in common.quarters(con) if q < FIRST_FAERS_QUARTER]
    series = common.series(rows, xs, [electronic, other])
    common.zeros(series)
    listed = sum(n for _, _, n in rows)
    sent = sum(n for _, kind, n in rows if kind == electronic)
    peak = max((r for r in rows if r[1] == electronic), key=lambda r: r[2], default=None)
    chart = common.chart(
        "stacked_bar",
        "Quarter the case's latest version was published",
        "quarter",
        xs,
        "AERS cases on a deleted-case list",
        "count",
        series,
        question="When were the AERS cases on FDA's deleted-case lists published?",
        note=(peak[0], f"{peak[2]:,} sent electronically") if peak else None,
    )
    when = f", {peak[2]:,} of those published in {common.quarter_label(peak[0])}" if peak else ""
    return common.card(
        "deleted_lists_name_aers_cases",
        "FDA's deleted-case lists also name AERS cases, many from one 2011 batch",
        f"FDA's deleted-case lists also name {common.plural(listed, 'AERS case')}, and {sent:,} of "
        f"them ({common.pct(sent, listed)}) are direct reports sent to FDA electronically{when}. "
        "We now take every listed AERS case out of the analysis set, as we already did for listed "
        "FAERS cases, and follow FDA's lists as they are.",
        chart,
        common.changed("after_deleted_lists", "deleted-cases"),
        NB02,
    )


def eras_write_countries_and_terms_differently(con: duckdb.DuckDBPyConnection) -> dict:
    """AERS wrote countries as names and reaction terms in capitals; FAERS
    writes ISO codes and MedDRA's mixed case. Changed our pipeline: duplicates
    are matched on the country code and the terms in capitals
    (rules/legacy-country.md, rules/reaction-term-case.md)."""
    code, caps = "Countries written as a two-letter code", "Reaction terms written in capitals"
    # of the countries given: FDA's words for no country are none (rules/country-not-given.md)
    country = "coalesce(occr_country, reporter_country)"
    none = sql_in(country, rulebook.value("country-not-given", "not_countries"))
    given = f"NOT coalesce({none}, true)"
    rows = common.query(
        con,
        f"""
        SELECT quarter_T, {quoted(code)},
               100.0
               * count(*) FILTER (WHERE {given} AND regexp_full_match({country}, '[A-Z]{{2}}'))
               / nullif(count(*) FILTER (WHERE {given}), 0)
        FROM case_latest_T GROUP BY ALL""",
    )
    rows += common.query(
        con,
        f"""
        SELECT quarter_T, {quoted(caps)}, 100.0 * count(*) FILTER (WHERE pt = upper(pt)) / count(*)
        FROM reac_latest_T WHERE pt IS NOT NULL GROUP BY ALL""",
    )
    groups = common.query(
        con,
        """
        WITH g AS (SELECT dup_group_T FROM case_dup_T WHERE dup_group_T IS NOT NULL
                   GROUP BY 1 HAVING count(DISTINCT era_T) = 2)
        SELECT count(*) FILTER (WHERE dup_kept_T),
               count(*) FILTER (WHERE dup_kept_T AND era_T = 'faers')
        FROM case_dup_T WHERE dup_group_T IN (SELECT dup_group_T FROM g)""",
    )
    across, faers_shown = groups[0] if groups else (0, 0)
    xs = common.quarters(con)
    first_faers = next((q for q in xs if q >= FIRST_FAERS_QUARTER), None)
    chart = common.chart(
        "line",
        "Quarter published",
        "quarter",
        xs,
        "Share written this way",
        "percent",
        common.series(rows, xs, [code, caps]),
        question="How do AERS and FAERS write countries and reaction terms?",
        note=(first_faers, "FAERS begins") if first_faers else None,
    )
    return common.card(
        "eras_write_countries_and_terms_differently",
        "AERS and FAERS write countries and reaction terms differently",
        "AERS wrote the country as a name (UNITED STATES) and every reaction term in capitals, "
        "while FAERS writes a two-letter code (US) and MedDRA's mixed case, so the same event "
        "reported in both could never be matched as a duplicate. Comparing countries as codes and "
        f"terms in capitals, we now find {across:,} duplicate groups that span both eras; each "
        f"shows its latest copy, the FAERS one in {faers_shown:,} of them, dated when FDA first "
        "received the earlier AERS report.",
        chart,
        common.changed("kept_after_duplicates", "legacy-country", "reaction-term-case"),
        NB02,
    )
