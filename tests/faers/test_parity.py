"""A release built from FDA's real 90 quarters, 2004Q1 to 2026Q2, gives the counts measured
apart from this code.

The reference counts come from an earlier, independent build of the same pipeline in Postgres
over the same quarters, and from notebooks 02 and 04, which counted what each of their rules
changes from the release without it. They are the oracle this test checks the release against,
not rule values.

Slow, and skipped unless its settings name what it needs:

    OPEN_ALTIO_ZIPS=<FDA's zips> OPEN_ALTIO_RELEASES=<a folder> \
        uv run pytest -m slow tests/faers/test_parity.py

builds a full release (about a quarter of an hour) into OPEN_ALTIO_RELEASES, replacing one of the
same name, with OPEN_ALTIO_MEMORY_LIMIT (default 6GB) as DuckDB's memory limit.
OPEN_ALTIO_REAL_RELEASE names an existing release to check instead, and OPEN_ALTIO_BEFORE a
release built with the rules of notebooks 02 and 04 switched off (notebook 02 gives its
rules.toml), which gives the Postgres build's counts themselves. The counts are read from
funnel.json only, as anything downstream reads them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from open_altio.faers import build_release

pytestmark = pytest.mark.slow

POSTGRES = {
    "report_versions": {"faers": 20_536_224, "legacy": 4_276_201},
    "latest_versions": {"faers": 17_683_864, "legacy": 3_091_168},
}
POSTGRES_TOTAL = {
    "after_deleted_lists": 20_676_945,
    "kept_after_duplicates": 20_385_398,
}
# What the rules of notebook 02 change, counted there from the release before them. One latest
# version per case across eras drops the AERS copies of the 82,342 cases FDA carried into FAERS
# (rules/latest-version.md). Of those copies, 395 were already set aside as duplicates and 114
# groups keep another member in their place, so 81,833 fewer cases are kept. Legacy countries
# read as ISO codes then set 11 more aside (rules/legacy-country.md), and reaction terms compared
# in capitals 941 more (rules/reaction-term-case.md). Legacy cases on FDA's deleted lists then
# leave the case set (rules/deleted-cases.md): 6,074 cases; 54 of them were already set aside and
# 40 cases they had set aside are kept again, so 5,980 fewer are kept.
NOTEBOOK_02 = {
    "latest_versions": {"legacy": -82_342},
    "after_deleted_lists": -82_342 - 6_074,
    "kept_after_duplicates": -81_833 - 11 - 941 - 5_980,
}
# What the rules of notebook 04 change, counted there from a release with notebook 02's rules,
# apart from the release code. Groups of 8 or more from one company whose shared event date is
# padded set nothing aside: 4,324 more kept (rules/dup-padded-event-dates.md). The manufacturer
# number with its sex and age guards sets 3,939 more aside, and a number without its country code
# 365 more (rules/dup-manufacturer-number.md). Which copy is shown changes in every group, not how
# many are kept (rules/dup-shown-copy.md).
NOTEBOOK_04 = {"kept_after_duplicates": 4_324 - 3_939 - 365}
EXPECTED = {
    step: {era: n + NOTEBOOK_02.get(step, {}).get(era, 0) for era, n in counts.items()}
    for step, counts in POSTGRES.items()
}
EXPECTED_TOTAL = {
    step: n + NOTEBOOK_02[step] + NOTEBOOK_04.get(step, 0) for step, n in POSTGRES_TOTAL.items()
}


def _funnel(path: Path) -> dict:
    return json.loads((path / "funnel.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def real_funnel() -> dict:
    existing = os.environ.get("OPEN_ALTIO_REAL_RELEASE")
    if existing:
        path = Path(existing).expanduser()
        if not (path / "funnel.json").is_file():
            pytest.fail(f"OPEN_ALTIO_REAL_RELEASE={existing} holds no funnel.json")
        return _funnel(path)
    if not (os.environ.get("OPEN_ALTIO_ZIPS") and os.environ.get("OPEN_ALTIO_RELEASES")):
        pytest.skip("set OPEN_ALTIO_ZIPS and OPEN_ALTIO_RELEASES, or OPEN_ALTIO_REAL_RELEASE")
    out = Path(os.environ["OPEN_ALTIO_RELEASES"]).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    return _funnel(
        build_release(
            Path(os.environ["OPEN_ALTIO_ZIPS"]).expanduser(),
            out,
            overwrite=True,
            memory_limit=os.environ.get("OPEN_ALTIO_MEMORY_LIMIT", "6GB"),
            threads=4,
            say=lambda line: print(line, flush=True),
        )
    )


@pytest.fixture(scope="module")
def before_funnel() -> dict:
    before = os.environ.get("OPEN_ALTIO_BEFORE")
    if not before:
        pytest.skip(
            "set OPEN_ALTIO_BEFORE to a release built with the rules of notebooks 02 and 04 off"
        )
    return _funnel(Path(before).expanduser())


def _count(funnel: dict, step_id: str) -> dict:
    return next(s for s in funnel["steps"] if s["id"] == step_id)["count"]


@pytest.mark.parametrize("step_id", sorted(EXPECTED))
def test_versions_per_era_equal_the_postgres_build_less_notebook_02(real_funnel, step_id):
    count = _count(real_funnel, step_id)
    assert {era: count[era] for era in EXPECTED[step_id]} == EXPECTED[step_id]


@pytest.mark.parametrize("step_id", sorted(EXPECTED_TOTAL))
def test_cases_equal_the_postgres_build_less_notebooks_02_and_04(real_funnel, step_id):
    assert _count(real_funnel, step_id)["total"] == EXPECTED_TOTAL[step_id]


@pytest.mark.parametrize("step_id", [*POSTGRES, *POSTGRES_TOTAL])
def test_with_those_rules_switched_off_a_release_gives_the_postgres_counts(before_funnel, step_id):
    count = _count(before_funnel, step_id)
    if step_id in POSTGRES:
        assert {era: count[era] for era in POSTGRES[step_id]} == POSTGRES[step_id]
    else:
        assert count["total"] == POSTGRES_TOTAL[step_id]
