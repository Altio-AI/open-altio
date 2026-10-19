"""The insight cards of notebook 07 (demographics and units): how FDA writes a patient's sex, age
and country, where the way it is written would change a count.

Each function is one card; its name is the card id. The cards read FDA's own columns on the
derived tables, never a value derived from them, so they say the same on a release built with any
rules.
"""

from __future__ import annotations

import duckdb

from open_altio.faers.reader import quoted

from . import common

NB07 = "notebooks/faers/07_demographics_units.ipynb"
NS_QUARTERS = ("2013q1", "2014q2")  # the six quarters in which FDA wrote NS for an empty sex
EU_FROM = "2025q3"  # the first quarter in which EU replaces the member state
EU_CHART_FROM = "2024q1"
# the country FDA's two fields give a FAERS case: where the event happened, else the reporter's
FDA_COUNTRY = "coalesce(occr_country, reporter_country)"


def sex_not_specified_for_empty(con: duckdb.DuckDBPyConnection) -> dict:
    """From 2013Q1 to 2014Q2 FDA wrote NS (not specified) where the sex was empty. Documented."""
    empty, ns = "Sex empty", "Sex written NS (not specified)"
    rows = common.query(
        con,
        f"""
        SELECT quarter_T, {quoted(empty)}, 100.0 * count(*) FILTER (WHERE sex IS NULL) / count(*)
        FROM case_latest_T GROUP BY ALL
        UNION ALL
        SELECT quarter_T, {quoted(ns)}, 100.0 * count(*) FILTER (WHERE sex = 'NS') / count(*)
        FROM case_latest_T GROUP BY ALL""",
    )
    counts = common.query(
        con,
        """
        SELECT count(*), count(*) FILTER (WHERE sex = 'NS'), count(*) FILTER (WHERE sex IS NULL)
        FROM case_latest_T WHERE quarter_T BETWEEN ? AND ?""",
        list(NS_QUARTERS),
    )
    cases, said_ns, no_sex = counts[0] if counts else (0, 0, 0)
    xs = common.quarters(con)
    chart = common.chart(
        "line",
        "Quarter the case's latest version was published",
        "quarter",
        xs,
        "Share of cases",
        "percent",
        common.series(rows, xs, [empty, ns]),
        question="How often is a case's sex empty, and how often is it written NS?",
        note=(NS_QUARTERS[0], "NS takes the place of empty"),
    )
    first, last = (common.quarter_label(q) for q in NS_QUARTERS)
    return common.card(
        "sex_not_specified_for_empty",
        f"From {first} to {last} FDA wrote NS where a patient's sex was empty",
        f"From {first} to {last}, {common.pct(said_ns, cases)} of cases say NS (not specified) and "
        f"{no_sex:,} of {cases:,} have an empty sex, while before and after NS is almost absent "
        "and the field is simply left empty. A count of cases with no sex that leaves NS out "
        f"misses {common.plural(said_ns, 'case')} in those quarters; Open Altio reads NS, UNK and "
        "an empty field alike as sex not given, and keeps FDA's letter beside it.",
        chart,
        common.DOCUMENTED,
        NB07,
    )


