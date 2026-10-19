"""drug_rxnorm_T built on a release build's connection (rule
rxnorm-ingredients), from an invented RxNorm release and drug records whose
ingredients are made here as the drug names step will make them."""

from __future__ import annotations

import hashlib

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers.rxnorm import layer
from open_altio.faers.rxnorm.match import BARE_ELEMENT, DIFFERENT_PARENT, NO_NAME, NO_PRODUCT
from open_altio.faers.rxnorm.rrf import RxNormRefused
from open_altio.testing.fakerxnorm import CODES, write_rxnorm

# drug_seq -> (FDA's drug name and active ingredient as drugname_norm_T and prod_ai_norm_T
# write them, the dictionary's ingredient)
RECORDS = {
    "1": ("GLIMMEREX", None, "zorbatide"),  # a brand RxNorm holds: its own code
    "2": ("DUOTREL", None, "quintelamab"),  # the brand's code is more precise than the ingredient
    "3": ("TYLEX 500", None, "paracetamol"),  # no RxNorm name: the ingredient's, by name pair
    "4": ("ENHERTU", None, "trastuzumab deruxtecan"),  # filed under another drug, both ways
    "5": ("PADCEV", None, "enfortumab vedotin"),  # under its antibody, kept by the reviewed list
    "6": ("HERBAL TEA", None, "camellia spp"),  # nothing in RxNorm
    "7": ("UNKNOWN PILL", None, None),  # no ingredient at all
    "8": ("APAZOR", None, "acetaminophen;zorbatide"),  # no product has exactly this set
    "9": ("KCL", "POTASSIUM CHLORIDE", "potassium"),  # FDA's active ingredient names the salt
    "10": ("K-TAB", None, "potassium"),  # only the dictionary's element: no code
    "11": ("POTASSIUM", None, "potassium"),  # FDA's drug name is the element itself
    "12": ("DUO PILL", "QUINTELAMAB\\VELTROZINE", "quintelamab"),  # FDA's parts give the set
    "13": ("FOSNETA", "FOSNETAZINE", "camellia spp"),  # FDA's ingredient is under a parent
}


CONCOMITANT = "6"  # the one record given as a background drug, never a suspect


def code(name: str) -> str:
    return CODES[name][0]


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE drug_latest_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
        "drug_seq VARCHAR, drugname_norm_T VARCHAR, prod_ai_norm_T VARCHAR, role_cod VARCHAR)"
    )
    con.execute(
        "CREATE TABLE drug_substance_T (era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR, "
        "drug_seq VARCHAR, substance_T VARCHAR)"
    )
    for seq, (name, prod_ai, substance) in RECORDS.items():
        key = ["faers", "100", "2026q2", seq]
        role = "C" if seq == CONCOMITANT else "PS"
        con.execute(
            "INSERT INTO drug_latest_T VALUES (?, ?, ?, ?, ?, ?, ?)", [*key, name, prod_ai, role]
        )
        con.execute("INSERT INTO drug_substance_T VALUES (?, ?, ?, ?, ?)", [*key, substance])
    # FDA repeats a record's key on a row per dose, with the same drug name
    for _ in range(2):
        con.execute(
            "INSERT INTO drug_latest_T "
            "VALUES ('faers', '100', '2026q2', '1', 'GLIMMEREX', NULL, 'PS')"
        )
        con.execute(
            "INSERT INTO drug_substance_T VALUES ('faers', '100', '2026q2', '1', 'zorbatide')"
        )
    return con


def records(con) -> dict:
    cols = ", ".join(layer.COLUMNS)
    rows = con.execute(f"SELECT DISTINCT drug_seq, {cols} FROM {layer.TABLE}").fetchall()
    return {r[0]: r[1:] for r in rows}


def test_one_row_per_row_of_the_ingredients_table_when_fda_repeats_a_key(con, tmp_path):
    layer.build(con, write_rxnorm(tmp_path / "rxnorm"))
    count = "SELECT drug_seq, count(*) FROM {} GROUP BY 1 ORDER BY 1"
    assert (
        con.execute(count.format(layer.TABLE)).fetchall()
        == con.execute(count.format("drug_substance_T")).fetchall()
    )


def test_the_drug_name_comes_first_then_the_ingredient(con, tmp_path):
    layer.build(con, write_rxnorm(tmp_path / "rxnorm"))
    got = records(con)
    assert got["1"] == (code("zorbatide"), "zorbatide", "IN", "drug_name", None)
    assert got["2"] == (
        code("quintelamab / veltrozine"),
        "quintelamab / veltrozine",
        "MIN",
        "drug_name",
        None,
    )
    assert got["3"] == (code("acetaminophen"), "acetaminophen", "IN", "substance", None)
    assert got["5"][:4] == (code("enfortumab"), "enfortumab", "IN", "drug_name")


def test_fdas_active_ingredient_comes_second_so_a_salt_takes_its_own_code(con, tmp_path):
    layer.build(con, write_rxnorm(tmp_path / "rxnorm"))
    got = records(con)
    assert got["9"] == (
        code("potassium chloride"),
        "potassium chloride",
        "IN",
        "prod_ai",
        None,
    )
    assert got["12"] == (
        code("quintelamab / veltrozine"),
        "quintelamab / veltrozine",
        "MIN",
        "prod_ai",
        None,
    )


