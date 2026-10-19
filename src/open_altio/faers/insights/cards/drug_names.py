"""The insight cards of notebook 05 (drug names): what FDA's drug names do
to a count, measured on the release with its drug-name step.

Each function is one card; its name is the card id. A drug record's
ingredients are `drug_ingredient_T` (one row per record and ingredient) and
`drug_substance_T`; cases are the default case set (`case_latest_T` where
`dup_kept_T`), and a drug counts as a suspect when FDA codes it PS or SS. A
release built without the drug-name step has no such tables: each card then
says so plainly, with no data, and its tag says nothing was transformed.
"""

from __future__ import annotations

import duckdb

from open_altio.faers.reader import quoted

from . import common

NB05 = "notebooks/faers/05_drug_names.ipynb"
STEP = "drug_names"
RULE = "drug-names"  # the rule these cards are the evidence for
SUSPECT = ("PS", "SS")
_SUSPECT = ", ".join(quoted(r) for r in SUSPECT)
_KEY = "era_T, primaryid, quarter_T, drug_seq"
BRAND, INGREDIENT = "HUMIRA", "adalimumab"  # one medicine many spell, and its ingredient
BACKGROUND = (
    "famotidine",
    "omeprazole",
    "paracetamol",
    "adalimumab",
)  # three taken alongside, one suspected
REBRANDED = ("ZANTAC", ("ranitidine", "famotidine"))  # a brand whose ingredient changed


def _built(con: duckdb.DuckDBPyConnection) -> bool:
    """Whether the release carries the drug-name step's tables."""
    [(have,)] = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'drug_ingredient_T'"
    ).fetchall()
    return bool(have)


def _absent(card_id: str, shows: str) -> dict:
    """The card of a release built without the DiAna dictionary: no data, and why."""
    return common.card(
        card_id,
        "This release does not read drug names to their ingredients",
        "It was built without the DiAna dictionary, so it carries no drug ingredients. Built with "
        f"it (open-altio fetch, then open-altio build), this card shows {shows}.",
        common.chart("stacked_bar", "", "category", [], "", "count", []),
        common.DOCUMENTED,
        NB05,
    )


def one_medicine_many_spellings(con: duckdb.DuckDBPyConnection) -> dict:
    """FDA publishes each drug name as typed, so one medicine has hundreds of
    spellings and a search for its brand misses the rest. Changed our pipeline:
    every record carries its ingredients (rules/drug-names.md)."""
    if not _built(con):
        return _absent("one_medicine_many_spellings", "how many spellings one medicine has")
    brand, generic, other, every = (
        f"A name with {BRAND}",
        f"A name with {INGREDIENT.upper()}",
        "Another name: biosimilar brands and others",
        f"Any name: the ingredient {INGREDIENT}",
    )
    rows = common.query(
        con,
        f"""
        WITH every_role AS (
          SELECT c.case_key_T, d.drugname, upper(d.drugname) AS name_T,
                 d.role_cod IN ({_SUSPECT}) AS suspect_T
          FROM drug_ingredient_T i JOIN drug_latest_T d USING ({_KEY})
          JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
          WHERE i.ingredient_T = ? AND c.dup_kept_T),
        d AS (SELECT * FROM every_role WHERE suspect_T)
        SELECT CASE WHEN contains(name_T, ?) THEN {quoted(brand)}
                    WHEN contains(name_T, ?) THEN {quoted(generic)}
                    ELSE {quoted(other)} END, count(DISTINCT case_key_T) FROM d GROUP BY 1
        UNION ALL SELECT {quoted(every)}, count(DISTINCT case_key_T) FROM d
        UNION ALL SELECT 'spellings', count(DISTINCT drugname) FROM every_role""",
        [INGREDIENT, BRAND, INGREDIENT.upper()],
    )
    got = dict(rows)
    xs = [brand, generic, other, every]
    chart = common.chart(
        "stacked_bar",
        "Which drug names are searched",
        "category",
        xs,
        "Cases with it as a suspect drug",
        "count",
        common.series([(x, "Cases", got.get(x)) for x in xs], xs, ["Cases"]),
        question=f"How many {INGREDIENT} cases does a search for its brand name find?",
    )
    total, found = got.get(every, 0), got.get(brand, 0)
    return common.card(
        "one_medicine_many_spellings",
        f"One medicine is written hundreds of ways: {INGREDIENT} under "
        f"{got.get('spellings', 0):,} spellings",
        f"FDA publishes each drug name as the reporter typed it, so {INGREDIENT} reaches FAERS "
        f"as {BRAND}, {INGREDIENT.upper()}, misspellings and every biosimilar brand. A search "
        f"for {BRAND.lower()} finds {found:,} of the {common.plural(total, 'case')} with "
        f"{INGREDIENT} as a suspect ({common.pct(found, total)}); searching by ingredient finds "
        "them all.",
        chart,
        common.changed(STEP, RULE),
        NB05,
    )


