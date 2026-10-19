"""The ROR by age band and by sex (rule ror-strata), on the cases the statistics count
(cases.py): for each pair and each value of each part the rule lists, the pair's table of cases
counted again on the cases with that value alone, and its ROR (rule ror). Each part is taken on
its own, never crossed with another. Only the values where the pair has a case are written; at
every other the pair has no case, so its ROR is empty.

    found = count(con, counts)       # con holds cases.count's tables: each pair's cases a value
    columns = table(counts, found)   # after con is closed, so its memory and this never add up

A stratum's value is the part as cases.stratum_parts gives it, `unknown` where not given (rule
statistics-cases). The margins come from the counts already made: each case is in one stratum
of statistics-cases, so an ingredient's cases with a value are its cases summed over the strata
holding that value. The text columns are built as Arrow arrays from each name once, not as a
Python string a row.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pyarrow as pa

from open_altio import rulebook
from open_altio.stats import disproportionality as dp

from .cases import Counts

RULE = "ror-strata"
TABLE = "statistics_strata_T"
# The statistics' name for each column the strata table keeps (its name in the release adds the
# derived suffix).
COLUMNS = (
    "ingredient",
    "reaction",
    "by",
    "stratum",
    "cases",
    "ingredient_cases",
    "reaction_cases",
    "stratum_cases",
    "ror",
    "ror_lower",
    "ror_upper",
)

# Each pair's cases in each value of each part, one pass over the pairs: a grouping set a part,
# told apart by GROUPING() over every part's value, which sets a bit for each value a row is not
# grouped by, the first value's highest. Each value is numbered; the rows come in the table's
# order, so they are scored in it.
PAIRS = """
WITH g AS (
  SELECT i.iid, r.eid, GROUPING({every}) AS grouped, coalesce({every}) AS value, count(*) AS n
  FROM counted_ingredient i JOIN counted_reaction r USING (cid, sid)
  JOIN stratum_value USING (sid)
  GROUP BY GROUPING SETS ({sets}))
SELECT iid::INTEGER AS iid, eid::INTEGER AS eid, CASE grouped {parts} END::TINYINT AS part,
  value::SMALLINT AS value, n::INTEGER AS n
FROM g ORDER BY iid, eid, part, value
"""


def parts() -> list[str]:
    """The parts the rule lists, in its order."""
    return list(rulebook.value(RULE, "by"))


def _numbered(counts: Counts, part: str) -> tuple[np.ndarray, np.ndarray]:
    """The part's values, sorted, and each stratum's number into them."""
    names, value_at = np.unique(counts.strata[part].astype(str), return_inverse=True)
    return names, value_at.ravel()


def count(con: duckdb.DuckDBPyConnection, counts: Counts) -> dict[str, np.ndarray]:
    """Each pair (iid, eid), part (its place in the rule's list) and value (its number into the
    part's sorted values) where the pair has cases, and how many (`n`), in the table's order."""
    by = parts()
    numbers = {f"v{k}": _numbered(counts, part)[1].astype(np.int16) for k, part in enumerate(by)}
    con.register("stratum_value_arrow", pa.table({"sid": counts.strata["stratum"]} | numbers))
    con.execute("CREATE TEMP TABLE stratum_value AS SELECT * FROM stratum_value_arrow")
    con.unregister("stratum_value_arrow")
    every = (1 << len(by)) - 1
    got = con.execute(
        PAIRS.format(
            every=", ".join(numbers),
            sets=", ".join(f"(i.iid, r.eid, {v})" for v in numbers),
            parts=" ".join(
                f"WHEN {every - (1 << (len(by) - 1 - k))} THEN {k}" for k in range(len(by))
            ),
        )
    ).fetchnumpy()
    con.execute("DROP TABLE stratum_value")
    return {name: np.asarray(column) for name, column in got.items()}


def _margin(
    table: dict[str, np.ndarray], key: str, value_at: np.ndarray, width: int, size: int
) -> np.ndarray:
    """Cases per ingredient (or reaction) and value: summed over the strata holding the value."""
    at = table[key] * width + value_at[table["stratum"]]
    return np.bincount(at, weights=table["n"], minlength=size * width).astype(np.int64)


def _text(numbers: np.ndarray, names: np.ndarray) -> pa.Array:
    """A text column from each row's number into `names`."""
    return pa.DictionaryArray.from_arrays(
        pa.array(numbers, type=pa.int32()), pa.array(list(names), type=pa.string())
    ).dictionary_decode()


def table(counts: Counts, found: dict[str, np.ndarray]) -> dict[str, np.ndarray | pa.Array]:
    """COLUMNS for every row of `found`, in its order: by ingredient, then reaction, then the
    rule's parts in order, then value."""
    numbered = [_numbered(counts, part) for part in parts()]
    part, value = found["part"], found["value"].astype(np.int64)
    n_ingredient, n_reaction, n_total = (np.empty(len(value), dtype=np.int64) for _ in range(3))
    name = np.empty(len(value), dtype=np.int64)  # into every part's values, one list
    first_name = 0
    for k, (names, value_at) in enumerate(numbered):
        width, here = len(names), part == k
        v = value[here]
        n_ingredient[here] = _margin(
            counts.ingredient_strata, "product", value_at, width, len(counts.ingredients)
        )[found["iid"][here].astype(np.int64) * width + v]
        n_reaction[here] = _margin(
            counts.reaction_strata, "event", value_at, width, len(counts.reactions)
        )[found["eid"][here].astype(np.int64) * width + v]
        n_total[here] = np.bincount(value_at, weights=counts.strata["n"], minlength=width)[v]
        name[here] = v + first_name
        first_name += width
    cases = found["n"].astype(np.int64)
    cells = dp.table(cases, n_ingredient, n_reaction, n_total)
    ror = dp.ror(cells["a"], cells["b"], cells["c"], cells["d"])
    del cells
    return {
        "ingredient": _text(found["iid"], counts.ingredients),
        "reaction": _text(found["eid"], counts.reactions),
        "by": _text(part, np.asarray(parts())),
        "stratum": _text(name, np.concatenate([names for names, _ in numbered])),
        "cases": cases,
        "ingredient_cases": n_ingredient,
        "reaction_cases": n_reaction,
        "stratum_cases": n_total,
        "ror": ror["ROR"],
        "ror_lower": ror["ROR_lower"],
        "ror_upper": ror["ROR_upper"],
    }
