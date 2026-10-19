"""Which drug and reaction pairs of a release get a label flag (rule label-flags): each suspect
drug record that is no trial product, by its RxNorm code and route families, with every
reaction of its case; and the same record by each ingredient it is counted under, read on that
ingredient's own label, for the pages that count any product containing the ingredient.

The record tables are read by their contracts, each one row per drug record keyed by `KEY`:
`drug_substance_T` (rule drug-names) says whether DiAna marks the record a trial product
(`diana_trial_T`); `drug_rxnorm_T` (rule rxnorm-ingredients) gives its RxNorm code (`rxcui_T`,
NULL without one); `drug_route_T` (rule drug-route) gives the families its form could be in
(`route_families_T`, sorted and joined with ";", empty when nothing is known);
`ingredient_rxnorm_T` (rule rxnorm-ingredients) gives each ingredient its own code (`rxcui_T`,
NULL without one), keyed by `ingredient_T`, one of `substance_T`'s ingredients. FDA repeats a
record's key on one drug row per dose, so records are read as distinct keys and counted as keys
or cases, never as rows joined back to `drug_latest_T`.

The label follows the unit counted: a record whose RxNorm code names another drug than the
ingredient it is counted under (`substance_T`; unit.py says when) is not read on that code's
label. It is flagged as a record with no code is, and `OTHER_DRUG` lists it.

    from open_altio.faers.labeldict import join
    scope = join.scope(release_dir)        # what the release lets the step read, and why not
    for rxcui, families, pt in join.pairs(release_dir, scope): ...
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from open_altio import rulebook

from ..drugnames.dictionary import SEPARATOR
from ..explorer_db import build_connection
from ..rxnorm.layer import INGREDIENTS
from .release_io import CANDIDATES, col, has_table, public, quoted
from .unit import Unit

RULE = "label-flags"
KEY = ("era_T", "primaryid", "quarter_T", "drug_seq")
CASE = KEY[:3]
DRUGS, REACTIONS = "drug_latest_T", "reac_latest_T"
SUBSTANCES, RXNORM, ROUTE = "drug_substance_T", "drug_rxnorm_T", "drug_route_T"
# what the step cannot do without each table it needs
NEEDED = {
    SUBSTANCES: "no drug record says whether it is a trial product (the drug names step)",
    RXNORM: "no drug record carries an RxNorm code, so none can find its label",
}
WITHOUT_ROUTE = f"no {ROUTE}: no drug record says its form, so each is read on every form's label"
WITHOUT_INGREDIENTS = (
    f"no {INGREDIENTS}: no ingredient has its own code, so no record is read on the own label "
    "of each ingredient it is counted under"
)
# the fates a suspect record can meet on its way to a label, in order
FATES = ("trial_product", "no_rxnorm_code", "code_names_another_drug", "no_label", "label")
# the suspect records whose code names another drug than the one counted, with that code
OTHER_DRUG = "label_other_drug_T"
OTHER_DRUG_COLUMNS = ("rxcui_T", "rxnorm_name_T", "matched_by_T", "substance_T")
_OTHER = "label_other_pairs_T"  # scratch: (counted ingredient, code name) pairs that disagree
_BATCH = 50_000  # pairs fetched from DuckDB at a time


@dataclass(frozen=True)
class Scope:
    """What a release lets the step read: why it cannot run, if it cannot, and what a
    missing route table means for the flags."""

    missing: dict[str, str] = field(default_factory=dict)  # needed table -> why it matters
    route: bool = True  # the release holds drug_route_T
    ingredients: bool = True  # the release holds ingredient_rxnorm_T
    # (substance_T, rxnorm_name_T) pairs whose code names another drug than the one counted
    other: frozenset[tuple[str, str]] = frozenset()

    @property
    def notes(self) -> list[str]:
        missing = ((self.route, WITHOUT_ROUTE), (self.ingredients, WITHOUT_INGREDIENTS))
        return [note for held, note in missing if not held]

    def why_not(self) -> str | None:
        if not self.missing:
            return None
        return "; ".join(f"no {table}: {why}" for table, why in self.missing.items())


def scope(release_dir: Path) -> Scope:
    missing = {t: why for t, why in NEEDED.items() if not has_table(release_dir, t)}
    return Scope(
        missing,
        route=has_table(release_dir, ROUTE),
        ingredients=has_table(release_dir, INGREDIENTS),
        other=frozenset() if missing else _other(release_dir),
    )


def _other(release_dir: Path) -> frozenset[tuple[str, str]]:
    """The (counted ingredient, code name) pairs of the release's records that disagree."""
    key = ", ".join(KEY)
    rx = public(release_dir, RXNORM)
    with _connection() as con:
        names = [n for (n,) in con.execute(f"SELECT DISTINCT rxnorm_name_T FROM {rx}").fetchall()]
        found = con.execute(f"""
            SELECT DISTINCT s.substance_T, r.rxnorm_name_T
            FROM {public(release_dir, SUBSTANCES)} s JOIN {rx} r USING ({key})
            WHERE s.substance_T IS NOT NULL AND r.rxnorm_name_T IS NOT NULL""").fetchall()
    unit = Unit(n for n in names if n)
    return frozenset((s, n) for s, n in found if unit.other_drug(s, n))


