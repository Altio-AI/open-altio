"""The insight cards of notebook 08 (dates and codes): what FDA's dates and codes do to a count,
measured on the release. Cases are the default case set (`case_latest_T` where `dup_kept_T`);
a card that counts therapy lines or drug rows says so.

Each function is one card; its name is the card id. Only derived tables are read, so a card runs
on a release folder and on the release build's own connection alike.
"""

from __future__ import annotations

import statistics

import duckdb

from open_altio import rulebook
from open_altio.faers.fda import FIRST_FAERS_QUARTER
from open_altio.faers.reader import quoted

from . import common

NB08 = "notebooks/faers/08_dates_and_codes.ipynb"
DATES, CODES = "dates", "codes"  # the funnel steps these cards' rules act in
_KEPT = "SELECT era_T, primaryid, quarter_T FROM case_latest_T WHERE dup_kept_T"
CONTROL_DAY = "15"  # a day of the month no one pads to, to compare the 1st with
REPEATS_FROM = "2023q1"  # the window of the repeated drug sequence number card


def _padded_from() -> str:
    return rulebook.value("event-date-precision", "faers_from_quarter")


def _month_day() -> str:
    return rulebook.value("event-date-precision", "month_day")


def _faers_before(quarters: list[str], since: str) -> list[str]:
    return [q for q in quarters if FIRST_FAERS_QUARTER <= q < since]


def event_dates_padded(con: duckdb.DuckDBPyConnection) -> dict:
    """From 2021Q3 FDA writes an event date known only to its month as the 1st, as legacy AERS
    did. Changed our pipeline: in those versions a date on the 1st is known to its month, on
    1 January to its year (rules/event-date-precision.md)."""
    since, day = _padded_from(), _month_day()
    on_1st, on_15th = "On the 1st of a month", f"On the {CONTROL_DAY}th, for comparison"
    rows = common.query(
        con,
        f"""
        SELECT quarter_T, {quoted(on_1st)},
               100.0 * count(*) FILTER (WHERE right(event_dt, 2) = ?) / count(*)
        FROM case_latest_T WHERE dup_kept_T AND length(event_dt) = 8 GROUP BY ALL
        UNION ALL
        SELECT quarter_T, {quoted(on_15th)},
               100.0 * count(*) FILTER (WHERE right(event_dt, 2) = ?) / count(*)
        FROM case_latest_T WHERE dup_kept_T AND length(event_dt) = 8 GROUP BY ALL""",
        [day, CONTROL_DAY],
    )
    xs = common.quarters(con)
    share = {(q, s): v for q, s, v in rows}
    before = _faers_before(xs, since)
    after = [q for q in xs if q >= since]
    base = [share[q, on_1st] for q in before if (q, on_1st) in share]
    late = [share[q, on_1st] for q in after if (q, on_1st) in share]
    control = [share[q, on_15th] for q in before + after if (q, on_15th) in share]
    chart = common.chart(
        "line",
        "Quarter published",
        "quarter",
        xs,
        "Share of full event dates",
        "percent",
        common.series(rows, xs, [on_1st, on_15th]),
        question="Did FDA write partial event dates as the 1st of the month?",
        note=(since, "Padding begins"),
    )
    words = (
        f"{min(late):.0f}% to {max(late):.0f}% of full event dates a quarter fall on the 1st, "
        f"against a median of {statistics.median(base):.1f}% from "
        f"{common.quarter_label(before[0])} to {common.quarter_label(before[-1])} and "
        f"{statistics.median(control):.1f}% on the {CONTROL_DAY}th"
        if base and late and control
        else "the share of full event dates on the 1st jumps"
    )
    return common.card(
        "event_dates_padded",
        f"Since {common.quarter_label(since)} FDA writes an event date known only to its month "
        "as the 1st",
        f"From {common.quarter_label(since)} FDA writes a month-only event date as the 1st and a "
        f"year-only one as 1 January, as legacy AERS did: {words}. In those versions we read an "
        "event date on the 1st as known to its month, and on 1 January to its year, so no time "
        "to onset is counted from a day nobody reported.",
        chart,
        common.changed(DATES, "event-date-precision"),
        NB08,
    )


