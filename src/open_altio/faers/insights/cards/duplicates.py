"""The insight cards of notebook 04 (duplicates): what FDA's data shows
about one event reaching FAERS more than once, and about the fields
duplicate matching needs.

Each function is one card; its name is the card id. Grain is `case_latest_T`
joined to `case_dup_T` (one row per case, latest version, deleted cases
removed). Only derived tables are read, so a card runs on a release folder
and on the release build's own connection alike. The numbers the rules set
(group size, age gap) come from the rule files.
"""

from __future__ import annotations

import duckdb

from open_altio import rulebook
from open_altio.faers.reader import quoted, sql_in

from . import common

NB04 = "notebooks/faers/04_duplicates.ipynb"
STEP = "kept_after_duplicates"
NUMBER_RULES = ("manufacturer_number", "manufacturer_number_country_code")


def _years(rows: list[tuple]) -> list:
    return sorted({r[0] for r in rows if r[0] is not None and r[0] >= common.FIRST_YEAR})


def _padded(col: str) -> str:
    """SQL: the event date in `col` is padded (a 1 January full date) or a month or year only."""
    full = rulebook.value("dup-padded-event-dates", "full_date_length")
    md = rulebook.value("dup-padded-event-dates", "padded_month_day")
    return f"(length({col}) < {full} OR right({col}, {len(md)}) = {quoted(md)})"


def same_event_several_cases(con: duckdb.DuckDBPyConnection) -> dict:
    """One event reaches FAERS as two or more cases: from a second company,
    from a company and a direct report, or from one company under two case
    numbers. Changed our pipeline: probable duplicates are flagged and one
    copy per event is shown, the latest received, dated by the earliest
    receipt of any copy (rules/dup-shown-copy.md)."""
    two, direct, one = (
        "A second company",
        "A company and a direct report",
        "One company under two case numbers",
    )
    rows = common.query(
        con,
        f"""
        WITH m AS (
          SELECT d.case_key_T, d.dup_kept_T, d.dup_shown_case_T, d.group_first_dt_T, c.mfr_sndr,
                 c.rept_cod
          FROM case_dup_T d JOIN case_latest_T c USING (era_T, case_key_T)
          WHERE d.probable_duplicate_T)
        SELECT year(s.group_first_dt_T),
               CASE WHEN a.rept_cod = 'DIR' OR s.rept_cod = 'DIR' THEN {quoted(direct)}
                    WHEN a.mfr_sndr = s.mfr_sndr THEN {quoted(one)} ELSE {quoted(two)} END,
               count(*)
        FROM m a JOIN m s ON s.case_key_T = a.dup_shown_case_T
        WHERE NOT a.dup_kept_T
        GROUP BY ALL""",
    )
    xs = _years(rows)
    series = common.zeros(common.series(rows, xs, [two, direct, one]))
    aside = sum(n for _, _, n in rows)
    total = common.query(con, "SELECT count(*) FROM case_latest_T")
    cases = total[0][0] if total else 0
    by_kind = {k: sum(n for _, kk, n in rows if kk == k) for k in (two, direct, one)}
    # Why the latest copy is shown: where one company sent an event twice,
    # the later copy more often holds the follow-up's added reactions.
    richer = common.query(
        con,
        """
        WITH m AS (
          SELECT d.dup_group_T, d.dup_kept_T, c.era_T, c.primaryid, c.quarter_T, c.mfr_sndr
          FROM case_dup_T d JOIN case_latest_T c USING (era_T, case_key_T)
          WHERE d.probable_duplicate_T),
        pairs AS (SELECT dup_group_T FROM m GROUP BY 1
                  HAVING count(*) = 2 AND count(DISTINCT mfr_sndr) = 1),
        pts AS (
          SELECT m.dup_group_T, m.dup_kept_T, count(r.pt) AS n_T
          FROM m JOIN pairs USING (dup_group_T)
          LEFT JOIN reac_latest_T r USING (era_T, primaryid, quarter_T) GROUP BY ALL),
        p AS (SELECT max(n_T) FILTER (WHERE dup_kept_T) AS later_T,
                     max(n_T) FILTER (WHERE NOT dup_kept_T) AS earlier_T
              FROM pts GROUP BY dup_group_T)
        SELECT count(*) FILTER (WHERE later_T <> earlier_T),
               count(*) FILTER (WHERE later_T > earlier_T),
               count(*) FILTER (WHERE earlier_T > later_T) FROM p""",
    )
    differ, later_more, earlier_more = richer[0] if richer else (0, 0, 0)
    chart = common.chart(
        "stacked_bar",
        "Year FDA first received any copy of the event",
        "year",
        xs,
        "Cases set aside as a copy of another",
        "count",
        series,
        question="Where do the extra copies of an event come from?",
    )
    why = (
        " Where one company sent an event twice and the copies list different reactions, the later "
        f"copy lists more in {common.pct(later_more, differ)} of pairs and the earlier in "
        f"{common.pct(earlier_more, differ)}."
        if differ
        else ""
    )
    share = f"{100.0 * aside / cases if cases else 0:.1f}%"
    return common.card(
        "same_event_several_cases",
        "The same event often reaches FAERS as two or more cases",
        f"{common.plural(aside, 'case')} ({share} of all cases) repeat an event already in FAERS "
        f"under another case number: {by_kind[two]:,} sent by a second company, "
        f"{by_kind[direct]:,} where a company and a direct report both sent it, and "
        f"{by_kind[one]:,} by one company under two numbers. We flag them and show one copy per "
        "event, the latest received, dated when FDA first received any copy." + why,
        chart,
        common.changed(STEP, "dedup-default"),
        NB04,
    )


