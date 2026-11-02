"""Each breakdown line's shares and the value it shows. A value's share is of the reports that
give the field, by period; its change is in points from before to the window; it rose when it is
up by rule breakdown-rose's points and its chance test passes (rule chance-test), so a rise by
chance never takes a line from a real one. Each field's `pick` in rule breakdown-lines names
the value its line shows (`shown`), one function here for each kind of pick, and the line is an
alarm when that value's change reaches the points (rule breakdown-alarm, or the question's
`points`) and its chance test passes; with falls counted (`fall`), a fall of that size too.

    Counts(rows, read)          the tallied rows, by field, value and period
    line(found, read, counts)   a field's line, each value with its share, change, p and rose
    asked(query)                the question's points, fall and strengths, refused when unread
    shown(answer, ...)          the answer with each line's shown value and alarm
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from statistics import median
from typing import Any, NamedTuple

from open_altio.rulebook import value
from open_altio.stats import chance

from ..answers import Problem
from ..eventfacts import band_ids
from ..explore import Query, value_of
from ..filters import age_bands
from . import fields
from .fields import Line, Reading, Strength, strength_reader
from .periods import BEFORE, WINDOW

ROSE, ALARM = "breakdown-rose", "breakdown-alarm"
PERIODS = (BEFORE, WINDOW)
COUNTED, EVERY = "_counted", "_every"  # the cases counted, and every case kept or set aside
OWN = ("points", "fall", "strength")  # what changes only the shown values, never a count
POINTS = "points must be a positive number, such as 10."
FALL = "fall must be 1, a fall counts as a rise does, or 0."


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


class Counts:
    """The tallied rows, by field: its reports and those giving it by period, and each value's
    cases by period and its words, those of the most cases where its texts are written apart;
    for a field whose texts count under a value worked out in fields.py, the cases themselves."""

    def __init__(self, rows: list[dict[str, Any]], read: dict[str, Reading]) -> None:
        self.given: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(PERIODS, 0))
        self.values: dict[str, dict[str, dict[str, int]]] = defaultdict(dict)
        self.ids: dict[tuple[str, str], dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
        written: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        for r in rows:
            f, p = r["f"], r["p"]
            if r["whole"]:
                self.given[f][p] = r["n"]
                continue
            reading = read.get(f)
            v = reading.key(r["v"]) if reading and reading.key else r["v"]
            if reading and reading.key:
                self.ids[(f, v)][p] |= set(r["ids"])
            else:
                self.values[f].setdefault(v, dict.fromkeys(PERIODS, 0))[p] = r["n"]
            if r["w"] is not None:
                written[(f, v)][r["w"]] += r["n"]
        for (f, v), by in self.ids.items():
            self.values[f][v] = {p: len(by.get(p, ())) for p in PERIODS}
        self.words = {
            fv: max(n.items(), key=lambda w: (w[1], w[0]))[0] for fv, n in written.items()
        }


class Shares:
    """Cases of a value, or of several, among the reports giving the field, by period."""

    def __init__(self, cases: Mapping[str, int], given: Mapping[str, int]) -> None:
        self.cases, self.given = dict(cases), dict(given)
        self.exact: Fraction | None = None
        self.test: chance.Chance | None = None
        if all(given[p] for p in PERIODS):
            b, w = (Fraction(cases[p], given[p]) for p in PERIODS)
            self.exact = (w - b) * 100
            a, c = cases[BEFORE], cases[WINDOW]
            self.test = chance.two_by_two(a, given[BEFORE] - a, c, given[WINDOW] - c)

    def periods(self) -> dict[str, dict[str, Any]]:
        return {
            p: {"cases": self.cases[p], "share": _share(self.cases[p], self.given[p])}
            for p in PERIODS
        }


class Days:
    """The days to onset by period: their median, and the change in days."""

    def __init__(self, days: Mapping[str, list[int]]) -> None:
        self.days = days
        self.cases = {p: len(days[p]) for p in PERIODS}
        self.median = {p: median(days[p]) if days[p] else None for p in PERIODS}
        self.exact: Fraction | None = None
        self.test: chance.Chance | None = None
        if all(days[p] for p in PERIODS):
            self.exact = Fraction(median(days[WINDOW])) - Fraction(median(days[BEFORE]))
            self.test = chance.days(days[BEFORE], days[WINDOW])

    def periods(self) -> dict[str, dict[str, Any]]:
        return {p: {"cases": self.cases[p], "days": self.median[p]} for p in PERIODS}


class Rise(NamedTuple):
    """Rule breakdown-rose, read once for many values."""

    at_least: Fraction
    tested: bool


def rise() -> Rise:
    return Rise(Fraction(str(value(ROSE, "points_at_least"))), bool(value(ROSE, "chance_test")))


def _rose(c: Shares | Days, rule: Rise) -> bool | None:
    """Up at least the rule's points and, where the rule asks it, past the chance test; None
    where a period has nothing to compare."""
    if c.exact is None or c.test is None:
        return None
    return c.exact >= rule.at_least and (bool(c.test.passes) or not rule.tested)


def _compared(c: Shares | Days, rule: Rise) -> dict[str, Any]:
    change = None if c.exact is None else float(c.exact)
    p = c.test.p if c.test else None
    return c.periods() | {"change": change, "p": p, "rose": _rose(c, rule)}


def line(found: Line, read: Reading | str, counts: Counts) -> dict[str, Any]:
    """A field's line: its reports, those giving it and their share by period, and each value's
    cases and share of those giving the field, with the change in points, p and rose."""
    out: dict[str, Any] = {"field": found.field, "name": found.name, "group": found.group}
    out["filter"] = fields.FILTERS.get(found.field)
    reports = counts.given[EVERY if isinstance(read, Reading) and read.whole else COUNTED]
    if isinstance(read, str):
        none = {"given": None, "given_share": None}
        return out | {p: {"cases": reports[p], **none} for p in PERIODS} | {"values": []}
    given = counts.given[found.field]
    for p in PERIODS:
        share = _share(given[p], reports[p]) if read.given_in else None
        out[p] = {"cases": reports[p], "given": given[p], "given_share": share}
    values, rule = [], rise()
    for v, n in counts.values[found.field].items():
        each: dict[str, Any] = {"value": int(v) if read.number else v}
        if read.name:
            each["name"] = read.name(v, counts.words.get((found.field, v)))
        values.append(each | _compared(Shares(n, given), rule))
    values.sort(key=lambda e: (-e[WINDOW]["cases"], -e[BEFORE]["cases"], str(e["value"])))
    if read.banded:
        out["bands"] = _bands(counts.values[found.field], given, rule)
    return out | {"values": values}


def _bands(days: Mapping[str, Mapping[str, int]], given: Mapping[str, int], rule: Rise) -> list:
    """The days' cases in each of rule breakdown-lines' onset bands, each band named by its
    onset filter's value (`2-7`, `91-`), with its share, change, p and rose."""
    out = []
    for band in value(fields.RULE, "onset_bands"):
        low, high = band["from"], band.get("to")
        inside = [n for v, n in days.items() if low <= int(v) and (high is None or int(v) <= high)]
        cases = {p: sum(n[p] for n in inside) for p in PERIODS}
        named = {"value": f"{low}-{'' if high is None else high}", "name": band["name"]}
        out.append(named | _compared(Shares(cases, given), rule))
    return out


