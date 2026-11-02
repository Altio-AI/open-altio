"""A counted question (/api/count) counted a second way, so every count it answers is checked:
the question is read from its query string again (recountquery.py), apart from filters.py, and
counted apart from the explorer database, over the release's own Parquet tables on a DuckDB
connection of its own.

    recount(opened, question, meddra)   a Recount: [[value, cases]] by the question's `by`, and
                                        its cases; `meddra` names the MedDRA version its
                                        reactions are counted by (None: FDA's text)
    unread(question)                    the parameters it names that are not in READS
    check(first, second, unread)        what /api/count answers as `check`
    sql_of(statement)                   the count as one query with its values written in
    READS                               every question parameter it reads

It reads `case_dedup_T` or `case_latest_T` by `dedup`, `drug_latest_T`, `drug_substance_T`,
`drug_ingredient_T`, `reac_latest_T` and `outc_latest_T`, the label flags' tables for Label
status (recountlabel.py), `drug_onset_T` and `indi_latest_T` for the filters on the drug
records (recountrecords.py), and for today's PTs the licensed `reac_meddra_T`, `indi_meddra_T`
and `meddra_pt`. A
question naming a parameter it does not read is not counted again: its check names the parameter
and never says the counts agree. The count is one statement over those tables (`Statement`),
each value a named parameter; `sql_of` writes each value into it as a constant, so the same
query runs as it stands on the release's tables, as Tables and SQL holds them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from open_altio.faers.dates import received_day
from open_altio.faers.derive import direct_report
from open_altio.faers.drugnames.dictionary import SEPARATOR
from open_altio.faers.explorer_db import reaction_key, reaction_term
from open_altio.faers.meddra.licensed import version_tables
from open_altio.faers.reader import quoted, register_release

from . import recountlabel, recountquery, recountrecords
from .filters import DIRECT, FORM_MARK, NOT_GIVEN
from .recountquery import RECORD, Asked, Drug, Question
from .release import OpenRelease, read_connection

# every question parameter it reads: the explorer's filters; the drug whose page it is and All
# cases' drugs; the chosen reactions; and the field counted by
READS = (
    *("drug", "role", "reaction", "received_from", "received_to", "event_from", "event_to"),
    *("country", "sex", "age", "outcome", "reporter", "sender", "era", FORM_MARK, "dedup"),
    *("label", "product", "prole", "unit", "include", "exclude", "dprod", "drole"),
    *("pt", "pt_out", "by"),
    *("dose", "route", "dose_form", "lot", "indication", "onset", "dechal", "rechal"),
    *("other_drug", "report_type", "other_reaction"),
)
# MedDRA's licensed tables it reads for today's PTs, of reactions and of indications
LICENSED = ("reac_meddra_T", "indi_meddra_T", "meddra_pt")
CASE = RECORD[:3]  # a case's key in the case table and every child table
CASES = {True: "case_dedup_T", False: "case_latest_T"}  # by whether duplicates are set aside
# each field counted as it is, and its column of the case table
FIELDS = {
    "sex": "sex_T",
    "age": "age_band_T",
    "country": "country_T",
    "reporter": "reporter_type_T",
}
# each time counted by: its value over the day a case is dated by (rule received-day)
TIMES = {
    "year": "year({day})",
    "quarter": "concat(year({day}), 'q', quarter({day}))",
    "month": "strftime({day}, '%Y-%m')",
}


class Values:
    """The values a statement is written with, each a named parameter."""

    def __init__(self) -> None:
        self.params: dict[str, Any] = {}

    def one(self, given: Any) -> str:
        name = f"v{len(self.params) + 1}"
        self.params[name] = given
        return f"${name}"

    def among(self, sql: str, given: Iterable[Any]) -> str:
        """SQL: `sql` is one of `given`; false for none."""
        marks = [self.one(g) for g in given]
        return f"{sql} IN ({', '.join(marks)})" if marks else "FALSE"


def _keys(alias: str) -> str:
    return ", ".join(f"{alias}.{k}" for k in CASE)


def _same(a: str, b: str, key: tuple[str, ...] = CASE) -> str:
    return " AND ".join(f"{a}.{k} = {b}.{k}" for k in key)


def _in_cases(cases: str) -> str:
    """SQL: case `c` is one of `cases`, a SELECT of case keys."""
    return f"({_keys('c')}) IN ({cases})"


@dataclass(frozen=True)
class Statement:
    """The second count's SQL: `cases` (WITH ...) picks the question's cases as `picked`;
    `counts` counts them by `by`, in the order /api/count gives them, `total` all of them.
    `licensed`: it reads MedDRA's licensed part."""

    by: str
    cases: str
    params: dict[str, Any]
    licensed: bool = False

    @property
    def counts(self) -> str:
        if self.by in TIMES:
            keyed = (
                f"SELECT {TIMES[self.by].format(day=f'p.{received_day()}')} AS value FROM picked p"
            )
        elif self.by in FIELDS:
            keyed = f"SELECT coalesce(p.{FIELDS[self.by]}, '{NOT_GIVEN}') AS value FROM picked p"
        elif self.by in recountrecords.FIELDS:  # `given`, each value each case's records give
            keyed = (
                f"SELECT DISTINCT {_keys('p')}, coalesce(x.value, '{NOT_GIVEN}') AS value "
                f"FROM picked p LEFT JOIN given x ON {_same('x', 'p')}"
            )
        elif self.by == "outcome":
            keyed = (
                f"SELECT DISTINCT {_keys('p')}, coalesce(o.outc_cod, '{NOT_GIVEN}') AS value "
                "FROM picked p LEFT JOIN (SELECT * FROM outc_latest_T WHERE outc_cod IS NOT NULL) "
                f"o ON {_same('o', 'p')}"
            )
        else:  # each event a case names, by its key; a case naming none counts under null
            keyed = (
                f"SELECT {_keys('p')}, coalesce(r.pt_T, r.text_T) AS k, "
                "max(coalesce(r.pt_name, r.pt)) AS name FROM picked p "
                f"LEFT JOIN reac_keyed r ON {_same('r', 'p')} GROUP BY ALL"
            )
            named = "max(name) AS value, count(*) AS cases"
            return f"{self.cases}\nSELECT {named} FROM ({keyed}) GROUP BY k {self._order}"
        return (
            f"{self.cases}\nSELECT value, count(*) AS cases FROM ({keyed}) GROUP BY 1 {self._order}"
        )

    @property
    def _order(self) -> str:
        """Times in time order, the other values by their cases, most first, then by value; a
        null value last."""
        if self.by in TIMES:
            return "ORDER BY value IS NULL, value"
        return "ORDER BY value IS NULL, cases DESC, value"

    @property
    def total(self) -> str:
        return f"{self.cases}\nSELECT count(*) AS cases FROM picked"


