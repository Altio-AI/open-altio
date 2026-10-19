"""Legacy MedDRA terms shown in MedDRA's spelling, taken from FAERS's own text (rule
legacy-term-spelling).

AERS wrote every MedDRA term in capitals (`DRUG INEFFECTIVE`); FAERS writes MedDRA's own
spelling (`Drug ineffective`). On a legacy row, `pt_spelling_T` (on `reac_latest_T`) and
`indi_pt_spelling_T` (on `indi_latest_T`) hold the spelling FAERS uses for the same term,
compared without capitals; where FAERS spells a term two ways, the one on more rows. A term
FAERS never spells, and every FAERS row, keeps FDA's text. No MedDRA file is read, so the
columns are public, and FDA's `pt` and `indi_pt` are not changed.

    statements = spelling_tables()          # scratch tables of FAERS's spellings, before the
    child_latest("reac")                    # child tables, which join them; drop_tables() after
"""

from __future__ import annotations

from open_altio import rulebook

RULE = "legacy-term-spelling"

# FDA's table -> its MedDRA term column and the column shown in MedDRA's spelling
COLUMNS = {"reac": ("pt", "pt_spelling_T"), "indi": ("indi_pt", "indi_pt_spelling_T")}


def _scratch(table: str) -> str:
    return f"{table}_spelling_T"


# A FAERS text with a small letter is written as MedDRA spells it; one wholly in capitals is not.
_SPELLINGS = """
CREATE TABLE {scratch} AS
SELECT lower({column}) AS key_T, arg_min({column}, (-n, {column})) AS spelling_T
FROM (SELECT {column}, count(*) AS n FROM {table}
      WHERE era_T = 'faers' AND regexp_matches({column}, '[a-z]') GROUP BY 1)
GROUP BY 1
"""


def spelling_tables() -> list[str]:
    """The scratch tables of FAERS's spellings, one per table; none with the rule off."""
    if not rulebook.is_on(RULE):
        return []
    return [
        _SPELLINGS.format(scratch=_scratch(t), column=c, table=t) for t, (c, _) in COLUMNS.items()
    ]


def drop_tables() -> list[str]:
    return [f"DROP TABLE {_scratch(t)}" for t in COLUMNS] if rulebook.is_on(RULE) else []


def column(table: str) -> tuple[str, str]:
    """(the select fragment, the join fragment) that give `table`'s child rows (alias a) their
    spelling column; FDA's text as written with the rule off. Empty for another table."""
    if table not in COLUMNS:
        return "", ""
    fda, shown = COLUMNS[table]
    if not rulebook.is_on(RULE):
        return f", a.{fda} AS {shown}", ""
    return (
        f", coalesce(s.spelling_T, a.{fda}) AS {shown}",
        f" LEFT JOIN {_scratch(table)} s ON a.era_T = 'legacy' AND s.key_T = lower(a.{fda})",
    )


__all__ = ["COLUMNS", "column", "drop_tables", "spelling_tables"]