def _scratch(con: duckdb.DuckDBPyConnection, sc: Scope) -> None:
    con.execute(f"CREATE TEMP TABLE {_OTHER} (substance_T VARCHAR, rxnorm_name_T VARCHAR)")
    if sc.other:  # DuckDB refuses an empty executemany
        con.executemany(f"INSERT INTO {_OTHER} VALUES (?, ?)", sorted(sc.other))


@contextmanager
def _connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """A connection held to the build's memory and threads (rule explorer-build-memory), so
    the join of every record with its case's reactions spills to disk rather than growing."""
    with tempfile.TemporaryDirectory(prefix="label-flags-") as spill:
        con = build_connection(":memory:", spill=spill)
        try:
            yield con
        finally:
            con.close()


def _records(release_dir: Path, route: bool) -> str:
    """One row per suspect drug record: its key, whether it is a trial product, the RxNorm
    code its label is read by (none when the code names another drug than the one counted),
    whether it does, its code as drug_rxnorm_T gives it, its ingredients, and its route families
    sorted and joined with ";" ('' when nothing is known). Needs the scratch pairs (_scratch)."""
    roles = ", ".join(quoted(r) for r in rulebook.value(RULE, "suspect_roles"))
    key = ", ".join(KEY)
    families = "coalesce(ro.route_families_T, '')" if route else "''"
    joined = f"LEFT JOIN {public(release_dir, ROUTE)} ro USING ({key})" if route else ""
    return f"""
    SELECT {key}, coalesce(s.diana_trial_T, false) AS trial_T,
           CASE WHEN o.substance_T IS NULL THEN r.rxcui_T END AS rxcui_T,
           o.substance_T IS NOT NULL AS other_T, r.rxcui_T AS code_T, r.rxnorm_name_T,
           r.matched_by_T, s.substance_T, {families} AS families_T
    FROM (SELECT DISTINCT {key} FROM {public(release_dir, DRUGS)} WHERE role_cod IN ({roles}))
    JOIN {public(release_dir, SUBSTANCES)} s USING ({key})
    LEFT JOIN {public(release_dir, RXNORM)} r USING ({key})
    LEFT JOIN {_OTHER} o ON o.substance_T = s.substance_T AND o.rxnorm_name_T = r.rxnorm_name_T
    {joined}"""


def _keyed(release_dir: Path, sc: Scope) -> str:
    """Each suspect record that is no trial product, by the code its flags are keyed by and its
    case: its own RxNorm code, and the own code of each ingredient it is counted under (NULL
    without one), so a combination's reactions are read on each of its ingredients' own labels
    too. A code met by both ways is one row."""
    case = ", ".join(CASE)
    kept = f"SELECT * FROM ({_records(release_dir, sc.route)}) WHERE NOT trial_T"
    own = f"SELECT rxcui_T, families_T, {case} FROM kept"
    if not sc.ingredients:
        return f"WITH kept AS ({kept}) {own}"
    counted = f"""SELECT g.rxcui_T, k.families_T, {", ".join(f"k.{c}" for c in CASE)}
      FROM (SELECT families_T, {case},
                   unnest(string_split(substance_T, '{SEPARATOR}')) AS ingredient_T
            FROM kept WHERE substance_T IS NOT NULL) k
      LEFT JOIN {public(release_dir, INGREDIENTS)} g USING (ingredient_T)"""
    return f"WITH kept AS ({kept}) {own} UNION {counted}"


