"""A release's labels kept current between releases, from DailyMed's daily update files, without
building FAERS again (rule label-refresh).

    from open_altio.faers.labels.refresh import refresh_labels
    done = refresh_labels("releases/2026Q2", "~/faers-labels")   # ime= where its flags read it

    python -m open_altio.faers labels-refresh --release RELEASE --labels LABELS [--ime FILE]

1. A switch a crash stopped is finished first (switch.py).
2. Each day's file not applied yet, from the day the labels are as of up to yesterday, is
   fetched into the labels folder (daily.py), and DailyMed's mapping file again.
3. The label tables are made again where a label changed (update.py).
4. Beside the release, in its staging folder, the labels step codes and flags again when a
   label the flags read changed, reading the rest of the release where it is.
5. The new files are switched in, the manifest last (switch.py).
"""

from __future__ import annotations

import dataclasses
import fnmatch
import json
import os
import shutil
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from open_altio import rulebook

from ..labeldict import build_label_terms, build_release_flags
from ..meddra import LICENSED_DIR, MEDDRA_DIR, keep_person_files, read_licensed_manifest
from ..meddra.licensed import LICENSED_MANIFEST, write_licensed_manifest
from ..reader import MANIFEST_FILE, read_manifest
from . import daily, fetch, folder, switch, update
from .build import as_of

RULE = "label-refresh"
SOURCE = "label-source"
STAGING = ".labels-refresh"  # in the release folder: the shadow release, then the switch
NEW_MANIFEST = "release-manifest.json"  # a manifest as it will be, in the staging folder
FLAGS, FLAGS_STEP, TERMS = "label_flags_T", "label_flags", "label_terms_T"
CANDIDATES, SECTIONS = update.CANDIDATES, update.SECTIONS
Moves = list[tuple[str, str]]


class RefreshRefused(Exception):
    """The labels cannot be brought up to date here; the message says why in plain words."""


def refresh_labels(
    release_dir: str | Path,
    labels_dir: str | Path,
    *,
    ime: str | Path | None = None,
    client: httpx.Client | None = None,
    today: date | None = None,
    say: Callable[[str], None] | None = None,
) -> dict:
    """Bring the release's labels up to date with DailyMed's daily files, fetched into
    `labels_dir` (the folder labels-fetch filled), under the rules the release was built with,
    and return what was done. `ime` is EMA's Important Medical Events file, needed when the
    release's flags read it. Raises RefreshRefused, or the error that stopped it, and the
    release keeps the labels it had."""
    release_dir = Path(release_dir).expanduser()
    say = say or (lambda _line: None)
    if switch.finish(release_dir / STAGING, release_dir):
        say("labels: switched in the labels a stopped refresh had built")
    manifest = read_manifest(release_dir)
    if CANDIDATES not in manifest["tables"]:
        raise RefreshRefused(f"{release_dir} holds no labels: build it with its labels first")
    read_ime = (manifest.get(FLAGS_STEP) or {}).get("important_medical_events") is not None
    if read_ime and ime is None:
        raise RefreshRefused(
            "its label flags read EMA's Important Medical Events: give that file with --ime"
        )
    rules = rulebook.from_differences(manifest.get("user_rules") or {})
    with rulebook.use_user_rules(rules), client or fetch.new_client() as http:
        return _refresh(
            release_dir,
            Path(labels_dir).expanduser(),
            manifest,
            Path(ime).expanduser() if read_ime and ime is not None else None,
            http,
            today or datetime.now(UTC).date(),
            say,
        )


def _parts(files: list[dict]) -> list[dict]:
    """The full release's parts among the files a labels entry or folder lists."""
    glob = rulebook.value(SOURCE, "release_file_glob")
    return [f for f in files if fnmatch.fnmatch(f["name"], glob)]


