"""The Statistics tab's answers, from the release's statistics (rules ebgm, prr, ror, rrr, ic and
time-to-onset, counted as rule statistics-cases says): what the release holds, one page of its
pairs, for an ingredient or across the release, narrowed by a screen and ordered by a column,
and one pair's ROR within each age band and each sex (rule ror-strata). Where the release holds
the statistics of each WHO class (rule statistics-classes) and the person may see the classes,
the release's list may be of class and reaction pairs at one level (`by=class&level=4`), and an
ingredient's pairs carry its class's EB05 at the level asked for (`level`, the deepest when none
is named).

A screen arrives as `pass=eb05:at_least:2,cases:at_least:3`, each condition a column, a
comparison and a number (open_altio.stats.screen). No value from the query is put into SQL text.
"""

from __future__ import annotations

from typing import Any

from open_altio.faers.explorer_db import CLASS_INGREDIENTS, CLASS_STATISTICS, explorer_statistics
from open_altio.faers.statistics import CLASS_COLUMNS, COLUMNS
from open_altio.rulebook import data_rule, value
from open_altio.stats import screen

from . import labels
from .classes import shown_names
from .explore import Data, Problem, Query, tidy, value_of
from .filters import NOT_GIVEN, age_bands
from .found import found_order_sql

NUMBERS = tuple(c for c in COLUMNS if c not in ("ingredient", "reaction"))
CLASS_RULE = "statistics-classes"
# the class table's numbers, and what each sorts by: a class by WHO's name for it
CLASS_NUMBERS = tuple(c for c in CLASS_COLUMNS if c not in ("class", "level", "reaction"))
CLASS_SORTS = {"class": "c.atc_name_T", "reaction": "s.reaction_T"} | {
    c: f"s.{c}_T" for c in CLASS_NUMBERS
}
# the columns that are each statistic's own, which its screen marks on the tab
OWN = {
    "EBGM": ("expected", "ebgm", "eb05", "eb95"),
    "PRR": ("prr", "chi_square", "chi_square_yates"),
    "ROR": ("ror", "ror_lower", "ror_upper"),
    "RRR": ("rrr",),
    "IC": ("ic", "ic025"),
}
BEFORE = (
    "This release was built before Open Altio worked out statistics. Build it again to see them."
)


def _column(name: str) -> str:
    return f"{name}_T"


AS_PUBLISHED_BEFORE = (
    "This release counted its statistics by MedDRA's current terms only. Build it again to see "
    "them by the reactions as FDA wrote them."
)


def _entry(data: Data) -> dict[str, Any]:
    """The statistics this viewer is given: those counted by current PT where their reactions
    are named so, else those counted by FDA's text, as in a release without MedDRA."""
    entry = data.opened.manifest.get("statistics") or {"present": False, "reason": BEFORE}
    if (
        not entry["present"]
        or data.reactions.version
        or entry.get("reaction_key", "fda_text") == "fda_text"
    ):
        return entry
    return entry.get("as_published") or {"present": False, "reason": AS_PUBLISHED_BEFORE}


def _tables(entry: dict[str, Any]) -> tuple[str, str]:
    """The explorer database's tables of the pairs and of their ROR by stratum."""
    return explorer_statistics(entry["table"]), explorer_statistics(entry["ror_strata"]["table"])


def about(data: Data, query: Query) -> dict[str, Any]:
    """Whether the release holds statistics (and why not), what was counted, the EBGM fit, and
    each statistic in plain words with its presets and where a person's own screen starts."""
    entry = _entry(data)
    if not entry["present"]:
        return {"present": False, "reason": entry["reason"]}
    fit = entry["ebgm"]
    return {
        "present": True,
        "counted": entry["counted"],
        "reaction_key": entry.get("reaction_key", "fda_text"),
        "meddra_version": entry.get("meddra_version"),
        # where reactions are FDA's text for this viewer and not for the release
        **({"line": data.reactions.line} if data.reactions.line else {}),
        "ebgm": {"fitted": fit["fitted"], "prior": fit.get("prior"), "reason": fit.get("reason")},
        "statistics": [
            {
                "id": name,
                "rule": rule,
                "title": data_rule(rule).title,
                "line": data_rule(rule).line,
                "columns": list(OWN[name]),
                "presets": screen.presets(name),
                "start": screen.start(name),
            }
            for name, rule in screen.RULES.items()
        ],
        "cases_rule": {"rule": "statistics-cases", "line": data_rule("statistics-cases").line},
        "shown": int(value("explorer-lists", "statistics_shown")),
        "classes": _classes_about(data),
    }


