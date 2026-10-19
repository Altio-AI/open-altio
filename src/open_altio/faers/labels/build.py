"""The labels step: two release tables from a labels folder.

    from open_altio.faers.labels.build import build_labels
    tables = build_labels("~/faers-labels")   # .candidates, .sections, .summary

Every label in the folder is read once for its facts (set ID, version,
dates, marketing category, routes and forms), keyed by RxNorm, and the
choice is made per route family (rule label-choice); then only the
chosen labels are read again for their safety sections (rule label-sections).
Each pass reads the release's parts side by side, one process per part.
"""

from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow as pa

from open_altio import rulebook

from . import choose, folder, rxnorm, spl

LABEL_TABLES = ("label_candidates_T", "label_sections_T")
# The data rules the step reads; with any of them switched off it leaves labels out.
LABEL_RULES = ("label-source", "label-choice", "label-sections")
# Switched off, labels the mapping file leaves without a code are left out
OWN_RULE = "label-own-ingredients"
_UNREADABLE = (ET.ParseError, zipfile.BadZipFile, folder.LabelsFolderError, ValueError)

CANDIDATES_SCHEMA = pa.schema(
    [
        ("rxcui_T", pa.string()),
        ("ingredient_T", pa.string()),
        ("route_family_T", pa.string()),
        ("setid_T", pa.string()),
        ("spl_version_T", pa.int32()),
        ("title_T", pa.string()),
        ("effective_date_T", pa.date32()),
        ("application_T", pa.string()),
        ("routes_T", pa.list_(pa.string())),
        ("dosage_form_T", pa.list_(pa.string())),
        ("chosen_because_T", pa.string()),
        ("forms_differ_T", pa.bool_()),
        ("keyed_by_T", pa.string()),
    ]
)
SECTIONS_SCHEMA = pa.schema(
    [
        ("setid_T", pa.string()),
        ("section_T", pa.string()),
        ("loinc_T", pa.string()),
        ("ordinal_T", pa.int32()),
        ("is_table_row_T", pa.bool_()),
        ("text_T", pa.string()),
    ]
)


def as_of(manifest: dict) -> str | None:
    """The DailyMed day a release's labels are as of (ISO), or None for a release without it:
    the build's, which each refresh moves on (rule label-refresh)."""
    return (manifest.get("labels") or {}).get("as_of")


def scan_part(
    part: str, safety: dict[str, str], separator: str, members: list[str] | None = None
) -> tuple[list[tuple[str, spl.LabelFacts]], int]:
    """Every label's facts in one part (or only those of `members`), and how many could not be
    read. `safety` names the sections whose words make a label readable."""
    found, unreadable = [], 0
    for member, xml in folder.label_xml(Path(part), members):
        try:
            root = spl.parse(xml)
            facts = spl.read_facts(root)
        except _UNREADABLE:
            unreadable += 1
            continue
        text = bool(spl.read_sections(root, safety, separator))
        found.append((member, replace(facts, safety_text=text)))
    return found, unreadable


def read_sections_of(
    part: str,
    members: list[str],
    wanted: dict[str, str],
    separator: str,
    unclassified: str,
) -> dict[str, tuple[list[spl.Line], bool]]:
    """member -> (its safety lines, whether it files any section as unclassified)."""
    out = {}
    with zipfile.ZipFile(part) as outer:
        for member in members:
            root = spl.parse(folder.read_member(outer, member))
            codes = {c.get("code") for c in root.iterfind(f".//{spl.NS}section/{spl.NS}code")}
            out[member] = (
                spl.read_sections(root, wanted, separator),
                unclassified in codes,
            )
    return out


def side_by_side(fn: Callable[..., Any], calls: list[tuple]) -> list[Any]:
    """`fn` over each argument tuple, one process per call; one call runs here."""
    if len(calls) <= 1:
        return [fn(*args) for args in calls]
    with ProcessPoolExecutor(max_workers=min(len(calls), os.cpu_count() or 1)) as pool:
        return list(pool.map(fn, *zip(*calls, strict=True)))


@dataclass(frozen=True)
class LabelTables:
    candidates: pa.Table
    sections: pa.Table
    summary: dict


def label_row(choice: choose.Choice, differ: dict[str, bool], policy: choose.Policy) -> dict:
    """A row of label_candidates_T."""
    c = choice.candidate
    return {
        "rxcui_T": c.rxcui,
        "ingredient_T": c.ingredient,
        "route_family_T": choice.family,
        "setid_T": c.facts.set_id,
        "spl_version_T": c.facts.spl_version,
        "title_T": c.facts.title,
        "effective_date_T": c.facts.effective_date,
        "application_T": c.application,
        "routes_T": list(policy.routes_of(c.facts)),
        "dosage_form_T": list(c.facts.dosage_forms),
        "chosen_because_T": choice.chosen_because,
        "forms_differ_T": differ[c.rxcui],
        "keyed_by_T": c.keyed_by,
    }


