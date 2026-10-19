"""Dates read as far as they are known and can be true, and the times worked out from them.

    event_date()          demo_T's event_dt_T and event_dt_prec_T (rules event-date-precision,
                          date-limits)
    therapy_columns()     ther_latest_T's start_dt_T, end_dt_T, their _prec_T and dur_days_T
                          (rules date-limits, therapy-duration)
    onset()               drug_onset_T: time_to_onset_T for each drug record, and why it has none
                          (rule time-to-onset)

A `_prec_T` says how much of a date is known: 8 the day, 6 the month, 4 the year. A date outside
the limits keeps FDA's text and gets no clean value: its `_T` and its `_prec_T` are empty. Each
function reads its rules when called, so a build under a person's own rules takes their values.
"""

from __future__ import annotations

from open_altio import rulebook

from .reader import quoted

ONSET_TABLE = "drug_onset_T"
# Why a drug record has no time to onset (time_to_onset_reason_T), each checked in this order:
# the event date is on the 1st and read as known only to its month or year, the event date is
# not known to the day for another reason, the first dose is not known to the day, the event
# came before the first dose.
ONSET_REASONS = (
    "padded_event_date",
    "event_date_not_exact",
    "first_dose_not_exact",
    "event_before_first_dose",
)
THERAPY_DATES = ("start_dt", "end_dt")


# A raw FAERS date is yyyymmdd text; anything else, a partial date or an
# impossible day among them, reads as no date.
def full_date(col: str) -> str:
    return (
        f"CASE WHEN regexp_full_match({col}, '[0-9]{{8}}') "
        f"THEN CAST(try_strptime({col}, '%Y%m%d') AS DATE) END"
    )


# How much of a raw date FDA gave: 8 (yyyymmdd), 6 (yyyymm), 4 (yyyy), or
# NULL.
def precision(col: str) -> str:
    return (
        f"CASE WHEN {col} IS NULL THEN NULL WHEN length({col}) IN (4, 6, 8) THEN length({col}) END"
    )


# A raw number, or nothing where the text is not one (rules/age-in-years.md): digits with at
# most one decimal point, which may lead (.8) or trail (60.), and spaces around them. A minus sign
# is not read, so a negative number is none.
def number(col: str) -> str:
    return (
        f"CASE WHEN regexp_full_match(trim({col}), '[0-9]+\\.?[0-9]*|\\.[0-9]+') "
        f"THEN CAST(trim({col}) AS DOUBLE) END"
    )


def _year(col: str) -> str:
    return f"try_cast(left({col}, 4) AS INTEGER)"


# The last day of the quarter a version was published in, as yyyymmdd text.
def _quarter_end(quarter: str) -> str:
    return (
        f"substr({quarter}, 1, 4) || "
        f"['0331', '0630', '0930', '1231'][try_cast(substr({quarter}, 6, 1) AS INTEGER)]"
    )


def _limited(col: str, known: str, quarter: str, floor: str) -> tuple[str, str]:
    """The clean date and its precision, from the raw date `col` known to `known` digits: none
    when the date is after its quarter, compared at its own precision, or under `floor`, an SQL
    condition on the date's year."""
    if rulebook.is_on("date-limits"):
        after = f"left({col}, {known}) > left({_quarter_end(quarter)}, {known})"
        outside = f"coalesce({after}, false) OR coalesce({floor}, false)"
        known = f"CASE WHEN {outside} THEN NULL ELSE {known} END"
    return f"CASE WHEN {known} = 8 THEN {full_date(col)} END", known


def _oldest_years() -> int:
    return int(rulebook.value("date-limits", "max_age_years"))


def event_date() -> tuple[str, str]:
    """demo_T's event_dt_T and event_dt_prec_T, over demo's own columns. In the versions FDA
    padded, a full date on the 1st of a month is known to the month, on 1 January to the year;
    the floor is the oldest a patient can be before the year FDA first received the case."""
    known = precision("event_dt")
    if rulebook.is_on("event-date-precision"):
        since = quoted(rulebook.value("event-date-precision", "faers_from_quarter"))
        padded = f"(era_T = 'legacy' OR quarter_T >= {since})"
        year_day = rulebook.value("event-date-precision", "year_month_day")
        month_day = rulebook.value("event-date-precision", "month_day")
        known = (
            f"CASE WHEN {padded} AND {known} = 8 AND right(event_dt, {len(year_day)}) = "
            f"{quoted(year_day)} THEN 4 WHEN {padded} AND {known} = 8 AND "
            f"right(event_dt, {len(month_day)}) = {quoted(month_day)} THEN 6 ELSE {known} END"
        )
    received = _year("coalesce(init_fda_dt, fda_dt)")
    floor = f"{_year('event_dt')} < {received} - {_oldest_years()}"
    return _limited("event_dt", known, "quarter_T", floor)


