"""A whole SQL result as a file: CSV with a header line, or Parquet. It downloads up to rule
sql-result-download `max_rows`, and as CSV only while it fits rule export-csv-row-cap with
its header line; past either it is refused (TooLarge) with a pointer to the table downloads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq

from open_altio.rulebook import value

from .export import csv_fits, csv_row_cap


class TooLarge(Exception):
    """A whole result too big to download; the message points to the table downloads."""

    status = 409
    outcome = "too_large"


def download_rows() -> int:
    """The most rows a SQL result may download (rule sql-result-download)."""
    return int(value("sql-result-download", "max_rows"))


BATCH_ROWS = 100_000  # rows Arrow hands the file at a time


def check_download(rows: int, fmt: str) -> None:
    """TooLarge past rule sql-result-download, or, for CSV, past rule export-csv-row-cap."""
    most = download_rows()
    if rows > most:
        raise TooLarge(
            f"This result has {rows:,} rows, more than the {most:,} a SQL result can download. "
            "Download the tables it reads instead, from the list of tables on this page, "
            "and run the query on your own machine."
        )
    if fmt == "csv" and not csv_fits(rows):
        raise TooLarge(
            f"This result has {rows:,} rows; with its header line that is more than the "
            f"{csv_row_cap():,} lines Excel opens, so it does not come as CSV. Download it as "
            "Parquet, or download the tables it reads from the list of tables on this page."
        )


def _plain_for_csv(t: pa.DataType) -> bool:
    return (
        pa.types.is_integer(t)
        or pa.types.is_floating(t)
        or pa.types.is_decimal(t)
        or pa.types.is_boolean(t)
        or pa.types.is_string(t)
        or pa.types.is_large_string(t)
        or pa.types.is_date(t)
        or pa.types.is_timestamp(t)
        or pa.types.is_time(t)
        or pa.types.is_null(t)
    )


def _as_text(v: Any) -> str | None:
    """A value CSV cannot hold as it is, as text: a list joined with ';' (as
    the filtered export joins outcomes_T), anything else as JSON."""
    if v is None:
        return None
    if isinstance(v, list):
        return ";".join("" if x is None else str(x) for x in v)
    if isinstance(v, (dict, tuple)):
        return json.dumps(v, default=str)
    return str(v)


def write_batches(
    reader: pa.RecordBatchReader, fmt: str, target: Path, notes: dict[str, str] | None = None
) -> None:
    """Write the result; `notes` go in a Parquet file's metadata (CSV has no place for them)."""
    if fmt == "parquet":
        schema = reader.schema.with_metadata({**(reader.schema.metadata or {}), **(notes or {})})
        with pq.ParquetWriter(target, schema) as out:
            for batch in reader:
                out.write_batch(batch)
        return
    fields = list(reader.schema)
    plain = [_plain_for_csv(f.type) for f in fields]
    schema = pa.schema(
        [f if ok else pa.field(f.name, pa.string()) for f, ok in zip(fields, plain, strict=True)]
    )
    with pa_csv.CSVWriter(target, schema) as out:
        for batch in reader:
            columns = [
                col if ok else pa.array([_as_text(v) for v in col.to_pylist()], pa.string())
                for col, ok in zip(batch.columns, plain, strict=True)
            ]
            out.write_batch(pa.RecordBatch.from_arrays(columns, schema=schema))


__all__ = [
    "BATCH_ROWS",
    "TooLarge",
    "check_download",
    "download_rows",
    "write_batches",
]
