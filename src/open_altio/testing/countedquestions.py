"""Counted questions (/api/count) that hold cases on the invented release, for the tests that
count each of them by every field: the filters alone and in combination, each way a product is
named, and with MedDRA the questions whose reactions are read by today's preferred term.

    QUESTIONS     on the invented release (`release`)
    REACTIONS     on the same with its licensed MedDRA part (`licensed_release`)
    by_value(by, counts)   each value's cases, an event by its reaction whatever its capitals
"""

from __future__ import annotations

from typing import Any

from open_altio.explorer import filters
from open_altio.explorer.filters import DIRECT, NOT_GIVEN
from open_altio.faers.explorer_db import reaction_term

DRUG = "acetylsalicylic acid"
AGES = [b["id"] for b in filters.age_bands()]
# each question holds cases on the invented release, so agreeing is never two counts of nothing
QUESTIONS: list[dict[str, Any]] = [
    {},
    {"product": DRUG},
    {"product": DRUG, "received_from": "2012-05-03", "received_to": "2019-03-02"},
    {"product": DRUG, "sex": "F", "age": NOT_GIVEN, "received_from": "2013-03-02"},
    {"product": DRUG, "dedup": "all", "prole": ["PS", "SS", "I", "C"]},
    {"product": "valsartan", "unit": "exact", "exclude": "DIOVAN", "include": "VALSARTAN TEVA"},
    {"product": "sacubitril;valsartan"},
    {"product": "HUMIRA"},  # a brand opens the drug its records were read to
    {"product": "VALSARTAN TEVA"},  # FDA's spelling with no ingredient
    {"dprod": ["valsartan", "ASPIRIN"], "drole": ["PS", "SS", "C"]},
    {"drug": "aspirin", "role": "PS", "country": ["US", NOT_GIVEN]},
    {"role": "C"},
    {"pt": ["Nausea"]},
    {"pt": ["Headache", "Nausea"], "pt_out": "Nausea", "reaction": "Headache"},
    {"era": "AERS"},
    {"era": ["AERS", "FAERS"], "f": "1", "dedup": "all"},
    {"outcome": ["DE", NOT_GIVEN]},
    {"sender": DIRECT},
    {"sender": NOT_GIVEN},
    {"sender": "eli lilly and co", "reporter": "1"},
    {"event_from": "2010-01-01", "event_to": "2026-06-30"},
    {"reporter": ["1", NOT_GIVEN], "age": AGES},
    # the filters on the drug records a question counts and on the report
    {"product": DRUG, "dose": "100 mg,  qd", "route": "oral", "dose_form": "TABLET"},
    {"product": DRUG, "lot": ["l1", NOT_GIVEN], "report_type": ["exp", "DIR"]},
    {"product": DRUG, "indication": ["Pain", NOT_GIVEN], "dechal": ["D", "Y"]},
    {"product": DRUG, "rechal": NOT_GIVEN, "onset": ["1-30", "91-", NOT_GIVEN]},
    {"product": "valsartan", "other_drug": ["Aspirin", NOT_GIVEN]},
    {"dose": "100 MG, QD", "dechal": "D", "other_drug": "ibuprofen"},
    {"pt": ["Haemorrhage"], "other_reaction": "nausea"},
]
# with MedDRA, the questions whose reactions are read by today's preferred term
REACTIONS: list[dict[str, Any]] = [
    {"product": DRUG},
    {"pt": ["Nausea"]},
    {"pt": ["Headache", "Nausea"], "reaction": "Headache"},
    {"product": DRUG, "indication": ["Pain", NOT_GIVEN]},
]


def by_value(by: str, counts: list[list[Any]]) -> dict[Any, int]:
    """Each value's cases, from `[value, cases, ...]` rows; an event by its reaction, whatever
    its capitals, as the two counts match their events."""
    if by == "event":
        return {reaction_term(v) if v else v: n for v, n, *_ in counts}
    return {v: n for v, n, *_ in counts}


__all__ = ["AGES", "DRUG", "QUESTIONS", "REACTIONS", "by_value"]
