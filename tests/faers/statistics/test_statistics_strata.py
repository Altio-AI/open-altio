"""Each pair's ROR by age band and by sex (src/open_altio/faers/statistics/strata.py, rule
ror-strata), worked by hand on nine cases: the pair's table counted again within each value of
each part, never the parts crossed, and only the values where the pair has a case."""

from __future__ import annotations

import math

import numpy as np
import pyarrow as pa

from open_altio import rulebook
from open_altio.faers.statistics import cases, strata
from open_altio.stats import disproportionality as dp

UNKNOWN = rulebook.value("statistics-cases", "unknown")
# primaryid, age band, sex, receipt year, kept; the year splits the strata EBGM reads, never these
CASES = [
    ("1", "18-64", "F", 2020, True),
    ("2", "18-64", "F", 2021, True),
    ("3", "18-64", "M", 2020, True),
    ("4", "18-64", "M", 2020, True),
    ("5", "18-64", "F", 2020, True),
    ("6", "65-74", "F", 2020, True),
    ("7", "65-74", "M", 2020, True),
    ("8", "65-74", "F", 2020, True),
    ("9", None, None, None, True),
    ("10", "18-64", "F", 2020, False),  # a duplicate set aside: in no table
]
# each case's one suspect ingredient and one reaction
TAKES = dict(enumerate(("aspirin",) * 3 + ("ibuprofen",) * 2 + ("aspirin", "ibuprofen", "ibuprofen")
                       + ("aspirin",) * 2, 1))  # fmt: skip
REPORTS = dict(enumerate(("Headache", "Headache", "Nausea", "Headache", "Nausea", "Headache")
                         + ("Nausea",) * 2 + ("Headache",) * 2, 1))  # fmt: skip


def table(small_release) -> dict:
    con = small_release(
        case_latest_T=CASES,
        drug_latest_T=[(str(p), "1", "PS") for p in TAKES],
        drug_ingredient_T=[(str(p), "1", i) for p, i in TAKES.items()],
        reac_latest_T=[(str(p), r) for p, r in REPORTS.items()],
    )
    counts = cases.count(con)
    got = strata.table(counts, strata.count(con, counts))
    return {c: np.asarray(v.to_pylist() if isinstance(v, pa.Array) else v) for c, v in got.items()}


def rows(got: dict) -> list[tuple]:
    return list(zip(*(got[c] for c in strata.COLUMNS), strict=True))


def test_aspirin_and_headache_within_each_age_band_and_each_sex(small_release):
    got = [r for r in rows(table(small_release)) if r[:2] == ("aspirin", "headache")]
    # 18 to 64: five cases; aspirin 1, 2, 3; headache 1, 2, 4; both 1 and 2
    adult = dp.ror(**dp.table(2, 3, 3, 5))
    assert [r[2:8] for r in got] == [
        ("age_band", "18-64", 2, 3, 3, 5),
        ("age_band", "65-74", 1, 1, 1, 3),
        ("age_band", UNKNOWN, 1, 1, 1, 1),
        ("sex", "F", 3, 3, 3, 5),  # no male case names both: no row
        ("sex", UNKNOWN, 1, 1, 1, 1),
    ]
    assert got[0][8:] == tuple(float(adult[k]) for k in ("ROR", "ROR_lower", "ROR_upper"))
    assert got[0][8] == 2.0
    assert all(math.isnan(v) for r in got[1:] for v in r[8:])  # a cell of 0: empty


def test_every_row_is_a_pair_with_a_case_there_and_the_rows_come_in_order(small_release):
    got = table(small_release)
    assert (got["cases"] >= 1).all()
    assert set(got["by"]) == set(strata.parts())
    keys = list(zip(got["ingredient"], got["reaction"], strict=True))
    assert keys == sorted(keys)
    # within each pair, each part in the rule's order
    for pair in set(keys):
        parts = [b for k, b in zip(keys, got["by"], strict=True) if k == pair]
        assert parts == sorted(parts, key=strata.parts().index)


def test_each_part_shares_out_every_counted_case_once_whatever_its_year(small_release):
    got = table(small_release)
    total: dict[tuple, int] = {}
    for ingredient, reaction, part, _, n, *_ in rows(got):
        total[(ingredient, reaction, part)] = total.get((ingredient, reaction, part), 0) + n
    pairs = {(i, e) for i, e, _ in total}
    want = {("aspirin", "headache"): 4, ("aspirin", "nausea"): 1, ("ibuprofen", "headache"): 1,
            ("ibuprofen", "nausea"): 3}  # fmt: skip
    assert {pair: {total[(*pair, part)] for part in strata.parts()} for pair in pairs} == {
        pair: {n} for pair, n in want.items()
    }
    for part in strata.parts():
        mine = got["by"] == part
        cases_in = dict(zip(got["stratum"][mine], got["stratum_cases"][mine], strict=True))
        assert sum(cases_in.values()) == 9  # every counted case in one value of the part
