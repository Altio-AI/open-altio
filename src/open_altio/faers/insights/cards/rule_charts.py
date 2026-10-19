"""The charts of the rules no notebook measured: for each rule, the simplest true chart of what it
did in this release, computed on the release's own tables, and the distribution of each statistic
over the release's pairs. Every number a card shows is in its `numbers`, as the query gave it;
the words the page puts around them are in `insights/lines.yaml`, filled where the page is served.

A card here reads the release's tables (`case_latest_T`, `statistics_T`, `label_flags_T`, ...) and
one table the methods command adds from the manifest: `input_lines_T`, the lines of FDA's files
the load split back apart (rules/overlong-lines.md). A table the release lacks gives no data."""

from __future__ import annotations

import duckdb

from open_altio import rulebook

from . import common
from .drug_classes import NB09

HERE = "src/open_altio/faers/insights/cards/rule_charts.py"

# The tables of FDA's files that keep every column as published, with what we add beside it
FDA_TABLES = {
    "demo_T": "DEMO",
    "drug_latest_T": "DRUG",
    "reac_latest_T": "REAC",
    "outc_latest_T": "OUTC",
    "rpsr_latest_T": "RPSR",
    "ther_latest_T": "THER",
    "indi_latest_T": "INDI",
}
AGE_BANDS = ["0-27d", "28d-1", "under-1", "2-11", "12-17", "18-64", "65-74", "75-84", "85+"]
NOT_GIVEN = "Not given"
# Every count of cases or of their records is over the cases the release shows (case_latest_T
# where dup_kept_T); a record table is cut to them by its case key, as views.sql cuts FDA's.
KEY = "era_T, primaryid, quarter_T"
SHOWN = f"SEMI JOIN (SELECT {KEY} FROM case_latest_T WHERE dup_kept_T) k USING ({KEY})"


def _card(id_: str, title: str, sentences: str, chart: dict, tag: dict, numbers: dict) -> dict:
    out = common.card(id_, title, sentences, chart, tag, HERE)
    out["numbers"] = numbers
    return out


def _bars(
    rows: list[tuple],
    xs: list,
    names: list[str],
    x_label: str,
    y_label: str,
    question: str,
    unit: str = "count",
) -> dict:
    """A bar chart of rows (category, series, value), the categories in the order `xs` gives."""
    lines = common.zeros(common.series(rows, xs, names))
    return common.chart("stacked_bar", x_label, "category", xs, y_label, unit, lines, question)


def _rows(con: duckdb.DuckDBPyConnection, table: str, sql: str) -> list[tuple]:
    """The query's rows, or none, without a warning, where the release was built without the
    layer that holds `table` (drug classes, RxNorm codes, statistics or labels)."""
    [(n,)] = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchall()
    return common.query(con, sql) if n else []


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> tuple:
    rows = common.query(con, sql)
    return rows[0] if rows else ()


def _years(rows: list[tuple]) -> list[int]:
    """Every year from the first to the last of rows (year, ...). A count with no year is in the
    card's numbers but has no bar."""
    years = [y for y, *_ in rows if y is not None]
    return list(range(min(years), max(years) + 1)) if years else []


# ---- report_versions ----


def fda_columns_kept(con: duckdb.DuckDBPyConnection) -> dict:
    names = ", ".join(f"'{t}'" for t in FDA_TABLES)
    rows = common.query(
        con,
        f"""SELECT table_name, ends_with(column_name, '_T'), count(*)
            FROM information_schema.columns WHERE table_name IN ({names}) GROUP BY ALL""",
    )
    fda, ours = "FDA's columns, as published", "Columns we add beside them"
    cells = [(FDA_TABLES[t], ours if added else fda, n) for t, added, n in rows]
    kept = sum(n for _, s, n in cells if s == fda)
    added = sum(n for _, s, n in cells if s == ours)
    return _card(
        "fda_columns_kept",
        f"All {kept} of FDA's columns are kept as published, with {added} of ours beside them",
        f"Across FDA's seven files, {kept} columns hold FDA's values exactly as published. "
        f"Beside them, {added} columns, each ending in _T, hold what we work out from them.",
        _bars(
            cells,
            list(FDA_TABLES.values()),
            [fda, ours],
            "FDA's file",
            "Columns",
            "In each of FDA's files, how many columns are FDA's and how many are ours?",
        ),
        common.changed("report_versions", "transformed-suffix-T"),
        {"fda_columns": kept, "added_columns": added},
    )


