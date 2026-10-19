"""drug_rxnorm_T in a release (rule rxnorm-ingredients): built at release
time, beside the drug names step's drug_substance_T, from the pinned RxNorm
release, which the manifest records."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from open_altio import rulebook
from open_altio.faers import build_release
from open_altio.faers.release import ReleaseError
from open_altio.faers.rxnorm import layer
from open_altio.faers.rxnorm.match import BARE_ELEMENT, NO_NAME
from open_altio.faers.rxnorm.rrf import RULE
from open_altio.testing import fakediana
from open_altio.testing.fakerxnorm import CODES, write_rxnorm
from open_altio.testing.releasereader import ReleaseReader

_KEY = ", ".join(layer.RECORD)


def test_a_release_built_without_rxnorm_carries_no_codes_and_says_why(rel):
    entry = rel.manifest["rxnorm"]
    assert entry["present"] is False and entry["reason"] == "no RxNorm folder given"
    assert entry["release"] == str(rulebook.value("rxnorm-ingredients", "release"))
    assert layer.TABLE not in rel.manifest["tables"]


@pytest.fixture(scope="module")
def coded(fake_input, fake_diana, tmp_path_factory) -> ReleaseReader:
    """The fake release built with the invented dictionary and the invented RxNorm."""
    folder = tmp_path_factory.mktemp("rxnorm_release")
    rxnorm = write_rxnorm(folder / "rxnorm")
    with fakediana.pinned(fake_diana, folder):
        built = build_release(
            fake_input, folder / "out", diana_dictionary=fake_diana, rxnorm_dir=rxnorm
        )
    return ReleaseReader(built)


def test_a_release_built_with_rxnorm_carries_the_table_and_records_the_release(coded):
    entry = coded.manifest["rxnorm"]
    assert entry["present"] and entry["release"] == rulebook.value("rxnorm-ingredients", "release")
    assert [f["file"] for f in entry["files"]] == ["rrf/RXNCONSO.RRF", "rrf/RXNREL.RRF"]
    assert coded.manifest["tables"][layer.TABLE]["kind"] == "derived"
    assert coded.columns(layer.TABLE) == [*layer.RECORD, *layer.COLUMNS]
    assert coded.manifest["tables"][layer.INGREDIENTS]["kind"] == "derived"
    assert coded.columns(layer.INGREDIENTS) == [
        "ingredient_T",
        "rxcui_T",
        "rxnorm_name_T",
        "tty_T",
        "no_code_reason_T",
    ]


def test_the_methods_page_states_what_has_no_code_over_the_cases_shown(coded):
    methods = json.loads((coded.path / "methods.json").read_text(encoding="utf-8"))
    limit = next(item for item in methods["limits"] if item["id"] == "rxnorm_us_drugs_only")
    roles = ", ".join(f"'{r}'" for r in rulebook.value("explorer-drug-counts", "default_roles"))
    [(records, with_code)] = coded.rows(
        f"""SELECT count(*), count(x.rxcui_T)
            FROM (SELECT DISTINCT {", ".join(f"d.{k}" for k in layer.RECORD)}
                  FROM drug_latest_T d JOIN case_latest_T c ON {coded.case_join("d")}
                  WHERE c.dup_kept_T AND d.role_cod IN ({roles})) d
            LEFT JOIN {layer.TABLE} x USING ({_KEY})"""
    )
    assert f"{100 * with_code / records:.1f}% of suspect drug records" in limit["text"]
    assert f"({with_code:,} of {records:,})" in limit["text"] and "needs" not in limit


def test_a_release_without_rxnorm_has_no_rxnorm_limit(rel):
    methods = json.loads((rel.path / "methods.json").read_text(encoding="utf-8"))
    ids = [item["id"] for item in methods["limits"]]
    assert "rxnorm_us_drugs_only" not in ids and "no_rxnorm" not in ids


def test_one_row_per_drug_record_of_the_drug_names_step(coded):
    count = f"SELECT count(*), count(DISTINCT ({_KEY})) FROM {{}}"
    assert coded.rows(count.format(layer.TABLE)) == coded.rows(count.format("drug_substance_T"))
    assert coded.rows(f"""SELECT count(*) FROM drug_substance_T s
                          ANTI JOIN {layer.TABLE} r USING ({_KEY})""") == [(0,)]


def test_the_drug_name_first_then_fdas_active_ingredient(coded):
    cols = "d.drugname, r.rxcui_T, r.matched_by_T, r.no_code_reason_T"
    rows = set(
        coded.rows(f"""SELECT DISTINCT {cols} FROM {layer.TABLE} r
                              JOIN drug_latest_T d USING ({_KEY})
                              WHERE d.drugname IN ('WARFARIN', 'BAYER LOW DOSE', 'IBUPROFEN')""")
    )
    assert rows == {
        ("WARFARIN", CODES["warfarin"][0], "drug_name", None),
        ("BAYER LOW DOSE", CODES["aspirin"][0], "prod_ai", None),  # FDA's prod_ai is ASPIRIN
        ("IBUPROFEN", None, "none", NO_NAME),
    }


def test_a_folder_of_another_rxnorm_release_refuses_the_build(fake_input, fake_diana, tmp_path):
    rxnorm = write_rxnorm(tmp_path / "rxnorm", release="01012000")
    with fakediana.pinned(fake_diana, tmp_path), pytest.raises(ReleaseError, match="RxNorm"):
        build_release(fake_input, tmp_path / "out", diana_dictionary=fake_diana, rxnorm_dir=rxnorm)
    assert not any((tmp_path / "out").iterdir())


@pytest.fixture(scope="module")
def real() -> ReleaseReader:
    """A real release, built with RxNorm."""
    release = os.environ.get("OPEN_ALTIO_REAL_RELEASE")
    if not release:
        pytest.skip("set OPEN_ALTIO_REAL_RELEASE")
    reader = ReleaseReader(Path(release).expanduser())
    if layer.TABLE not in reader.manifest["tables"]:
        pytest.skip(f"{release} was built without RxNorm")
    reader.con.execute("SET memory_limit = '6GB'; SET threads = 4")
    return reader


@pytest.mark.slow
def test_on_a_real_release_every_drug_record_has_one_row_that_says_how_or_why_not(real):
    count = f"SELECT count(*), count(DISTINCT ({_KEY})) FROM {{}}"
    assert real.rows(count.format(layer.TABLE)) == real.rows(count.format("drug_substance_T"))
    how = {layer.DRUG_NAME, layer.PROD_AI, layer.SUBSTANCE, layer.NONE}
    assert {r[0] for r in real.rows(f"SELECT DISTINCT matched_by_T FROM {layer.TABLE}")} <= how
    unexplained = f"""SELECT count(*) FROM {layer.TABLE}
        WHERE (rxcui_T IS NULL) = (no_code_reason_T IS NULL)
           OR (rxcui_T IS NULL) <> (matched_by_T = '{layer.NONE}')"""
    assert real.rows(unexplained) == [(0,)]


@pytest.mark.slow
def test_on_a_real_release_no_element_alone_comes_from_the_dictionary(real):
    elements = [e.lower() for e in rulebook.value(RULE, "bare_elements")]
    from_dictionary = f"""SELECT count(*) FROM {layer.TABLE}
        WHERE matched_by_T = '{layer.SUBSTANCE}' AND list_contains(?, lower(rxnorm_name_T))"""
    assert real.rows(from_dictionary, elements) == [(0,)]
    refused = f"SELECT count(*) FROM {layer.TABLE} WHERE no_code_reason_T = ?"
    assert real.rows(refused, BARE_ELEMENT)[0][0] > 0


@pytest.mark.slow
def test_on_a_real_release_kcl_takes_the_salt_fda_names(real):
    kcl = f"""SELECT DISTINCT r.rxnorm_name_T, r.matched_by_T FROM {layer.TABLE} r
        JOIN (SELECT DISTINCT {_KEY} FROM drug_latest_T
              WHERE drugname_norm_T = 'KCL' AND prod_ai_norm_T = 'POTASSIUM CHLORIDE') k
        USING ({_KEY})"""
    assert real.rows(kcl) == [("potassium chloride", layer.PROD_AI)]
