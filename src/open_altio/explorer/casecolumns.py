"""More of each case on a page of the case list (/api/cases), and the orders the list sorts by.

    columns(data, sc, found, events)  with `detail=columns` on a product's page: each case's
                                      `columns_T`, what the case gives about the drug
    order(query, sc, where)           the join a `sort` needs, its parameters and its ORDER BY

The drug's own records in a case are those the page counts (`Unit.records`), first by FDA's role
order (rule explorer-drug-counts) and then by FDA's drug sequence, as an event's breakdowns read
them (breakdowns/fields.py): its role, time to onset, dechallenge and rechallenge are those of
its first record that gives one; its doses, routes, dose forms, lots and what it was taken for
are every value its records give, as written, a value that reads Not given (rule not-given) left
out; its therapy start is the earliest day any record gives and its stop the latest, each with
how far FDA gives it. The suspect drugs are the drug's own records, then the case's other drugs
in the roles the page counts. The other reactions are the case's reactions besides the event's,
by the key a reaction counts under (reactions.py).

Each order sorts two ways (`onset`, `onset-asc`) and a case that gives no value sorts last both
ways; ties go to the newest received first. An order read from the drug's records needs a
product, and a sort the list does not know is newest first. No value from the query is put into
SQL text.
"""

from __future__ import annotations

from typing import Any

from open_altio.faers import not_given
from open_altio.rulebook import value

from . import drugs
from .explore import Data, Query, Scope, value_of

TIE = "c.group_first_dt_T DESC NULLS LAST, c.case_id_T"
# the case's most serious outcome, by its place in rule serious-outcomes' list
WORST = "list_min(list_transform(c.outcomes_T, x -> list_position(?::VARCHAR[], x)))"
CASE_ORDER: dict[str, str] = {
    "newest": "c.group_first_dt_T DESC NULLS LAST, c.case_id_T",
    "oldest": "c.group_first_dt_T ASC NULLS LAST, c.case_id_T",
    "age": "c.age_years_T DESC NULLS LAST, c.case_id_T",
    "age-asc": "c.age_years_T ASC NULLS LAST, c.case_id_T",
    "case": f"TRY_CAST(c.case_key_T AS BIGINT) DESC NULLS LAST, {TIE}",
    "case-asc": f"TRY_CAST(c.case_key_T AS BIGINT) ASC NULLS LAST, {TIE}",
    "event": f"c.event_dt_T DESC NULLS LAST, {TIE}",
    "event-asc": f"c.event_dt_T ASC NULLS LAST, {TIE}",
    "sex": f"CASE c.sex_T WHEN 'F' THEN 0 WHEN 'M' THEN 1 END ASC NULLS LAST, {TIE}",
    "sex-asc": f"CASE c.sex_T WHEN 'M' THEN 0 WHEN 'F' THEN 1 END ASC NULLS LAST, {TIE}",
    "weight": f"c.wt_kg_T DESC NULLS LAST, {TIE}",
    "weight-asc": f"c.wt_kg_T ASC NULLS LAST, {TIE}",
    # health professionals first: rule reporter-type numbers a physician 1 and a consumer 5
    "reporter": f"c.reporter_type_T ASC NULLS LAST, {TIE}",
    "reporter-asc": f"c.reporter_type_T DESC NULLS LAST, {TIE}",
    "serious": f"{WORST} ASC NULLS LAST, {TIE}",
    "serious-asc": f"{WORST} DESC NULLS LAST, {TIE}",
}
# the records in a drug's order: FDA's roles in the rule's order, then its drug sequence
RANK = "list_position(?::VARCHAR[], d.role_T), try_cast(d.drug_seq AS BIGINT), d.drug_seq"
# FDA's dechallenge codes in each of its orders: positive first, or negative first
DECHAL_ORDERS = {"": ["Y", "N", "D", "U"], "asc": ["N", "Y", "D", "U"]}
THERAPY = "JOIN explorer_ther_T t ON t.case_id_T = d.case_id_T AND t.dsg_drug_seq = d.drug_seq"
INDICATION = "JOIN explorer_indi_T i ON i.case_id_T = d.case_id_T AND i.indi_drug_seq = d.drug_seq"
# the orders read from the drug's records: the value a case sorts by, over its records `d` and
# its case `k` (with `t` its therapy rows or `i` its indications where joined); whether the first
# choice puts the largest first; whether it reads every record in the roles counted, not only the
# drug's own
RECORD_ORDER: dict[str, tuple[str, str, bool, bool]] = {
    "onset": (
        f"first(d.time_to_onset_T ORDER BY {RANK}) FILTER (WHERE d.time_to_onset_T IS NOT NULL)",
        "", True, False,
    ),
    "role": ("min(list_position(?::VARCHAR[], d.role_T))", "", False, False),
    "drugs": ("count(DISTINCT d.drug_seq)", "", True, True),
    "indication": (
        "min(lower(coalesce(i.indi_pt_spelling_T, trim(i.indi_pt)))) FILTER "
        f"(WHERE {not_given.given('indi_pt', 'i.indi_pt')} IS NOT NULL)",
        INDICATION, False, False,
    ),
    "start": ("min(t.start_dt_T)", THERAPY, True, False),
    "stop": ("max(t.end_dt_T)", THERAPY, True, False),
}  # fmt: skip
WRITTEN = {"dose": "dose_vbm", "route": "route", "dose_form": "dose_form", "lot": "lot_num"}


