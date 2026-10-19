"""Find and read the files `labels-fetch` puts in a labels folder, and the daily update files
`labels-refresh` adds to it (rule label-source). DailyMed names each label in both as
`<yyyymmdd>_<set id>.zip`, by the day it published that version."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath

from open_altio import rulebook

RULE = "label-source"


class LabelsFolderError(Exception):
    """The labels folder does not hold what the labels step reads, said by name."""


@dataclass(frozen=True)
class LabelsFolder:
    parts: tuple[Path, ...]  # the human prescription full release, part 1 first
    mapping: Path  # DailyMed's labels to RxNorm file
    rxnorm: Path  # RxNorm's current prescribable content

    def files(self) -> list[dict]:
        """Each file's name and size, for the manifest; never its path,
        which is a place on one person's machine."""
        return [
            {"name": p.name, "bytes": p.stat().st_size}
            for p in (*self.parts, self.mapping, self.rxnorm)
        ]


def _part_number(path: Path) -> int:
    found = re.search(r"(\d+)\.zip$", path.name)
    return int(found.group(1)) if found else 0


def find(folder: str | Path) -> LabelsFolder:
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise LabelsFolderError(f"labels folder {root} does not exist")
    parts = sorted(root.glob(rulebook.value(RULE, "release_file_glob")), key=_part_number)
    mapping = root / rulebook.value(RULE, "mapping_file")
    rxnorm = sorted(root.glob(rulebook.value(RULE, "rxnorm_file_glob")))
    missing = []
    if not parts:
        missing.append(rulebook.value(RULE, "release_file_glob"))
    if not mapping.is_file():
        missing.append(mapping.name)
    if not rxnorm:
        missing.append(rulebook.value(RULE, "rxnorm_file_glob"))
    if missing:
        raise LabelsFolderError(
            f"labels folder {root} lacks {', '.join(missing)}; run labels-fetch into it"
        )
    if len(rxnorm) > 1:
        raise LabelsFolderError(
            f"labels folder {root} holds {len(rxnorm)} RxNorm releases; keep one"
        )
    return LabelsFolder(tuple(parts), mapping, rxnorm[0])


def products_by_label(mapping: Path) -> dict[str, list[str]]:
    """Set ID (lower case) -> the RxNorm product codes DailyMed maps it to.
    The file is `SETID|SPL_VERSION|RXCUI|RXSTRING|RXTTY`, one row per name
    of each code, so a code is listed once however many names it has."""
    out: dict[str, dict[str, None]] = {}
    with zipfile.ZipFile(mapping) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        with z.open(name) as raw:
            lines = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            header = next(lines).rstrip("\r\n").split("|")
            set_at, code_at = header.index("SETID"), header.index("RXCUI")
            for line in lines:
                fields = line.rstrip("\r\n").split("|")
                if len(fields) > max(set_at, code_at):
                    out.setdefault(fields[set_at].lower(), {})[fields[code_at]] = None
    return {k: list(v) for k, v in out.items()}


def members(part: Path) -> list[str]:
    """The names of every file in a zip, read from its directory alone."""
    with zipfile.ZipFile(part) as z:
        return z.namelist()


def label_xml(part: Path, only: list[str] | None = None) -> Iterator[tuple[str, bytes]]:
    """(member name, SPL XML) of every label in one part of the release, or of `only` those.
    Each label is a zip of its own inside the part, holding the XML and
    the label's pictures; only the XML is read."""
    with zipfile.ZipFile(part) as outer:
        names = only if only is not None else outer.namelist()
        for name in names:
            if name.lower().endswith(".zip"):
                yield name, read_member(outer, name)


def read_member(outer: zipfile.ZipFile, member: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(outer.read(member))) as inner:
        xml = sorted(n for n in inner.namelist() if n.lower().endswith(".xml"))
        if len(xml) != 1:
            raise LabelsFolderError(f"{member}: expected one XML file, found {len(xml)}")
        return inner.read(xml[0])


def set_of(member: str) -> str:
    """The set ID a label's file is named by."""
    return PurePosixPath(member).stem.split("_", 1)[-1].lower()


def day_of(member: str) -> date | None:
    """The day a label's file is named by: the day DailyMed published that version."""
    stamp = PurePosixPath(member).stem.split("_", 1)[0]
    try:
        return date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
    except ValueError:
        return None


def is_label(member: str) -> bool:
    """A prescription label's file: a zip in the prescription folder."""
    path = PurePosixPath(member)
    folder = rulebook.value(RULE, "daily_label_folder")
    return path.suffix.lower() == ".zip" and len(path.parts) > 1 and path.parts[0] == folder


def newest_day(parts: Iterable[Path]) -> date:
    """The newest day a label of the full release was published: the day its labels are as of."""
    days = [
        d for part in parts for n in members(part) if is_label(n) and (d := day_of(n)) is not None
    ]
    return max(days)


@dataclass(frozen=True)
class Day:
    """One of DailyMed's daily update files, read (rule label-source): a day's file holds every
    kind of label DailyMed changed that day, each kind in a folder of its own, and only the
    prescription folder is read, the folder the full release's labels are in."""

    path: Path
    members: tuple[str, ...]  # the prescription labels the day adds or replaces
    removed: frozenset[str]  # set IDs whose prescription label the day takes away for good


def read_day(path: Path) -> Day:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        members = tuple(sorted(n for n in names if is_label(n)))
        listed = rulebook.value(RULE, "daily_deleted_list")
        deleted = z.read(listed).decode("utf-8", "replace").split() if listed in names else []
    added = {set_of(m) for m in members}
    return Day(path, members, frozenset(set_of(m) for m in deleted if is_label(m)) - added)
