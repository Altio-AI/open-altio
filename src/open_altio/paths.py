"""Where Open Altio keeps its files on this machine, for the command and the explorer alike.

One data folder holds what Open Altio keeps for the person using it: FDA's quarterly files
(`fda/`), the releases the demo builds (`releases/`) and the small files the command and the
explorer keep between runs. It is the platform's own place for an application's data, never a
documents folder. OPEN_ALTIO_DATA_DIR moves the whole folder; OPEN_ALTIO_FDA_DIR moves only
FDA's files, and OPEN_ALTIO_RXNORM_DIR only NLM's RxNorm files (`rxnorm/`), for someone who
keeps them elsewhere already.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DATA_ENV = "OPEN_ALTIO_DATA_DIR"
FDA_ENV = "OPEN_ALTIO_FDA_DIR"
RXNORM_ENV = "OPEN_ALTIO_RXNORM_DIR"
NAME = "open-altio"


def _platform_data_folder() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def data_folder() -> Path:
    """The data folder: $OPEN_ALTIO_DATA_DIR, else open-altio in the platform's data folder."""
    chosen = os.environ.get(DATA_ENV)
    return Path(chosen).expanduser() if chosen else _platform_data_folder() / NAME


def fda_folder() -> Path:
    """Where FDA's quarterly zips are downloaded to and read from."""
    fda = os.environ.get(FDA_ENV)
    return Path(fda).expanduser() if fda else data_folder() / "fda"


def rxnorm_folder() -> Path:
    """Where NLM's RxNorm Current Prescribable Content is unpacked, for the drug codes."""
    rxnorm = os.environ.get(RXNORM_ENV)
    return Path(rxnorm).expanduser() if rxnorm else data_folder() / "rxnorm"


def releases_folder() -> Path:
    """Where the demo release is built."""
    return data_folder() / "releases"