def _drug_cases(drug: Drug, v: Values) -> str:
    """SQL: the keys of the cases naming the drug in one of its roles."""
    return (
        f"SELECT {_keys('d')} FROM drug_latest_T d JOIN drug_substance_T s "
        f"ON {_same('s', 'd', RECORD)} WHERE {_records(drug, v)}"
    )


def _records(drug: Drug, v: Values, *, others: bool = False) -> str:
    """SQL over a drug record `d` and its ingredients `s`: one the drug counts, in one of its
    roles; with `others`, a record in those roles that is another drug's."""
    either = []
    if drug.substance:
        if drug.exact:
            holds = f"s.substance_T = {v.one(drug.substance)}"
        else:  # each of its ingredients is one of the record's
            holds = " AND ".join(
                f"EXISTS (SELECT 1 FROM drug_ingredient_T i WHERE {_same('i', 'd', RECORD)} "
                f"AND i.ingredient_T = {v.one(part)})"
                for part in drug.substance.split(SEPARATOR)
            )
        if drug.excluded:
            spelled = v.among("d.drugname_norm_T", drug.excluded)
            holds += f" AND (d.drugname_norm_T IS NULL OR NOT {spelled})"
        either.append(f"({holds})")
    if drug.included:
        either.append(f"(s.substance_T IS NULL AND {v.among('d.drugname_norm_T', drug.included)})")
    named = v.among("upper(trim(d.role_cod))", drug.roles)
    held = " OR ".join(either)
    return f"{named} AND NOT coalesce(({held}), FALSE)" if others else f"{named} AND ({held})"


