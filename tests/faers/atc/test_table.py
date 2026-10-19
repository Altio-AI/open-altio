"""Building our drug-to-class table from WHO's index (rules atc-index and
atc-spelling-bridges), on an invented index, and the table committed in
mappings/."""

from __future__ import annotations

import csv
import json

import pytest

from open_altio import rulebook
from open_altio.faers.__main__ import main
from open_altio.faers.atc.table import (
    COLUMNS,
    TableRefused,
    build_table,
    read_bridges,
    read_groups,
    repo_path,
)
from open_altio.faers.rxnorm.match import substance_key
from open_altio.testing.fakewho import BRIDGES, write_bridges, write_index
from open_altio.testing.rules import rules_with

YEAR = int(rulebook.value("atc-index", "index_year"))


def _no_groups(path):
    """An empty group list: the repository's names classes the invented index does not hold."""
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerow(("substance", "atc_code", "reason"))
    return path


@pytest.fixture
def built(tmp_path):
    out = tmp_path / "classes.csv"
    summary = build_table(
        write_index(tmp_path / "who"),
        out,
        bridges=write_bridges(tmp_path / "bridges.csv"),
        groups=_no_groups(tmp_path / "groups.csv"),
    )
    with out.open(encoding="utf-8", newline="") as fh:
        return summary, list(csv.DictReader(fh))


def _codes(rows, ingredient):
    return sorted(r["atc_code"] for r in rows if r["ingredient"] == ingredient)


def test_a_substance_with_two_uses_has_both_codes(built):
    _, rows = built
    assert _codes(rows, "zelotolol") == ["C07ZZ01", "S01ZZ01"]


def test_a_combination_is_keyed_by_its_whole_ingredient_set(built):
    _, rows = built
    assert _codes(rows, "dostavir;plenivir") == ["J05ZZ51"]
    assert (
        next(r["who_name"] for r in rows if r["atc_code"] == "J05ZZ51") == "plenivir and dostavir"
    )


def test_a_bridge_adds_the_dictionarys_spelling_and_keeps_WHOs(built):
    _, rows = built
    assert _codes(rows, "korvastatin") == _codes(rows, "korvastatin calcium") == ["C10ZZ01"]
    assert _codes(rows, "lumavir;plenivir") == [
        "J05ZZ53"
    ]  # lumavir is coded only in the combination


def test_combinations_named_by_an_unbridged_class_or_as_combinations_are_left_out(built):
    summary, rows = built
    assert summary["combination_codes_left_out"] == ["J05ZZ52", "J05ZZ54"]
    assert not {"J05ZZ52", "J05ZZ54"} & {r["atc_code"] for r in rows}


def test_every_level_above_a_substance_code_has_WHOs_name(built):
    _, rows = built
    classes = {r["atc_code"]: r for r in rows if not r["ingredient"]}
    for code in {r["atc_code"] for r in rows if r["ingredient"]}:
        for n, level in ((1, 1), (3, 2), (4, 3), (5, 4)):
            assert classes[code[:n]]["level"] == str(level)
    assert classes["N02ZZ"]["who_name"] == "Invented analgesics"


def _build(tmp_path, bridges=(), groups=()):
    """The table from the invented index, with these bridges added to the invented ones and
    these group classes."""
    bridge_file, group_file = tmp_path / "bridges.csv", tmp_path / "groups.csv"
    with bridge_file.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows([*BRIDGES, *bridges])
    with group_file.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(
            [("substance", "atc_code", "reason"), *groups]
        )
    out = tmp_path / "classes.csv"
    summary = build_table(
        write_index(tmp_path / "who"), out, bridges=bridge_file, groups=group_file
    )
    with out.open(encoding="utf-8", newline="") as fh:
        return summary, list(csv.DictReader(fh))


def test_a_bridge_on_a_combinations_whole_name_joins_its_code_to_the_set_or_part_it_names(
    tmp_path,
):
    summary, rows = _build(
        tmp_path,
        [
            ("plenivir, combinations", "Plenivir ; Boostavir", "WHO codes the pair as one"),
            ("plenivir and boosters", "boostavir", "the part named alone is always the pair"),
        ],
    )
    assert _codes(rows, "boostavir;plenivir") == ["J05ZZ54"]  # sorted, trimmed, lower case
    assert _codes(rows, "boostavir") == ["J05ZZ52"]
    assert summary["combination_codes_left_out"] == []


def test_a_bridge_on_a_class_name_joins_the_class_to_an_ingredient_set_and_never_to_one_word(
    tmp_path,
):
    _, rows = _build(
        tmp_path,
        [
            ("invented antivirals", "dostavir;rivavir", "WHO classes the mix only by its class"),
            ("invented antivirals", "rivavir", "a single word on a class name"),
        ],
    )
    assert [(r["atc_code"], r["level"]) for r in rows if r["ingredient"] == "dostavir;rivavir"] == [
        ("J05ZZ", "4")
    ]
    assert _codes(rows, "rivavir") == []


