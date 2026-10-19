"""How a WHO class name reads on a screen (classnames.py), and that files keep WHO's text."""

from __future__ import annotations

import pytest

from open_altio.explorer.classnames import abbreviations_in, shown

WHO_NORMAL = [
    "ACE inhibitors, plain",
    "HMG CoA reductase inhibitors",
    "Monoamine oxidase type B inhibitors (MAO-B)",
    "Platelet aggregation inhibitors excl. heparin",
]
ABBR = abbreviations_in(WHO_NORMAL + ["BETA BLOCKING AGENTS"])


def test_the_abbreviations_come_from_the_normally_written_names_only():
    assert {"ACE", "HMG", "MAO"} == ABBR


@pytest.mark.parametrize(
    ("who", "screen"),
    [
        ("CARDIOVASCULAR SYSTEM", "Cardiovascular system"),
        ("ACE INHIBITORS, PLAIN", "ACE inhibitors, plain"),
        ("HMG COA REDUCTASE INHIBITORS", "HMG coa reductase inhibitors"),
        (
            "ANTIINFLAMMATORY AND ANTIRHEUMATIC PRODUCTS",
            "Antiinflammatory and antirheumatic products",
        ),
        ("ACE inhibitors, plain", "ACE inhibitors, plain"),
        ("ibuprofen", "ibuprofen"),
        ("", ""),
        (None, None),
    ],
)
def test_an_all_capitals_name_reads_in_sentence_case_and_any_other_is_unchanged(who, screen):
    assert shown(who, ABBR) == screen
