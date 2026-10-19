"""Reviewed codings of the label phrases the rules could not settle, frozen as data so a
build never calls a model (rule label-flags).

Each line of `licensed/meddra/label_codings_frozen.jsonl` codes one uncertain item:
`item_id`, `set_id`, `section`, `sentence`, `pts` (the PTs the phrase states, as codes or
names, or empty when it states none), `none_reason`, `agent`, `instructions_version`,
`reviewed_at`. The file sits in the version's folder, which a rebuild of the version
keeps it in."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from ..meddra import LABEL_CODINGS_FILE
from .coding import Coded

CODINGS_FILE = LABEL_CODINGS_FILE
CODED_BY = "reviewer"
CODING_RULE = "label-flags"


def _key(item: Mapping) -> tuple:
    return item["set_id"], item["section"], item["sentence"]


def read_codings(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def apply_codings(coded: Coded, codings: Iterable[Mapping], pt_names: Mapping[str, str]) -> int:
    """A coding with PTs keeps those PTs on the label from its sentence; a coding with
    none keeps every term of its sentence off, rule hits included. Either way the item
    leaves the uncertain list. Returns how many codings matched the label text."""
    by_name = {name.lower(): code for code, name in pt_names.items()}
    by_sentence: dict[tuple, list[dict]] = {}
    for row in coded.terms:
        by_sentence.setdefault((row["set_id"], row["section"], row["sentence"]), []).append(row)
    matched = 0
    for coding in codings:
        key = (coding["set_id"], coding["section"], coding["sentence"])
        rows = by_sentence.get(key, [])
        if coding["item_id"] not in coded.items and not rows:
            continue  # the label no longer says this
        matched += 1
        item = coded.items.pop(coding["item_id"], None)
        named = [c if c in pt_names else by_name.get(str(c).lower()) for c in coding["pts"] or []]
        codes = {c for c in named if c is not None}
        if not codes:
            for row in rows:
                row["kept"], row["decided_by"] = False, CODED_BY
            for other in [k for k, i in coded.items.items() if _key(i) == key]:
                del coded.items[other]
            continue
        for row in rows:
            if row["item_id"] == coding["item_id"]:
                row["kept"], row["decided_by"] = row["pt_code"] in codes, CODED_BY
        present = {r["pt_code"] for r in rows if r["kept"]}
        for code in sorted(c for c in codes if c not in present):
            row = {
                "set_id": coding["set_id"],
                "section": coding["section"],
                "pt_code": code,
                "pt_name": pt_names[code],
                "llt_code": None,
                "matched_text": item["matched_text"] if item else None,
                "sentence": coding["sentence"],
                "kept": True,
                "rule": CODING_RULE,
                "decided_by": CODED_BY,
                "item_id": coding["item_id"],
            }
            coded.terms.append(row)
            by_sentence.setdefault(key, []).append(row)
    return matched
