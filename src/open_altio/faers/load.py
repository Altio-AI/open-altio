"""Load FDA's text files into the build database, every value verbatim.

`$`-delimited, no quoting or escaping, every column as text, short rows
padded with empty values, Latin-1 where a file is not UTF-8. Legacy AERS
rows end in a stray `$` the header does not have; DuckDB drops that empty
trailing field. An empty field is NULL; any other value is kept exactly as
FDA wrote it, spaces included.

The header line decides the columns, never a guess from the rows, and a
line with more fields than the header is never cut short in silence
(rules/overlong-lines.md): one holding whole records run together is split
back into them, any other keeps its first fields, and each is listed in the
manifest under `overlong_lines`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb

from open_altio import rulebook

from .reader import quoted
from .schema import RAW_COLUMNS, TABLES, columns, normal_header, unified_name
from .sources import Quarter, SourceError, file_facts

TOO_MANY = "TOO MANY COLUMNS"  # DuckDB's reject for a line wider than the header


@dataclass
class LoadedFile:
    """One FDA file read into a raw table: what the manifest records."""

    table: str
    quarter: str  # quarter_T of its rows
    source: str  # '<zip or folder>/<member>'
    sha256: str
    bytes: int
    encoding: str
    rows: int
    rejected_lines: int
    era: str | None = None
    overflow_values: int = 0  # non-empty values past the header's last column, not kept
    renamed: dict[str, str] = field(default_factory=dict)
    overlong_lines: list[dict] = field(default_factory=list)  # see _overlong_lines

    def as_json(self) -> dict:
        return asdict(self)


def create_raw_tables(con: duckdb.DuckDBPyConnection) -> None:
    for table in RAW_COLUMNS:
        cols = ", ".join(f'"{c}" VARCHAR' for c in columns(table))
        con.execute(f"CREATE TABLE {table} ({cols})")


def _header(path: Path, encoding: str) -> list[str]:
    """The header line's names as FDA wrote them, a byte order mark dropped."""
    with open(path, "rb") as f:
        first = f.readline().removeprefix(b"\xef\xbb\xbf")
    return first.decode(encoding).rstrip("\r\n").split("$")


def _read_csv(path: Path, encoding: str, headers: list[str]) -> str:
    """The header gives the columns, so a long line further down is reported
    as too long instead of widening the table."""
    cols = "{" + ", ".join(f"{quoted(h)}: 'VARCHAR'" for h in headers) + "}"
    return (
        f"read_csv({quoted(str(path))}, delim='$', header=true, auto_detect=false, "
        f"columns={cols}, quote='', escape='', null_padding=true, ignore_errors=true, "
        f"encoding={quoted(encoding)}, strict_mode=true, "
        f"rejects_table='rejects_scratch', rejects_limit=0)"
    )


def _overlong_lines(con: duckdb.DuckDBPyConnection, width: int) -> list[dict]:
    """Put back the lines the strict read set aside for having more fields
    than the header (rules/overlong-lines.md), and say what was done to each.

    A line that is whole records one after the other (a multiple of the
    header's `width` fields, plus legacy's stray trailing `$`) is split into
    those records. Any other keeps its first `width` fields, as a lenient read
    would; the text past them is recorded as `dropped`. Empty fields are NULL,
    as everywhere else; no value is changed."""
    split = rulebook.is_on("overlong-lines")
    rows, done = [], []
    for line, text in con.execute(
        f"SELECT line, any_value(csv_line) FROM rejects_scratch WHERE error_type = '{TOO_MANY}' "
        "GROUP BY line ORDER BY line"
    ).fetchall():
        fields = text.strip("\r\n").split("$")
        body = fields[:-1] if fields[-1] == "" else fields  # legacy's stray trailing `$`
        records = len(body) // width if split and len(body) % width == 0 else 1
        entry: dict[str, int | str] = {"line": int(line), "fields": len(fields), "records": records}
        if records > 1:
            rows += [body[i * width : (i + 1) * width] for i in range(records)]
        else:
            rows.append(fields[:width])
            entry["dropped"] = "$".join(fields[width:])
        done.append(entry)
    if rows:
        marks = ", ".join("?" * width)
        con.executemany(
            f"INSERT INTO staged VALUES ({marks})", [[v or None for v in r] for r in rows]
        )
    return done


def _era_of(headers: list[str]) -> str:
    """Legacy AERS keys its reports by ISR; FAERS by primaryid."""
    return "legacy" if "isr" in {normal_header(h) for h in headers} else "faers"