def _refresh(
    release_dir: Path,
    labels_dir: Path,
    manifest: dict,
    ime: Path | None,
    http: httpx.Client,
    today: date,
    say: Callable[[str], None],
) -> dict:
    started = time.monotonic()
    where = folder.find(labels_dir)
    entry = dict(manifest.get("labels") or {})
    same = _parts(where.files()) == _parts(entry.get("files", []))
    held = as_of(manifest) if same else None
    day = date.fromisoformat(held) if held else folder.newest_day(where.parts)
    applied = list(entry.get("daily_files", [])) if same else []
    behind = (today - day).days
    if behind > int(rulebook.value(RULE, "catch_up_days")):
        raise RefreshRefused(
            f"the labels are as of {day}, {behind} days behind DailyMed: fetch the full release "
            "again with labels-fetch, then refresh"
        )
    gone = [date.fromisoformat(a["day"]) for a in applied if not (labels_dir / a["file"]).is_file()]
    if len(daily.fetch_days(http, gone, labels_dir, say)) < len(gone):
        raise RefreshRefused("a daily file these labels were read from is no longer at DailyMed")
    due = daily.due(day, [a["file"] for a in applied], today)
    found = daily.fetch_days(http, due, labels_dir, say)
    if same and not found:
        say(f"labels: up to date, as of {day}")
        return {"release": manifest["release"], "as_of": day.isoformat(), "daily_files": []}

    days = [folder.read_day(labels_dir / a["file"]) for a in applied]
    new_days = [folder.read_day(p) for _, p in found]
    changed = {folder.set_of(m) for d in new_days for m in d.members}
    removed: set[str] = set().union(*(d.removed for d in new_days))
    newest = max([day, *(d for d, _ in found)])
    entry["as_of"] = newest.isoformat()
    entry["daily_files"] = applied + [{"day": d.isoformat(), "file": p.name} for d, p in found]
    record: dict = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "as_of": newest.isoformat(),
        "daily_files": [p.name for _, p in found],
        "full_release_read": not same,
        "labels_changed": len(changed),
        "labels_withdrawn": len(removed),
        "changed": [],
    }
    flagged = bool((manifest.get(FLAGS_STEP) or {}).get("present"))
    staging = release_dir / STAGING
    staging.mkdir()
    try:
        tables: dict[str, dict] = {}
        moves: Moves = []
        step = None
        before = folder.products_by_label(where.mapping)
        mapping = rulebook.value(SOURCE, "release_files_url") + where.mapping.name
        fresh = _fetch_fresh(http, mapping, where.mapping)
        updated = update.update_tables(
            release_dir,
            dataclasses.replace(where, mapping=fresh),
            days + new_days,
            changed,
            removed,
            mapped_before=before,
            everything=not same,
            say=say,
        )
        entry["files"] = [
            f | ({"bytes": fresh.stat().st_size} if f["name"] == where.mapping.name else {})
            for f in where.files()
        ]
        if updated is not None:
            entry |= updated.counts
            record |= {
                "labels_remapped": updated.labels_remapped,
                "labels_read": updated.labels_read,
                "changed": updated.changed,
            }
            tables, moves = _shadow(release_dir, staging, manifest, updated)
            if flagged and updated.changed:
                say(f"labels: {len(updated.changed)} chosen labels changed; coding, flagging again")
                flag_tables, flag_moves, step = _flag_again(release_dir, staging, manifest, ime)
                tables |= flag_tables
                moves += flag_moves
        unflagged = "unchanged" if flagged else "none"
        record["flags"] = "flagged again" if step is not None else unflagged
        record["seconds"] = round(time.monotonic() - started, 1)
        entry["refreshes"] = [*entry.get("refreshes", []), record]
        new = {**manifest, "tables": {**manifest["tables"], **tables}, "labels": entry}
        if step is not None:
            new[FLAGS_STEP] = step
        (staging / NEW_MANIFEST).write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
        switch.switch(staging, release_dir, [*moves, (NEW_MANIFEST, MANIFEST_FILE)])
    except BaseException:
        if not (staging / switch.MOVES).is_file():  # once the switch began, the next one ends it
            shutil.rmtree(staging, ignore_errors=True)
        where.mapping.with_name(f".{where.mapping.name}.fresh").unlink(missing_ok=True)
        raise
    os.replace(fresh, where.mapping)  # the mapping file these labels are now keyed with
    say(f"labels: as of {newest}, {len(record['changed'])} chosen labels changed")
    return {"release": manifest["release"], **record}


