"""The insight cards of notebook 03 (empty fields): how FDA's files and its senders write that a
value is not known, and what that leaves a reader. Every card reads what counts as empty from rule
`not-given`, so its exceptions apply here as everywhere else.

Each function is one card; its name is the card id. Grain is the rows FDA published in each
quarterly file (`demo_T`, every report version) for a change in FDA's files, and the latest version
of each case (`case_latest_T`, `drug_latest_T`) for what a reader sees. Only derived tables and the
reviewed sender mapping are read, so a card runs on a release folder and on the release build's own
connection alike.
"""

from __future__ import annotations

import duckdb

from open_altio import rulebook
from open_altio.faers import not_given
from open_altio.faers.reader import quoted

from . import common

NB03 = "notebooks/faers/03_empty_fields.ipynb"
STEP = "report_versions"  # rule not-given acts as FDA's rows are read
# FDA's sender spellings grouped as company names, reviewed; FDA's mfr_sndr is never changed
SENDER_MAPPING = rulebook.data_root() / rulebook.value("company-names", "mapping")
RECENT_FROM = "2023q1"  # the quarters a change in FDA's newest files is read against
DIRECT, COMPANY = "Direct reports", "Company reports"
LARGEST_SENDERS = 10


def _blank(expr: str) -> str:
    """SQL: the rule's blank, nothing or only spaces (a field it reads for nothing more)."""
    return not_given.check("", expr)


def _report_kind() -> str:
    return f"CASE WHEN rept_cod = 'DIR' THEN {quoted(DIRECT)} ELSE {quoted(COMPANY)} END"


def _pct(lines: list[dict], name: str, x: str, xs: list) -> float | None:
    values = next(s["values"] for s in lines if s["name"] == name)
    return values[xs.index(x)] if x in xs else None


def unknown_written_two_ways(con: duckdb.DuckDBPyConnection) -> dict:
    """A missing route is written blank or UNKNOWN, and FDA's 2026 files turned UNKNOWN into
    blank. Changed our pipeline: rule not-given reads both as one state."""
    given, unknown, blank = "Given", "Says unknown", "Blank"
    rows = common.query(
        con,
        f"""
        SELECT quarter_T,
               CASE WHEN {_blank("route")} THEN {quoted(blank)}
                    WHEN {not_given.check("route")} THEN {quoted(unknown)}
                    ELSE {quoted(given)} END,
               100.0 * count(*) / sum(count(*)) OVER (PARTITION BY quarter_T)
        FROM drug_latest_T WHERE era_T = 'faers' AND quarter_T >= ? GROUP BY 1, 2""",
        [RECENT_FROM],
    )
    xs = common.quarters(con, RECENT_FROM)
    lines = common.zeros(common.series(rows, xs, [given, unknown, blank]))
    last = xs[-1] if xs else None
    before = xs[-3] if len(xs) >= 3 else last
    chart = common.chart(
        "stacked_area",
        "Quarter of the case's latest version",
        "quarter",
        xs,
        "Share of drug rows",
        "percent",
        lines,
        question="How do FDA's files give a drug's route, quarter by quarter?",
        note=(last, "UNKNOWN turns into blank"),
    )

    def share(name: str, x: str | None) -> str:
        v = _pct(lines, name, x, xs) if x else None
        return f"{v:.0f}%" if v is not None else "none"

    return common.card(
        "unknown_written_two_ways",
        f"Unknown is written two ways, and FDA's {(last or '')[:4]} files swapped one for the "
        "other",
        f"A missing route reaches FAERS as a blank or as UNKNOWN, by the sender's habit, and in "
        f"{common.quarter_label(last or '')} FDA's files wrote UNKNOWN on {share(unknown, last)} "
        f"of drug rows against {share(unknown, before)} in {common.quarter_label(before or '')}, "
        f"while blank rose from {share(blank, before)} to {share(blank, last)}. Counted apart, "
        "the two draw trends that are not real, so we read both, and every other way of saying "
        f"unknown, as one state: {not_given.label()}.",
        chart,
        common.changed(STEP, "not-given"),
        NB03,
    )