# the question's own settings ----------------------------------------------------------------


@dataclass(frozen=True)
class Asked:
    points: Fraction
    fall: bool
    strengths: tuple[Strength, ...]
    rise: Rise


def asked(query: Query) -> Asked:
    """The question's points (else rule breakdown-alarm's), whether a fall counts, and the
    strengths passed; refused naming what cannot be read."""
    text = value_of(query, "points").strip()
    try:
        points = Fraction(text) if text else Fraction(str(value(ALARM, "points")))
    except (ValueError, ZeroDivisionError):
        raise Problem(400, POINTS) from None
    if points <= 0:
        raise Problem(400, POINTS)
    fall = value_of(query, "fall").strip()
    if fall not in ("", "0", "1"):
        raise Problem(400, FALL)
    strengths, read = [], strength_reader()
    for written in (s.strip() for s in query.get("strength", [])):
        if not written:
            continue
        if (found := read(written)) is None:
            raise Problem(400, f"strength {written!r} is not a strength, such as 40 mg.")
        strengths.append(found)
    if len({s.measure for s in strengths}) > 1:
        raise Problem(400, "strength: strengths in different units cannot be compared.")
    counts = bool(value(ALARM, "fall_counts")) if not fall else fall == "1"
    return Asked(points, counts, tuple(strengths), rise())


