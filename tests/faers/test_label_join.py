"""The flags of a release's own drug records (rule label-flags): suspect records only (PS and
SS), trial products left out, each record found its label by its RxNorm code and read on its
route families, counted as records and cases, never as drug rows.

Built on a copy of the session release with the invented MedDRA versions, the invented labels
of open_altio.testing.fakelabeltables and invented record tables in the shape of drug_rxnorm_T and
drug_route_T. Aspirin's ingredient is coded as inventamab (900001: a label by mouth and one
injected), warfarin's and omeprazole's as fakeoxacin (900002: a label by mouth only),
digoxin's as a drug with no label, ibuprofen's as a trial product; metformin has no code."""

from __future__ import annotations

import json
import shutil

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from open_altio import rulebook
from open_altio.faers.__main__ import main
from open_altio.faers.labeldict import build_label_terms, build_release_flags
from open_altio.faers.labeldict.join import FATES, WITHOUT_INGREDIENTS, WITHOUT_ROUTE
from open_altio.faers.labeldict.unit import Unit
from open_altio.testing.fakelabeltables import add_label_groups, add_labels, add_record_tables
from open_altio.testing.rules import rules_with

VERSION = "29.1"
ASPIRIN, WARFARIN = "acetylsalicylic acid", "warfarin"
CODES = {
    ASPIRIN: "900001",
    WARFARIN: "900002",
    "omeprazole": "900002",  # only ever concomitant: never flagged
    "digoxin": "900003",  # no label
    "ibuprofen": "900004",  # a trial product
}
FAMILIES = {ASPIRIN: ["by_mouth"], WARFARIN: ["by_mouth", "injected"], "digoxin": ["by_mouth"]}
TRIAL = {"ibuprofen"}


@pytest.fixture
def labelled(licensed_release, tmp_path):
    copy = tmp_path / licensed_release.name
    shutil.copytree(licensed_release, copy)
    add_label_groups(copy, VERSION, {"not_a_medical_event": [], "procedure": []})
    add_labels(copy)
    build_label_terms(copy)
    return copy


def flags_of(release):
    path = release / "parquet" / "label_flags_T.parquet"
    sql = "SELECT rxcui_T, route_families_T, pt_T, outcome_T, judged_on_T FROM read_parquet(?)"
    return {(r[0], r[1], r[2]): r[3:] for r in duckdb.execute(sql, [str(path)]).fetchall()}


def manifest_of(release):
    return json.loads((release / "manifest.json").read_text(encoding="utf-8"))


def test_only_suspect_records_that_are_no_trial_product_are_flagged(labelled):
    add_record_tables(labelled, CODES, FAMILIES, TRIAL)
    build_release_flags(labelled)
    got = flags_of(labelled)
    assert {k for k in got if k[0] == "900001"} == {
        ("900001", "by_mouth", pt)
        for pt in ("Headache", "HEADACHE", "Vomiting", "Haemorrhage", "Nausea")
    } | {("900001", "by_mouth", "Hepatic enzyme INCREASED")}
    # omeprazole is only concomitant, so its case's vomiting reaches fakeoxacin through no one
    assert {pt for rx, _, pt in got if rx == "900002"} == {"Haemorrhage", "Nausea"}
    assert not any(rx == "900004" for rx, _, _ in got)  # the trial product
    assert rulebook.value("label-flags", "suspect_roles") == ["PS", "SS"]


def test_each_record_is_read_on_the_label_its_code_and_families_find(labelled):
    add_record_tables(labelled, CODES, FAMILIES, TRIAL)
    build_release_flags(labelled)
    got = flags_of(labelled)
    assert got[("900001", "by_mouth", "Headache")] == ("on_label", "by_mouth")
    # no injected label for fakeoxacin: the family counts as unknown, every label is read
    assert got[("900002", "by_mouth;injected", "Nausea")][1] == "by_mouth"
    assert got[("900003", "by_mouth", "Arrhythmia")] == ("no_label", None)
    # no code: no label found, unless the term alone decides
    assert got[(None, "", "Headache")] == ("no_label", None)
    assert got[(None, "", "Lactic acidosis")] == ("no_label", None)  # renamed, read by history


