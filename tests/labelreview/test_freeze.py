"""Freezing: decided codings become the file the label step reads; no agent runs to rebuild, and
neither a labels rerun nor a MedDRA rebuild loses the review's work."""

from __future__ import annotations

import inspect
import json
import shutil

from reviewhelpers import REVIEWER, accept_all, suggest_all

from open_altio.faers.labeldict.codings import read_codings
from open_altio.faers.meddra import build_licensed, read_licensed_manifest
from open_altio.labelreview import batches, decisions, freeze, patterns, runner, suggest
from open_altio.labelreview.items import read_items
from open_altio.labelreview.store import FROZEN, UNCERTAIN, Folder
from open_altio.testing.fakemeddra import write_meddra
from open_altio.testing.fakereview import item_rows, write_items

CONTRACT = [
    "item_id",
    "set_id",
    "section",
    "sentence",
    "pts",
    "none_reason",
    "agent",
    "instructions_version",
    "reviewed_at",
]


def test_every_decided_item_is_frozen_in_the_agreed_shape(reviewed, clock):
    first = batches.current(reviewed).item_ids[0]
    decisions.decide(reviewed, first, decisions.REJECT, [], "population", "", REVIEWER, clock.now)
    count = freeze.freeze(reviewed)
    made = decisions.latest(reviewed)
    items = read_items(reviewed)
    rows = reviewed.read(FROZEN)
    assert FROZEN == "label_codings_frozen.jsonl"
    assert count == len(made) == len(rows)
    for row in rows:
        assert list(row) == sorted(CONTRACT)  # written with sorted keys, exactly these
        d, item = made[row["item_id"]], items[row["item_id"]]
        assert (row["pts"], row["none_reason"]) == (d.pts, d.none_reason)
        assert (row["set_id"], row["section"], row["sentence"]) == (
            item.set_id,
            item.section,
            item.sentence,
        )
        assert row["agent"] == d.suggested_by and row["reviewed_at"] == d.decided_at
    none = next(r for r in rows if r["item_id"] == first)
    assert none["pts"] == [] and none["none_reason"] == "population"


def test_a_rebuild_reads_the_same_codings_without_running_an_agent(reviewed, monkeypatch):
    freeze.freeze(reviewed)
    first = reviewed.file(FROZEN).read_bytes()

    def no_agent(*args, **kwargs):
        raise AssertionError("a build ran an agent")

    monkeypatch.setattr(runner, "run", no_agent)
    monkeypatch.setattr(suggest, "export_batch", no_agent)
    monkeypatch.setattr(suggest, "import_suggestions", no_agent)
    read = read_codings(reviewed.file(FROZEN))  # the label step's own reader
    assert read == reviewed.read(FROZEN) and read
    freeze.freeze(reviewed)
    assert reviewed.file(FROZEN).read_bytes() == first
    assert read_codings(reviewed.file(FROZEN)) == read
    assert "runner" not in inspect.getsource(freeze)


def test_a_labels_rerun_that_drops_decided_phrases_leaves_their_batch_whole(reviewed, clock):
    freeze.freeze(reviewed)
    frozen = reviewed.file(FROZEN).read_bytes()
    batch = batches.current(reviewed)
    # The label step writes the uncertain list again, without the phrases a coding decided.
    rest = [r for r in reviewed.read(UNCERTAIN) if r["item_id"] not in batch.item_ids]
    reviewed.file(UNCERTAIN).write_text("".join(json.dumps(r) + "\n" for r in rest))
    assert set(batch.item_ids) <= set(read_items(reviewed))
    assert batches.check(reviewed, batch).passed
    freeze.freeze(reviewed)
    assert reviewed.file(FROZEN).read_bytes() == frozen
    second = batches.start_next(reviewed, clock.now)
    assert set(second.item_ids) <= {r["item_id"] for r in rest}


def test_rebuilding_the_meddra_version_keeps_the_reviews_work(licensed_release, tmp_path, clock):
    release = shutil.copytree(licensed_release, tmp_path / "release")
    (version,) = read_licensed_manifest(release)["meddra"]["versions"]
    folder = Folder(release / "licensed" / "meddra" / version)
    write_items(folder.path, item_rows(drugs=2, per_drug=3))
    batches.start_next(folder, clock.now)
    suggest_all(folder, clock)
    accept_all(folder, clock)
    made, said = decisions.latest(folder), suggest.latest(folder)
    build_licensed(release, write_meddra(tmp_path / "meddra", version), overwrite=True)
    assert decisions.latest(folder) == made and suggest.latest(folder) == said
    assert batches.check(folder, batches.current(folder)).passed


def test_unreviewed_suggestions_are_never_frozen(folder, clock):
    from reviewhelpers import suggest_all

    batches.start_next(folder, clock.now)
    suggest_all(folder, clock)
    assert freeze.freeze(folder) == 0


def test_repeated_patterns_list_traits_coded_the_same_way_and_skip_mixed_ones(reviewed, clock):
    found = patterns.repeated(reviewed)
    some = next(p for p in found if p.kind == "why uncertain")
    assert some.coded_as == "terms: Nausea"
    items = read_items(reviewed)
    odd = next(
        i for i in batches.current(reviewed).item_ids if items[i].why_uncertain == some.value
    )
    decisions.decide(reviewed, odd, decisions.REJECT, [], "population", "", REVIEWER, clock.now)
    assert ("why uncertain", some.value) not in {
        (p.kind, p.value) for p in patterns.repeated(reviewed)
    }
