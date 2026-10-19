"""Check that two explorer databases hold the same data, table by table.

    python scripts/compare_explorer_db.py REFERENCE.duckdb CANDIDATE.duckdb

For every table and view in either file it compares the column names and
types, the row count, and for every column the number of NULLs and an
order-independent checksum: the sum of the 128-bit MD5 of each value (as two
64-bit halves). A sum keeps how often each value occurs, which an XOR would
lose. A row checksum (the MD5 of each row's values, length-prefixed, summed)
catches values that moved between rows. For the tables whose storage order the
explorer relies on (cases by id, children by case, terms by term), an order
checksum hashes each row's position with its sort key, so a build that stores
the same rows in another order is caught too. DuckDB's hash() is never used: it
collides.

`explorer_release_T.built_at_T` is the build's own timestamp and is reported,
not compared. Exit code 0 when everything else matches, 1 when anything differs.
Read only: both files are opened with read_only=True.
"""

from __future__ import annotations

import argparse
import sys
import time

import duckdb

from open_altio.faers.explorer_db import CHILD_ORDER

# Columns that differ on every build by design.
EXPECTED_TO_DIFFER = {("explorer_release_T", "built_at_T")}

# The storage order each table is written in (explorer_db.py).
ORDER_KEYS = {
    "explorer_case_T": "case_id_T",
    "explorer_sender_T": "spelling_T, company_T",
    "explorer_drug_term_T": "term_T, case_id_T",
    "explorer_reac_term_T": "term_T, case_id_T",
    "explorer_ingredient_T": "ingredient_T, case_id_T",
    "explorer_no_ingredient_T": "spelling_T, case_id_T",
    "explorer_atc_class_T": "atc_code_T",
    "explorer_atc_drug_T": "case_id_T, drug_seq",
    "explorer_atc_term_T": "atc_code_T, case_id_T",
    "explorer_atc_could_T": "atc_code_T, case_id_T",
    **{
        f"explorer_{child}_T": "case_id_T, " + order.replace("d.", "")
        for child, order in CHILD_ORDER.items()
    },
}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _text(col: str, dtype: str) -> str:
    """A column's value as text; nested types through JSON so their parts stay apart."""
    if dtype.endswith("[]") or dtype.startswith(("STRUCT", "MAP")):
        return f"to_json({_q(col)})::VARCHAR"
    return f"{_q(col)}::VARCHAR"


def _encoded(col: str, dtype: str) -> str:
    t = _text(col, dtype)
    return f"CASE WHEN {_q(col)} IS NULL THEN 'N' ELSE 'V' || length({t}) || ':' || {t} END"


def _relations(con) -> dict[str, str]:
    rows = con.execute("""
        SELECT table_name, 'table' FROM duckdb_tables()
        WHERE NOT internal AND database_name = current_database()
        UNION ALL
        SELECT view_name, 'view' FROM duckdb_views()
        WHERE NOT internal AND database_name = current_database()
    """).fetchall()
    return dict(rows)


def _columns(con, name: str) -> list[tuple[str, str]]:
    return con.execute(
        "SELECT column_name, data_type FROM duckdb_columns() WHERE table_name = ? "
        "AND database_name = current_database() ORDER BY column_index",
        [name],
    ).fetchall()


def fingerprint(path: str, *, threads: int, memory_limit: str, temp_directory: str | None) -> dict:
    con = duckdb.connect(path, read_only=True)
    con.execute(f"SET threads = {int(threads)}")
    con.execute(f"SET memory_limit = '{memory_limit}'")
    con.execute("SET enable_progress_bar = false")
    if temp_directory:
        con.execute(f"SET temp_directory = '{temp_directory}'")
    out = {}
    try:
        for name, kind in sorted(_relations(con).items()):
            t0 = time.monotonic()
            cols = _columns(con, name)
            parts = ["count(*)"]
            for col, dtype in cols:
                t = _text(col, dtype)
                parts += [
                    f"count({_q(col)})",
                    f"sum(md5_number_lower({t}))",
                    f"sum(md5_number_upper({t}))",
                ]
            row = "md5(" + " || '|' || ".join(_encoded(c, d) for c, d in cols) + ")"
            parts += [f"sum(md5_number_lower({row}))", f"sum(md5_number_upper({row}))"]
            order = ORDER_KEYS.get(name) if kind == "table" else None
            if order:
                keys = [k.strip() for k in order.split(",")]
                pos = "rowid::VARCHAR || '|' || " + " || '|' || ".join(
                    f"coalesce({k}::VARCHAR, 'N')" for k in keys
                )
                parts += [f"sum(md5_number_lower({pos}))", f"sum(md5_number_upper({pos}))"]
            got = con.execute(f"SELECT {', '.join(parts)} FROM {_q(name)}").fetchone()
            entry = {"kind": kind, "rows": got[0], "columns": {}, "types": dict(cols)}
            i = 1
            for col, _ in cols:
                entry["columns"][col] = {
                    "nulls": got[0] - got[i],
                    "md5_sum": (got[i + 1], got[i + 2]),
                }
                i += 3
            entry["row_md5_sum"] = (got[i], got[i + 1])
            i += 2
            entry["order_md5_sum"] = (got[i], got[i + 1]) if order else None
            entry["seconds"] = round(time.monotonic() - t0, 1)
            out[name] = entry
    finally:
        con.close()
    return out


