"""The insight cards of notebook 06 (MedDRA versions): what FDA's MedDRA terms do to a count,
measured on the release with its MedDRA version.

They read the mapping tables of the licensed part (open_altio.faers.meddra.terms) where the
connection holds them: the release build's own database when it was given MedDRA, or a
notebook that read MedDRA's files. A card shows counts and PT names only, never a code, a lower
level term or an old name. Cases are the default case set (`case_latest_T` where `dup_kept_T`).
A release built without MedDRA has no such tables: each card then says so plainly, with no
data, and its tag says nothing was transformed.
"""

from __future__ import annotations

import duckdb

from open_altio.faers.meddra import COLUMNS, key_sql

from . import common

NB06 = "notebooks/faers/06_meddra_versions.ipynb"
STEP = "meddra_terms"
TERMS, VERSION = "meddra-terms", "meddra-version"  # the rules these cards are the evidence for
UNKNOWN_INDICATION = "Product used for unknown indication"  # MedDRA's PT for a reason not given
TOP = 8  # the PTs a chart shows

# Each reaction of the default case set with the PT its text maps to, and whether FDA wrote that
# PT itself (pt_current_T) or an older term of it.
_REACTIONS = f"""
SELECT c.case_key_T, c.era_T, r.quarter_T, m.pt_code_T, m.pt_current_T
FROM reac_latest_T r JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
JOIN {COLUMNS["pt"].table} m ON m.reac_term_T = {key_sql("pt", "r.pt")}
WHERE c.dup_kept_T
"""


def _built(con: duckdb.DuckDBPyConnection) -> bool:
    """Whether the connection holds the MedDRA mapping and MedDRA's PTs."""
    [(have,)] = con.execute(
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_name IN ('{COLUMNS['pt'].table}', 'meddra_pt')"
    ).fetchall()
    return have == 2


def _absent(card_id: str, shows: str) -> dict:
    """The card of a release built without MedDRA: no data, and why."""
    return common.card(
        card_id,
        "This release does not read MedDRA terms",
        "It was built without a MedDRA release, so it carries no mapping of FDA's terms. Built "
        f"with one (open-altio build --meddra), this card shows {shows}.",
        common.chart("stacked_bar", "", "category", [], "", "count", []),
        common.DOCUMENTED,
        NB06,
    )


def older_meddra_terms_missed(con: duckdb.DuckDBPyConnection) -> dict:
    """FDA codes each report in the MedDRA version of its day, so older reports carry terms
    MedDRA has since demoted or renamed, and a search on today's term misses them. Changed our
    pipeline: each term is read to its current PT (rules/meddra-terms.md)."""
    if not _built(con):
        return _absent(
            "older_meddra_terms_missed", "how many cases a search on today's term misses"
        )
    today, older = "Written as today's term", "Written only as an older term"
    cases = common.query(
        con,
        f"""
        WITH pairs AS (SELECT case_key_T, era_T, pt_code_T, bool_or(pt_current_T) AS direct_T,
                              bool_or(NOT pt_current_T) AS older_T
                       FROM ({_REACTIONS}) GROUP BY ALL)
        SELECT era_T, count(DISTINCT case_key_T),
               count(DISTINCT case_key_T) FILTER (WHERE older_T),
               count(DISTINCT case_key_T) FILTER (WHERE older_T AND NOT direct_T)
        FROM pairs GROUP BY ROLLUP (era_T)""",
    )
    got = {era or "all": (n, carry, missed) for era, n, carry, missed in cases}
    rows = common.query(
        con,
        f"""
        WITH pairs AS (SELECT case_key_T, pt_code_T, bool_or(pt_current_T) AS direct_T
                       FROM ({_REACTIONS}) GROUP BY ALL),
        per_pt AS (SELECT pt_code_T, count(*) FILTER (WHERE direct_T) AS today_T,
                          count(*) FILTER (WHERE NOT direct_T) AS older_T FROM pairs GROUP BY 1)
        SELECT p.pt_name, today_T, older_T
        FROM per_pt JOIN meddra_pt p ON p.pt_code = per_pt.pt_code_T
        ORDER BY older_T DESC, p.pt_name LIMIT {TOP}""",
    )
    xs = [name for name, _, _ in rows]
    lines = common.series(
        [(n, today, t) for n, t, _ in rows] + [(n, older, o) for n, _, o in rows],
        xs,
        [today, older],
    )
    chart = common.chart(
        "stacked_bar",
        "Today's MedDRA term",
        "category",
        xs,
        "Cases in the default case set",
        "count",
        lines,
        question="How many cases does a search on today's MedDRA term miss?",
    )
    n, carry, missed = got.get("all", (0, 0, 0))
    legacy, faers = got.get("legacy", (0, 0, 0)), got.get("faers", (0, 0, 0))
    first = rows[0] if rows else ("", 0, 0)
    return common.card(
        "older_meddra_terms_missed",
        f"{common.pct(carry, n, 1)} of cases carry a reaction term from an older MedDRA version",
        "FDA codes each report in the MedDRA version of its day, and MedDRA later demotes or "
        f"renames terms, so {common.plural(carry, 'case')} ({common.pct(legacy[1], legacy[0], 1)} "
        f"of AERS cases, {common.pct(faers[1], faers[0], 1)} of FAERS cases) carry a reaction that "
        f"is not a current term. A search on today's term misses {missed:,} of them: {first[0]} "
        f"alone is written another way in {first[2]:,} cases.",
        chart,
        common.changed(STEP, TERMS),
        NB06,
    )


