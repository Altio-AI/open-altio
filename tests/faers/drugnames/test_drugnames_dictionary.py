"""The DiAna dictionary as the drug-name step reads it (rule drug-names): its
key, its checksum, its download, and our reviewed names and corrections, on an
invented dictionary (open_altio.testing.fakediana) and the committed mappings."""

from __future__ import annotations

import csv
import socket

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers.drugnames import dictionary
from open_altio.faers.drugnames.dictionary import DictionaryRefused, key_sql
from open_altio.testing import fakediana
from open_altio.testing.rules import rules_with

RULE = dictionary.RULE


def key(name: str | None) -> str | None:
    return duckdb.connect().execute(f"SELECT {key_sql('CAST(? AS VARCHAR)')}", [name]).fetchone()[0]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("HUMIRA", "humira"),
        ("Humira.", "humira"),  # one trailing period
        ("  HUMIRA   40 MG\tPEN ", "humira 40 mg pen"),  # spaces and tabs made one
        ("**HUMIRA**", "humira"),  # punctuation at both ends
        ("HUMIRA (ADALIMUMAB)", "humira (adalimumab)"),  # a closing bracket at the end stays
        ("(HUMIRA)", "(humira)"),  # and an opening one at the start
        ("HUMIRA ( ADALIMUMAB )", "humira (adalimumab)"),  # no space just inside a bracket
        ("HUMIRA (", "humira"),  # an opening bracket at the end is punctuation
        ("...", None),  # nothing left is no key
        (None, None),
    ],
)
def test_the_key_is_dianas_2023_cleaning(raw, expected):
    assert key(raw) == expected


def test_punctuation_is_stripped_twice_not_until_none_is_left():
    # DiAna strips the end, then the start, twice; a third layer stays, as in its script
    assert key("-x-") == "x"
    assert key(".-(x)-.") == "(x)"
    assert key("- -.- x") == "x"
    assert key("a-.-.-") == "a"


def test_only_one_trailing_period_is_removed_before_the_punctuation():
    assert key("tylenol.") == "tylenol"
    assert key("vitamin b12..") == "vitamin b12"  # the second goes with the trailing punctuation


@pytest.fixture
def fake(tmp_path):
    """The invented dictionary, with the rule pinning its checksum."""
    path = fakediana.write_dictionary(tmp_path / "ref" / "DiAna_dictionary.csv")
    with rules_with(tmp_path, {RULE: {"sha256": dictionary.sha256(path)}}):
        yield path


def test_a_file_whose_checksum_the_rule_does_not_pin_stops_the_build(tmp_path):
    path = fakediana.write_dictionary(tmp_path / "DiAna_dictionary.csv")
    with pytest.raises(DictionaryRefused, match="move the rule to its checksum"):
        dictionary.checked_file(path)


def test_the_pinned_file_is_accepted(fake):
    assert dictionary.checked_file(fake) == fake


def test_a_missing_file_is_downloaded_from_the_rules_address_and_checked(tmp_path):
    source = fakediana.write_dictionary(tmp_path / "osf" / "DiAna_dictionary.csv")
    target = tmp_path / "ref" / "DiAna_dictionary.csv"
    with rules_with(
        tmp_path, {RULE: {"sha256": dictionary.sha256(source), "download": source.as_uri()}}
    ):
        assert dictionary.checked_file(target) == target
    assert target.read_bytes() == source.read_bytes()


def test_a_download_with_another_checksum_is_refused_and_not_kept(tmp_path):
    source = fakediana.write_dictionary(tmp_path / "osf" / "DiAna_dictionary.csv")
    target = tmp_path / "ref" / "DiAna_dictionary.csv"
    with (
        rules_with(tmp_path, {RULE: {"download": source.as_uri()}}),
        pytest.raises(DictionaryRefused, match="downloaded"),
    ):
        dictionary.checked_file(target)
    assert list(target.parent.iterdir()) == []


def test_a_download_that_stalls_is_stopped_after_the_rules_timeout(tmp_path):
    # the server takes the connection but never answers
    with socket.create_server(("127.0.0.1", 0)) as server:
        url = f"http://127.0.0.1:{server.getsockname()[1]}/DiAna_dictionary.csv"
        with (
            rules_with(tmp_path, {RULE: {"download": url, "download_timeout_seconds": 1}}),
            pytest.raises(DictionaryRefused, match="timed out"),
        ):
            dictionary.fetch(tmp_path / "ref" / "DiAna_dictionary.csv")
    assert list((tmp_path / "ref").iterdir()) == []


def names(con) -> dict[str, tuple]:
    return {
        k: (s, t, c) for k, s, t, c in con.execute(f"SELECT * FROM {dictionary.TABLE}").fetchall()
    }


