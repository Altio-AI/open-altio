"""Reading a label's tables row by row (rule label-table-rows)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from open_altio import rulebook

from .scope import Verdict
from .text import TextReader

RULE = "label-table-rows"
CELL = "|"
_NUMBER = re.compile(r"([<≤]\s*)?(\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class RowReading:
    # no verdict when the row holds no values: it is then read as a sentence
    verdict: Verdict | None
    under_header: bool  # the row is in a table with a comparator header


def cells(row: str) -> list[str]:
    return [c.strip() for c in row.split(CELL)]


class TableReader:
    def __init__(
        self,
        reader: TextReader,
        comparator_words: Sequence[str],
        zero_marks: Sequence[str],
    ) -> None:
        self._reader = reader
        self._comparators = [tuple(w.key for w in reader.words(p)) for p in comparator_words]
        self._zero = {m.lower() for m in zero_marks}

    @classmethod
    def from_rules(cls, reader: TextReader) -> TableReader:
        # switched off, no column is a comparator's, so every row with a value is kept
        comparators = rulebook.value(RULE, "comparator_words") if rulebook.is_on(RULE) else []
        return cls(reader, comparators, rulebook.value(RULE, "zero_marks"))

    def _is_comparator(self, cell: str) -> bool:
        keys = [w.key for w in self._reader.words(cell)]
        return any(
            tuple(keys[i : i + len(p)]) == p for p in self._comparators for i in range(len(keys))
        )

    def value(self, cell: str) -> float | None:
        """The cell's first number; "<1" counts as more than zero; a zero mark is zero."""
        if cell.lower() in self._zero:
            return 0.0
        found = _NUMBER.search(cell)
        if found is None:
            return None
        number = float(found.group(2))
        return max(number, 0.5) if found.group(1) else number

    def read(self, rows: Sequence[str]) -> list[RowReading]:
        """One reading per row of one table, in order."""
        header: tuple[int, set[int]] | None = None
        out = []
        for row in rows:
            parts = cells(row)
            arms = {i for i, c in enumerate(parts) if i > 0 and self._is_comparator(c)}
            if arms:
                header = (len(parts), arms)
                why = "a header row names the treatment arms"
                out.append(RowReading(Verdict(False, RULE, "header", why), True))
                continue
            values = {
                i: v for i, c in enumerate(parts) if i > 0 and (v := self.value(c)) is not None
            }
            if not values:
                out.append(RowReading(None, header is not None))
            elif header is None:
                why = "a table with no comparator lists it"
                out.append(RowReading(Verdict(True, RULE, "table", why), False))
            else:
                out.append(RowReading(self._judge(len(parts), values, *header), True))
        return out

    @staticmethod
    def _judge(width: int, values: dict[int, float], header_width: int, arms: set[int]) -> Verdict:
        if all(v > 0 for v in values.values()):
            return Verdict(True, RULE, "table", "every column has it, so the drug's does")
        if width != header_width:
            why = "the row does not line up with the table's header"
            return Verdict(None, RULE, "table-misaligned", why)
        drug = [v for i, v in values.items() if i not in arms]
        others = [v for i, v in values.items() if i in arms]
        if any(v > 0 for v in drug):
            return Verdict(True, RULE, "table", "the drug's column has it")
        if drug and any(v > 0 for v in others):
            return Verdict(False, RULE, "table-comparator-only", "only the comparator had it")
        why = "no value above zero in the drug's columns"
        return Verdict(None, RULE, "table-no-value", why)
