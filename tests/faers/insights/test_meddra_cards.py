"""The methods page's MedDRA cards (src/open_altio/faers/insights/cards/meddra.py), computed by
the release build when it is given MedDRA, and plain about it without."""

from __future__ import annotations

import json

import pytest

from open_altio.faers import build_release
from open_altio.faers.meddra import COLUMNS
from open_altio.testing import fakediana
from open_altio.testing.fakemeddra import write_meddra
from open_altio.testing.releasereader import ReleaseReader

CHANGED = {
    "older_meddra_terms_missed": ["meddra-terms"],
    "quarterly_files_keep_their_meddra_version": ["meddra-version", "meddra-terms"],
}
DOCUMENTED = ["unknown_indication_placeholder"]


@pytest.fixture(scope="module")
def with_meddra(fake_input, fake_diana, tmp_path_factory) -> ReleaseReader:
    out = tmp_path_factory.mktemp("with_meddra")
    meddra = write_meddra(tmp_path_factory.mktemp("meddra") / "29.1", "29.1")
    with fakediana.pinned(fake_diana, out):
        built = build_release(fake_input, out, diana_dictionary=fake_diana, meddra_dir=meddra)
    return ReleaseReader(built)


def _methods(rel):
    return json.loads((rel.path / rel.manifest["methods"]).read_text(encoding="utf-8"))


def _card(methods, card_id):
    return next(c for c in methods["insights"] if c["id"] == card_id)


def _licensed(rel) -> dict:
    """The licensed part's cards: those that need MedDRA's files never reach the public page."""
    licensed = json.loads((rel.path / "licensed" / "manifest.json").read_text())
    return {"insights": licensed["meddra"]["versions"]["29.1"]["insights"]}


def test_with_meddra_the_funnel_has_a_step_that_removes_no_case_and_its_cards(with_meddra):
    step = with_meddra.step("meddra_terms")
    assert step["removed"] == {"legacy": 0, "faers": 0, "total": 0}
    methods = _methods(with_meddra)
    linked = next(s for s in methods["steps"] if s["id"] == "meddra_terms")["insights"]
    assert linked == []  # its cards need MedDRA's files: they are in the licensed part
    assert not {c["id"] for c in methods["insights"]} & set(CHANGED)
    licensed = _licensed(with_meddra)
    for card_id, rules in CHANGED.items():
        tag = _card(licensed, card_id)["tag"]
        assert (tag["kind"], tag["step"], tag["rules"]) == (
            "changed_pipeline",
            "meddra_terms",
            rules,
        )
    for card_id in DOCUMENTED:
        assert _card(methods, card_id)["tag"]["kind"] == "documented"
    for card_id in [*CHANGED, *DOCUMENTED]:
        card = _card(licensed if card_id in CHANGED else methods, card_id)
        assert card["chart"]["question"].endswith("?")
        assert card["notebook"].endswith("06_meddra_versions.ipynb")


def test_the_older_terms_card_counts_the_cases_a_search_on_todays_term_misses(with_meddra):
    licensed = json.loads((with_meddra.path / "licensed" / "manifest.json").read_text())
    entry = licensed["meddra"]["versions"]["29.1"]["tables"][COLUMNS["pt"].table]
    table = with_meddra.path / "licensed" / entry["path"]
    [(cases, older)] = with_meddra.rows(f"""
        SELECT count(DISTINCT c.case_key_T),
               count(DISTINCT c.case_key_T) FILTER (WHERE NOT m.pt_current_T)
        FROM reac_latest_T r JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
        JOIN read_parquet('{table}') m ON m.reac_term_T = lower(r.pt)
        WHERE c.dup_kept_T""")
    card = _card(_licensed(with_meddra), "older_meddra_terms_missed")
    assert older > 0
    assert card["title"].startswith(f"{100.0 * older / cases:.1f}% of cases")
    assert f"so {older:,} case" in card["two_sentences"]
    # the chart names PTs only: Arrhythmia is now a lower level term of Heart rhythm abnormal
    assert "Heart rhythm abnormal" in card["chart"]["x"]["values"]
    assert "Arrhythmia" not in card["chart"]["x"]["values"]


def test_without_meddra_the_cards_say_so_show_no_data_and_change_nothing(rel, methods):
    assert "meddra_terms" not in [s["id"] for s in rel.funnel["steps"]]
    assert not {c["id"] for c in methods["insights"]} & set(CHANGED)  # licensed, never public
    for card_id in DOCUMENTED:
        card = _card(methods, card_id)
        assert card["tag"]["kind"] == "documented"
        assert "without a MedDRA release" in card["two_sentences"]
        assert card["chart"]["series"] == []
