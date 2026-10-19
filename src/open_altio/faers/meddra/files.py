"""MedDRA's ASCII release files: which of them the licensed part reads, and reading them."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa

ENCODING = "latin-1"
SUBDIR = "MedAscii"
RELEASE_FILE = "meddra_release.asc"

# The release files read: table, the fields taken (MedDRA's distribution file
# format), their positions, and the field count a record must reach.
FILES: dict[str, tuple[str, tuple[str, ...], tuple[int, ...], int]] = {
    "soc.asc": ("meddra_soc", ("soc_code", "soc_name", "soc_abbrev"), (0, 1, 2), 3),
    "hlgt.asc": ("meddra_hlgt", ("hlgt_code", "hlgt_name"), (0, 1), 2),
    "hlt.asc": ("meddra_hlt", ("hlt_code", "hlt_name"), (0, 1), 2),
    "pt.asc": ("meddra_pt", ("pt_code", "pt_name", "pt_soc_code"), (0, 1, 3), 4),
    "llt.asc": (
        "meddra_llt",
        ("llt_code", "llt_name", "pt_code", "llt_currency"),
        (0, 1, 2, 9),
        10,
    ),
    "mdhier.asc": (
        "meddra_mdhier",
        (
            "pt_code",
            "hlt_code",
            "hlgt_code",
            "soc_code",
            "pt_name",
            "hlt_name",
            "hlgt_name",
            "soc_name",
            "soc_abbrev",
            "null_field",
            "pt_soc_code",
            "primary_soc_fg",
        ),
        tuple(range(12)),
        12,
    ),
    "soc_hlgt.asc": ("meddra_soc_hlgt", ("soc_code", "hlgt_code"), (0, 1), 2),
    "hlgt_hlt.asc": ("meddra_hlgt_hlt", ("hlgt_code", "hlt_code"), (0, 1), 2),
    "hlt_pt.asc": ("meddra_hlt_pt", ("hlt_code", "pt_code"), (0, 1), 2),
    "smq_list.asc": (
        "meddra_smq_list",
        (
            "smq_code",
            "smq_name",
            "smq_level",
            "smq_description",
            "smq_source",
            "smq_note",
            "meddra_version",
            "status",
            "smq_algorithm",
        ),
        tuple(range(9)),
        9,
    ),
    "smq_content.asc": (
        "meddra_smq_content",
        (
            "smq_code",
            "term_code",
            "term_level",
            "term_scope",
            "term_category",
            "term_weight",
            "term_status",
            "term_addition_version",
            "term_last_modified_version",
        ),
        tuple(range(9)),
        9,
    ),
    # every term's additions (A), demotions (D) and updates (U, a rename among them) since 2.1
    "meddra_history_english.asc": (
        "meddra_history",
        ("term_code", "term_name", "version", "term_type", "llt_currency", "action"),
        tuple(range(6)),
        6,
    ),
}
VERBATIM_TABLES = tuple(spec[0] for spec in FILES.values())


class MeddraRefused(Exception):
    """The MedDRA input or the release is not what this step accepts; the message says why."""


def _records(path: Path, least: int) -> Iterator[list[str]]:
    with path.open(encoding=ENCODING) as fh:
        for n, line in enumerate(fh, start=1):
            line = line.rstrip("\r\n")
            if not line:
                continue
            fields = line.split("$")
            if fields and fields[-1] == "":
                fields.pop()
            if len(fields) < least:
                raise MeddraRefused(
                    f"{path.name} line {n}: expected at least {least} fields, found {len(fields)}"
                )
            yield fields


def ascii_folder(directory: str | Path) -> Path:
    """The folder holding the files: `directory` itself, or its MedAscii/."""
    root = Path(directory).expanduser()
    return root / SUBDIR if (root / SUBDIR).is_dir() else root


def read_release_file(where: Path) -> tuple[str, str]:
    """(version, language) from meddra_release.asc."""
    path = where / RELEASE_FILE
    if not path.is_file():
        raise MeddraRefused(f"not in {where}: {RELEASE_FILE}")
    for fields in _records(path, 2):
        return fields[0].strip(), fields[1].strip()
    raise MeddraRefused(f"{path} is empty")


def read_table(where: Path, name: str) -> pa.Table:
    """One of FILES as a table of text, its fields trimmed."""
    _, cols, take, least = FILES[name]
    columns: list[list[str]] = [[] for _ in cols]
    for fields in _records(where / name, least):
        for i, pos in enumerate(take):
            columns[i].append(fields[pos].strip())
    return pa.table({c: pa.array(v, type=pa.string()) for c, v in zip(cols, columns, strict=True)})


def check_ascii(directory: str | Path) -> tuple[str, str]:
    """(version, language) of a MedDRA ASCII release, once every file FILES
    reads is there and parses. Raises MeddraRefused naming the first file
    missing or broken."""
    where = ascii_folder(directory)
    missing = [n for n in FILES if not (where / n).is_file()]
    if missing:
        raise MeddraRefused(f"missing: {', '.join(missing)}")
    version, language = read_release_file(where)
    for name in FILES:
        read_table(where, name)
    return version, language
