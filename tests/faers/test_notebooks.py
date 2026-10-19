"""The insight notebooks run headless from the repository against a release built by the
command line, and are committed with the outputs of a run, in a shape a reader can run.

Running them is slow: each needs a release folder ($OPEN_ALTIO_RELEASE) and takes under a minute;
run with `uv run pytest -m slow tests/faers`. Notebook 02 also needs the release built with its
rules off ($OPEN_ALTIO_BEFORE) and FDA's zips ($OPEN_ALTIO_ZIPS); notebook 03 needs a release
built from every quarter and takes about twenty minutes; notebook 06 MedDRA's English ASCII
release ($OPEN_ALTIO_MEDDRA), and about five minutes; notebook 08 ICH's code lists
($OPEN_ALTIO_E2B_CODE_LISTS), DiAna's lookups ($OPEN_ALTIO_DIANA_LOOKUPS) and the dose form check
($OPEN_ALTIO_DOSE_FORM_CHECK). The checks on the
committed notebooks themselves are fast.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import nbformat
import pytest

from open_altio.faers.fda import FIRST_QUARTER
from open_altio.faers.insights.source import RELEASE_ENV, release_folder
from open_altio.faers.reader import read_manifest

# Column names that only a table of MedDRA's hierarchy, or of its codes, carries.
MEDDRA_HIERARCHY = re.compile(r"\b(?:llt|hlt|hlgt|soc|smq)_(?:code|name)\b", re.IGNORECASE)

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run_nb.py"
NOTEBOOKS = sorted((ROOT / "notebooks" / "faers").glob("*.ipynb"))


def _release(setting: str) -> Path | None:
    try:
        return release_folder(None, setting)
    except FileNotFoundError:
        return None


needs_release = pytest.mark.skipif(
    _release(RELEASE_ENV) is None, reason=f"set {RELEASE_ENV} to a release folder"
)


@pytest.fixture
def run_notebook(tmp_path) -> Callable[[str], nbformat.NotebookNode]:
    """Run one notebook through scripts/run_nb.py into tmp_path; the executed copy, checked to
    hold no error."""

    def run(name: str) -> nbformat.NotebookNode:
        done = subprocess.run(
            [sys.executable, str(RUNNER), name],
            capture_output=True,
            text=True,
            env={**os.environ, "OPEN_ALTIO_INSIGHTS_OUT": str(tmp_path)},
        )
        assert done.returncode == 0, done.stdout + done.stderr
        executed = nbformat.read(tmp_path / "notebooks" / f"{name}.ipynb", as_version=4)
        code = [c for c in executed.cells if c.cell_type == "code"]
        assert [o for c in code for o in c.outputs if o.output_type == "error"] == []
        return executed

    return run


@pytest.mark.slow
@needs_release
@pytest.mark.parametrize("name", ["00_setup_and_inventory", "01_volume_over_time", "90_questions"])
def test_notebook_runs_headless_and_writes_its_cards(name, run_notebook, tmp_path):
    run_notebook(name)
    assert (tmp_path / "cards" / f"{name}.json").is_file()


@pytest.mark.slow
@needs_release
@pytest.mark.skipif(
    _release("OPEN_ALTIO_BEFORE") is None or not os.environ.get("OPEN_ALTIO_ZIPS"),
    reason="set OPEN_ALTIO_BEFORE to the release built with notebook 02's rules off, "
    "and OPEN_ALTIO_ZIPS to FDA's zips",
)
def test_the_case_versions_notebook_draws_a_chart_in_every_analysis_cell(run_notebook):
    executed = run_notebook("02_case_versions")
    analysis = [c for c in executed.cells if c.cell_type == "code"][1:]  # after the setup cell
    assert all(any("image/png" in o.get("data", {}) for o in c.outputs) for c in analysis)


def _from_every_quarter(folder: Path | None) -> bool:
    """A release built from FDA's first quarter on, as notebook 03's breaks over time need."""
    return folder is not None and FIRST_QUARTER in read_manifest(folder)["quarters"]


@pytest.mark.slow
@pytest.mark.skipif(
    not _from_every_quarter(_release(RELEASE_ENV)),
    reason=f"set {RELEASE_ENV} to a release built from every quarter",
)
def test_the_empty_fields_notebook_draws_a_chart_in_every_analysis_cell(run_notebook):
    executed = run_notebook("03_empty_fields")
    analysis = [c for c in executed.cells if c.cell_type == "code"][1:]  # after the setup cell
    assert all(any("image/png" in o.get("data", {}) for o in c.outputs) for c in analysis)


def _meddra() -> Path | None:
    """MedDRA's English ASCII release, unzipped ($OPEN_ALTIO_MEDDRA). MedDRA is licensed, so the
    test that needs it skips without it."""
    value = os.environ.get("OPEN_ALTIO_MEDDRA")
    folder = Path(value).expanduser() if value else None
    return folder if folder and any(folder.glob("**/llt.asc")) else None


@pytest.mark.slow
@needs_release
@pytest.mark.skipif(_meddra() is None, reason="set OPEN_ALTIO_MEDDRA to MedDRA's ASCII release")
def test_the_meddra_notebook_runs_headless_and_its_git_copy_names_no_meddra_term(
    run_notebook, tmp_path
):
    executed = run_notebook("06_meddra_versions")
    assert (tmp_path / "cards" / "06_meddra_versions.json").is_file()
    code = [c for c in executed.cells if c.cell_type == "code"][1:]  # after the setup cell
    charted = [any("image/png" in o.get("data", {}) for o in c.outputs) for c in code]
    assert sum(charted) >= len(code) - 2  # two cells only write prose that quotes the run's numbers
    # MedDRA is licensed: the copy in git names no MedDRA term, current or former, of two words or
    # more
    words = re.compile(r"[a-z0-9]+")
    committed = nbformat.read(ROOT / "notebooks" / "faers" / "06_meddra_versions.ipynb", 4)
    text = " " + " ".join(words.findall(" ".join(c.source for c in committed.cells).lower())) + " "
    folder = _meddra()
    assert folder is not None
    names = set()
    for name in ("llt.asc", "meddra_history_english.asc"):
        for line in next(folder.glob(f"**/{name}")).open(encoding="latin-1"):
            names.add(" ".join(words.findall(line.split("$")[1].lower())))
    assert [n for n in names if " " in n and f" {n} " in text] == []


@pytest.mark.slow
@needs_release
def test_the_demographics_notebook_draws_a_chart_in_every_analysis_cell(run_notebook):
    executed = run_notebook("07_demographics_units")
    analysis = [c for c in executed.cells if c.cell_type == "code"][1:]  # after the setup cell
    assert all(any("image/png" in o.get("data", {}) for o in c.outputs) for c in analysis)


@pytest.mark.slow
@needs_release
@pytest.mark.skipif(
    not all(
        os.environ.get(name)
        for name in (
            "OPEN_ALTIO_E2B_CODE_LISTS",
            "OPEN_ALTIO_DIANA_LOOKUPS",
            "OPEN_ALTIO_DOSE_FORM_CHECK",
        )
    ),
    reason="set OPEN_ALTIO_E2B_CODE_LISTS to ICH's code list folder, OPEN_ALTIO_DIANA_LOOKUPS to "
    "DiAna's lookup tables and OPEN_ALTIO_DOSE_FORM_CHECK to the dose form check (notebook 08's "
    "first cell says what each is)",
)
def test_the_dates_and_codes_notebook_draws_a_chart_in_every_analysis_cell(run_notebook):
    executed = run_notebook("08_dates_and_codes")
    analysis = [c for c in executed.cells if c.cell_type == "code"][1:]  # after the setup cell
    assert all(any("image/png" in o.get("data", {}) for o in c.outputs) for c in analysis)


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
def test_notebooks_in_git_carry_no_licensed_meddra_output(path):
    nb = nbformat.read(path, as_version=4)
    for cell in nb.cells:
        for out in cell.get("outputs", []):
            text = str(out.get("text", "")) + "".join(
                str(out.get("data", {}).get(k, "")) for k in ("text/plain", "text/html")
            )
            assert not MEDDRA_HIERARCHY.search(text), f"{path.name}: an output shows MedDRA content"


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
def test_each_notebook_says_how_to_get_a_release_and_names_the_one_it_reads(path):
    nb = nbformat.read(path, as_version=4)
    intro = nb.cells[0]
    first_code = next(c.source for c in nb.cells if c.cell_type == "code")
    assert intro.cell_type == "markdown"
    for text in (intro.source, first_code):
        assert "open-altio demo" in text and "open-altio build" in text
    assert re.search(r"^RELEASE = None\b", first_code, re.M)