def _given(field: str, expr: str) -> str:
    """SQL: `expr`, or NULL where it reads Not given; read by its case's quarter and report."""
    return not_given.given(field, expr, quarter="k.quarter_T", report="k.rept_cod")


def _code(field: str) -> str:
    return f"upper(trim({_given(field, f'd.{field}')}))"


def _written(field: str) -> str:
    """SQL: a field as written, its runs of spaces made one, or NULL where it reads Not given."""
    return f"regexp_replace(trim({_given(field, f'd.{field}')}), '[[:space:]]+', ' ', 'g')"


def _marks(values: list[Any]) -> str:
    return ", ".join("?" for _ in values)


# a page's cases, with more of each ---------------------------------------------------------------


def columns(data: Data, sc: Scope, found: list[dict], events: set[str]) -> None:
    """Each case of `found` with its `columns_T` (this module's docstring), null off a product's
    page; `events` are the keys of the event's reactions."""
    unit = sc.product
    if unit is None or not found:
        for c in found:
            c["columns_T"] = None
        return
    ids = [c["case_id_T"] for c in found]
    ours, ours_params = unit.records("d")
    within = f"d.case_id_T IN ({_marks(ids)})"
    words = ", ".join(f"{_written(column)} AS {name}" for name, column in WRITTEN.items())
    records = data.rows(
        f"SELECT d.case_id_T AS id, d.drugname AS name, d.role_T AS role, ({ours}) AS ours, "
        f"{words}, {_code('dechal')} AS dechal, {_code('rechal')} AS rechal, "
        "d.time_to_onset_T AS onset, d.time_to_onset_reason_T AS onset_why "
        "FROM explorer_drug_T d JOIN explorer_case_T k ON k.case_id_T = d.case_id_T "
        f"WHERE {within} AND d.role_T IN ({_marks(list(unit.roles))}) ORDER BY d.case_id_T, {RANK}",
        [*ours_params, *ids, *unit.roles, drugs.roles()],
    )
    indications = data.rows(
        "SELECT DISTINCT d.case_id_T AS id, coalesce(i.indi_pt_spelling_T, trim(i.indi_pt)) AS v "
        f"FROM explorer_drug_T d {INDICATION} WHERE {within} AND {ours} "
        f"AND {not_given.given('indi_pt', 'i.indi_pt')} IS NOT NULL ORDER BY 1, 2",
        [*ids, *ours_params],
    )
    therapy = data.rows(
        "SELECT d.case_id_T AS id, t.start_dt_T AS s, t.start_dt_prec_T AS sp, t.end_dt_T AS e, "
        f"t.end_dt_prec_T AS ep FROM explorer_drug_T d {THERAPY} WHERE {within} AND {ours}",
        [*ids, *ours_params],
    )
    held = {i: Held() for i in ids}
    for r in records:
        held[r["id"]].record(r)
    for r in indications:
        held[r["id"]].once("indication", r["v"])
    for r in therapy:
        held[r["id"]].therapy(r)
    for c in found:
        c["columns_T"] = held[c["case_id_T"]].answer(_others(data, c["reactions"], events))