def test_the_classes_of_the_group_words_are_written_and_one_who_lacks_is_refused(tmp_path):
    _, rows = _build(tmp_path, groups=[("invented group", "B01Z", "")])
    classes = {r["atc_code"] for r in rows if not r["ingredient"]}
    assert {"B", "B01", "B01Z"} <= classes and "invented group" not in {
        r["ingredient"] for r in rows
    }
    with pytest.raises(TableRefused, match="R03A"):
        _build(tmp_path, groups=[("invented group", "R03A", "")])


@pytest.mark.parametrize(
    "rows, match",
    [
        ([("insulin", "A", "")], "level 2 to 4"),
        ([("insulin", "A10AE04", "")], "level 2 to 4"),
        ([("insulin", "A10A", ""), ("insulin", "A10", "")], "twice"),
        ([(" ; ", "A10A", "")], "no substance"),
    ],
)
def test_group_classes_of_another_level_or_listed_twice_are_refused(tmp_path, rows, match):
    path = tmp_path / "groups.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows([("substance", "atc_code", "reason"), *rows])
    with pytest.raises(TableRefused, match=match):
        read_groups(path)


def test_rows_carry_the_rules_index_year_in_our_columns(built):
    summary, rows = built
    assert tuple(rows[0]) == COLUMNS
    assert {r["index_year"] for r in rows} == {str(YEAR)} and summary["index_year"] == YEAR


def test_an_index_of_another_year_is_refused(tmp_path):
    folder = write_index(tmp_path / "who", file_name=f"{YEAR + 1} ATC index with DDDs_english.xlsx")
    with pytest.raises(TableRefused, match=str(YEAR + 1)):
        build_table(folder, tmp_path / "classes.csv")


def test_bridges_with_other_columns_are_refused(tmp_path):
    path = tmp_path / "bridges.csv"
    path.write_text("from,to\nx,y\n", encoding="utf-8")
    with pytest.raises(TableRefused, match="columns"):
        read_bridges(path)


def test_a_bridge_keys_its_substance_as_the_rxnorm_step_does_and_one_with_none_is_refused(
    tmp_path,
):
    path = tmp_path / "bridges.csv"
    path.write_text('who_name,substance,evidence\nmix," b ; A ;",x\n', encoding="utf-8")
    assert read_bridges(path) == {"mix": [substance_key(" b ; A ;")]} == {"mix": ["a;b"]}
    path.write_text("who_name,substance,evidence\nmix,,x\n", encoding="utf-8")
    with pytest.raises(TableRefused, match="no substance"):
        read_bridges(path)


def test_the_command_reads_the_who_folder_setting(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPEN_ALTIO_WHO_DIR", str(write_index(tmp_path / "who")))
    out = tmp_path / "classes.csv"
    groups = {"mapping": str(_no_groups(tmp_path / "groups.csv"))}
    with rules_with(tmp_path, {"atc-group-classes": groups}):
        assert main(["atc-table", "--out", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == len(out.read_text().splitlines()) - 1
    monkeypatch.delenv("OPEN_ALTIO_WHO_DIR")
    assert main(["atc-table", "--out", str(out)]) == 2


# the table in mappings/, built from WHO's index -------------------------------------


def test_the_committed_table_is_whole_and_of_the_rules_year():
    with repo_path("atc-index", "table").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert tuple(rows[0]) == COLUMNS
    assert {r["index_year"] for r in rows} == {str(YEAR)}
    codes = {r["atc_code"] for r in rows if not r["ingredient"]}
    for r in rows:
        if r["ingredient"]:
            # a substance's code, or the class WHO gives a combination only by its class
            assert r["level"] == "5" or ";" in r["ingredient"], r
            assert {r["atc_code"][:n] for n in (1, 3, 4, 5) if n <= len(r["atc_code"])} <= codes
            assert r["ingredient"] == r["ingredient"].lower().strip()


def test_the_committed_table_holds_the_examples_the_rules_give():
    with repo_path("atc-index", "table").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert _codes(rows, "timolol") == ["C07AA06", "S01ED01"]
    assert _codes(rows, "sacubitril;valsartan") == ["C09DX04"]
    assert _codes(rows, "cyclosporine") == _codes(rows, "ciclosporin")
    assert _codes(rows, "levothyroxine") == _codes(rows, "levothyroxine sodium")
    for rule in rulebook.value("atc-class-choice", "dose_rules"):
        assert rule["code"] in _codes(rows, rule["substance"])


def test_every_group_class_is_a_class_the_committed_table_holds():
    with repo_path("atc-index", "table").open(encoding="utf-8", newline="") as fh:
        classes = {r["atc_code"] for r in csv.DictReader(fh) if not r["ingredient"]}
    assert set(read_groups().values()) <= classes


def test_every_bridge_names_a_word_WHO_uses():
    with repo_path("atc-index", "table").open(encoding="utf-8", newline="") as fh:
        names = {r["who_name"].lower() for r in csv.DictReader(fh)}
    for word in read_bridges():
        assert any(word == n or word in n for n in names), f"bridges.csv: WHO never writes {word!r}"