def padding_puts_reactions_before_drug(con: duckdb.DuckDBPyConnection) -> dict:
    """A padded event date makes a reaction look as if it came before the drug. Changed our
    pipeline: time to onset only from two dates known to the day, and none when the event is
    before the first dose (rules/time-to-onset.md). Grain: therapy lines whose start and whose
    case's event date are both full dates as FDA wrote them."""
    since, day = _padded_from(), _month_day()
    on_1st, other = "Event dated the 1st of a month", "Event dated any other day"
    period = (
        f"CASE WHEN c.era_T = 'legacy' THEN 'legacy' WHEN c.quarter_T < {quoted(since)} "
        "THEN 'before' ELSE 'after' END"
    )
    rows = common.query(
        con,
        f"""
        SELECT c.quarter_T, {period} AS period_T,
               CASE WHEN right(c.event_dt, 2) = ? THEN {quoted(on_1st)}
                    ELSE {quoted(other)} END AS day_T,
               count(*) FILTER (WHERE c.event_dt < t.start_dt) AS before_T, count(*) AS n_T
        FROM ther_latest_T t JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
        WHERE c.dup_kept_T AND length(c.event_dt) = 8 AND length(t.start_dt) = 8
        GROUP BY ALL""",
        [day],
    )
    xs = common.quarters(con)
    lines = [(q, d, 100.0 * b / n) for q, _, d, b, n in rows]
    pooled: dict[tuple[str, str], list[int]] = {}
    for _, p, d, b, n in rows:
        acc = pooled.setdefault((p, d), [0, 0])
        acc[0] += b
        acc[1] += n

    def pct(p: str, d: str) -> float:
        b, n = pooled.get((p, d), [0, 0])
        return 100.0 * b / n if n else 0.0

    chart = common.chart(
        "line",
        "Quarter published",
        "quarter",
        xs,
        "Therapy lines with the event before the drug's start",
        "percent",
        common.series(lines, xs, [on_1st, other]),
        question="Does a padded date make a reaction look as if it came before the drug?",
        note=(since, "Padding begins"),
    )
    before = _faers_before(xs, since)
    span = (
        f"{common.quarter_label(before[0])} to {common.quarter_label(before[-1])}"
        if before
        else "the versions before"
    )
    return common.card(
        "padding_puts_reactions_before_drug",
        "Padded event dates make reactions look as if they came before the drug",
        f"In therapy lines published from {common.quarter_label(since)} a reaction dated the 1st "
        f"comes before the drug's start in {pct('after', on_1st):.0f}% of lines, against "
        f"{pct('after', other):.0f}% for other days, while from {span}, before the padding, the "
        f"two match ({pct('before', on_1st):.1f}% and {pct('before', other):.1f}%). We count a "
        "time to onset only from an event date and a first dose both known to the day, and leave "
        "it empty when the event comes before the first dose.",
        chart,
        common.changed(DATES, "time-to-onset"),
        NB08,
    )


REPORTER_LINES = [
    ("OT", "Other health professional (OT)"),
    ("HP", "Health professional (HP)"),
    ("MD", "Physician (MD)"),
    ("PH", "Pharmacist (PH)"),
]
ONE_TYPE = "OT and HP read as one type"
OTHER_PROFESSIONAL = "3"  # E2B(R3) code list 6: other health professional


