"""Code a release's labels into MedDRA terms, into its licensed part.

The coded rows and the uncertain items are MedDRA content (rule meddra-licensed-tier),
so they go only into `licensed/meddra/<version>/`, beside the MedDRA tables they were
coded from, and into the licensed manifest. The public flags are written by
flagbuild.py."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from open_altio import rulebook

from ..meddra import MEDDRA_DIR, licensed_dir, term_key, write_licensed_manifest
from .coding import (
    TERM_COLUMNS,
    Coded,
    LabelCoder,
    LabelInfo,
    SectionRow,
    distinct_terms,
)
from .codings import CODINGS_FILE, apply_codings, read_codings
from .release_io import (
    CANDIDATES,
    LABELS,
    SECTIONS,
    col,
    connect,
    has_table,
    held_version,
    licensed,
    public,
    require_suffix,
    rows,
)
from .terms import Term

DICTIONARY = "label-dictionary"
SWITCHED_OFF = "rule {rule} is switched off, so the release has no label flags"
TERMS = "label_terms_T"
UNCERTAIN_FILE = "label_uncertain.jsonl"


def _label_infos(release_dir: Path) -> dict[str, LabelInfo]:
    """Each label's RxNorm codes and drugs, joined with ";" when one label serves
    several, and its effective date."""
    sources = [public(release_dir, CANDIDATES)]
    if has_table(release_dir, LABELS):
        sources.append(public(release_dir, LABELS))
    names = ", ".join(col(c) for c in ("set_id", "rxcui", "ingredient", "effective_date"))
    union = " UNION ".join(f"SELECT {names} FROM {s}" for s in sources)
    found: dict[str, tuple[set[str], set[str], date | None]] = {}
    for set_id, rxcui, drug, day in rows(union):
        rxcuis, drugs, _ = found.setdefault(set_id, (set(), set(), day))
        rxcuis.add(rxcui)
        drugs.add(drug or "")
    return {
        s: LabelInfo(";".join(sorted(r)), ";".join(sorted(d)), day.isoformat() if day else None)
        for s, (r, d, day) in found.items()
    }


def _rank_items(
    coded: Coded, ranks: Iterable[tuple[str, str, float]], reaction_pt: Mapping
) -> None:
    """Each item's rank: the highest given for its label's drug and its candidate term,
    the reaction text read as its current PT, as the comparison reads it."""
    best: dict[tuple[str, str], float] = {}
    for rxcui, text, rank in ranks:
        term = term_key("pt", text)
        pt = reaction_pt.get(term) if term else None
        if pt is not None and rank is not None:
            best[(rxcui, pt)] = max(rank, best.get((rxcui, pt), rank))
    for item in coded.items.values():
        found = [
            best[(rxcui, item["candidate_pt_code"])]
            for rxcui in item["rxcui"].split(";")
            if (rxcui, item["candidate_pt_code"]) in best
        ]
        item["rank"] = max(found) if found else None


def _section_rows(release_dir: Path) -> Iterator[SectionRow]:
    names = ", ".join(col(c) for c in ("set_id", "section", "ordinal", "is_table_row", "text"))
    con = connect()
    cur = con.execute(
        f"SELECT {names} FROM {public(release_dir, SECTIONS)} WHERE {col('text')} IS NOT NULL"
        f" ORDER BY {col('set_id')}, {col('section')}, {col('ordinal')}"
    )
    while batch := cur.fetchmany(10_000):
        for set_id, section, ordinal, is_table_row, text in batch:
            yield SectionRow(set_id, section, ordinal, bool(is_table_row), text)
    con.close()


def terms_schema() -> pa.Schema:
    return pa.schema([(col(c), pa.bool_() if c == "kept" else pa.string()) for c in TERM_COLUMNS])


def build_label_terms(
    release_dir: str | Path,
    *,
    codings: str | Path | None = None,
    ranks: Iterable[tuple[str, str, float]] = (),
) -> dict:
    """Code every label of the release with the release's MedDRA version and
    write `label_terms_T` and `label_uncertain.jsonl` beside that version's tables. The
    version's frozen codings, if any, decide the phrases the rules could not settle.
    `ranks` gives (rxcui, reaction text, rank) for the pairs a ranking scored, so each
    uncertain item carries the highest rank of its drug and term. Returns what was
    written and the counts, or why nothing was written: a person switched the rule off.
    Raises LabelRefused when the release has no labels or no MedDRA version."""
    if not rulebook.is_on(DICTIONARY):
        return {"skipped": SWITCHED_OFF.format(rule=DICTIONARY)}
    release_dir = Path(release_dir).expanduser()
    manifest, version, entry = held_version(release_dir)
    pt_names = dict(
        rows(f"SELECT pt_code, pt_name FROM {licensed(release_dir, entry, 'meddra_pt')}")
    )
    terms = [
        Term(llt, name, pt, pt_names[pt])
        for llt, name, pt in rows(
            f"SELECT llt_code, llt_name, pt_code FROM {licensed(release_dir, entry, 'meddra_llt')}"
            " WHERE llt_currency = 'Y'"
        )
        if pt in pt_names
    ]
    socs = [
        n for (n,) in rows(f"SELECT soc_name FROM {licensed(release_dir, entry, 'meddra_soc')}")
    ]
    coder = LabelCoder(terms, socs)
    coded = Coded()
    coder.code(_section_rows(release_dir), _label_infos(release_dir), coded)
    coded.terms = distinct_terms(coded.terms)
    reac = licensed(release_dir, entry, "reac_meddra_T")
    _rank_items(coded, ranks, dict(rows(f"SELECT reac_term_T, pt_code_T FROM {reac}")))
    folder = licensed_dir(release_dir) / MEDDRA_DIR / version
    frozen = read_codings(Path(codings) if codings else folder / CODINGS_FILE)
    matched = apply_codings(coded, frozen, pt_names)

    schema = terms_schema()
    require_suffix(TERMS, schema.names)
    table = pa.table({col(c): [r[c] for r in coded.terms] for c in TERM_COLUMNS}, schema)
    pq.write_table(table, folder / f"{TERMS}.parquet", compression="zstd")
    with (folder / UNCERTAIN_FILE).open("w", encoding="utf-8") as fh:
        for key in sorted(coded.items):
            fh.write(json.dumps(coded.items[key], ensure_ascii=False) + "\n")
    entry["tables"][TERMS] = {
        "path": f"{MEDDRA_DIR}/{version}/{TERMS}.parquet",
        "kind": "derived",
        "rows": len(coded.terms),
        "bytes": (folder / f"{TERMS}.parquet").stat().st_size,
    }
    entry["label_uncertain"] = {
        "path": f"{MEDDRA_DIR}/{version}/{UNCERTAIN_FILE}",
        "items": len(coded.items),
    }
    write_licensed_manifest(release_dir, manifest)
    kept = [r["kept"] for r in coded.terms]
    return {
        "version": version,
        "labels": len({r["set_id"] for r in coded.terms}),
        "rows": len(coded.terms),
        "kept": kept.count(True),
        "kept_off": kept.count(False),
        "uncertain": kept.count(None),
        "items": len(coded.items),
        "codings_matched": matched,
        "terms_path": str(folder / f"{TERMS}.parquet"),
        "uncertain_path": str(folder / UNCERTAIN_FILE),
    }
