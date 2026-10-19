"""Read-only SQL over the live release, within the limits of rule sql-limits.

    sql = SqlService(live)                        # live: the explorer's LiveRelease
    db = sql.current(classes=True, by_pt=True)    # the live release's SqlDatabase, or NotLive
    with sql.slot(viewer.id):                     # Busy past concurrent_queries_per_user
        result = db.run(text, page=1)             # Result, or Refused / LimitHit
        rows = db.write(text, "parquet", target)  # the whole result to a file, or also TooLarge

A whole result is written as a file by sql_files.py, within its limits; the rows
reach the file through Arrow, so the locked-down connection never writes a file
itself.

What users can query: every table of the release (`manifest.json` `tables`,
one view of the same name over its Parquet file) and the release's
deduplicated views (`views.sql`, e.g. `case_dedup_T`). That is the release
exactly as downloaded, so a query written here runs unchanged on the full
release with `open_altio.faers.open_release`. A viewer who may not see WHO's
drug classes gets a database without the classes layer's tables (the
manifest's `classes` list): they are neither views nor allowed files there.
A viewer shown reactions as FDA wrote them gets one without the statistics
counted by current PT (statistics.by_current_pt), and queries the ones
counted by FDA's text instead.

How it is locked down, outermost first:
1. Only one statement, and it must be a SELECT (DuckDB's own parser,
   `duckdb.extract_statements`), so COPY, ATTACH, INSTALL, LOAD, PRAGMA,
   SET, EXPORT, CREATE and the rest never reach DuckDB.
2. The views live in a small catalog file written once per release in a
   private temporary folder, then opened read only: nothing can be created
   in it.
3. After opening: external access off with only the release's Parquet files
   allowed (read only), extension autoload and autoinstall off, memory limit
   and threads from the rule, and the configuration locked so no query can
   change any of it.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import tempfile
import threading
import time
import weakref
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from open_altio.faers import MANIFEST_FILE, read_manifest, register_release
from open_altio.faers.reader import quoted
from open_altio.faers.statistics import by_current_pt
from open_altio.rulebook import value

from .release import LiveRelease
from .sql_files import BATCH_ROWS, check_download, write_batches

CATALOG_FILE = "sql_catalog.duckdb"


# Each way a query does not run carries its HTTP status and the outcome a usage log keeps.


class Refused(Exception):
    """The query is not allowed or could not be read; the message says why in plain words."""

    status = 400
    outcome = "refused"


class Busy(Exception):
    """The person already has as many queries running as rule sql-limits allows."""

    status = 429
    outcome = "busy"


class LimitHit(Exception):
    """A query hit a hard limit (`outcome` is "timeout" or "memory")."""

    status = 422

    def __init__(self, outcome: str, message: str) -> None:
        super().__init__(message)
        self.outcome = outcome


@dataclass(frozen=True)
class Result:
    columns: list[str]
    rows: list[tuple[Any, ...]]  # one page: at most rule sql-limits rows_shown
    total: int  # rows the whole query gives
    page: int  # which page these are, from 1
    size: int  # rows a page holds (rows_shown)
    seconds: float


@dataclass(frozen=True)
class Relation:
    name: str
    kind: str  # "table" (a release table) or "view" (a deduplicated view)
    columns: list[tuple[str, str]]  # (name, DuckDB type)


def single_select(text: str) -> str:
    """The query, if it is exactly one SELECT statement; otherwise Refused.
    Comments and casing make no difference: DuckDB's parser decides."""
    if not text.strip():
        raise Refused("Write a query first.")
    try:
        statements = duckdb.extract_statements(text)
    except duckdb.Error as exc:
        raise Refused(f"DuckDB could not read that query. {_first_line(exc)}") from None
    if not statements:
        raise Refused("Write a query first.")
    if len(statements) > 1:
        raise Refused("Run one statement at a time: only a single SELECT is allowed here.")
    kind = statements[0].type
    # DuckDB runs a bare PRAGMA as a SELECT; refuse it all the same
    if kind == duckdb.StatementType.SELECT and _first_word(text) == "PRAGMA":
        kind = duckdb.StatementType.PRAGMA
    if kind != duckdb.StatementType.SELECT:
        raise Refused(
            f"Only SELECT queries can run here; this is a {kind.name} statement. "
            "SQL here is read only: nothing can be written, attached, installed or changed."
        )
    return text


def _first_word(text: str) -> str:
    """The statement's first word, comments skipped (DuckDB's tokenizer)."""
    tokens = duckdb.tokenize(text)
    if not tokens:
        return ""
    found = re.match(r"\w+", text[tokens[0][0] :])
    return found.group(0).upper() if found else ""