def candidate(
    code: str, facts: spl.LabelFacts, rx: rxnorm.RxNorm, policy: choose.Policy, keyed_by: str
) -> choose.Candidate:
    app, number, ident = choose.application(facts, policy)
    return choose.Candidate(code, rx.names.get(code, ""), facts, app, number, ident, keyed_by)


def own_ingredients(
    unmapped: list[spl.LabelFacts], mapped: set[str], rx: rxnorm.RxNorm, policy: choose.Policy
) -> list[choose.Candidate]:
    """Candidates keyed by their own active ingredients (rule label-own-ingredients): the
    labels the mapping file gives no code the current RxNorm holds, for an ingredient or
    combination the file gives no label. A kit's pad does not count beside other ingredients."""
    at = {"substance": 0, "active_moiety": 1}
    order = [at[n] for n in rulebook.value(OWN_RULE, "names_tried")]
    out = []
    for facts in unmapped:
        actives = [a for a in facts.actives if not {a[0], a[1]} & policy.accessories] or list(
            facts.actives
        )
        code, _ = rx.key_named([tuple(a[i] for i in order if a[i]) for a in actives])
        if code is not None and code not in mapped:
            out.append(candidate(code, facts, rx, policy, choose.OWN_INGREDIENTS))
    return out


def forms_differ(
    chosen: list[choose.Choice], lines: dict[str, list[spl.Line]], safety: set[str]
) -> dict[str, bool]:
    """rxcui -> whether two of its families' labels have different safety
    sections, compared with case and spacing ignored (rule label-choice)."""

    def safety_text(set_id: str) -> str:
        words = (ln.text for ln in lines[set_id] if ln.section in safety)
        return " ".join(" ".join(words).lower().split())

    texts: dict[str, set[str]] = defaultdict(set)
    for c in chosen:
        texts[c.candidate.rxcui].add(safety_text(c.candidate.facts.set_id))
    return {rxcui: len(found) > 1 for rxcui, found in texts.items()}


def highest_versions(scans: Iterable[tuple[str, list[tuple[str, spl.LabelFacts]]]]) -> dict:
    """set ID -> (part, member, facts), the highest version where a set
    appears twice."""
    latest: dict[str, tuple[str, str, spl.LabelFacts]] = {}
    for part, found in scans:
        for member, facts in found:
            held = latest.get(facts.set_id)
            if held is None or facts.spl_version > held[2].spl_version:
                latest[facts.set_id] = (part, member, facts)
    return latest


def _own_summary(
    own: list[choose.Candidate], chosen: list[choose.Choice], policy: choose.Policy
) -> dict:
    """What rule label-own-ingredients added: its labels, the ingredients and combinations
    they give a label, and how many of the labels chosen are older than `recent_from`."""
    picked = {
        c.candidate.facts.set_id: c.candidate
        for c in chosen
        if c.candidate.keyed_by == choose.OWN_INGREDIENTS
    }
    old = [c for c in picked.values() if (c.facts.effective_date or date.min) < policy.recent_from]
    return {
        "labels": len(own),
        "ingredients_with_label": len({c.rxcui for c in picked.values()}),
        "labels_chosen": len(picked),
        "labels_chosen_before_recent_from": len(old),
    }


def _unplaced(candidates: list[choose.Candidate], policy: choose.Policy) -> dict[str, int]:
    """Each route of a keyed label the shared route table lacks, with how many labels name it."""
    found: Counter[str] = Counter()
    for c in candidates:
        found.update(set(policy.unplaced(c.facts)))
    return dict(sorted(found.items()))


def _no_family(
    candidates: list[choose.Candidate], chosen: list[choose.Choice], policy: choose.Policy
) -> dict:
    """Keyed labels whose routes give no family, and the ingredients whose label is chosen
    under no family."""
    return {
        "labels": sum(policy.families_of(c.facts) == {policy.no_family} for c in candidates),
        "ingredients": len({c.candidate.rxcui for c in chosen if c.family == policy.no_family}),
    }


