"""Build a release folder from a folder of FDA quarterly files.

    from open_altio.faers import build_release
    path = build_release("zips", "releases")   # releases/2026Q2

The release folder is the pipeline's whole output and the only thing anything
downstream reads (see src/open_altio/faers/README.md for its layout). It is built in a
hidden staging folder beside it and renamed into place at the end, so a
failed build never leaves a half release under a quarter's name.
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from importlib import metadata
from pathlib import Path

import duckdb

from open_altio import rulebook
from open_altio.faers.insights import numbers
from open_altio.faers.insights.methods import MethodsError, build_methods, refresh_cards
from open_altio.machine import peak_rss_bytes
from open_altio.rulebook import UserRules

from . import derive, drugnames, formats, meddra, statistics
from .atc import layer as classes
from .explorer_db import build_explorer_db
from .funnel import funnel
from .labels.build import LABEL_RULES, LABEL_TABLES, add_labels
from .labels.folder import find as find_labels
from .load import LoadedFile, create_raw_tables, load_quarter
from .reader import MANIFEST_FILE, quoted
from .rxnorm import layer as rxnorm
from .rxnorm.match import PairsRefused
from .rxnorm.rrf import RxNormRefused
from .schema import RAW_COLUMNS, derived_suffix, misnamed, table_columns
from .sources import Quarter, SourceError, discover, quarter_key, release_name

FORMAT_VERSION = 1
PARQUET_DIR = "parquet"
FUNNEL_FILE = "funnel.json"
VIEWS_FILE = "views.sql"
METHODS_FILE = "methods.json"  # the methods page data (src/open_altio/faers/insights/methods.py)

RAW_TABLES = tuple(RAW_COLUMNS)  # demo, drug, reac, outc, rpsr, ther, indi, deleted
DERIVED_TABLES = derive.DERIVED_TABLES
DERIVED_VIEWS = derive.DERIVED_VIEWS

VIEWS_HEADER = """-- The release's views, over its tables by name. Open each file listed under
-- "tables" in manifest.json as a view of the same name, then run this file.
"""


class ReleaseError(Exception):
    """A release this build will not write, said by name."""


def _check_legacy_countries(con: duckdb.DuckDBPyConnection) -> None:
    """Every legacy country name has its code in the mapping the
    legacy-country rule names (rules/legacy-country.md); a name it does not
    hold would leave those cases with no country_T."""
    unmapped = [r[0] for r in con.execute(derive.UNMAPPED_LEGACY_COUNTRIES).fetchall()]
    if unmapped:
        mapping = rulebook.value("legacy-country", "mapping")
        raise ReleaseError(
            f"refused: legacy reporter_country not in {mapping}: "
            + ", ".join(repr(v) for v in unmapped)
        )


# How far a build has got, for a progress bar: progress(step_title, steps_done, steps_in_all).
Progress = Callable[[str, int, int], None]

# A check a caller adds to the build's own: it reads the build's database before a byte of the
# release is written, and raises ReleaseError to refuse the release.
Check = Callable[[duckdb.DuckDBPyConnection], None]


def checks_before_write(
    con: duckdb.DuckDBPyConnection, checks: Sequence[Check] = (), layer: tuple[str, ...] = ()
) -> None:
    """Everything that must hold before a byte of the release is written, the caller's checks
    first; `layer` names the tables built beside the derive steps that the release carries."""
    for check in checks:
        check(con)
    _check_legacy_countries(con)
    problems = misnamed(con, DERIVED_TABLES + DERIVED_VIEWS + layer, RAW_TABLES)
    if problems:
        raise ReleaseError("refused: " + "; ".join(problems))


# How a table's rows are stored: by quarter, then report (or case), using
# whichever of these columns it has. Derived tables come out of their joins
# in no order; sorted, the per-quarter and per-report columns compress to a
# fraction (demo_latest_T and case_latest_T roughly halve), and readers skip
# row groups by quarter. zstd at level 9 takes about a tenth more off for a
# little more build time.
WRITE_ORDER = ("quarter_T", "primaryid", "case_key_T", "caseid")
PARQUET_OPTIONS = "FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9"


def _copy_statement(con: duckdb.DuckDBPyConnection, table: str, path: Path) -> str:
    cols = table_columns(con, table)
    order = ", ".join(f'"{c}"' for c in WRITE_ORDER if c in cols)
    query = f"SELECT * FROM {table}" + (f" ORDER BY {order}" if order else "")
    return f"COPY ({query}) TO {quoted(str(path))} ({PARQUET_OPTIONS})"


def inputs_hash(loaded: list[LoadedFile]) -> str:
    """One hash over every (table, quarter_T, file hash) triple, sorted: the
    data cut's identity. A quarter read from its zip and from its extracted
    folder gives the same hash."""
    triples = sorted((f.table, f.quarter, f.sha256) for f in loaded)
    return sha256(json.dumps(triples, separators=(",", ":")).encode()).hexdigest()


def _code_version() -> str:
    try:
        return metadata.version("open-altio")
    except metadata.PackageNotFoundError:
        return "unknown"


def _select_quarters(
    found: list[Quarter], quarter: str | None, only: Sequence[str] | None = None
) -> list[Quarter]:
    have = [q.name for q in found]
    if only is not None:
        exact = {name.lower() for name in only}
        if exact - set(have):
            raise SourceError(
                f"quarters {sorted(exact - set(have))} are not in the input (have {have})"
            )
        return [q for q in found if q.name in exact]
    if quarter is None:
        return found
    wanted = quarter.lower()
    if wanted not in have:
        raise SourceError(f"quarter {quarter} is not in the input (have {have})")
    return [q for q in found if quarter_key(q.name) <= quarter_key(wanted)]


def build_release(
    input_dir: str | Path,
    out_dir: str | Path,
    *,
    quarter: str | None = None,
    quarters: Sequence[str] | None = None,
    overwrite: bool = False,
    threads: int | None = None,
    memory_limit: str | None = None,
    temp_directory: str | Path | None = None,
    diana_dictionary: str | Path | None = None,
    meddra_dir: str | Path | None = None,
    rxnorm_dir: str | Path | None = None,
    labels: str | Path | None = None,
    say: Callable[[str], None] | None = None,
    checks: Sequence[Check] = (),
    progress: Progress | None = None,
    user_rules: UserRules | None = None,
) -> Path:
    """Build the release named by the latest FDA quarter in `input_dir` (or by
    `quarter`, ignoring anything later; or from exactly `quarters`) into `out_dir/<quarter>/`,
    under a person's own rules when given (rules.toml, `rulebook.load_user_rules`).

    `diana_dictionary` is the DiAna dictionary file rule drug-names pins by its
    checksum (downloaded there first when missing); with it the release carries
    `drug_substance_T` and `drug_ingredient_T`. `meddra_dir` is a MedDRA English
    ASCII release (the folder holding MedAscii/); with it the release has a
    licensed part, FDA's MedDRA terms read to that version (rule meddra-terms).
    With a `labels` folder (from labels-fetch) it adds the label tables.

    `rxnorm_dir` is the folder NLM's RxNorm Current Prescribable Content
    unpacks to, of the release rule rxnorm-ingredients pins; with it the
    release carries `drug_rxnorm_T` and records that release.

    Returns the release folder. Raises SourceError when the input is not
    what FDA publishes and ReleaseError when the release would break a rule,
    fails one of `checks`, already exists (pass overwrite=True to replace it),
    the person's rules would not build, or the MedDRA release is refused (a
    file missing, not English, or older than the data).
    """
    rules = user_rules or UserRules()
    problems = rulebook.check_user_rules(rules)
    if problems:
        raise ReleaseError("refused: your rules: " + " ".join(problems))
    with rulebook.use_user_rules(rules):
        return _build(
            input_dir,
            out_dir,
            quarter=quarter,
            quarters=quarters,
            overwrite=overwrite,
            threads=threads,
            memory_limit=memory_limit,
            temp_directory=temp_directory,
            diana_dictionary=diana_dictionary,
            meddra_dir=meddra_dir,
            rxnorm_dir=rxnorm_dir,
            labels=labels,
            say=say or (lambda _line: None),
            progress=progress or (lambda _title, _done, _total: None),
            checks=checks,
            recorded=rulebook.differences(rules),
        )


def _build(
    input_dir: str | Path,
    out_dir: str | Path,
    *,
    quarter: str | None,
    quarters: Sequence[str] | None,
    overwrite: bool,
    threads: int | None,
    memory_limit: str | None,
    temp_directory: str | Path | None,
    diana_dictionary: str | Path | None,
    meddra_dir: str | Path | None,
    rxnorm_dir: str | Path | None,
    labels: str | Path | None,
    say: Callable[[str], None],
    progress: Progress,
    checks: Sequence[Check],
    recorded: dict,
) -> Path:
    started = time.monotonic()
    try:
        licensed = meddra.source(meddra_dir) if meddra_dir is not None else None
    except meddra.MeddraRefused as e:
        raise ReleaseError(f"refused: MedDRA: {e}") from e
    chosen = _select_quarters(discover(Path(input_dir).expanduser()), quarter, quarters)
    labels_off = [r for r in LABEL_RULES if not rulebook.is_on(r)]
    if labels and not labels_off:
        find_labels(labels)  # a labels folder missing a file is refused before FDA's files load
    release = release_name(chosen[-1].name)
    steps = len(chosen) + 4
    out = Path(out_dir).expanduser()
    target = out / release
    if target.exists() and not overwrite:
        raise ReleaseError(f"release {target} already exists; pass overwrite=True to replace it")
    staging = out / f".{release}.building"
    work = staging / "_work"
    if staging.exists():
        shutil.rmtree(staging)
    (staging / PARQUET_DIR).mkdir(parents=True)
    work.mkdir()

    con = duckdb.connect(str(work / "build.duckdb"))
    try:
        con.execute("SET preserve_insertion_order = false")
        con.execute("SET enable_progress_bar = false")
        spill = Path(temp_directory).expanduser() if temp_directory else work / "spill"
        con.execute(f"SET temp_directory = {quoted(str(spill))}")
        if memory_limit:
            con.execute(f"SET memory_limit = {quoted(memory_limit)}")
        if threads:
            con.execute(f"SET threads = {int(threads)}")
        create_raw_tables(con)
        loaded: list[LoadedFile] = []
        for n, q in enumerate(chosen):
            progress(f"Reading FDA's files for {release_name(q.name)}", n, steps)
            t0 = time.monotonic()
            files = load_quarter(con, q, work / "extract")
            loaded += files
            shutil.rmtree(work / "extract", ignore_errors=True)
            demo_rows = next(f.rows for f in files if f.table == "demo")
            say(f"{q.name} {files[0].era:6} demo={demo_rows} {time.monotonic() - t0:.1f}s")
        progress("Working out the cases", len(chosen), steps)
        for statement in derive.statements([q.name for q in chosen]):
            derive.run(con, statement)
        views_sql = "".join(f"{v};\n" for v in derive.view_statements())
        con.execute(views_sql)
        say("derived " + ", ".join(DERIVED_TABLES + DERIVED_VIEWS))
        try:
            names_entry = drugnames.build(con, diana_dictionary)
        except drugnames.DictionaryRefused as e:
            raise ReleaseError(f"refused: drug names: {e}") from e
        layer = tuple(names_entry.get("tables", ()))
        say("drug names: " + (", ".join(layer) if layer else names_entry["reason"]))
        try:  # after the drug names: the classes read drug_substance_T
            classes_entry = classes.build(con)
        except classes.LayerRefused as e:
            raise ReleaseError(f"refused: drug classes: {e}") from e
        class_tables = tuple(classes_entry.get("tables", ()))
        say("drug classes: " + (", ".join(class_tables) or classes_entry["reason"]))
        layer += class_tables
        try:
            rxnorm_entry = rxnorm.build(con, rxnorm_dir)
        except (RxNormRefused, PairsRefused) as e:
            raise ReleaseError(f"refused: RxNorm: {e}") from e
        if rxnorm_entry["present"]:
            layer += rxnorm.TABLES
        say(
            f"RxNorm {rxnorm_entry['release']}: "
            + (", ".join(rxnorm.TABLES) if rxnorm_entry["present"] else rxnorm_entry["reason"])
        )
        terms = None
        if licensed is not None:  # in the build's own database, so the methods cards count with it
            try:
                terms = meddra.map_licensed(con, licensed)
            except meddra.MeddraRefused as e:
                raise ReleaseError(f"refused: MedDRA: {e}") from e
            for line in meddra.report_lines(licensed.version, terms):
                say(line)
        if labels and not labels_off:
            labels_entry: dict = add_labels(con, labels, say)
            layer += LABEL_TABLES
        else:
            why = (
                f"rule {', '.join(labels_off)} switched off" if labels else "no labels folder given"
            )
            labels_entry = {"skipped": why}
            say(f"labels: skipped, {why}")
        checks_before_write(con, checks, layer)

        progress("Writing the release", len(chosen) + 1, steps)
        con.execute("SET preserve_insertion_order = true")  # COPY keeps the ORDER BY
        tables = {}
        for table in RAW_TABLES + DERIVED_TABLES + layer:
            rel = f"{PARQUET_DIR}/{table}.parquet"
            con.execute(_copy_statement(con, table, staging / rel))
            tables[table] = {
                "path": rel,
                "kind": "raw"
                if table in RAW_TABLES
                else "classes"
                if table in class_tables
                else "derived",
                "rows": con.execute(f"SELECT count(*) FROM {table}").fetchall()[0][0],
                "bytes": (staging / rel).stat().st_size,
            }
        views = {
            v: {"rows": con.execute(f"SELECT count(*) FROM {v}").fetchall()[0][0]}
            for v in DERIVED_VIEWS
        }
        funnel_doc = funnel(con, release)
        try:
            methods_doc = build_methods(
                con,
                funnel_doc,
                _code_version(),
                user_rules=recorded,
                classes=classes_entry,
            )
        except MethodsError as e:
            raise ReleaseError(f"refused: methods page: {e}") from e
        if licensed is not None and terms is not None:
            meddra.write_licensed(con, staging, release, licensed, terms)
    except BaseException:  # a refused or failed build leaves nothing behind
        con.close()
        shutil.rmtree(staging, ignore_errors=True)
        raise
    con.close()
    shutil.rmtree(work)

    (staging / VIEWS_FILE).write_text(VIEWS_HEADER + views_sql, encoding="utf-8")
    (staging / FUNNEL_FILE).write_text(json.dumps(funnel_doc, indent=2) + "\n", encoding="utf-8")
    (staging / METHODS_FILE).write_text(json.dumps(methods_doc, indent=2) + "\n", encoding="utf-8")
    progress("Counting the statistics", len(chosen) + 2, steps)
    scored, statistics_entry = statistics.build(
        staging, tables, memory_limit=memory_limit, threads=threads
    )
    tables |= scored
    say(
        "statistics: "
        + (f"{scored[statistics.TABLE]['rows']} pairs" if scored else statistics_entry["reason"])
    )
    by_class, class_entry = statistics.build_classes(
        staging, tables, memory_limit=memory_limit, threads=threads
    )
    tables |= by_class
    say(
        "class statistics: "
        + (
            ", ".join(f"level {v['level']} {v['pairs']} pairs" for v in class_entry["levels"])
            if by_class
            else class_entry["reason"]
        )
    )
    progress("Building the explorer's database", len(chosen) + 3, steps)
    explorer = build_explorer_db(staging, tables=tables, release=release)  # explorer.duckdb
    say(f"explorer database: {explorer['bytes']} bytes")
    manifest = {
        "format": formats.RELEASE,
        "format_version": FORMAT_VERSION,
        "release": release,
        "quarters": [q.name for q in chosen],
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "build_seconds": round(time.monotonic() - started, 3),
        "release_bytes": sum(p.stat().st_size for p in staging.rglob("*") if p.is_file()),
        "peak_rss_bytes": peak_rss_bytes(),
        "code_version": _code_version(),
        "duckdb_version": duckdb.__version__,
        "inputs_hash": inputs_hash(loaded),
        "inputs": [f.as_json() for f in loaded],
        "tables": tables,
        "views": {"file": VIEWS_FILE, "views": views},
        "funnel": FUNNEL_FILE,
        "methods": METHODS_FILE,
        "drug_names": names_entry,
        "classes": classes_entry,
        "statistics": statistics_entry,
        "rxnorm": rxnorm_entry,
        "labels": labels_entry,
        "explorer": explorer,
        "user_rules": recorded,
    }
    statistics.record_classes(manifest, by_class, class_entry)
    (staging / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # last, from what the release holds, as `python -m open_altio.faers methods` does on one
    # built: its cards again, with its statistics, then the story's numbers
    try:
        refresh_cards(staging, memory_limit=memory_limit, threads=threads)
    except MethodsError as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise ReleaseError(f"refused: methods page: {e}") from e
    # last, from what the release holds, as `python -m open_altio.faers methods` does on one built;
    # the release's size then counts what it added
    numbers.write(staging, memory_limit=memory_limit, threads=threads)
    manifest["release_bytes"] = sum(
        p.stat().st_size for p in staging.rglob("*") if p.is_file() and p != staging / MANIFEST_FILE
    )
    (staging / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    say("methods: the story's numbers and every rule's version")

    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)
    say(f"release {release}: {target}")
    progress("Release built", steps, steps)
    return target


__all__ = [
    "DERIVED_TABLES",
    "FORMAT_VERSION",
    "FUNNEL_FILE",
    "MANIFEST_FILE",
    "METHODS_FILE",
    "PARQUET_DIR",
    "RAW_TABLES",
    "DERIVED_VIEWS",
    "VIEWS_FILE",
    "Check",
    "Progress",
    "ReleaseError",
    "build_release",
    "derived_suffix",
]
