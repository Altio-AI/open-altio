"""The methods page is on a US website, so every text the release writes into
methods.json uses American spelling. Data values FDA published (reaction
terms, sender names) are not our text and are not checked."""

import json
import re

BRITISH = [
    r"\bstandardis",
    r"\bnormalis",
    r"\borganis",
    r"\bharmonis",
    r"\brecognis",
    r"\bsummaris",
    r"\banalys(e|ed|es|ing)\b",
    r"\bcolour",
    r"\bbehaviour",
    r"\bfavour",
    r"\bcentre",
    r"\bprogramme",
    r"\bcatalogue",
    r"\bfull stops?\b",
    r"\bless (cases|probable|reports|duplicates)\b",
    r"\bhaemorrhag",
    r"\boedema",
    r"\bdiarrhoea",
    r"\blabelled",
    r"\bmodelled",
    r"\btravelled",
]

# Keys whose strings are data or identifiers, not our prose.
NOT_PROSE = {
    "id",
    "step",
    "kind",
    "table",
    "values",
    "notebook",
    "code",
    "path",
    "url",
    "release",
    "ref",
    "repository",
    "version",
    "unit",
    "citation",  # a source cited as its owner writes it: WHO's Collaborating Centre
}


def prose(value, key=""):
    if isinstance(value, str):
        if key not in NOT_PROSE:
            yield key, value
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in ("series", "rule_versions"):  # FDA's values and the rules' values, not words
                continue
            yield from prose(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from prose(v, key)


def test_methods_json_has_no_common_british_spellings(release):
    methods = json.loads((release / "methods.json").read_text())
    found = [
        (key, text, pattern)
        for key, text in prose(methods)
        for pattern in BRITISH
        if re.search(pattern, text, re.IGNORECASE)
    ]
    assert not found, found


def test_the_funnel_says_fewer_not_less(release):
    labels = [
        s["label"] for s in json.loads((release / "methods.json").read_text())["funnel"]["steps"]
    ]
    assert any(label.startswith("Fewer cases") for label in labels)
    assert not any(label.lower().startswith("less ") for label in labels)