class Held:
    """What one case gives about the drug, gathered record by record in the drug's order."""

    def __init__(self) -> None:
        self.cols: dict[str, Any] = {
            "suspects": [], "role": None, "onset": None, "onset_why": None, "dechal": None,
            "rechal": None, "dose": [], "route": [], "dose_form": [], "lot": [],
            "indication": [], "start": None, "stop": None,
        }  # fmt: skip
        self.seen: set[tuple[str, str, bool]] = set()

    def once(self, name: str, v: str | None) -> None:
        if v and v not in self.cols[name]:
            self.cols[name].append(v)

    def record(self, r: dict[str, Any]) -> None:
        named = (r["name"], r["role"], bool(r["ours"]))
        if named not in self.seen:
            self.seen.add(named)
            self.cols["suspects"].append(list(named))
        if not r["ours"]:
            return
        cols = self.cols
        if cols["role"] is None:
            cols["role"] = r["role"]
            # a drug with no time to onset says why on its first record (rule time-to-onset)
            cols["onset_why"] = r["onset_why"]
        for name in ("onset", "dechal", "rechal"):
            if cols[name] is None and r[name] is not None and r[name] != "":
                cols[name] = r[name]
        for name in WRITTEN:
            self.once(name, r[name])

    def therapy(self, r: dict[str, Any]) -> None:
        """The earliest start and the latest stop any of the drug's therapy rows gives."""
        start, stop = self.cols["start"], self.cols["stop"]
        if r["s"] is not None and (start is None or str(r["s"]) < start[0]):
            self.cols["start"] = [str(r["s"]), r["sp"]]
        if r["e"] is not None and (stop is None or str(r["e"]) > stop[0]):
            self.cols["stop"] = [str(r["e"]), r["ep"]]

    def answer(self, others: list[str]) -> dict[str, Any]:
        # the drug's own records first, then the others, each in the drug order
        self.cols["suspects"].sort(key=lambda s: not s[2])
        return self.cols | {"other_reaction": others}


def _others(data: Data, reactions: list[str], events: set[str]) -> list[str]:
    """The case's reactions besides the event's, each once, as a page names them."""
    out: list[str] = []
    for text in reactions:
        key = data.reactions.key_of(text)
        named = data.pt_name(key) or text
        if key not in events and named not in out:
            out.append(named)
    return out


# the orders --------------------------------------------------------------------------------------


Order = tuple[str, list, str, list]


def order(query: Query, sc: Scope, where: tuple[str, list]) -> Order:
    """The join `sort` needs ('' for none) with its parameters, and the ORDER BY with its
    parameters; `where` is the question's condition over `explorer_case_T c`."""
    sort = value_of(query, "sort", "newest")
    if sort in CASE_ORDER:
        serious = [list(value("serious-outcomes", "serious"))]
        return "", [], CASE_ORDER[sort], serious * CASE_ORDER[sort].count("?")
    which, _, way = sort.partition("-")
    unit = sc.product
    if unit is None or way not in DECHAL_ORDERS or which not in (*RECORD_ORDER, "dechal"):
        return "", [], CASE_ORDER["newest"], []
    rows, rows_params = unit.records("d")
    if which == "dechal":
        code = _code("dechal")
        expr = (
            f"list_position(?::VARCHAR[], first({code} ORDER BY {RANK}) "
            f"FILTER (WHERE {code} IS NOT NULL))"
        )
        expr_params: list[Any] = [DECHAL_ORDERS[way], drugs.roles()]
        joined, desc = "", False
    else:
        expr, joined, largest_first, every = RECORD_ORDER[which]
        expr_params = [drugs.roles()] if "?" in expr else []
        desc = largest_first != (way == "asc")
        if every:
            rows, rows_params = f"d.role_T IN ({_marks(list(unit.roles))})", list(unit.roles)
    sql, params = where
    join = (
        f"LEFT JOIN (SELECT d.case_id_T AS sort_id, {expr} AS sort_v FROM explorer_drug_T d "
        f"JOIN explorer_case_T k ON k.case_id_T = d.case_id_T {joined} WHERE {rows} AND "
        f"d.case_id_T IN (SELECT c.case_id_T FROM explorer_case_T c WHERE {sql}) GROUP BY 1) s "
        "ON s.sort_id = c.case_id_T"
    )
    direction = "DESC" if desc else "ASC"
    return (
        join,
        [*expr_params, *rows_params, *params],
        f"s.sort_v {direction} NULLS LAST, {TIE}",
        [],
    )


__all__ = ["CASE_ORDER", "DECHAL_ORDERS", "RECORD_ORDER", "Order", "columns", "order"]