def who_reported_lost_on_company_reports(con: duckdb.DuckDBPyConnection) -> dict:
    """occp_cod goes blank on company reports from 2025Q3, not on direct reports. Changed our
    pipeline: the explorer notes it on the field (rule explorer-field-notes)."""
    since = next(
        n["from"]
        for n in rulebook.value("explorer-field-notes", "notes")
        if n["field"] == "occp_cod"
    )
    rows = common.query(
        con,
        f"""
        SELECT quarter_T, {_report_kind()},
               100.0 * count(*) FILTER (WHERE NOT {not_given.check("occp_cod")}) / count(*),
               100.0 * count(*) FILTER (WHERE occp_cod = 'CN') / count(*)
        FROM demo_T WHERE era_T = 'faers' AND quarter_T >= ? GROUP BY ALL""",
        [RECENT_FROM],
    )
    xs = common.quarters(con, RECENT_FROM)
    lines = common.series([r[:3] for r in rows], xs, [COMPANY, DIRECT])
    consumers = {r[0]: r[3] for r in rows if r[1] == COMPANY}
    last = xs[-1] if xs else None
    before = xs[xs.index(since) - 1] if since in xs and xs.index(since) > 0 else None
    chart = common.chart(
        "line",
        "Quarter published",
        "quarter",
        xs,
        "Share of reports saying who reported",
        "percent",
        lines,
        question="Do FDA's files still say who reported?",
        note=(since, "Company reports start losing it"),
    )

    def share(name: str, x: str | None) -> str:
        v = _pct(lines, name, x, xs) if x else None
        return f"{v:.0f}%" if v is not None else "none"

    def consumer(x: str | None) -> str:
        return f"{consumers[x]:.0f}%" if x in consumers else "none"

    return common.card(
        "who_reported_lost_on_company_reports",
        f"From {common.quarter_label(since)}, FDA's files stop saying who reported on company "
        "reports",
        f"FDA's files said who reported on {share(COMPANY, before)} of company reports in "
        f"{common.quarter_label(before or '')} and on {share(COMPANY, last)} in "
        f"{common.quarter_label(last or '')}; consumers fell from {consumer(before)} to "
        f"{consumer(last)} of them. Direct reports, which people send FDA themselves, kept it "
        f"({share(DIRECT, last)} in {common.quarter_label(last or '')}), so a count by who "
        "reported after mid-2025 shows a change in FDA's files, not in who reports; the explorer "
        "says so under the field's chart and filter.",
        chart,
        common.changed(STEP, "not-given", "explorer-field-notes"),
        NB03,
    )


