"""A release's label tables brought up to date with the labels DailyMed changed (rule
label-refresh), choosing again only where a label changed.

    done = update_tables(release_dir, where, days, changed, removed)
    done.candidates, done.sections     the new label_candidates_T and label_sections_T
    done.changed                       each ingredient and family whose label changed

The labels in force are the full release's, each replaced by its version in the newest day's
file that holds it, less those a day withdrew. Every ingredient or combination a changed label
belongs to, before or after, is chosen again among all its labels in force, as the labels step
chooses (build.py); only labels newly chosen, or chosen at a new version, are read for their
sections. With `everything`, every label is read and every choice made again, as when the
labels folder holds another full release than the one the release was read from.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from open_altio import rulebook

from ..reader import read_manifest
from . import build, choose, folder, rxnorm, spl

CANDIDATES, SECTIONS = build.LABEL_TABLES

Located = dict[str, list[tuple[str, str]]]  # set ID -> (zip, member) holding its label


@dataclass(frozen=True)
class Updated:
    candidates: pa.Table
    sections: pa.Table
    changed: list[dict]  # per ingredient and family: its old and new set ID and version
    labels_read: int  # labels whose file was read
    labels_remapped: int  # labels whose products in the mapping file changed
    counts: dict  # the labels entry's counts of the tables, made again


def in_force(parts: Iterable[Path], days: Iterable[folder.Day]) -> Located:
    """Where each label in force is: the full release's, replaced day by day."""
    found: Located = defaultdict(list)
    for part in parts:
        for member in folder.members(part):
            if folder.is_label(member):
                found[folder.set_of(member)].append((str(part), member))
    for day in days:
        for set_id in day.removed:
            found.pop(set_id, None)
        for member in day.members:
            found[folder.set_of(member)] = [(str(day.path), member)]
    return found


def _facts(located: Located, set_ids: Iterable[str]) -> dict[str, tuple[str, str, spl.LabelFacts]]:
    """set ID -> (zip, member, facts) of each of these labels, read side by side, one process
    per file; the highest version where a set is held twice."""
    by_zip: dict[str, list[str]] = defaultdict(list)
    for set_id in sorted(set(set_ids)):
        for where, member in located.get(set_id, []):
            by_zip[where].append(member)
    safety, separator = _safety(), rulebook.value("label-sections", "cell_separator")
    calls = [(z, safety, separator, members) for z, members in by_zip.items()]
    scans = build.side_by_side(build.scan_part, calls)
    return build.highest_versions((z, found) for z, (found, _) in zip(by_zip, scans, strict=True))


def _wanted() -> dict[str, str]:
    return {str(k): v for k, v in rulebook.value("label-sections", "sections").items()}


def _safety() -> dict[str, str]:
    readable = set(rulebook.value("label-choice", "readable_sections"))
    return {k: v for k, v in _wanted().items() if v in readable}


def _lines(read: dict[str, tuple[str, str, spl.LabelFacts]]) -> dict[str, list[spl.Line]]:
    """set ID -> its lines, read from the files that hold these labels."""
    by_zip: dict[str, list[str]] = defaultdict(list)
    for z, member, _ in read.values():
        by_zip[z].append(member)
    separator = rulebook.value("label-sections", "cell_separator")
    unclassified = str(rulebook.value("label-sections", "unclassified_section"))
    calls = [(z, m, _wanted(), separator, unclassified) for z, m in by_zip.items()]
    by_member = {
        m: v for r in build.side_by_side(build.read_sections_of, calls) for m, v in r.items()
    }
    return {s: by_member[member][0] for s, (_, member, _) in read.items()}


def _rows(release_dir: Path, table: str) -> list[dict]:
    manifest = read_manifest(release_dir)
    return pq.read_table(release_dir / manifest["tables"][table]["path"]).to_pylist()


def _label(row: dict | None) -> dict | None:
    return None if row is None else {"setid": row["setid_T"], "version": row["spl_version_T"]}


def _changes(before: list[dict], after: list[dict]) -> list[dict]:
    """Each ingredient and family whose label is another, or another version, or none."""
    old = {(r["rxcui_T"], r["route_family_T"]): r for r in before}
    new = {(r["rxcui_T"], r["route_family_T"]): r for r in after}
    out = []
    for key in sorted(old.keys() | new.keys()):
        was, now = _label(old.get(key)), _label(new.get(key))
        if was != now:
            row = new.get(key) or old[key]
            out.append(
                {
                    "rxcui": key[0],
                    "ingredient": row["ingredient_T"],
                    "family": key[1],
                    "old": was,
                    "new": now,
                }
            )
    return out


def _counts(rows: list[dict], section_rows: list[dict], rx: rxnorm.RxNorm) -> dict:
    """The labels entry's counts that come from the tables alone (build.py names them)."""
    keys = {r["rxcui_T"] for r in rows}
    minimal = set(rx.min_of.values())
    families = Counter(r["rxcui_T"] for r in rows)
    differ = {r["rxcui_T"]: r["forms_differ_T"] for r in rows}
    return {
        "ingredients_with_label": len(keys - minimal),
        "combinations_with_label": len(keys & minimal),
        "family_labels": len(rows),
        "with_several_families": sum(n > 1 for n in families.values()),
        "several_families_forms_differ": sum(differ[k] for k, n in families.items() if n > 1),
        "labels_with_sections_read": len({r["setid_T"] for r in rows}),
        "section_rows": dict(Counter(r["section_T"] for r in section_rows)),
    }


