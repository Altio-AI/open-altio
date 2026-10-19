"""Write the public `label_flags_T` from the coded labels (rule label-flags).

It holds no MedDRA code, no lower level term and no group name, so it is public. The
MedDRA groups the rules set aside are named only in the licensed part
(`label_groups.json` beside the version's tables), never in the repository."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from itertools import batched
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from open_altio import rulebook

from ..insights import numbers
from ..insights.methods import refresh_cards
from ..meddra import LABEL_GROUPS_FILE, MEDDRA_DIR, licensed_dir
from ..reader import MANIFEST_FILE, read_manifest
from ..release import PARQUET_DIR, VIEWS_FILE
from . import join
from .build import DICTIONARY, SWITCHED_OFF, TERMS
from .flags import FLAG_COLUMNS, Comparison, Label, Meddra
from .ime import read_ime
from .release_io import (
    CANDIDATES,
    LabelRefused,
    col,
    held_version,
    licensed,
    public,
    require_suffix,
    rows,
)
from .terms import plural

FLAGS_RULE = "label-flags"
NOT_MEDICAL = "label-not-a-medical-event"
UMBRELLA_RULE = "label-umbrella"
FLAGS = "label_flags_T"
# {"not_a_medical_event": [...], "procedure": [...], "catch_all": [...]}
GROUPS_FILE = LABEL_GROUPS_FILE
PROCEDURE = "label-procedure"
STEP = "label_flags"  # the step's entry in the release's manifest
_BATCH = 100_000  # flags written at a time


def _labels(release_dir: Path) -> dict[tuple[str, str], Label]:
    """The label read for each (rxcui, route family), from the per-route candidates
    (rule label-choice gives one per ingredient and family)."""
    names = ", ".join(col(c) for c in ("rxcui", "route_family", "set_id", "effective_date"))
    order = ", ".join(col(c) for c in ("rxcui", "route_family", "set_id"))
    found: dict[tuple[str, str], Label] = {}
    for rxcui, family, set_id, day in rows(
        f"SELECT {names} FROM {public(release_dir, CANDIDATES)} ORDER BY {order}"
    ):
        found.setdefault((rxcui, family), Label(set_id, day))
    return found


def read_groups(release_dir: Path, version: str) -> dict[str, list[str]]:
    """The MedDRA group names each set-aside outcome reads, from the licensed part."""
    path = licensed_dir(release_dir) / MEDDRA_DIR / version / GROUPS_FILE
    if not path.is_file():
        raise LabelRefused(
            f"no {path}: give the labels step your groups file with --groups (rule label-groups)"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def codes_under(release_dir: Path, entry: dict, pts: list[str], groups: list[str]) -> set[str]:
    """The PT codes named in `pts`, or under one of `groups` (a body-system class, a
    group term or a high level term) on the PT's primary path."""
    sql = (
        f"SELECT DISTINCT pt_code FROM {licensed(release_dir, entry, 'meddra_mdhier')}"
        " WHERE primary_soc_fg = 'Y' AND (list_contains(?::VARCHAR[], lower(pt_name))"
        " OR list_has_any(?::VARCHAR[], [lower(soc_name), lower(hlgt_name), lower(hlt_name)]))"
    )
    lowered = [[n.lower() for n in pts], [g.lower() for g in groups]]
    return {code for (code,) in rows(sql, lowered)}


def _set_aside(release_dir: Path, entry: dict, rule: str, groups: dict) -> set[str]:
    """The PT codes a set-aside rule names; none when a person switched the rule off."""
    if not rulebook.is_on(rule):
        return set()
    pts = rulebook.value(rule, "pts") if rule == NOT_MEDICAL else []
    return codes_under(release_dir, entry, pts, groups.get(rulebook.value(rule, "groups_key"), []))


def _named_with(names: Iterable[tuple[str, str]], words: Iterable[str]) -> set[str]:
    """The codes whose name holds one of `words` as whole words, a hyphen read as a
    space."""
    padded = [f" {w.lower().replace('-', ' ')} " for w in words]
    found = set()
    for code, name in names:
        plain = f" {' '.join(name.lower().replace('-', ' ').split())} "
        if any(w in plain for w in padded):
            found.add(code)
    return found


def _pt_pairs(pairs: Iterable[Iterable[str]], names: Mapping[str, set[str]]) -> dict[str, set[str]]:
    """Pairs of PT names (a reported PT, the PT that means the same or is close to it) as PT
    codes, the first of each pair to the second. A name the version does not hold is no pair."""
    found: dict[str, set[str]] = {}
    for first, second in pairs:
        for one in names.get(first.lower(), ()):
            found.setdefault(one, set()).update(names.get(second.lower(), ()))
    return {pt: others for pt, others in found.items() if others}


