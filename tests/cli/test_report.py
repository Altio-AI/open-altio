"""open-altio report: GitHub's bug form, filled in through its address and nothing else."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import yaml

from open_altio import cli
from open_altio.cli import report

FORM = Path(__file__).resolve().parents[2] / ".github" / "ISSUE_TEMPLATE" / report.FORM


def fields(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def form() -> dict:
    return yaml.safe_load(FORM.read_text(encoding="utf-8"))


def test_every_filled_field_is_one_the_bug_form_has():
    url = report.issue_url(
        command="open-altio build",
        error="Traceback\nOSError: no space",
        doctor_lines="  ok    Python 3.12",
        release="2026Q2",
    )
    filled = fields(url)
    ids = {item["id"] for item in form()["body"] if "id" in item}
    assert url.startswith("https://github.com/Altio-AI/open-altio/issues/new?")
    assert filled["template"] == FORM.name
    assert set(filled) - {"template", "title", "labels"} <= ids
    where = next(item for item in form()["body"] if item.get("id") == "where")
    assert filled["where"] in where["attributes"]["options"]
    assert filled["command"] == "open-altio build"
    assert filled["error"].endswith("OSError: no space")
    assert filled["title"] == "Bug: open-altio build: OSError: no space"
    assert filled["release"] == "2026Q2"
    assert "Python 3.12" in filled["doctor"]


def test_the_labels_asked_for_are_the_form_s_own_and_the_command_s_area():
    url = report.issue_url(command="", error="", doctor_lines="", release="")
    labels = fields(url)["labels"].split(",")
    assert set(form()["labels"]) <= set(labels)
    assert "area: cli" in labels
    assert "own-words" not in fields(url)


def test_a_long_error_is_cut_to_fit_and_keeps_its_last_line():
    error = (
        "\n".join(f'  File "x.py", line {n}, in step_{n}' for n in range(3000)) + "\nValueError: x"
    )
    url = report.issue_url(
        command="open-altio demo",
        error=error,
        doctor_lines="  ok    line\n" * 400,
        release="2026Q2",
    )
    assert len(url) <= report.MAX_URL
    filled = fields(url)
    assert filled["error"].startswith("[...]") and filled["error"].endswith("ValueError: x")
    assert filled["doctor"].endswith("[...]")


def test_report_fills_in_the_last_crash_and_opens_the_form(home, monkeypatch, capsys):
    report.remember_error("open-altio fetch", "Traceback\nTimeoutError: FDA took too long")
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert cli.main(["report"]) == 0
    filled = fields(opened[0])
    assert filled["command"] == "open-altio fetch"
    assert filled["error"].endswith("TimeoutError: FDA took too long")
    out = capsys.readouterr().out
    assert opened[0] in out and "Nothing is sent until you submit" in out


def test_an_old_crash_is_left_out(home, monkeypatch):
    kept = report.remember_error("open-altio fetch", "Traceback\nTimeoutError")
    record = json.loads(kept.read_text())
    kept.write_text(json.dumps({**record, "at": time.time() - 2 * report.RECENT_SECONDS}))
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert cli.main(["report"]) == 0
    assert "command" not in fields(opened[0]) and "error" not in fields(opened[0])