def _first_line(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__


def _limit_message(kind: str) -> str:
    if kind == "timeout":
        seconds = value("sql-limits", "timeout_seconds")
        what = f"The query ran longer than {seconds} seconds and was stopped."
    else:
        memory = value("sql-limits", "memory_limit_gb")
        what = f"The query needed more than the {memory} GB of memory SQL may use."
    return (
        f"{what} Narrow it (fewer columns, a filter, an aggregate), or download the full release "
        "and run it on your own machine."
    )


def withheld(manifest: dict[str, Any], *, classes: bool, by_pt: bool) -> tuple[str, ...]:
    """The release's tables a viewer is not given: the drug classes layer's without WHO's
    classes (`classes`), and the statistics counted by current PT when their reactions are FDA's
    text (`by_pt`, Viewer.named_by_meddra)."""
    layer = () if classes else tuple((manifest.get("classes") or {}).get("tables") or ())
    return layer + (() if by_pt else by_current_pt(manifest))


class SqlDatabase:
    """The live release as a locked-down, read-only DuckDB catalog. Thread-safe:
    every query runs on its own cursor."""

    def __init__(self, folder: Path, *, classes: bool = True, by_pt: bool = True) -> None:
        self.folder = folder
        manifest = read_manifest(folder)
        self.name: str = manifest["release"]
        entry = manifest.get("classes") or {}
        hidden = set(withheld(manifest, classes=classes, by_pt=by_pt))
        manifest["tables"] = {k: v for k, v in manifest["tables"].items() if k not in hidden}
        # WHO's citation, in every Parquet result from a database that holds its codes
        self.notes = (
            {"who_atc_citation": str(entry["citation"])} if classes and entry.get("present") else {}
        )
        self._workdir = Path(tempfile.mkdtemp(prefix="open-altio-sql-"))
        # The folder goes when this database is closed or garbage collected.
        self._cleanup = weakref.finalize(self, shutil.rmtree, self._workdir, True)
        catalog = self._workdir / CATALOG_FILE
        build = duckdb.connect(str(catalog))
        try:
            register_release(build, folder, tables=manifest["tables"])
        finally:
            build.close()
        parquet = [str(folder / entry["path"]) for entry in manifest["tables"].values()]
        self._con = duckdb.connect(
            str(catalog),
            read_only=True,
            config={
                "autoload_known_extensions": False,
                "autoinstall_known_extensions": False,
                "memory_limit": f"{value('sql-limits', 'memory_limit_gb')}GiB",
                "threads": int(value("sql-limits", "threads")),
            },
        )
        allowed = ", ".join(quoted(p) for p in parquet)
        self._con.execute(f"SET allowed_paths = [{allowed}]")
        self._con.execute("SET enable_external_access = false")
        self._con.execute("SET lock_configuration = true")
        tables = set(manifest["tables"])
        self.schema = self._schema(tables)

    def close(self) -> None:
        self._con.close()
        self._cleanup()

    def _schema(self, tables: set[str]) -> list[Relation]:
        cur = self._con.cursor()
        try:
            rows = cur.execute(
                "SELECT table_name, column_name, data_type FROM duckdb_columns() "
                "WHERE database_name = current_database() AND schema_name = 'main' "
                "ORDER BY table_name, column_index"
            ).fetchall()
        finally:
            cur.close()
        by_name: dict[str, list[tuple[str, str]]] = {}
        for table, column, dtype in rows:
            by_name.setdefault(table, []).append((column, dtype))
        relations = [
            Relation(n, "table" if n in tables else "view", cols) for n, cols in by_name.items()
        ]
        return sorted(relations, key=lambda r: (r.kind != "table", r.name))

    def run(self, text: str, page: int = 1) -> Result:
        """Run one SELECT within the rule's limits: count the rows it gives,
        then fetch one page of rows_shown of them (the last page when `page`
        is past the end). Both steps share one timeout_seconds."""
        body = _paged(single_select(text))
        size = int(value("sql-limits", "rows_shown"))
        cur = self._con.cursor()
        started = time.monotonic()
        try:
            with _deadline(cur):
                total = _count(cur, body)
                page = max(1, min(int(page), -(-total // size) or 1))
                cur.execute(
                    single_select(
                        f"SELECT * FROM (\n{body}\n) LIMIT {size} OFFSET {(page - 1) * size}"
                    )
                )
                columns = [d[0] for d in cur.description or []]
                rows = cur.fetchall()
        finally:
            cur.close()
        return Result(
            columns=columns,
            rows=rows,
            total=total,
            page=page,
            size=size,
            seconds=time.monotonic() - started,
        )

    def write(self, text: str, fmt: str, target: Path) -> int:
        """Write the whole result of one SELECT to `target` as CSV (with a
        header line) or Parquet, and return its rows. Counting and writing
        share one timeout_seconds; past the row limits it is TooLarge and
        nothing is written."""
        body = _paged(single_select(text))
        cur = self._con.cursor()
        try:
            with _deadline(cur):
                total = _count(cur, body)
                check_download(total, fmt)
                cur.execute(single_select(f"SELECT * FROM (\n{body}\n)"))
                write_batches(cur.to_arrow_reader(BATCH_ROWS), fmt, target, self.notes)
        finally:
            cur.close()
        return total


@contextlib.contextmanager
def _deadline(cur: duckdb.DuckDBPyConnection) -> Iterator[None]:
    """Interrupt the cursor's work past rule sql-limits timeout_seconds, and
    turn DuckDB's errors into Refused or LimitHit."""
    timeout = float(value("sql-limits", "timeout_seconds"))
    done = threading.Event()
    timed_out = threading.Event()

    def watch() -> None:
        # Keep interrupting past the deadline until the query has stopped,
        # so an interrupt that lands between steps is not lost.
        if done.wait(timeout):
            return
        timed_out.set()
        while not done.is_set():
            cur.interrupt()
            done.wait(0.05)

    watcher = threading.Thread(target=watch, name="sql-timeout", daemon=True)
    watcher.start()
    try:
        yield
    except duckdb.InterruptException:
        raise LimitHit("timeout", _limit_message("timeout")) from None
    except duckdb.OutOfMemoryException:
        raise LimitHit("memory", _limit_message("memory")) from None
    except duckdb.Error as exc:
        if timed_out.is_set():
            raise LimitHit("timeout", _limit_message("timeout")) from None
        raise Refused(f"DuckDB could not run that query. {_first_line(exc)}") from None
    except pa.ArrowException as exc:
        if timed_out.is_set():  # an interrupt while Arrow was reading the rows
            raise LimitHit("timeout", _limit_message("timeout")) from None
        raise Refused(f"The result could not be written as a file. {_first_line(exc)}") from None
    finally:
        done.set()
        watcher.join()


def _count(cur: duckdb.DuckDBPyConnection, body: str) -> int:
    """How many rows the query gives."""
    return int(cur.execute(single_select(f"SELECT count(*) FROM (\n{body}\n)")).fetchall()[0][0])


def _paged(text: str) -> str:
    """The query without a final semicolon, so it can stand inside a subquery
    (it is put on lines of its own there, so a trailing comment ends before
    the closing bracket)."""
    tokens = duckdb.tokenize(text)
    if tokens and text[tokens[-1][0]] == ";":
        return text[: tokens[-1][0]]
    return text


class SqlService:
    """Opens the live release for SQL (again when the folder or the limits
    change) and counts each person's running queries."""

    def __init__(self, release: LiveRelease) -> None:
        self.release = release
        self._lock = threading.Lock()
        # with WHO's classes or without them, and by current PT or by FDA's text
        self._open: dict[tuple[bool, bool], SqlDatabase] = {}
        self._key: tuple | None = None
        self._running: dict[str, int] = {}

    def current(self, *, classes: bool, by_pt: bool) -> SqlDatabase:
        """The live release for SQL, with WHO's drug classes or without them, and with the
        statistics counted by current PT or without them."""
        folder = self.release.folder()
        stat = (folder / MANIFEST_FILE).stat()
        key = (
            folder,
            stat.st_ino,
            stat.st_mtime_ns,
            value("sql-limits", "memory_limit_gb"),
            value("sql-limits", "threads"),
        )
        with self._lock:
            # The old database is left to the garbage collector, so a query
            # still running on it finishes.
            if self._key != key:
                self._open, self._key = {}, key
            if (classes, by_pt) not in self._open:
                self._open[classes, by_pt] = SqlDatabase(folder, classes=classes, by_pt=by_pt)
            return self._open[classes, by_pt]

    @contextlib.contextmanager
    def slot(self, who: str) -> Iterator[None]:
        """Hold one of `who`'s query slots for the block; Busy if none is free."""
        allowed = int(value("sql-limits", "concurrent_queries_per_user"))
        with self._lock:
            if self._running.get(who, 0) >= allowed:
                raise Busy(
                    "You already have a query running. Wait for it to finish, then run this one. "
                    f"Each person may run {allowed} at a time."
                )
            self._running[who] = self._running.get(who, 0) + 1
        try:
            yield
        finally:
            with self._lock:
                self._running[who] -= 1
                if not self._running[who]:
                    del self._running[who]
