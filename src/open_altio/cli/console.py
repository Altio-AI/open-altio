"""How the command talks to the person running it: plain lines, progress, sizes and one question."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from open_altio.faers import read_manifest
from open_altio.faers.fda import OnBytes
from open_altio.faers.release import FUNNEL_FILE, Progress


class Refusal(Exception):
    """What was asked cannot be done here; the message says why and what to do instead."""


def say(text: str = "") -> None:
    print(text, flush=True)


def megabytes(n: int) -> str:
    return f"{n / 1e6:,.0f} MB"


def disk_size(n: int) -> str:
    return f"{n / 1e12:,.1f} TB" if n >= 1e12 else f"{n / 1e9:,.1f} GB"


def memory(n: int) -> str:
    """Memory as the operating system shows it: in GB of 1024 MB."""
    return f"{n / 2**30:,.1f} GB"


def duration(seconds: float) -> str:
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


def count(n: int, thing: str) -> str:
    return f"{n:,} {thing}{'' if n == 1 else 's'}"


def about(manifest: dict) -> str:
    """A release in a few words: '2026Q2, 1 quarter, built by open-altio 1.0.0'."""
    quarters = count(len(manifest["quarters"]), "quarter")
    return f"{manifest['release']}, {quarters}, built by open-altio {manifest['code_version']}"


def download_bar(label: str) -> OnBytes:
    """One line per file: redrawn as bytes arrive in a terminal, else written once at the end."""
    redraw = sys.stdout.isatty()

    def show(done: int, total: int) -> None:
        if redraw:
            end = "\n" if done >= total else ""
            print(f"\r  {label}  {megabytes(done)} of {megabytes(total)}", end=end, flush=True)
        elif done >= total:
            say(f"  {label}  {megabytes(total)}")

    return show


def build_steps() -> Progress:
    def show(title: str, done: int, total: int) -> None:
        if done < total:
            say(f"  [{done + 1}/{total}] {title}")

    return show


def built(release: Path) -> None:
    """The finished build in one line, from what the release records about itself."""
    manifest = read_manifest(release)
    funnel = json.loads((release / FUNNEL_FILE).read_text(encoding="utf-8"))
    cases = funnel["steps"][-1]["count"]["total"]
    say(
        f"Built {manifest['release']} in {duration(manifest['build_seconds'])}, "
        f"peak memory {memory(manifest['peak_rss_bytes'])}: {cases:,} cases in {release}"
    )


def ask(question: str) -> bool:
    """Yes or no from the person at the keyboard; no when nobody is there to answer."""
    if not sys.stdin.isatty():
        return False
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False