def test_a_combinations_reactions_are_also_read_on_each_ingredients_own_label(labelled):
    """Entresto's record is coded as the combination (inventamab's code here, read on its by
    mouth label); its valsartan is fakeoxacin's code, whose own records give the same rows,
    and its sacubitril has no code of its own."""
    codes = {**CODES, "sacubitril;valsartan": "900001", "valsartan": "900002"}
    families = {**FAMILIES, "sacubitril;valsartan": ["by_mouth"], "valsartan": ["by_mouth"]}
    add_record_tables(labelled, codes, families, TRIAL)
    done = build_release_flags(labelled)
    got = flags_of(labelled)
    entresto = ("by_mouth", "Headache")
    assert got[("900001", *entresto)] == ("on_label", "by_mouth")  # the product's own label
    assert got[("900002", *entresto)][1] == "by_mouth"  # valsartan's own label
    assert got[(None, *entresto)] == ("no_label", None)  # sacubitril: no code, no label
    # one row per code, families and reaction, however many records and ingredients met it
    path = labelled / "parquet" / "label_flags_T.parquet"
    distinct = "SELECT count(DISTINCT (rxcui_T, route_families_T, pt_T)) FROM read_parquet(?)"
    assert duckdb.execute(distinct, [str(path)]).fetchone()[0] == done["rows"] == len(got)