def test_an_element_only_the_dictionary_names_has_no_code_unless_fda_names_it(con, tmp_path):
    layer.build(con, write_rxnorm(tmp_path / "rxnorm"))
    got = records(con)
    assert got["10"] == (None, None, None, "none", BARE_ELEMENT)
    assert got["11"] == (code("potassium"), "potassium", "IN", "drug_name", None)


def test_a_record_without_a_code_says_why(con, tmp_path):
    layer.build(con, write_rxnorm(tmp_path / "rxnorm"))
    got = records(con)
    assert got["4"] == (None, None, None, "none", DIFFERENT_PARENT)
    assert got["6"] == (None, None, None, "none", NO_NAME)
    assert got["7"] == (None, None, None, "none", NO_NAME)
    assert got["8"] == (None, None, None, "none", NO_PRODUCT)
    assert got["13"] == (None, None, None, "none", DIFFERENT_PARENT)


def test_records_the_rxnorm_release_its_files_and_counts(con, tmp_path):
    folder = write_rxnorm(tmp_path / "rxnorm")
    entry = layer.build(con, folder)
    assert entry["present"] and entry["table"] == layer.TABLE
    assert entry["release"] == str(rulebook.value("rxnorm-ingredients", "release"))
    assert entry["download"].endswith(f"RxNorm_full_prescribe_{entry['release']}.zip")
    conso = (folder / "rrf" / "RXNCONSO.RRF").read_bytes()
    assert entry["files"][0] == {
        "file": "rrf/RXNCONSO.RRF",
        "bytes": len(conso),
        "sha256": hashlib.sha256(conso).hexdigest(),
    }
    assert entry["records_by_how"] == {"drug_name": 6, "prod_ai": 2, "substance": 1, "none": 6}
    tables = [r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()]
    assert sorted(t for t in tables if "rxnorm" in t) == sorted(layer.TABLES)  # scratch gone


def test_each_ingredient_a_record_is_counted_under_gets_the_code_its_own_reading_gives(
    con, tmp_path
):
    """One row per ingredient, however many records name it, a combination's ingredients each
    on their own: acetaminophen and zorbatide have codes though no product holds exactly the
    two. The reading is the ingredient's, never a record's drug name: zorbatide's record coded
    by its brand and paracetamol's by its name pair give the same codes as their ingredients."""
    entry = layer.build(con, write_rxnorm(tmp_path / "rxnorm"))
    cols = "ingredient_T, rxcui_T, tty_T, no_code_reason_T"
    got = {r[0]: r[1:] for r in con.execute(f"SELECT {cols} FROM {layer.INGREDIENTS}").fetchall()}
    assert got == {
        "zorbatide": (code("zorbatide"), "IN", None),
        "quintelamab": (code("quintelamab"), "IN", None),
        "paracetamol": (code("acetaminophen"), "IN", None),
        "acetaminophen": (code("acetaminophen"), "IN", None),
        "trastuzumab deruxtecan": (None, None, DIFFERENT_PARENT),
        "enfortumab vedotin": (code("enfortumab"), "IN", None),
        "camellia spp": (None, None, NO_NAME),
        "potassium": (None, None, BARE_ELEMENT),
    }
    assert entry["ingredients"] == {"table": layer.INGREDIENTS, "ingredients": 8, "coded": 5}


def test_the_entry_counts_the_suspect_records_and_how_many_have_a_code(con, tmp_path):
    """Records, never rows: record 1 is written on three dose rows. Record 6 is a background
    drug, so it is no suspect record whatever its code."""
    entry = layer.build(con, write_rxnorm(tmp_path / "rxnorm"))
    coded = {"1", "2", "3", "5", "9", "11", "12"}
    suspect = set(RECORDS) - {CONCOMITANT}
    assert entry["suspect_records"] == {
        "roles": rulebook.value("label-flags", "suspect_roles"),
        "records": len(suspect),
        "coded": len(coded),
        "coded_share": round(100.0 * len(coded) / len(suspect), 2),
    }


def test_without_a_folder_or_ingredients_it_writes_nothing_and_says_why(con, tmp_path):
    assert layer.build(con, None)["reason"] == "no RxNorm folder given"
    with rulebook.use_user_rules(rulebook.UserRules(off=frozenset({"rxnorm-ingredients"}))):
        off = layer.build(con, write_rxnorm(tmp_path / "rxnorm"))
    assert off["present"] is False and off["reason"] == "switched off in your rules"
    bare = duckdb.connect()
    entry = layer.build(bare, write_rxnorm(tmp_path / "rxnorm"))
    assert entry["present"] is False and "drug_substance_T" in entry["reason"]
    tables = [r[0] for r in bare.execute("SELECT table_name FROM duckdb_tables()").fetchall()]
    assert layer.TABLE not in tables and layer.INGREDIENTS not in tables


def test_refuses_a_folder_of_another_release(con, tmp_path):
    with pytest.raises(RxNormRefused, match="01012000"):
        layer.build(con, write_rxnorm(tmp_path / "rxnorm", release="01012000"))


def test_a_person_may_read_another_rxnorm_release_which_the_entry_records(con, tmp_path):
    folder = write_rxnorm(tmp_path / "rxnorm", release="01012000")
    chosen = rulebook.UserRules(values={"rxnorm-ingredients": {"release": "01012000"}})
    with rulebook.use_user_rules(chosen):
        entry = layer.build(con, folder)
    assert entry["release"] == "01012000"
    assert entry["download"].endswith("RxNorm_full_prescribe_01012000.zip")
