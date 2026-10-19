"""open-altio serve: the explorer over a release, in the browser, on this machine only.

The explorer listens on 127.0.0.1, so nobody else on the network can reach it, and nothing it
shows needs a sign-in. The container image sets OPEN_ALTIO_HOST because inside a container
127.0.0.1 is the container's own; see the Dockerfile.
"""

from __future__ import annotations

import argparse
import os
import socket
import threading
import time
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from open_altio import paths
from open_altio.explorer.rebuild import settle
from open_altio.faers import EXPLORER_FILE, MANIFEST_FILE, read_manifest
from open_altio.faers.build import Inputs
from open_altio.faers.meddra import (
    ascii_folder,
    build_licensed,
    older_part,
    read_licensed_manifest,
    read_release_file,
)
from open_altio.faers.sources import QUARTER, quarter_key

from .console import Refusal, say

if TYPE_CHECKING:
    import uvicorn

LOOPBACK = "127.0.0.1"
HOST_ENV = "OPEN_ALTIO_HOST"
PORT = 8000
PORTS_TRIED = 20  # when the default port is taken, the next free one of these is used
OPEN_WAIT_SECONDS = 30  # the explorer answers in well under a second

SERVE = """\
Run the explorer over a release folder, in your browser, on this machine only (127.0.0.1).
Without --release it opens the newest release in the current folder, or else the demo's.

MedDRA: if your organisation subscribes to MedDRA, point the explorer at the English release
MSSO sent you, unzipped (the folder that holds MedAscii/). The explorer then shows MedDRA's
hierarchy above the preferred term, the SMQs and their filters. The files are read on this
machine and stay on it; the release keeps what it needs in its licensed/ folder, so later
runs need no --meddra, except to rebuild the release with your rules.

Rebuild with your rules, on the methods page, builds the release again from FDA's files and the
other files it was built with, so the new release holds everything the first one did. Start
the explorer with each of them the release holds: --meddra for MedDRA, --rxnorm for RxNorm's
drug codes (by default $OPEN_ALTIO_RXNORM_DIR, else the data folder's rxnorm/), --labels for
FDA's labels and, when the release flags its reactions against them with EMA's Important
Medical Events, --ime for that file. The groups file and reviewed codings of the label flags
stay in the release. Without a file it needs, the rebuild says which and does not start.
"""


