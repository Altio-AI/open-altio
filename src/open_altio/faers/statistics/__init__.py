"""The statistics step: EBGM, PRR, ROR, RRR and IC for every suspect ingredient and reaction
pair a release's cases name, with each pair's time to onset, written into the release as
`statistics_T`; and each pair's ROR by age band and by sex, as `statistics_strata_T`.

    cases.py    the one set of cases every statistic counts (rule statistics-cases)
    scored.py   every pair scored, with the maths of open_altio.stats
    onset.py    every pair's time to onset (rule time-to-onset)
    strata.py   every pair's ROR within each age band and each sex (rule ror-strata)
    classes.py  the same cases counted by WHO class in place of ingredient, at each level of
                rule statistics-classes, written as `atc_statistics_T`
    step.py     the build's steps: counted, scored and written, with their manifest entries;
                and the class statistics added to a release already built
"""

from .classes import TABLES as CLASS_TABLES
from .step import (
    AS_PUBLISHED,
    CLASS_COLUMNS,
    COLUMNS,
    STRATA_TABLE,
    TABLE,
    add_as_published,
    add_classes,
    build,
    build_classes,
    by_current_pt,
    record_classes,
    recount,
)

__all__ = [
    "AS_PUBLISHED",
    "CLASS_COLUMNS",
    "CLASS_TABLES",
    "COLUMNS",
    "STRATA_TABLE",
    "TABLE",
    "add_as_published",
    "add_classes",
    "build",
    "build_classes",
    "by_current_pt",
    "recount",
    "record_classes",
]
