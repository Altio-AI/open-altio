"""The numbers the methods story shows that the rest of the release does not carry: how each part
of a case is read one way (dates, ages, reporters, empty routes) and the counts on the paths to an
answer (drug names, RxNorm codes, routes, reaction terms, WHO classes, the statistics' screens),
and those "What we do not do" quotes. Every count is over the cases the release shows
(case_latest_T where dup_kept_T) and their drug and reaction rows. The page's words around them
are read at serve time, never written here; only "What we do not do" is filled here with them.

    from open_altio.faers.insights import numbers
    numbers.write(release_dir)  # methods.json's `numbers`, `limits` and `rule_versions`, and
                                # the licensed manifest's `numbers`, from the release's own tables

The build runs `write` last, on the release it has just written, and `python -m open_altio.faers
methods` runs it on a release already built, so both give the same files. A part whose tables the
release lacks (built without the drug names, RxNorm, the classes or MedDRA) is left out.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import duckdb

from open_altio import rulebook
from open_altio.faers import not_given
from open_altio.faers.drugnames.substances import UNMAPPED
from open_altio.faers.meddra import licensed_dir, read_licensed_manifest
from open_altio.faers.meddra.licensed import LICENSED_MANIFEST
from open_altio.faers.reader import quoted, read_manifest, register_release
from open_altio.stats import screen

from .cards.meddra import _REACTIONS as REACTIONS
from .methods import MethodsError, fill_limits, rule_versions, validate

# the release's tables the numbers read, where it has them
TABLES = ("case_latest_T", "drug_latest_T", "reac_latest_T", "drug_route_T", "drug_substance_T",
          "drug_ingredient_T", "drug_rxnorm_T", "atc_drug_T", "atc_index_T", "statistics_T",
          "label_candidates_T", "label_other_drug_T")  # fmt: skip
# what the label step leaves once it has flagged the release's drug records
FLAGGED = ("drug_substance_T", "drug_rxnorm_T", "label_candidates_T", "label_other_drug_T")
MEDDRA_TABLES = ("reac_meddra_T",)
KEY = "era_T, primaryid, quarter_T"
DRUG_KEY = f"{KEY}, drug_seq"
SHOWN = f"(SELECT {KEY} FROM case_latest_T WHERE dup_kept_T)"
# a value made only of these is blank (as rule not-given reads one)
SPACES = "' ' || chr(9) || chr(10) || chr(13)"
# FDA's date written as a full day, a month or a year, by its digits; precision as read
DIGITS = {8: "day", 6: "month", 4: "year"}


def _has(con: duckdb.DuckDBPyConnection, *tables: str) -> bool:
    names = ", ".join(f"'{t}'" for t in tables)
    [(n,)] = con.execute(
        f"SELECT count(DISTINCT table_name) FROM information_schema.tables "
        f"WHERE table_name IN ({names})"
    ).fetchall()
    return n == len(tables)


def _suspect(
    alias: str = "d", rule: str = "explorer-drug-counts", key: str = "default_roles"
) -> str:
    """SQL: true for a drug row in a suspect role: the roles a drug's count takes by default
    (explorer-drug-counts), or those `rule`'s `key` names."""
    roles = ", ".join(f"'{r}'" for r in rulebook.value(rule, key))
    return f"upper(trim({alias}.role_cod)) IN ({roles})"


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def _tally(rows: list[tuple]) -> dict[str, int]:
    """(value, count) rows as {value: count}, largest first."""
    return {str(v): int(n) for v, n in sorted(rows, key=lambda r: (-r[1], str(r[0])))}