def update_tables(
    release_dir: Path,
    where: folder.LabelsFolder,
    days: list[folder.Day],
    changed: set[str],
    removed: set[str],
    *,
    mapped_before: dict[str, list[str]] | None = None,
    everything: bool = False,
    say: Callable[[str], None] = lambda _line: None,
) -> Updated | None:
    """The release's label tables with `changed` and `removed` (set IDs) applied, from the
    labels folder `where` and the daily files `days`, every one applied so far, oldest first;
    None when there is nothing to choose again. `mapped_before` is each label's products in the
    mapping file the release was keyed with: a label whose products differ now is chosen again
    as a changed one is."""
    located = in_force(where.parts, days)
    products = folder.products_by_label(where.mapping)
    remapped = {
        s for s in located if mapped_before is not None and mapped_before.get(s) != products.get(s)
    }
    changed = changed | remapped
    if not everything and not (changed & located.keys() or removed):
        return None
    rx = rxnorm.read_rxnorm(where.rxnorm)
    policy = choose.Policy.read()
    aside = rx.codes_named(rulebook.value("label-choice", "not_counted_beside_others"))
    old = _rows(release_dir, CANDIDATES)
    # DailyMed maps a label's new version some days after it publishes it, and until then the
    # mapping file has no row for its set ID: a label the release chose keeps the key it had
    held_key = {r["setid_T"]: r["rxcui_T"] for r in old if r["keyed_by_T"] == choose.MAPPING_FILE}
    keyed = {s: rx.key(products.get(s, []), aside) for s in located}
    unlisted = (located.keys() - products.keys()) & held_key.keys()
    keyed |= {s: (held_key[s], "held") for s in unlisted}
    code_of = {s: code for s, (code, _) in keyed.items() if code is not None}
    mapped = set(code_of.values())
    own_on = rulebook.is_on(build.OWN_RULE)

    read = _facts(located, changed & located.keys())
    unmapped = {s for s, (_, how) in keyed.items() if how == "no_code"}
    affected: set[str] | None = None
    if not everything:
        news = [f for s, (_, _, f) in read.items() if s in unmapped]
        own = build.own_ingredients(news, mapped, rx, policy) if own_on else []
        affected = (
            {code_of[s] for s in changed & code_of.keys()}
            | {c.rxcui for c in own}
            | {r["rxcui_T"] for r in old if r["setid_T"] in changed | removed}
        )
    wanted = {s for s, code in code_of.items() if affected is None or code in affected}
    # only a key no mapped label reaches can take a label by its own ingredients
    own_needed = own_on and (affected is None or bool(affected - mapped))
    read |= _facts(located, (wanted | (unmapped if own_needed else set())) - read.keys())
    say(
        f"labels: read {len(read)} labels for {'every' if affected is None else len(affected)} "
        "ingredients and combinations"
    )

    candidates = [
        build.candidate(code_of[s], read[s][2], rx, policy, choose.MAPPING_FILE)
        for s in sorted(wanted & read.keys())
    ]
    if own_needed:
        own = build.own_ingredients(
            [read[s][2] for s in sorted(unmapped & read.keys())], mapped, rx, policy
        )
        candidates += [c for c in own if affected is None or c.rxcui in affected]
    chosen = choose.choose(candidates, policy)

    held = {r["setid_T"]: r["spl_version_T"] for r in old}
    old_lines: dict[str, list[spl.Line]] = defaultdict(list)
    for r in _rows(release_dir, SECTIONS):
        old_lines[r["setid_T"]].append(
            spl.Line(r["section_T"], r["loinc_T"], r["ordinal_T"], r["is_table_row_T"], r["text_T"])
        )
    picked = {c.candidate.facts.set_id for c in chosen}
    again = {s: read[s] for s in picked if held.get(s) != read[s][2].spl_version}
    lines = {s: old_lines[s] for s in picked - again.keys()} | _lines(again)
    differ = build.forms_differ(chosen, lines, set(_safety().values()))
    new_rows = [build.label_row(c, differ, policy) for c in chosen]
    kept = [r for r in old if affected is not None and r["rxcui_T"] not in affected]
    rows = sorted(kept + new_rows, key=lambda r: (r["rxcui_T"], r["route_family_T"]))
    for set_id in {r["setid_T"] for r in kept} - lines.keys():
        lines[set_id] = old_lines[set_id]
    section_rows = [
        {
            "setid_T": set_id,
            "section_T": ln.section,
            "loinc_T": ln.loinc,
            "ordinal_T": ln.ordinal,
            "is_table_row_T": ln.is_table_row,
            "text_T": ln.text,
        }
        for set_id in sorted({r["setid_T"] for r in rows})
        for ln in lines[set_id]
    ]
    touched = [r for r in old if affected is None or r["rxcui_T"] in affected]
    return Updated(
        pa.Table.from_pylist(rows, build.CANDIDATES_SCHEMA),
        pa.Table.from_pylist(section_rows, build.SECTIONS_SCHEMA),
        _changes(touched, new_rows),
        len(read),
        len(remapped),
        _counts(rows, section_rows, rx),
    )
