"""The drug-name step in a release (rule drug-names): the shared fake release
is built with the invented dictionary and read back from its files; a release
built without the dictionary says so; and, marked slow, the step runs on a real
release folder with DiAna's own dictionary.

    OPEN_ALTIO_REAL_RELEASE=~/releases/2026Q2 \\
    OPEN_ALTIO_DIANA_DICTIONARY=~/reference/DiAna_dictionary.csv \\
    .venv/bin/pytest -m slow tests/faers/drugnames/test_drugnames_release.py
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path

import duckdb
import pytest

from open_altio.faers import ReleaseError, build_release
from open_altio.faers.build import build_release as one_build
from open_altio.faers.drugnames import dictionary, substances
from open_altio.faers.insights.cards import MissingDataWarning
from open_altio.faers.reader import register_release
from open_altio.rulebook import UserRules
from open_altio.testing import fakediana
from open_altio.testing.releasereader import ReleaseReader

_KEY = "era_T, primaryid, quarter_T, drug_seq"


def test_the_release_carries_both_tables_and_records_the_dictionary(rel, fake_diana):
    for table in substances.TABLES:
        assert rel.manifest["tables"][table]["kind"] == "derived"
    entry = rel.manifest["drug_names"]
    assert entry["present"] and entry["tables"] == list(substances.TABLES)
    assert entry["dictionary"]["sha256"] == dictionary.sha256(fake_diana)
    assert (
        entry["drug_records"]
        == rel.rows(f"SELECT count(DISTINCT ({_KEY})) FROM drug_latest_T")[0][0]
    )


def test_every_drug_record_has_one_row_and_fdas_values_stay(rel):
    records = rel.rows(f"SELECT count(DISTINCT ({_KEY})) FROM drug_latest_T")[0][0]
    assert rel.rows(f"SELECT count(*), count(DISTINCT ({_KEY})) FROM drug_substance_T") == [
        (records, records)
    ]
    # the fake BAYER LOW DOSE is listed with no substance: FDA's prod_ai supplies it, unchanged
    assert rel.rows(f"""SELECT d.drugname, d.prod_ai, s.substance_T, s.substance_source_T
                        FROM drug_latest_T d JOIN drug_substance_T s USING ({_KEY})
                        WHERE d.drugname = 'BAYER LOW DOSE'""") == [
        ("BAYER LOW DOSE", "ASPIRIN", "acetylsalicylic acid", "diana_prod_ai")
    ]


def test_the_funnel_has_a_drug_name_step_that_removes_no_case(rel):
    steps = rel.funnel["steps"]
    step = rel.step("drug_names")
    assert step["count"] == steps[steps.index(step) - 1]["count"]
    assert set(step["removed"].values()) == {0}
    assert "needs" not in step


def test_the_methods_page_states_the_unmapped_share_over_the_cases_shown_and_links_the_cards(rel):
    methods = json.loads((rel.path / "methods.json").read_text())
    [(records, unmapped)] = rel.rows(
        f"""SELECT count(*), count(*) FILTER (WHERE s.substance_source_T = '{substances.UNMAPPED}')
            FROM drug_substance_T s JOIN case_latest_T c ON {rel.case_join("s")}
            WHERE c.dup_kept_T"""
    )
    limit = next(item for item in methods["limits"] if item["id"] == "unmapped_drug_names")
    assert f"{100 * unmapped / records:.2f}% of drug records" in limit["text"]
    assert f"({unmapped:,} of {records:,})" in limit["text"] and "needs" not in limit
    step = next(s for s in methods["steps"] if s["id"] == "drug_names")
    cards = [c for c in methods["insights"] if c["notebook"].endswith("05_drug_names.ipynb")]
    assert cards and {c["id"] for c in cards} == set(step["insights"])


@pytest.fixture(scope="module")
def unnamed(fake_input, tmp_path_factory) -> ReleaseReader:
    """The fake quarters built without a dictionary; no card warns that it lacks data."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", MissingDataWarning)
        return ReleaseReader(build_release(fake_input, tmp_path_factory.mktemp("unnamed")))


def test_a_release_without_the_dictionary_has_no_drug_names_and_says_so(unnamed):
    assert not set(substances.TABLES) & set(unnamed.manifest["tables"])
    assert unnamed.manifest["drug_names"] == {
        "present": False,
        "reason": "no DiAna dictionary given",
    }
    assert "drug_names" not in [s["id"] for s in unnamed.funnel["steps"]]
    methods = json.loads((unnamed.path / "methods.json").read_text())
    assert "unmapped_drug_names" not in [item["id"] for item in methods["limits"]]
    cards = [c for c in methods["insights"] if c["notebook"].endswith("05_drug_names.ipynb")]
    assert len(cards) == 3
    for card in cards:
        assert card["tag"]["kind"] == "documented"
        assert "built without the DiAna dictionary" in card["two_sentences"], card["id"]
        assert card["chart"]["x"]["values"] == [] and card["chart"]["series"] == []


