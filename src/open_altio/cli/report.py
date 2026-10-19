"""open-altio report: GitHub's bug form, opened in the browser with the details filled in.

The details travel in the address itself (GitHub's issue forms take a value per field id), so
nothing is sent anywhere until the person reads the form and submits it, and no GitHub sign-in
is needed here. The last crash is kept in the data folder so a report made later still has it.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from open_altio import paths
from open_altio.faers import read_manifest

from . import console, doctor, serve
from .console import Refusal, say

NEW_ISSUE = "https://github.com/Altio-AI/open-altio/issues/new"
FORM = "bug.yml"
WHERE = "The open-altio command"  # one of the form's "Where it happened" options, word for word
LABELS = "type: bug,area: cli,status: needs-triage"
# GitHub refuses longer addresses; the error and the doctor's lines are cut to fit under it.
MAX_URL = 8000
LAST_ERROR = "last-error.json"
RECENT_SECONDS = 24 * 3600  # a crash older than this is not the one being reported

REPORT = """\
Open GitHub's bug form for Open Altio in your browser, with what was run, the last error, your
system and the versions filled in. Add your own words and submit it there. Nothing is sent
until you submit it, and this needs no GitHub sign-in. The address is printed too, for a
machine with no browser.
"""


def add(commands: argparse._SubParsersAction) -> None:
    report = commands.add_parser(
        "report",
        help="open GitHub's bug form with the details filled in",
        description=REPORT,
        epilog="Example:\n  open-altio report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    report.set_defaults(run=run_report)


def run_report(args: argparse.Namespace) -> int:
    last = last_error()
    open_report(command=last.get("command", ""), error=last.get("error", ""))
    return 0


def remember_error(command: str, error: str) -> Path:
    """Keep a crash for a later report; returns where it was kept."""
    path = paths.data_folder() / LAST_ERROR
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"command": command, "error": error, "at": time.time()}
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def last_error() -> dict:
    """The last crash, if it happened recently enough to be what is being reported."""
    path = paths.data_folder() / LAST_ERROR
    if not path.is_file():
        return {}
    record = json.loads(path.read_text(encoding="utf-8"))
    return record if time.time() - record["at"] < RECENT_SECONDS else {}


def open_report(*, command: str = "", error: str = "", doctor_lines: str | None = None) -> None:
    lines = doctor.render(doctor.checks(online=False)) if doctor_lines is None else doctor_lines
    url = issue_url(command=command, error=error, doctor_lines=lines, release=_release())
    say("Opening GitHub's bug form with the details filled in. Nothing is sent until you submit")
    say("it there. If no browser opens, open this address:")
    say(url)
    webbrowser.open(url)


def issue_url(*, command: str, error: str, doctor_lines: str, release: str) -> str:
    """The new-issue address with the bug form's fields filled in, under GitHub's length limit."""
    summary = error.strip().splitlines()[-1] if error.strip() else ""
    fields = {
        "template": FORM,
        "labels": LABELS,
        "title": f"Bug: {command}: {summary}"[:120] if command else "Bug: ",
        "where": WHERE,
        "command": command,
        "error": error,
        "release": release,
        "doctor": f"{system()}\n{doctor_lines}",
    }
    url = _address(fields)
    # cut the longer field until it fits: the error keeps its end, where the cause is, and the
    # doctor's lines keep their start
    while len(url) > MAX_URL:
        longest = max(("error", "doctor"), key=lambda k: len(fields[k]))
        text = fields[longest]
        cut = len(text) // 4
        fields[longest] = "[...]\n" + text[cut:] if longest == "error" else text[:-cut] + "\n[...]"
        url = _address(fields)
    return url


def _address(fields: dict[str, str]) -> str:
    return f"{NEW_ISSUE}?{urlencode({k: v for k, v in fields.items() if v})}"


def system() -> str:
    return (
        f"{platform.system()} {platform.release()} ({platform.machine()}), "
        f"Python {platform.python_version()}, at {datetime.now(UTC):%Y-%m-%d %H:%M} UTC"
    )


def _release() -> str:
    try:
        release = serve.newest_release(Path.cwd())
    except Refusal:
        return ""
    return console.about(read_manifest(release))
