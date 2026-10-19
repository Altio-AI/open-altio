"""The label review: python -m open_altio.labelreview <command> --folder <MedDRA version folder>."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from open_altio import rulebook

from . import (
    batches,
    coding,
    decisions,
    freeze,
    patterns,
    redo,
    rulecheck,
    runner,
    suggest,
)
from .store import Folder, PublicPath, Refused

RULE = "label-review"
COMMANDS = [
    ("batch", "start the next batch; refused while the current one fails a gate"),
    (
        "export",
        "write the batch folder an agent works in: INSTRUCTIONS.md, items.jsonl",
    ),
    ("import", "check and keep the suggestions.jsonl the agent wrote"),
    (
        "run",
        "run your agent command on the batch folder, import, and retry what it left blank",
    ),
    ("status", "the gates for the current batch, and the items decided as other"),
    (
        "patterns",
        "repeated patterns among decided items, as candidates for fixed rules",
    ),
    ("freeze", "write decided items to the frozen file the label step reads"),
    ("review", "open the review page on this machine"),
    ("sample", "draw the rule check's random sample from label_flags_T, once"),
    ("rates", "the rule check's error rate for each outcome"),
    ("redo", "the blind redo: start it once, or report where answers differ"),
]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m open_altio.labelreview", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "definitions", help="print the coding question and its rules as a page to read"
    )
    for name, text in COMMANDS:
        command = commands.add_parser(name, help=text)
        command.add_argument(
            "--folder",
            required=True,
            help="a MedDRA version folder: <release>/licensed/meddra/<version>",
        )
        if name in ("export", "import", "run", "review"):
            command.add_argument(
                "--release",
                type=Path,
                help="the release whose MedDRA part checks terms (default: the one with --folder)",
            )
        if name == "import":
            command.add_argument(
                "--by", required=True, help='the agent and model, e.g. "Codex, gpt-5"'
            )
            command.add_argument(
                "--from",
                dest="source",
                type=Path,
                help="a batch folder, if not the current",
            )
        if name == "run":
            command.add_argument(
                "--agent", required=True, help='your agent command, e.g. "claude -p"'
            )
            command.add_argument(
                "--by", default="", help="the agent and model (default: the command)"
            )
        if name == "review":
            command.add_argument(
                "--reviewer",
                default=getpass.getuser(),
                help="who decides (default: you)",
            )
            command.add_argument("--port", type=int, default=int(rulebook.value(RULE, "page_port")))
        if name == "sample":
            command.add_argument(
                "--flags", required=True, help="the release's label_flags_T Parquet"
            )
        if name == "redo":
            command.add_argument("step", choices=["start", "report"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "definitions":
        print(coding.as_markdown(), end="")
        return 0
    try:
        _run(args, Folder(args.folder))
    except (PublicPath, Refused) as why:
        print(why, file=sys.stderr)
        return 1
    return 0


def _status(folder: Folder) -> None:
    batch = batches.current(folder)
    if batch is None:
        print("No batch yet. Start one with: batch")
        return
    r = batches.check(folder, batch)
    print(
        f"Batch {batch.number}: {r.items} items, {r.decided} decided, {r.other} other "
        f"({r.other_share:.1%}), the agent agreed on {r.agreed} ({r.agreement:.0%}), "
        f"{r.no_answer} without an answer, {r.stale} suggestions not current."
    )
    if r.passed:
        print(f"The next batch may start, with {batches.size_for(batch.number + 1)} items.")
    else:
        print("The next batch may not start yet:")
        for reason in r.reasons:
            print(f"  {reason}")
    others = [
        d for d in decisions.latest(folder).values() if not d.pts and d.none_reason == "other"
    ]
    if others:
        print(f'{len(others)} items coded none for "other", to read for a reason to add or change:')
        for d in others:
            print(f"  {d.item_id}: {d.note}")
    if r.reason_only:
        print(f"{len(r.reason_only)} items where both said none, for other reasons (tidying only):")
        for item_id in r.reason_only:
            print(f"  {item_id}")


def _run(args: argparse.Namespace, folder: Folder) -> None:
    if args.command == "batch":
        batch = batches.start_next(folder)
        print(
            f"Batch {batch.number} started with {len(batch.item_ids)} items. Next: export or run."
        )
    elif args.command == "export":
        out = suggest.export_batch(folder, release=args.release)
        print(
            f'Batch folder: {out}\nTell your agent: "{rulebook.value("label-agent", "prompt")}"'
            '\nThen: import --by "<agent and model>"'
        )
    elif args.command == "import":
        report = suggest.import_suggestions(folder, args.by, args.source, release=args.release)
        print(
            f"Batch {report.batch}: {len(report.answered)} answered, "
            f"{len(report.unanswered)} without an answer (the reviewer decides those)."
        )
    elif args.command == "run":
        done = runner.run(folder, args.agent, args.by, release=args.release)
        print(
            f"Batch {done.batch}: {done.answered} answered in {done.attempts} attempts, "
            f"{len(done.refused)} refused. The log is attempts.jsonl in the batch folder."
        )
    elif args.command == "status":
        _status(folder)
    elif args.command == "patterns":
        found = patterns.repeated(folder)
        print(f"{len(found)} repeated patterns among decided items (a person writes any rule):")
        for p in found:
            print(f"  {p.items} items, {p.drugs} drugs: {p.kind} = {p.value!r} -> {p.coded_as}")
    elif args.command == "freeze":
        print(
            f"{freeze.freeze(folder)} decided items frozen. A build reads them and calls no agent."
        )
    elif args.command == "review":
        import uvicorn

        from .page import create_app

        host = str(rulebook.value(RULE, "page_host"))
        print(
            f"Review page: http://{host}:{args.port}/  (reviewer {args.reviewer}; Ctrl+C stops it)"
        )
        uvicorn.run(
            create_app(folder, args.reviewer, release=args.release),
            host=host,
            port=args.port,
            log_level="warning",
        )
    elif args.command == "sample":
        drawn = rulecheck.draw(folder, args.flags)
        print(f"{len(drawn)} flags drawn for the rule check. Open the review page's Rule check.")
    elif args.command == "rates":
        for r in rulecheck.error_rates(folder):
            line = f"{r.outcome}: {r.wrong} wrong of {r.checked} checked ({r.drawn} drawn)"
            if r.checked:
                line += f", {r.rate:.0%}, likely between {r.low:.0%} and {r.high:.0%}"
            print(line)
    elif args.step == "start":
        print(f"{len(redo.start(folder))} items set for the blind redo; see the page's Blind redo.")
    else:
        result = redo.compare(folder)
        print(f"{result.answered} of {result.items} answered; {len(result.differences)} differ:")
        for d in result.differences:
            print(
                f"  {d.item_id}: first {d.first or d.first_reason}, redo {d.redo or d.redo_reason}"
            )
        print(f"{len(result.reason_only)} none both times, for different reasons:")
        for d in result.reason_only:
            print(f"  {d.item_id}: first {d.first_reason}, redo {d.redo_reason}")


if __name__ == "__main__":
    sys.exit(main())