def quarterly_files_keep_their_meddra_version(con: duckdb.DuckDBPyConnection) -> dict:
    """Each quarterly file is coded in the MedDRA version current when FDA built it, and FDA
    never reissues one, so a file's terms age with it. Changed our pipeline: a release reads
    every quarter in one MedDRA version, the newest when it is built (rules/meddra-version.md)."""
    if not _built(con):
        return _absent(
            "quarterly_files_keep_their_meddra_version",
            "how much of each quarter's reactions is no longer a current term",
        )
    name = "Reaction rows that are not a current MedDRA term"
    rows = common.query(
        con,
        f"""SELECT quarter_T, era_T, 100.0 * count(*) FILTER (WHERE NOT pt_current_T) / count(*)
            FROM ({_REACTIONS}) GROUP BY ALL ORDER BY 1""",
    )
    version = common.query(con, f"SELECT any_value(meddra_version_T) FROM {COLUMNS['pt'].table}")
    xs = [q for q, _, _ in rows]
    chart = common.chart(
        "line",
        "Quarter of the case's latest version",
        "quarter",
        xs,
        "Share of the quarter's reaction rows",
        "percent",
        common.series([(q, name, share) for q, _, share in rows], xs, [name]),
        question="How much of each quarter's reactions is no longer a current MedDRA term?",
        note=(xs[-1], "The newest quarter") if xs else None,
    )
    peak = {
        era: max(((s, q) for q, e, s in rows if e == era), default=(0.0, ""))
        for era in ("legacy", "faers")
    }
    last = rows[-1] if rows else ("", "", 0.0)
    return common.card(
        "quarterly_files_keep_their_meddra_version",
        "Each quarterly file keeps the MedDRA version FDA built it in",
        "FDA recodes its own database to each new MedDRA version but never reissues a published "
        "file, so the older the quarter, the more of its terms are no longer current: up to "
        f"{peak['legacy'][0]:.1f}% of an AERS quarter's rows ({peak['legacy'][1].upper()}) and "
        f"{peak['faers'][0]:.1f}% of a FAERS quarter's ({peak['faers'][1].upper()}), against "
        f"{last[2]:.2f}% in {last[0].upper()}. This release reads every quarter in one version, "
        f"MedDRA {version[0][0] if version else ''}, the newest when it was built.",
        chart,
        common.changed(STEP, VERSION, TERMS),
        NB06,
    )


def unknown_indication_placeholder(con: duckdb.DuckDBPyConnection) -> dict:
    """A third of FAERS's indication rows give no indication: they are MedDRA's term for a
    drug used for a reason not given. Documented, not transformed."""
    if not _built(con):
        return _absent(
            "unknown_indication_placeholder", "how many indication rows give no reason for the drug"
        )
    name = "Indication rows that give no reason"
    rows = common.query(
        con,
        f"""
        SELECT i.quarter_T, count(*) AS rows_T, count(*) FILTER (WHERE p.pt_name = ?) AS unknown_T
        FROM indi_latest_T i JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
        LEFT JOIN {COLUMNS["indi_pt"].table} m ON m.indi_term_T = {key_sql("indi_pt", "i.indi_pt")}
        LEFT JOIN meddra_pt p ON p.pt_code = m.pt_code_T
        WHERE c.dup_kept_T AND i.indi_pt IS NOT NULL GROUP BY 1 ORDER BY 1""",
        [UNKNOWN_INDICATION],
    )
    xs = [q for q, _, _ in rows]
    chart = common.chart(
        "line",
        "Quarter of the case's latest version",
        "quarter",
        xs,
        "Share of the quarter's indication rows",
        "percent",
        common.series([(q, name, 100.0 * u / n) for q, n, u in rows], xs, [name]),
        question="How many indication rows say what the drug was given for?",
    )
    total, unknown = sum(n for _, n, _ in rows), sum(u for _, _, u in rows)
    return common.card(
        "unknown_indication_placeholder",
        f"{common.pct(unknown, total)} of FAERS's indications give no reason for the drug",
        f"{unknown:,} of {total:,} indication rows are MedDRA's term for a drug used for a reason "
        f"not given ({UNKNOWN_INDICATION}), in today's wording or an older one. A count or filter "
        "of what drugs were given for leaves these rows out, or counts them as one indication.",
        chart,
        common.DOCUMENTED,
        NB06,
    )
