"""How the label dictionary finds MedDRA names in label text (rule label-dictionary).

Terms are the invented ones of open_altio.testing.fakemeddra, or made up here."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.faers.labeldict.terms import Headings, Term, TermIndex, plural
from open_altio.faers.labeldict.text import TextReader
from open_altio.testing.fakemeddra import current_llts


@pytest.fixture(scope="module")
def reader() -> TextReader:
    return TextReader.from_rules()


@pytest.fixture(scope="module")
def index(reader) -> TermIndex:
    return TermIndex.from_rules([Term(*t) for t in current_llts("29.1")], reader)


def found(index, reader, text: str) -> list[tuple[str, str]]:
    words = reader.words(text)
    return [
        (text[words[h.first].start : words[h.last - 1].end], h.term.pt_name)
        for h in index.hits(words)
    ]


def test_longest_name_wins_and_matching_resumes_after_it(index, reader):
    assert found(index, reader, "Acute renal failure occurred.") == [
        ("Acute renal failure", "Renal failure acute")
    ]
    assert found(index, reader, "Renal failure occurred.") == [("Renal failure", "Renal failure")]


def test_a_synonym_llt_gives_its_pt(index, reader):
    assert found(index, reader, "Kidney failure and head pain were seen.") == [
        ("Kidney failure", "Renal failure"),
        ("head pain", "Headache"),
    ]


def test_a_non_current_llt_is_never_matched(index, reader):
    assert found(index, reader, "Sickness was reported.") == []


def test_case_is_ignored_but_a_capitals_name_matches_only_capitals(index, reader):
    assert found(index, reader, "HEADACHE and Nausea") == [
        ("HEADACHE", "Headache"),
        ("Nausea", "Nausea"),
    ]
    assert found(index, reader, "ARF was seen.") == [("ARF", "Renal failure acute")]
    assert found(index, reader, "Arf was seen.") == []
    assert rulebook.value("label-dictionary", "capitals_match_capitals") is True


def test_a_hyphen_keeps_one_word_so_no_name_is_read_inside_it(index, reader):
    assert found(index, reader, "extra-renal failure") == []
    assert found(index, reader, "post-headache nausea") == [("nausea", "Nausea")]


def test_british_and_us_spellings_meet(index, reader):
    assert found(index, reader, "Hemorrhage and haemorrhage") == [
        ("Hemorrhage", "Haemorrhage"),
        ("haemorrhage", "Haemorrhage"),
    ]


def test_accents_are_ignored_and_the_match_is_shown_as_written(index, reader):
    assert found(index, reader, "Headaché") == [("Headaché", "Headache")]


def test_a_plural_last_word_matches(index, reader):
    assert found(index, reader, "Head pains and haemorrhages") == [
        ("Head pains", "Headache"),
        ("haemorrhages", "Haemorrhage"),
    ]
    assert plural("rash") == "rashes" and plural("allergy") == "allergies"


def test_a_lab_result_matches_in_prose_order(index, reader):
    first = rulebook.value("label-dictionary", "prose_order")["increased"][1]
    assert found(index, reader, f"{first.capitalize()} hepatic enzymes were seen.") == [
        (f"{first.capitalize()} hepatic enzymes", "Hepatic enzyme increased")
    ]
    assert found(index, reader, "Increased hepatic enzyme") == [
        ("Increased hepatic enzyme", "Hepatic enzyme increased")
    ]


def test_a_lab_change_written_as_a_phrase_first_matches_too(index, reader):
    phrases = rulebook.value("label-dictionary", "prose_order")["increased"]
    assert "increase in" in phrases and "elevation of" in phrases
    assert found(index, reader, "An increase in hepatic enzymes was seen.") == [
        ("increase in hepatic enzymes", "Hepatic enzyme increased")
    ]
    assert found(index, reader, "Elevation of hepatic enzyme.") == [
        ("Elevation of hepatic enzyme", "Hepatic enzyme increased")
    ]
    # the phrase alone, or before another word, names nothing
    assert found(index, reader, "An increase in dose was needed.") == []


def test_a_name_as_written_wins_over_another_names_other_form(reader):
    terms = [
        Term("97000001", "Pain increased", "97000001", "Pain increased"),
        Term("97000002", "Increased pain", "97000003", "Hyperalgesia"),
        Term("97000003", "Hyperalgesia", "97000003", "Hyperalgesia"),
    ]
    index = TermIndex.from_rules(terms, reader)
    assert found(index, reader, "increased pain") == [("increased pain", "Hyperalgesia")]


def test_two_llts_with_the_same_words_give_the_pts_own_llt(reader):
    terms = [
        Term("97000005", "Blood loss", "97000009", "Haemorrhage"),
        Term("97000009", "Blood Loss", "97000009", "Blood loss"),
    ]
    index = TermIndex.from_rules(terms, reader)
    assert found(index, reader, "blood loss") == [("blood loss", "Blood loss")]


def test_a_match_never_crosses_a_mark(index, reader):
    assert found(index, reader, "acute, renal failure") == [("renal failure", "Renal failure")]


def test_body_system_names_are_found_singular_or_plural(reader):
    heads = Headings(["Invented swellings and lumps"], reader)
    words = reader.words("under invented swellings and lump except")
    assert heads.spans(words) == [(1, 5)]


def test_sentences_end_at_a_full_stop_but_not_after_an_abbreviation(reader):
    text = "Nausea, e.g. mild, occurred. Vomiting was seen; rarely."
    assert reader.sentences(text) == [
        "Nausea, e.g. mild, occurred.",
        "Vomiting was seen;",
        "rarely.",
    ]
