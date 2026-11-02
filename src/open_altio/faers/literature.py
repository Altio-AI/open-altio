"""FDA's literature reference as a report gives it (rule literature-reference): it cites an article
where `lit_ref` is given (rule not-given); a report from a file before the rule's first quarter,
which had no such field, gives Not given; from then on a blank says no article is cited. The
breakdowns and the methods page read it here, so they read it one way. FDA's `lit_ref` is never
changed.

    from open_altio.faers import literature
    literature.cited("c.quarter_T", "c.lit_ref")   # SQL: 'cites', '_none' or NULL (Not given)
"""

from __future__ import annotations

from open_altio import rulebook

from . import not_given
from .reader import quoted

RULE = "literature-reference"
CITES = "cites"
NO_ARTICLE = "_none"


def first_quarter() -> str:
    """The first quarter of FDA's files with a literature reference field."""
    return str(rulebook.value(RULE, "first_quarter"))


def cited(quarter: str, column: str) -> str:
    """SQL: CITES where the report in the file of `quarter` cites an article in `column`,
    NO_ARTICLE where its file had the field and the report left it blank, else NULL: the file
    had no such field, or the field says unknown."""
    return (
        f"CASE WHEN {quarter} < {quoted(first_quarter())} THEN NULL "
        f"WHEN {not_given.given('lit_ref', column)} IS NOT NULL THEN {quoted(CITES)} "
        f"WHEN {not_given.check('', column)} THEN {quoted(NO_ARTICLE)} END"
    )


__all__ = ["CITES", "NO_ARTICLE", "RULE", "cited", "first_quarter"]
