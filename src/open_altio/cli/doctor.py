"""open-altio doctor: what on this machine stops Open Altio working, and how to fix it."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from open_altio import paths, rulebook
from open_altio.faers import EXPLORER_FILE, fda, read_manifest
from open_altio.faers.drugnames import dictionary
from open_altio.faers.meddra import newest, older_part, older_words, read_licensed_manifest
from open_altio.machine import total_memory_bytes

from . import console, serve
from .console import disk_size, memory, say

PYPI = "https://pypi.org/pypi/open-altio/json"
PYPI_TIMEOUT_SECONDS = 5
PACKAGES = ("open-altio", "duckdb", "pyarrow", "fastapi", "uvicorn")

DOCTOR = """\
Check this machine for what Open Altio needs: Python, memory, free disk, the explorer's port,
the data folder with FDA's files, DiAna's drug dictionary and the releases, the versions
installed and whether a newer open-altio is out, and whether FDA's server can be reached. Each
line says what was found; anything to fix says how, and then it offers to report it. Nothing on
this machine is changed, and nothing about it is sent.
"""

OK, NOTE, FIX = "ok", "note", "fix"


@dataclass(frozen=True)
class Finding:
    status: str  # OK, NOTE (worth knowing) or FIX (stops something working)
    text: str


def add(commands: argparse._SubParsersAction) -> None:
    doctor = commands.add_parser(
        "doctor",
        help="check this machine and say in plain words what is wrong",
        description=DOCTOR,
        epilog="Example:\n  open-altio doctor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    doctor.set_defaults(run=run_doctor)


def run_doctor(args: argparse.Namespace) -> int:
    from . import report  # report reads the doctor's lines, so it is imported here, not above

    findings = checks(online=True)
    say(render(findings))
    to_fix = [f for f in findings if f.status == FIX]
    if not to_fix:
        say("\nAll good.")
        return 0
    say(f"\n{console.count(len(to_fix), 'thing')} to fix, above.")
    if console.ask("Report this? It opens GitHub's bug form with these lines filled in."):
        report.open_report(command="open-altio doctor", doctor_lines=render(findings))
    else:
        say("To report it later: open-altio report")
    return 1


def render(findings: list[Finding]) -> str:
    return "\n".join(f"  {f.status:<5} {f.text}" for f in findings)


def checks(*, online: bool) -> list[Finding]:
    """Every check, in the order a person would fix them. `online` adds the ones that ask
    FDA and PyPI, which `report` leaves out so it works offline."""
    found = [_python(), *_versions(online), _memory(), _disk(), _port(), *_data()]
    if online:
        found.append(_fda())
    return found


def _need(key: str) -> float:
    return float(rulebook.value("machine-needs", key))


def _python() -> Finding:
    words = f"Python {platform.python_version()} ({platform.machine()})"
    if sys.maxsize <= 2**32:
        return Finding(FIX, f"{words} is 32-bit. DuckDB needs a 64-bit Python 3.12 or later.")
    return Finding(OK, words)


def installed() -> dict[str, str]:
    found = {}
    for name in PACKAGES:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = "not installed"
    return found


def _versions(online: bool) -> list[Finding]:
    versions = installed()
    line = ", ".join(f"{name} {version}" for name, version in versions.items())
    found = [Finding(OK, line)]
    if online:
        mine = versions["open-altio"]
        try:
            newest = _newest_on_pypi()
        except OSError:
            found.append(Finding(NOTE, "Could not reach PyPI to see if a newer open-altio is out."))
            return found
        if newest and _as_tuple(newest) > _as_tuple(mine):
            found.append(
                Finding(
                    NOTE,
                    f"open-altio {newest} is out (you have {mine}). Upgrade "
                    "with: uv tool upgrade open-altio (or pipx upgrade, or pip "
                    "install -U)",
                )
            )
    return found


def _newest_on_pypi() -> str | None:
    """The newest open-altio on PyPI, or None when PyPI has none; OSError when out of reach."""
    try:
        with urlopen(PYPI, timeout=PYPI_TIMEOUT_SECONDS) as answer:
            return str(json.load(answer)["info"]["version"])
    except HTTPError:
        return None


def _as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def _memory() -> Finding:
    total = total_memory_bytes()
    demo, build = _need("demo_memory_gb"), _need("build_memory_gb")
    words = f"Memory: {memory(total)}."
    if total < demo * 2**30:
        return Finding(
            FIX,
            f"{words} The demo needs about {demo:g} GB; close other programs "
            "or use a machine with more memory.",
        )
    if total < build * 2**30:
        return Finding(
            NOTE,
            f"{words} Enough for the demo; a build of every quarter needs "
            f"about {build:g} GB and will be slow or fail here.",
        )
    return Finding(OK, f"{words} Enough for a build of every quarter.")


def _disk() -> Finding:
    folder = paths.data_folder()
    existing = next(p for p in (folder, *folder.parents) if p.exists())
    free = shutil.disk_usage(existing).free
    demo, build = _need("demo_disk_gb"), _need("build_disk_gb")
    words = f"Free disk: {disk_size(free)} where the data folder is."
    move = f"Free some space, or set {paths.DATA_ENV} to a folder on a bigger disk."
    if free < demo * 1e9:
        return Finding(FIX, f"{words} The demo needs about {demo:g} GB. {move}")
    if free < build * 1e9:
        return Finding(
            NOTE, f"{words} Enough for the demo; every quarter needs about {build:g} GB. {move}"
        )
    return Finding(OK, f"{words} Enough for every quarter.")


def _port() -> Finding:
    if serve.choose_port(serve.LOOPBACK, None) == serve.PORT:
        return Finding(OK, f"Port {serve.PORT} on {serve.LOOPBACK} is free for the explorer.")
    return Finding(
        NOTE,
        f"Port {serve.PORT} is in use by another program; open-altio serve "
        "takes the next free one, or choose one with --port.",
    )


def _data() -> list[Finding]:
    folder = paths.data_folder()
    found = []
    if folder.exists() and not os.access(folder, os.W_OK):
        found.append(
            Finding(
                FIX,
                f"The data folder {folder} cannot be written to. Fix its "
                f"permissions, or set {paths.DATA_ENV} to another folder.",
            )
        )
    fda_folder = paths.fda_folder()
    quarters = fda.downloaded(fda_folder)
    stopped = sorted(p.name for p in fda_folder.glob(f"*{fda.PART}"))
    held = console.count(len(quarters), "quarter") if quarters else "none downloaded yet"
    found.append(Finding(OK, f"FDA's files: {held}, in {fda_folder}"))
    found.append(_dictionary())
    if stopped:
        found.append(
            Finding(
                NOTE,
                f"A download stopped part way ({', '.join(stopped)}); "
                "open-altio fetch or demo carries on from there.",
            )
        )
    releases = serve.releases_in(Path.cwd()) + serve.releases_in(paths.releases_folder())
    found += [f for release in releases for f in (_release(release), _meddra(release)) if f]
    if not releases:
        found.append(Finding(OK, "Releases: none built yet; open-altio demo builds one."))
    return found


def _dictionary() -> Finding:
    path = dictionary.default_path()
    if not path.is_file():
        return Finding(
            NOTE,
            "DiAna's drug dictionary: not downloaded yet, so a build gives drug records no "
            "ingredients. open-altio fetch downloads it.",
        )
    if dictionary.sha256(path) != rulebook.value(dictionary.RULE, "sha256"):
        return Finding(
            FIX,
            f"DiAna's drug dictionary in {path} is not the file rule {dictionary.RULE} names, "
            "so a build stops. Move it away and run open-altio fetch for the right one.",
        )
    return Finding(OK, f"DiAna's drug dictionary, in {path}")


def _release(release: Path) -> Finding:
    try:
        manifest = read_manifest(release)
    except (OSError, ValueError) as e:
        return Finding(
            FIX,
            f"Release {release}: its manifest cannot be read ({e}). Build it "
            "again with open-altio build (or open-altio demo).",
        )
    words = f"Release {console.about(manifest)}, in {release}"
    if not (release / EXPLORER_FILE).is_file():
        return Finding(FIX, f"{words}, has no {EXPLORER_FILE}. Build it again.")
    if manifest["code_version"] != installed()["open-altio"]:
        return Finding(NOTE, f"{words}; build it again to get this version's changes.")
    return Finding(OK, words)


def _meddra(release: Path) -> Finding | None:
    """A note when the release's MedDRA part was added by an older version, which the explorer
    does not serve."""
    try:
        versions = (read_licensed_manifest(release) or {}).get("meddra", {}).get("versions", {})
    except (OSError, ValueError):
        return None
    version = newest(versions)
    if version is None or not older_part(versions[version]):
        return None
    return Finding(NOTE, f"Release in {release}: {older_words(version)}")


def _fda() -> Finding:
    try:
        size = fda.published_size(fda.FIRST_QUARTER)
    except fda.FetchError as e:
        return Finding(FIX, str(e))
    if size is None:
        return Finding(
            FIX,
            f"FDA's server at {fda.EXPORTS} answers, but not with its files. "
            "FDA may have moved them; please report this.",
        )
    return Finding(OK, f"FDA's files can be downloaded from {fda.EXPORTS}")
