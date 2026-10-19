"""The insight cards of notebooks 00, 01 and 90: how FDA publishes FAERS, and what reporting
changed over the years. Grain is `case_latest_T` (latest version of each case, deleted cases
removed) unless the card says otherwise. The reporter and report type cards are notebook 08's
(dates_codes.py).

Each function is one card; its name is the card id. Only derived tables are read, so a card runs
on a release folder and on the release build's own connection alike.
"""

from __future__ import annotations

import duckdb

from open_altio.faers.reader import quoted

from . import common

NB00 = "notebooks/faers/00_setup_and_inventory.ipynb"
NB01 = "notebooks/faers/01_volume_over_time.ipynb"
NB90 = "notebooks/faers/90_questions.ipynb"


def deleted_lists_unpublished(con: duckdb.DuckDBPyConnection) -> dict:
    """FDA's deleted-case lists name far more caseids than ever reached a
    published file, AERS or FAERS. Changed our pipeline: the published ones
    are removed."""
    rows = common.query(
        con,
        """
        WITH listed AS (
          SELECT caseid, coalesce(first_listed_quarter_T, 'history') AS first_T,
                 caseid IN (SELECT caseid FROM demo_T) AS published_T
          FROM deleted_cases_T)
        SELECT first_T, CASE WHEN published_T THEN 'Published in a quarterly file'
                             ELSE 'Never published' END, count(*)
        FROM listed GROUP BY ALL""",
    )
    names = ["Published in a quarterly file", "Never published"]
    quarters = sorted({r[0] for r in rows if r[0] != "history"})
    xs = (["history"] if any(r[0] == "history" for r in rows) else []) + quarters
    series = common.series(rows, xs, names)
    listed = sum(r[2] for r in rows)
    published = sum(r[2] for r in rows if r[1] == names[0])
    labels = ["Whole-history list only" if x == "history" else common.quarter_label(x) for x in xs]
    chart = common.chart(
        "stacked_bar",
        "Quarter whose list first named the case",
        "category",
        labels,
        "Case ids",
        "count",
        series,
    )
    return common.card(
        "deleted_lists_unpublished",
        "Most cases on FDA's deleted-case lists were never published",
        f"FDA's deleted-case lists name {listed:,} case ids, but only {published:,} of them "
        f"({common.pct(published, listed)}) ever appeared in a published quarterly file. "
        "We remove every published one from the release; the others never reached the files, "
        "so there is nothing to remove.",
        chart,
        common.changed("after_deleted_lists", "deleted-cases"),
        NB00,
    )


# The same senders under FDA's standard name and under a long legal name that
# appears from 2024Q4 (notebook 90, question 1c).
SENDER_SPELLINGS = [
    ("Eli Lilly", "ELI LILLY AND CO", "ELI LILLY AND COMPANY"),
    ("Bristol Myers Squibb", "BRISTOL MYERS SQUIBB", "BRISTOL-MYERS SQUIBB COMPANY"),
    ("Merck", "MERCK", "MERCK SHARP + DOHME LLC"),
    ("Bayer", "BAYER", "BAYER HEALTHCARE PHARMACEUTICALS INC."),
]
SENDER_WINDOW_FROM = "2022q1"


