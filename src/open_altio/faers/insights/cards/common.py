"""What every insight card is made of: its query, its chart, its tag, and the words its
sentences put numbers in."""

from __future__ import annotations

import warnings
from typing import Any

import duckdb

DOCUMENTED = {"kind": "documented"}
FIRST_YEAR = 2004  # FDA's quarterly files begin in 2004Q1; earlier years hold a handful of cases


class MissingDataWarning(UserWarning):
    """A card could not read a table or column it needs and shows no data."""


def changed(step: str, *rules: str) -> dict:
    """The tag of a card a funnel step acts on, naming the rules whose evidence it is."""
    return {"kind": "changed_pipeline", "step": step, "rules": list(rules)}


def query(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[tuple]:
    """The query's rows, or none where the data lacks a table or column the
    card needs (a small or partial release): the card then shows no data."""
    try:
        return con.execute(sql, params or []).fetchall()
    except (duckdb.CatalogException, duckdb.BinderException) as e:
        warnings.warn(f"insight card shows no data: {e}", MissingDataWarning, stacklevel=2)
        return []


def quarters(con: duckdb.DuckDBPyConnection, since: str | None = None) -> list[str]:
    """Every quarter in the data, oldest first, optionally from `since` on."""
    rows = query(con, "SELECT quarter_T FROM quarters_T ORDER BY qnum_T")
    return [q for (q,) in rows if since is None or q >= since]


def quarter_label(q: str) -> str:
    return q.upper()


def series(rows: list[tuple], xs: list, names: list[str]) -> list[dict]:
    """rows of (x, series name, value) laid out as one value per x per series."""
    cell = {(x, name): value for x, name, value in rows}
    return [{"name": name, "values": [_num(cell.get((x, name))) for x in xs]} for name in names]


def zeros(lines: list[dict]) -> list[dict]:
    """The series with a missing value read as 0: an x with none of a kind holds 0 of it, not
    missing data."""
    for line in lines:
        line["values"] = [0 if v is None else v for v in line["values"]]
    return lines


def _num(v: Any) -> int | float | None:
    if v is None:
        return None
    f = float(v)
    return int(f) if f.is_integer() else round(f, 2)


def chart(
    kind: str,
    x_label: str,
    x_kind: str,
    xs: list,
    y_label: str,
    unit: str,
    lines: list[dict],
    question: str | None = None,
    note: tuple | None = None,
) -> dict:
    """The chart, with the question it answers above it and a note, (x, text),
    labelling the x value that matters, when given."""
    label = quarter_label if x_kind == "quarter" else (lambda x: x)
    out = {
        "type": kind,
        "x": {"label": x_label, "kind": x_kind, "values": [label(x) for x in xs]},
        "y": {"label": y_label, "unit": unit},
        "series": lines,
    }
    if question:
        out["question"] = question
    if note and note[0] in xs:
        out["note"] = {"x": label(note[0]), "text": note[1]}
    return out


def card(id_: str, title: str, two_sentences: str, chart: dict, tag: dict, notebook: str) -> dict:
    return {
        "id": id_,
        "title": title,
        "two_sentences": two_sentences,
        "chart": chart,
        "tag": tag,
        "notebook": notebook,
    }


def pct(part: int, whole: int, digits: int = 0) -> str:
    return f"{100.0 * part / whole:.{digits}f}%" if whole else "0%"


def plural(count: int, noun: str) -> str:
    """1 line, 3 lines."""
    return f"{count:,} {noun}" + ("" if count == 1 else "s")