def dates(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Event dates: as FDA wrote them, by digits, and as read (rule event-date-precision), with
    the full days that are read as a month or a year."""
    written = " ".join(f"WHEN length(trim(event_dt)) = {n} THEN '{w}'" for n, w in DIGITS.items())
    read = " ".join(f"WHEN event_dt_prec_T = {n} THEN '{w}'" for n, w in DIGITS.items())
    rows = _rows(
        con,
        f"""SELECT CASE WHEN nullif(trim(event_dt), '') IS NULL THEN 'none' {written}
                        ELSE 'other' END,
                   CASE {read} ELSE 'none' END, count(*)
            FROM case_latest_T WHERE dup_kept_T GROUP BY ALL""",
    )
    out: dict[str, Any] = {"written": {}, "read": {}}
    for w, r, n in rows:
        out["written"][w] = out["written"].get(w, 0) + n
        out["read"][r] = out["read"].get(r, 0) + n
    out = {k: _tally(list(v.items())) for k, v in out.items()}
    out["day_read_as_month_or_year"] = sum(
        n for w, r, n in rows if w == "day" and r in ("month", "year")
    )
    return out


def ages(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Ages: by the unit FDA gave (`none` for an age with no unit), the cases with no age, and the
    ages read in years (rule age-in-years)."""
    rows = _rows(
        con,
        """SELECT CASE WHEN nullif(trim(age), '') IS NULL THEN NULL
                       ELSE coalesce(nullif(upper(trim(age_cod)), ''), 'none') END,
                  count(*), count(age_years_T)
           FROM case_latest_T WHERE dup_kept_T GROUP BY 1""",
    )
    return {
        "units": _tally([(u, n) for u, n, _ in rows if u is not None]),
        "no_age": sum(n for u, n, _ in rows if u is None),
        "in_years": sum(y for _, _, y in rows),
    }


def reporters(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Who reported: FDA's occupation code as written (`none` when blank) and the reporter type
    it is read to (rule reporter-type)."""
    rows = _rows(
        con,
        """SELECT coalesce(nullif(upper(trim(occp_cod)), ''), 'none'),
                  coalesce(CAST(reporter_type_T AS VARCHAR), 'none'), count(*)
           FROM case_latest_T WHERE dup_kept_T GROUP BY ALL""",
    )
    written: dict[str, int] = {}
    read: dict[str, int] = {}
    for w, r, n in rows:
        written[w] = written.get(w, 0) + n
        read[r] = read.get(r, 0) + n
    return {"written": _tally(list(written.items())), "read": _tally(list(read.items()))}


def routes(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Drug rows' routes: blank, saying unknown, and so read Not given (rule not-given); with the
    route families (rule drug-route) when the release has them."""
    blank = f"nullif(trim(d.route, {SPACES}), '') IS NULL"
    [(rows, blanks, nothing)] = _rows(
        con,
        f"""SELECT count(*), count(*) FILTER (WHERE {blank}),
                   count(*) FILTER (WHERE {not_given.check("route", "d.route")})
            FROM drug_latest_T d SEMI JOIN {SHOWN} c USING ({KEY})""",
    )
    out: dict[str, Any] = {
        "rows": rows,
        "blank": blanks,
        "says_unknown": nothing - blanks,
        "not_given": nothing,
    }
    if _has(con, "drug_route_T"):
        [(families, one, several, unknown)] = _rows(
            con,
            f"""WITH r AS (SELECT route_families_T AS f
                           FROM drug_route_T SEMI JOIN {SHOWN} c USING ({KEY}))
                SELECT (SELECT count(DISTINCT x) FROM (SELECT unnest(string_split(f, ';')) AS x
                                                       FROM r WHERE coalesce(f, '') <> '')),
                       count(*) FILTER (WHERE coalesce(f, '') <> '' AND NOT contains(f, ';')),
                       count(*) FILTER (WHERE contains(f, ';')),
                       count(*) FILTER (WHERE coalesce(f, '') = '')
                FROM r""",
        )
        out["families"] = {
            "families": families,
            "one": one,
            "several": several,
            "not_known": unknown,
        }
    return out


def drug_names(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Drug names as FDA wrote them read to ingredients (rule drug-names): the spellings, the
    ingredients and the combinations (each counted ignoring capitals), the ingredients by how
    many spellings each has, the suspect cases a search by each ingredient's most common spelling
    finds against those its ingredient finds, and the drug records, those whose name finds no
    ingredient among them."""
    rows = f"""(SELECT d.*, i.ingredient_T FROM drug_latest_T d SEMI JOIN {SHOWN} c USING ({KEY})
               JOIN drug_ingredient_T i USING ({DRUG_KEY}) WHERE i.ingredient_T IS NOT NULL)"""
    [(spellings,)] = _rows(
        con,
        f"SELECT count(DISTINCT d.drugname) FROM drug_latest_T d SEMI JOIN {SHOWN} c USING ({KEY})",
    )
    # ingredients by how many spellings each has: those with one, then by its count's digits
    per = _rows(
        con,
        f"""SELECT length(CAST(n AS VARCHAR)), count(*), count(*) FILTER (WHERE n = 1)
            FROM (SELECT lower(ingredient_T) AS ingredient_T, count(DISTINCT drugname) AS n
                  FROM {rows} GROUP BY 1)
            GROUP BY 1 ORDER BY 1""",
    )
    ingredients, one = sum(n for _, n, _ in per), sum(o for _, _, o in per)
    [(records, unmapped, combinations)] = _rows(  # drug_substance_T holds one row per drug record
        con,
        f"""SELECT count(*), count(*) FILTER (WHERE s.substance_source_T = '{UNMAPPED}'),
                   count(DISTINCT lower(s.substance_T)) FILTER (WHERE s.substance_T LIKE '%;%')
            FROM drug_substance_T s SEMI JOIN {SHOWN} c USING ({KEY})""",
    )
    [(by_spelling, by_ingredient)] = _rows(
        con,
        f"""WITH s AS (SELECT DISTINCT ingredient_T, drugname, {KEY} FROM {rows} d
                       WHERE {_suspect()}),
                 top AS (SELECT ingredient_T, max(n) AS n
                         FROM (SELECT ingredient_T, drugname, count(*) AS n FROM s GROUP BY 1, 2)
                         GROUP BY 1),
                 every AS (SELECT ingredient_T, count(DISTINCT ({KEY})) AS n FROM s GROUP BY 1)
            SELECT coalesce(sum(top.n), 0), coalesce(sum(every.n), 0)
            FROM every JOIN top USING (ingredient_T)""",
    )
    return {
        "spellings": spellings,
        "ingredients": ingredients,
        "combinations": combinations,
        "spellings_per_ingredient": {
            "one": one,
            "by_digits": [{"digits": d, "ingredients": n} for d, n, _ in per],
        },
        "written_two_or_more_ways": ingredients - one,
        "suspect_cases": {
            "by_ingredient": int(by_ingredient),
            "by_most_common_spelling": int(by_spelling),
        },
        "drug_records": records,
        "unmapped_records": unmapped,
    }


def rxnorm(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Suspect drug rows and their RxNorm codes (rule rxnorm-ingredients), and the suspect drug
    records, each counted once however many dose rows FDA repeats it on."""
    [(suspect, coded, codes)] = _rows(
        con,
        f"""SELECT count(*), count(x.rxcui_T), count(DISTINCT x.rxcui_T)
            FROM drug_latest_T d SEMI JOIN {SHOWN} c USING ({KEY})
            LEFT JOIN drug_rxnorm_T x USING ({DRUG_KEY}) WHERE {_suspect()}""",
    )
    [(records, coded_records)] = _rows(
        con,
        f"""SELECT count(*), count(x.rxcui_T)
            FROM (SELECT DISTINCT {DRUG_KEY} FROM drug_latest_T d SEMI JOIN {SHOWN} c USING ({KEY})
                  WHERE {_suspect()}) d
            LEFT JOIN drug_rxnorm_T x USING ({DRUG_KEY})""",
    )
    return {
        "suspect_rows": suspect,
        "coded_rows": coded,
        "codes": codes,
        "suspect_records": records,
        "coded_records": coded_records,
    }


def terms(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Reaction terms as FDA wrote them; the MedDRA terms they read to are licensed (licensed())."""
    [(texts,)] = _rows(
        con,
        f"SELECT count(DISTINCT r.pt) FROM reac_latest_T r SEMI JOIN {SHOWN} c USING ({KEY})",
    )
    return {"texts": texts}


def classes(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """WHO classes (rules atc-*): drug rows by how their one class was chosen, those with a class,
    the classes used, and the suspect cases (explorer-drug-counts' default roles) in each main
    group."""
    drugs = f"(SELECT * FROM atc_drug_T SEMI JOIN {SHOWN} c USING ({KEY}))"
    chosen = _rows(
        con, f"SELECT coalesce(atc_chosen_by_T, 'none'), count(*) FROM {drugs} GROUP BY 1"
    )
    [(rows, with_class, codes)] = _rows(
        con, f"SELECT count(*), count(atc_code_T), count(DISTINCT atc_code_T) FROM {drugs}"
    )
    groups = _rows(
        con,
        f"""SELECT g.atc_code_T, g.atc_name_T, count(DISTINCT (a.era_T, a.primaryid, a.quarter_T))
            FROM {drugs} a JOIN drug_latest_T d USING ({DRUG_KEY})
            JOIN atc_index_T g ON g.atc_level_T = 1 AND g.atc_code_T = substr(a.atc_code_T, 1, 1)
                              AND g.atc_index_year_T = a.atc_index_year_T
            WHERE {_suspect()} GROUP BY 1, 2 ORDER BY 3 DESC, 1""",
    )
    return {
        "rows": rows,
        "chosen_by": _tally(chosen),
        "rows_with_class": with_class,
        "codes": codes,
        "main_groups": [{"code": c, "name": name, "cases": n} for c, name, n in groups],
    }


def stand_out(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, Any]]:
    """The pairs of statistics_T meeting each statistic's default screen (the preset its rule
    marks default), by statistic; one with no default preset (RRR) is left out."""
    out = {}
    described = _rows(con, "SELECT column_name FROM (DESCRIBE statistics_T)")
    columns = {c.removesuffix("_T") for (c,) in described}
    for name in screen.RULES:
        preset = next((p for p in screen.presets(name) if p.get("default")), None)
        if preset is None:
            continue
        clause, params = screen.where(screen.check(preset["when"], columns), lambda c: f"{c}_T")
        [(n,)] = con.execute(f"SELECT count(*) FROM statistics_T WHERE {clause}", params).fetchall()
        out[name] = {"preset": preset["id"], "pairs": int(n)}
    return out


def public(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """methods.json's `numbers`, from the release's tables on `con`."""
    out: dict[str, Any] = {
        "dates": dates(con),
        "ages": ages(con),
        "reporters": reporters(con),
        "routes": routes(con),
        "terms": terms(con),
    }
    if _has(con, "drug_ingredient_T"):
        out["drug_names"] = drug_names(con)
    if _has(con, "drug_rxnorm_T"):
        out["rxnorm"] = rxnorm(con)
    if _has(con, "atc_drug_T", "atc_index_T"):
        out["classes"] = classes(con)
    if _has(con, "statistics_T"):
        out["statistics"] = {"stand_out": stand_out(con)}
    if _has(con, *FLAGGED):
        out["label_flags"] = label_flags(con)
    return out


def label_flags(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """The suspect drug records (rule label-flags' roles) by the fate each met on the way to a
    label, the fates of labeldict.join, read from what the label step wrote: a trial product, a
    code that names another drug (label_other_drug_T), no RxNorm code, a code no label has, or
    a label."""
    rows = _rows(
        con,
        f"""SELECT CASE WHEN coalesce(s.diana_trial_T, false) THEN 'trial_product'
                        WHEN o.drug_seq IS NOT NULL THEN 'code_names_another_drug'
                        WHEN x.rxcui_T IS NULL THEN 'no_rxnorm_code'
                        WHEN l.rxcui_T IS NULL THEN 'no_label' ELSE 'label' END, count(*)
            FROM (SELECT DISTINCT {DRUG_KEY} FROM drug_latest_T d SEMI JOIN {SHOWN} c USING ({KEY})
                  WHERE {_suspect(rule="label-flags", key="suspect_roles")}) d
            JOIN drug_substance_T s USING ({DRUG_KEY})
            LEFT JOIN drug_rxnorm_T x USING ({DRUG_KEY})
            LEFT JOIN label_other_drug_T o USING ({DRUG_KEY})
            LEFT JOIN (SELECT DISTINCT rxcui_T FROM label_candidates_T) l ON l.rxcui_T = x.rxcui_T
            GROUP BY 1""",
    )
    fates = ("trial_product", "no_rxnorm_code", "code_names_another_drug", "no_label", "label")
    records = {fate: 0 for fate in fates} | {str(f): int(n) for f, n in rows}
    return {"records": records | {"suspect": sum(records.values())}}


def licensed(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """The numbers that need MedDRA's files, for the licensed manifest: the MedDRA terms the
    reactions of the cases shown read to (rule meddra-terms), and the cases carrying a term
    MedDRA has since replaced, with those a search on today's term misses (the card
    older_meddra_terms_missed counts them the same way)."""
    [(pts, cases, older, missed)] = _rows(
        con,
        f"""WITH r AS ({REACTIONS}),
                 per AS (SELECT case_key_T, pt_code_T, bool_or(pt_current_T) AS direct_T,
                                bool_or(NOT pt_current_T) AS older_T FROM r GROUP BY ALL)
            SELECT (SELECT count(DISTINCT pt_code_T) FROM r), count(DISTINCT case_key_T),
                   count(DISTINCT case_key_T) FILTER (WHERE older_T),
                   count(DISTINCT case_key_T) FILTER (WHERE older_T AND NOT direct_T)
            FROM per""",
    )
    return {
        "terms": {"meddra_terms": pts},
        "older_terms": {
            "cases": cases,
            "with_an_older_term": older,
            "missed_by_todays_term": missed,
        },
    }


def _replace(path: Path, doc: dict) -> None:
    """Write `doc` beside `path` and rename it into place, so a reader never sees half a file."""
    writing = path.with_name(path.name + ".writing")
    writing.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    os.replace(writing, path)


def write(
    release_dir: str | Path, *, memory_limit: str | None = None, threads: int | None = None
) -> dict[str, Any]:
    """Add the numbers, "What we do not do" filled with them, and every rule's version to a
    written release's methods.json, under the rules it was built with, and the numbers that need
    MedDRA to its licensed manifest. Each file is replaced whole, so running it again gives the
    same files. Returns the public numbers."""
    release_dir = Path(release_dir)
    manifest = read_manifest(release_dir)
    held = read_licensed_manifest(release_dir)
    spill = release_dir / ".numbers.spill"
    con = duckdb.connect()
    try:
        if memory_limit:
            con.execute(f"SET memory_limit = {quoted(memory_limit)}")
        if threads:
            con.execute(f"SET threads = {int(threads)}")
        con.execute(f"SET temp_directory = {quoted(str(spill))}")
        con.execute("SET enable_progress_bar = false")
        tables = {t: e for t, e in manifest["tables"].items() if t in TABLES}
        register_release(con, release_dir, tables=tables, temporary=True, with_views=False)
        built = rulebook.from_differences(manifest.get("user_rules") or {"off": [], "changed": []})
        with rulebook.use_user_rules(built):
            doc = json.loads((release_dir / manifest["methods"]).read_text(encoding="utf-8"))
            doc["numbers"] = public(con)
            funnel = json.loads((release_dir / manifest["funnel"]).read_text(encoding="utf-8"))
            doc["limits"] = fill_limits(funnel, doc["numbers"])
            doc["rule_versions"] = rule_versions()
            problems = validate(doc)
            if problems:
                raise MethodsError("; ".join(problems))
            versions = (held or {}).get("meddra", {}).get("versions", {})
            for entry in versions.values():  # one (rule meddra-version)
                mapping = {t: entry["tables"][t] for t in MEDDRA_TABLES}
                register_release(
                    con, licensed_dir(release_dir), tables=mapping, temporary=True, with_views=False
                )
                entry["numbers"] = licensed(con)
        _replace(release_dir / manifest["methods"], doc)
        if held and versions:
            _replace(licensed_dir(release_dir) / LICENSED_MANIFEST, held)
    finally:
        con.close()
        shutil.rmtree(spill, ignore_errors=True)
    return doc["numbers"]


__all__ = [
    "TABLES",
    "ages",
    "classes",
    "dates",
    "drug_names",
    "label_flags",
    "licensed",
    "public",
    "reporters",
    "routes",
    "rxnorm",
    "stand_out",
    "terms",
    "write",
]
