"""The label step on a release: coded rows and uncertain items go only into the
licensed part, the flags into the public part with no MedDRA content (rules
label-flags, label-umbrella, label-treated-disease, label-not-a-medical-event,
label-procedure, transformed-suffix-T and meddra-licensed-tier).

Built on a copy of the session release with the invented MedDRA versions
(conftest.licensed_release) and the invented labels of open_altio.testing.fakelabeltables."""

from __future__ import annotations

import json
import shutil

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers.__main__ import main
from open_altio.faers.labeldict import (
    CODINGS_FILE,
    FLAG_COLUMNS,
    ITEM_FIELDS,
    TERM_COLUMNS,
    LabelRefused,
    build_label_flags,
    build_label_terms,
    col,
)
from open_altio.faers.labeldict.flagbuild import meddra_for_flags
from open_altio.faers.labeldict.release_io import held_version
from open_altio.faers.meddra import build_licensed
from open_altio.rulebook import UserRules
from open_altio.testing import fakemeddra
from open_altio.testing.fakelabeltables import (
    add_label_groups,
    add_labels,
    write_ime_workbook,
)
from open_altio.testing.fakemeddra import write_meddra
from open_altio.testing.rules import rules_with

VERSION = "29.1"
LICENSED_WORDS = ("meddra", "soc", "hlgt", "hlt", "llt", "smq", "pt_code", "pt_current")
NO_GROUPS = {"not_a_medical_event": [], "procedure": []}


@pytest.fixture
def labelled(licensed_release, tmp_path):
    copy = tmp_path / licensed_release.name
    shutil.copytree(licensed_release, copy)
    add_label_groups(copy, VERSION, NO_GROUPS)
    return add_labels(copy)


def folder_of(release):
    return release / "licensed" / "meddra" / VERSION


def public_files(release):
    return {
        p.relative_to(release).as_posix(): p.read_bytes()
        for p in release.rglob("*")
        if p.is_file() and "licensed" not in p.relative_to(release).parts
    }