def _reacs(meddra: bool) -> str:
    """Each reaction row's key as FDA wrote it (`text_T`) and, with MedDRA, its PT today."""
    text = reaction_key("r.pt")
    if not meddra:
        return (
            f"SELECT {_keys('r')}, r.pt, {text} AS text_T, NULL::VARCHAR AS pt_T, "
            f"NULL::VARCHAR AS pt_name FROM reac_latest_T r WHERE {text} IS NOT NULL"
        )
    return (
        f"SELECT {_keys('r')}, r.pt, {text} AS text_T, lower(p.pt_name) AS pt_T, p.pt_name "
        f"FROM reac_latest_T r LEFT JOIN reac_meddra_T m ON m.reac_term_T = {text} "
        f"LEFT JOIN meddra_pt p ON p.pt_code = m.pt_code_T WHERE {text} IS NOT NULL"
    )


def _either(column: str, given: tuple[str, ...], v: Values) -> str:
    """SQL: the case's `column` is one of `given`, NOT_GIVEN for none."""
    codes = [g for g in given if g != NOT_GIVEN]
    either = [v.among(column, codes)] if codes else []
    if NOT_GIVEN in given:
        either.append(f"{column} IS NULL")
    return f"({' OR '.join(either)})"


def _where(asked: Asked, v: Values, meddra: bool) -> list[str]:
    """Each condition the question puts on case `c`."""
    where = [v.among("c.era_T", asked.eras)]
    if asked.drug or asked.drug_roles:
        named = (
            f"(d.drugname_norm_T = {v.one(asked.drug)} OR d.prod_ai_norm_T = {v.one(asked.drug)})"
            if asked.drug
            else "(d.drugname_norm_T IS NOT NULL OR d.prod_ai_norm_T IS NOT NULL)"
        )
        if asked.drug_roles:
            named += " AND " + v.among("upper(trim(d.role_cod))", asked.drug_roles)
        where.append(_in_cases(f"SELECT {_keys('d')} FROM drug_latest_T d WHERE {named}"))
    for keys in ([asked.reaction] if asked.reaction else [], asked.reactions):
        if keys:
            matched = f"{v.among('r.text_T', keys)} OR {v.among('r.pt_T', keys)}"
            where.append(_in_cases(f"SELECT {_keys('r')} FROM reac_keyed r WHERE {matched}"))
    for column, (low, high) in ((received_day(), asked.received), ("event_dt_T", asked.event)):
        where += [f"c.{column} >= {v.one(low)}"] if low else []
        where += [f"c.{column} <= {v.one(high)}"] if high else []
    where += [_either(f"c.{FIELDS[n]}", g, v) for n, g in asked.fields.items() if g]
    if asked.outcomes:
        gave = "SELECT era_T, primaryid, quarter_T FROM outc_latest_T WHERE outc_cod IS NOT NULL"
        codes = [o for o in asked.outcomes if o != NOT_GIVEN]
        either = [_in_cases(f"{gave} AND {v.among('outc_cod', codes)}")] if codes else []
        either += [f"NOT {_in_cases(gave)}"] if NOT_GIVEN in asked.outcomes else []
        where.append(f"({' OR '.join(either)})")
    if asked.sender == DIRECT:
        where.append(direct_report("c.rept_cod"))
    elif asked.sender == NOT_GIVEN:
        where.append(f"c.company_T IS NULL AND NOT {direct_report('c.rept_cod')}")
    elif asked.sender:  # a company by any of FDA's spellings of it, or its own name
        spelled = (
            "SELECT company_T FROM case_latest_T WHERE company_T IS NOT NULL AND "
            f"(upper(trim(mfr_sndr)) = {v.one(asked.sender)} "
            f"OR upper(company_T) = {v.one(asked.sender)})"
        )
        where.append(f"c.company_T IN ({spelled})")
    # the product, and any one of All cases' drugs
    for group in ([asked.product] if asked.product else [], asked.drugs):
        if group:
            where.append(_in_cases(" UNION ALL ".join(_drug_cases(d, v) for d in group)))
    # the drug records and the report: the product's records, or every record; each written
    # only where a filter reads it, as every value is a parameter the statement must hold
    ours, others = ("TRUE", "TRUE")
    if asked.product:
        if any(asked.records[n] for n in recountrecords.OURS):
            ours = _records(asked.product, v)
        if asked.records["other_drug"]:
            others = _records(asked.product, v, others=True)
    return where + recountrecords.conditions(asked, v, ours, others, meddra)


