"""The labels a FAERS drug record is compared with (rule label-choice).

    from open_altio.faers.labels.lookup import LabelLookup
    lookup = LabelLookup.read("releases/2026Q2")
    lookup.set_id(rxcui, "by_mouth")   # the label for that route family, or None
    lookup.families(rxcui)             # every family's label, for a record whose family is unknown

There is no default label: a record whose family is unknown is compared with
every family's label, and `forms_differ(rxcui)` says whether those can disagree.
The same in SQL:

    SELECT route_family_T, setid_T, forms_differ_T FROM label_candidates_T
    WHERE rxcui_T = <rxcui> [AND route_family_T = <family>]
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb


@dataclass(frozen=True)
class LabelLookup:
    by_family: dict[str, dict[str, str]]  # rxcui -> route family -> set ID
    differ: dict[str, bool]  # rxcui -> whether its families' safety sections differ

    @classmethod
    def from_rows(cls, candidates: Iterable[Mapping[str, Any]]) -> LabelLookup:
        """From the rows of label_candidates_T."""
        by_family: dict[str, dict[str, str]] = defaultdict(dict)
        differ = {}
        for r in candidates:
            by_family[r["rxcui_T"]][r["route_family_T"]] = r["setid_T"]
            differ[r["rxcui_T"]] = r["forms_differ_T"]
        return cls(dict(by_family), differ)

    @classmethod
    def read(cls, release_dir: str | Path) -> LabelLookup:
        path = Path(release_dir).expanduser() / "parquet" / "label_candidates_T.parquet"
        rel = duckdb.connect().sql(f"SELECT * FROM read_parquet('{path}')")
        return cls.from_rows(
            dict(zip(rel.columns, values, strict=True)) for values in rel.fetchall()
        )

    def set_id(self, rxcui: str, family: str) -> str | None:
        """The ingredient's label for that route family; None when it has none."""
        return self.by_family.get(rxcui, {}).get(family)

    def families(self, rxcui: str) -> dict[str, str]:
        """Every route family's label; empty when the ingredient has no label."""
        return dict(self.by_family.get(rxcui, {}))

    def forms_differ(self, rxcui: str) -> bool:
        return self.differ.get(rxcui, False)
