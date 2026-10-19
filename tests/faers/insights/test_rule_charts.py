"""Every rule has a chart: the cards' `rules` (insights/cards RULES_OF), the rule charts' numbers
counted a second way (rule_chart_checks.py), the methods command against a full build, the
licensed cards kept out of the public methods.json, and the opened lines read at serve time."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from rule_chart_checks import independent

from open_altio import rulebook
from open_altio.faers.__main__ import main
from open_altio.faers.insights.cards import LICENSED, RULES_OF, card_ids, rule_charts
from open_altio.faers.insights.methods import CODE_REF_ENV, LINES_FILE, card_lines, refresh_cards
from open_altio.rulebook import catalogue
from open_altio.testing import fakediana

NEW = [fn.__name__ for fn in rule_charts.CARDS]
PUBLIC = [i for i in NEW if i not in LICENSED]  # a licensed card is in the licensed part


def _methods(folder: Path) -> dict:
    return json.loads((folder / "methods.json").read_text(encoding="utf-8"))


def test_every_rule_on_the_page_has_a_card():
    served = {name for rules in RULES_OF.values() for name in rules}
    page = [info.name for info in catalogue()]
    assert len(page) == 54
    assert [name for name in page if name not in served] == []


def test_every_card_named_for_a_rule_exists_and_every_rule_named_has_a_file():
    assert set(RULES_OF) - set(card_ids()) == set()
    assert {n for rules in RULES_OF.values() for n in rules} - set(rulebook.rule_names()) == set()


def test_the_built_methods_page_gives_each_card_its_rules_and_no_licensed_card(release):
    doc = _methods(release)
    assert all(
        card["rules"] == RULES_OF.get(card["id"], card["tag"].get("rules", []))
        for card in doc["insights"]
    )
    assert not {card["id"] for card in doc["insights"]} & LICENSED
    assert set(PUBLIC) <= {card["id"] for card in doc["insights"]}


def test_the_methods_command_writes_what_a_full_build_wrote(release, fake_diana, tmp_path):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    before = _methods(copy)
    (copy / "methods.json").write_text(json.dumps({**before, "insights": []}), encoding="utf-8")
    with fakediana.pinned(fake_diana, tmp_path / "rules"):  # the rules it was built with
        assert main(["methods", "--release", str(copy)]) == 0
    assert _methods(copy) == before


def test_the_methods_command_points_the_code_links_at_the_ref_it_is_given(
    release, fake_diana, tmp_path, monkeypatch
):
    copy = tmp_path / release.name
    shutil.copytree(release, copy)
    monkeypatch.setenv(CODE_REF_ENV, "v9.9.9")
    with fakediana.pinned(fake_diana, tmp_path / "rules"):
        assert main(["methods", "--release", str(copy)]) == 0
    built, refreshed = _methods(release), _methods(copy)
    assert built["code"]["ref"] != "v9.9.9"
    assert refreshed["code"] == built["code"] | {"ref": "v9.9.9"}
    for before, after in zip(built["steps"], refreshed["steps"], strict=True):
        assert after["code"] == before["code"] | {
            "url": before["code"]["url"].replace(f"/blob/{built['code']['ref']}/", "/blob/v9.9.9/")
        }


@pytest.fixture(
    scope="module", params=["release", "classes_release", "labelled_release", "stats_release"]
)
def refreshed(request, tmp_path_factory) -> Path:
    copy = tmp_path_factory.mktemp("rule_charts") / "release"
    shutil.copytree(request.getfixturevalue(request.param), copy)
    refresh_cards(copy)
    return copy


def test_each_new_card_counts_what_a_second_query_counts(refreshed):
    cards = {c["id"]: c for c in _methods(refreshed)["insights"]}
    checks = independent(refreshed)
    assert set(checks) <= set(PUBLIC)
    for card_id, numbers in checks.items():
        got = {k: cards[card_id]["numbers"][k] for k in numbers}
        assert got == numbers, card_id


def test_the_fake_release_gives_the_rule_charts_data(refreshed):
    cards = {c["id"]: c for c in _methods(refreshed)["insights"]}
    checks = independent(refreshed)
    assert checks["cases_by_age_band"]["cases"] > 0
    assert cards["cases_by_age_band"]["chart"]["series"][0]["values"]
    assert (
        sum(cards["cases_by_age_band"]["chart"]["series"][0]["values"])
        == checks["cases_by_age_band"]["cases"]
    )


def test_a_licensed_card_goes_to_the_licensed_part(licensed_release, tmp_path):
    copy = tmp_path / licensed_release.name
    shutil.copytree(licensed_release, copy)
    refresh_cards(copy)
    licensed = json.loads((copy / "licensed" / "manifest.json").read_text(encoding="utf-8"))
    (version,) = licensed["meddra"]["versions"].values()
    assert {c["id"] for c in version["insights"]} == LICENSED
    assert not {c["id"] for c in _methods(copy)["insights"]} & LICENSED


def test_every_new_card_has_its_opened_lines_filled_from_its_numbers(release):
    words = yaml.safe_load(LINES_FILE.read_text(encoding="utf-8"))
    assert set(NEW) <= set(words)
    for card in _methods(release)["insights"]:
        if card["id"] in PUBLIC:
            lines = card_lines(card)
            assert lines and set(lines) == {"shows", "matters", "did"}, card["id"]
            assert "{" not in "".join(lines.values()), card["id"]


def test_the_lines_are_read_now_not_from_the_release(monkeypatch, tmp_path):
    words = tmp_path / "lines.yaml"
    words.write_text("x:\n  shows: '{n:,} reworded'\n", encoding="utf-8")
    monkeypatch.setattr("open_altio.faers.insights.methods.LINES_FILE", words)
    assert card_lines({"id": "x", "numbers": {"n": 1200}}) == {"shows": "1,200 reworded"}


def _cut_set_aside(folder: Path) -> int:
    """Take every set-aside case, and every record keyed by its case, out of the release's
    Parquet files. Returns how many cases went."""
    import duckdb

    con = duckdb.connect()
    key = ["era_T", "primaryid", "quarter_T"]
    tables = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["tables"]
    files = [folder / entry["path"] for entry in tables.values()]
    cases = folder / tables["case_latest_T"]["path"]
    con.execute(
        f"CREATE TABLE aside AS SELECT {', '.join(key)} FROM read_parquet('{cases}') "
        "WHERE NOT dup_kept_T"
    )
    for file in files:
        cols = {c for (c, *_) in con.execute(f"DESCRIBE FROM read_parquet('{file}')").fetchall()}
        if set(key) <= cols:
            cut = file.with_name("cut.parquet")
            con.execute(
                f"COPY (FROM read_parquet('{file}') ANTI JOIN aside USING ({', '.join(key)})) "
                f"TO '{cut}' (FORMAT parquet)"
            )
            cut.replace(file)
    return con.execute("SELECT count(*) FROM aside").fetchone()[0]


@pytest.mark.parametrize("built", ["release", "classes_release", "labelled_release"])
def test_a_set_aside_duplicate_is_counted_by_no_new_card_and_no_check(built, request, tmp_path):
    kept, without = tmp_path / "kept", tmp_path / "without"
    shutil.copytree(request.getfixturevalue(built), kept)
    shutil.copytree(kept, without)
    assert _cut_set_aside(without) > 0  # the fake release holds set-aside cases to miscount
    refresh_cards(kept)
    refresh_cards(without)
    shown = {c["id"]: c for c in _methods(kept)["insights"]}
    cut = {c["id"]: c for c in _methods(without)["insights"]}
    seen = {i: (shown[i]["numbers"], shown[i]["chart"]) for i in PUBLIC}
    assert [i for i in PUBLIC if seen[i] != (cut[i]["numbers"], cut[i]["chart"])] == []
    assert independent(kept) == independent(without)