def test_without_each_ingredients_own_code_records_are_read_on_their_own_and_it_says_so(
    labelled,
):
    codes = {**CODES, "sacubitril;valsartan": "900001", "valsartan": "900002"}
    families = {**FAMILIES, "sacubitril;valsartan": ["by_mouth"]}
    add_record_tables(labelled, codes, families, TRIAL)
    manifest = manifest_of(labelled)
    del manifest["tables"]["ingredient_rxnorm_T"]
    (labelled / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    done = build_release_flags(labelled)
    assert done["notes"] == [WITHOUT_INGREDIENTS]
    got = flags_of(labelled)
    assert ("900001", "by_mouth", "Headache") in got
    assert ("900002", "by_mouth", "Headache") not in got  # no record of valsartan by mouth


def test_the_step_counts_records_and_cases_by_how_far_they_got(labelled):
    add_record_tables(labelled, CODES, FAMILIES, TRIAL)
    done = build_release_flags(labelled)
    counts = done["suspect_records"]
    assert counts["records"] == {
        "trial_product": 2,
        "no_rxnorm_code": 14,
        "code_names_another_drug": 0,
        "no_label": 4,
        "label": 19,
        "suspect": 39,
    }
    assert counts["cases"] == {
        "trial_product": 2,
        "no_rxnorm_code": 12,
        "code_names_another_drug": 0,
        "no_label": 4,
        "label": 15,
    }
    assert tuple(counts["cases"]) == FATES
    entry = manifest_of(labelled)["label_flags"]
    assert entry["suspect_records"] == counts and entry["present"] is True
    assert entry["rows"] == manifest_of(labelled)["tables"]["label_flags_T"]["rows"]


def _shown_suspect_records(release) -> int:
    """The suspect drug records (rule label-flags' roles) of the cases the release shows that the
    drug names step read, counted here apart from the step's own query."""
    roles = list(rulebook.value("label-flags", "suspect_roles"))
    key = "era_T, primaryid, quarter_T"
    tables = {t: f"read_parquet('{release / 'parquet' / t}.parquet')"
              for t in ("case_latest_T", "drug_latest_T", "drug_substance_T")}  # fmt: skip
    sql = f"""SELECT count(*) FROM (SELECT DISTINCT {key}, drug_seq FROM {tables["drug_latest_T"]}
                                    WHERE role_cod IN (SELECT unnest(?::VARCHAR[]))) d
              JOIN {tables["drug_substance_T"]} s USING ({key}, drug_seq)
              JOIN {tables["case_latest_T"]} c USING ({key}) WHERE c.dup_kept_T"""
    return duckdb.execute(sql, [roles]).fetchone()[0]


def test_the_methods_page_gains_the_label_flags_limit_over_the_cases_shown(labelled):
    def methods():
        return json.loads((labelled / "methods.json").read_text(encoding="utf-8"))

    def limit():
        found = (i for i in methods()["limits"] if i["id"] == "label_flags_read_todays_label")
        return next(found, None)

    assert limit() is None  # no flags yet, so no limit about them
    add_record_tables(labelled, CODES, FAMILIES, TRIAL)
    every = build_release_flags(labelled)["suspect_records"]["records"]
    records = methods()["numbers"]["label_flags"]["records"]
    assert records["suspect"] == _shown_suspect_records(labelled) == sum(records[f] for f in FATES)
    assert records["suspect"] < every["suspect"]  # the duplicates set aside are not counted
    assert all(records[f] <= every[f] for f in FATES)
    text = limit()["text"]
    cant_tell = rulebook.value("explorer-label-words", "words")["uncertain"]  # the flag's word
    assert "today" in text and cant_tell in text and "caused" in text
    assert f"{records['no_label']:,} suspect drug records have an RxNorm code but no label" in text
    assert f"{records['no_rxnorm_code']:,} have no code" in text


def _code_one_warfarin_record_as_aspirin(release):
    """One suspect warfarin record coded as acetylsalicylic acid, whose code is another drug's,
    as valproic acid's records are coded diazepam by FDA's active ingredient; warfarin's other
    records keep its own code."""
    path = release / "parquet" / "drug_rxnorm_T.parquet"
    table = pq.read_table(path).to_pylist()
    i = next(i for i, r in enumerate(table) if r["rxnorm_name_T"] == WARFARIN)
    table[i].update(rxcui_T=CODES[ASPIRIN], rxnorm_name_T=ASPIRIN, matched_by_T="prod_ai")
    pq.write_table(pa.Table.from_pylist(table, schema=pq.read_schema(path)), path)
    return {k: table[i][k] for k in ("era_T", "primaryid", "quarter_T", "drug_seq")}


def test_a_record_whose_code_names_another_drug_is_not_read_on_that_drugs_label(labelled):
    add_record_tables(labelled, CODES, FAMILIES, TRIAL)
    before = build_release_flags(labelled)["suspect_records"]["records"]
    key = _code_one_warfarin_record_as_aspirin(labelled)
    after = build_release_flags(labelled)["suspect_records"]["records"]
    assert after["code_names_another_drug"] == 1
    assert after["label"] == before["label"] - 1 and after["suspect"] == before["suspect"]
    other = manifest_of(labelled)["tables"]["label_other_drug_T"]
    rows = pq.read_table(labelled / other["path"]).to_pylist()
    assert [{k: r[k] for k in key} for r in rows] == [key] and other["rows"] == 1
    assert (rows[0]["rxcui_T"], rows[0]["substance_T"]) == (CODES[ASPIRIN], WARFARIN)


def test_a_code_more_precise_than_its_counted_ingredient_names_the_same_drug():
    unit = Unit(["insulin glargine", "oxybate", "acetaminophen", "diazepam", "valproate"])
    assert not unit.other_drug("insulin", "insulin glargine")  # a group and one of it
    assert not unit.other_drug("oxybate sodium", "oxybate")  # a salt and its drug
    assert not unit.other_drug("paracetamol", "acetaminophen")  # a reviewed name pair
    assert not unit.other_drug("potassium", "potassium chloride")  # an element alone
    assert not unit.other_drug("immunoglobulins, unspecified", "diazepam")  # coded nowhere
    assert unit.other_drug("valproic acid", "diazepam")  # another drug


def test_a_drug_rxnorm_names_two_ways_is_one_drug_through_the_reviewed_list():
    """CRESEMBA's records are counted as isavuconazole and coded isavuconazonium, its prodrug,
    whose label FDA's is; isavuconazole's own code names the same drug too."""
    unit = Unit(["isavuconazonium", "isavuconazole", "voriconazole"])
    assert not unit.other_drug("isavuconazole", "isavuconazonium")
    assert not unit.other_drug("isavuconazole", "isavuconazole")
    assert unit.other_drug("isavuconazole", "voriconazole")  # the list joins only its pair


def test_a_counted_group_name_is_not_compared_with_its_code(tmp_path):
    unit = Unit(["vitamin B6", "pyridoxine", "factor VIII", "efmoroctocog alfa"])
    assert rulebook.value("label-flags", "group_name_starts")
    assert not unit.other_drug("vitamin b6", "pyridoxine")
    assert not unit.other_drug("factor viii", "efmoroctocog alfa")
    with rules_with(tmp_path, {"label-flags": {"group_name_starts": []}}):
        assert Unit(["vitamin B6", "pyridoxine"]).other_drug("vitamin b6", "pyridoxine")


def test_a_record_on_several_dose_rows_counts_once(labelled):
    add_record_tables(labelled, CODES, FAMILIES, TRIAL)
    before = build_release_flags(labelled)["suspect_records"]
    path = labelled / "parquet" / "drug_latest_T.parquet"
    rows = pq.read_table(path)
    pq.write_table(pa.concat_tables([rows, rows.slice(0, 3)]), path)  # three more dose rows
    after = build_release_flags(labelled)
    assert after["suspect_records"] == before
    assert after["rows"] == len(flags_of(labelled))


def test_without_route_families_every_record_is_read_on_every_label_and_the_step_says_so(
    labelled,
):
    add_record_tables(labelled, CODES, None, TRIAL)
    done = build_release_flags(labelled)
    assert done["notes"] == [WITHOUT_ROUTE] == manifest_of(labelled)["label_flags"]["notes"]
    got = flags_of(labelled)
    assert {fam for _, fam, _ in got} == {""}
    assert got[("900001", "", "Headache")] == ("forms_differ", "by_mouth; injected")


def test_without_rxnorm_codes_no_flags_are_written_and_the_step_says_why(labelled):
    done = build_release_flags(labelled)
    assert "drug_rxnorm_T" in done["skipped"]
    entry = manifest_of(labelled)["label_flags"]
    assert entry == {"present": False, "reason": done["skipped"]}
    assert not (labelled / "parquet" / "label_flags_T.parquet").exists()


def test_the_command_line_codes_the_labels_then_flags_the_records(labelled, capsys):
    add_record_tables(labelled, CODES, FAMILIES, TRIAL)
    assert main(["labels", "--release", str(labelled)]) == 0
    done = json.loads(capsys.readouterr().out)
    assert done["coded"]["version"] == done["flags"]["version"] == VERSION
    assert done["flags"]["rows"] == len(flags_of(labelled))


def test_the_command_line_reads_the_rules_toml_where_it_runs_as_the_build_does(
    labelled, tmp_path, monkeypatch, capsys
):
    add_record_tables(labelled, CODES, FAMILIES, TRIAL)
    (tmp_path / rulebook.FILE_NAME).write_text("[label-flags]\non = false\n")
    monkeypatch.chdir(tmp_path)
    assert main(["labels", "--release", str(labelled)]) == 0
    skipped = json.loads(capsys.readouterr().out)["flags"]["skipped"]
    assert skipped.startswith("rule label-flags is switched off")


def test_a_person_can_flag_every_role(labelled, tmp_path):
    add_record_tables(labelled, CODES, FAMILIES, TRIAL)
    with rules_with(tmp_path, {"label-flags": {"suspect_roles": ["PS", "SS", "I", "C"]}}):
        done = build_release_flags(labelled)
    # the concomitant omeprazole now brings its case's vomiting to fakeoxacin's label
    assert ("900002", "", "Vomiting") in flags_of(labelled)
    assert done["suspect_records"]["records"]["suspect"] == 43
