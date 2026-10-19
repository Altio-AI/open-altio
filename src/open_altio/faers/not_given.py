"""What reads Not given (rule not-given): a value that is blank, says unknown or is a filler
number, or a column FDA's file did not have that quarter. The duplicate key, the case window and
the release's company names all ask here, so they read one empty state. FDA's own values are
never changed.

    from open_altio.faers import not_given
    not_given.check("route", "d.route")     # SQL: true when d.route reads Not given
    not_given.given("route", "d.route")     # SQL: d.route, or NULL where it reads Not given

Sex and country are read by their own rules (rules/sex-codes.md, rules/country-not-given.md):
sex_T and country_T are empty where they give none, and nothing here reads them again.
"""

from __future__ import annotations

from collections.abc import Iterable

from open_altio import rulebook

from .reader import quoted, sql_in

RULE = "not-given"
# a value made only of these is blank
_SPACES = "' ' || chr(9) || chr(10) || chr(13)"


def label() -> str:
    return rulebook.value(RULE, "label")


def fields() -> dict[str, dict]:
    """Each field read for more than blank, with what reads Not given in it."""
    return rulebook.value(RULE, "fields")


def _words(v: str, glue_list: str) -> str:
    unknown = "|".join(rulebook.value(RULE, "unknown_words"))
    glue = "|".join(rulebook.value(RULE, glue_list))
    return (
        f"(regexp_replace({v}, '({unknown}|{glue}|[^A-Z0-9])', '', 'g') = '' "
        f"AND regexp_matches({v}, '({unknown})') "
        f"OR {sql_in(v, rulebook.value(RULE, 'unknown_alone'))})"
    )


def check(
    field: str, expr: str | None = None, *, quarter: str = "quarter_T", report: str = "rept_cod"
) -> str:
    """SQL: true when `field`, held in `expr` (by default a column of the field's name), reads
    Not given. `quarter` and `report` are the row's quarter_T and its case's rept_cod, which some
    fields are read by."""
    e = expr or field
    v = f"upper(trim({e}))"
    parts = [f"{e} IS NULL", f"trim({e}, {_SPACES}) = ''"]
    how = fields().get(field, {})
    if "codes" in how:
        parts.append(sql_in(v, how["codes"]))
    if how.get("words"):
        parts.append(_words(v, how.get("glue", "glue_words")))
    if how.get("no_drug_names"):
        parts.append(sql_in(v, rulebook.value("no-drug-or-reaction", "unusable_drug_names")))
    if "filler" in how:
        pattern = rulebook.value(RULE, "fillers")[how["filler"]]
        parts.append(f"regexp_full_match(trim({e}), {quoted(pattern)})")
    if "codes_in_quarters" in how:
        q = how["codes_in_quarters"]
        within = f"{quarter} BETWEEN {quoted(q['from'])} AND {quoted(q['to'])}"
        parts.append(f"({sql_in(v, q['codes'])} AND {within})")
    if "only_report_types" in how:
        read_on = sql_in(f"upper(trim({report}))", how["only_report_types"])
        parts.append(f"NOT coalesce({read_on}, false)")
    return "(" + " OR ".join(parts) + ")"


def given(field: str, expr: str | None = None, value: str | None = None, **context: str) -> str:
    """SQL: `value` (by default the field itself), or NULL where the field reads Not given."""
    return f"CASE WHEN {check(field, expr, **context)} THEN NULL ELSE {value or expr or field} END"


def named(columns: Iterable[str], alias: str, **context: str) -> str:
    """SQL: the names of those of `columns`, in the row `alias`, the rule reads and that read Not
    given."""
    each = [
        f"CASE WHEN {check(c, f'{alias}.{c}', **context)} THEN {quoted(c)} END"
        for c in columns
        if c in fields()
    ]
    return f"list_filter([{', '.join(each)}]::VARCHAR[], x -> x IS NOT NULL)"


__all__ = ["RULE", "check", "fields", "given", "label", "named"]
