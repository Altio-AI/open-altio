"""The live release rebuilt with the rules saved beside it, in the background, one at a
time, while the explorer goes on answering from the release it has open.

A rebuild never writes over the release the explorer has open, because Windows refuses to
remove or replace a file another program holds open. It builds the new release beside it and
points the explorer at it through a pointer file (`release.point_live`), so the next request
opens the new one:

    <folder>/2026Q2/             the release as `open-altio build` or `demo` wrote it
    <folder>/.2026Q2.rebuilt/    the release rebuilt beside it while the first was open
    <folder>/.2026Q2.live        the pointer naming which of the two the explorer serves

A second rebuild writes into whichever of the two is not live. At the next `open-altio`
command, when no explorer has either open, `settle` puts the live one back under the release's
own name and removes the other and the pointer.

A rebuilt release comes out as a first build with the same files would. The build reads the
files the explorer was started with (`open-altio serve --meddra --rxnorm --labels --ime`, as
`Inputs`): MedDRA's, RxNorm's and FDA's labels, then, when the labels step had flagged the
release's reactions, runs that step again under the same rules, with the groups file and the
reviewed codings the release keeps and EMA's Important Medical Events file given. A release that
holds a layer is never rebuilt without its files: the rebuild refuses, saying which to give,
rather than lose the layer.

Before the first rebuild with someone's rules, the methods of the release built with Altio's
standard rules are kept beside it (STANDARD_METHODS), so the methods page can show Altio's counts
next to the new ones.
"""

from __future__ import annotations

import errno
import json
import logging
import shutil
import threading
from pathlib import Path
from typing import Any

import duckdb

from open_altio import rulebook
from open_altio.faers import read_manifest
from open_altio.faers.build import Inputs, build_release
from open_altio.faers.labeldict import build_label_terms, build_release_flags
from open_altio.faers.labeldict.flagbuild import STEP as LABEL_FLAGS
from open_altio.faers.labels.build import LABEL_TABLES
from open_altio.faers.meddra import keep_person_files, read_licensed_manifest
from open_altio.machine import total_memory_bytes
from open_altio.rulebook import FILE_NAME, UserRules

from .release import LiveRelease, OpenRelease, live_folder, point_live

STANDARD_METHODS = "{release}-standard-methods.json"
REBUILT = ".{release}.rebuilt"
POINTER = ".{release}.live"
BUILDING = ".{release}.rebuilding"  # the build writes here; its release then moves into place
FLAGGING = "Flagging each reaction on FDA's labels"


log = logging.getLogger(__name__)


class CannotRebuild(Exception):
    """Why this release cannot be rebuilt here, in plain words."""


GB = 1e9
GIB = 2**30  # memory, as the operating system counts it
UNCHANGED = "The release you have open is unchanged."
AGAIN = "Rebuild again; if it stops at the same step, tell Altio which step it was."
_FULL = ("no space left on device", "disk is full", "not enough space on the disk")


def _gb(n: float, unit: float = GB) -> str:
    return f"{max(n / unit, 0.1):.1f}" if n < 10 * unit else f"{n / unit:.0f}"