def run_on_lines_split(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _rows(
        con,
        "input_lines_T",
        """SELECT upper(table_T) || ' ' || upper(quarter_T), records_T FROM input_lines_T
           WHERE records_T > 1 ORDER BY quarter_T, table_T""",
    )
    xs = [x for x, _ in rows]
    saved = sum(n - 1 for _, n in rows)
    name = "Records on the line"
    return _card(
        "run_on_lines_split",
        f"{common.plural(saved, 'record')} run together with another in FDA's files "
        f"{'is' if saved == 1 else 'are'} put back as {'its' if saved == 1 else 'their'} own",
        f"In {common.plural(len(rows), 'line')} of FDA's files a missing line break joined whole "
        f"records. Split back, {common.plural(saved, 'record')} that a reader would drop "
        f"{'is' if saved == 1 else 'are'} kept.",
        _bars(
            [(x, name, n) for x, n in rows],
            xs,
            [name],
            "FDA's file",
            "Records",
            "Which of FDA's files had records run together on one line, and how many?",
        ),
        common.changed("report_versions", "overlong-lines"),
        {"lines": len(rows), "records_saved": saved},
    )


def weights_read_in_kg(con: duckdb.DuckDBPyConnection) -> dict:
    rows = common.query(
        con,
        """SELECT CASE WHEN wt_cod IN ('KG', 'LBS', 'GMS') THEN wt_cod
                       WHEN wt_cod IS NULL THEN 'No unit' ELSE 'Other unit' END AS unit_T,
                  wt_kg_T IS NOT NULL, count(*)
           FROM case_latest_T WHERE dup_kept_T AND wt IS NOT NULL GROUP BY ALL""",
    )
    read, none = "Read in kilograms", "No weight"
    cells = [(u, read if ok else none, n) for u, ok, n in rows]
    given = sum(n for *_, n in cells)
    kept = sum(n for _, s, n in cells if s == read)
    return _card(
        "weights_read_in_kg",
        f"All but {given - kept:,} of the {given:,} weights FDA gives read in kilograms",
        f"Of {given:,} cases that give a weight, {kept:,} read in kilograms. "
        f"The other {given - kept:,} have no unit, an unknown one or a value no patient has, "
        "and give none.",
        _bars(
            cells,
            ["KG", "LBS", "GMS", "No unit", "Other unit"],
            [read, none],
            "Unit FDA gives",
            "Cases",
            "By the unit FDA gives, how many weights read in kilograms?",
        ),
        common.changed("report_versions", "weight-in-kg"),
        {"weights_given": given, "read_in_kg": kept, "no_weight": given - kept},
    )


def cases_by_age_band(con: duckdb.DuckDBPyConnection) -> dict:
    rows = common.query(
        con,
        f"""SELECT coalesce(age_band_T, '{NOT_GIVEN}'), count(*)
            FROM case_latest_T WHERE dup_kept_T GROUP BY ALL""",
    )
    name = "Cases"
    total = sum(n for _, n in rows)
    banded = sum(n for b, n in rows if b != NOT_GIVEN)
    return _card(
        "cases_by_age_band",
        f"{common.pct(banded, total)} of cases fall in an age band; the rest give no age",
        f"{banded:,} of {total:,} cases fall in one age band, the same for the age filter and "
        "the statistics. A case that gives no age is in none.",
        _bars(
            [(b, name, n) for b, n in rows],
            [*AGE_BANDS, NOT_GIVEN],
            [name],
            "Age band",
            "Cases",
            "How many cases fall in each age band?",
        ),
        common.changed("report_versions", "age-bands"),
        {"cases": total, "in_a_band": banded},
    )


# ---- kept_after_duplicates ----


def country_not_specified(con: duckdb.DuckDBPyConnection) -> dict:
    rows = common.query(
        con,
        """SELECT init_year_T, country_T IS NOT NULL, count(*) FROM case_latest_T
            WHERE dup_kept_T AND (upper(trim(occr_country)) IN ('COUNTRY NOT SPECIFIED', 'A1')
                   OR upper(trim(reporter_country)) IN ('COUNTRY NOT SPECIFIED', 'A1'))
            GROUP BY ALL""",
    )
    other, none = "Country from the other field", "No country"
    cells = [(y, other if has else none, n) for y, has, n in rows]
    xs = _years(cells)
    total = sum(n for *_, n in cells)
    without = sum(n for _, s, n in cells if s == none)
    lines = common.zeros(common.series(cells, xs, [other, none]))
    return _card(
        "country_not_specified",
        f"{total:,} cases say COUNTRY NOT SPECIFIED or A1, read as no country",
        f"FDA's words COUNTRY NOT SPECIFIED and the code A1 name no country. Of these cases "
        f"{total - without:,} still get one from the other country field and {without:,} none.",
        common.chart(
            "stacked_bar",
            "Year FDA first received the case",
            "year",
            xs,
            "Cases",
            "count",
            lines,
            "Each year, how many cases gave COUNTRY NOT SPECIFIED or A1 for a country?",
        ),
        common.changed("kept_after_duplicates", "country-not-given"),
        {"cases": total, "no_country": without, "country_from_other_field": total - without},
    )


# ---- cases_you_see: a mark, not a funnel step ----


def route_found(con: duckdb.DuckDBPyConnection) -> dict:
    rows = common.query(
        con,
        f"""SELECT CASE WHEN route_source_T = 'none' THEN 'Nothing says'
                       WHEN route_source_T = 'disagree' THEN 'Sources disagree'
                       WHEN route_source_T LIKE 'route%' THEN 'FDA''s route'
                       WHEN route_source_T LIKE 'dose_form%' THEN 'Dose form'
                       ELSE 'Drug name' END, count(*)
           FROM drug_route_T {SHOWN} GROUP BY ALL""",
    )
    name = "Drug records"
    total = sum(n for _, n in rows)
    found = sum(n for k, n in rows if k not in ("Nothing says", "Sources disagree"))
    return _card(
        "route_found",
        f"{common.pct(found, total)} of drug records say how the drug was given",
        f"{found:,} of {total:,} drug records get the ways the drug could have been given, from "
        "FDA's route, the dose form or words in the drug name. The rest say nothing, or disagree.",
        _bars(
            [(k, name, n) for k, n in rows],
            ["FDA's route", "Dose form", "Drug name", "Sources disagree", "Nothing says"],
            [name],
            "Where the way it was given comes from",
            "Drug records",
            "Where does each drug record's way of being given come from?",
        ),
        common.DOCUMENTED,
        {"drug_records": total, "with_a_route": found},
    )


# ---- dates ----


def dates_without_a_clean_date(con: duckdb.DuckDBPyConnection) -> dict:
    rows = common.query(
        con,
        """SELECT fda_year_T, 'Event dates', count(*) FROM case_latest_T
            WHERE dup_kept_T AND nullif(trim(event_dt), '') IS NOT NULL AND event_dt_prec_T IS NULL
            GROUP BY ALL
            UNION ALL
            SELECT c.fda_year_T, 'Therapy dates', count(*)
            FROM ther_latest_T t JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
            WHERE c.dup_kept_T
              AND ((nullif(trim(t.start_dt), '') IS NOT NULL AND t.start_dt_prec_T IS NULL)
                OR (nullif(trim(t.end_dt), '') IS NOT NULL AND t.end_dt_prec_T IS NULL))
            GROUP BY ALL""",
    )
    names = ["Event dates", "Therapy dates"]
    xs = _years(rows)
    events = sum(n for _, k, n in rows if k == names[0])
    therapy = sum(n for _, k, n in rows if k == names[1])
    return _card(
        "dates_without_a_clean_date",
        f"{events + therapy:,} dates FDA writes cannot be read as true, so no time is counted "
        "from them",
        f"{events:,} event dates and {therapy:,} therapy lines' dates are later than the file "
        "holding them, too early to be true, or not a date at all. Each gets no clean date.",
        common.chart(
            "stacked_bar",
            "Year of FDA's file",
            "year",
            xs,
            "Dates",
            "count",
            common.zeros(common.series(rows, xs, names)),
            "Each year, how many dates FDA wrote get no clean date?",
        ),
        common.changed("dates", "date-limits"),
        {"event_dates": events, "therapy_dates": therapy},
    )


def therapy_durations(con: duckdb.DuckDBPyConnection) -> dict:
    rows = common.query(
        con,
        f"""SELECT CASE WHEN dur_days_T IS NULL THEN 'None'
                       WHEN start_dt_prec_T = 8 AND end_dt_prec_T = 8 THEN 'From two exact dates'
                       ELSE 'From the duration FDA wrote' END, count(*)
           FROM ther_latest_T {SHOWN} GROUP BY ALL""",
    )
    name = "Therapy lines"
    xs = ["From two exact dates", "From the duration FDA wrote", "None"]
    total = sum(n for _, n in rows)
    cell = dict(rows)
    dates, written = cell.get(xs[0], 0), cell.get(xs[1], 0)
    return _card(
        "therapy_durations",
        f"{common.pct(dates + written, total)} of therapy lines get a duration, most from two "
        "exact dates"
        if dates >= written
        else f"{common.pct(dates + written, total)} of therapy lines get a duration",
        f"Of {total:,} therapy lines, {dates:,} get a duration from start and end dates known to "
        f"the day and {written:,} from the duration FDA wrote. The rest get none.",
        _bars(
            [(k, name, n) for k, n in rows],
            xs,
            [name],
            "Where the duration comes from",
            "Therapy lines",
            "Where does each therapy line's duration come from?",
        ),
        common.changed("dates", "therapy-duration"),
        {"therapy_lines": total, "from_dates": dates, "from_fda_duration": written},
    )


# ---- drug_classes and drug_codes: layers, not funnel steps ----


def drug_records_classed(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _rows(
        con,
        "atc_drug_T",
        f"""SELECT CASE WHEN atc_matched_on_T IN ('substance', 'active_ingredient')
                       THEN 'Its ingredient'
                       WHEN atc_matched_on_T = 'drug_name' THEN 'Its name'
                       ELSE 'Its ingredients together or each' END,
                  count(*), any_value(atc_index_year_T)
           FROM atc_drug_T {SHOWN} WHERE atc_code_T IS NOT NULL GROUP BY 1""",
    )
    (drugs,) = _one(con, f"SELECT count(*) FROM drug_latest_T {SHOWN}") or (0,)
    name = "Drug records"
    classed = sum(n for _, n, _ in rows)
    year = next((y for *_, y in rows if y is not None), None)
    cells = [(k, name, n) for k, n, _ in rows] + [("No class", name, drugs - classed)]
    return _card(
        "drug_records_classed",
        f"{common.pct(classed, drugs)} of drug records get a WHO class, all from one year's index",
        f"{classed:,} of {drugs:,} drug records get a class in WHO's drug classification, all "
        f"from its {year} edition. Each is matched on its ingredients or, failing them, its name.",
        _bars(
            cells,
            ["Its ingredient", "Its ingredients together or each", "Its name", "No class"],
            [name],
            "What the class was matched on",
            "Drug records",
            "What does each drug record's WHO class come from?",
        ),
        common.DOCUMENTED,
        {"drug_records": drugs, "classed": classed, "index_year": year},
    ) | {"notebook": NB09}


CHOSEN = {
    "only_code": "WHO gives one class",
    "shared_class": "The class all its uses share",
    "route": "By how it was given",
    "dose": "By its dose",
    "indication": "By its stated use",
    "group_class": "The group's class",
    "cannot_tell": "Use not said",
}


def classes_chosen(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _rows(
        con,
        "atc_drug_T",
        f"SELECT atc_chosen_by_T, count(*) FROM atc_drug_T {SHOWN} GROUP BY ALL",
    )
    name = "Drug records"
    cell = dict(rows)
    group = cell.get("group_class", 0)
    by_use = sum(cell.get(k, 0) for k in ("route", "dose", "indication"))
    return _card(
        "classes_chosen",
        f"{by_use:,} drug records get the class of their use, and {group:,} a group's class",
        f"Where WHO codes a drug for several uses, the report's route, dose or stated use chose "
        f"the class for {by_use:,} drug records. Another {group:,}, named only as a group such as "
        "insulin, got the group's class.",
        _bars(
            [(CHOSEN.get(k, k), name, n) for k, n in rows],
            list(CHOSEN.values()),
            [name],
            "How the class was chosen",
            "Drug records",
            "How was each drug record's WHO class chosen?",
        ),
        common.DOCUMENTED,
        {"by_use": by_use, "group_class": group, "use_not_said": cell.get("cannot_tell", 0)},
    ) | {"notebook": NB09}


def rxnorm_codes(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _rows(
        con,
        "drug_rxnorm_T",
        f"""SELECT CASE matched_by_T WHEN 'drug_name' THEN 'Its name'
                    WHEN 'prod_ai' THEN 'Its active ingredient'
                    WHEN 'substance' THEN 'Its ingredient'
                    ELSE 'No code' END, count(*)
           FROM drug_rxnorm_T {SHOWN} GROUP BY ALL""",
    )
    name = "Drug records"
    total = sum(n for _, n in rows)
    coded = sum(n for k, n in rows if k != "No code")
    return _card(
        "rxnorm_codes",
        f"{common.pct(coded, total)} of drug records get an RxNorm code, none of them guessed",
        f"{coded:,} of {total:,} drug records match an RxNorm drug by name, active ingredient or "
        "ingredient. The rest match none exactly and get no code.",
        _bars(
            [(k, name, n) for k, n in rows],
            ["Its name", "Its active ingredient", "Its ingredient", "No code"],
            [name],
            "What the code was matched on",
            "Drug records",
            "What does each drug record's RxNorm code come from?",
        ),
        common.DOCUMENTED,
        {"drug_records": total, "coded": coded},
    )


# ---- statistics ----

Bin = tuple[str, int | None, int | None]  # label, lowest value in it, lowest value above it
CASE_BINS: list[Bin] = [
    ("1", 1, 2),
    ("2", 2, 3),
    ("3 to 4", 3, 5),
    ("5 to 9", 5, 10),
    ("10 to 99", 10, 100),
]
RATIO_BINS: list[Bin] = [("Under 1", None, 1), ("1 to 2", 1, 2), ("2 to 3", 2, 3), ("3 to 5", 3, 5)]
RATIO_BINS += [("5 to 10", 5, 10), ("10 or more", 10, None)]
IC_BINS: list[Bin] = [("Under 0", None, 0), ("0 to 1", 0, 1), ("1 to 2", 1, 2), ("2 to 3", 2, 3)]
IC_BINS += [("3 or more", 3, None)]
NO_VALUE = "No value"


def _binned(con: duckdb.DuckDBPyConnection, column: str, bins: list, table: str) -> list[tuple]:
    whens = " ".join(
        "WHEN "
        + " AND ".join(
            ([f"{column} >= {lo}"] if lo is not None else [])
            + ([f"{column} < {hi}"] if hi is not None else [])
        )
        + f" THEN '{label}'"
        for label, lo, hi in bins
    )
    return _rows(
        con,
        table,
        f"""SELECT CASE WHEN {column} IS NULL OR NOT isfinite({column}) THEN '{NO_VALUE}'
                        {whens} END, count(*)
            FROM {table} GROUP BY ALL""",
    )


def pairs_by_cases(con: duckdb.DuckDBPyConnection) -> dict:
    bins = [*CASE_BINS, ("100 or more", 100, None)]
    rows = _binned(con, "cases_T", bins, "statistics_T")
    name = "Pairs"
    total = sum(n for _, n in rows)
    few = sum(n for k, n in rows if k in ("1", "2"))
    return _card(
        "pairs_by_cases",
        f"{common.pct(few, total)} of the {total:,} ingredient and reaction pairs rest on one or "
        "two cases",
        f"The statistics count {total:,} pairs of a suspected drug's ingredient and a reaction "
        f"named together. Of them, {few:,} are named together in only one or two cases.",
        _bars(
            [(k, name, n) for k, n in rows],
            [b[0] for b in bins],
            [name],
            "Cases naming the pair",
            "Pairs",
            "How many cases name each ingredient and reaction pair?",
        ),
        common.DOCUMENTED,
        {"pairs": total, "one_or_two_cases": few},
    )


def _spread(
    con: duckdb.DuckDBPyConnection, id_: str, rule: str, column: str, label: str, above: float
) -> dict:
    a = "a" if label == "PRR" else "an"
    bins = IC_BINS if rule == "ic" else RATIO_BINS
    rows = _binned(con, column, bins, "statistics_T")
    name = "Pairs"
    total = sum(n for _, n in rows)
    high = sum(n for k, n in rows if (_low(bins, k) or float("-inf")) >= above)
    return _card(
        id_,
        f"{common.pct(high, total)} of pairs have {a} {label} of {above:g} or more",
        f"Of {total:,} ingredient and reaction pairs, {high:,} have {a} {label} of {above:g} or "
        f"more. A pair it cannot be worked out for has no value.",
        _bars(
            [(k, name, n) for k, n in rows],
            [b[0] for b in bins] + [NO_VALUE],
            [name],
            label,
            "Pairs",
            f"How is the {label} spread over the release's pairs?",
        ),
        common.DOCUMENTED,
        {"pairs": total, "at_or_above": high, "threshold": above},
    )


def _low(bins: list, label: str) -> float | None:
    return next((lo for k, lo, _ in bins if k == label), None)


def ebgm_spread(con: duckdb.DuckDBPyConnection) -> dict:
    return _spread(con, "ebgm_spread", "ebgm", "ebgm_T", "EBGM", 2)


def prr_spread(con: duckdb.DuckDBPyConnection) -> dict:
    return _spread(con, "prr_spread", "prr", "prr_T", "PRR", 2)


def ror_spread(con: duckdb.DuckDBPyConnection) -> dict:
    return _spread(con, "ror_spread", "ror", "ror_T", "ROR", 2)


def rrr_spread(con: duckdb.DuckDBPyConnection) -> dict:
    return _spread(con, "rrr_spread", "rrr", "rrr_T", "RRR", 2)


def ic_spread(con: duckdb.DuckDBPyConnection) -> dict:
    return _spread(con, "ic_spread", "ic", "ic_T", "IC", 1)


def ror_by_stratum(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _rows(
        con,
        "statistics_strata_T",
        """SELECT CASE by_T WHEN 'sex' THEN 'Sex ' ELSE 'Age ' END || stratum_T,
                  coalesce(ror_lower_T > 1, false), count(*)
           FROM statistics_strata_T GROUP BY ALL""",
    )
    above, other = "Lower bound above 1", "Not above 1"
    cells = [(k, above if up else other, n) for k, up, n in rows]
    xs = [f"Age {b}" for b in [*AGE_BANDS, "unknown"]] + ["Sex F", "Sex M", "Sex unknown"]
    total = sum(n for *_, n in cells)
    high = sum(n for _, s, n in cells if s == above)
    return _card(
        "ror_by_stratum",
        f"{common.pct(high, total)} of the odds ratios worked out within an age band or a sex "
        "stand clear of 1",
        f"Each pair's ROR is worked out again within each age band and each sex, {total:,} in "
        f"all. Of them, {high:,} have a lower bound above 1.",
        _bars(
            cells,
            xs,
            [above, other],
            "Age band or sex",
            "Pair and stratum",
            "Within each age band and each sex, how many pairs' odds ratios stand clear of 1?",
        ),
        common.DOCUMENTED,
        {"pair_strata": total, "lower_above_1": high},
    )


# ---- drug_labels and label_flags: added to a release with a labels folder ----


def labels_by_application(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _rows(
        con,
        "label_candidates_T",
        """SELECT CASE WHEN application_T LIKE 'NDA%' THEN 'New drug (NDA)'
                       WHEN application_T LIKE 'BLA%' THEN 'Biologic (BLA)'
                       WHEN application_T LIKE 'ANDA%' THEN 'Generic (ANDA)'
                       ELSE 'Other' END, count(DISTINCT setid_T)
           FROM label_candidates_T GROUP BY ALL""",
    )
    name = "Labels"
    total = sum(n for _, n in rows)
    return _card(
        "labels_by_application",
        f"{total:,} current FDA prescription labels are read for this release",
        f"The release reads {total:,} of DailyMed's human prescription labels, each in its current "
        "version. The chart counts them by the kind of application FDA approved them under.",
        _bars(
            [(k, name, n) for k, n in rows],
            ["New drug (NDA)", "Biologic (BLA)", "Generic (ANDA)", "Other"],
            [name],
            "FDA application",
            "Labels",
            "Under which kind of FDA application was each label read approved?",
        ),
        common.DOCUMENTED,
        {"labels": total},
    )


CHOICE = ["the only label", "newest of the labels under this application"]
CHOICE += ["the only label from 2020 on", "the only label whose safety sections hold text"]


def label_choice_reasons(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _rows(
        con,
        "label_candidates_T",
        """SELECT regexp_extract(chosen_because_T, ': ([^;]*)', 1), count(*)
           FROM label_candidates_T GROUP BY ALL""",
    )
    name = "Ingredient and route"
    total = sum(n for _, n in rows)
    only = dict(rows).get(CHOICE[0], 0)
    words = {k: k[0].upper() + k[1:] for k in CHOICE}
    return _card(
        "label_choice_reasons",
        f"{common.pct(only, total)} of ingredients and routes have only one label to read",
        f"Each of {total:,} ingredients and ways of taking it is read against one label. For "
        f"{only:,} it is the only one; for the rest, the newest from its original maker.",
        _bars(
            [(words.get(k, "Other"), name, n) for k, n in rows],
            [*words.values(), "Other"],
            [name],
            "Why the label was chosen",
            "Ingredients and routes",
            "Why was each ingredient and route read against the label it was?",
        ),
        common.DOCUMENTED,
        {"chosen": total, "only_label": only},
    )


def label_sections_read(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _rows(
        con,
        "label_sections_T",
        """SELECT replace(section_T, '_', ' '), is_table_row_T, count(*)
           FROM label_sections_T GROUP BY ALL""",
    )
    rows_ = _rows(con, "label_sections_T", "SELECT count(DISTINCT setid_T) FROM label_sections_T")
    (labels,) = rows_[0] if rows_ else (0,)
    prose, table = "Text", "Table rows"
    cells = [(k[0].upper() + k[1:], table if t else prose, n) for k, t, n in rows]
    rows_in_tables = sum(n for _, s, n in cells if s == table)
    xs = ["Boxed warning", "Warnings and precautions", "Warnings", "Precautions"]
    xs += ["Adverse reactions", "Contraindications", "Indications"]
    return _card(
        "label_sections_read",
        f"{labels:,} labels' safety sections are read, {rows_in_tables:,} lines of them as table "
        "rows",
        f"The release reads the safety sections and what the drug is for from {labels:,} labels. "
        f"Of their lines, {rows_in_tables:,} are rows of a table, read row by row.",
        _bars(
            cells,
            xs,
            [prose, table],
            "Label section",
            "Lines",
            "How much of each safety section is text, and how much table rows?",
        ),
        common.DOCUMENTED,
        {"labels": labels, "table_rows": rows_in_tables},
    )


def labels_keyed_by_ingredients(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _rows(
        con,
        "label_candidates_T",
        """SELECT CASE keyed_by_T WHEN 'label_ingredients' THEN 'Its own ingredients'
                                  ELSE 'Its drug code' END, count(*)
           FROM label_candidates_T GROUP BY ALL""",
    )
    name = "Labels chosen"
    own = dict(rows).get("Its own ingredients", 0)
    return _card(
        "labels_keyed_by_ingredients",
        f"{own:,} labels with no drug code are matched by their own ingredients",
        f"A current label that DailyMed links to no drug code is matched by the ingredients it "
        f"names. Of the chosen labels, {own:,} are read this way.",
        _bars(
            [(k, name, n) for k, n in rows],
            ["Its drug code", "Its own ingredients"],
            [name],
            "What the label is matched by",
            "Labels chosen",
            "What is each chosen label matched to its drug by?",
        ),
        common.DOCUMENTED,
        {"own_ingredients": own},
    )


def _flag_words() -> dict[str, str]:
    """Each flag in the screens' words (rule explorer-label-words), a flag never compared with
    the label as Not compared with its reason, the umbrella's Listed apart."""
    words = rulebook.value("explorer-label-words", "words")
    reasons = rulebook.value("explorer-label-words", "reasons")
    order = ["on_label", "umbrella", "related", "not_on_label", "forms_differ", "uncertain"]
    order += ["treated_disease", "not_a_medical_event", "procedure", "no_label"]
    out = {"umbrella": f"{words['on_label']}, under a wider term"}
    out |= {k: f"{w} ({reasons[k]})" if k in reasons else w for k, w in words.items()}
    return {k: out[k] for k in order if k in out}


PARTS = 16  # the shown pairs are found in parts of the cases, so the join fits the temp space
PAIRS = "shown_pairs_T"
PAIR_TABLES = (
    "label_flags_T",
    "drug_latest_T",
    "drug_substance_T",
    "drug_rxnorm_T",
    "drug_route_T",
    "reac_latest_T",
    "case_latest_T",
)
RECORD = "era_T, primaryid, quarter_T, drug_seq"


def _have(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    [(n,)] = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchall()
    return bool(n)


def _shown_pairs(con: duckdb.DuckDBPyConnection) -> bool:
    """Make, once per connection, the temp table `shown_pairs_T` of the pairs the cases people
    see use, as notebook 10 counts them: one row per distinct (rxcui_T, route_families_T, pt_T)
    of `label_flags_T` that a suspect record of a shown case, not a DiAna trial product, uses,
    with its outcome, how it was decided and the label section. A record the labels step reads
    to another drug (`label_other_drug_T`) has no code, as the flags were written. Returns
    False, with the table empty, where the release lacks a table it needs."""
    if _have(con, PAIRS):
        return True
    cols = "rxcui_T VARCHAR, route_families_T VARCHAR, pt_T VARCHAR, outcome_T VARCHAR, "
    cols += "decided_by_T VARCHAR, section_T VARCHAR"
    con.execute(f"CREATE TEMP TABLE {PAIRS} ({cols})")
    if not all(_have(con, t) for t in PAIR_TABLES):
        return False
    roles = ", ".join(repr(r) for r in rulebook.value("label-flags", "suspect_roles"))
    other, code = "", "x.rxcui_T"
    if _have(con, "label_other_drug_T"):
        other = (
            f"LEFT JOIN (SELECT DISTINCT {RECORD}, true AS other_T FROM label_other_drug_T) o "
            f"USING ({RECORD})"
        )
        code = "CASE WHEN o.other_T THEN NULL ELSE x.rxcui_T END"
    con.execute("CREATE TEMP TABLE used_T (rxcui_T VARCHAR, families_T VARCHAR, pt_T VARCHAR)")
    for part in range(PARTS):
        con.execute(
            f"""INSERT INTO used_T
SELECT DISTINCT coalesce({code}, ''), coalesce(ro.route_families_T, ''), r.pt
FROM (SELECT DISTINCT {RECORD} FROM drug_latest_T {SHOWN}
      WHERE role_cod IN ({roles}) AND hash({KEY}) % {PARTS} = {part}) d
JOIN drug_substance_T s USING ({RECORD})
LEFT JOIN drug_rxnorm_T x USING ({RECORD})
LEFT JOIN drug_route_T ro USING ({RECORD})
{other}
JOIN reac_latest_T r USING ({KEY})
WHERE NOT coalesce(s.diana_trial_T, false) AND r.pt IS NOT NULL"""
        )
    con.execute(
        f"""INSERT INTO {PAIRS}
SELECT u.rxcui_T, u.families_T, u.pt_T, f.outcome_T, f.decided_by_T, f.section_T
FROM (SELECT DISTINCT rxcui_T, families_T, pt_T FROM used_T) u
LEFT JOIN label_flags_T f ON coalesce(f.rxcui_T, '') = u.rxcui_T
  AND coalesce(f.route_families_T, '') = u.families_T AND f.pt_T = u.pt_T"""
    )
    con.execute("DROP TABLE used_T")
    return True


def _pair_rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    """The rows of a query over `shown_pairs_T` (written FROM shown_pairs_T), or none."""
    return common.query(con, sql) if _shown_pairs(con) else []


UMBRELLA = "outcome_T = 'on_label' AND decided_by_T = 'rule: umbrella'"


def label_flags_given(con: duckdb.DuckDBPyConnection) -> dict:
    rows = _pair_rows(
        con,
        f"""SELECT CASE WHEN {UMBRELLA} THEN 'umbrella' ELSE outcome_T END, count(*)
           FROM {PAIRS} GROUP BY ALL""",
    )
    name = "Drug and reaction"
    total = sum(n for _, n in rows)
    cell = dict(rows)
    on = cell.get("on_label", 0) + cell.get("umbrella", 0)
    aside = sum(cell.get(k, 0) for k in ("treated_disease", "not_a_medical_event", "procedure"))
    flags = _flag_words()
    return _card(
        "label_flags_given",
        f"{common.pct(on, total)} of drug and reaction pairs are listed on the drug's label",
        f"Each of {total:,} suspect drug and reaction pairs in the cases shown gets one flag. Of "
        f"them {on:,} are Listed, {cell.get('related', 0):,} Possibly listed, and {aside:,} Not "
        "compared, because they name the disease treated, no medical event or a procedure.",
        _bars(
            [(flags.get(k, k), name, n) for k, n in rows],
            list(flags.values()),
            [name],
            "Flag",
            "Drug and reaction pairs",
            "Which flag does each suspect drug and reaction get?",
        ),
        common.DOCUMENTED,
        {"pairs": total, "on_label": on, "umbrella": cell.get("umbrella", 0), "set_aside": aside},
    )


def _top_reactions(
    con: duckdb.DuckDBPyConnection,
    id_: str,
    where: str,
    title: str,
    sentences: str,
    series: str,
    question: str,
) -> dict:
    """The ten reaction terms, as FDA wrote them, with the most shown pairs that `where` picks."""
    rows = _pair_rows(
        con,
        f"""SELECT pt_T, count(*) FROM {PAIRS} WHERE {where}
           GROUP BY ALL ORDER BY 2 DESC, 1 LIMIT 10""",
    )
    [(total,)] = _pair_rows(con, f"SELECT count(*) FROM {PAIRS} WHERE {where}") or [(0,)]
    top = sum(n for _, n in rows)
    return _card(
        id_,
        title.format(total=total),
        sentences.format(total=total, top=top),
        _bars(
            [(pt, series, n) for pt, n in rows],
            [pt for pt, _ in rows],
            [series],
            "Reaction as FDA wrote it",
            "Drug and reaction pairs",
            question,
        ),
        common.DOCUMENTED,
        {"pairs": total, "top_pairs": top},
    )


def label_treated_disease(con: duckdb.DuckDBPyConnection) -> dict:
    return _top_reactions(
        con,
        "label_treated_disease",
        "outcome_T = 'treated_disease'",
        "{total:,} drug and reaction pairs name the disease the drug was given for",
        "A reaction that is the disease the drug was given for is not compared with the label; "
        "a worse form of it is. Ten reactions make up {top:,} of the {total:,} pairs.",
        _flag_words()["treated_disease"],
        "Which diseases the drug treats are reported most?",
    )


def label_not_a_medical_event(con: duckdb.DuckDBPyConnection) -> dict:
    return _top_reactions(
        con,
        "label_not_a_medical_event",
        "outcome_T = 'not_a_medical_event'",
        "{total:,} drug and reaction pairs name no medical event",
        "Terms such as drug ineffective, off-label use or an overdose are not compared with the "
        "label. Ten of them make up {top:,} of the {total:,} pairs.",
        _flag_words()["not_a_medical_event"],
        "Which terms that name no medical event are reported most?",
    )


def label_procedure(con: duckdb.DuckDBPyConnection) -> dict:
    return _top_reactions(
        con,
        "label_procedure",
        "outcome_T = 'procedure'",
        "{total:,} drug and reaction pairs name what was done to the patient",
        "A hospital stay, surgery or dialysis is no reaction a label could list, so it is not "
        "compared and stays in view. Ten make up {top:,} of the {total:,} pairs.",
        _flag_words()["procedure"],
        "Which procedures are reported most?",
    )


def label_umbrella(con: duckdb.DuckDBPyConnection) -> dict:
    return _top_reactions(
        con,
        "label_umbrella",
        UMBRELLA,
        "{total:,} drug and reaction pairs are listed under a wider term",
        "A label that names a group, such as an injection site reaction or an upper respiratory "
        "tract infection, lists the mild reactions in it, never a serious form. Ten reactions "
        "make up {top:,} of the {total:,} pairs listed this way.",
        _flag_words()["umbrella"],
        "Which reactions are listed under a wider term most often?",
    )


def label_dictionary(con: duckdb.DuckDBPyConnection) -> dict:
    sections = ["Boxed warning", "Warnings and precautions", "Warnings", "Precautions"]
    sections += ["Adverse reactions", "Contraindications", "Indications"]
    rows = _pair_rows(
        con,
        f"""SELECT replace(section_T, '_', ' '), count(*) FROM {PAIRS}
           WHERE outcome_T = 'on_label' GROUP BY ALL""",
    )
    name = "Listed pairs"
    cells = [(k[0].upper() + k[1:] if k else None, name, n) for k, n in rows]
    total = sum(n for _, _, n in cells)
    none = sum(n for k, _, n in cells if k is None)
    adverse = sum(n for k, _, n in cells if k == "Adverse reactions")
    other = sorted(k for k, _, _ in cells if k is not None and k not in sections)
    return _card(
        "label_dictionary",
        f"{common.pct(adverse, total)} of listed pairs are named in the label's adverse "
        "reactions section",
        f"Each listed pair is found in the section of the label that names the reaction. "
        f"{none:,} of the {total:,} have no one section: a wider term lists them, or the labels "
        "of several forms agree.",
        _bars(
            [c for c in cells if c[0] is not None],
            [*sections, *other],
            [name],
            "Label section",
            "Drug and reaction pairs",
            "In which section of the label is each reaction named?",
        ),
        common.DOCUMENTED,
        {"pairs": total, "no_section": none},
    )


def label_table_rows(con: duckdb.DuckDBPyConnection) -> dict:
    """Needs the licensed `label_terms_T`, so it is a licensed card (cards.LICENSED)."""
    rows = _rows(
        con,
        "label_terms_T",
        """SELECT CASE kept_T WHEN true THEN 'Kept as the drug''s'
                             WHEN false THEN 'Only placebo or comparison had it'
                             ELSE 'Sent to a person' END, count(*)
           FROM label_terms_T WHERE rule_T = 'label-table-rows' GROUP BY ALL""",
    )
    cell = dict(rows)
    kept, left, sent = (cell.get(k, 0) for k in TABLE_ROW_OUTCOMES)
    name = "Terms found in table rows"
    return _card(
        "label_table_rows",
        f"{left:,} terms in label tables belong to the placebo or comparison group only",
        f"The label tables name {kept + left + sent:,} terms. {kept:,} are kept as the drug's, "
        f"{left:,} only the placebo or comparison group had, and {sent:,} go to a person.",
        _bars(
            [(k, name, n) for k, n in rows],
            list(TABLE_ROW_OUTCOMES),
            [name],
            "What the rule did",
            "Terms",
            "What happens to a term found in a row of a label table?",
        ),
        common.DOCUMENTED,
        {"kept": kept, "left_out": left, "sent_to_person": sent},
    )


TABLE_ROW_OUTCOMES = ("Kept as the drug's", "Only placebo or comparison had it", "Sent to a person")


def class_pairs_by_level(con: duckdb.DuckDBPyConnection) -> dict:
    levels = {2: "Therapeutic subgroup", 3: "Pharmacological subgroup", 4: "Chemical subgroup"}
    rows = _rows(
        con,
        "atc_statistics_T",
        "SELECT level_T, count(*) FROM atc_statistics_T GROUP BY ALL",
    )
    name = "Class and reaction pairs"
    total = sum(n for _, n in rows)
    return _card(
        "class_pairs_by_level",
        f"{total:,} class and reaction pairs get statistics, at three levels of the class",
        f"The statistics are worked out again for {total:,} pairs of a WHO class and a reaction "
        "named together in a counted case. Each level of the class is counted on its own.",
        _bars(
            [(levels.get(k, str(k)), name, n) for k, n in rows],
            list(levels.values()),
            [name],
            "Level of the class",
            "Pairs",
            "How many class and reaction pairs does each level of the class have?",
        ),
        common.DOCUMENTED,
        {"pairs": total},
    )


CARDS = [
    fda_columns_kept,
    run_on_lines_split,
    weights_read_in_kg,
    cases_by_age_band,
    country_not_specified,
    dates_without_a_clean_date,
    therapy_durations,
    route_found,
    drug_records_classed,
    classes_chosen,
    rxnorm_codes,
    pairs_by_cases,
    ebgm_spread,
    prr_spread,
    ror_spread,
    rrr_spread,
    ic_spread,
    ror_by_stratum,
    labels_by_application,
    label_choice_reasons,
    label_sections_read,
    labels_keyed_by_ingredients,
    label_flags_given,
    label_treated_disease,
    label_not_a_medical_event,
    label_procedure,
    label_umbrella,
    label_dictionary,
    label_table_rows,
    class_pairs_by_level,
]