def _alarm(c: Shares | Days | None, settings: Asked) -> bool | None:
    if c is None or c.exact is None or c.test is None:
        return None
    reaches = c.exact >= settings.points or (settings.fall and c.exact <= -settings.points)
    return reaches and bool(c.test.passes)


# the value each line shows, one function for each kind of pick --------------------------------


class Pick(NamedTuple):
    """What a pick is given: the field's line as counted, its pick, the counts and the question."""

    line: dict[str, Any]
    pick: Any
    counts: Counts
    settings: Asked


class Chosen(NamedTuple):
    value: Any  # the value shown, or the name of the values it gathers
    values: list[Any]  # the line's values it counts
    compared: Shares | Days


def _cases(p: Pick, values: list[Any]) -> dict[str, int]:
    """The values' cases together by period, each case once."""
    f = p.line["field"]
    kept = [k for k in (p.counts.ids.get((f, str(v))) for v in values) if k is not None]
    if kept:
        return {q: len(set().union(*(k.get(q, set()) for k in kept))) for q in PERIODS}
    held = p.counts.values.get(f, {})
    zero = dict.fromkeys(PERIODS, 0)
    return {q: sum(held.get(str(v), zero)[q] for v in values) for q in PERIODS}


def _chosen(p: Pick, shown: Any, values: list[Any]) -> Chosen:
    return Chosen(shown, values, Shares(_cases(p, values), p.counts.given[p.line["field"]]))


class Option(NamedTuple):
    """A value, or a group of values, as _most ranks it."""

    value: Any
    values: list[Any]
    rose: bool | None
    change: Fraction | float | None
    cases: tuple[int, int]  # in the window, then before


def _option(p: Pick, shown: Any, values: list[Any]) -> Option:
    c = _chosen(p, shown, values).compared
    rose = _rose(c, p.settings.rise)
    return Option(shown, values, rose, c.exact, (c.cases[WINDOW], c.cases[BEFORE]))


def _counted(v: dict[str, Any]) -> Option:
    """A value of the line, ranked by its rose and change as counted."""
    cases = (v[WINDOW]["cases"], v[BEFORE]["cases"])
    return Option(v["value"], [v["value"]], v["rose"], v["change"], cases)


def _most(p: Pick, options: list[Option]) -> Chosen | None:
    """The option that rose most among those that rose, else the one up most, else the
    commonest in the window, else before; None where no option has a case."""
    changed = [o for o in options if o.rose] or [o for o in options if o.change is not None]
    best: Option | None
    if changed:
        best = max(changed, key=lambda o: (o.change, o.cases[0]))
    else:
        best = max((o for o in options if any(o.cases)), key=lambda o: o.cases, default=None)
    return None if best is None else _chosen(p, best.value, best.values)


def rose_most(p: Pick) -> Chosen | None:
    return _most(p, [_counted(v) for v in p.line["values"]])


def most_severe_rose(p: Pick) -> Chosen | None:
    """The first outcome of rule serious-outcomes' order that rose, else the first: death."""
    order = list(value("serious-outcomes", "serious"))
    rose = {v["value"] for v in p.line["values"] if v["rose"]}
    code = next((code for code in order if code in rose), order[0])
    return _chosen(p, code, [code])


def children_or_older_rose_else_most(p: Pick) -> Chosen | None:
    """Children or the older bands (rule age-groups) where either rose, the one up most; else
    the group that rose most of those two and each band in neither."""
    children, older = band_ids("age-groups", "children"), band_ids("age-groups", "older")
    named = [_option(p, "children", children), _option(p, "older", older)]
    if rose := [o for o in named if o.rose]:
        return _most(p, rose)
    others = [b["id"] for b in age_bands() if b["id"] not in children + older]
    return _most(p, named + [_option(p, band, [band]) for band in others])


def health_professionals_or_lawyers_rose(p: Pick) -> Chosen | None:
    lawyers = _chosen(p, "lawyers", list(value(fields.RULE, "lawyers")))
    if _rose(lawyers.compared, p.settings.rise):
        return lawyers
    return _chosen(p, "health_professionals", list(value(fields.RULE, "health_professionals")))


