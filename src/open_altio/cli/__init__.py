"""The open-altio command: see the data, rebuild it from FDA's files, and say what is wrong.

With no arguments it lists tasks rather than commands, because a person arrives wanting to do
something, not knowing the command for it. A refusal says why in plain words and exits 2. A
crash keeps its details for `open-altio report` and offers to open the report there and then.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from importlib import metadata

from open_altio.faers import ReleaseError, SourceError
from open_altio.faers.drugnames import DictionaryRefused
from open_altio.faers.fda import FetchError
from open_altio.faers.meddra import MeddraRefused
from open_altio.rulebook import UserRulesError

from . import console, data, doctor, report, serve
from .console import Refusal, say

DOCS = "https://altio-ai.github.io/open-altio/"

TASKS = f"""\
Open Altio: FDA's adverse event reports, cleaned and deduplicated.

What would you like to do?

  See the data                  open-altio demo
  Rebuild with all FDA data     open-altio fetch, then open-altio build
  Change a rule                 open-altio serve, then Rules
  Something's wrong             open-altio doctor

Every command explains itself: open-altio demo --help. All commands: open-altio --help.
Docs: {DOCS}"""

# Refusals the person can act on; anything else is a crash worth reporting.
REFUSALS = (
    Refusal,
    SourceError,
    ReleaseError,
    UserRulesError,
    FetchError,
    DictionaryRefused,
    MeddraRefused,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="open-altio",
        description="Open Altio: FDA's adverse event reports (FAERS), cleaned and deduplicated\n"
        "in the open, and explored on your own machine.",
        epilog=f"Example:\n  open-altio demo\n\nDocs: {DOCS}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    version = metadata.version("open-altio")
    parser.add_argument("--version", action="version", version=f"open-altio {version}")
    commands = parser.add_subparsers(title="commands", metavar="command", required=True)
    for module in (data, serve, doctor, report):
        module.add(commands)
    return parser


def main(argv: list[str] | None = None) -> int:
    given = sys.argv[1:] if argv is None else argv
    if not given:
        say(TASKS)
        return 0
    args = _parser().parse_args(given)
    command = " ".join(["open-altio", *given])
    try:
        return int(args.run(args))
    except KeyboardInterrupt:
        say("\nStopped. Run the same command again to carry on.")
        return 130
    except REFUSALS as refusal:
        print(f"open-altio: {refusal}", file=sys.stderr)
        return 2
    except Exception:
        return crashed(command, traceback.format_exc())


def crashed(command: str, error: str) -> int:
    kept = report.remember_error(command, error)
    print(f"\n{command} stopped with an error it did not expect:\n", file=sys.stderr)
    print(error.strip().splitlines()[-1], file=sys.stderr)
    print(f"\nThe whole error is kept in {kept}", file=sys.stderr)
    if console.ask("Report this? It opens GitHub's bug form with the details filled in."):
        report.open_report(command=command, error=error)
    else:
        print("To report it later: open-altio report", file=sys.stderr)
    return 1


__all__ = ["main"]