def test_the_dictionary_is_read_with_trial_marks_names_and_corrections(fake):
    con = duckdb.connect()
    facts = dictionary.load(con, fake)
    got = names(con)
    assert got["aspirin"] == ("acetylsalicylic acid", False, False)
    assert "bayer low dose" not in got  # NA: DiAna saw it and gave nothing
    assert got["entresto"] == ("sacubitril;valsartan", False, False)  # sorted, not a correction
    assert got["blinded lcz696"] == ("sacubitril;valsartan", True, False)
    assert got["study drug"] == ("unspecified", True, False)
    assert got["trametinib"] == ("trametinib", True, False)  # ',trial' with no space
    assert got["vevye"] == ("ciclosporin", False, True)  # names.csv
    assert got["tetrofosmin"] == ("technetium tc 99m tetrofosmin", False, True)
    assert got["tecfidera"] == ("dimethyl fumarate", False, True)  # corrections.csv
    assert got["fumaderm"] == ("fumaric acid", False, False)  # not named by the correction
    assert got["valstar"] == ("valrubicin", False, True)  # corrections.csv
    assert got["co valstar"] == ("hydrochlorothiazide;valsartan", False, False)  # not Valstar
    assert got["cortisone (hydrocortisone)"] == ("hydrocortisone", False, True)
    assert got["cortisone acetate"] == ("cortisone", False, False)
    assert got["isopropanolamine"] == ("isopropanolamine", False, True)
    assert got["lorax"] == ("lorazepam", False, True)
    assert got["lorax (lorazepam)"] == ("lorazepam", False, True)
    assert got["lorax (loratadine)"] == ("loratadine", False, False)  # Lorax that says loratadine
    assert got["refresh p.m"] == ("mineral oil;petrolatum", False, True)
    assert got["refresh tears"] == ("polyvinyl alcohol;povidone", False, False)
    powermax = "alka-seltzer plus maximum strength day and night cold and flu powermax gels"
    assert got[powermax] == ("dextromethorphan;doxylamine;paracetamol;phenylephrine", False, True)
    assert got["brexafemme"] == ("ibrexafungerp", False, True)
    assert got["hyoscine butylbromide"] == ("butylscopolamine", False, True)
    assert got["hyoscine butylbromide/metamizole"] == ("metamizole;scopolamine", False, False)
    assert got["levolet (levothyroxine sodium)"] == ("levothyroxine", False, True)
    assert got["levolet"] == ("levofloxacin", False, False)  # plain Levolet is not named
    assert facts["sha256"] == dictionary.sha256(fake)
    assert facts["keys_with_a_substance"] == len(got)
    tecfidera = next(c for c in facts["corrections"] if c["substance"] == "dimethyl fumarate")
    assert tecfidera["keys"] == 1


def _mapping(tmp_path, name: str, rows: list[dict]) -> str:
    path = tmp_path / f"{name}.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return str(path)


def _correction(**row) -> dict:
    return {
        "diana_substance": "fumaric acid",
        "spelling": "",
        "substance": "dimethyl fumarate",
        "reason": "r",
        "evidence": "e",
    } | row


def test_two_corrections_that_name_one_spelling_stop_the_build(tmp_path, fake):
    path = _mapping(tmp_path, "c", [_correction(spelling="tec"), _correction(spelling="fidera")])
    with (
        rules_with(tmp_path / "inner", {RULE: {"corrections": path}}),
        pytest.raises(DictionaryRefused, match="tecfidera"),
    ):
        dictionary.load(duckdb.connect(), fake)


def test_a_correction_must_write_its_sets_sorted(tmp_path, fake):
    path = _mapping(tmp_path, "c", [_correction(diana_substance="valsartan;sacubitril")])
    with (
        rules_with(tmp_path / "inner", {RULE: {"corrections": path}}),
        pytest.raises(DictionaryRefused, match="not sorted"),
    ):
        dictionary.load(duckdb.connect(), fake)


def test_a_correction_needs_its_reason_and_evidence(tmp_path, fake):
    path = _mapping(tmp_path, "c", [_correction(evidence="")])
    with (
        rules_with(tmp_path / "inner", {RULE: {"corrections": path}}),
        pytest.raises(DictionaryRefused, match="evidence empty"),
    ):
        dictionary.load(duckdb.connect(), fake)


def test_the_committed_mappings_are_well_formed():
    fixes = dictionary.corrections()
    assert fixes and all(row["reason"] and row["evidence"] for row in fixes)
    renamed = dictionary.read_mapping("names", dictionary.NAME_COLUMNS)
    assert len({r["diana_name"] for r in renamed}) == len(renamed)
    # a name is never renamed to a name that is itself renamed
    assert not {r["name"] for r in renamed} & {r["diana_name"] for r in renamed}
    misencoded = [r for r in renamed if fakediana.MISENCODED_SPACE in r["diana_name"]]
    assert misencoded and all(" " in r["name"] and " " not in r["name"] for r in misencoded)


def test_the_rule_names_the_mapping_files_in_the_repository():
    for value in ("corrections", "names"):
        assert (rulebook.data_root() / rulebook.value(RULE, value)).is_file()
