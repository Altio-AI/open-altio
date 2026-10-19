#!/usr/bin/env python3
"""Run the insight notebooks headless, or strip their outputs.

    OPEN_ALTIO_RELEASE=releases/2026Q2 .venv/bin/python scripts/run_nb.py 00_setup_and_inventory
    .venv/bin/python scripts/run_nb.py --strip          # every notebook here, outputs removed

Notebooks run on the interpreter running this script (the repository's .venv, through its
ipykernel) against the release folder $OPEN_ALTIO_RELEASE names (build one with `open-altio demo`
or `open-altio build`), with the package from this working tree. The executed copies, outputs
embedded, go to notebooks/out/notebooks/ (or $OPEN_ALTIO_INSIGHTS_OUT/notebooks); the notebooks
in git carry the outputs of a run, with licensed MedDRA output cleared (notebooks/README.md).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
HERE = REPO / "notebooks" / "faers"
TIMEOUT_SECONDS = 1800  # one cell; notebook 04 builds its working tables in one


def notebooks(names: list[str]) -> list[Path]:
    if not names:
        return sorted(HERE.glob("*.ipynb"))
    return [HERE / (n if n.endswith(".ipynb") else f"{n}.ipynb") for n in names]


def strip(path: Path) -> None:
    nb = nbformat.read(path, as_version=4)
    for cell in nb.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
        cell.metadata.pop("execution", None)
    nbformat.write(nb, path)


def run(path: Path) -> Path:
    from open_altio.faers.insights.cards.notebook import out_dir

    nb = nbformat.read(path, as_version=4)
    started = time.time()
    NotebookClient(
        nb,
        timeout=TIMEOUT_SECONDS,
        kernel_name="python3",
        resources={"metadata": {"path": str(HERE)}},
    ).execute()
    target = out_dir() / "notebooks" / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, target)
    print(f"{path.name} executed in {time.time() - started:.0f}s -> {target}", flush=True)
    return target


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("names", nargs="*", help="notebook names (default: every notebook here)")
    ap.add_argument(
        "--strip", action="store_true", help="remove the notebooks' outputs instead of running them"
    )
    args = ap.parse_args(argv)
    # The working tree's package, here and in each kernel, never an installed copy.
    sys.path.insert(0, str(SRC))
    os.environ["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(SRC), os.environ.get("PYTHONPATH")))
    )
    for path in notebooks(args.names):
        if args.strip:
            strip(path)
        else:
            run(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