def _fetch_fresh(http: httpx.Client, url: str, held: Path) -> Path:
    """The file fetched afresh beside the one held, which it replaces only once the labels are
    switched, so a refresh that fails is compared again with the file the release was read with."""
    size = fetch.size_of(http, url)
    fetch.pause()
    if size is None:
        raise RefreshRefused(f"{url} does not exist")
    fresh = held.with_name(f".{held.name}.fresh")
    fresh.unlink(missing_ok=True)
    fetch.download(http, url, fresh, size)
    fetch.pause()
    return fresh


def _write(table: pa.Table, staging: Path, rel: str) -> dict:
    path = staging / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd")
    return {"path": rel, "kind": "derived", "rows": table.num_rows, "bytes": path.stat().st_size}


def _shadow(
    release_dir: Path, staging: Path, manifest: dict, updated: update.Updated
) -> tuple[dict[str, dict], Moves]:
    """The staging folder made a release of its own: the new label tables, and every other table
    read where it is in the release (one folder up), its licensed part too. Returns the new label
    tables' manifest entries and moves."""
    up = Path(os.pardir)
    shadow = json.loads(json.dumps(manifest))
    for name, held in manifest["tables"].items():
        shadow["tables"][name] = {**held, "path": (up / held["path"]).as_posix()}
    tables, moves = {}, []
    for name, table in ((CANDIDATES, updated.candidates), (SECTIONS, updated.sections)):
        rel = manifest["tables"][name]["path"]
        shadow["tables"][name] = tables[name] = _write(table, staging, rel)
        moves.append((rel, rel))
    for doc in (manifest["funnel"], manifest["methods"]):
        shutil.copy2(release_dir / doc, staging / doc)
    (staging / MANIFEST_FILE).write_text(json.dumps(shadow, indent=2) + "\n", encoding="utf-8")
    licensed = read_licensed_manifest(release_dir)
    if licensed is not None:
        back = up / up / LICENSED_DIR
        for version in licensed["meddra"]["versions"].values():
            for table in version["tables"].values():
                table["path"] = (back / table["path"]).as_posix()
            (staging / LICENSED_DIR / MEDDRA_DIR / version["version"]).mkdir(parents=True)
        write_licensed_manifest(staging, licensed)
        keep_person_files(release_dir, staging)
    return tables, moves


def _flag_again(
    release_dir: Path, staging: Path, manifest: dict, ime: Path | None
) -> tuple[dict[str, dict], Moves, dict]:
    """The labels step run on the staging folder, with the groups file and the reviewed codings
    the release keeps. Returns the flags' manifest entry, the moves, and the step's entry."""
    coded = build_label_terms(staging)
    flagged = build_release_flags(staging, ime=ime)
    for done in (coded, flagged):
        if "skipped" in done:
            raise RefreshRefused(f"the labels step did not run: {done['skipped']}")
    shadow = read_manifest(staging)
    moves: Moves = [
        (shadow["tables"][FLAGS]["path"], manifest["tables"][FLAGS]["path"]),
        (manifest["methods"], manifest["methods"]),
    ]
    licensed = read_licensed_manifest(release_dir) or {}
    ours = licensed["meddra"]["versions"][coded["version"]]
    theirs = (read_licensed_manifest(staging) or {})["meddra"]["versions"][coded["version"]]
    for key in ("tables", "label_uncertain"):
        written = theirs[key][TERMS] if key == "tables" else theirs[key]
        rel = (Path(LICENSED_DIR) / written["path"]).as_posix()
        moves.append((rel, rel))
    ours["tables"][TERMS] = theirs["tables"][TERMS]
    ours["label_uncertain"] = theirs["label_uncertain"]
    staged = Path(LICENSED_DIR) / NEW_MANIFEST
    (staging / staged).write_text(json.dumps(licensed, indent=2) + "\n", encoding="utf-8")
    moves.append((staged.as_posix(), (Path(LICENSED_DIR) / LICENSED_MANIFEST).as_posix()))
    return {FLAGS: shadow["tables"][FLAGS]}, moves, shadow[FLAGS_STEP]
