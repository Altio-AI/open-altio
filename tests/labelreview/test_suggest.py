"""Codings from any agent, file in and file out: what is exported, kept and refused."""

from __future__ import annotations

import json

import pytest
from reviewhelpers import REVIEWER, suggest_all

from open_altio import rulebook
from open_altio.faers.meddra import read_licensed_manifest
from open_altio.labelreview import batches, coding, decisions, suggest
from open_altio.labelreview.store import SUGGESTIONS, Folder, Refused
from open_altio.testing.fakereview import DEFAULT_PTS, answer_items, item_rows, write_items
from open_altio.testing.rules import rules_with


def _export(folder, clock):
    batches.start_next(folder, clock.now)
    return suggest.export_batch(folder, clock.now)


def _lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write(path, rows):
    (path / suggest.ANSWERS).write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_the_export_holds_the_instructions_the_items_and_an_empty_answers_file(folder, clock):
    out = _export(folder, clock)
    text = (out / suggest.INSTRUCTIONS).read_text(encoding="utf-8")
    assert text == suggest.instructions_document()
    for word in (suggest.ITEMS, suggest.ANSWERS, *suggest.FIELDS, coding.question()):
        assert word in text
    for reason in coding.reasons().values():
        assert reason.key in text and reason.definition in text
        assert all(example in text for example in reason.examples)
    assert rulebook.value("label-coding", "faers_line") in text
    shown = _lines(out / suggest.ITEMS)
    assert [i["item_id"] for i in shown] == list(batches.current(folder).item_ids)
    assert set(shown[0]) == {
        "item_id",
        "drug",
        "section",
        "sentence",
        "rules_guess",
        "why_uncertain",
    }
    assert (out / suggest.ANSWERS).read_text() == ""
    assert out.parent == folder.path  # inside the licensed folder


def test_the_export_lists_the_versions_preferred_terms_for_the_agent_to_spell(folder, clock):
    out = _export(folder, clock)
    names = (out / suggest.TERMS).read_text(encoding="utf-8").splitlines()
    assert "Nausea" in names and "Heart rhythm abnormal" in names  # the release's version
    assert "Arrhythmia" not in names and "Head pain" not in names  # retired, a lower level term
    assert names == sorted(names)


def test_a_good_file_is_kept_with_who_produced_it_and_terms_spelt_as_meddra_spells_them(
    folder, clock
):
    out = _export(folder, clock)
    answer_items(out, pts=["nausea", "HEADACHE"])
    report = suggest.import_suggestions(folder, "Codex, a model", out, clock.now)
    assert len(report.answered) == len(batches.current(folder).item_ids) and not report.unanswered
    for row in folder.read(SUGGESTIONS):
        assert row["by"] == "Codex, a model" and row["status"] == suggest.ANSWERED
        assert row["instructions_version"] == rulebook.value("label-agent", "instructions_version")
        assert row["pts"] == ["Nausea", "Headache"]


def test_a_term_that_is_not_a_current_preferred_term_refuses_the_file(folder, clock):
    out = _export(folder, clock)
    answer_items(out)
    rows = _lines(out / suggest.ANSWERS)
    rows[0]["pts"] = ["Glimmer"]  # not in MedDRA
    rows[1]["pts"] = ["Head pain"]  # a lower level term
    rows[2]["pts"] = ["Arrhythmia"]  # a preferred term only in the version no longer served
    _write(out, rows)
    with pytest.raises(Refused) as refused:
        suggest.import_suggestions(folder, "an agent", out, clock.now)
    message = str(refused.value)
    for name in ("'Glimmer'", "'Head pain'", "'Arrhythmia'"):
        assert name in message
    assert message.count("not a current MedDRA preferred term") == 3
    assert folder.read(SUGGESTIONS) == []


def test_one_bad_line_refuses_the_whole_file_with_a_reason_per_line(folder, clock):
    out = _export(folder, clock)
    answer_items(out)
    rows = _lines(out / suggest.ANSWERS)
    rows[0]["none_reason"] = "population"  # terms and a reason
    rows[1]["evidence"] = "words the label never says"
    rows[2]["item_id"] = "not-an-item"
    rows[3] = {"item_id": rows[3]["item_id"]}
    rows[4]["pts"], rows[4]["none_reason"] = [], "probably"
    rows[5]["pts"], rows[5]["none_reason"], rows[5]["note"] = [], "other", ""
    rows[6]["pts"] = "Nausea"
    rows.append(dict(rows[-1]))
    _write(out, rows)
    (out / suggest.ANSWERS).write_text((out / suggest.ANSWERS).read_text() + "not json\n")
    with pytest.raises(Refused) as refused:
        suggest.import_suggestions(folder, "an agent", out, clock.now)
    message = str(refused.value)
    for expected in (
        "line 1: give preferred terms or a reason",
        "line 2: the evidence",
        "line 3: item 'not-an-item'",
        "line 4: needs exactly the keys",
        "line 5: 'probably' is not a reason",
        "line 6: other needs a note",
        "line 7: pts is a list",
        "appears twice",
        "not a JSON object",
    ):
        assert expected in message
    assert folder.read(SUGGESTIONS) == []


