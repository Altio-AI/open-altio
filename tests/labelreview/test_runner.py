"""The run command: the person's own agent on the batch folder, with retries (rule label-agent)."""

from __future__ import annotations

import json

import pytest
from reviewhelpers import REVIEWER

from open_altio import rulebook
from open_altio.labelreview import batches, decisions, runner, suggest
from open_altio.testing.fakereview import write_agent
from open_altio.testing.rules import rules_with


class Waits:
    """Stands in for sleeping: keeps each wait asked for, and waits for none."""

    def __init__(self) -> None:
        self.asked: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.asked.append(seconds)


def _log(folder):
    out = suggest.batch_dir(folder, batches.current(folder).number)
    return [json.loads(line) for line in (out / runner.LOG).read_text().splitlines()]


def test_an_agent_that_answers_everything_is_run_once(folder, clock, tmp_path):
    batches.start_next(folder, clock.now)
    waits = Waits()
    done = runner.run(folder, write_agent(tmp_path / "agent.py"), "a fake agent", clock.now, waits)
    size = len(batches.current(folder).item_ids)
    assert (done.attempts, done.answered, done.refused) == (1, size, [])
    assert waits.asked == []
    [entry] = _log(folder)
    assert entry["exit_code"] == 0 and entry["left"] == [] and len(entry["items"]) == size
    assert all(r["by"] == "a fake agent" for r in suggest.latest(folder).values())


def test_items_left_blank_are_asked_again_after_the_rules_waits(folder, clock, tmp_path):
    batches.start_next(folder, clock.now)
    waits = Waits()
    done = runner.run(
        folder, write_agent(tmp_path / "agent.py", blank_calls=2), "", clock.now, waits
    )
    assert done.attempts == 3 and done.refused == []
    assert waits.asked == runner.waits()[:2]
    log = _log(folder)
    assert [len(e["left"]) for e in log] == [
        len(log[0]["items"]),
        len(log[0]["items"]),
        0,
    ]
    assert all(suggest.is_answer(r) for r in suggest.latest(folder).values())


def test_an_item_still_unanswered_after_the_last_retry_is_refused(folder, clock, tmp_path):
    batch = batches.start_next(folder, clock.now)
    stubborn = batch.item_ids[0]
    waits = Waits()
    agent = write_agent(tmp_path / "agent.py", never=[stubborn])
    done = runner.run(folder, agent, "", clock.now, waits)
    retries = rulebook.value("label-agent", "retries")
    assert done.attempts == retries + 1 and done.refused == [stubborn]
    assert waits.asked == runner.waits() and len(waits.asked) == retries
    assert suggest.latest(folder)[stubborn]["status"] == suggest.REFUSED
    assert _log(folder)[-1]["refused"] == [stubborn]
    # Refused goes to the reviewer, and counts as a disagreement.
    decisions.decide(folder, stubborn, decisions.REJECT, ["Nausea"], "", "", REVIEWER, clock.now)
    for item_id in batch.item_ids[1:]:
        decisions.decide(folder, item_id, decisions.ACCEPT, [], "", "", REVIEWER, clock.now)
    result = batches.check(folder, batch)
    assert result.no_answer == 1 and result.agreed == result.items - 1 and not result.passed


def test_a_file_the_agent_got_wrong_is_kept_and_every_item_is_asked_again(folder, clock, tmp_path):
    batches.start_next(folder, clock.now)
    agent = write_agent(tmp_path / "agent.py", junk_calls=1)
    done = runner.run(folder, agent, "", clock.now, Waits())
    assert done.attempts == 2 and done.refused == []
    first, second = _log(folder)
    assert "file refused" in first["outcome"] and first["left"] == first["items"]
    out = suggest.batch_dir(folder, batches.current(folder).number)
    assert (out / "suggestions.attempt-0.jsonl").read_text().startswith("not what")
    assert second["left"] == []


def test_the_reasons_a_file_was_refused_are_left_for_the_agents_next_try(folder, clock, tmp_path):
    batches.start_next(folder, clock.now)
    with rules_with(tmp_path, {"label-agent": {"retries": 1}}):
        runner.run(
            folder,
            write_agent(tmp_path / "agent.py", junk_calls=9),
            "",
            clock.now,
            Waits(),
        )
    out = suggest.batch_dir(folder, batches.current(folder).number)
    assert "not a JSON object" in (out / suggest.PROBLEMS).read_text()
    runner_ok = write_agent(tmp_path / "agent2.py")
    with rules_with(tmp_path, {"label-agent": {"retries": 1}}):
        changed = {"label-coding": {"question": "Which preferred terms does this phrase state?"}}
        with rules_with(tmp_path / "again", changed):
            runner.run(folder, runner_ok, "", clock.now, Waits())
    assert not (out / suggest.PROBLEMS).exists()


def test_the_waits_come_from_the_rule(folder, clock, tmp_path):
    changed = {
        "retries": 4,
        "first_wait_seconds": 5,
        "wait_factor": 3,
        "longest_wait_seconds": 50,
    }
    with rules_with(tmp_path, {"label-agent": changed}):
        assert runner.waits() == [5, 15, 45, 50]
        batches.start_next(folder, clock.now)
        waits = Waits()
        agent = write_agent(tmp_path / "agent.py", blank_calls=99)
        done = runner.run(folder, agent, "", clock.now, waits)
    assert waits.asked == [5, 15, 45, 50] and done.attempts == 5
    assert len(done.refused) == len(batches.current(folder).item_ids)


def test_the_real_waits_start_at_the_first_double_and_stop_at_the_longest():
    rule = rulebook.rule("label-agent")
    got = runner.waits()
    assert got[0] == rule.value("first_wait_seconds")
    assert got[1] == got[0] * rule.value("wait_factor")
    assert max(got) == rule.value("longest_wait_seconds")


def test_an_agent_command_is_needed(folder, clock):
    batches.start_next(folder, clock.now)
    with pytest.raises(suggest.Refused, match="agent command"):
        runner.run(folder, "  ", "", clock.now, Waits())