def occupation_code_changes(con: duckdb.DuckDBPyConnection) -> dict:
    """occp_cod: OT ends and HP begins in 2020, a new name for the same reporters. Changed our
    pipeline: both are read as the E2B(R3) other health professional (rules/reporter-type.md)."""
    codes = ", ".join(f"({quoted(c)}, {quoted(n)})" for c, n in REPORTER_LINES)
    rows = common.query(
        con,
        f"""
        WITH names(code_T, name_T) AS (VALUES {codes}),
        c AS (SELECT quarter_T, occp_cod, reporter_type_T FROM case_latest_T
              WHERE dup_kept_T AND era_T = 'faers'),
        n AS (SELECT quarter_T, count(*) AS n_T FROM c GROUP BY 1)
        SELECT c.quarter_T, names.name_T, 100.0 * count(*) / any_value(n.n_T)
        FROM c JOIN names ON c.occp_cod = names.code_T JOIN n USING (quarter_T) GROUP BY ALL
        UNION ALL
        SELECT c.quarter_T, {quoted(ONE_TYPE)},
               100.0 * count(*) FILTER (WHERE reporter_type_T = ?) / any_value(n.n_T)
        FROM c JOIN n USING (quarter_T) GROUP BY ALL""",
        [OTHER_PROFESSIONAL],
    )
    xs = common.quarters(con, FIRST_FAERS_QUARTER)
    names = [ONE_TYPE] + [n for _, n in REPORTER_LINES]
    series = common.series(rows, xs, names)
    if rows:  # a reporter code absent from a quarter is 0% of it; no rows at all is no data
        common.zeros(series)
    share = {s["name"]: dict(zip(xs, s["values"], strict=True)) for s in series}
    ot, hp = share[REPORTER_LINES[0][1]], share[REPORTER_LINES[1][1]]
    first_hp = next((q for q in xs if (hp[q] or 0) >= 1), None)
    last_ot = max((q for q in xs if (ot[q] or 0) >= 1), default=None)
    chart = common.chart(
        "line",
        "Quarter published",
        "quarter",
        xs,
        "Share of FAERS cases",
        "percent",
        series,
        question="Did fewer health professionals report in 2020, or did the code change?",
        note=(first_hp, "HP replaces OT") if first_hp else None,
    )
    later = max((ot[q] or 0 for q in xs if last_ot and q > last_ot), default=0)
    when = (
        f"OT, other health professional, is {ot[last_ot]:.1f}% of FAERS cases in "
        f"{common.quarter_label(last_ot)} and {'none' if later == 0 else 'almost none'} after, "
        f"when HP, health professional, starts at {hp[first_hp]:.1f}%"
        if first_hp and last_ot
        else "OT, other health professional, gives way to HP, health professional"
    )
    return common.card(
        "occupation_code_changes",
        "FDA renamed the other health professional code from OT to HP in 2020",
        f"{when}, while physicians and pharmacists show no such step. We read both as ICH "
        "E2B(R3)'s other health professional, so a count by reporter type runs straight across "
        "2020, with FDA's own code beside it.",
        chart,
        common.changed(CODES, "reporter-type"),
        NB08,
    )


def _with_outcome(alias: str) -> str:
    return (
        f"EXISTS (SELECT 1 FROM outc_latest_T o WHERE o.era_T = {alias}.era_T "
        f"AND o.primaryid = {alias}.primaryid AND o.quarter_T = {alias}.quarter_T)"
    )


def rept_cod_combination_products(con: duckdb.DuckDBPyConnection) -> dict:
    """30-day reports are device malfunctions on drug-device combination products, with no
    adverse event, not expedited reports. Documented: FDA's report type is kept as given."""
    none30, out30, five = (
        "30-day, no outcome",
        "30-day, with an outcome",
        "5-day",
    )
    rows = common.query(
        con,
        f"""
        SELECT c.init_year_T,
               CASE WHEN c.rept_cod = '5DAY' THEN {quoted(five)}
                    WHEN {_with_outcome("c")} THEN {quoted(out30)}
                    ELSE {quoted(none30)} END,
               count(*)
        FROM case_latest_T c
        WHERE c.dup_kept_T AND c.rept_cod IN ('30DAY', '5DAY') GROUP BY ALL""",
    )
    years = common.query(
        con,
        "SELECT DISTINCT init_year_T FROM case_latest_T WHERE era_T = 'faers' "
        "AND init_year_T >= 2013 ORDER BY 1",
    )
    xs = [y for (y,) in years]
    series = common.zeros(common.series(rows, xs, [none30, out30, five]))
    total = {name: sum(n for _, k, n in rows if k == name) for name in (none30, out30, five)}
    n30 = total[none30] + total[out30]
    [(first,)] = common.query(
        con, "SELECT min(quarter_T) FROM case_latest_T WHERE dup_kept_T AND rept_cod = '30DAY'"
    ) or [(None,)]
    chart = common.chart(
        "stacked_bar",
        "Year FDA first received the case",
        "year",
        xs,
        "Cases",
        "count",
        series,
        question="What do 30-day reports carry?",
        note=(int(first[:4]), "Combination-product rule") if first else None,
    )
    return common.card(
        "rept_cod_combination_products",
        "30-day reports are device malfunctions, not expedited reports",
        f"Since {common.quarter_label(first) if first else 'they began'} FDA has published "
        f"{n30:,} cases as 30-day reports, which FDA's "
        "E2B(R3) rules keep for a malfunction of a drug-device combination product with no "
        f"adverse event, and {common.pct(total[none30], n30)} give no outcome; "
        f"{total[five]:,} 5-day reports ask for remedial action. We keep FDA's report type as "
        "given and count neither as an expedited 15-day report, as DiAna does.",
        chart,
        common.DOCUMENTED,
        NB08,
    )


