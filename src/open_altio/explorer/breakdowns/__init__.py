"""The breakdowns of a drug and event pair's cases, one field at a time (rule breakdown-lines):
for each field, each value's share among only the reports that give the field, in the window
and before it (periods.py), the change in points, and how many of the reports give the field.

    breakdowns(data, query)   `product` and its settings, the event as `reaction` (repeated for
                              a group of reactions counted as one), the filters, the window as
                              `received_from` and `received_to`, and `before_from`, `before_to`
    case_filter(data, query)  the cases behind one of its counts, for the case list: the same
                              question with `period`, and a line's `field` and `value`

The cases are those /api/events counts for the event under the same settings and filters, each
counted once however many of the group's reactions it names, and placed in a period by the day
it is dated by. A share whose period has no report giving the field is null, never 0. The
counts are kept per release, so asking again reads them back; the value each line shows and its
alarm (lines.py) are worked out on each ask, from the question's `points`, `fall` and
`strength`. No value from the query is put into SQL text.
"""

from __future__ import annotations

from typing import Any

from ..answers import Problem, cases_query
from ..drugs import Unit
from ..explore import Data, Query, Scope, scope, value_of
from ..recordfields import is_onset, onset_span
from . import fields, lines, periods
from .fields import CASE_COLUMNS, Reading
from .lines import COUNTED, EVERY, PERIODS
from .periods import Periods

NO_DRUG = "A breakdown needs a drug: name it as product."
NO_EVENT = "Name the event as reaction, one or more."


def _cases(data: Data, asked: Scope, keys: list[str], when: Periods) -> tuple[str, list]:
    """SQL: cs (fields.py), every case of the question naming the event, kept or set aside, in
    the window or before it."""
    sql, params = asked.where(**when.dates, dedup="all")
    period, period_params = when.of("c")
    counted = "c.dup_kept_T" if asked.filters.kept_only else "TRUE"
    columns = ", ".join(f"c.{c}" for c in CASE_COLUMNS)
    return (
        f"SELECT * FROM (SELECT c.case_id_T, {columns}, {counted} AS counted_T, "
        f"{period} AS period_T FROM explorer_case_T c WHERE {sql} AND c.case_id_T IN "
        "(SELECT case_id_T FROM explorer_reac_term_T "
        "WHERE term_T IN (SELECT unnest(?::VARCHAR[])))) WHERE period_T IS NOT NULL",
        [*period_params, *params, data.reactions.texts(keys)],
    )


def _read(
    cases: tuple[str, list], records: tuple[str, list], read: dict[str, Reading]
) -> tuple[str, list]:
    """SQL: the WITH of cs, rec and `a`, each field's values as its reading reads them
    (f, case_id_T, v, w), and its parameters."""
    plain = {f: r for f, r in read.items() if f != fields.KEY_DETAILS}
    parts = [
        f"SELECT '{COUNTED}' AS f, case_id_T, '' AS v, NULL::VARCHAR AS w FROM cs WHERE counted_T",
        f"SELECT '{EVERY}', case_id_T, '', NULL FROM cs",
        *(
            f"SELECT '{f}', case_id_T, CAST(v AS VARCHAR), CAST(w AS VARCHAR) FROM ({r.sql})"
            for f, r in plain.items()
        ),
    ]
    params = [*cases[1], *records[1], *(p for r in plain.values() for p in r.params)]
    each = "SELECT * FROM v"
    if fields.KEY_DETAILS in read:
        details = read[fields.KEY_DETAILS]
        each += (
            f" UNION ALL SELECT '{fields.KEY_DETAILS}', case_id_T, CAST(v AS VARCHAR), NULL "
            f"FROM ({details.sql})"
        )
        params += details.params
    return (
        f"WITH cs AS MATERIALIZED ({cases[0]}), rec AS MATERIALIZED ({records[0]}), "
        f"v AS MATERIALIZED ({' UNION ALL '.join(parts)}), a AS ({each})",
        params,
    )