def pairs(release_dir: Path, sc: Scope) -> Iterator[tuple[str | None, str, str]]:
    """Every distinct (rxcui, route families, reaction as FDA published it) of the suspect
    records that are no trial product, by their own codes and their ingredients' (`_keyed`), in
    the order of rxcui and reaction, so one reaction of one drug comes together."""
    sql = f"""
    SELECT DISTINCT d.rxcui_T, d.families_T, x.pt
    FROM ({_keyed(release_dir, sc)}) d
    JOIN {public(release_dir, REACTIONS)} x USING ({", ".join(CASE)})
    WHERE x.pt IS NOT NULL
    ORDER BY d.rxcui_T NULLS LAST, x.pt, d.families_T"""
    with _connection() as con:
        _scratch(con, sc)
        cur = con.execute(sql)
        while batch := cur.fetchmany(_BATCH):
            yield from batch


def fates(release_dir: Path, sc: Scope) -> dict[str, dict[str, int]]:
    """How many suspect records, and cases, meet each fate on the way to a label: a trial
    product, no RxNorm code, a code with no label in any family, or a label. A case counts
    under each fate one of its records meets."""
    labelled = f"SELECT DISTINCT {col('rxcui')} AS rxcui_T FROM {public(release_dir, CANDIDATES)}"
    sql = f"""
    WITH r AS ({_records(release_dir, sc.route)}),
    f AS (
      SELECT {", ".join(KEY)},
             CASE WHEN trial_T THEN '{FATES[0]}' WHEN other_T THEN '{FATES[2]}'
                  WHEN r.rxcui_T IS NULL THEN '{FATES[1]}'
                  WHEN l.rxcui_T IS NULL THEN '{FATES[3]}' ELSE '{FATES[4]}' END AS fate_T
      FROM r LEFT JOIN ({labelled}) l USING (rxcui_T))
    SELECT fate_T, count(*), count(DISTINCT ({", ".join(CASE)})) FROM f GROUP BY 1"""
    with _connection() as con:
        _scratch(con, sc)
        found = {fate: (n, c) for fate, n, c in con.execute(sql).fetchall()}
    out = {
        "records": {fate: int(found.get(fate, (0, 0))[0]) for fate in FATES},
        "cases": {fate: int(found.get(fate, (0, 0))[1]) for fate in FATES},
    }
    out["records"]["suspect"] = sum(out["records"].values())
    return out


def write_other(release_dir: Path, sc: Scope, path: Path) -> int:
    """Write the suspect records that are no trial product and whose code names another drug
    than the one counted (OTHER_DRUG) to `path`; return how many."""
    cols = ", ".join(("code_T AS rxcui_T", *OTHER_DRUG_COLUMNS[1:]))
    sql = f"""SELECT {", ".join(KEY)}, {cols} FROM ({_records(release_dir, sc.route)})
              WHERE other_T AND NOT trial_T ORDER BY {", ".join(KEY)}"""
    with _connection() as con:
        _scratch(con, sc)
        con.execute(f"COPY ({sql}) TO {quoted(str(path))} (FORMAT parquet, COMPRESSION zstd)")
        counted = f"SELECT count(*) FROM read_parquet({quoted(str(path))})"
        return int(con.execute(counted).fetchall()[0][0])


__all__ = [
    "CASE",
    "FATES",
    "KEY",
    "OTHER_DRUG",
    "OTHER_DRUG_COLUMNS",
    "WITHOUT_INGREDIENTS",
    "Scope",
    "fates",
    "pairs",
    "scope",
    "write_other",
]