def add(commands: argparse._SubParsersAction) -> None:
    serve = commands.add_parser(
        "serve",
        help="run the explorer on a release you have built",
        description=SERVE,
        epilog=(
            "Examples:\n"
            "  open-altio serve\n"
            "  open-altio serve --release ~/faers/2026Q2 --port 8100\n"
            "  open-altio serve --meddra ~/Downloads/MedDRA_29_1_English\n"
            "  open-altio serve --meddra ~/meddra/MedDRA_29_1_English --labels ~/labels \\\n"
            "      --rxnorm ~/rxnorm --ime ~/meddra/ime_29_1.xlsx"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    serve.add_argument("--release", type=Path, help="a release folder, as the build writes it")
    serve.add_argument(
        "--meddra", type=Path, metavar="FOLDER", help="MedDRA's English release, unzipped"
    )
    serve.add_argument(
        "--rxnorm", type=Path, metavar="FOLDER", help="NLM's RxNorm files, unzipped, for a rebuild"
    )
    serve.add_argument(
        "--labels",
        type=Path,
        metavar="FOLDER",
        help="the labels folder labels-fetch filled, for a rebuild",
    )
    serve.add_argument(
        "--ime",
        type=Path,
        metavar="FILE",
        help="EMA's Important Medical Events file, for a rebuild",
    )
    add_serving_options(serve)
    serve.set_defaults(run=run_serve)


def add_serving_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--port", type=int, help=f"the port on 127.0.0.1 (default {PORT}, or the next free one)"
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="print the explorer's address instead of opening it in a browser",
    )


def run_serve(args: argparse.Namespace) -> int:
    release = args.release or newest_release(Path.cwd())
    _check(release)
    settle(release.parent, read_manifest(release)["release"])
    inputs = Inputs(meddra=args.meddra, rxnorm=args.rxnorm, labels=args.labels, ime=args.ime)
    for given in (inputs.meddra, inputs.rxnorm, inputs.labels, inputs.ime):
        if given is not None and not given.exists():
            raise Refusal(f"{given} is not there. Check the path and start the explorer again.")
    if inputs.meddra:
        add_meddra(release, inputs.meddra)
    serve(release, port=args.port, open_browser=not args.no_open, inputs=inputs)
    return 0


def releases_in(folder: Path) -> list[Path]:
    """The release folders in `folder` (or `folder` itself, if it is one), oldest quarter first."""
    if (folder / MANIFEST_FILE).is_file():
        return [folder]
    found = [
        p.parent for p in folder.glob(f"*/{MANIFEST_FILE}") if QUARTER.fullmatch(p.parent.name)
    ]
    return sorted(found, key=lambda p: quarter_key(p.name.lower()))


def newest_release(here: Path) -> Path:
    for folder in (here, paths.releases_folder()):
        found = releases_in(folder)
        if found:
            return found[-1]
    raise Refusal(
        f"There is no release in {here} or {paths.releases_folder()} yet. Run open-altio demo for "
        "FDA's latest quarter, or open-altio fetch and then open-altio build for all of it."
    )


def _check(release: Path) -> None:
    if not (release / MANIFEST_FILE).is_file():
        raise Refusal(f"{release} is not a release folder: it has no {MANIFEST_FILE}.")
    if not (release / EXPLORER_FILE).is_file():
        raise Refusal(
            f"{release} has no {EXPLORER_FILE} yet. Build it with: "
            f"python -m open_altio.faers explorer {release}"
        )


def add_meddra(release: Path, meddra: Path) -> None:
    """Read the release to the MedDRA version in `meddra`, in its licensed part, unless it holds
    it already. It replaces any other version held: a release has one (rule meddra-version)."""
    version, _language = read_release_file(ascii_folder(meddra))
    held = (read_licensed_manifest(release) or {}).get("meddra", {}).get("versions", {})
    if version in held and not older_part(held[version]):  # an older part is written anew
        say(f"The release has MedDRA {version} already.")
        return
    say(f"Adding MedDRA {version} from {meddra} to the release.")
    build_licensed(release, meddra, overwrite=version in held)


def _free(host: str, port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def choose_port(host: str, asked: int | None) -> int:
    """The port asked for, or the default or the next free one after it."""
    if asked is not None:
        if not _free(host, asked):
            raise Refusal(f"Port {asked} is in use by another program. Choose another with --port.")
        return asked
    for port in range(PORT, PORT + PORTS_TRIED):
        if _free(host, port):
            return port
    raise Refusal(
        f"Ports {PORT} to {PORT + PORTS_TRIED - 1} are all in use. Choose one with --port."
    )


def serve(
    release: Path, *, port: int | None, open_browser: bool, inputs: Inputs | None = None
) -> None:
    # the web server is loaded only here, so the other commands start without it
    import uvicorn

    from open_altio.explorer.app import create_app
    from open_altio.explorer.outbox import Outbox

    host = os.environ.get(HOST_ENV) or LOOPBACK
    chosen = choose_port(host, port)
    url = f"http://{LOOPBACK}:{chosen}"
    name = read_manifest(release)["release"]
    say(f"Open Altio: release {name} at {url} (Ctrl+C stops it)")
    if host != LOOPBACK:
        say(f"Listening on {host}, port {chosen}.")
    server = uvicorn.Server(
        uvicorn.Config(
            # the methods page's Rebuild reads FDA's files from where fetch and demo put them, and
            # the others from the folders given
            create_app(
                release,
                fda_dir=paths.fda_folder(),
                inputs=inputs,
                outbox=Outbox.on_this_machine(),
                warm=True,
            ),
            host=host,
            port=chosen,
            log_level="warning",
        )
    )
    if open_browser:
        threading.Thread(target=_open_when_up, args=(server, url), daemon=True).start()
    server.run()


def _open_when_up(server: uvicorn.Server, url: str) -> None:
    deadline = time.monotonic() + OPEN_WAIT_SECONDS
    while not server.started:
        if time.monotonic() > deadline:
            return
        time.sleep(0.1)
    if not webbrowser.open(url):
        say(f"No browser opened here; open {url} in one.")