def _classes(data: Data) -> dict[str, Any] | None:
    """The release's class statistics, where it holds them and the person may see the classes;
    none for a viewer shown reactions as FDA wrote them where they are counted by current PT,
    since they have no set counted by FDA's text (statistics.by_current_pt)."""
    if data.classes is None:
        return None
    entry = data.opened.manifest.get("class_statistics") or {}
    if entry.get("reaction_key") == "meddra_pt" and not data.reactions.version:
        return None
    built = (data.opened.manifest.get("explorer") or {}).get("tables") or {}
    held = entry.get("present") and all(t in built for t in (CLASS_STATISTICS, CLASS_INGREDIENTS))
    return entry if held else None


def classes_held(data: Data) -> bool:
    """Whether the Statistics tab offers the classes' statistics to this person."""
    return _classes(data) is not None


def _classes_about(data: Data) -> dict[str, Any] | None:
    entry = _classes(data)
    if entry is None:
        return None
    return {
        "rule": CLASS_RULE,
        "line": data_rule(CLASS_RULE).line,
        "levels": [
            {
                "level": v["level"],
                "name": v["name"],
                "classes": v["classes"],
                "pairs": v["pairs"],
                "fitted": v["ebgm"]["fitted"],
                "reason": v["ebgm"].get("reason"),
            }
            for v in entry["levels"]
        ],
    }


def _level(data: Data, query: Query) -> tuple[dict[str, Any], dict[str, Any]]:
    """The class statistics and the level asked for (`level`), the deepest when none is named;
    refused where there are none to see."""
    entry = _classes(data)
    if entry is None:
        data.need_classes()
        raise Problem(404, "This release holds no statistics of drug classes.")
    asked = value_of(query, "level")
    levels = {str(v["level"]): v for v in entry["levels"]}
    if asked and asked not in levels:
        raise Problem(400, f"The class level is one of {', '.join(levels)}.")
    return entry, levels[asked] if asked else entry["levels"][-1]


def _screen(text: str) -> list[tuple[str, str, float]]:
    when = []
    for part in filter(None, text.split(",")):
        column, _, rest = part.partition(":")
        comparison, _, number = rest.partition(":")
        try:
            when.append({"column": column, comparison: float(number)})
        except ValueError:
            raise Problem(
                400, f"A condition reads column:comparison:number, not {part!r}."
            ) from None
    try:
        return screen.check(when, NUMBERS)
    except screen.ScreenError as exc:
        raise Problem(400, str(exc)) from None