def compare(ref: dict, new: dict) -> list[str]:
    """Lines saying what differs; empty when the two match."""
    problems = []
    for name in sorted(set(ref) | set(new)):
        if name not in new:
            problems.append(f"{name}: missing from the candidate")
            continue
        if name not in ref:
            problems.append(f"{name}: not in the reference")
            continue
        a, b = ref[name], new[name]
        if a["types"] != b["types"]:
            problems.append(f"{name}: columns or types differ: {a['types']} vs {b['types']}")
            continue
        if a["rows"] != b["rows"]:
            problems.append(f"{name}: rows {a['rows']} vs {b['rows']}")
        expected = {c for t, c in EXPECTED_TO_DIFFER if t == name}
        for col in a["columns"]:
            if col in expected:
                continue
            if a["columns"][col] != b["columns"][col]:
                problems.append(f"{name}.{col}: {a['columns'][col]} vs {b['columns'][col]}")
        if not expected and a["row_md5_sum"] != b["row_md5_sum"]:
            problems.append(f"{name}: row checksum differs")
        if a["order_md5_sum"] != b["order_md5_sum"]:
            problems.append(f"{name}: storage order differs (order checksum)")
    return problems


def report(ref_path: str, new_path: str, ref: dict, new: dict, problems: list[str]) -> str:
    lines = [f"reference: {ref_path}", f"candidate: {new_path}", ""]
    lines.append(f"{'table or view':24} {'kind':5} {'rows':>12} {'cols':>4}  columns  row  order")
    for name in sorted(set(ref) | set(new)):
        if name not in ref or name not in new:
            continue
        a, b = ref[name], new[name]
        expected = {c for t, c in EXPECTED_TO_DIFFER if t == name}
        cols_ok = (
            all(a["columns"][c] == b["columns"].get(c) for c in a["columns"] if c not in expected)
            and a["types"] == b["types"]
        )
        row_ok = "n/a" if expected else ("same" if a["row_md5_sum"] == b["row_md5_sum"] else "DIFF")
        order_ok = (
            "n/a"
            if a["order_md5_sum"] is None
            else ("same" if a["order_md5_sum"] == b["order_md5_sum"] else "DIFF")
        )
        rows = f"{b['rows']:,}" if a["rows"] == b["rows"] else f"{a['rows']:,}->{b['rows']:,}"
        lines.append(
            f"{name:24} {a['kind']:5} {rows:>12} {len(a['types']):>4}  "
            f"{'same' if cols_ok else 'DIFF':7}  {row_ok:4} {order_ok:5}"
        )
    for t, c in sorted(EXPECTED_TO_DIFFER):
        if t in ref and t in new:
            lines.append(f"not compared: {t}.{c} (the build's own timestamp)")
    lines.append("")
    lines.append(
        "RESULT: every table and view matches"
        if not problems
        else "RESULT: DIFFERENT\n" + "\n".join(problems)
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("reference")
    ap.add_argument("candidate")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--memory-limit", default="3GB")
    ap.add_argument("--temp-directory", default=None)
    args = ap.parse_args(argv)
    opts = dict(
        threads=args.threads, memory_limit=args.memory_limit, temp_directory=args.temp_directory
    )
    ref = fingerprint(args.reference, **opts)
    new = fingerprint(args.candidate, **opts)
    problems = compare(ref, new)
    print(report(args.reference, args.candidate, ref, new, problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
