"""The methods-page data a release carries (methods.json): its steps, counts and limits, and what
validate() refuses. The website's methods page draws only from this file."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from open_altio import rulebook
from open_altio.faers import ReleaseError, build_release
from open_altio.faers.funnel import FUNNEL_STEPS
from open_altio.faers.insights import methods as methods_module
from open_altio.faers.insights.cards.rule_charts import CARDS as RULE_CHARTS
from open_altio.faers.insights.methods import schema, validate
from open_altio.testing import fakefda

ROOT = Path(__file__).resolve().parents[3]
EM_DASH = "\u2014"


def _strings(value):
    """Every text of the document; the rules' values are data (a pattern, a dash in a label's
    table), not words, and are left out."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            if k != "rule_versions":
                yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def test_manifest_names_the_methods_file_and_it_is_there(rel):
    assert rel.manifest["methods"] == "methods.json"
    assert (rel.path / "methods.json").is_file()


def test_methods_json_is_valid_against_its_schema(methods):
    jsonschema.Draft202012Validator.check_schema(schema())
    errors = [e.message for e in jsonschema.Draft202012Validator(schema()).iter_errors(methods)]
    assert errors == []


def test_methods_json_is_for_this_release_and_code(rel, methods):
    assert methods["release"] == rel.manifest["release"] == fakefda.RELEASE
    assert methods["code"]["version"] == rel.manifest["code_version"]
    assert methods["changelog"]["release"] == fakefda.RELEASE
    assert methods["changelog"]["placeholder"] is True


def test_no_em_dashes_in_any_text(methods):
    assert [s for s in _strings(methods) if EM_DASH in s] == []


def test_funnel_matches_funnel_json(rel, methods):
    assert [s["id"] for s in methods["funnel"]["steps"]] == [s["id"] for s in rel.funnel["steps"]]
    for page, built in zip(methods["funnel"]["steps"], rel.funnel["steps"], strict=True):
        assert page["count"] == built["count"]
        assert page["label"] == built["label"]
    assert methods["funnel"]["deleted_lists"] == rel.funnel["deleted_lists"]
    assert methods["funnel"]["duplicates"] == rel.funnel["duplicates"]


def test_the_page_says_how_many_cases_the_duplicate_rule_cannot_check(rel, methods):
    dup = rel.funnel["duplicates"]
    limit = next(lim for lim in methods["limits"] if lim["id"] == "missing_fields_never_duplicates")
    share = 100.0 * dup["not_compared_by_aeolus"] / dup["cases"]
    said = f"{dup['not_compared_by_aeolus']:,} of {dup['cases']:,} cases ({share:.1f}%)"
    assert said in limit["text"]


def test_step_cards_quote_rule_values_never_their_placeholders(methods):
    card = next(s for s in methods["steps"] if s["id"] == "kept_after_duplicates")
    size = rulebook.value("dup-padded-event-dates", "min_group_size")
    gap = rulebook.value("dup-manufacturer-number", "max_age_gap_years")
    assert f"In a group of {size} or more cases" in card["rule"]
    assert f"differ by more than {gap}." in card["rule"]
    assert not [s for s in _strings(methods) if "{" in s or "}" in s]


def test_every_funnel_step_has_a_step_card_in_order(rel, methods):
    assert [s["id"] for s in methods["steps"]] == [s["id"] for s in rel.funnel["steps"]]
    for n, step in enumerate(methods["steps"], 1):
        assert step["number"] == n
        assert step["title"] and step["sentence"] and step["rule"]


def test_step_counts_are_the_funnel_counts(rel, methods):
    previous = None
    for step, built in zip(methods["steps"], rel.funnel["steps"], strict=True):
        assert step["after"] == built["count"]
        assert step["before"] == previous
        assert step["removed"] == built.get("removed")
        if previous is not None:
            assert {k: previous[k] - step["after"][k] for k in previous} == step["removed"]
        previous = built["count"]