def background_drugs_counted_every_role(con: duckdb.DuckDBPyConnection) -> dict:
    """A report lists the drugs the patient also took (concomitant, C) beside
    the suspect ones (PS, SS). Counting every role turns a medicine many people
    take into a frequent suspect. Changed our pipeline: ingredients are counted
    by record, and the role of each record stays FDA's (rules/drug-names.md)."""
    if not _built(con):
        return _absent(
            "background_drugs_counted_every_role", "what counting every drug role does to a count"
        )
    suspect, other = (
        "As a suspect drug (PS or SS)",
        "Only in another role (concomitant or interacting)",
    )
    names = ", ".join(quoted(n) for n in BACKGROUND)
    rows = common.query(
        con,
        f"""
        WITH d AS (
          SELECT i.ingredient_T, c.case_key_T, bool_or(d.role_cod IN ({_SUSPECT})) AS suspect_T
          FROM drug_ingredient_T i JOIN drug_latest_T d USING ({_KEY})
          JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
          WHERE i.ingredient_T IN ({names}) AND c.dup_kept_T GROUP BY ALL)
        SELECT ingredient_T,
               CASE WHEN suspect_T THEN {quoted(suspect)} ELSE {quoted(other)} END, count(*)
        FROM d GROUP BY ALL""",
    )
    # records, not rows: FDA writes some records on one row per dose
    share = common.query(
        con,
        f"""SELECT count(*) FILTER (WHERE role_cod = 'C'), count(*)
            FROM (SELECT {_KEY}, any_value(role_cod) AS role_cod
                  FROM drug_latest_T GROUP BY ALL)""",
    )
    concomitant, drugs = share[0] if share else (0, 0)
    xs = list(BACKGROUND)
    series = common.series(rows, xs, [suspect, other])
    cell = {(x, s): v for x, s, v in rows}
    first = BACKGROUND[0]
    as_suspect, every = (
        cell.get((first, suspect), 0),
        cell.get((first, suspect), 0) + cell.get((first, other), 0),
    )
    chart = common.chart(
        "stacked_bar",
        "Ingredient",
        "category",
        xs,
        "Cases in the default case set",
        "count",
        series,
        question="How much of an ingredient's count is patients who only took it alongside "
        "the suspect drug?",
    )
    times = every / as_suspect if as_suspect else 0
    return common.card(
        "background_drugs_counted_every_role",
        f"Counted in every role, {first} has {times:.0f} times its suspect cases",
        f"{common.pct(concomitant, drugs)} of FAERS drug records are concomitant: medicines the "
        f"patient also took, not the one suspected. {first.capitalize()} is a suspect drug in "
        f"{common.plural(as_suspect, 'case')} but appears in {every:,}, so a count over every role "
        "mostly measures how many patients take it.",
        chart,
        common.changed(STEP, RULE),
        NB05,
    )


def brand_changes_ingredient(con: duckdb.DuckDBPyConnection) -> dict:
    """A brand name can be sold with another ingredient: after ranitidine was
    withdrawn in 2020, Zantac 360 is famotidine. Changed our pipeline: each
    spelling is read to the ingredient it names (rules/drug-names.md)."""
    if not _built(con):
        return _absent("brand_changes_ingredient", "a brand that changed its ingredient")
    brand, (old, new) = REBRANDED
    name = brand.capitalize()
    none = "No ingredient found"
    rows = common.query(
        con,
        f"""
        SELECT c.init_year_T, coalesce(s.substance_T, {quoted(none)}) AS what_T,
               count(DISTINCT c.case_key_T)
        FROM drug_substance_T s JOIN drug_latest_T d USING ({_KEY})
        JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
        WHERE contains(upper(d.drugname), ?) AND c.dup_kept_T GROUP BY ALL""",
        [brand],
    )
    xs = sorted({r[0] for r in rows if r[0] is not None and r[0] >= common.FIRST_YEAR})
    kept = [r for r in rows if r[1] in (old, new, none) and r[0] in xs]
    series = common.zeros(common.series(kept, xs, [old, new, none]))
    totals = {k: sum(n for _, w, n in kept if w == k) for k in (old, new)}
    first_new = min((y for y, w, n in kept if w == new and n), default=None)
    chart = common.chart(
        "stacked_bar",
        "Year FDA first received the case",
        "year",
        xs,
        f"Cases naming {brand.capitalize()}",
        "count",
        series,
        question=f"Which ingredient do the reports that name {brand.capitalize()} carry?",
        note=(first_new, f"{brand.capitalize()} 360, {new}") if first_new else None,
    )
    return common.card(
        "brand_changes_ingredient",
        f"One brand, two ingredients: {name} was {old}, {name} 360 is {new}",
        f"After {old} was withdrawn in 2020 the {name} name came back as {name} 360, "
        f"which is {new}. Of the cases naming {name}, {totals[old]:,} carry {old} and "
        f"{totals[new]:,} {new}, so a search for the brand mixes two medicines and a search "
        "by ingredient does not.",
        chart,
        common.changed(STEP, RULE),
        NB05,
    )
