"""The one build every caller runs: `open-altio build`, `open-altio demo` and the explorer's
"Rebuild with your rules".

    from open_altio.faers.build import Inputs, build_release
    build_release(fda_dir, ".", user_rules=rules, progress=show)  # -> ./2026Q2
    build_release(fda_dir, ".", inputs=Inputs(meddra=ascii, labels=fetched))  # and their layers

It is the pipeline's build held to the build memory rule (rules/explorer-build-memory.md), so a
laptop with 16 GB builds every quarter, spilling to disk past the limit rather than failing. It
replaces a release of the same name; the old one stays in place until the new one is whole.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from open_altio import paths, rulebook
from open_altio.rulebook import UserRules

from . import release
from .drugnames import dictionary
from .release import Progress


@dataclass(frozen=True)
class Inputs:
    """What a release is built from besides FDA's files and the rules: the person's own copies
    of others' files, read on this machine. Each gives the release a layer; without it the
    release has none.

    meddra  MedDRA's English release, unzipped (the folder holding MedAscii/): the licensed part
    rxnorm  NLM's RxNorm files, unzipped: the drug codes. By default the folder
            OPEN_ALTIO_RXNORM_DIR names, else the data folder's rxnorm/, when it is there
    labels  the folder `python -m open_altio.faers labels-fetch` filled: FDA's labels
    ime     EMA's Important Medical Events file, which the labels step reads after the build
    """

    meddra: Path | None = None
    rxnorm: Path | None = None
    labels: Path | None = None
    ime: Path | None = None

    def rxnorm_folder(self) -> Path | None:
        """The RxNorm folder a build reads: the one given, else the default when it is there."""
        if self.rxnorm is not None:
            return self.rxnorm
        default = paths.rxnorm_folder()
        return default if default.is_dir() else None


def build_release(
    input_dir: str | Path,
    out_dir: str | Path,
    *,
    user_rules: UserRules | None = None,
    quarters: Sequence[str] | None = None,
    progress: Progress | None = None,
    inputs: Inputs | None = None,
) -> Path:
    """Build a release from FDA's files in `input_dir` into `out_dir/<latest quarter>/`, from
    every quarter there or from exactly `quarters`, under the user's rules when given, with the
    layers `inputs` give it."""
    inputs = inputs or Inputs()
    memory = rulebook.value("explorer-build-memory", "memory_limit_gb")
    threads = rulebook.value("explorer-build-memory", "threads")
    return release.build_release(
        input_dir,
        out_dir,
        quarters=quarters,
        overwrite=True,
        memory_limit=f"{memory}GB",
        threads=threads,
        progress=progress,
        user_rules=user_rules,
        diana_dictionary=dictionary.held(),
        meddra_dir=inputs.meddra,
        rxnorm_dir=inputs.rxnorm_folder(),
        labels=inputs.labels,
    )


def user_rules_beside(folder: Path) -> UserRules | None:
    """The user's rules.toml in `folder`, or None when there is none. Raises
    rulebook.UserRulesError, in plain words, for a file that cannot be read."""
    path = folder / rulebook.FILE_NAME
    return rulebook.load_user_rules(path) if path.is_file() else None
