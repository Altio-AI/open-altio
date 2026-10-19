"""The numbers the methods story shows (src/open_altio/faers/insights/numbers.py): each counted on
a handful of invented cases whose answers are known, the cases set aside as duplicates left out;
and, on the fake releases, that the build writes them where the page reads them."""

from __future__ import annotations

import json
import operator
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from open_altio.faers import build_release
from open_altio.faers import release as release_module
from open_altio.faers.__main__ import main as faers_main
from open_altio.faers.drugnames.substances import UNMAPPED
from open_altio.faers.insights import numbers
from open_altio.faers.meddra import term_key
from open_altio.faers.meddra.licensed import read_licensed_manifest
from open_altio.stats import screen
from open_altio.testing import fakediana
from open_altio.testing.fakemeddra import write_meddra

ADA, ASA = "adalimumab", "acetylsalicylic acid"
TWO = "by_mouth;under_tongue"  # a route that allows two families
# (case, kept, event_dt, its precision as read, age, age_cod, age in years, occp_cod, reporter)
CASES = [
    ("A", True, "20200101", 6, "40", "YR", 40.0, "OT", 3),
    ("B", True, "20200315", 8, "6", "MON", 0.5, "HP", 3),
    ("C", True, "", None, "", None, None, "", None),
    ("D", False, "20200101", 6, "50", "YR", 50.0, "MD", 1),  # a duplicate set aside
]
# (case, seq, role, drug name, route, ingredient, route families, rxcui, ATC code, chosen by)
DRUGS = [
    ("A", 1, "PS", "HUMIRA", "SUBCUTANEOUS", ADA, "injected", "1", "L04AB04", "only_code"),
    ("A", 2, "C", "ASPIRIN", "", ASA, "", "2", "B01AC06", "dose"),
    ("B", 1, "SS", "ADALIMUMAB", "Unknown", ADA, TWO, "1", "L04AB04", "only_code"),
    ("B", 2, "PS", "Humira", None, ADA, "", None, None, "cannot_tell"),
    ("C", 1, "PS", "HUMIRA", "ORAL", ADA, "by_mouth", "1", "L04AB04", "only_code"),
    ("D", 1, "PS", "HUMIRA PEN", "ORAL", ADA, "by_mouth", "3", "L04AB04", "only_code"),
]
# (case, FDA's text); and each text's PT and whether FDA wrote that PT itself
REACTIONS = [("A", "Nausea"), ("B", "nausea"), ("B", "Headache"), ("C", "Headache"),
             ("C", "Head pain"), ("D", "Vomiting")]  # fmt: skip
MAPPED = {"Nausea": (100, True), "Headache": (200, False), "Head pain": (200, True),
          "Vomiting": (300, True)}  # fmt: skip
# the drug records whose name finds no ingredient: one shown, one of the duplicate set aside
UNMAPPED_RECORDS = {("A", 2), ("D", 1)}


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    key = "era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR"
    c.execute(
        f"""CREATE TABLE case_latest_T ({key}, case_key_T VARCHAR, dup_kept_T BOOLEAN,
            event_dt VARCHAR, event_dt_prec_T INTEGER, age VARCHAR, age_cod VARCHAR,
            age_years_T DOUBLE, occp_cod VARCHAR, reporter_type_T INTEGER)"""
    )
    c.executemany(
        "INSERT INTO case_latest_T VALUES ('faers', ?, '2020q1', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(case, case, *rest) for case, *rest in CASES],
    )
    drug = f"{key}, drug_seq VARCHAR"
    c.execute(
        f"CREATE TABLE drug_latest_T ({drug}, role_cod VARCHAR, drugname VARCHAR, route VARCHAR)"
    )
    c.execute(f"CREATE TABLE drug_ingredient_T ({drug}, ingredient_T VARCHAR)")
    c.execute(
        f"CREATE TABLE drug_substance_T ({drug}, substance_T VARCHAR, substance_source_T VARCHAR)"
    )
    c.execute(f"CREATE TABLE drug_route_T ({drug}, route_families_T VARCHAR)")
    c.execute(f"CREATE TABLE drug_rxnorm_T ({drug}, rxcui_T VARCHAR)")
    c.execute(
        f"""CREATE TABLE atc_drug_T ({drug}, atc_code_T VARCHAR, atc_chosen_by_T VARCHAR,
            atc_index_year_T INTEGER)"""
    )
    for case, seq, role, name, route, ing, families, rxcui, atc, chosen in DRUGS:
        k = ("faers", case, "2020q1", str(seq))
        c.execute("INSERT INTO drug_latest_T VALUES (?, ?, ?, ?, ?, ?, ?)", [*k, role, name, route])
        c.execute("INSERT INTO drug_ingredient_T VALUES (?, ?, ?, ?, ?)", [*k, ing])
        source = UNMAPPED if (case, seq) in UNMAPPED_RECORDS else "diana_name"
        c.execute("INSERT INTO drug_substance_T VALUES (?, ?, ?, ?, ?, ?)", [*k, ing, source])
        c.execute("INSERT INTO drug_route_T VALUES (?, ?, ?, ?, ?)", [*k, families])
        c.execute("INSERT INTO drug_rxnorm_T VALUES (?, ?, ?, ?, ?)", [*k, rxcui])
        c.execute("INSERT INTO atc_drug_T VALUES (?, ?, ?, ?, ?, ?, 2026)", [*k, atc, chosen])
    c.execute(
        """CREATE TABLE atc_index_T AS SELECT * FROM (VALUES
           ('L', 1, 'ANTINEOPLASTIC AND IMMUNOMODULATING AGENTS', 2026),
           ('B', 1, 'BLOOD AND BLOOD FORMING ORGANS', 2026))
           t(atc_code_T, atc_level_T, atc_name_T, atc_index_year_T)"""
    )
    c.execute(f"CREATE TABLE reac_latest_T ({key}, pt VARCHAR)")
    c.executemany(
        "INSERT INTO reac_latest_T VALUES ('faers', ?, '2020q1', ?)", [list(r) for r in REACTIONS]
    )
    c.execute(
        "CREATE TABLE reac_meddra_T (reac_term_T VARCHAR, pt_code_T INTEGER, pt_current_T BOOLEAN)"
    )
    c.executemany(
        "INSERT INTO reac_meddra_T VALUES (?, ?, ?)",
        [(term_key("pt", text), pt, current) for text, (pt, current) in MAPPED.items()],
    )
    return c