def test_step_sentence_is_one_plain_sentence(methods):
    for step in methods["steps"]:
        text = step["sentence"].strip()
        assert text.endswith(".") and text.count(". ") == 0, step["id"]


def test_step_code_links_point_at_the_line_holding_the_step_on_github(methods):
    cards = methods_module.step_cards()
    for step in methods["steps"]:
        code = step["code"]
        lines = (ROOT / code["path"]).read_text(encoding="utf-8").splitlines()
        assert cards[step["id"]]["code"]["anchor"] in lines[code["line"] - 1], step["id"]
        assert code["url"] == (
            f"https://github.com/Altio-AI/open-altio/blob/{methods['code']['ref']}"
            f"/{code['path']}#L{code['line']}"
        )


def test_every_step_that_removes_cases_has_a_finding_behind_it(methods):
    """Each step that removes cases links to a card saying why ("Why this step"); the first step
    removes nothing, and its cards are the evidence for how its rows are read (rule not-given)."""
    assert all(step["insights"] for step in methods["steps"] if step["removed"] is not None)
    first = next(s for s in methods["steps"] if s["removed"] is None)
    rule_charts = {fn.__name__ for fn in RULE_CHARTS}
    for card in (c for c in methods["insights"] if c["id"] in first["insights"]):
        if card["id"] not in rule_charts:  # a rule chart is the chart of its own rule
            assert "not-given" in card["tag"]["rules"], card["id"]


def test_limits_say_what_we_do_not_do(methods):
    titles = " ".join(lim["title"] for lim in methods["limits"]).lower()
    for phrase in ("meddra", "missing fields"):
        assert phrase in titles


def test_limits_say_our_drug_counts_take_fewer_roles_and_combinations_count_under_each(methods):
    limits = {lim["id"]: lim["text"] for lim in methods["limits"]}
    assert "every role" in limits["fewer_roles_than_diana"]
    assert {"valsartan", "Entresto", "label"} <= set(
        limits["combinations_counted_under_each_ingredient"].replace(",", " ").split()
    )


def _insight(doc: dict, card_id: str) -> dict:
    return next(c for c in doc["insights"] if c["id"] == card_id)


def test_validate_refuses_a_card_naming_a_rule_with_no_file(methods):
    doc = json.loads(json.dumps(methods))
    _insight(doc, "deleted_lists_unpublished")["tag"]["rules"] = ["no-such-rule"]
    said = "is evidence for rule 'no-such-rule', which has no rule file"
    assert f"insight deleted_lists_unpublished {said}" in validate(doc)


def test_validate_refuses_a_step_that_removes_cases_with_no_card(methods):
    doc = json.loads(json.dumps(methods))
    step = next(s for s in doc["steps"] if s["id"] == "latest_versions")
    doc["insights"] = [c for c in doc["insights"] if c["id"] not in step["insights"]]
    step["insights"] = []
    assert "step latest_versions removes cases but no insight card says why" in validate(doc)


def test_validate_refuses_a_chart_note_off_its_axis(methods):
    doc = json.loads(json.dumps(methods))
    _insight(doc, "eras_write_countries_and_terms_differently")["chart"]["note"]["x"] = "1999Q1"
    assert any("not on its x axis" in p for p in validate(doc))
    assert validate(methods) == []


def test_build_fails_when_a_funnel_step_has_no_step_card(fake_input, tmp_path, monkeypatch):
    original = methods_module.step_cards()
    trimmed = tmp_path / "steps.yaml"
    last = [s for s in FUNNEL_STEPS if "needs" not in s][-1]["id"]  # a step every release has
    trimmed.write_text(yaml.safe_dump({k: v for k, v in original.items() if k != last}))
    monkeypatch.setattr(methods_module, "STEPS_FILE", trimmed)
    with pytest.raises(ReleaseError, match=last):
        build_release(fake_input, tmp_path / "out")
    assert not (tmp_path / "out" / fakefda.RELEASE).exists()