def one_case_two_numbers(con: duckdb.DuckDBPyConnection) -> dict:
    """One company's case sent to FDA under two case numbers, found by the
    company's own case number. Changed our pipeline: matched on manufacturer
    number and sender, except where the copies disagree on sex or on age by
    more than the rule's gap (rules/dup-manufacturer-number.md)."""
    matched, skipped = (
        "Set aside: same company case number",
        "Not matched: one number, different patients",
    )
    sexes = rulebook.value("dup-manufacturer-number", "clashing_sexes")
    gap = rulebook.value("dup-manufacturer-number", "max_age_gap_years")
    rules = ", ".join(quoted(r) for r in NUMBER_RULES)
    rows = common.query(
        con,
        f"""
        SELECT c.init_year_T, {quoted(matched)}, count(*)
        FROM case_dup_T d JOIN case_latest_T c USING (era_T, case_key_T)
        WHERE NOT d.dup_kept_T AND len(list_intersect(d.dup_rule_T, [{rules}])) > 0
        GROUP BY ALL""",
    )
    guarded = common.query(
        con,
        f"""
        WITH n AS (
          SELECT upper(trim(mfr_sndr)) AS sndr_T, upper(trim(mfr_num)) AS num_T,
                 count(DISTINCT upper(sex)) FILTER (WHERE {sql_in("upper(sex)", sexes)}) > 1
                   AS sex_T,
                 coalesce(max(age_years_T) - min(age_years_T) > {gap}, false) AS age_T
          FROM case_latest_T WHERE mfr_num IS NOT NULL AND mfr_sndr IS NOT NULL
          GROUP BY 1, 2 HAVING count(*) > 1)
        SELECT c.init_year_T, {quoted(skipped)}, count(*)
        FROM case_latest_T c
        JOIN n ON n.sndr_T = upper(trim(c.mfr_sndr)) AND n.num_T = upper(trim(c.mfr_num))
        WHERE n.sex_T OR n.age_T GROUP BY ALL""",
    )
    rows += guarded
    xs = _years(rows)
    series = common.zeros(common.series(rows, xs, [matched, skipped]))
    n_matched = sum(n for _, k, n in rows if k == matched)
    before_2012 = sum(n for y, k, n in rows if k == matched and y is not None and y < 2012)
    n_skipped = sum(n for _, k, n in rows if k == skipped)
    chart = common.chart(
        "stacked_bar",
        "Year FDA first received the case",
        "year",
        xs,
        "Cases",
        "count",
        series,
        question="When did companies send one case under two FDA case numbers?",
    )
    return common.card(
        "one_case_two_numbers",
        "Companies sent some cases twice under two FDA case numbers, mostly before 2012",
        f"{common.plural(n_matched, 'case')} share their company case number and sender with "
        f"another FDA case, {common.pct(before_2012, n_matched)} of them received before 2012, "
        "often a follow-up filed as a new case with reactions added or a field left blank, which "
        "an exact match on every field misses. We set them aside on the number, except "
        f"{common.plural(n_skipped, 'case')} whose copies disagree on sex or on age by more than "
        f"{gap} years, where one number was used for different patients.",
        chart,
        common.changed(STEP, "dup-manufacturer-number"),
        NB04,
    )