def _tallied(
    data: Data, cases: tuple[str, list], records: tuple[str, list], read: dict[str, Reading]
) -> list[dict[str, Any]]:
    """Each field's cases by period and value, and by period alone (`whole`), counted once; for
    a field whose texts count under a value worked out here, the cases themselves (`ids`)."""
    values, params = _read(cases, records, read)
    keyed = [f for f, r in read.items() if r.key is not None]
    return data.rows(
        f"{values} SELECT a.f, cs.period_T AS p, a.v, count(DISTINCT a.case_id_T) AS n, "
        "grouping(a.v) AS whole, any_value(a.w) AS w, "
        "list(DISTINCT a.case_id_T) FILTER (WHERE list_contains(?::VARCHAR[], a.f)) AS ids "
        "FROM a JOIN cs USING (case_id_T) "
        "GROUP BY GROUPING SETS ((a.f, cs.period_T, a.v), (a.f, cs.period_T))",
        [*params, keyed],
    )


def _asked(data: Data, query: Query) -> tuple[Scope, Unit, list[str], Periods]:
    """The question: what it is asked of, the product, the event's keys and the periods."""
    # the reactions here are the event, not the one-reaction filter
    asked = scope(data, {k: v for k, v in query.items() if k != "reaction"})
    unit = asked.product
    if unit is None:
        raise Problem(400, NO_DRUG)
    keys = sorted({k for k in map(data.reactions.key, query.get("reaction", [])) if k})
    if not keys:
        raise Problem(400, NO_EVENT)
    return asked, unit, keys, periods.asked(data, query)


def _counted(data: Data, query: Query) -> tuple[dict[str, Any], lines.Counts]:
    """The answer as counted, each count with the /api/cases question that lists its cases
    (_queried), and its counts, for the shown values worked out on each ask."""
    asked, unit, keys, when = _asked(data, query)
    found = fields.lines()
    lines.check(found)
    read = fields.readings(data, unit, found)
    usable = {f: r for f, r in read.items() if isinstance(r, Reading)}
    cases = _cases(data, asked, keys, when)
    counts = lines.Counts(_tallied(data, cases, fields.records(unit), usable), usable)
    answer = {
        "product": unit.substance or unit.included[0],
        "reactions": [data.pt_name(k) or k for k in keys],
        **when.described(),
        "cases": {p: counts.given[COUNTED][p] for p in PERIODS},
        "groups": fields.groups(),
        "lines": [lines.line(line, read[line.field], counts) for line in found],
        "not_available": {f: why for f, why in read.items() if isinstance(why, str)},
    }
    return _queried(query, answer, read), counts


def breakdowns(data: Data, query: Query) -> dict[str, Any]:
    """The event's breakdowns: the product (`product`), the event's reactions as the release
    names them (`reactions`), the `window` and `before` it was counted on, the cases counted in
    each (`cases`), the rule's `groups`, and each field's line, in the rule's order (`lines`),
    with the value it shows and whether it is an alarm; `not_available` gives, for each line the
    release or this viewer cannot give, why. Each count carries the /api/cases question that
    lists its cases. The counts are kept without the question's points, fall and strengths,
    which change only the values shown."""
    settings = lines.asked(query)
    counted = {k: v for k, v in query.items() if k not in lines.OWN}
    answer, counts = data.remember("breakdowns", counted, lambda: _counted(data, counted))
    return lines.shown(answer, counts, fields.lines(), settings)


# the cases behind each count -----------------------------------------------------------------