def test_event_dates_are_counted_as_written_and_as_read_with_the_padded_days(con):
    assert numbers.dates(con) == {
        "written": {"day": 2, "none": 1},
        "read": {"day": 1, "month": 1, "none": 1},
        "day_read_as_month_or_year": 1,
    }


def test_ages_are_counted_by_fdas_unit_and_as_read_in_years(con):
    assert numbers.ages(con) == {"units": {"MON": 1, "YR": 1}, "no_age": 1, "in_years": 2}


def test_reporters_are_counted_by_fdas_code_and_by_the_type_they_read_to(con):
    assert numbers.reporters(con) == {
        "written": {"HP": 1, "OT": 1, "none": 1},
        "read": {"3": 2, "none": 1},
    }


def test_routes_blank_or_saying_unknown_read_not_given_and_their_families_are_counted(con):
    assert numbers.routes(con) == {
        "rows": 5,
        "blank": 2,
        "says_unknown": 1,
        "not_given": 3,
        "families": {"families": 3, "one": 2, "several": 1, "not_known": 2},
    }


def test_drug_names_count_spellings_ingredients_and_what_one_spelling_misses(con):
    assert numbers.drug_names(con) == {
        "spellings": 4,
        "ingredients": 2,
        "combinations": 0,
        "spellings_per_ingredient": {"one": 1, "by_digits": [{"digits": 1, "ingredients": 2}]},
        "written_two_or_more_ways": 1,
        # adalimumab is a suspect in A, B and C; HUMIRA, its most common spelling, finds A and C
        "suspect_cases": {"by_ingredient": 3, "by_most_common_spelling": 2},
        # the five records of A, B and C, not D's, set aside; A's aspirin finds no ingredient
        "drug_records": 5,
        "unmapped_records": 1,
    }


def test_drug_names_count_ingredients_and_combinations_ignoring_capitals():
    c = duckdb.connect()
    key = "era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, drug_seq VARCHAR"
    shown = "SELECT 'faers' era_T, '1' primaryid, '2020q1' quarter_T"
    c.execute(f"CREATE TABLE case_latest_T AS SELECT *, true dup_kept_T FROM ({shown})")
    c.execute(f"CREATE TABLE drug_latest_T ({key}, role_cod VARCHAR, drugname VARCHAR)")
    c.execute(f"CREATE TABLE drug_ingredient_T ({key}, ingredient_T VARCHAR)")
    c.execute(
        f"CREATE TABLE drug_substance_T ({key}, substance_T VARCHAR, substance_source_T VARCHAR)"
    )
    records = [  # (drug name, ingredient, substance)
        ("A", "lactobacillus spp", "lactobacillus spp"),
        ("B", "lactobacillus SPP", "lactobacillus SPP"),
        ("C", "valsartan", "sacubitril;valsartan"),
        ("D", "sacubitril", "sacubitril;valsartan"),
        ("E", "valsartan", "SACUBITRIL;valsartan"),
    ]
    for seq, (name, ingredient, substance) in enumerate(records):
        row = ["faers", "1", "2020q1", str(seq)]
        c.execute("INSERT INTO drug_latest_T VALUES (?, ?, ?, ?, 'PS', ?)", [*row, name])
        c.execute("INSERT INTO drug_ingredient_T VALUES (?, ?, ?, ?, ?)", [*row, ingredient])
        c.execute(
            "INSERT INTO drug_substance_T VALUES (?, ?, ?, ?, ?, 'diana_name')", [*row, substance]
        )
    got = numbers.drug_names(c)
    assert (got["ingredients"], got["combinations"]) == (3, 1)