def build_labels(labels_dir: str | Path, say: Callable[[str], None] | None = None) -> LabelTables:
    say = say or (lambda _line: None)
    started = time.monotonic()
    where = folder.find(labels_dir)
    parts = [str(p) for p in where.parts]
    wanted = {str(k): v for k, v in rulebook.value("label-sections", "sections").items()}
    separator = rulebook.value("label-sections", "cell_separator")
    readable = set(rulebook.value("label-choice", "readable_sections"))
    safety = {k: v for k, v in wanted.items() if v in readable}
    scans = side_by_side(scan_part, [(p, safety, separator, None) for p in parts])
    latest = highest_versions((p, found) for p, (found, _) in zip(parts, scans, strict=True))
    unreadable = sum(n for _, n in scans)
    say(f"labels: read {len(latest)} labels from {len(parts)} parts ({unreadable} unreadable)")

    products = folder.products_by_label(where.mapping)
    rx = rxnorm.read_rxnorm(where.rxnorm)
    policy = choose.Policy.read()
    set_aside = rx.codes_named(rulebook.value("label-choice", "not_counted_beside_others"))
    keyed: Counter[str] = Counter()
    candidates, unmapped = [], []
    for set_id, (_, _, facts) in sorted(latest.items()):
        code, how = rx.key(products.get(set_id, []), set_aside)
        keyed[how] += 1
        if code is not None:
            candidates.append(candidate(code, facts, rx, policy, choose.MAPPING_FILE))
        elif how == "no_code":
            unmapped.append(facts)
    own = (
        own_ingredients(unmapped, {c.rxcui for c in candidates}, rx, policy)
        if rulebook.is_on(OWN_RULE)
        else []
    )
    chosen = choose.choose(candidates + own, policy)
    keys = {c.candidate.rxcui for c in chosen}
    say(f"labels: {len(keys)} ingredients or sets with a label, {len(chosen)} per family")

    needed: dict[str, list[str]] = defaultdict(list)
    for set_id in sorted({c.candidate.facts.set_id for c in chosen}):
        part, member, _ = latest[set_id]
        needed[part].append(member)
    unclassified = str(rulebook.value("label-sections", "unclassified_section"))
    read = side_by_side(
        read_sections_of,
        [(p, m, wanted, separator, unclassified) for p, m in needed.items()],
    )
    by_member = {m: v for r in read for m, v in r.items()}

    section_rows, silent, silent_unclassified = [], 0, 0
    lines_of: dict[str, list[spl.Line]] = {}
    for set_id in sorted({c.candidate.facts.set_id for c in chosen}):
        lines, files_unclassified = by_member[latest[set_id][1]]
        lines_of[set_id] = lines
        if not lines:
            silent += 1
            silent_unclassified += files_unclassified
        section_rows += [
            {
                "setid_T": set_id,
                "section_T": ln.section,
                "loinc_T": ln.loinc,
                "ordinal_T": ln.ordinal,
                "is_table_row_T": ln.is_table_row,
                "text_T": ln.text,
            }
            for ln in lines
        ]
    min_codes = set(rx.min_of.values())
    differ = forms_differ(chosen, lines_of, set(safety.values()))
    families = Counter(c.candidate.rxcui for c in chosen)
    summary = {
        "files": where.files(),
        "as_of": folder.newest_day(where.parts).isoformat(),
        "label_files": sum(len(found) + n for found, n in scans),
        "labels_read": len(latest),
        "unreadable": unreadable,
        "document_types": dict(Counter(f.document_type for _, _, f in latest.values())),
        "labels_without_safety_text": sum(not f.safety_text for _, _, f in latest.values()),
        "rxnorm_keys": {k: keyed[k] for k in ("IN", "MIN", "no_code", "no_min")},
        "keyed_by_own_ingredients": _own_summary(own, chosen, policy),
        "routes_not_in_route_table": _unplaced(candidates + own, policy),
        "labels_with_no_route_family": _no_family(candidates + own, chosen, policy),
        "ingredients_with_label": len(keys - min_codes),
        "combinations_with_label": len(keys & min_codes),
        "family_labels": len(chosen),
        "with_several_families": sum(n > 1 for n in families.values()),
        "several_families_forms_differ": sum(differ[k] for k, n in families.items() if n > 1),
        "labels_with_sections_read": sum(len(m) for m in needed.values()),
        "without_safety_sections": silent,
        "without_safety_sections_filing_unclassified": silent_unclassified,
        "section_rows": dict(Counter(r["section_T"] for r in section_rows)),
        "seconds": round(time.monotonic() - started, 1),
    }
    return LabelTables(
        pa.Table.from_pylist([label_row(c, differ, policy) for c in chosen], CANDIDATES_SCHEMA),
        pa.Table.from_pylist(section_rows, SECTIONS_SCHEMA),
        summary,
    )


def add_labels(con: Any, labels_dir: str | Path, say: Callable[[str], None]) -> dict:
    """Build the label tables into the release's DuckDB connection, under
    their release names; returns the summary for the manifest."""
    tables = build_labels(labels_dir, say)
    for name, table in zip(LABEL_TABLES, (tables.candidates, tables.sections), strict=True):
        con.register("_label_arrow", table)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _label_arrow")
        con.unregister("_label_arrow")
    s = tables.summary
    say(
        f"labels: {s['labels_with_sections_read']} labels' sections read, "
        f"{sum(s['section_rows'].values())} lines; {s['without_safety_sections']} with no "
        f"safety section ({s['without_safety_sections_filing_unclassified']} file sections "
        f"as unclassified); {s['seconds']}s"
    )
    return s
