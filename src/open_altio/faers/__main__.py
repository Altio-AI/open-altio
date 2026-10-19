"""The pipeline's own command, for hosts and for the jobs the `open-altio` command leaves out.

    python -m open_altio.faers build --input DIR --out DIR [--quarter 2026Q2] [--diana FILE]
                                     [--meddra ASCII_DIR] [--rxnorm DIR]
                                     [--labels LABELS_DIR]
    python -m open_altio.faers explorer RELEASE_DIR
    python -m open_altio.faers methods --release RELEASE_DIR
    python -m open_altio.faers companies --release RELEASE_DIR
    python -m open_altio.faers meddra --release RELEASE_DIR --meddra ASCII_DIR
    python -m open_altio.faers meddra --release RELEASE_DIR --held HELD_DIR
    python -m open_altio.faers labels-fetch --into LABELS_DIR
    python -m open_altio.faers atc-table [--who WHO_DIR] [--out CSV]
    python -m open_altio.faers labels --release RELEASE_DIR [--groups FILE] [--codings FILE]
                                      [--ranks FILE] [--ime FILE]
    python -m open_altio.faers labels-refresh --release RELEASE_DIR --labels LABELS_DIR [--ime FILE]
    python -m open_altio.faers statistics --release RELEASE_DIR --reactions as-published
    python -m open_altio.faers class-statistics --release RELEASE_DIR

A person builds with `open-altio build`, from the FDA files in the data folder. `build` here takes
any input and output folders and DuckDB's limits, and a host that publishes releases runs its own
refusals through it with `main(checks=...)`. Both read the rules.toml in the folder they run in.
`--diana` names the DiAna dictionary the drug-name step reads (rule drug-names), by default the
file $OPEN_ALTIO_DIANA_DICTIONARY names; without one the release has no drug ingredients.
`--meddra` names a MedDRA release to read FDA's MedDRA terms to, into the release's licensed part.
`--rxnorm` names the folder NLM's RxNorm zip unpacks to (rule rxnorm-ingredients), by default the
folder $OPEN_ALTIO_RXNORM_DIR names; without one the release has no RxNorm codes.
`--labels` names a folder `labels-fetch` filled with FDA's prescription labels and RxNorm; with it
the release carries the label tables (rules label-source, label-choice and label-sections).
`explorer` rebuilds a release's explorer database; `methods` computes a built release's methods
page cards again on its own tables, fills "What we do not do" and adds the numbers the page
shows and every rule's version, to its methods.json and licensed part, as the build does last,
under the explorer build's memory (rule explorer-build-memory); `companies` puts the
company table in a built release, company_T in its Parquet and its explorer database, as a build
with the table writes them (rule company-names): safe to run again, and needing no rebuild; then
`methods` records the rule's version, and a running explorer restarts to read it. `meddra` reads a
built release to one MedDRA version, replacing the one it held (rule meddra-version), from MedDRA's
files or the newest of the versions a host holds. `labels` codes the release's FDA labels into its
MedDRA version, in the licensed part, then flags each suspect drug's reactions (rules
label-dictionary and label-flags), under the rules.toml in the folder it runs in, as `build` is.
`labels-refresh` brings a release's labels up to date with DailyMed's daily update files,
fetched into the labels folder, and flags again where a label changed, under the rules the
release was built with (rule label-refresh).
`atc-table` builds our drug-to-class table from WHO's ATC index, in the folder `--who` or
$OPEN_ALTIO_WHO_DIR names.
`statistics --reactions as-published` adds to a release built with MedDRA, before its build
counted them so, the statistics counted by FDA's text, by the build's own step
(statistics.add_as_published): safe to run again, and needing no rebuild.
`class-statistics` adds the statistics of each WHO class to a built release (rule
statistics-classes), as a full build writes them, under the rules.toml in the folder it runs in.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from open_altio import rulebook
from open_altio.paths import RXNORM_ENV as RXNORM_DIR_ENV
from open_altio.rulebook import FILE_NAME, UserRules, UserRulesError, differences, use_user_rules

from .atc.table import TableRefused, build_table
from .atc.whofile import WhoRefused
from .build import user_rules_beside
from .companies import apply_company_table
from .drugnames.dictionary import DIANA_ENV
from .explorer_db import build_explorer_db
from .insights import numbers
from .insights.methods import refresh_cards
from .labels.folder import LabelsFolderError
from .meddra import MeddraRefused, add_held, build_licensed, report_lines
from .release import Check, ReleaseError, build_release
from .sources import SourceError
from .statistics import add_as_published, add_classes

WHO_DIR_ENV = "OPEN_ALTIO_WHO_DIR"


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m open_altio.faers", description="Open Altio pipeline"
    )
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build a release folder from FDA quarterly zips or folders")
    b.add_argument(
        "--input",
        required=True,
        help="folder of FDA quarterly zips and/or extracted quarter folders",
    )
    b.add_argument("--out", required=True, help="folder the release folder is written into")
    b.add_argument(
        "--quarter", default=None, help="release quarter, e.g. 2026Q2; later inputs are ignored"
    )
    b.add_argument("--overwrite", action="store_true", help="replace a release of the same name")
    b.add_argument("--threads", type=int, default=None, help="DuckDB worker threads")
    b.add_argument(
        "--memory-limit",
        default=None,
        help="DuckDB memory limit, e.g. 16GB (default: DuckDB's, 80%% of RAM)",
    )
    b.add_argument(
        "--temp-directory", default=None, help="where DuckDB spills when over the memory limit"
    )
    b.add_argument(
        "--diana",
        default=os.environ.get(DIANA_ENV),
        help=f"the DiAna dictionary, downloaded there if missing (default ${DIANA_ENV})",
    )
    b.add_argument(
        "--meddra",
        default=None,
        help="MedDRA's English ASCII release (holding MedAscii/), for the licensed part",
    )
    b.add_argument(
        "--rxnorm",
        default=os.environ.get(RXNORM_DIR_ENV),
        help=f"the folder NLM's RxNorm zip unpacks to (default ${RXNORM_DIR_ENV})",
    )
    b.add_argument("--labels", default=None, help="folder from labels-fetch; adds the label tables")
    e = sub.add_parser(
        "explorer", help="(re)build the explorer database of an existing release folder"
    )
    e.add_argument("release", help="the release folder, e.g. releases/2026Q2")
    n = sub.add_parser(
        "methods",
        help="refill the limits, add the methods page's numbers and every rule's version",
    )
    n.add_argument("--release", required=True, help="the release folder, e.g. releases/2026Q2")
    co = sub.add_parser(
        "companies", help="put the company table in a built release, with no rebuild"
    )
    co.add_argument("--release", required=True, help="the release folder, e.g. releases/2026Q2")
    m = sub.add_parser(
        "meddra", help="read a release to a MedDRA version, in its licensed part (licensed/)"
    )
    m.add_argument("--release", required=True, help="the release folder, e.g. releases/2026Q2")
    given = m.add_mutually_exclusive_group(required=True)
    given.add_argument("--meddra", help="MedDRA's English ASCII release folder (holding MedAscii/)")
    given.add_argument(
        "--held",
        help="a folder of MedDRA versions a host holds, each as <version>/MedAscii/: the newest",
    )
    m.add_argument(
        "--released",
        default=None,
        help="the MedDRA release date, if not the usual 1 March / 1 September",
    )
    m.add_argument("--overwrite", action="store_true", help="replace a MedDRA version already held")
    f = sub.add_parser("labels-fetch", help="download what the labels step reads")
    f.add_argument("--into", required=True, help="the labels folder, outside the repository")
    w = sub.add_parser("atc-table", help="build the drug-to-class table from WHO's ATC index")
    w.add_argument(
        "--who",
        default=os.environ.get(WHO_DIR_ENV),
        help=f"the folder holding WHO's index (default ${WHO_DIR_ENV})",
    )
    w.add_argument(
        "--out",
        default=None,
        help="where to write the table (default: the file rule atc-index names)",
    )
    lab = sub.add_parser("labels", help="code a release's labels to its MedDRA, then flag them")
    lab.add_argument("--release", required=True, help="the release folder, labels and MedDRA in")
    lab.add_argument("--codings", default=None, help="frozen codings of uncertain items")
    lab.add_argument("--ranks", default=None, help="a Parquet of rxcui, pt, rank: each item's rank")
    lab.add_argument("--ime", default=None, help="EMA's Important Medical Events file")
    lab.add_argument(
        "--groups", default=None, help="your MedDRA groups file (rule label-groups), checked first"
    )
    r = sub.add_parser("labels-refresh", help="bring a release's labels up to date with DailyMed")
    r.add_argument("--release", required=True, help="the release folder, e.g. releases/2026Q2")
    r.add_argument("--labels", required=True, help="the folder labels-fetch filled")
    r.add_argument(
        "--ime", default=None, help="EMA's Important Medical Events file, if it read one"
    )
    st = sub.add_parser("statistics", help="add statistics to a built release, from its own tables")
    st.add_argument("--release", required=True, help="the release folder, e.g. releases/2026Q2")
    st.add_argument(
        "--reactions",
        required=True,
        choices=["as-published"],
        help="as-published: the set counted by FDA's text, in a release counted by current PT",
    )
    cs = sub.add_parser(
        "class-statistics", help="add the statistics of each WHO class to a built release"
    )
    cs.add_argument("--release", required=True, help="the release folder, e.g. releases/2026Q2")
    return ap


def _labels_refresh(args: argparse.Namespace) -> int:
    import httpx

    from .labeldict import LabelRefused
    from .labels.refresh import RefreshRefused, refresh_labels

    try:
        done = refresh_labels(
            args.release, args.labels, ime=args.ime, say=lambda line: print(line, flush=True)
        )
    except (RefreshRefused, LabelRefused, LabelsFolderError, OSError, httpx.HTTPError) as exc:
        print(f"refused: {exc}; the release keeps the labels it had", file=sys.stderr)
        return 2
    print(json.dumps(done, indent=2))
    return 0


def _statistics(args: argparse.Namespace) -> int:
    entry = add_as_published(args.release)
    if entry is None:
        print(f"{args.release}: its statistics are counted by FDA's text already, or it has none")
        return 0
    counted, seconds = entry["counted"], entry["seconds"]["total"]
    print(
        f"{args.release}: {entry['table']} and {entry['ror_strata']['table']} written, "
        f"{counted['pairs']} pairs over {counted['reactions']} reactions, in {seconds} s"
    )
    return 0


def _class_statistics(args: argparse.Namespace) -> int:
    try:
        rules = user_rules_beside(Path.cwd()) or UserRules()  # as the build reads them
        with use_user_rules(rules):
            entry = add_classes(args.release)
    except UserRulesError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if not entry["present"]:
        print(f"no class statistics: {entry['reason']}")
        return 0
    for level in entry["levels"]:
        fit = "fitted" if level["ebgm"]["fitted"] else "not fitted"
        print(
            f"level {level['level']}, {level['name']}: {level['classes']} classes, "
            f"{level['pairs']} pairs, EBGM {fit}"
        )
    print(f"{entry['seconds']['total']} seconds: {args.release}")
    return 0


def _labels_fetch(args: argparse.Namespace) -> int:
    import httpx

    from .labels.fetch import fetch

    try:
        paths = fetch(args.into, say=lambda line: print(line, flush=True))
    except (OSError, httpx.HTTPError) as exc:  # a run again carries on where it stopped
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{len(paths)} files in {args.into}")
    return 0


def _atc_table(args: argparse.Namespace) -> int:
    if not args.who:
        print(
            f"refused: give --who or set {WHO_DIR_ENV} to the folder holding WHO's index",
            file=sys.stderr,
        )
        return 2
    try:
        summary = build_table(args.who, args.out)
    except (TableRefused, WhoRefused) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


def _labels(args: argparse.Namespace) -> int:
    import duckdb

    from .labeldict import LabelRefused, build_label_terms, build_release_flags
    from .labeldict.groups import install_groups

    try:
        rules = user_rules_beside(Path.cwd()) or UserRules()  # as the build reads them
        with use_user_rules(rules):
            groups = install_groups(args.release, args.groups) if args.groups else None
            ranks = []
            if args.ranks:
                sql = "SELECT rxcui, pt, rank FROM read_parquet(?)"
                ranks = duckdb.execute(sql, [args.ranks]).fetchall()
            coded = build_label_terms(args.release, codings=args.codings, ranks=ranks)
            flagged = build_release_flags(args.release, ime=args.ime)
    except (LabelRefused, UserRulesError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"groups": groups, "coded": coded, "flags": flagged}, indent=2))
    return 0


def _meddra(args: argparse.Namespace) -> int:
    try:
        if args.held:
            built = add_held(args.release, args.held)
        else:
            released = date.fromisoformat(args.released) if args.released else None
            entry = build_licensed(
                args.release, args.meddra, overwrite=args.overwrite, released=released
            )
    except MeddraRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if args.held:
        print(
            f"MedDRA {built[0]} read in: {args.release}/licensed"
            if built
            else f"{args.release} already has the newest held MedDRA version, or none is held"
        )
    else:
        for line in report_lines(entry["version"], entry["terms"]):
            print(line)
        print(f"MedDRA {entry['version']} released {entry['released']}: {args.release}/licensed")
    return 0


def _build(args: argparse.Namespace, checks: tuple[Check, ...]) -> int:
    try:
        rules = user_rules_beside(Path.cwd())
        if rules is not None:
            recorded = differences(rules)
            if recorded["off"] or recorded["changed"]:
                off, changed = len(recorded["off"]), len(recorded["changed"])
                print(f"your rules ({FILE_NAME}): {off} off, {changed} changed")
        path = build_release(
            args.input,
            args.out,
            quarter=args.quarter,
            overwrite=args.overwrite,
            threads=args.threads,
            memory_limit=args.memory_limit,
            temp_directory=args.temp_directory,
            diana_dictionary=args.diana,
            meddra_dir=args.meddra,
            rxnorm_dir=args.rxnorm,
            labels=args.labels,
            say=lambda line: print(line, flush=True),
            checks=checks,
            user_rules=rules,
        )
    except (SourceError, ReleaseError, UserRulesError, LabelsFolderError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0


def main(argv: list[str] | None = None, checks: tuple[Check, ...] = ()) -> int:
    """The command; `checks` are a caller's own, run before the build's (build_release)."""
    args = _parser().parse_args(argv)
    if args.command == "labels-fetch":
        return _labels_fetch(args)
    if args.command == "meddra":
        return _meddra(args)
    if args.command == "atc-table":
        return _atc_table(args)
    if args.command == "labels":
        return _labels(args)
    if args.command == "labels-refresh":
        return _labels_refresh(args)
    if args.command == "statistics":
        return _statistics(args)
    if args.command == "methods":
        refresh_cards(
            args.release,
            memory_limit=f"{rulebook.value('explorer-build-memory', 'memory_limit_gb')}GB",
            threads=int(rulebook.value("explorer-build-memory", "threads")),
        )
        numbers.write(
            args.release,
            memory_limit=f"{rulebook.value('explorer-build-memory', 'memory_limit_gb')}GB",
            threads=int(rulebook.value("explorer-build-memory", "threads")),
        )
        print(
            f"{args.release}/methods.json: its cards, the story's numbers and every rule's version"
        )
        return 0
    if args.command == "class-statistics":
        return _class_statistics(args)
    if args.command == "companies":
        done = apply_company_table(args.release)
        rows = ", ".join(f"{n} rows of {t}" for t, n in done["changed"].items())
        print(f"{args.release}: company_T changed in {rows}, in {done['seconds']} s")
        return 0
    if args.command == "explorer":
        entry = build_explorer_db(args.release)
        print(f"{args.release}/{entry['file']} {entry['bytes']} bytes")
        return 0
    return _build(args, checks)


if __name__ == "__main__":
    sys.exit(main())