def _directions(names: Iterable[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """The PTs that name a rise or a fall of a measure ("Platelet count increased",
    "Hypoglycaemia"), each as its direction and the measure it moves (rule label-flags,
    `opposite_direction`)."""
    rule = rulebook.value(FLAGS_RULE, "opposite_direction")
    found = {}
    for pt, name in names:
        low = name.lower().strip()
        for end, way in ((rule["up_ends"], "up"), (rule["down_ends"], "down")):
            if low.endswith(f" {end}"):
                stem = low[: -len(end) - 1].strip()
                found[pt] = (way, rule["same_measure"].get(stem, stem))
        if pt in found:
            continue
        for start, way in ((rule["up_starts"], "up"), (rule["down_starts"], "down")):
            if low.startswith(start) and len(low) >= len(start) + rule["shortest_stem"]:
                found[pt] = (way, low[len(start) :])
    return found


def meddra_for_flags(
    release_dir: Path, version: str, entry: dict, ime: str | Path | None
) -> tuple[Meddra, int | None]:
    """What the comparison reads from the licensed part, and how many PTs EMA's list
    holds (None when no list was given)."""
    groups = read_groups(release_dir, version)
    reac = licensed(release_dir, entry, "reac_meddra_T")
    paths = rows(
        "SELECT pt_code, pt_name, hlt_code, hlt_name FROM "
        f"{licensed(release_dir, entry, 'meddra_mdhier')}"
        " WHERE primary_soc_fg = 'Y'"
    )
    important = read_ime(ime, {pt for pt, *_ in paths}) if ime else set()
    severe = _named_with(
        ((pt, name) for pt, name, *_ in paths),
        rulebook.value(UMBRELLA_RULE, "severe_words"),
    )
    umbrellas_on = rulebook.is_on(UMBRELLA_RULE)
    # a PT the not-a-medical-event rule names itself is not a procedure (self-medication)
    named = (
        codes_under(release_dir, entry, rulebook.value(NOT_MEDICAL, "pts"), [])
        if rulebook.is_on(NOT_MEDICAL)
        else set()
    )
    catch_all = {
        name.lower() for name in groups.get(rulebook.value(FLAGS_RULE, "catch_all_key"), [])
    }
    names: dict[str, set[str]] = {}
    for pt, name, *_ in paths:
        names.setdefault(name.lower(), set()).add(pt)
    exact = (
        codes_under(release_dir, entry, rulebook.value(NOT_MEDICAL, "compared_pts"), [])
        if rulebook.is_on(NOT_MEDICAL)
        else set()
    )
    meddra = Meddra(
        reaction_pt=dict(rows(f"SELECT reac_term_T, pt_code_T FROM {reac}")),
        primary_hlt={pt: hlt for pt, _n, hlt, _h in paths},
        # an umbrella PT is named as the singular of its HLT (rule label-umbrella)
        umbrella_hlt={
            pt: hlt
            for pt, name, hlt, hlt_name in paths
            if umbrellas_on and plural(name.lower()) == hlt_name.lower()
        },
        severe=severe | important,
        not_medical=_set_aside(release_dir, entry, NOT_MEDICAL, groups) - exact,
        exact=exact,
        procedures=_set_aside(release_dir, entry, PROCEDURE, groups) - named,
        same_meaning=_pt_pairs(rulebook.value(FLAGS_RULE, "same_meaning"), names),
        direction=_directions((pt, name) for pt, name, *_ in paths),
        catch_all={hlt for _p, _n, hlt, hlt_name in paths if hlt_name.lower() in catch_all},
    )
    return meddra, (len(important) if ime else None)


def flags_schema() -> pa.Schema:
    return pa.schema(
        [(col(c), pa.date32() if c == "label_date" else pa.string()) for c in FLAG_COLUMNS]
    )


def _write(path: Path, flags: Iterable[dict]) -> Counter[str]:
    """Write the flags in batches, so a release's millions never sit in memory at once;
    return how many got each outcome."""
    schema = flags_schema()
    require_suffix(FLAGS, schema.names)
    outcomes: Counter[str] = Counter()
    with pq.ParquetWriter(path, schema, compression="zstd") as out:
        for batch in batched(flags, _BATCH):
            outcomes.update(f["outcome"] for f in batch)
            out.write_table(pa.table({col(c): [f[c] for f in batch] for c in FLAG_COLUMNS}, schema))
        if not outcomes:
            out.write_table(schema.empty_table())
    return outcomes


def _record(release_dir: Path, entry: dict, table: dict | None) -> None:
    """The step's entry in the release's manifest, and the flags table when written."""
    manifest = read_manifest(release_dir)
    if table is not None:
        manifest["tables"][FLAGS] = table
    manifest[STEP] = entry
    (release_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def build_label_flags(
    release_dir: str | Path,
    pairs: Iterable[tuple[str | None, str, str]],
    *,
    ime: str | Path | None = None,
    entry: Mapping | None = None,
) -> dict:
    """Compare (rxcui, route families, reaction text) triples with the coded labels and
    write the public `label_flags_T`, recorded in the release's manifest with `entry` (what
    the caller read the pairs from). `ime` is EMA's Important Medical Events file for the
    version: the umbrella rule never covers a PT on it. Needs build_label_terms first.
    Writes nothing, and says why, when a person switched the coding or the flags off."""
    for rule in (DICTIONARY, FLAGS_RULE):
        if not rulebook.is_on(rule):
            return {"skipped": SWITCHED_OFF.format(rule=rule)}
    release_dir = Path(release_dir).expanduser()
    _, version, held = held_version(release_dir)
    names = ", ".join(col(c) for c in ("set_id", "section", "pt_code", "kept", "decided_by"))
    terms = [
        dict(zip(("set_id", "section", "pt_code", "kept", "decided_by"), r, strict=True))
        for r in rows(f"SELECT {names} FROM {licensed(release_dir, held, TERMS)}")
    ]
    meddra, important = meddra_for_flags(release_dir, version, held, ime)
    comparison = Comparison(labels=_labels(release_dir), terms=terms, meddra=meddra)
    path = f"{PARQUET_DIR}/{FLAGS}.parquet"
    counted = _write(release_dir / path, comparison.flags(pairs))
    done = {
        "present": True,
        "version": version,
        "rows": sum(counted.values()),
        "outcomes": {o: counted[o] for o in rulebook.value(FLAGS_RULE, "outcomes")},
        "important_medical_events": important,
        **(entry or {}),
    }
    table = {
        "path": path,
        "kind": "derived",
        "rows": done["rows"],
        "bytes": (release_dir / path).stat().st_size,
    }
    _record(release_dir, done, table)
    return {**done, "path": str(release_dir / path)}


def build_release_flags(
    release_dir: str | Path,
    *,
    ime: str | Path | None = None,
) -> dict:
    """Flag the reactions of every suspect drug record of a release that is no trial product
    (join.py), by its RxNorm code and route families, and say in the manifest how many
    records met each fate on the way to a label. Without the record tables it needs, it
    writes no flags and says why; without drug_route_T it reads every record on every
    form's label and says so."""
    release_dir = Path(release_dir).expanduser()
    for rule in (DICTIONARY, FLAGS_RULE):
        if not rulebook.is_on(rule):
            return {"skipped": SWITCHED_OFF.format(rule=rule)}
    sc = join.scope(release_dir)
    why = sc.why_not()
    if why is not None:
        _record(release_dir, {"present": False, "reason": why}, None)
        _count(release_dir)
        return {"skipped": why}
    entry = {"suspect_records": join.fates(release_dir, sc), "notes": sc.notes}
    done = build_label_flags(release_dir, join.pairs(release_dir, sc), ime=ime, entry=entry)
    _record_other(release_dir, sc)
    if (release_dir / VIEWS_FILE).exists():  # a staging folder holds no views to read cards from
        refresh_cards(release_dir)  # the cards, the label flags' among them
    _count(release_dir)  # the numbers, so the limits that quote the flags count them
    return done


def _count(release_dir: Path) -> None:
    """The methods page's numbers again, so the limits that quote the flags count them."""
    numbers.write(
        release_dir,
        memory_limit=f"{rulebook.value('explorer-build-memory', 'memory_limit_gb')}GB",
        threads=int(rulebook.value("explorer-build-memory", "threads")),
    )


def _record_other(release_dir: Path, sc: join.Scope) -> None:
    """The suspect records whose code names another drug than the one counted, as a public
    table of the release (join.OTHER_DRUG), which the screens read so they never show the code's
    label for them either."""
    path = f"{PARQUET_DIR}/{join.OTHER_DRUG}.parquet"
    rows = join.write_other(release_dir, sc, release_dir / path)
    manifest = read_manifest(release_dir)
    manifest["tables"][join.OTHER_DRUG] = {
        "path": path,
        "kind": "derived",
        "rows": rows,
        "bytes": (release_dir / path).stat().st_size,
    }
    (release_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