def _disk_full(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return True
    return any(words in str(exc).lower() for words in _FULL)


def free_disk(folder: Path) -> int:
    """The free disk where `folder` is, in bytes."""
    return shutil.disk_usage(folder).free


def needs(opened: OpenRelease) -> dict[str, Any]:
    """What a rebuild of `opened` needs of this machine, the numbers `open-altio doctor` checks
    (rule machine-needs: the demo's for a release of one quarter, a build of every quarter's
    otherwise), beside what it has: free disk where the release is, and memory. `says` puts it
    in words for the methods page, and `refused` is why a rebuild will not start, or None."""
    which = "demo" if len(opened.manifest["quarters"]) == 1 else "build"
    disk = float(rulebook.value("machine-needs", f"{which}_disk_gb"))
    memory = float(rulebook.value("machine-needs", f"{which}_memory_gb"))
    folder = opened.folder.parent
    free, total = free_disk(folder), total_memory_bytes()
    says = (
        f"A rebuild of this release needs about {disk:g} GB of free disk and {memory:g} GB of "
        f"memory. This computer has {_gb(free)} GB free where the release is and "
        f"{_gb(total, GIB)} GB of memory."
    )
    if total < memory * GIB:
        says += " With less memory than that the rebuild is slow and may stop."
    refused = None
    if free < disk * GB:
        refused = (
            f"A rebuild of this release needs about {disk:g} GB of free disk, and the disk that "
            f"holds {folder} has {_gb(free)} GB free. Make room there, then rebuild."
        )
    return {
        "disk_gb": disk,
        "memory_gb": memory,
        "free_disk_gb": round(free / GB, 1),
        "memory_total_gb": round(total / GIB, 1),
        "says": says,
        "refused": refused,
    }


def why_it_stopped(exc: BaseException, step: str, opened: OpenRelease) -> str:
    """What the page says when a rebuild of `opened` stopped at `step`: what happened and what
    to do, in plain words. DuckDB's own words go to the log, never the page."""
    folder = opened.folder
    at = f'at the step "{step}"'
    spill = rulebook.value("explorer-build-memory", "spill_limit_gb")
    free = free_disk(folder.parent)
    if _disk_full(exc) or (
        isinstance(exc, duckdb.OutOfMemoryException)
        and "max_temp_directory_size" in str(exc)
        and free < spill * GB
    ):
        return (
            f"The disk ran out of room {at}. A rebuild of this release needs about "
            f"{needs(opened)['disk_gb']:g} GB free on the disk that holds {folder.parent}; it has "
            f"{_gb(free)} GB free now. Make room there, then rebuild. {UNCHANGED}"
        )
    if isinstance(exc, duckdb.OutOfMemoryException) and "max_temp_directory_size" in str(exc):
        return (
            f"The rebuild needed more than the {spill} GB of working files it may write to disk "
            f"{at}, so it stopped. {UNCHANGED} {AGAIN}"
        )
    if isinstance(exc, duckdb.OutOfMemoryException):
        memory = rulebook.value("explorer-build-memory", "memory_limit_gb")
        return (
            f"The rebuild needed more than the {memory} GB of memory it may use {at}, so it "
            f"stopped. {UNCHANGED} {AGAIN}"
        )
    if isinstance(exc, OSError):
        name = exc.filename or "a file"
        return (
            f"The rebuild could not read or write {name} {at}. Check that the folder is still "
            f"there and that you may write to it, then rebuild. {UNCHANGED}"
        )
    if type(exc).__module__.startswith("open_altio"):  # our own refusals say why in plain words
        return f"The rebuild stopped {at}: {exc}"
    return f"The rebuild stopped {at} on a problem of its own. {UNCHANGED} {AGAIN}"


def rules_file(opened: OpenRelease) -> Path:
    """The person's rules file: beside the release, where `open-altio build` reads it too."""
    return opened.folder.parent / FILE_NAME


def methods_of(opened: OpenRelease) -> dict[str, Any]:
    return json.loads((opened.folder / opened.manifest["methods"]).read_text(encoding="utf-8"))


def built_with(methods: dict[str, Any]) -> dict[str, list]:
    """What the release records about the rules it was built with: none for Altio's standard."""
    recorded = methods.get("user_rules") or {}
    return {"off": list(recorded.get("off") or []), "changed": list(recorded.get("changed") or [])}


def standard_methods(opened: OpenRelease) -> dict[str, Any] | None:
    """The methods of this release as built with Altio's standard rules, when they were kept."""
    kept = opened.folder.parent / STANDARD_METHODS.format(release=opened.name)
    return json.loads(kept.read_text(encoding="utf-8")) if kept.is_file() else None


def missing_files(opened: OpenRelease, inputs: Inputs) -> str | None:
    """Why `inputs` cannot rebuild `opened`, in plain words: a layer the release holds whose
    files were not given. None when every layer it holds can be built again."""
    manifest = opened.manifest
    held = (read_licensed_manifest(opened.folder) or {"meddra": {"versions": {}}})["meddra"]
    meddra = next(iter(held["versions"]), None)
    rxnorm = manifest.get("rxnorm") or {}
    flags = manifest.get(LABEL_FLAGS) or {}
    layers = (
        (
            meddra is not None,
            inputs.meddra,
            f"is read to MedDRA {meddra}",
            "MedDRA's files",
            f"--meddra and the folder of MedDRA {meddra}",
        ),
        (
            rxnorm.get("present"),
            inputs.rxnorm_folder(),
            "codes its drugs to RxNorm",
            "RxNorm's files",
            f"--rxnorm and the folder RxNorm_full_prescribe_{rxnorm.get('release')}.zip unzips to",
        ),
        (
            LABEL_TABLES[0] in manifest["tables"],
            inputs.labels,
            "holds FDA's labels",
            "them",
            "--labels and the folder labels-fetch filled",
        ),
        (
            flags.get("important_medical_events") is not None,
            inputs.ime,
            "flags its reactions with EMA's Important Medical Events",
            "EMA's file",
            f"--ime and EMA's Important Medical Events file for MedDRA {meddra}",
        ),
    )
    for holds, given, what, files, start_with in layers:
        if holds and (given is None or not given.exists()):
            return (
                f"This release {what}, and a rebuild reads {files} again. "
                f"Start the explorer with {start_with}, then rebuild."
            )
    return None


def settle(folder: Path, release: str) -> None:
    """Put the release a rebuild made live back under its own name in `folder`, and remove the
    other copy and the pointer. Only for when no explorer has either open."""
    pointer = folder / POINTER.format(release=release)
    if not pointer.is_file():
        return
    named, rebuilt = folder / release, folder / REBUILT.format(release=release)
    if live_folder(pointer) == rebuilt.resolve():
        if named.exists():
            shutil.rmtree(named)
        rebuilt.rename(named)
    elif rebuilt.exists():
        shutil.rmtree(rebuilt)
    pointer.unlink()


class Rebuild:
    def __init__(
        self,
        live: LiveRelease,
        fda_dir: str | Path | None,
        inputs: Inputs | None = None,
    ) -> None:
        self.live = live
        self.fda_dir = Path(fda_dir) if fda_dir else None
        self.inputs = inputs or Inputs()
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {"state": "idle"}

    def state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def start(self, opened: OpenRelease, rules: UserRules) -> dict[str, Any]:
        """Start rebuilding `opened` with `rules`; CannotRebuild says why it cannot start."""
        if self.fda_dir is None:
            raise CannotRebuild(
                "This explorer was started without the folder of FDA's quarterly "
                "files, so it cannot rebuild the release."
            )
        if not self.fda_dir.is_dir():
            raise CannotRebuild(
                f"FDA's quarterly files are not in {self.fda_dir} any more. "
                "Fetch them again, then rebuild."
            )
        missing = missing_files(opened, self.inputs)
        if missing is not None:
            raise CannotRebuild(missing)
        short = needs(opened)["refused"]
        if short is not None:
            raise CannotRebuild(short)
        if opened.folder.name not in (opened.name, REBUILT.format(release=opened.name)):
            raise CannotRebuild(
                f"A rebuild writes the release to a folder named {opened.name}. "
                f"Rename this folder to {opened.name} first."
            )
        with self._lock:
            if self._state["state"] == "running":
                raise CannotRebuild("A rebuild is already running. It ends on its own.")
            self._state = {"state": "running", "step": "Starting", "done": 0, "total": 1}
        work = threading.Thread(
            target=self._run, args=(self.fda_dir, opened, rules), daemon=True, name="rules-rebuild"
        )
        work.start()
        return self.state()

    def _run(self, fda_dir: Path, opened: OpenRelease, rules: UserRules) -> None:
        flagged = LABEL_FLAGS in opened.manifest  # the labels step ran on it, so it runs again
        steps_after = int(flagged)  # one more step after the build's, the labels step

        def progress(step: str, done: int, total: int) -> None:
            with self._lock:
                self._state = {
                    "state": "running",
                    "step": step,
                    "done": done,
                    "total": total + steps_after,
                }

        beside = opened.folder.parent
        named = beside / opened.name
        free = beside / REBUILT.format(release=opened.name) if opened.folder == named else named
        building = beside / BUILDING.format(release=opened.name)
        try:
            if not any(built_with(methods_of(opened)).values()):
                shutil.copyfile(
                    opened.folder / opened.manifest["methods"],
                    beside / STANDARD_METHODS.format(release=opened.name),
                )
            built = build_release(
                fda_dir,
                building,
                user_rules=rules,
                quarters=opened.manifest["quarters"],
                progress=progress,
                inputs=self.inputs,
            )
            if flagged and LABEL_TABLES[0] in read_manifest(built)["tables"]:
                with self._lock:  # the step the build left room for
                    self._state["step"] = FLAGGING
                keep_person_files(opened.folder, built)
                with rulebook.use_user_rules(rules):
                    build_label_terms(built)
                    build_release_flags(built, ime=self.inputs.ime)
            if free.exists():
                shutil.rmtree(free)
            built.rename(free)
            building.rmdir()
            pointer = beside / POINTER.format(release=opened.name)
            point_live(pointer, free)
            self.live.release_dir = pointer  # from now on the explorer follows the pointer
        except Exception as exc:  # the person sees why it failed; the old release stays live
            log.exception("The rebuild of %s stopped", opened.name)
            shutil.rmtree(building, ignore_errors=True)
            with self._lock:
                step = self._state.get("step", "Starting")
                self._state = {
                    "state": "failed",
                    "problem": why_it_stopped(exc, step, opened),
                }
            return
        with self._lock:
            self._state = {"state": "done", "release": opened.name}


__all__ = [
    "STANDARD_METHODS",
    "CannotRebuild",
    "Rebuild",
    "built_with",
    "methods_of",
    "missing_files",
    "needs",
    "rules_file",
    "settle",
    "standard_methods",
    "why_it_stopped",
]