def pairs(data: Data, query: Query) -> dict[str, Any]:
    """One page of pairs: an ingredient's (`ingredient`), or the release's, whose reaction (or,
    across the release, ingredient) holds `find`, meeting the screen `pass`, ordered by `sort`
    (`dir` asc or desc), from `offset`."""
    entry = _entry(data)
    if not entry["present"]:
        raise Problem(404, entry["reason"])
    if value_of(query, "by") == "class":
        return _class_pairs(data, query)
    by_pt = entry.get("reaction_key") == "meddra_pt"
    pairs_table, _ = _tables(entry)
    ingredient = tidy(value_of(query, "ingredient")).lower()
    find = tidy(value_of(query, "find")).lower()
    sort, order = value_of(query, "sort", "eb05"), value_of(query, "dir", "desc")
    label = labels.on_statistics(data, ingredient, query)  # Label column, Label status, sort
    sorts = (*COLUMNS, labels.SORT) if label else COLUMNS
    if sort not in sorts or order not in ("asc", "desc"):
        raise Problem(400, f"Sort by one of {', '.join(COLUMNS)}, asc or desc.")
    try:
        offset = max(int(value_of(query, "offset", "0")), 0)
    except ValueError:
        raise Problem(400, "The offset is a whole number.") from None
    clause, params = screen.where(_screen(value_of(query, "pass")), _column)
    where, args = [clause], list[Any]()
    args += params
    if ingredient:
        where.append("ingredient_T = ?")
        args.append(ingredient)
    if find:
        where.append(
            "contains(lower(reaction_T), ?)"
            if ingredient
            else "(contains(lower(reaction_T), ?) OR contains(ingredient_T, ?))"
        )
        args += [find] if ingredient else [find, find]
    sql = f"FROM {pairs_table} WHERE {' AND '.join(where)}"
    ordered, by = f"{_column(sort)} {order} NULLS LAST", list[Any]()
    if label:
        counts = label.counts(data, sql, args)
        more, extra = label.where()
        sql, args = f"{sql} AND {more}", [*args, *extra]
        if sort == labels.SORT:
            ordered, by = label.order(order)
    if find:  # the pairs named as typed first, then those starting so, each in the sort's order
        named = ["lower(reaction_T)"] if ingredient else ["lower(reaction_T)", "ingredient_T"]
        first, first_args = found_order_sql(find, *named)
        ordered, by = f"{first}, {ordered}", [*first_args, *by]
    shown = int(value("explorer-lists", "statistics_shown"))
    rows = data.rows(
        f"SELECT * {sql} ORDER BY {ordered}, ingredient_T, reaction_T LIMIT ? OFFSET ?",
        [*args, *by, shown, offset],
    )
    [matched] = data.rows(f"SELECT count(*) AS n {sql}", args)
    out = {
        "ingredient": ingredient or None,
        "matched": matched["n"],
        "offset": offset,
        "rows": [_row(data, r, by_pt) for r in rows],
    }
    if label:
        for row in out["rows"]:
            row["label"] = label.flag(row["term"])
        out["label"] = {"labels": label.labels, "counts": counts}
    if ingredient and _classes(data) is not None:
        out["class"] = _beside(data, query, ingredient, out["rows"])
    return out