def test_a_blank_or_missing_answer_reaches_the_reviewer_as_no_answer_not_other(folder, clock):
    out = _export(folder, clock)
    first, second = batches.current(folder).item_ids[:2]
    answer_items(out, blank=[first])
    _write(out, [r for r in _lines(out / suggest.ANSWERS) if r["item_id"] != second])
    report = suggest.import_suggestions(folder, "an agent", out, clock.now)
    assert set(report.unanswered) == {first, second}
    said = suggest.latest(folder)
    assert said[first]["status"] == said[second]["status"] == suggest.NO_ANSWER
    assert said[first]["pts"] == [] and said[first]["none_reason"] == ""
    with pytest.raises(Refused, match="no answer to accept"):
        decisions.decide(folder, first, decisions.ACCEPT, [], "", "", REVIEWER, clock.now)


def test_an_item_without_an_answer_counts_as_a_disagreement(folder, clock):
    batch = batches.start_next(folder, clock.now)
    first = batch.item_ids[0]
    suggest_all(folder, clock, blank=[first])
    decisions.decide(folder, first, decisions.REJECT, ["Nausea"], "", "", REVIEWER, clock.now)
    for item_id in batch.item_ids[1:]:
        decisions.decide(folder, item_id, decisions.ACCEPT, [], "", "", REVIEWER, clock.now)
    result = batches.check(folder, batch)
    assert result.decided == result.items and result.agreed == result.items - 1
    assert result.no_answer == 1 and not result.passed
    assert any("no answer" in r for r in result.reasons)


def test_a_second_export_hands_over_only_items_without_a_settled_answer(folder, clock):
    out = _export(folder, clock)
    blank = batches.current(folder).item_ids[:3]
    answer_items(out, blank=blank)
    suggest.import_suggestions(folder, "an agent", out, clock.now)
    again = suggest.export_batch(folder, clock.now)
    assert [i["item_id"] for i in _lines(again / suggest.ITEMS)] == list(blank)


def test_an_unimported_file_is_not_overwritten_by_a_new_export(folder, clock):
    out = _export(folder, clock)
    answer_items(out)
    with pytest.raises(Refused, match="not imported"):
        suggest.export_batch(folder, clock.now)


def test_an_import_after_the_words_changed_is_refused(folder, clock, tmp_path):
    out = _export(folder, clock)
    answer_items(out)
    changed = {"label-coding": {"question": "Which preferred terms does this phrase state?"}}
    with rules_with(tmp_path, changed), pytest.raises(Refused, match="Export again"):
        suggest.import_suggestions(folder, "an agent", out, clock.now)


def test_import_needs_who_produced_it_a_batch_and_a_release_with_meddra(folder, clock, tmp_path):
    with pytest.raises(Refused, match="no batch"):
        suggest.import_suggestions(folder, "an agent", None, clock.now)
    out = _export(folder, clock)
    with pytest.raises(Refused, match="who produced"):
        suggest.import_suggestions(folder, " ", out, clock.now)
    alone = Folder(tmp_path / "elsewhere" / "licensed")
    write_items(alone.path, item_rows(drugs=1, per_drug=2))
    batches.start_next(alone, clock.now)
    with pytest.raises(Refused, match="--release"):
        suggest.export_batch(alone, clock.now)


def test_a_review_in_the_releases_version_folder_checks_terms_against_that_version(
    licensed_release, tmp_path, clock
):
    import shutil

    release = shutil.copytree(licensed_release, tmp_path / "release")
    (built,) = read_licensed_manifest(release)["meddra"]["versions"]  # one version per release
    own = Folder(release / "licensed" / "meddra" / built)  # where the label step writes items
    write_items(own.path, item_rows(drugs=1, per_drug=3))
    batches.start_next(own, clock.now)
    out = suggest.export_batch(own, clock.now)
    assert out.parent == own.path
    answer_items(out, pts=["Arrhythmia"])  # a lower level term in this version
    with pytest.raises(Refused, match="not a current MedDRA preferred term"):
        suggest.import_suggestions(own, "an agent", out, clock.now)
    answer_items(out)
    suggest.import_suggestions(own, "an agent", out, clock.now)
    assert all(r["pts"] == list(DEFAULT_PTS) for r in suggest.latest(own).values())


def test_a_review_in_a_folder_for_a_version_the_release_does_not_hold_is_refused(
    licensed_release, tmp_path, clock
):
    import shutil

    release = shutil.copytree(licensed_release, tmp_path / "release")
    other = Folder(release / "licensed" / "meddra" / "0.0")
    write_items(other.path, item_rows(drugs=1, per_drug=3))
    batches.start_next(other, clock.now)
    with pytest.raises(Refused, match="not 0.0"):
        suggest.export_batch(other, clock.now)
