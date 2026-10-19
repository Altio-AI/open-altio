"""Matching a substance to its RxNorm code (rule rxnorm-ingredients), on an
invented release and the reviewed name pairs in mappings/."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.faers.rxnorm.match import (
    BARE_ELEMENT,
    DIFFERENT_PARENT,
    NO_NAME,
    NO_PRODUCT,
    NONE,
    PARTS_ONLY,
    Match,
    Matcher,
    PairsRefused,
    read_keeps,
    read_pairs,
    read_prod_ai_pairs,
    substance_key,
)
from open_altio.faers.rxnorm.rrf import read_rxnorm
from open_altio.testing.fakerxnorm import CODES, write_rxnorm
from open_altio.testing.rules import rules_with

NO_CODE = Match(None, None, None, NONE, NO_NAME)
OTHER_PARENT = Match(None, None, None, NONE, DIFFERENT_PARENT)
ELEMENT_ONLY = Match(None, None, None, NONE, BARE_ELEMENT)


def coded(name: str, matched_by: str) -> Match:
    rxcui, tty = CODES[name]
    return Match(rxcui, name, tty, matched_by)


@pytest.fixture
def rx(tmp_path):
    return read_rxnorm(write_rxnorm(tmp_path / "rxnorm"))


@pytest.fixture
def matcher(rx):
    return Matcher(rx)


def test_an_ingredient_name_takes_its_own_code(matcher):
    assert matcher.match("zorbatide") == coded("zorbatide", "ingredient")


def test_a_salt_takes_its_ingredients_code(matcher):
    assert matcher.match("zorbatide sodium") == coded("zorbatide", "salt")


def test_a_brand_takes_its_ingredient_or_its_ingredient_set(matcher):
    assert matcher.match("glimmerex") == coded("zorbatide", "brand")
    assert matcher.match("duotrel") == coded("quintelamab / veltrozine", "brand")


def test_a_combination_takes_the_code_of_exactly_its_ingredient_set(matcher):
    expected = coded("quintelamab / veltrozine", "ingredient_set")
    assert matcher.match("quintelamab;veltrozine") == expected
    assert matcher.match("veltrozine; Quintelamab") == expected
    assert matcher.match("veltrozine;zorbatide sodium") == coded(
        "veltrozine / zorbatide sodium", "ingredient_set"
    )


def test_a_reviewed_name_pair_finds_rxnorms_name(matcher):
    assert read_pairs()["paracetamol"] == "acetaminophen"
    assert matcher.match("paracetamol") == coded("acetaminophen", "name_pair")


def test_a_combination_is_as_strong_as_its_weakest_name(matcher):
    assert matcher.match("dronecodone;paracetamol") == coded(
        "acetaminophen / dronecodone", "name_pair"
    )


def test_the_acid_ending_and_the_ignored_characters_spell_one_name(matcher):
    assert matcher.match("plorinic acid") == coded("plorinate", "spelling")
    assert matcher.match("alpha-1-sorbase") == coded("alpha 1-sorbase", "spelling")


def test_the_spelling_rule_is_read_from_the_rule(rx, tmp_path):
    with rules_with(tmp_path, {"rxnorm-ingredients": {"acid_endings": {}}}):
        assert Matcher(rx).match("plorinic acid") == NO_CODE


def test_refuses_a_near_miss(matcher):
    assert matcher.match("osmedrostat") == NO_CODE
    assert matcher.match("zorbatid") == NO_CODE


def test_refuses_a_spelling_two_ingredients_share(matcher):
    assert matcher.match("vexamine") == coded("vexamine", "ingredient")
    assert matcher.match("vex amine") == NO_CODE


def test_a_combination_no_product_has_keeps_no_code_of_its_own(matcher):
    assert matcher.match("acetaminophen;zorbatide") == Match(
        None, None, None, PARTS_ONLY, NO_PRODUCT
    )


def test_a_combination_with_a_part_rxnorm_lacks_has_no_code(matcher):
    assert matcher.match("unknownium;zorbatide") == NO_CODE
    assert matcher.match("zorbatide old") == NO_CODE
    assert matcher.match(";") == NO_CODE


def test_a_salt_acid_or_suffixed_form_keeps_its_ingredients_code(matcher):
    assert matcher.match("kelodric acid") == coded("kelodrate", "salt")
    assert matcher.match("olvidase alfa-xqzt") == coded("olvidase alfa", "salt")


def test_a_drug_rxnorm_files_under_a_different_parent_has_no_code(matcher):
    assert matcher.match("trelumab vexotecan") == OTHER_PARENT
    assert matcher.match("fosnetazine") == OTHER_PARENT
    assert matcher.match("fosnetazine;quintelamab") == OTHER_PARENT
    assert matcher.match("trelumab") == coded("trelumab", "ingredient")


def test_a_reviewed_name_keeps_its_parents_code_and_an_unlisted_conjugate_does_not(rx, matcher):
    assert matcher.match("enfortumab vedotin") == coded("enfortumab", "salt")
    assert matcher.match("trastuzumab deruxtecan") == OTHER_PARENT
    assert Matcher(rx, keeps=set()).match("enfortumab vedotin") == OTHER_PARENT


def test_a_drug_named_differently_from_its_parent_keeps_the_code_when_listed(rx, matcher):
    assert {"divalproex sodium", "glycopyrrolate", "ursodiol"} <= read_keeps()
    assert matcher.match("divalproex sodium") == coded("valproate", "salt")
    assert matcher.drug_name("DEPAKOTE") == coded("valproate", "brand")
    assert Matcher(rx, keeps=set()).drug_name("DEPAKOTE") == OTHER_PARENT


def test_fdas_active_ingredient_is_matched_exactly_whole_or_by_its_parts(matcher):
    assert matcher.prod_ai("POTASSIUM CHLORIDE") == coded("potassium chloride", "ingredient")
    assert matcher.prod_ai("ZORBATIDE SODIUM") == coded("zorbatide", "salt")
    assert matcher.prod_ai("VELTROZINE\\QUINTELAMAB") == coded(
        "quintelamab / veltrozine", "ingredient_set"
    )


def test_fdas_active_ingredient_takes_no_pair_no_spelling_and_no_near_set(matcher):
    assert matcher.prod_ai("PARACETAMOL") == NO_CODE
    assert matcher.prod_ai("PLORINIC ACID") == NO_CODE
    assert matcher.prod_ai("ZORBATIDE\\UNKNOWNIUM") == NO_CODE
    assert matcher.prod_ai("ACETAMINOPHEN\\ZORBATIDE") == Match(
        None, None, None, PARTS_ONLY, NO_PRODUCT
    )
    assert matcher.prod_ai("TRELUMAB VEXOTECAN") == OTHER_PARENT
    assert matcher.prod_ai("\\") == NO_CODE


def test_fdas_dextrose_is_rxnorms_glucose_through_the_reviewed_list(matcher):
    assert read_prod_ai_pairs()["dextrose"] == "glucose"
    assert matcher.prod_ai("DEXTROSE") == coded("glucose", "name_pair")
    assert matcher.prod_ai("SODIUM CHLORIDE\\DEXTROSE") == coded(
        "glucose / sodium chloride", "name_pair"
    )


def test_fdas_list_reaches_only_fdas_active_ingredient(rx, matcher):
    assert matcher.drug_name("DEXTROSE") == NO_CODE
    assert matcher.match("dextrose") == NO_CODE
    assert Matcher(rx, prod_ai_pairs={}).prod_ai("DEXTROSE") == NO_CODE
    unused = Matcher(rx, prod_ai_pairs={"fooose": "barose"})
    assert unused.prod_ai("FOOOSE") == NO_CODE and "fooose" in unused.unused_pairs


def test_fdas_list_needs_its_columns(tmp_path):
    bad = tmp_path / "prod_ai_pairs.csv"
    bad.write_text("fda_name,rxnorm_name\ndextrose,glucose\n", encoding="utf-8")
    with pytest.raises(PairsRefused, match="columns"):
        read_prod_ai_pairs(bad)


def test_an_element_alone_from_the_dictionary_has_no_code(matcher):
    assert "potassium" in rulebook.value("rxnorm-ingredients", "bare_elements")
    assert matcher.match("potassium") == ELEMENT_ONLY
    assert matcher.match("potassium;zorbatide") == ELEMENT_ONLY
    assert matcher.match("potassium chloride") == coded("potassium chloride", "ingredient")


def test_fda_naming_the_element_itself_keeps_its_code(matcher):
    assert matcher.drug_name("POTASSIUM") == coded("potassium", "ingredient")
    assert matcher.prod_ai("POTASSIUM") == coded("potassium", "ingredient")


def test_the_bare_elements_are_read_from_the_rule(rx, tmp_path):
    with rules_with(tmp_path, {"rxnorm-ingredients": {"bare_elements": []}}):
        assert Matcher(rx).match("potassium") == coded("potassium", "ingredient")


def test_the_keeps_list_has_a_reason_for_every_name(tmp_path):
    assert "enfortumab vedotin" in read_keeps()
    bad = tmp_path / "keeps.csv"
    bad.write_text("rxnorm_name\nenfortumab vedotin\n", encoding="utf-8")
    with pytest.raises(PairsRefused, match="columns"):
        read_keeps(bad)


def test_a_drug_name_is_matched_only_as_it_is(matcher):
    assert matcher.drug_name(" GLIMMEREX ") == coded("zorbatide", "brand")
    assert matcher.drug_name("Duotrel") == coded("quintelamab / veltrozine", "brand")
    assert matcher.drug_name("paracetamol") == NO_CODE  # a name pair is for ingredients only
    assert matcher.drug_name("plorinic acid") == NO_CODE  # and so is the spelling rule


def test_a_brand_takes_no_code_when_it_sells_a_drug_filed_under_another(matcher):
    assert matcher.drug_name("enhertu") == OTHER_PARENT
    assert matcher.drug_name("padcev") == coded("enfortumab", "brand")


def test_salt_and_ester_words_are_dropped_by_list_and_by_ending(matcher):
    assert matcher.bare("fluticasone furoate") == matcher.bare("fluticasone")
    assert matcher.bare("penicillin g benzathine") == matcher.bare("penicillin g")
    assert matcher.bare("trastuzumab deruxtecan") != matcher.bare("trastuzumab")


def test_the_form_words_are_read_from_the_rule(rx, tmp_path):
    with rules_with(tmp_path, {"rxnorm-ingredients": {"form_words": []}}):
        assert Matcher(rx).match("zorbatide sodium") == OTHER_PARENT


def test_a_pair_whose_rxnorm_name_the_release_lacks_codes_nothing(rx):
    matcher = Matcher(rx, pairs={"zorbatidum": "zorbatide", "fooine": "barine"})
    assert matcher.match("zorbatidum") == coded("zorbatide", "name_pair")
    assert matcher.match("fooine") == NO_CODE
    assert matcher.unused_pairs == ["fooine"]


def test_substance_key_writes_the_drug_names_steps_form():
    assert substance_key(" Valsartan ;sacubitril") == "sacubitril;valsartan"
    assert substance_key("b;a;b;") == "a;b"
    assert substance_key(" ; ") is None


def test_the_name_pairs_have_their_evidence_and_one_rxnorm_name_each(tmp_path):
    pairs = read_pairs()
    assert pairs and all(name != rxnorm for name, rxnorm in pairs.items())
    bad = tmp_path / "pairs.csv"
    bad.write_text("dictionary_name,rxnorm_name,evidence\na,b,why\na,c,why\n", encoding="utf-8")
    with pytest.raises(PairsRefused, match="two RxNorm names"):
        read_pairs(bad)
    bad.write_text("name,rxnorm\na,b\n", encoding="utf-8")
    with pytest.raises(PairsRefused, match="columns"):
        read_pairs(bad)
