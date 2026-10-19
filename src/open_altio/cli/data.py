"""open-altio demo, fetch and build: FDA's files onto this machine, and releases built from them."""

from __future__ import annotations

import argparse
from datetime import date
from importlib import metadata
from pathlib import Path

from open_altio import paths, rulebook
from open_altio.explorer.rebuild import settle
from open_altio.faers import EXPLORER_FILE, MANIFEST_FILE, fda, read_manifest
from open_altio.faers.build import build_release, user_rules_beside
from open_altio.faers.drugnames import DictionaryRefused, dictionary
from open_altio.faers.sources import QUARTER, discover, release_name

from . import console, serve
from .console import Refusal, say

DEMO = """\
Download FDA's latest quarterly file (about 65 MB) and DiAna's drug dictionary, build a
release from them (about 30 seconds) and open the explorer in your browser. The demo is one
quarter only; for all of FAERS, use open-altio fetch and then open-altio build.

Run it again later and it opens the same release without downloading or building again.
"""

FETCH = """\
Download every quarterly file FDA has published since 2004Q1, about 3.5 GB, into Open Altio's
data folder. Stop it whenever you like: run it again and it carries on where it stopped. Each
file is checked against the size FDA's server gives and the checksums inside the zip.

It also downloads DiAna's drug dictionary (University of Bologna, CC BY 4.0), through which
the build reads each drug name to its ingredients. It is kept only when its checksum is the one
rule drug-names names.
"""

BUILD = """\
Build a release from the FDA files open-altio fetch downloaded, into the current folder,
named after the latest quarter (for example 2026Q2). If the current folder holds a rules.toml
(the explorer's methods page saves one), the build follows it and the release records how it
differs from Altio's standard. With DiAna's drug dictionary in the data folder (open-altio
fetch downloads it), each drug record gets its ingredients; without it the release has none.

The build holds DuckDB to a memory limit, so a laptop with 16 GB of memory builds every
quarter; past the limit it spills to disk and takes longer rather than failing. open-altio
doctor checks this machine has the memory and the free disk a build needs.
"""


def add(commands: argparse._SubParsersAction) -> None:
    demo = commands.add_parser(
        "demo",
        help="see the data: FDA's latest quarter, built and opened in your browser",
        description=DEMO,
        epilog="Examples:\n  open-altio demo\n"
        "  open-altio demo --no-open   (a machine with no browser)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    serve.add_serving_options(demo)
    demo.set_defaults(run=run_demo)

    fetch = commands.add_parser(
        "fetch",
        help="download every quarter FDA has published (about 3.5 GB)",
        description=FETCH,
        epilog="Example:\n  open-altio fetch\n  open-altio build",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    fetch.set_defaults(run=run_fetch)

    build = commands.add_parser(
        "build",
        help="build a release from FDA's files into the current folder",
        description=BUILD,
        epilog="Example:\n  mkdir faers && cd faers\n  open-altio build\n  open-altio serve",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    build.set_defaults(run=run_build)


def run_demo(args: argparse.Namespace) -> int:
    folder = paths.fda_folder()
    quarter = _latest(folder)
    name = release_name(quarter)
    zip_name = fda.zip_name(quarter)
    if (folder / zip_name).is_file():
        say(f"FDA's latest quarter is {name}; its file is here already.")
    else:
        say(f"FDA's latest quarter is {name}. Downloading it into {folder}")
        fda.download(quarter, folder, on_bytes=console.download_bar(zip_name))
    out = paths.releases_folder()
    release = out / name
    settle(out, name)
    if _is_current(release, [quarter]):
        say(f"The demo release {name} is built already: {release}")
    else:
        try:
            fetch_dictionary()
        except DictionaryRefused as refused:
            say(f"The demo is built without drug ingredients: {refused}.")
        say(f"Building the demo release {name} from that one quarter.")
        rules = user_rules_beside(out)
        build_release(
            folder, out, user_rules=rules, quarters=[quarter], progress=console.build_steps()
        )
        console.built(release)
    serve.serve(release, port=args.port, open_browser=not args.no_open)
    return 0


def _latest(folder: Path) -> str:
    """FDA's latest quarter; the newest one here when FDA cannot be reached but one is."""
    try:
        return fda.latest_quarter(date.today())
    except fda.FetchError:
        here = fda.downloaded(folder)
        if not here:
            raise
        say(f"Could not reach FDA, so the demo uses {release_name(here[-1])}, downloaded before.")
        return here[-1]


def _is_current(release: Path, quarters: list[str]) -> bool:
    """A whole release of exactly these quarters, built by the open-altio installed now."""
    if not (release / MANIFEST_FILE).is_file() or not (release / EXPLORER_FILE).is_file():
        return False
    manifest = read_manifest(release)
    return manifest["quarters"] == quarters and manifest["code_version"] == metadata.version(
        "open-altio"
    )


def run_fetch(args: argparse.Namespace) -> int:
    folder = paths.fda_folder()
    latest = fda.latest_quarter(date.today())
    wanted = fda.quarters_until(latest)
    here = set(fda.downloaded(folder))
    missing = [q for q in wanted if q not in here]
    say(
        f"FDA has published {len(wanted)} quarters, {release_name(wanted[0])} to "
        f"{release_name(latest)}. Here already: {len(wanted) - len(missing)}, in {folder}"
    )
    for n, quarter in enumerate(missing, 1):
        label = f"[{n}/{len(missing)}] {fda.zip_name(quarter)}"
        fda.download(quarter, folder, on_bytes=console.download_bar(label))
    fetch_dictionary()
    say("Every quarter is here. Build the release with: open-altio build")
    return 0


def fetch_dictionary() -> None:
    """DiAna's drug dictionary, which the build reads drug names through, unless it is here."""
    target = dictionary.default_path()
    if dictionary.held():
        say(f"DiAna's drug dictionary is here already, in {target}")
        return
    say(
        "Downloading DiAna's drug dictionary (University of Bologna, CC BY 4.0, "
        f"{rulebook.value(dictionary.RULE, 'page')}) into {target}"
    )
    dictionary.fetch(target)


def run_build(args: argparse.Namespace) -> int:
    folder = paths.fda_folder()
    if not folder.is_dir() or not any(QUARTER.search(p.name) for p in folder.iterdir()):
        raise Refusal(
            f"There are no FDA files in {folder} yet. Download them with: open-altio fetch "
            "(or run open-altio demo for the latest quarter only)."
        )
    quarters = [q.name for q in discover(folder)]
    out = Path.cwd()
    settle(out, release_name(quarters[-1]))
    rules = user_rules_beside(out)
    following = "your rules.toml" if rules is not None else "Altio's standard rules"
    say(
        f"Building {release_name(quarters[-1])} from {len(quarters)} quarters of FDA's files "
        f"in {folder}, with {following}, into {out}"
    )
    release = build_release(folder, out, user_rules=rules, progress=console.build_steps())
    console.built(release)
    say("Explore it with: open-altio serve")
    return 0