GROUP_SIZES = [
    ("2", 2, 2),
    ("3", 3, 3),
    ("4", 4, 4),
    ("5", 5, 5),
    ("6", 6, 6),
    ("7", 7, 7),
    ("8 to 9", 8, 9),
    ("10 to 14", 10, 14),
    ("15 or more", 15, 10**9),
]


def padded_dates_join_different_patients(con: duckdb.DuckDBPyConnection) -> dict:
    """Event dates padded to 1 January, or written as a month or year only,
    make large groups of reports look like one patient. Changed our pipeline:
    in groups at or above the rule's size that one company sent, such a date
    does not count as a match (rules/dup-padded-event-dates.md). Groups are the
    AEOLUS key's, before the guard (dup_key_T)."""
    min_size = rulebook.value("dup-padded-event-dates", "min_group_size")
    sizes = " ".join(
        f"WHEN n_T BETWEEN {lo} AND {hi} THEN {quoted(label)}" for label, lo, hi in GROUP_SIZES
    )
    share = "Groups whose shared date is 1 January, or a month or year only"
    rows = common.query(
        con,
        f"""
        WITH g AS (
          SELECT d.dup_key_T, count(*) AS n_T, bool_and({_padded("c.event_dt")}) AS padded_T
          FROM case_dup_T d JOIN case_latest_T c USING (era_T, case_key_T)
          WHERE d.dup_key_T IS NOT NULL GROUP BY 1 HAVING count(*) > 1)
        SELECT CASE {sizes} END, {quoted(share)},
               100.0 * count(*) FILTER (WHERE padded_T) / count(*)
        FROM g GROUP BY 1""",
    )
    left = common.query(
        con,
        """
        SELECT count(DISTINCT d.dup_key_T), count(*) - count(DISTINCT d.dup_key_T)
        FROM case_dup_T d WHERE d.dup_padded_date_T""",
    )
    groups, kept = left[0] if left else (0, 0)
    xs = [label for label, _, _ in GROUP_SIZES if any(r[0] == label for r in rows)]
    series = common.series(rows, xs, [share])
    jan1 = common.query(
        con,
        f"""SELECT 100.0 * count(*) FILTER (WHERE {_padded("event_dt")}) / count(*)
                         FROM case_latest_T WHERE length(event_dt) = 8""",
    )
    on_jan1 = f"{jan1[0][0]:.0f}%" if jan1 and jan1[0][0] is not None else "a large share"
    first_big = next((label for label, lo, hi in GROUP_SIZES if lo <= min_size <= hi), None)
    chart = common.chart(
        "stacked_bar",
        "Cases in the group",
        "category",
        xs,
        "Share of groups",
        "percent",
        series,
        question="How often is a matching group's shared event date padded or partial?",
        note=(first_big, f"From {min_size} cases on, such a date no longer counts")
        if first_big
        else None,
    )
    return common.card(
        "padded_dates_join_different_patients",
        "Padded event dates make large groups of different patients look like one",
        f"When only the year is known, FAERS often shows 1 January: {on_jan1} of full event dates "
        "fall on it, against under 1% if dates were spread evenly, and the larger a group of "
        "exactly matching cases, the more often its shared date is 1 January or a month or year "
        "alone, mostly where one company filed dozens of separate cases with the same profile. "
        f"In groups of {min_size} or more that one company sent, such a date no longer counts as a "
        f"match, so {common.plural(kept, 'case')} in {common.plural(groups, 'group')} are no "
        "longer set aside; copies of one event from several companies stay set aside.",
        chart,
        common.changed(STEP, "dup-padded-event-dates"),
        NB04,
    )