def sender_names_unstable(con: duckdb.DuckDBPyConnection) -> dict:
    """FDA standardizes sender names in FAERS, but from 2024Q4 large senders
    split across two spellings. Documented: no sender mapping yet."""
    values = ", ".join(
        f"({quoted(company)}, {quoted(std)}, {quoted(long)})"
        for company, std, long in SENDER_SPELLINGS
    )
    rows = common.query(
        con,
        f"""
        WITH names(company_T, std_T, long_T) AS (VALUES {values})
        SELECT c.quarter_T, n.company_T,
               100.0 * count(*) FILTER (WHERE c.mfr_sndr = n.long_T) / count(*)
        FROM case_latest_T c JOIN names n ON c.mfr_sndr IN (n.std_T, n.long_T)
        WHERE c.era_T = 'faers' AND c.quarter_T >= ?
        GROUP BY ALL""",
        [SENDER_WINDOW_FROM],
    )
    xs = common.quarters(con, SENDER_WINDOW_FROM)
    series = common.series(rows, xs, [company for company, _, _ in SENDER_SPELLINGS])
    chart = common.chart(
        "line",
        "Quarter published",
        "quarter",
        xs,
        "Share of the company's cases under its long legal name",
        "percent",
        series,
    )
    return common.card(
        "sender_names_unstable",
        "Sender names were standardized, then became unstable from 2024Q4",
        "FDA publishes FAERS sender names from a standard list, but from 2024Q4 Lilly, Bristol "
        "Myers Squibb and Bayer, and from 2025Q1 Merck, also appear under long legal names, and "
        "Lilly and Bayer flip back in 2026. Counting cases by sender after 2024 needs a mapping "
        "of these spellings, which we document but do not yet apply.",
        chart,
        common.DOCUMENTED,
        NB90,
    )


def rechal_filler(con: duckdb.DuckDBPyConnection) -> dict:
    """rechal is filled in, mostly with D, 2012Q4 to 2015Q3, while dechal is near empty."""
    rows = common.query(
        con,
        """
        SELECT quarter_T, 'dechal filled', 100.0 * count(dechal) / count(*)
        FROM drug_latest_T GROUP BY ALL
        UNION ALL
        SELECT quarter_T, 'rechal filled', 100.0 * count(rechal) / count(*)
        FROM drug_latest_T GROUP BY ALL""",
    )
    xs = common.quarters(con)
    series = common.series(rows, xs, ["dechal filled", "rechal filled"])
    chart = common.chart(
        "line",
        "Quarter published",
        "quarter",
        xs,
        "Share of drug rows with a value",
        "percent",
        series,
    )
    return common.card(
        "rechal_filler",
        "Rechallenge is filled in with D from 2012Q4 to 2015Q3, while dechallenge is near empty",
        "From 2012Q4 to 2015Q3 the rechallenge field is filled for over 90% of drug rows, mostly "
        "with D, does not apply, while dechallenge is almost empty until 2016Q3. When the same "
        "drug comes back in a later version, almost every D is gone, so the D is a filler, not an "
        "answer swapped with dechallenge.",
        chart,
        common.changed("report_versions", "not-given"),
        NB00,
    )


def country_empty_rising(con: duckdb.DuckDBPyConnection) -> dict:
    """occr_country empty share rises again from 2022. Documented."""
    rows = common.query(
        con,
        """
        SELECT init_year_T, 'Country empty',
               100.0 * count(*) FILTER (WHERE occr_country IS NULL) / count(*)
        FROM case_latest_T WHERE era_T = 'faers' AND init_year_T >= 2013 GROUP BY ALL
        UNION ALL
        SELECT init_year_T, 'United States',
               100.0 * count(*) FILTER (WHERE occr_country = 'US') / count(*)
        FROM case_latest_T WHERE era_T = 'faers' AND init_year_T >= 2013 GROUP BY ALL""",
    )
    xs = sorted({r[0] for r in rows})
    series = common.series(rows, xs, ["Country empty", "United States"])
    chart = common.chart(
        "line",
        "Year FDA first received the case",
        "year",
        xs,
        "Share of FAERS cases by country of the event",
        "percent",
        series,
    )
    return common.card(
        "country_empty_rising",
        "The country of the event is empty more often since 2022",
        "Cases with no country of occurrence almost disappear from 2017 to 2021, then come back "
        "from 2022 at 6% to 14% of FAERS cases a year, while the United States share falls from "
        "about 72% to about 60%. Country filters miss these cases; we document the gap and do "
        "not infer a country.",
        chart,
        common.DOCUMENTED,
        NB01,
    )
