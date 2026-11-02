"""What the filters on a case's drug records and its report choose (filters.py reads them,
recordfilters.py turns them into SQL): each parameter with its field in Filters and its words,
FDA's dechallenge, rechallenge and report type codes in words, and the onset ranges, `2-7`, both
ends included, either end open (`91-`), named by rule breakdown-lines' onset bands.
"""

from __future__ import annotations

import re

from open_altio.rulebook import value

# the filters on a case's drug records and its report (recordfilters.py): each parameter, its
# field in Filters and the words a page and a manifest name it by
RECORD_FIELDS = {
    "dose": ("doses", "Dose"),
    "route": ("routes", "Route"),
    "dose_form": ("dose_forms", "Dose form"),
    "lot": ("lots", "Lot"),
    "indication": ("indications", "Taken for"),
    "onset": ("onsets", "Time to onset"),
    "dechal": ("dechals", "Dechallenge"),
    "rechal": ("rechals", "Rechallenge"),
    "other_drug": ("other_drugs", "Other drugs"),
    "report_type": ("report_types", "Report type"),
    "other_reaction": ("other_reactions", "Other reactions"),
}
CHALLENGES = ("Y", "N", "D")  # FDA's dechal and rechal codes that give one; U reads Not given
DECHALS = {
    "Y": "Reaction abated when stopped",
    "N": "Did not abate when stopped",
    "D": "Does not apply",
}
RECHALS = {
    "Y": "Recurred when restarted",
    "N": "Did not recur when restarted",
    "D": "Does not apply",
}
REPORT_TYPES = {
    "EXP": "Expedited",
    "PER": "Periodic",
    "DIR": "Direct",
    "5DAY": "5-day",
    "30DAY": "30-day",
}
ONSET = re.compile(r"(\d*)-(\d*)")


def onset_span(text: str) -> tuple[int | None, int | None]:
    """The days an onset choice holds, both ends included; None where an end is open."""
    low, high = ONSET.fullmatch(text).groups()  # type: ignore[union-attr]
    return (int(low) if low else None, int(high) if high else None)


def is_onset(text: str) -> bool:
    found = ONSET.fullmatch(text)
    if not found or text == "-":
        return False
    low, high = onset_span(text)
    return low is None or high is None or low <= high


def onset_words(text: str) -> str:
    """An onset choice in words: a band of rule breakdown-lines by its name, else its days."""
    low, high = onset_span(text)
    for band in value("breakdown-lines", "onset_bands"):
        if (band.get("from"), band.get("to")) == (low, high):
            return str(band["name"])
    if low is not None and high is not None:
        return f"{low} {'day' if low == 1 else 'days'}" if low == high else f"{low} to {high} days"
    return f"{low} days or more" if low is not None else f"up to {high} days"


__all__ = [
    "CHALLENGES",
    "DECHALS",
    "ONSET",
    "RECHALS",
    "RECORD_FIELDS",
    "REPORT_TYPES",
    "is_onset",
    "onset_span",
    "onset_words",
]