def no_outcome_not_non_serious(con: duckdb.DuckDBPyConnection) -> dict:
    """A case with no outcome is not a non-serious case: some expedited reports, sent because
    the reaction is serious, give none. Documented: never called non-serious."""
    exp, per = "Expedited (15-day) reports", "Periodic reports"
    rows = common.query(
        con,
        f"""
        SELECT c.init_year_T, CASE c.rept_cod WHEN 'EXP' THEN {quoted(exp)}
                                ELSE {quoted(per)} END,
               count(*) FILTER (WHERE NOT {_with_outcome("c")}) AS none_T, count(*) AS n_T
        FROM case_latest_T c
        WHERE c.dup_kept_T AND c.rept_cod IN ('EXP', 'PER') GROUP BY ALL""",
    )
    xs = sorted({r[0] for r in rows if r[0] is not None and r[0] >= common.FIRST_YEAR})
    lines = [(y, k, 100.0 * none / n) for y, k, none, n in rows if y in xs]
    count = {
        k: [sum(r[2] for r in rows if r[1] == k), sum(r[3] for r in rows if r[1] == k)]
        for k in (exp, per)
    }
    chart = common.chart(
        "line",
        "Year FDA first received the case",
        "year",
        xs,
        "Share of the report type's cases with no outcome",
        "percent",
        common.series(lines, xs, [exp, per]),
        question="Does a case with no outcome mean the reaction was not serious?",
    )
    return common.card(
        "no_outcome_not_non_serious",
        "A case with no outcome is not a non-serious case",
        f"FDA gives no outcome for {count[exp][0]:,} cases sent as expedited reports, which go to "
        "FDA within 15 days because the reaction is serious, as well as for "
        f"{common.pct(count[per][0], count[per][1])} of periodic reports, mostly about "
        "non-serious reactions. We never call a case with no outcome non-serious, as DiAna does; "
        "an expedited one says it was sent for serious reactions with no seriousness criterion.",
        chart,
        common.DOCUMENTED,
        NB08,
    )


def drug_seq_repeated(con: duckdb.DuckDBPyConnection) -> dict:
    """From 2024Q4 FDA often writes one drug on several rows under one drug_seq, one row per
    dosage regimen. Documented. Grain: FAERS drug rows of the default case set."""
    name = "Drug rows sharing their drug number"
    rows = common.query(
        con,
        f"""
        WITH r AS (
          SELECT d.quarter_T, d.primaryid, d.drug_seq, count(*) AS n_T
          FROM drug_latest_T d JOIN ({_KEPT}) k USING (era_T, primaryid, quarter_T)
          WHERE d.era_T = 'faers' AND d.quarter_T >= ? GROUP BY ALL)
        SELECT quarter_T, {quoted(name)},
               100.0 * coalesce(sum(n_T) FILTER (WHERE n_T > 1), 0) / sum(n_T)
        FROM r GROUP BY ALL""",
        [REPEATS_FROM],
    )
    xs = common.quarters(con, REPEATS_FROM)
    share = {q: v for q, _, v in rows}
    first = next((q for q in xs if share.get(q, 0) >= 1), None)
    last = xs[-1] if xs else None
    chart = common.chart(
        "line",
        "Quarter published",
        "quarter",
        xs,
        "Share of FAERS drug rows",
        "percent",
        common.series(rows, xs, [name]),
        question="Does one row of FDA's drug file still mean one drug?",
        note=(first, "Repeats begin") if first else None,
    )
    when = (
        f"From {common.quarter_label(first)} FDA often writes one drug on several rows, one per "
        "dosage regimen, under the same drug sequence number: "
        f"{share.get(last, 0):.0f}% of the drug rows published in {common.quarter_label(last)}"
        if first and last
        else "FDA writes each drug on one row under its own drug sequence number"
    )
    return common.card(
        "drug_seq_repeated",
        f"One drug can fill several rows of FDA's drug file since {common.quarter_label(first)}"
        if first
        else "One drug, one row of FDA's drug file",
        f"{when}. A count of drugs must count each case's drug sequence numbers, not FDA's rows, "
        "and time to onset takes each drug's earliest start however many rows it has.",
        chart,
        common.DOCUMENTED,
        NB08,
    )