def load_table_file(
    con: duckdb.DuckDBPyConnection, quarter: Quarter, table: str, work: Path
) -> LoadedFile:
    member = quarter.table_file(table)
    path = quarter.materialise(member, work)
    facts = file_facts(path)
    headers = _header(path, facts.encoding)
    era = _era_of(headers)
    wanted = set(RAW_COLUMNS[table])
    source_of: dict[str, str] = {}
    renamed: dict[str, str] = {}
    for h in headers:
        name = unified_name(table, h)
        if name not in wanted:
            raise SourceError(
                f"{quarter.label}/{member}: column {h.strip()!r} is not in the release schema "
                f"for {table}; add it to src/open_altio/faers/schema.py before building"
            )
        if name in source_of:
            raise SourceError(
                f"{quarter.label}/{member}: columns {source_of[name]!r} and {h!r} both mean {name}"
            )
        source_of[name] = h
        if normal_header(h) != name:
            renamed[h.strip()] = name
    # DuckDB adds to an existing rejects table; start each file with none
    con.execute(
        "DROP TABLE IF EXISTS staged; DROP TABLE IF EXISTS rejects_scratch; "
        "DROP TABLE IF EXISTS reject_scans"
    )
    con.execute(
        f"CREATE TEMP TABLE staged AS SELECT * FROM {_read_csv(path, facts.encoding, headers)}"
    )
    overlong = _overlong_lines(con, len(headers))
    rejected = con.execute(
        f"SELECT count(DISTINCT line) FROM rejects_scratch WHERE error_type <> '{TOO_MANY}'"
    ).fetchall()[0][0]
    select = [
        _sql_ident(source_of[c]) if c in source_of else "NULL::VARCHAR" for c in RAW_COLUMNS[table]
    ]
    select += [quoted(quarter.name), quoted(era)]
    con.execute(f"INSERT INTO {table} SELECT {', '.join(select)} FROM staged")
    rows = con.execute("SELECT count(*) FROM staged").fetchall()[0][0]
    overflow_values = sum(1 for o in overlong for v in o.get("dropped", "").split("$") if v)
    con.execute("DROP TABLE staged")
    return LoadedFile(
        table,
        quarter.name,
        f"{quarter.label}/{member}",
        facts.sha256,
        facts.bytes,
        facts.encoding,
        rows,
        rejected,
        era=era,
        overflow_values=overflow_values,
        renamed=renamed,
        overlong_lines=overlong,
    )


def _sql_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _load_deleted_list(
    con: duckdb.DuckDBPyConnection, quarter: Quarter, member: str, quarter_t: str, work: Path
) -> LoadedFile:
    """One deleted-case list: one caseid per line, no header, blank lines
    (FDA's lists can open with a lone space) skipped, values verbatim."""
    path = quarter.materialise(member, work)
    facts = file_facts(path)
    before = con.execute("SELECT count(*) FROM deleted").fetchall()[0][0]
    con.execute(
        f"INSERT INTO deleted SELECT caseid, {quoted(quarter_t)} FROM read_csv("
        f"{quoted(str(path))}, header=false, delim='$', quote='', escape='', "
        f"columns={{'caseid': 'VARCHAR'}}, null_padding=true, ignore_errors=true, "
        f"strict_mode=false, encoding={quoted(facts.encoding)}) "
        f"WHERE caseid IS NOT NULL AND trim(caseid) <> ''"
    )
    rows = con.execute("SELECT count(*) FROM deleted").fetchall()[0][0] - before
    return LoadedFile(
        "deleted",
        quarter_t,
        f"{quarter.label}/{member}",
        facts.sha256,
        facts.bytes,
        facts.encoding,
        rows,
        0,
    )


def load_quarter(con: duckdb.DuckDBPyConnection, quarter: Quarter, work: Path) -> list[LoadedFile]:
    """Every table of one quarter, then its deleted-case lists. A quarter's
    regular list is quarter_T '<quarter>'; FDA's one-off whole-history list
    (AllDeletedCases.txt, shipped in 2019Q1) is quarter_T 'pre<quarter>'."""
    loaded = [load_table_file(con, quarter, t, work) for t in TABLES]
    eras = {f.era for f in loaded}
    if len(eras) != 1:
        raise SourceError(
            f"{quarter.label}: files mix the AERS and FAERS layouts: {sorted(map(str, eras))}"
        )
    for member in quarter.all_deleted_files():
        loaded.append(_load_deleted_list(con, quarter, member, f"pre{quarter.name}", work))
    for member in quarter.deleted_files():
        loaded.append(_load_deleted_list(con, quarter, member, quarter.name, work))
    return loaded