def completeness_depends_on_sender(con: duckdb.DuckDBPyConnection) -> dict:
    """How many of age, sex and event date a case gives depends on the company that sent it.
    Changed our pipeline: every explorer chart says how many of its cases give the field (rule
    not-given), and senders are counted by company (the reviewed sender mapping). Sex is given
    where sex_T is (rule sex-codes)."""
    kinds = ["All three", "Two", "One", "None"]
    given = " + ".join(
        f"(NOT {not_given.check(f, f'c.{f}')})::INT" for f in ("age", "sex_T", "event_dt")
    )
    rows = common.query(
        con,
        f"""
        WITH m AS (SELECT fda_value, company
                   FROM read_csv({quoted(SENDER_MAPPING.as_posix())}, all_varchar = true)),
        c AS (
          SELECT CASE WHEN c.rept_cod = 'DIR' THEN {quoted(DIRECT)} ELSE m.company END AS sender_T,
                 {given} AS given_T
          FROM case_latest_T c LEFT JOIN m ON m.fda_value = c.mfr_sndr AND c.rept_cod <> 'DIR'
          WHERE c.era_T = 'faers'),
        top AS (
          SELECT sender_T FROM c WHERE sender_T IS NOT NULL AND sender_T <> {quoted(DIRECT)}
          GROUP BY 1 ORDER BY count(*) DESC, sender_T LIMIT {LARGEST_SENDERS})
        SELECT sender_T, given_T, 100.0 * count(*) / sum(count(*)) OVER (PARTITION BY sender_T),
               sum(count(*)) OVER (PARTITION BY sender_T)
        FROM c WHERE sender_T IN (SELECT sender_T FROM top) OR sender_T = {quoted(DIRECT)}
        GROUP BY 1, 2""",
    )
    size = {r[0]: r[3] for r in rows}
    xs = sorted((s for s in size if s != DIRECT), key=lambda s: (-size[s], s))
    xs += [DIRECT] if DIRECT in size else []
    named = [(x, kinds[3 - g], v) for x, g, v, _ in rows]
    lines = common.zeros(common.series(named, xs, kinds))
    complete = {x: v for x, v in zip(xs, lines[0]["values"], strict=True)}
    companies = [x for x in xs if x != DIRECT]
    low = min(companies, key=lambda x: complete[x]) if companies else None
    high = max(companies, key=lambda x: complete[x]) if companies else None
    chart = common.chart(
        "stacked_bar",
        "Sender, largest first",
        "category",
        xs,
        "Share of the sender's cases",
        "percent",
        lines,
        question="How many of age, sex and event date do the largest senders give?",
        note=(low, "Fewest cases with all three") if low else None,
    )
    spread = (
        f"ranges from {complete[low]:.0f}% ({low}) to {complete[high]:.0f}% ({high})"
        if low and high
        else "cannot be measured here: no sender in this release is in the mapping"
    )
    direct = f"{complete[DIRECT]:.0f}%" if DIRECT in complete else "none"
    return common.card(
        "completeness_depends_on_sender",
        "How complete a case is depends on who sent it",
        f"Among the {len(companies)} companies that sent the most FAERS cases, the share of cases "
        f"giving the patient's age and sex and the event date {spread}; direct reports give all "
        f"three in {direct}. A product's cases carry the habits of the companies that report it, "
        "so every chart in the explorer says how many of its cases give the field, and senders "
        "are counted by company, their spellings grouped.",
        chart,
        common.changed(STEP, "not-given"),
        NB03,
    )


def to_mfr_filler_on_company_reports(con: duckdb.DuckDBPyConnection) -> dict:
    """to_mfr means something only on direct reports; on company reports it is a filler.
    Changed our pipeline: rule not-given reads it only on direct reports."""
    rows = common.query(
        con,
        f"""
        SELECT quarter_T, {_report_kind()},
               100.0 * count(*) FILTER (WHERE NOT {_blank("to_mfr")}) / count(*),
               count(*) FILTER (WHERE upper(trim(to_mfr)) = 'N')
        FROM demo_T GROUP BY ALL""",
    )
    xs = common.quarters(con)
    lines = common.series([r[:3] for r in rows], xs, [DIRECT, COMPANY])
    filled = [r for r in rows if r[1] == COMPANY and r[2] > 50]
    window = sorted(r[0] for r in filled)
    fillers = sum(r[3] for r in filled)
    direct = common.query(
        con,
        f"""SELECT 100.0 * count(*) FILTER (WHERE NOT {_blank("to_mfr")}) / count(*)
            FROM demo_T WHERE rept_cod = 'DIR'""",
    )
    span = (
        f"{fillers:,} of them say N from {common.quarter_label(window[0])} to "
        f"{common.quarter_label(window[-1])}"
        if window
        else "it is never filled on most of them"
    )
    chart = common.chart(
        "line",
        "Quarter published",
        "quarter",
        xs,
        "Share of report versions with to_mfr filled",
        "percent",
        lines,
        question="On which reports is to_mfr filled?",
        note=(window[0], "Company reports filled with N") if window else None,
    )
    return common.card(
        "to_mfr_filler_on_company_reports",
        "Whether the reporter also told the company is a filler on company reports",
        "to_mfr asks whether a person who reported straight to FDA also told the company, so it "
        "means something only on direct reports, where FDA's files fill it on "
        f"{(direct[0][0] or 0) if direct else 0:.0f}% of report versions. Company reports are "
        f"blank in almost every quarter, and {span}, a filler, so we read to_mfr on a company "
        f"report as {not_given.label()}.",
        chart,
        common.changed(STEP, "not-given"),
        NB03,
    )