def _beside(
    data: Data, query: Query, ingredient: str, rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The ingredient's class at the level asked for, the one most of its counted cases name,
    and its EB05 with each row's reaction (`class_eb05`); None where it has no class there."""
    _, level = _level(data, query)
    found = data.rows(
        f"SELECT class_T FROM {CLASS_INGREDIENTS} WHERE ingredient_T = ? AND level_T = ? "
        "ORDER BY cases_T DESC, class_T LIMIT 1",
        [ingredient, level["level"]],
    )
    if not found:
        return None
    code = found[0]["class_T"]
    eb05 = {
        r["reaction_T"]: r["eb05_T"]
        for r in data.rows(
            f"SELECT reaction_T, eb05_T FROM {CLASS_STATISTICS} WHERE level_T = ? AND class_T = ? "
            "AND list_contains(?::VARCHAR[], reaction_T)",
            [level["level"], code, [r["term"] for r in rows]],
        )
    }
    for row in rows:
        row["class_eb05"] = eb05.get(row["term"])
    name = shown_names(data, [code]).get(code, code)
    return {"code": code, "name": name, "level": level["level"], "level_name": level["name"]}


def _class_pairs(data: Data, query: Query) -> dict[str, Any]:
    """One page of the class and reaction pairs at one level, as `pairs` gives the release's."""
    entry, level = _level(data, query)
    by_pt = entry.get("reaction_key") == "meddra_pt"
    find = tidy(value_of(query, "find")).lower()
    sort, order = value_of(query, "sort", "eb05"), value_of(query, "dir", "desc")
    if sort not in CLASS_SORTS or order not in ("asc", "desc"):
        raise Problem(400, f"Sort by one of {', '.join(CLASS_SORTS)}, asc or desc.")
    try:
        offset = max(int(value_of(query, "offset", "0")), 0)
    except ValueError:
        raise Problem(400, "The offset is a whole number.") from None
    clause, params = screen.where(_screen(value_of(query, "pass")), lambda c: f"s.{_column(c)}")
    where = [clause, "s.level_T = ?"]
    args: list[Any] = [*params, level["level"]]
    if find:
        where.append(
            "(contains(lower(s.reaction_T), ?) OR contains(lower(c.atc_name_T), ?) "
            "OR starts_with(lower(s.class_T), ?))"
        )
        args += [find, find, find]
    sql = (
        f"FROM {CLASS_STATISTICS} s JOIN explorer_atc_class_T c ON c.atc_code_T = s.class_T "
        f"WHERE {' AND '.join(where)}"
    )
    ordered, by = f"{CLASS_SORTS[sort]} {order} NULLS LAST", list[Any]()
    if find:  # the pairs named as typed first, then those starting so, each in the sort's order
        first, by = found_order_sql(find, "lower(s.reaction_T)", "lower(c.atc_name_T)")
        ordered = f"{first}, {ordered}"
    shown = int(value("explorer-lists", "statistics_shown"))
    rows = data.rows(
        f"SELECT s.* {sql} ORDER BY {ordered}, s.class_T, s.reaction_T LIMIT ? OFFSET ?",
        [*args, *by, shown, offset],
    )
    [matched] = data.rows(f"SELECT count(*) AS n {sql}", args)
    names = shown_names(data, sorted({r["class_T"] for r in rows}))
    out = []
    for r in rows:
        row = {name: r[_column(name)] for name in CLASS_COLUMNS}
        row["class_name"] = names.get(row["class"], row["class"])
        row["term"] = row["reaction"]
        if not by_pt:
            row["reaction"] = data.pt_name(row["reaction"])
        out.append(row)
    return {
        "by": "class",
        "level": level["level"],
        "matched": matched["n"],
        "offset": offset,
        "rows": out,
    }


def _row(data: Data, row: dict[str, Any], by_pt: bool) -> dict[str, Any]:
    out = {name: row[_column(name)] for name in COLUMNS}
    out["term"] = out["reaction"]  # the reaction as a filter names it
    if not by_pt:  # a preferred term is already named as MedDRA writes it
        out["reaction"] = data.pt_name(out["reaction"])
    return out


# Each part's values in the order the explorer lists them (rules age-bands, sex-codes).
ORDER = {
    "age_band": lambda: [b["id"] for b in age_bands()],
    "sex": lambda: list(value("sex-codes", "known")),
}


def strata(data: Data, query: Query) -> dict[str, Any]:
    """The pair of `ingredient` and `reaction` (as the pairs name it, `term`): its ROR within each
    value of each part, every value listed, with no case and an empty ROR where the pair has
    none there. A value not given is NOT_GIVEN, as the filters name it."""
    entry = _entry(data)
    if not entry["present"]:
        raise Problem(404, entry["reason"])
    pairs_table, strata_table = _tables(entry)
    ingredient = tidy(value_of(query, "ingredient")).lower()
    reaction = value_of(query, "reaction")
    rows = data.rows(
        f"SELECT * FROM {strata_table} WHERE ingredient_T = ? AND reaction_T = ?",
        [ingredient, reaction],
    )
    [pair] = data.rows(
        f"SELECT count(*) AS n, any_value(cases_T) AS cases FROM {pairs_table} "
        "WHERE ingredient_T = ? AND reaction_T = ?",
        [ingredient, reaction],
    )
    if not pair["n"]:
        raise Problem(404, "The statistics name no such pair.")
    found = {(r["by_T"], r["stratum_T"]): r for r in rows}
    unknown = value("statistics-cases", "unknown")
    out = []
    for part in entry["ror_strata"]["by"]:
        shown = []
        for v in [*ORDER[part](), unknown]:
            r = found.get((part, v), {})
            shown.append(
                {
                    "stratum": NOT_GIVEN if v == unknown else v,
                    "cases": r.get("cases_T", 0),
                    **{k: r.get(f"{k}_T") for k in ("ror", "ror_lower", "ror_upper")},
                }
            )
        out.append({"by": part, "strata": shown})
    by_pt = (
        entry.get("reaction_key") == "meddra_pt"
    )  # a preferred term is named as MedDRA writes it
    return {
        "ingredient": ingredient,
        "reaction": reaction if by_pt else data.pt_name(reaction),
        "term": reaction,
        "cases": pair["cases"],
        "parts": out,
    }