def read_items(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def licensed_entry(release):
    manifest = json.loads((release / "licensed" / "manifest.json").read_text())
    return manifest["meddra"]["versions"][VERSION]


def test_coded_rows_and_uncertain_items_go_only_into_the_licensed_part(labelled):
    before = public_files(labelled)
    done = build_label_terms(labelled)
    assert public_files(labelled) == before  # nothing public written or changed
    assert done["terms_path"] == str(folder_of(labelled) / "label_terms_T.parquet")
    assert done["uncertain_path"] == str(folder_of(labelled) / "label_uncertain.jsonl")
    entry = licensed_entry(labelled)
    assert entry["tables"]["label_terms_T"]["rows"] == done["rows"] > 0
    assert entry["label_uncertain"]["items"] == done["items"] > 0
    described = duckdb.sql(f"DESCRIBE SELECT * FROM '{done['terms_path']}'").fetchall()
    assert [c for c, *_ in described] == [col(c) for c in TERM_COLUMNS]
    suffix = rulebook.value("transformed-suffix-T", "derived_suffix")
    assert all(c.endswith(suffix) for c, *_ in described)
    items = read_items(done["uncertain_path"])
    assert all(tuple(i) == ITEM_FIELDS for i in items)
    assert {(i["rxcui"], i["drug"], i["label_date"]) for i in items} == {
        ("900001", "inventamab", "2025-06-01")
    }


def test_each_label_line_gets_the_verdict_its_rule_gives(labelled):
    done = build_label_terms(labelled)
    rows = duckdb.sql(
        f"SELECT setid_T, section_T, pt_name_T, kept_T, rule_T FROM '{done['terms_path']}'"
    ).fetchall()
    got = {(s, sec, pt): (kept, rule) for s, sec, pt, kept, rule in rows}
    assert got[("set-a", "boxed_warning", "Renal failure acute")] == (
        True,
        "label-dictionary",
    )
    assert got[("set-a", "warnings_and_precautions", "Haemorrhage")] == (
        False,
        "label-negation",
    )
    assert got[("set-a", "adverse_reactions", "Vomiting")] == (
        False,
        "label-table-rows",
    )
    assert got[("set-a", "adverse_reactions", "Nausea")] == (None, "label-table-rows")
    assert got[("set-a", "contraindications", "Renal failure")] == (
        False,
        "label-population",
    )
    assert got[("set-a", "contraindications", "Nausea")] == (False, "label-population")
    assert got[("set-b", "adverse_reactions", "Hepatic enzyme increased")][0] is True
    assert got[("set-c", "indications", "Headache")] == (True, "label-treated-disease")


def test_flags_are_public_and_hold_no_meddra_content(labelled):
    build_label_terms(labelled)
    pairs = [
        ("900001", "by_mouth", "Headache"),
        ("900001", "by_mouth", "Haemorrhage"),
        ("900001", "by_mouth", "Vomiting"),
        ("900001", "by_mouth", "Nausea"),
        ("900001", "by_mouth", "Arrhythmia"),  # an old term, as its current PT
        ("900001", "by_mouth", "Lactic acidosis"),  # renamed: read through the history file
        ("900001", "injected", "Hepatic enzyme INCREASED"),
        ("900001", "skin", "Headache"),  # no label for this family: read like unknown
        ("900001", "unknown", "Headache"),  # by mouth on the label, injected not
        ("900001", "by_mouth;injected", "Headache"),  # either form: the same split
        ("900002", "by_mouth", "Headache"),
        ("900002", "by_mouth", "Vomiting"),
        ("900003", "by_mouth", "Headache"),
    ]
    done = build_label_flags(labelled, pairs)
    rows = duckdb.sql(f"SELECT * FROM '{done['path']}'")
    assert tuple(rows.columns) == tuple(col(c) for c in FLAG_COLUMNS)
    got = rows.fetchall()
    outcome = {(r[0], r[1], r[2]): r[3] for r in got}
    assert outcome == {
        ("900001", "by_mouth", "Headache"): "on_label",
        ("900001", "by_mouth", "Haemorrhage"): "not_on_label",
        ("900001", "by_mouth", "Vomiting"): "not_on_label",
        ("900001", "by_mouth", "Nausea"): "uncertain",
        ("900001", "by_mouth", "Arrhythmia"): "on_label",
        ("900001", "by_mouth", "Lactic acidosis"): "not_on_label",
        ("900001", "injected", "Hepatic enzyme INCREASED"): "on_label",
        ("900001", "skin", "Headache"): "forms_differ",
        ("900001", "unknown", "Headache"): "forms_differ",
        ("900001", "by_mouth;injected", "Headache"): "forms_differ",
        ("900002", "by_mouth", "Headache"): "treated_disease",
        ("900002", "by_mouth", "Vomiting"): "not_on_label",
        ("900003", "by_mouth", "Headache"): "no_label",
    }
    judged = {(r[0], r[1], r[2]): r[-1] for r in got}
    assert judged[("900001", "unknown", "Headache")] == "by_mouth; injected"
    assert judged[("900001", "injected", "Hepatic enzyme INCREASED")] == "injected"
    manifest = json.loads((labelled / "manifest.json").read_text())
    assert manifest["tables"]["label_flags_T"]["rows"] == len(pairs)
    text = json.dumps(manifest).lower() + json.dumps(got, default=str).lower()
    assert "label_terms" not in text and "uncertain.jsonl" not in text
    assert not any(w in col(c) for c in FLAG_COLUMNS for w in LICENSED_WORDS)
    pts, llts = fakemeddra._terms(VERSION)[:2]
    hidden = set(pts) | set(llts) | set(fakemeddra.HLTS) | set(fakemeddra.HLGTS)
    hidden |= set(fakemeddra.SOCS) | {n.lower() for n, _ in fakemeddra.HLTS.values()}
    values = {str(v).lower() for row in got for v in row}
    assert not values & {h.lower() for h in hidden}


def test_flags_need_the_licensed_list_of_groups(labelled):
    build_label_terms(labelled)
    (folder_of(labelled) / "label_groups.json").unlink()
    with pytest.raises(LabelRefused, match="label_groups.json"):
        build_label_flags(labelled, [("900001", "by_mouth", "Headache")])


def test_the_not_a_medical_event_list_reads_names_and_groups_at_any_level(labelled, tmp_path):
    build_label_terms(labelled)
    groups = [
        fakemeddra.HLGTS["92000003"][0],  # a group term holding Haemorrhage
        fakemeddra.HLTS["93000005"][0],  # a high level term holding Arrhythmia's PT today
    ]
    add_label_groups(labelled, VERSION, {**NO_GROUPS, "not_a_medical_event": groups})
    pairs = [("900001", "by_mouth", pt) for pt in ("Vomiting", "Haemorrhage", "Arrhythmia")]
    with rules_with(tmp_path, {"label-not-a-medical-event": {"pts": ["Vomiting"]}}):
        done = build_label_flags(labelled, pairs + [("900001", "by_mouth", "Headache")])
    assert done["outcomes"]["not_a_medical_event"] == 3 and done["outcomes"]["on_label"] == 1


def test_a_procedure_is_read_from_its_body_system_class(labelled):
    build_label_terms(labelled)
    soc = fakemeddra.SOCS["91000002"][0]  # holds Nausea and Vomiting
    add_label_groups(labelled, VERSION, {**NO_GROUPS, "procedure": [soc]})
    pairs = [("900001", "by_mouth", pt) for pt in ("Nausea", "Vomiting", "Headache")]
    done = build_label_flags(labelled, pairs)
    assert done["outcomes"]["procedure"] == 2 and done["outcomes"]["on_label"] == 1


def test_a_term_the_not_a_medical_event_rule_names_is_never_a_procedure(labelled, tmp_path):
    build_label_terms(labelled)
    soc = fakemeddra.SOCS["91000002"][0]  # holds Nausea and Vomiting
    add_label_groups(labelled, VERSION, {**NO_GROUPS, "procedure": [soc]})
    pairs = [("900001", "by_mouth", pt) for pt in ("Nausea", "Vomiting")]
    with rules_with(tmp_path, {"label-not-a-medical-event": {"pts": ["Vomiting"]}}):
        done = build_label_flags(labelled, pairs)
    assert done["outcomes"]["not_a_medical_event"] == 1 and done["outcomes"]["procedure"] == 1
    pts = rulebook.value("label-not-a-medical-event", "pts")
    assert {"Self-medication", "Therapy interrupted", "Therapy cessation", "Therapy change"} <= set(
        pts
    )


def test_the_catch_all_groups_are_read_from_the_licensed_part(labelled):
    _, _, entry = held_version(labelled)
    hlt = fakemeddra.HLTS["93000002"][0]  # holds Nausea and Vomiting
    key = rulebook.value("label-flags", "catch_all_key")
    add_label_groups(labelled, VERSION, {**NO_GROUPS, key: [hlt.upper()]})
    meddra, _ = meddra_for_flags(labelled, VERSION, entry, None)
    assert set(meddra.catch_all) == {"93000002"}
    add_label_groups(labelled, VERSION, NO_GROUPS)
    assert not meddra_for_flags(labelled, VERSION, entry, None)[0].catch_all


def test_switching_the_coding_or_the_flags_off_writes_no_flags_and_says_why(labelled):
    with rulebook.use_user_rules(UserRules(off=frozenset({"label-dictionary"}))):
        done = build_label_terms(labelled)
    assert "label-dictionary" in done["skipped"]
    assert not (folder_of(labelled) / "label_terms_T.parquet").exists()
    build_label_terms(labelled)
    pair = [("900001", "by_mouth", "Headache")]
    for rule in ("label-dictionary", "label-flags"):
        with rulebook.use_user_rules(UserRules(off=frozenset({rule}))):
            done = build_label_flags(labelled, pair)
        assert rule in done["skipped"]
    assert not (labelled / "parquet" / "label_flags_T.parquet").exists()


def test_set_aside_rules_switched_off_set_nothing_aside(labelled):
    soc = fakemeddra.SOCS["91000002"][0]  # holds Nausea and Vomiting
    add_label_groups(labelled, VERSION, {**NO_GROUPS, "procedure": [soc]})
    _, _, entry = held_version(labelled)
    off = UserRules(off=frozenset({"label-procedure", "label-umbrella"}))
    with rulebook.use_user_rules(off):
        meddra, _ = meddra_for_flags(labelled, VERSION, entry, None)
    assert meddra.procedures == set() and meddra.umbrella_hlt == {}
    meddra, _ = meddra_for_flags(labelled, VERSION, entry, None)
    assert meddra.procedures and meddra.umbrella_hlt


def test_umbrella_terms_are_found_and_ime_and_severe_forms_never_covered(labelled, tmp_path):
    _, _, entry = held_version(labelled)
    without, count = meddra_for_flags(labelled, VERSION, entry, None)
    assert without.umbrella_hlt == {"94000024": "93000007"}  # named as its HLT, singular
    assert "94000026" in without.severe and "94000025" not in without.severe  # "necrosis"
    assert count is None
    # EMA's list on the first sheet; a PT on its dropped sheet does not count
    ime = write_ime_workbook(tmp_path / "ime.xlsx", ["94000025", "12345678"], ["94000024"])
    with_ime, count = meddra_for_flags(labelled, VERSION, entry, ime)
    assert "94000025" in with_ime.severe and "94000024" not in with_ime.severe
    assert count == 1  # only codes that are PTs of the version


def test_an_uncertain_item_carries_the_highest_rank_of_its_drug_and_term(labelled):
    ranks = [
        ("900001", "Nausea", 2.5),
        ("900001", "NAUSEA", 3.1),
        ("900002", "Nausea", 9.0),
    ]
    done = build_label_terms(labelled, ranks=ranks)
    items = read_items(done["uncertain_path"])
    assert {i["rank"] for i in items if i["candidate_pt"] == "Nausea"} == {3.1}
    assert {i["rank"] for i in items if i["candidate_pt"] != "Nausea"} == {None}


def write_codings(release, *codings):
    path = folder_of(release) / CODINGS_FILE
    path.write_text("".join(json.dumps(c) + "\n" for c in codings), encoding="utf-8")


def coding(item_id, set_id, section, sentence, pts):
    return {
        "item_id": item_id,
        "set_id": set_id,
        "section": section,
        "sentence": sentence,
        "pts": pts,
        "none_reason": "" if pts else "names who the patients are",
        "agent": "invented",
        "instructions_version": "1",
        "reviewed_at": "",
    }


def flag_of(release, pair):
    build_label_flags(release, [pair])
    path = f"{release}/parquet/label_flags_T.parquet"
    return duckdb.sql(f"SELECT outcome_T, section_T, decided_by_T FROM '{path}'").fetchone()


def test_a_coding_with_pts_keeps_them_and_takes_the_item_off_the_list(labelled):
    first = build_label_terms(labelled)
    items = read_items(first["uncertain_path"])
    nausea = next(i for i in items if i["candidate_pt"] == "Nausea")
    item = (nausea["item_id"], nausea["set_id"], nausea["section"], nausea["sentence"])
    write_codings(labelled, coding(*item, ["Nausea"]))
    again = build_label_terms(labelled)
    assert again["codings_matched"] == 1 and again["items"] == first["items"] - 1
    pair = ("900001", "by_mouth", "Nausea")
    assert flag_of(labelled, pair) == (
        "on_label",
        "adverse_reactions",
        "model_reviewed",
    )


def test_a_none_coding_keeps_every_term_of_its_sentence_off_rule_hits_included(
    labelled,
):
    build_label_terms(labelled)
    pair = ("900001", "by_mouth", "Headache")
    assert flag_of(labelled, pair)[0] == "on_label"  # the table row keeps it
    row = "Headache | 12 (3%) | 4 (1%)"
    write_codings(labelled, coding("no-such-item", "set-a", "adverse_reactions", row, []))
    assert build_label_terms(labelled)["codings_matched"] == 1
    assert flag_of(labelled, pair)[0] == "not_on_label"


def test_rebuilding_a_meddra_version_keeps_the_files_a_person_wrote(labelled, tmp_path):
    write_codings(labelled, coding("x", "set-a", "adverse_reactions", "Nausea.", ["Nausea"]))
    sources = write_meddra(tmp_path / "meddra", VERSION)
    build_licensed(labelled, sources, overwrite=True)
    assert (folder_of(labelled) / CODINGS_FILE).is_file()
    assert (folder_of(labelled) / "label_groups.json").is_file()


def test_the_step_refuses_a_release_without_labels_or_meddra(licensed_release, release, tmp_path):
    copy = tmp_path / "nolabels"
    shutil.copytree(licensed_release, copy)
    with pytest.raises(LabelRefused, match="label"):
        build_label_terms(copy)
    with pytest.raises(LabelRefused, match="MedDRA"):
        build_label_terms(release)


def test_the_command_line_codes_the_labels(labelled, capsys):
    assert main(["labels", "--release", str(labelled)]) == 0
    done = json.loads(capsys.readouterr().out)
    assert done["coded"]["version"] == VERSION
    assert "drug_rxnorm_T" in done["flags"]["skipped"]  # the release has no codes
    assert main(["labels", "--release", str(labelled.parent / "no-such-release")]) == 2