def _days(start: str, end: str) -> str:
    """dur_days_T: from the two clean dates when the end is not before the start, else FDA's
    duration in its unit; none when longer than the patient's age and a margin, or where the age
    is unknown, longer than the rule's longest."""
    if not rulebook.is_on("therapy-duration"):
        return "NULL::DOUBLE"
    units = rulebook.value("therapy-duration", "unit_days")
    per_day = rulebook.value("therapy-duration", "units_a_day")
    unit = " ".join(
        [f"WHEN {quoted(u)} THEN {float(d)!r}" for u, d in units.items()]
        + [f"WHEN {quoted(u)} THEN 1.0 / {float(n)!r}" for u, n in per_day.items()]
    )
    year = float(units["YR"])
    margin = float(rulebook.value("therapy-duration", "age_margin_years"))
    longest = float(rulebook.value("therapy-duration", "max_years_unknown_age"))
    days = (
        f"coalesce(CASE WHEN {end} >= {start} THEN CAST({end} - {start} + 1 AS DOUBLE) END, "
        f"{number('a.dur')} * CASE a.dur_cod {unit} END)"
    )
    cap = (
        f"CASE WHEN c.age_years_T >= 0 THEN (c.age_years_T + {margin}) * {year} "
        f"ELSE {longest} * {year} END"
    )
    return f"CASE WHEN {days} <= {cap} THEN {days} END"


# The case columns the therapy limits read, carried by child_latest's join to case_latest_T.
THERAPY_CASE_COLUMNS = ("age_years_T", "init_year_T", "event_dt", "event_dt_prec_T")


def therapy_columns() -> str:
    """ther_latest_T's clean dates, their precision and dur_days_T, over a therapy row `a` and
    its case `c`. A therapy date's floor follows the patient: no more than the rule's years
    before the birth year (the event year, else the year FDA first received the case, less the
    age, rounded down) where the age is known, else the oldest a patient can be."""
    event_year = f"CASE WHEN c.event_dt_prec_T IS NOT NULL THEN {_year('c.event_dt')} END"
    born = f"floor(coalesce({event_year}, c.init_year_T) - c.age_years_T)"
    before = int(rulebook.value("date-limits", "before_birth_years"))
    out, clean = [], {}
    for col in THERAPY_DATES:
        floor = (
            f"CASE WHEN c.age_years_T >= 0 THEN {_year('a.' + col)} < {born} - {before} "
            f"ELSE {_year('a.' + col)} < c.init_year_T - {_oldest_years()} END"
        )
        clean[col], known = _limited(f"a.{col}", precision(f"a.{col}"), "a.quarter_T", floor)
        out += [f"{clean[col]} AS {col}_T", f"{known} AS {col}_prec_T"]
    out.append(f"{_days(clean['start_dt'], clean['end_dt'])} AS dur_days_T")
    return ", ".join(out)


def onset() -> str:
    """drug_onset_T, one row per drug record of drug_latest_T, however many rows FDA wrote for
    it: the event date less the record's earliest therapy start known to the day, plus the first
    dose's day; none when either is unknown, when the event came before the first dose, or when
    a start known only to its month or year could be on or before that earliest full start, and
    then the first of ONSET_REASONS that holds."""
    first = int(rulebook.value("time-to-onset", "first_dose_day"))
    tto = f"c.event_dt_T - s.first_start_T + {first}"
    padded, other, no_dose, before = (quoted(r) for r in ONSET_REASONS)
    if rulebook.is_on("time-to-onset"):
        value = f"CASE WHEN NOT s.maybe_earlier_T AND {tto} >= {first} THEN {tto} END"
        # a full date FDA wrote that the padding rule reads to its month or year
        on_the_first = "c.event_dt_prec_T IN (4, 6) AND length(c.event_dt) = 8"
        reason = (
            f"CASE WHEN {value} IS NOT NULL THEN NULL "
            f"WHEN c.event_dt_T IS NULL AND {on_the_first} THEN {padded} "
            f"WHEN c.event_dt_T IS NULL THEN {other} "
            f"WHEN s.first_start_T IS NULL OR s.maybe_earlier_T THEN {no_dose} ELSE {before} END"
        )
    else:
        value = reason = "NULL"
    return f"""
CREATE TABLE {ONSET_TABLE} AS
WITH f AS (
  SELECT era_T, primaryid, quarter_T, dsg_drug_seq AS drug_seq, min(start_dt_T) AS first_start_T
  FROM ther_latest_T WHERE start_dt_T IS NOT NULL GROUP BY ALL),
s AS (
  SELECT f.era_T, f.primaryid, f.quarter_T, f.drug_seq, f.first_start_T,
    coalesce(bool_or(t.start_dt_prec_T IN (4, 6) AND left(t.start_dt, t.start_dt_prec_T)
      <= left(strftime(f.first_start_T, '%Y%m%d'), t.start_dt_prec_T)), false) AS maybe_earlier_T
  FROM f JOIN ther_latest_T t ON t.era_T = f.era_T AND t.primaryid = f.primaryid
    AND t.quarter_T = f.quarter_T AND t.dsg_drug_seq = f.drug_seq
  GROUP BY ALL)
SELECT d.era_T, d.primaryid, d.quarter_T, d.drug_seq, CAST({value} AS INTEGER) AS time_to_onset_T,
  CAST({reason} AS VARCHAR) AS time_to_onset_reason_T
FROM (SELECT DISTINCT era_T, primaryid, quarter_T, drug_seq FROM drug_latest_T) d
JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
LEFT JOIN s USING (era_T, primaryid, quarter_T, drug_seq)
"""