def _queried(query: Query, found: dict[str, Any], read: dict[str, Reading | str]) -> dict[str, Any]:
    """The answer with the /api/cases question of each count, the event named as `event`: the
    cases counted in each period (`cases_query`); each line's reports (`cases_query`) and those
    giving its field (`given_query`, null where `given` is); and each value's."""

    def behind(period: str, field: str = "", value: Any = None) -> str:
        # the case list's reaction is its one-reaction filter: the event is its `event`
        chosen = {"event": query["reaction"], "period": [period], "field": [field] if field else []}
        chosen["value"] = [] if value is None else [str(value)]
        return cases_query(query, "reaction", **chosen)

    found["cases_query"] = {p: behind(p) for p in PERIODS}
    for line in found["lines"]:
        f, reading = line["field"], read[line["field"]]
        # a line over every case, kept or set aside, counts its reports as those giving it
        whole = isinstance(reading, Reading) and reading.whole
        for p in PERIODS:
            line[p]["cases_query"] = behind(p, f) if whole else behind(p)
            line[p]["given_query"] = behind(p, f) if line[p]["given"] is not None else None
        for each in [*line["values"], *line.get("bands", [])]:
            for p in PERIODS:
                each[p]["cases_query"] = behind(p, f, each["value"])
    return found


def case_filter(data: Data, query: Query) -> tuple[str, list]:
    """The condition over `explorer_case_T c` for the cases behind one count of the breakdowns
    `query` asks for, in `period` (before or window): with no `field`, the cases counted in it;
    with `field`, those giving the field (for a line over every case, kept or set aside, every
    case); with `value`, those giving that value, read by the reading the line was counted with.
    Refused for a period, field or value the breakdowns do not know, and for a line the release
    or this viewer cannot give. The cases are kept per release, so each page reads them back."""
    ids = data.remember("breakdown_cases", query, lambda: _behind(data, query))
    return "c.case_id_T IN (SELECT unnest(?::BIGINT[]))", [ids]


def _behind(data: Data, query: Query) -> list[int]:
    """The ids of the cases case_filter picks, in order."""
    period = value_of(query, "period").strip()
    if period not in PERIODS:
        raise Problem(400, f"Name the period as {' or '.join(PERIODS)}.")
    field, chosen = value_of(query, "field").strip(), value_of(query, "value").strip()
    if chosen and not field:
        raise Problem(400, "A value is a field's: name the field as field.")
    asked, unit, keys, when = _asked(data, query)
    cases = _cases(data, asked, keys, when)
    if not field:
        return [
            r["case_id_T"]
            for r in data.rows(
                f"SELECT case_id_T FROM ({cases[0]}) WHERE counted_T AND period_T = ? "
                "ORDER BY case_id_T",
                [*cases[1], period],
            )
        ]
    found = fields.lines()
    if field not in {line.field for line in found}:
        named = ", ".join(line.field for line in found)
        raise Problem(400, f"{field} is not a field of the breakdowns, which are {named}.")
    read = fields.readings(data, unit, found)
    reading = read[field]
    if isinstance(reading, str):
        raise Problem(400, reading)
    usable = {f: r for f, r in read.items() if isinstance(r, Reading)}
    # Key details counts the other fields' values; any other field is read alone
    wanted = usable if field == fields.KEY_DETAILS else {field: reading}
    values, params = _read(cases, fields.records(unit), wanted)
    rows = data.rows(
        f"{values} SELECT a.case_id_T, a.v, cs.period_T AS p FROM a JOIN cs USING (case_id_T) "
        "WHERE a.f = ?",
        [*params, field],
    )
    key = reading.key or (lambda v: v)
    if reading.banded and is_onset(chosen):  # a band of days, as the onset filter reads it
        low, high = onset_span(chosen)
        return sorted(
            r["case_id_T"]
            for r in rows
            if r["p"] == period
            and (low is None or int(r["v"]) >= low)
            and (high is None or int(r["v"]) <= high)
        )
    if chosen and chosen not in {key(r["v"]) for r in rows}:
        [name] = [line.name for line in found if line.field == field]
        raise Problem(400, f"{chosen} is not a value {name} gives in these cases.")
    return sorted(
        {r["case_id_T"] for r in rows if r["p"] == period and (not chosen or key(r["v"]) == chosen)}
    )


__all__ = ["breakdowns", "case_filter"]