def median_days(p: Pick) -> Chosen | None:
    held = p.counts.values.get(p.line["field"], {})
    days = {q: [int(v) for v, n in held.items() for _ in range(n[q])] for q in PERIODS}
    return Chosen("median", [], Days(days))


def value_named(p: Pick) -> Chosen | None:
    return _chosen(p, p.pick["value"], [p.pick["value"]])


def all_given(p: Pick) -> Chosen | None:
    every = len(p.pick["all_given"])
    return _chosen(p, every, [every])


def copies_set_aside(p: Pick) -> Chosen | None:
    return _chosen(p, "set_aside", ["set_aside"])


def highest_strength(p: Pick) -> Chosen | None:
    """The doses that read to the highest strength passed; with none passed, the highest
    strength read from at least rule dose-strength's `min_share` of the reports giving a dose,
    of the measure most of those reports are in, named as its commonest dose writes it. None
    where no strength is known."""
    at: dict[tuple[str, Decimal], list[tuple[Strength, str]]] = defaultdict(list)
    reader = strength_reader()
    for v in p.line["values"]:  # the commonest first
        if (read := reader(v["value"])) is not None:
            at[(read.measure, read.size)].append((read, v["value"]))
    top = max(p.settings.strengths, key=lambda s: s.size, default=None)
    if top is None:
        given = sum(p.counts.given[p.line["field"]].values())
        at_least = Fraction(str(value(fields.STRENGTH, "min_share")))
        common = []
        for doses in at.values():
            n = sum(_cases(p, [d for _, d in doses]).values())
            if given and Fraction(n, given) >= at_least:
                common.append((doses[0][0], n))
        if not common:
            return None
        by: Counter[str] = Counter()
        for s, n in common:
            by[s.measure] += n
        measure = max(by, key=lambda m: (by[m], m))
        top = max((s for s, _ in common if s.measure == measure), key=lambda s: s.size)
    written = sorted(d for _, d in at.get((top.measure, top.size), []))
    return _chosen(p, top.words(), written)


PICKS: dict[str, Callable[[Pick], Chosen | None]] = {
    "most_severe_rose": most_severe_rose,
    "children_or_older_rose_else_most": children_or_older_rose_else_most,
    "health_professionals_or_lawyers_rose": health_professionals_or_lawyers_rose,
    "median_days": median_days,
    "value": value_named,
    "highest_strength": highest_strength,
    "all_given": all_given,
    "copies_set_aside": copies_set_aside,
    "rose_most": rose_most,
}


def kind(pick: Any) -> str:
    """A pick's kind: its name, or the one key of a pick that gives its own value."""
    if isinstance(pick, dict) and len(pick) == 1:
        return str(next(iter(pick)))
    return str(pick)


def check(found: list[Line]) -> None:
    """Refuse the question when the rule names a pick no function here makes."""
    if unknown := [f.field for f in found if kind(f.pick) not in PICKS]:
        raise Problem(400, f"Rule {fields.RULE} names picks the breakdowns cannot make: {unknown}.")


def shown(answer: dict[str, Any], counts: Counts, found: list[Line], settings: Asked) -> dict:
    """The answer with each line's shown value (`shown`, null where the line has none) and
    whether it is an alarm (`alarm`, null where its value has no change to compare)."""
    picks = {f.field: f.pick for f in found}
    out = []
    for each in answer["lines"]:
        chosen = None
        if each["field"] not in answer["not_available"]:
            pick = picks[each["field"]]
            chosen = PICKS[kind(pick)](Pick(each, pick, counts, settings))
        made = None
        if chosen is not None:
            made = {"pick": kind(picks[each["field"]]), "value": chosen.value}
            made |= {"values": chosen.values} | _compared(chosen.compared, settings.rise)
        alarm = _alarm(chosen.compared if chosen else None, settings)
        out.append(each | {"shown": made, "alarm": alarm})
    return answer | {"lines": out}


__all__ = [
    "COUNTED",
    "EVERY",
    "OWN",
    "PICKS",
    "Asked",
    "Counts",
    "asked",
    "check",
    "kind",
    "line",
    "shown",
]