def test_rxnorm_counts_suspect_rows_their_codes_and_leaves_other_roles_out(con):
    assert numbers.rxnorm(con) == {
        "suspect_rows": 4,
        "coded_rows": 3,
        "codes": 1,
        "suspect_records": 4,
        "coded_records": 3,
    }


def test_rxnorm_counts_a_record_fda_repeats_on_two_dose_rows_once_as_a_record():
    c = duckdb.connect()
    shown = "SELECT 'faers' era_T, '1' primaryid, '2020q1' quarter_T"
    c.execute(f"CREATE TABLE case_latest_T AS SELECT *, true dup_kept_T FROM ({shown})")
    c.execute(f"CREATE TABLE drug_latest_T AS SELECT *, '1' drug_seq, 'PS' role_cod FROM ({shown})")
    c.execute("INSERT INTO drug_latest_T SELECT * FROM drug_latest_T")  # a second dose row
    c.execute(f"CREATE TABLE drug_rxnorm_T AS SELECT *, '1' drug_seq, '7' rxcui_T FROM ({shown})")
    got = numbers.rxnorm(c)
    assert (got["suspect_rows"], got["coded_rows"]) == (2, 2)
    assert (got["suspect_records"], got["coded_records"]) == (1, 1)


def test_classes_count_how_each_row_was_chosen_and_suspect_cases_per_main_group(con):
    assert numbers.classes(con) == {
        "rows": 5,
        "chosen_by": {"only_code": 3, "cannot_tell": 1, "dose": 1},
        "rows_with_class": 4,
        "codes": 2,
        # aspirin is only concomitant, so its main group has no suspect case
        "main_groups": [
            {"code": "L", "name": "ANTINEOPLASTIC AND IMMUNOMODULATING AGENTS", "cases": 3}
        ],
    }


def test_reaction_texts_are_public_and_their_meddra_terms_licensed(con):
    assert numbers.terms(con) == {"texts": 4}
    assert numbers.licensed(con) == {
        "terms": {"meddra_terms": 2},
        # B and C carry an older term of PT 200; C also has it as written today, so is found
        "older_terms": {"cases": 3, "with_an_older_term": 2, "missed_by_todays_term": 1},
    }


def test_a_release_without_a_part_has_no_numbers_for_it():
    c = duckdb.connect()
    c.execute(
        """CREATE TABLE case_latest_T AS SELECT 'faers' era_T, '1' primaryid, '2020q1' quarter_T,
           true dup_kept_T, '' event_dt, NULL::INTEGER event_dt_prec_T, '' age, '' age_cod,
           NULL::DOUBLE age_years_T, '' occp_cod, NULL::INTEGER reporter_type_T"""
    )
    c.execute(
        """CREATE TABLE drug_latest_T AS SELECT 'faers' era_T, '1' primaryid, '2020q1' quarter_T,
           '1' drug_seq, 'PS' role_cod, 'X' drugname, '' route"""
    )
    c.execute("CREATE TABLE reac_latest_T AS SELECT 'faers' era_T, '1' primaryid, "
              "'2020q1' quarter_T, 'Nausea' pt")  # fmt: skip
    assert sorted(numbers.public(c)) == ["ages", "dates", "reporters", "routes", "terms"]


def _cases_shown(methods: dict) -> int:
    return methods["funnel"]["steps"][-1]["count"]["total"]


def test_the_build_writes_the_numbers_over_the_cases_it_shows(stats_release):
    methods = json.loads((stats_release / "methods.json").read_text(encoding="utf-8"))
    got, shown = methods["numbers"], _cases_shown(methods)
    assert sum(got["dates"]["written"].values()) == sum(got["dates"]["read"].values()) == shown
    assert sum(got["ages"]["units"].values()) + got["ages"]["no_age"] == shown
    assert sum(got["reporters"]["written"].values()) == shown
    names = got["drug_names"]
    assert names["ingredients"] > 0 and names["spellings"] >= names["ingredients"]
    by_digits = sum(b["ingredients"] for b in names["spellings_per_ingredient"]["by_digits"])
    assert by_digits == names["ingredients"]
    cases = names["suspect_cases"]
    assert 0 < cases["by_most_common_spelling"] <= cases["by_ingredient"]


