"""Each field of rule breakdown-lines as an event's cases give it: the value or values a case
gives, and no row where it gives the field Not given (rule not-given), so a blank is never a
value. Each reader is SQL over two tables the answer makes first:

    cs    the event's cases, kept or set aside (case_id_T, period_T, counted_T and CASE_COLUMNS);
          a case set aside is not counted, so only Duplicates reads it
    rec   the counted cases' drug records in the roles the product is counted in (RECORDS):
          `ours_T` for the product's own, `rank_T` and `seq_T` their order, by role and then by
          FDA's drug sequence

and selects (case_id_T, v, w): a value, and the words the release writes it in where the page
cannot name it from a code (an indication's spelling, an other drug's ingredients).

`strength_of(text)` reads a strength from the first words of a dose as written, in one of rule
dose-strength's units: 40 mg, 2.5MG, 250 MG/5ML, 80 MILLIGRAM.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from open_altio.faers import literature
from open_altio.rulebook import value

from .. import drugs
from ..answers import Problem
from ..drugs import Unit
from ..eventfacts import NameNotHeld, pregnancy_terms
from ..explore import Data
from ..filters import NOT_GIVEN
from ..recordfilters import INDICATION, OTHER, code, indication_given, indication_keyer, written

RULE = "breakdown-lines"
CORRECTION = "rechallenge-correction"
STRENGTH = "dose-strength"
KEY_DETAILS = "key_details"
SERIOUS = "serious"  # Seriousness' value for a case with any serious outcome
# what cs carries of the case table, for the readers below
CASE_COLUMNS = (
    "quarter_T",
    "outcomes_T",
    "age_band_T",
    "sex_T",
    "reporter_type_T",
    "country_T",
    "rept_cod",
    "dup_kept_T",
)
NO_LITERATURE = "This release's explorer database was built without FDA's literature reference."
_AMOUNT = re.compile(r"\s*([0-9]+(?:\.[0-9]+)?|\.[0-9]+)\s*")


@dataclass(frozen=True)
class Line:
    """A line of rule breakdown-lines: its field, name, group and pick."""

    field: str
    name: str
    group: str
    pick: Any


@dataclass(frozen=True)
class Reading:
    """How a field is read: `sql` selects (case_id_T, v, w) over cs and rec."""

    sql: str
    params: list[Any] = field(default_factory=list)
    given_in: bool = True  # the line has a Given in share: FAERS has a field for it
    whole: bool = False  # over every case of the question, kept or set aside
    number: bool = False  # its values are whole numbers
    key: Callable[[str], str] | None = None  # the value a text counts under, worked out here
    name: Callable[[str, str | None], str | None] | None = None  # (value, w) -> its words
    banded: bool = False  # its days are counted in rule breakdown-lines' onset bands too


@dataclass(frozen=True)
class Strength:
    """An amount in a unit of rule dose-strength, as the rule writes the unit, and what the unit
    measures with its size there (the rule's `measures`)."""

    amount: Decimal
    unit: str
    measure: str
    scale: Decimal  # the unit's size in its measure

    @property
    def size(self) -> Decimal:
        """The amount in its measure's unit of size 1, so 0.32 g and 320 mg are one strength."""
        return self.amount * self.scale

    def same(self, other: Strength) -> bool:
        return self.measure == other.measure and self.size == other.size

    def words(self) -> str:
        return f"{self.amount.normalize():f} {self.unit}"


def _spellings() -> tuple[re.Pattern[str], dict[str, str], dict[str, tuple[str, Decimal]]]:
    """Every way of writing a unit of the rule, as one pattern, the unit each way names, and
    what each unit measures with its size there."""
    units = tuple(value(STRENGTH, "units"))
    measures = tuple((m, tuple(sizes.items())) for m, sizes in value(STRENGTH, "measures").items())
    pattern, ways = _unit_pattern(units, tuple(dict(value(STRENGTH, "spellings")).items()))
    return pattern, ways, _measured(units, measures)


@functools.cache
def _measured(
    units: tuple[str, ...], measures: tuple[tuple[str, tuple[tuple[str, Any], ...]], ...]
) -> dict[str, tuple[str, Decimal]]:
    """Each unit's measure and size; a unit in no measure or in two, or a unit measured that
    the rule does not read, refuses the question, naming the rule."""
    found = [(u, (m, Decimal(str(size)))) for m, sizes in measures for u, size in sizes]
    named = [u for u, _ in found]
    if unmeasured := [u for u in units if u not in named]:
        raise Problem(400, f"Rule {STRENGTH} names units in no measure: {unmeasured}.")
    if unread := [u for u in named if u not in units]:
        raise Problem(400, f"Rule {STRENGTH} measures units that are not in its units: {unread}.")
    if twice := sorted({u for u in named if named.count(u) > 1}):
        raise Problem(400, f"Rule {STRENGTH} puts units in more than one measure: {twice}.")
    return dict(found)


@functools.cache
def _unit_pattern(
    units: tuple[str, ...], spellings: tuple[tuple[str, str], ...]
) -> tuple[re.Pattern[str], dict[str, str]]:
    """The longest way first, matched whatever its capitals and spaces, and not followed by
    more of a unit (mg/kg is no mg)."""
    ways = {_bare(u): u for u in units} | {_bare(w): u for w, u in spellings if u in units}
    parts = [r"\s*".join(map(re.escape, w)) for w in sorted(ways, key=len, reverse=True)]
    return re.compile(rf"(?:{'|'.join(parts)})(?![A-Za-z0-9/])", re.IGNORECASE), ways


def _bare(way: str) -> str:
    return "".join(way.split()).lower()


def strength_of(text: str | None) -> Strength | None:
    """The strength a dose as written starts with, or None where it starts with none of rule
    dose-strength's units: no number first, a number written with a comma, or a unit the rule
    does not hold, such as mg/kg."""
    return strength_reader()(text)


def strength_reader() -> Callable[[str | None], Strength | None]:
    """strength_of with the rule read once, for many doses."""
    pattern, ways, measured = _spellings()

    def read(text: str | None) -> Strength | None:
        number = _AMOUNT.match(text or "")
        if not number:
            return None
        if not (found := pattern.match(text or "", number.end())):
            return None
        unit = ways[_bare(found.group())]
        return Strength(Decimal(number.group(1)), unit, *measured[unit])

    return read


def groups() -> list[dict[str, str]]:
    return [dict(g) for g in value(RULE, "groups")]


def lines() -> list[Line]:
    """The rule's lines, in order; a field in no group of the rule, or one no reader here
    reads, refuses the question, naming the rule."""
    held = {g["group"] for g in groups()}
    found = [Line(f["field"], f["name"], f["group"], f["pick"]) for f in value(RULE, "fields")]
    if strays := [f.field for f in found if f.group not in held]:
        raise Problem(400, f"Rule {RULE} puts fields in no group it holds: {strays}.")
    if unread := [f.field for f in found if f.field not in READERS]:
        raise Problem(400, f"Rule {RULE} names fields the breakdowns cannot read: {unread}.")
    return found


def records(unit: Unit) -> tuple[str, list[Any]]:
    """SQL: rec, from cs."""
    ours, ours_params = unit.records("d")
    marks = ", ".join("?" for _ in unit.roles)
    return (
        "SELECT d.case_id_T, cs.quarter_T, d.drug_seq, try_cast(d.drug_seq AS BIGINT) AS seq_T, "
        "list_position(?::VARCHAR[], d.role_T) AS rank_T, d.role_T, d.dechal, d.rechal, "
        "d.dose_vbm, d.time_to_onset_T, d.substance_T, d.drugname_norm_T, "
        f"coalesce(({ours}), FALSE) AS ours_T FROM explorer_drug_T d JOIN cs USING (case_id_T) "
        f"WHERE cs.counted_T AND d.role_T IN ({marks})",
        [drugs.roles(), *ours_params, *unit.roles],
    )


# each field ----------------------------------------------------------------------------------


def _case(expr: str) -> Reading:
    """A field of the case table, one value a case."""
    return Reading(
        f"SELECT case_id_T, {expr} AS v, NULL AS w FROM cs WHERE counted_T AND {expr} IS NOT NULL"
    )


def _first(expr: str, *, number: bool = False, banded: bool = False) -> Reading:
    """A field of the product's records, from its first record that gives it, in the order the
    filters read it too (recordfilters.FIRST)."""
    return Reading(
        f"SELECT case_id_T, {expr} AS v, NULL AS w FROM rec WHERE ours_T AND {expr} IS NOT NULL "
        "QUALIFY row_number() OVER (PARTITION BY case_id_T ORDER BY rank_T, seq_T, drug_seq) = 1",
        number=number,
        banded=banded,
    )


def _seriousness(data: Data, unit: Unit) -> Reading:
    """Each outcome code the case gives, and SERIOUS where one of them is a code of rule
    serious-outcomes: read here, so the case list picks those cases as the line counts them."""
    # FDA writes outcome rows only for serious outcomes: a case with none is not missing a field
    return Reading(
        "SELECT case_id_T, unnest(CASE WHEN len(outcomes_T) = 0 "
        f"THEN ['{NOT_GIVEN}'] ELSE outcomes_T END) AS v, NULL AS w FROM cs WHERE counted_T "
        f"UNION ALL SELECT case_id_T, '{SERIOUS}', NULL FROM cs "
        "WHERE counted_T AND list_has_any(outcomes_T, ?::VARCHAR[])",
        [list(value("serious-outcomes", "serious"))],
    )


def _pregnancy(data: Data, unit: Unit) -> Reading | str:
    if data.meddra is None:
        return data.why_no_smqs
    try:
        terms = pregnancy_terms(data.meddra)
    except NameNotHeld as lost:
        return str(lost)
    return Reading(
        "SELECT case_id_T, CASE WHEN case_id_T IN (SELECT case_id_T FROM explorer_reac_term_T "
        "WHERE term_T IN (SELECT unnest(?::VARCHAR[]))) THEN 'yes' ELSE 'no' END AS v, "
        "NULL AS w FROM cs WHERE counted_T",
        [data.reactions.texts(terms)],
        given_in=False,
    )


def _indication(data: Data, unit: Unit) -> Reading:
    """Each indication the product's records give, counted under today's preferred term where
    reactions are, else as FDA wrote it whatever its capitals and spaces."""
    meddra = data.reactions.meddra
    named = meddra.pt_names() if meddra else {}
    return Reading(
        f"SELECT DISTINCT r.case_id_T, {INDICATION.format(i='i')} AS v, i.indi_pt_spelling_T AS w "
        "FROM rec r JOIN explorer_indi_T i "
        "ON i.case_id_T = r.case_id_T AND i.indi_drug_seq = r.drug_seq "
        f"WHERE r.ours_T AND {indication_given('i')}",
        key=indication_keyer(data.reactions),
        name=lambda k, spelled: named.get(k) or spelled,
    )


def _rechal(data: Data, unit: Unit) -> Reading:
    if value(CORRECTION, "correction") != "none":
        raise Problem(400, f"Rule {CORRECTION} gives a correction the explorer cannot read.")
    # the filler of some quarters is read by the quarter of FDA's file the case came in
    return _first(code("rechal", "rechal", quarter="quarter_T"))


def _literature(data: Data, unit: Unit) -> Reading | str:
    """Whether the case cites an article (rule literature-reference), from FDA's lit_ref, which
    an explorer database built before it held the field cannot give."""
    held = data.facts.once(
        "case_table_holds_lit_ref",
        lambda: bool(
            data.rows(
                "SELECT 1 FROM duckdb_columns() WHERE database_name = current_database() "
                "AND table_name = 'explorer_case_T' AND column_name = 'lit_ref'"
            )
        ),
    )
    if not held:
        return NO_LITERATURE
    cited = literature.cited("c.quarter_T", "c.lit_ref")
    return Reading(
        f"SELECT case_id_T, v, NULL AS w FROM (SELECT cs.case_id_T, {cited} AS v FROM cs "
        "JOIN explorer_case_T c USING (case_id_T) WHERE cs.counted_T) WHERE v IS NOT NULL"
    )


def _dose(data: Data, unit: Unit) -> Reading:
    dose = written("dose_vbm", "dose_vbm")
    # each dose's cases are kept, as a case's doses can read to one strength (strength_of)
    return Reading(
        f"SELECT DISTINCT case_id_T, {dose} AS v, NULL AS w FROM rec "
        f"WHERE ours_T AND {dose} IS NOT NULL",
        key=str,
    )


def _other_drugs(data: Data, unit: Unit) -> Reading:
    """Each other drug in the roles the product is counted in, or NOT_GIVEN for none."""
    drug = OTHER.format(d="rec")
    others = (
        f"SELECT DISTINCT case_id_T, {drug} AS v, substance_T AS w FROM rec "
        f"WHERE NOT ours_T AND {drug} IS NOT NULL"
    )
    return Reading(
        f"{others} UNION ALL SELECT case_id_T, '{NOT_GIVEN}', NULL FROM cs WHERE counted_T "
        f"AND case_id_T NOT IN (SELECT case_id_T FROM ({others}))",
        name=lambda drug, ingredients: drugs.title(drug) if ingredients else None,
    )


def _duplicates(data: Data, unit: Unit) -> Reading:
    return Reading(
        "SELECT case_id_T, CASE WHEN dup_kept_T THEN 'kept' ELSE 'set_aside' END AS v, "
        "NULL AS w FROM cs",
        whole=True,
    )


def key_details(found: list[Line], available: set[str]) -> Reading | str:
    """How many of the fields Key details' pick names (`all_given`) a case gives, read over the
    other fields' values (v); Not available where one of them is."""
    pick = next(f.pick for f in found if f.field == KEY_DETAILS)
    named = list(pick.get("all_given") or []) if isinstance(pick, dict) else []
    if not named or set(named) - {f.field for f in found} - {KEY_DETAILS}:
        raise Problem(400, f"Rule {RULE} gives Key details no fields of its own lines to count.")
    if missing := [f.name for f in found if f.field in named and f.field not in available]:
        return f"It counts {', '.join(missing)}, which this release cannot give."
    return Reading(
        "SELECT cs.case_id_T, count(DISTINCT x.f) AS v, NULL AS w FROM cs LEFT JOIN v x "
        "ON x.case_id_T = cs.case_id_T AND list_contains(?::VARCHAR[], x.f) "
        "WHERE cs.counted_T GROUP BY 1",
        [named],
        number=True,
    )


# the explorer filter that picks each line's values' cases, by its parameter (filters.py): each
# value of the line is a value of the filter; a line not named has none
FILTERS = {
    "seriousness": "outcome",
    "age": "age",
    "sex": "sex",
    "indication": "indication",
    "onset": "onset",
    "dechal": "dechal",
    "rechal": "rechal",
    "role": "prole",
    "dose": "dose",
    "other_drugs": "other_drug",
    "reporter": "reporter",
    "country": "country",
    "report_type": "report_type",
}

READERS: dict[str, Callable[[Data, Unit], Reading | str] | None] = {
    "seriousness": _seriousness,
    "age": lambda data, unit: _case("age_band_T"),
    "sex": lambda data, unit: _case("sex_T"),
    "pregnancy": _pregnancy,
    "indication": _indication,
    "onset": lambda data, unit: _first("time_to_onset_T", number=True, banded=True),
    "dechal": lambda data, unit: _first(code("dechal", "dechal")),
    "rechal": _rechal,
    "role": lambda data, unit: _first("role_T"),
    "dose": _dose,
    "other_drugs": _other_drugs,
    "reporter": lambda data, unit: _case("reporter_type_T"),
    "literature": _literature,
    "country": lambda data, unit: _case("country_T"),
    "report_type": lambda data, unit: _case(code("rept_cod", "rept_cod")),
    KEY_DETAILS: None,  # read over the others' values: key_details()
    "duplicates": _duplicates,
}


def readings(data: Data, unit: Unit, found: list[Line]) -> dict[str, Reading | str]:
    """Each line's reading, or why the release or this viewer cannot give it."""
    out: dict[str, Reading | str] = {}
    for line in found:
        read = READERS[line.field]
        if read is not None:
            out[line.field] = read(data, unit)
    available = {f for f, r in out.items() if isinstance(r, Reading)}
    if any(f.field == KEY_DETAILS for f in found):
        out[KEY_DETAILS] = key_details(found, available)
    return out


__all__ = [
    "CASE_COLUMNS",
    "FILTERS",
    "KEY_DETAILS",
    "READERS",
    "RULE",
    "SERIOUS",
    "STRENGTH",
    "Line",
    "Reading",
    "Strength",
    "groups",
    "lines",
    "readings",
    "records",
    "strength_of",
    "strength_reader",
]
