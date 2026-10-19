"""The open-altio command as a whole: tasks before commands, help with examples, plain refusals,
and a crash that keeps its details and offers a report."""

from __future__ import annotations

import json

import pytest

from open_altio import cli
from open_altio.cli import console, data, report

COMMANDS = ["demo", "fetch", "build", "serve", "doctor", "report"]


def test_with_no_arguments_it_lists_tasks_not_commands(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    for task, command in [
        ("See the data", "open-altio demo"),
        ("Rebuild with all FDA data", "open-altio fetch, then open-altio build"),
        ("Change a rule", "open-altio serve, then Rules"),
        ("Something's wrong", "open-altio doctor"),
    ]:
        line = next(line for line in out.splitlines() if task in line)
        assert line.split(task, 1)[1].strip() == command
    assert "usage:" not in out


def test_the_help_lists_every_command_with_an_example(capsys):
    with pytest.raises(SystemExit) as done:
        cli.main(["--help"])
    assert done.value.code == 0
    out = capsys.readouterr().out
    assert all(f"\n    {command} " in out for command in COMMANDS)
    assert "Example:\n  open-altio demo" in out


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_explains_itself_with_a_worked_example(command, capsys):
    with pytest.raises(SystemExit) as done:
        cli.main([command, "--help"])
    assert done.value.code == 0
    out = capsys.readouterr().out
    description = out.split("\n\n")[1]
    assert len(description.split()) >= 15, description
    example = out.split("Example")[1]
    assert f"open-altio {command}" in example


def test_the_version_is_the_installed_one(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip().startswith("open-altio ")


def test_a_refusal_says_why_and_exits_2_without_offering_a_report(home, capsys):
    assert cli.main(["build"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("open-altio: There are no FDA files in ")
    assert "open-altio fetch" in err
    assert not (home / report.LAST_ERROR).exists()


def test_a_crash_keeps_its_details_and_offers_a_report(home, monkeypatch, capsys):
    def broken(args):
        raise RuntimeError("the disk went away")

    monkeypatch.setattr(data, "run_fetch", broken)
    opened = []
    monkeypatch.setattr(console, "ask", lambda question: question.startswith("Report this?"))
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert cli.main(["fetch"]) == 1
    err = capsys.readouterr().err
    assert "open-altio fetch stopped with an error it did not expect" in err
    assert "RuntimeError: the disk went away" in err
    kept = json.loads((home / report.LAST_ERROR).read_text())
    assert kept["command"] == "open-altio fetch"
    assert "Traceback" in kept["error"] and "the disk went away" in kept["error"]
    assert len(opened) == 1 and "the+disk+went+away" in opened[0]


def test_a_crash_with_nobody_at_the_keyboard_says_how_to_report_later(monkeypatch, capsys):
    monkeypatch.setattr(data, "run_fetch", lambda args: 1 / 0)
    monkeypatch.setattr("webbrowser.open", lambda url: pytest.fail("opened a browser unasked"))
    assert cli.main(["fetch"]) == 1
    assert "To report it later: open-altio report" in capsys.readouterr().err


def test_ctrl_c_stops_quietly_and_says_how_to_carry_on(monkeypatch, capsys):
    def stopped(args):
        raise KeyboardInterrupt

    monkeypatch.setattr(data, "run_fetch", stopped)
    assert cli.main(["fetch"]) == 130
    assert "Run the same command again to carry on" in capsys.readouterr().out
