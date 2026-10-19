"""Find FDA's quarterly files in an input folder and hand them to the loader.

An input folder holds FDA quarterly zips as downloaded (`aers_ascii_2004q1.zip`,
`faers_ascii_2012q4.zip`, ...), extracted quarter folders (`2004q1/`,
`faers_ascii_2026q2/`, ...), or both for different quarters. Inside a quarter
the files are found by name, case-blind and at any depth, because FDA's own
layout moved over the years: `ascii/DEMO04Q1.TXT`, `ascii/demo12q4.txt`,
`ascii/DEMO18Q1_new.txt`, `ASCII/DEMO26Q2.txt`, and the deleted-case lists
`deleted/ADR19Q1DeletedCases.txt`, `Deleted/21Q1DeletedCases.txt`,
`Deleted/DELETE26Q2.txt` and the one-off `AllDeletedCases.txt`.
"""

from __future__ import annotations

import codecs
import hashlib
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .schema import TABLES

QUARTER = re.compile(r"(?<!\d)(\d{4})q([1-4])(?!\d)", re.IGNORECASE)


def _table_pattern(table: str) -> re.Pattern[str]:
    return re.compile(rf"(^|/){table}\d\dq\d(_new)?\.txt$", re.IGNORECASE)


TABLE_FILE = {t: _table_pattern(t) for t in TABLES}
DELETED_FILE = re.compile(r"(delete\d\dq\d|(adr)?\d\dq\ddeletedcases)\.txt$", re.IGNORECASE)
ALL_DELETED_FILE = re.compile(r"alldeletedcases\.txt$", re.IGNORECASE)


class SourceError(Exception):
    """The input folder does not hold what a build needs, said by name."""


def quarter_key(quarter: str) -> int:
    """'2012q4' -> 20124, sortable."""
    return int(quarter[:4]) * 10 + int(quarter[5])


def release_name(quarter: str) -> str:
    """'2026q2' -> '2026Q2', the name FDA's quarter gives a release."""
    return quarter.upper()


@dataclass
class Quarter:
    """One FDA quarter in the input: a zip or an extracted folder."""

    name: str  # '2012q4', the form quarter_T takes
    path: Path
    is_zip: bool
    members: list[str] = field(default_factory=list)  # posix paths inside

    @property
    def label(self) -> str:
        return self.path.name

    def find(self, pattern: re.Pattern[str]) -> list[str]:
        return sorted(m for m in self.members if pattern.search(m))

    def table_file(self, table: str) -> str:
        found = self.find(TABLE_FILE[table])
        if len(found) != 1:
            raise SourceError(
                f"{self.label}: expected one {table.upper()} file, found {len(found)}: {found}"
            )
        return found[0]

    def deleted_files(self) -> list[str]:
        return self.find(DELETED_FILE)

    def all_deleted_files(self) -> list[str]:
        return self.find(ALL_DELETED_FILE)

    def materialise(self, member: str, work: Path) -> Path:
        """A real file on disk for one member: the folder's own file, or the
        zip member extracted into `work`."""
        if not self.is_zip:
            return self.path / member
        target = work / self.name / PurePosixPath(member)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(self.path) as z, z.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        return target


def _members_of_folder(folder: Path) -> list[str]:
    return [p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()]


def _members_of_zip(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        return [i.filename for i in z.infolist() if not i.is_dir()]


def discover(input_dir: str | Path) -> list[Quarter]:
    """Every quarter in the input folder, oldest first."""
    root = Path(input_dir)
    if not root.is_dir():
        raise SourceError(f"input folder {root} does not exist")
    found: dict[str, Quarter] = {}
    for entry in sorted(root.iterdir()):
        m = QUARTER.search(entry.name)
        if not m or entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix.lower() == ".zip":
            q = Quarter(f"{m.group(1)}q{m.group(2)}", entry, True, _members_of_zip(entry))
        elif entry.is_dir():
            q = Quarter(f"{m.group(1)}q{m.group(2)}", entry, False, _members_of_folder(entry))
        else:
            continue
        if q.name in found:
            raise SourceError(
                f"quarter {q.name} is in the input twice: {found[q.name].label} and {q.label}"
            )
        found[q.name] = q
    if not found:
        raise SourceError(f"no FDA quarter zips or folders in {root}")
    return sorted(found.values(), key=lambda q: quarter_key(q.name))


@dataclass(frozen=True)
class FileFacts:
    sha256: str
    bytes: int
    encoding: str  # 'utf-8' or 'latin-1'


def sha256(path: Path) -> str:
    """The file's sha256, read in one streamed pass."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_facts(path: Path) -> FileFacts:
    """Hash and size in one streamed pass, and the encoding the loader reads
    the file with: UTF-8 when every byte decodes as UTF-8, else Latin-1, found
    without reading the whole file into memory."""
    h = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")()
    utf8 = True
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
            if utf8:
                try:
                    decoder.decode(chunk)
                except UnicodeDecodeError:
                    utf8 = False
    if utf8:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            utf8 = False
    return FileFacts(h.hexdigest(), size, "utf-8" if utf8 else "latin-1")
