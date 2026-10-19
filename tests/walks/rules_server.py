"""The explorer over a fresh fake release, told where its fake FDA files are, for the rules page
walk (rules_page.py). Dev only.

    .venv/bin/python tests/walks/rules_server.py --port <port> --work <empty folder> \\
        [--step-seconds 0.5]

`--step-seconds` holds each step of a rebuild that long, so a walk can see the progress.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import uvicorn

from open_altio.explorer import rebuild
from open_altio.explorer.app import create_app
from open_altio.faers import build_release
from open_altio.testing import fakefda


def slowed(build, seconds: float):
    def build_slowly(*args, progress=None, **kwargs):
        def held(step: str, done: int, total: int) -> None:
            progress(step, done, total)
            time.sleep(seconds)

        return build(*args, progress=held if progress else None, **kwargs)

    return build_slowly


def main() -> None:
    asked = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    asked.add_argument("--port", type=int, required=True)
    asked.add_argument("--work", type=Path, required=True)
    asked.add_argument("--step-seconds", type=float, default=0.0)
    args = asked.parse_args()
    zips = fakefda.write_input(args.work / "zips")
    release = build_release(zips, args.work / "releases")
    if args.step_seconds:
        rebuild.build_release = slowed(rebuild.build_release, args.step_seconds)
    print(f"rules walk explorer on http://127.0.0.1:{args.port} serving {release}", flush=True)
    uvicorn.run(
        create_app(release, fda_dir=zips), host="127.0.0.1", port=args.port, log_level="warning"
    )


if __name__ == "__main__":
    main()