def test_the_licensed_numbers_go_to_the_licensed_manifest_and_agree_with_the_card(
    licensed_release: Path,
):
    methods = json.loads((licensed_release / "methods.json").read_text(encoding="utf-8"))
    assert "meddra_terms" not in json.dumps(methods["numbers"])
    [entry] = read_licensed_manifest(licensed_release)["meddra"]["versions"].values()
    older = entry["numbers"]["older_terms"]
    assert older["cases"] <= _cases_shown(methods) and entry["numbers"]["terms"]["meddra_terms"] > 0
    card = next(c for c in entry["insights"] if c["id"] == "older_meddra_terms_missed")
    assert f"misses {older['missed_by_todays_term']:,} of them" in card["two_sentences"]


def test_stand_out_counts_the_pairs_meeting_each_default_screen_and_no_other():
    c = duckdb.connect()
    defaults = {n: p for n in screen.RULES for p in screen.presets(n) if p.get("default")}
    columns = sorted({cond["column"] for p in defaults.values() for cond in p["when"]})
    c.execute(f"CREATE TABLE statistics_T ({', '.join(f'{x}_T DOUBLE' for x in columns)})")
    c.execute(f"INSERT INTO statistics_T VALUES ({', '.join(['NULL'] * len(columns))})")
    got = numbers.stand_out(c)
    assert got == {n: {"preset": p["id"], "pairs": 0} for n, p in defaults.items()}


def test_the_statistics_numbers_count_the_pairs_meeting_each_default_screen(stats_release):
    manifest = json.loads((stats_release / "manifest.json").read_text(encoding="utf-8"))
    methods = json.loads((stats_release / "methods.json").read_text(encoding="utf-8"))
    got = methods["numbers"]["statistics"]["stand_out"]
    table = pq.read_table(stats_release / manifest["tables"]["statistics_T"]["path"]).to_pylist()
    assert table
    defaults = {n: p for n in screen.RULES for p in screen.presets(n) if p.get("default")}
    assert sorted(got) == sorted(defaults)  # a statistic with no default is left out
    compare = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt}

    def meets(row: dict, when: list[dict]) -> bool:
        for cond in when:
            [op] = [k for k in cond if k != "column"]
            value = row[cond["column"] + "_T"]
            if value is None or not compare[screen.COMPARISONS[op]](value, cond[op]):
                return False
        return True

    for name, preset in defaults.items():
        pairs = sum(meets(row, preset["when"]) for row in table)
        assert got[name] == {"preset": preset["id"], "pairs": pairs}
        assert pairs <= manifest["statistics"]["counted"]["pairs"]


def _built(fake_input, fake_diana, folder: Path) -> Path:
    meddra = write_meddra(folder / "meddra" / "29.1", "29.1")
    with fakediana.pinned(fake_diana, folder):
        return build_release(fake_input, folder, diana_dictionary=fake_diana, meddra_dir=meddra)


def _numbers_of(release: Path) -> dict:
    [entry] = read_licensed_manifest(release)["meddra"]["versions"].values()
    return entry["numbers"]


def test_the_command_on_a_release_built_without_the_step_writes_what_the_build_writes(
    fake_input, fake_diana, tmp_path, monkeypatch
):
    built = _built(fake_input, fake_diana, tmp_path / "with")
    monkeypatch.setattr(release_module.numbers, "write", lambda *a, **k: {})
    without = _built(fake_input, fake_diana, tmp_path / "without")
    monkeypatch.undo()
    assert "numbers" not in json.loads((without / "methods.json").read_text(encoding="utf-8"))
    for n in range(2):  # and again: it replaces what it wrote
        with fakediana.pinned(fake_diana, tmp_path / f"rules{n}"):  # the rules it was built with
            assert faers_main(["methods", "--release", str(without)]) == 0
        assert (without / "methods.json").read_bytes() == (built / "methods.json").read_bytes()
        assert _numbers_of(without) == _numbers_of(built)
    left = [p.name for p in without.rglob("*") if p.name.endswith(".writing") or "spill" in p.name]
    assert left == []


def test_the_command_fills_what_we_do_not_do_again_as_the_package_words_it(
    fake_input, fake_diana, tmp_path
):
    built = _built(fake_input, fake_diana, tmp_path / "built")
    path = built / "methods.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    words = {item["id"]: item["text"] for item in doc["limits"]}
    doc["limits"] = [{**item, "text": "words an older package wrote"} for item in doc["limits"]]
    path.write_text(json.dumps(doc), encoding="utf-8")
    with fakediana.pinned(fake_diana, tmp_path / "rules"):
        assert faers_main(["methods", "--release", str(built)]) == 0
    again = json.loads(path.read_text(encoding="utf-8"))
    assert {item["id"]: item["text"] for item in again["limits"]} == words