def ages_without_a_unit(con: duckdb.DuckDBPyConnection) -> dict:
    """Cases that give an age with no unit, and why those ages are in years. Documented."""
    name = "Cases with an age but no unit"
    rows = common.query(
        con,
        f"""
        SELECT quarter_T, {quoted(name)}, count(*) FROM case_latest_T
        WHERE age IS NOT NULL AND age_cod IS NULL GROUP BY ALL""",
    )
    checked = common.query(
        con,
        """
        WITH x AS (SELECT case_key_T, caseid, age FROM case_latest_T
                   WHERE age IS NOT NULL AND age_cod IS NULL AND caseid IS NOT NULL)
        SELECT count(DISTINCT x.case_key_T),
               count(DISTINCT x.case_key_T) FILTER (WHERE o.age_cod = 'YR')
        FROM x JOIN demo_T o ON o.caseid = x.caseid AND o.age = x.age AND o.age_cod IS NOT NULL""",
    )
    elsewhere, in_years = checked[0] if checked else (0, 0)
    xs = common.quarters(con)
    lines = common.zeros(common.series(rows, xs, [name]))
    total = sum(n for _, _, n in rows)
    peak = max(rows, key=lambda r: r[2], default=None)
    chart = common.chart(
        "stacked_bar",
        "Quarter the case's latest version was published",
        "quarter",
        xs,
        "Cases with an age but no unit",
        "count",
        lines,
        question="When do cases give an age without its unit?",
        note=(peak[0], f"{peak[2]:,} cases") if peak else None,
    )
    return common.card(
        "ages_without_a_unit",
        f"{total:,} cases give an age with no unit, and they are in years",
        f"{common.plural(total, 'case')} give an age but no unit, most of them published in AERS's "
        "last years and around the switch to FAERS, so a count that needs the unit leaves them "
        f"without an age. Where another version of the same case gives the same number with a "
        f"unit, it is years for {common.pct(in_years, elsewhere)} of {elsewhere:,} cases, and the "
        "numbers are spread like ages in years, so Open Altio reads them as years.",
        chart,
        common.DOCUMENTED,
        NB07,
    )


def european_union_for_member_state(con: duckdb.DuckDBPyConnection) -> dict:
    """Since 2025Q3 many cases give EU, not the member state, as their country; an earlier
    version of the same case names the state for some of them."""
    back, none = "Member state named by an earlier version", "No member state given"
    rows = common.query(
        con,
        f"""
        WITH eu AS (SELECT quarter_T, caseid FROM case_latest_T
                    WHERE era_T = 'faers' AND {FDA_COUNTRY} = 'EU'),
             named AS (SELECT DISTINCT caseid FROM demo_T
                       WHERE era_T = 'faers' AND caseid IN (SELECT caseid FROM eu)
                         AND regexp_full_match(occr_country, '[A-Z]{{2}}') AND occr_country <> 'EU')
        SELECT quarter_T,
               CASE WHEN caseid IN (SELECT caseid FROM named) THEN {quoted(back)}
                    ELSE {quoted(none)} END,
               count(*)
        FROM eu GROUP BY ALL""",
    )
    recent = common.query(
        con,
        f"""
        SELECT count(*), count(*) FILTER (WHERE era_T = 'faers' AND {FDA_COUNTRY} = 'EU'),
               count(*) FILTER (WHERE era_T = 'faers' AND {FDA_COUNTRY} = 'EU'
                                AND starts_with(mfr_num, 'EU-'))
        FROM case_latest_T WHERE quarter_T >= ?""",
        [EU_FROM],
    )
    published, eu, eu_number = recent[0] if recent else (0, 0, 0)
    given_back = sum(n for q, kind, n in rows if q >= EU_FROM and kind == back)
    xs = common.quarters(con, since=EU_CHART_FROM)
    lines = common.zeros(common.series(rows, xs, [back, none]))
    first = common.quarter_label(EU_FROM)
    one_in = f"about one case in {round(published / eu)}" if eu else "some cases"
    chart = common.chart(
        "stacked_bar",
        "Quarter the case's latest version was published",
        "quarter",
        xs,
        "Cases whose country is EU",
        "count",
        lines,
        question="How many cases give the European Union instead of a member state?",
        note=(EU_FROM, "EU replaces the member state"),
    )
    return common.card(
        "european_union_for_member_state",
        f"Since {first} {one_in} names the European Union, not a member state",
        f"Since {first}, {eu:,} of the {published:,} cases published ({common.pct(eu, published)}) "
        "give EU as their country instead of the member state, and "
        f"{common.pct(eu_number, eu)} of them start the manufacturer's case number with EU- where "
        "it used to start with the country; before, EU is almost absent. For "
        f"{given_back:,} of them an earlier version of the same case still names the member state, "
        "which Open Altio shows, marked as from an earlier version; the rest show "
        '"European Union, member state not given".',
        chart,
        common.changed("kept_after_duplicates", "eu-member-state"),
        NB07,
    )