def duplicate_check_needs_fields(con: duckdb.DuckDBPyConnection) -> dict:
    """Most cases leave blank a field that exact duplicate matching needs.
    Documented: we do not fill blanks."""
    cannot, no_date, no_age = (
        "Cannot be checked (a needed field is blank)",
        "Event date blank",
        "Age blank",
    )
    rows = common.query(
        con,
        f"""
        SELECT c.init_year_T, {quoted(cannot)},
               100.0 * count(*) FILTER (WHERE d.dup_key_T IS NULL) / count(*)
        FROM case_latest_T c JOIN case_dup_T d USING (era_T, case_key_T) GROUP BY ALL
        UNION ALL
        SELECT init_year_T, {quoted(no_date)},
               100.0 * count(*) FILTER (WHERE event_dt IS NULL) / count(*)
        FROM case_latest_T GROUP BY ALL
        UNION ALL
        SELECT init_year_T, {quoted(no_age)},
               100.0 * count(*) FILTER (WHERE age IS NULL OR age_cod IS NULL) / count(*)
        FROM case_latest_T GROUP BY ALL""",
    )
    xs = [
        y for y in _years(rows) if y > common.FIRST_YEAR
    ]  # 2004Q1's AERS layout has no reporter country
    series = common.series(rows, xs, [cannot, no_date, no_age])
    totals = common.query(
        con, "SELECT count(*), count(*) FILTER (WHERE dup_key_T IS NULL) FROM case_dup_T"
    )
    cases, blank = totals[0] if totals else (0, 0)
    share = dict(zip(xs, series[0]["values"], strict=True))
    then, now = share.get(2011), share.get(xs[-1]) if xs else None
    trend = (
        f", up from {then:.0f}% of cases received in 2011 to {now:.0f}% in {xs[-1]}, "
        "led by the event date"
        if then is not None and now is not None
        else ""
    )
    chart = common.chart(
        "line",
        "Year FDA first received the case",
        "year",
        xs,
        "Share of cases",
        "percent",
        series,
        question="How many cases leave blank a field duplicate matching needs?",
    )
    return common.card(
        "duplicate_check_needs_fields",
        "Most cases leave blank a field that duplicate matching needs",
        f"{common.plural(blank, 'case')} ({common.pct(blank, cases)}) leave the event date, age, "
        f"sex or country blank, so no exact rule can tell whether they repeat another case{trend}. "
        "We do not fill blanks, so the duplicate flag finds only the copies it can check.",
        chart,
        common.DOCUMENTED,
        NB04,
    )


def no_adverse_event_serious_outcome(con: duckdb.DuckDBPyConnection) -> dict:
    """Reports with no usable drug or reaction, almost all saying no adverse
    event, some recording a death or a hospitalisation. Documented: kept and
    never hidden; those with a serious outcome are flagged
    (rules/no-drug-or-reaction.md)."""
    with_outcome, without = "A serious outcome recorded", "No serious outcome recorded"
    only_no_event = sql_in("upper(pt)", rulebook.value("no-drug-or-reaction", "no_event_terms"))
    rows = common.query(
        con,
        f"""
        SELECT c.init_year_T,
               CASE WHEN d.serious_no_drug_or_reaction_T THEN {quoted(with_outcome)}
                    ELSE {quoted(without)} END,
               count(*)
        FROM case_latest_T c JOIN case_dup_T d USING (era_T, case_key_T)
        WHERE d.no_drug_or_reaction_T GROUP BY ALL""",
    )
    detail = common.query(
        con,
        f"""
        WITH c AS (SELECT c.era_T, c.primaryid, c.quarter_T FROM case_latest_T c
                   JOIN case_dup_T d USING (era_T, case_key_T) WHERE d.no_drug_or_reaction_T),
        none_ AS (SELECT era_T, primaryid, quarter_T
                  FROM reac_latest_T JOIN c USING (era_T, primaryid, quarter_T)
                  GROUP BY ALL HAVING bool_and({only_no_event})),
        o AS (SELECT era_T, primaryid, quarter_T, bool_or(outc_cod = 'DE') AS death_T,
                     bool_or(outc_cod = 'HO') AS hosp_T
              FROM outc_latest_T JOIN c USING (era_T, primaryid, quarter_T) GROUP BY ALL)
        SELECT (SELECT count(*) FROM none_), count(*) FILTER (WHERE death_T),
               count(*) FILTER (WHERE hosp_T) FROM o""",
    )
    no_event, deaths, hosp = detail[0] if detail else (0, 0, 0)
    xs = _years(rows)
    series = common.zeros(common.series(rows, xs, [with_outcome, without]))
    total = sum(n for _, _, n in rows)
    serious = sum(n for _, k, n in rows if k == with_outcome)
    chart = common.chart(
        "stacked_bar",
        "Year FDA first received the case",
        "year",
        xs,
        "Cases with no usable drug or reaction",
        "count",
        series,
        question="Do reports of 'no adverse event' record serious outcomes?",
    )
    return common.card(
        "no_adverse_event_serious_outcome",
        "Some reports of 'no adverse event' record a death or a hospitalisation",
        f"{common.plural(total, 'case')} name no usable drug or reaction, "
        f"{common.pct(no_event, total)} of them saying only 'no adverse event', yet {serious:,} "
        f"record a serious outcome, including {common.plural(deaths, 'death')} and "
        f"{common.plural(hosp, 'hospitalisation')}. "
        "We keep all of them in the analysis set and flag the ones with a serious outcome.",
        chart,
        common.DOCUMENTED,
        NB04,
    )