def statement(opened: OpenRelease, asked: Asked, meddra: bool) -> Statement:
    """The second count of what a question asks, as one statement over the release's tables;
    it reads the reactions only for a count by event or a question choosing reactions."""
    v = Values()
    reacs = asked.by == "event" or bool(
        asked.reaction or asked.reactions or asked.records["other_reaction"]
    )
    items = [f"reac_keyed AS ({_reacs(meddra)})"] if reacs else []
    where = _where(asked, v, meddra)
    labelled = recountlabel.kept(opened, asked, v)
    if labelled is not None:
        items.append(labelled[0])
        where.append(_in_cases(labelled[1]))
    table = CASES[asked.kept_only]
    items.append(f"picked AS (SELECT c.* FROM {table} c WHERE {' AND '.join(where)})")
    if asked.by in recountrecords.FIELDS:
        ours = _records(asked.product, v) if asked.product else "TRUE"
        items.append(f"given AS ({recountrecords.counted_by(asked.by, ours)})")
    licensed = meddra and (reacs or bool(asked.records["indication"]))
    return Statement(asked.by, "WITH " + ",\n".join(items), v.params, licensed)


@dataclass(frozen=True)
class Recount:
    counts: list[list[Any]]  # [value, cases], in the order the first count gives them
    total: int
    statement: Statement = field(repr=False)


class _Connection:
    """The release's tables on a DuckDB connection of its own, held to the explorer's memory
    limit, with the licensed MedDRA part's text to PT link for `meddra`; its spill folder goes
    with it."""

    def __init__(self, opened: OpenRelease, meddra: str | None) -> None:
        self.con = read_connection(self)
        register_release(self.con, opened.folder, temporary=True)
        licensed = version_tables(opened.folder, meddra)
        for name in LICENSED if meddra else ():
            path = quoted(str(licensed[name]))
            self.con.execute(f"CREATE TEMP VIEW {name} AS SELECT * FROM read_parquet({path})")

    def rows(self, sql: str, params: dict[str, Any]) -> list[list[Any]]:
        return [list(r) for r in self.con.execute(sql, params).fetchall()]


def recount(opened: OpenRelease, question: Question, meddra: str | None = None) -> Recount:
    """`question` counted again by its `by`, its reactions by today's PT in MedDRA `meddra`."""
    own = _Connection(opened, meddra)
    try:
        made = statement(opened, recountquery.read(own.con, question), meddra is not None)
        counts = own.rows(made.counts, made.params)
        (total,) = own.rows(made.total, made.params)[0]
    finally:
        own.con.close()
    return Recount(counts, int(total), made)


def _same_value(by: str, found: Any) -> Any:
    """A value as the two counts are matched by: an event by its key, whatever its capitals."""
    return reaction_term(found) if by == "event" and found is not None else found


def unread(question: Question) -> list[str]:
    """The parameters `question` names that the second count does not read."""
    return sorted(name for name in question if name not in READS)


def check(first: dict[str, Any], second: Recount | None, unread: list[str]) -> dict[str, Any]:
    """The first count checked by the second: each value's cases and the question's, whether
    the two agree, and each value they differ on with both counts. A question naming a
    parameter not in READS is not counted again (`unread`, `second` None), and never said to
    agree."""
    if second is None:
        nothing = dict.fromkeys(("counts", "total", "agrees", "differences"))
        return nothing | {"unread": unread}
    by = first["by"]
    theirs = {_same_value(by, v): n for v, n in second.counts}
    ours = {_same_value(by, v): n for v, n, _ in first["counts"]}
    differences = [
        [v, n, theirs.get(_same_value(by, v), 0)]
        for v, n, _ in first["counts"]
        if theirs.get(_same_value(by, v), 0) != n
    ] + [[v, 0, n] for v, n in second.counts if _same_value(by, v) not in ours]
    return {
        "counts": second.counts,
        "total": second.total,
        "agrees": not differences and second.total == first["total"],
        "differences": differences,
        "unread": [],
    }


# a value's name in a statement: $v1, $v2, ... (Values.one)
MARK = re.compile(r"\$(v\d+)\b")


def literal(given: str | date) -> str:
    """A value written in SQL as a constant: text as a quoted string that nothing in it can
    end, a day as a DATE."""
    if isinstance(given, date):
        return f"DATE {quoted(given.isoformat())}"
    return quoted(given)


def sql_of(made: Statement) -> str:
    """The count by `by` as one query that runs as it stands: each value written in where its
    name stands, in one pass, so no value is read as SQL or as another value's name."""
    return MARK.sub(lambda m: literal(made.params[m.group(1)]), made.counts)


__all__ = [
    "READS",
    "Recount",
    "Statement",
    "Values",
    "check",
    "literal",
    "recount",
    "sql_of",
    "statement",
    "unread",
]