def test_the_one_build_reads_the_dictionary_kept_on_this_machine_and_never_fetches_it(
    fake_input, fake_diana, tmp_path, monkeypatch
):
    monkeypatch.setenv(dictionary.DIANA_ENV, str(tmp_path / "nowhere.csv"))
    bare = ReleaseReader(one_build(fake_input, tmp_path / "bare"))
    assert bare.manifest["drug_names"] == {"present": False, "reason": "no DiAna dictionary given"}
    assert not (tmp_path / "nowhere.csv").exists()
    monkeypatch.setenv(dictionary.DIANA_ENV, str(fake_diana))
    with fakediana.pinned(fake_diana, tmp_path):
        named = ReleaseReader(one_build(fake_input, tmp_path / "named"))
    assert set(substances.TABLES) <= set(named.manifest["tables"])


def test_switched_off_the_rule_builds_no_drug_names_even_with_the_dictionary(
    fake_input, fake_diana, tmp_path
):
    with fakediana.pinned(fake_diana, tmp_path):
        off = ReleaseReader(
            build_release(
                fake_input,
                tmp_path / "out",
                diana_dictionary=fake_diana,
                user_rules=UserRules(off=frozenset({dictionary.RULE})),
            )
        )
    assert off.manifest["drug_names"] == {
        "present": False,
        "reason": f"rule {dictionary.RULE} is off",
    }
    assert not set(substances.TABLES) & set(off.manifest["tables"])


def test_a_dictionary_the_rule_does_not_pin_refuses_the_release(fake_input, tmp_path):
    path = fakediana.write_dictionary(tmp_path / "DiAna_dictionary.csv")
    with pytest.raises(ReleaseError, match="drug names"):
        build_release(fake_input, tmp_path / "out", diana_dictionary=path)
    assert not (tmp_path / "out" / "2026Q2").exists()


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """The step run on a real release's drug_latest_T, with DiAna's dictionary."""
    release = os.environ.get("OPEN_ALTIO_REAL_RELEASE")
    diana = os.environ.get("OPEN_ALTIO_DIANA_DICTIONARY")
    if not release or not diana:
        pytest.skip("set OPEN_ALTIO_REAL_RELEASE and OPEN_ALTIO_DIANA_DICTIONARY")
    work = tmp_path_factory.mktemp("real_drug_names")
    con = duckdb.connect(str(work / "step.duckdb"))
    con.execute(f"SET temp_directory = '{work / 'spill'}'")
    con.execute("SET memory_limit = '6GB'; SET threads = 4; SET preserve_insertion_order = false")
    register_release(con, Path(release).expanduser(), temporary=True, with_views=False)
    return con, substances.build(con, Path(diana).expanduser())


@pytest.mark.slow
def test_on_a_real_release_the_dose_rows_of_a_record_agree_on_its_name(real):
    con, _ = real
    differ = con.execute(f"""SELECT count(*) FROM (
        SELECT {_KEY} FROM drug_latest_T GROUP BY ALL HAVING count(*) > 1
           AND (min(drugname) IS DISTINCT FROM max(drugname)
                OR min(prod_ai) IS DISTINCT FROM max(prod_ai)))""")
    assert differ.fetchone()[0] == 0


@pytest.mark.slow
def test_on_a_real_release_every_record_gets_one_answer_and_every_correction_applies(real):
    con, entry = real
    one = con.execute(f"SELECT count(*), count(DISTINCT ({_KEY})) FROM drug_substance_T").fetchone()
    assert one[0] == one[1] == entry["drug_records"]
    assert entry["unused_corrections"] == []
    assert sum(entry["records_by_source"].values()) == entry["drug_records"]
    # an unmapped share above a few percent would mean the key or the file broke
    assert 0 < entry["unmapped_share"] < 5
    sep = dictionary.SEPARATOR
    unsorted = con.execute(f"""SELECT count(*) FROM drug_substance_T WHERE substance_T <>
        array_to_string(list_sort(list_distinct(string_split(substance_T, '{sep}'))), '{sep}')""")
    assert unsorted.fetchone()[0] == 0
    answers = dict(
        con.execute(f"""SELECT d.drugname, any_value(s.substance_T) FROM drug_latest_T d
        JOIN drug_substance_T s USING ({_KEY})
        WHERE d.drugname IN ('HUMIRA', 'TECFIDERA', 'VEVYE', 'ENTRESTO', 'ISTURISA')
        GROUP BY 1""").fetchall()
    )
    assert answers == {
        "HUMIRA": "adalimumab",
        "TECFIDERA": "dimethyl fumarate",
        "VEVYE": "ciclosporin",
        "ENTRESTO": "sacubitril;valsartan",
        "ISTURISA": "osilodrostat",
    }
    assert (
        con.execute("SELECT count(*) FROM drug_substance_T WHERE diana_trial_T").fetchone()[0] > 0
    )
    assert (
        con.execute(
            "SELECT count(*) FROM drug_substance_T WHERE substance_T LIKE '%trial%'"
        ).fetchone()[0]
        == 0
    )
