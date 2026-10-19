"""Rebuilding the release with the rules saved beside it: in the background, one at a time,
saying how far it is, beside the release the explorer has open, and the explorer answering from
the new release when it is done."""

from __future__ import annotations

import errno
import json
import os
import shutil
import threading
import time
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from open_altio import rulebook
from open_altio.explorer import rebuild as rebuild_module
from open_altio.explorer.context import explorer_of
from open_altio.explorer.rebuild import POINTER, REBUILT, STANDARD_METHODS, settle
from open_altio.explorer.release import OpenRelease
from open_altio.faers.build import Inputs
from open_altio.faers.drugnames.dictionary import DIANA_ENV
from open_altio.faers.explorer_db import ExplorerBuildError
from open_altio.faers.labeldict import build_label_terms, build_release_flags
from open_altio.faers.labeldict.groups import install_groups
from open_altio.faers.meddra import LABEL_GROUPS_FILE, licensed_dir, read_licensed_manifest
from open_altio.faers.release import build_release
from open_altio.rulebook import UserRules
from open_altio.testing import fakediana
from open_altio.testing.browser import open_page, served
from open_altio.testing.browser import settle as drawn
from open_altio.testing.fakelabels import write_labels
from open_altio.testing.fakelabeltables import write_ime_workbook
from open_altio.testing.fakemeddra import write_meddra
from open_altio.testing.fakerxnorm import write_rxnorm

SPILL = rulebook.value("explorer-build-memory", "spill_limit_gb")
MEMORY = rulebook.value("explorer-build-memory", "memory_limit_gb")
OFF_AND_CHANGED = {
    "off": ["deleted-cases"],
    "changed": [{"rule": "dup-manufacturer-number", "key": "max_age_gap_years", "value": 5}],
}


def follow(client, until: str = "done", seconds: float = 60) -> dict:
    """The rebuild's state, asked again until it reaches `until` (or fails)."""
    end = time.monotonic() + seconds
    while True:
        state = client.get("/api/rules/rebuild").json()
        if state["state"] in (until, "failed") or time.monotonic() > end:
            return state
        time.sleep(0.05)


GROUPS = {"not_a_medical_event": [], "procedure": ["Invented investigations"], "catch_all": []}
CODED_CASE = "/api/labels/case/faers/9001001"  # its aspirin has an RxNorm code and a flag


class HeldBuild:
    """A build that says how far it is, then waits until the test lets it finish; it writes
    a copy of `source` with the choices recorded, as the release build does."""

    def __init__(self, source: Path) -> None:
        self.source = source
        self.go = threading.Event()
        self.said = threading.Event()
        self.asked: dict = {}

    def __call__(
        self, input_dir, out_dir, *, user_rules=None, quarters=None, progress=None, inputs=None
    ) -> Path:
        self.asked = {
            "input_dir": Path(input_dir),
            "out_dir": Path(out_dir),
            "quarters": quarters,
            "user_rules": user_rules,
        }
        progress("Latest version of each case", 2, 5)
        self.said.set()
        assert self.go.wait(10)
        release = Path(out_dir) / self.source.name
        shutil.copytree(self.source, release)
        for name in ("manifest.json", "methods.json"):
            doc = json.loads((release / name).read_text())
            doc["user_rules"] = {"off": sorted(user_rules.off), "changed": []}
            (release / name).write_text(json.dumps(doc))
        return release


@pytest.fixture
def held(monkeypatch, own_release) -> HeldBuild:
    build = HeldBuild(own_release)
    monkeypatch.setattr(rebuild_module, "build_release", build)
    return build


@pytest.fixture
def held_open(monkeypatch) -> list[Path]:
    """Windows, simulated: nothing inside a folder a program has open can be removed, renamed
    or replaced. The test lists the folders the explorer has open."""
    folders: list[Path] = []

    def refusing(real):
        def call(path, *args, **kwargs):
            for named in (path, *args[:1]):
                if any(Path(named).resolve().is_relative_to(f.resolve()) for f in folders):
                    raise PermissionError(f"{named} is open in another program")
            return real(path, *args, **kwargs)

        return call

    for module, name in ((shutil, "rmtree"), (os, "rename"), (os, "replace"), (os, "unlink")):
        monkeypatch.setattr(module, name, refusing(getattr(module, name)))
    return folders


def pointer_of(release: Path) -> Path:
    return release.parent / POINTER.format(release=release.name)


def rebuilt_of(release: Path) -> Path:
    return release.parent / REBUILT.format(release=release.name)


def test_a_rebuild_runs_in_the_background_and_says_how_far_it_is(
    own_client, own_release, held, fake_input
):
    own_client.put("/api/rules", json=OFF_AND_CHANGED)
    started = own_client.post("/api/rules/rebuild", json={})
    assert started.status_code == 202
    assert started.json()["state"] == "running"
    assert held.said.wait(10)
    running = own_client.get("/api/rules/rebuild").json()
    assert running == {
        "state": "running",
        "step": "Latest version of each case",
        "done": 2,
        "total": 5,
    }
    assert own_client.get("/api/summary").status_code == 200  # the explorer goes on answering
    assert held.asked["input_dir"] == fake_input
    assert held.asked["out_dir"].parent == own_release.parent  # beside the release, not into it
    assert (
        held.asked["quarters"]
        == json.loads((own_release / "manifest.json").read_text())["quarters"]
    )
    assert held.asked["user_rules"].off == {"deleted-cases"}
    held.go.set()
    assert follow(own_client) == {"state": "done", "release": own_release.name}


def test_only_one_rebuild_runs_at_a_time(own_client, held):
    assert own_client.post("/api/rules/rebuild", json={}).status_code == 202
    again = own_client.post("/api/rules/rebuild", json={})
    assert again.status_code == 409
    assert again.json()["problem"] == "A rebuild is already running. It ends on its own."
    held.go.set()
    assert follow(own_client)["state"] == "done"


def test_altios_counts_are_kept_beside_the_release_for_the_page(own_client, own_release, held):
    standard = json.loads((own_release / "methods.json").read_text())
    own_client.put("/api/rules", json=OFF_AND_CHANGED)
    own_client.post("/api/rules/rebuild", json={})
    held.go.set()
    follow(own_client)
    kept = own_release.parent / STANDARD_METHODS.format(release=own_release.name)
    assert json.loads(kept.read_text()) == standard
    got = own_client.get("/api/rules").json()
    assert got["built"]["off"] == ["deleted-cases"]
    assert got["standard"] == standard


def test_a_failed_rebuild_says_why_and_the_release_stays(own_client, own_release, monkeypatch):
    def broken(*args, progress, **kwargs):
        progress("Building the explorer's database", 3, 4)
        raise duckdb.IOException('Could not write file "spill/x.block": No space left on device')

    monkeypatch.setattr(rebuild_module, "build_release", broken)
    own_client.post("/api/rules/rebuild", json={})
    state = follow(own_client)
    assert state["state"] == "failed"
    assert state["problem"].startswith(
        'The disk ran out of room at the step "Building the explorer\'s database". A rebuild of '
        "this release needs about "
    )
    assert f"GB free on the disk that holds {own_release.parent};" in state["problem"]
    assert "No space left" not in state["problem"] and "spill" not in state["problem"]
    assert own_client.get("/api/release").json()["release"] == own_release.name
    assert sorted(p.name for p in own_release.parent.iterdir()) == sorted(
        [own_release.name, STANDARD_METHODS.format(release=own_release.name)]
    )


SPILL_LIMIT = (
    "Out of Memory Error: failed to offload data block of size 64.0 KiB (18.6 GiB/18.6 GiB "
    "used). This limit was set by the 'max_temp_directory_size' setting."
)
STEP = "Building the explorer's database"


@pytest.mark.parametrize(
    ("raised", "free_gb", "says"),
    [
        (OSError(errno.ENOSPC, "No space left on device"), 500, "The disk ran out of room"),
        (duckdb.OutOfMemoryException(SPILL_LIMIT), 2, "The disk ran out of room"),
        (
            duckdb.OutOfMemoryException(SPILL_LIMIT),
            500,
            f"The rebuild needed more than the {SPILL} GB of working files it may write to disk",
        ),
        (
            duckdb.OutOfMemoryException("Out of Memory Error: could not allocate block"),
            500,
            f"The rebuild needed more than the {MEMORY} GB of memory it may use",
        ),
        (
            duckdb.InternalException("INTERNAL Error: Attempted to access index 3"),
            500,
            "The rebuild stopped at",
        ),
        (
            FileNotFoundError(errno.ENOENT, "No such file", "/x/drug.parquet"),
            500,
            "could not read or write /x/drug.parquet",
        ),
        (KeyError("tables"), 500, "on a problem of its own"),
    ],
)
def test_a_failed_rebuild_says_in_plain_words_what_happened_and_what_to_do(
    own_release, monkeypatch, raised, free_gb, says
):
    """Never DuckDB's or Python's own text: what stopped it, at which step, and what to do."""
    machine(monkeypatch, free_gb=free_gb)
    said = rebuild_module.why_it_stopped(raised, STEP, OpenRelease(own_release))
    assert says in said and f'at the step "{STEP}"' in said
    assert str(raised) not in said and "max_temp" not in said and "Error" not in said
    if "disk ran out" in says:
        shown = f"{free_gb:.0f}" if free_gb >= 10 else f"{free_gb:.1f}"
        assert f"GB free on the disk that holds {own_release.parent}; it has {shown} GB" in said


def test_a_refusal_of_our_own_keeps_its_plain_words(own_release):
    refused = "refused: explorer_case_T.age is not named as derived"
    said = rebuild_module.why_it_stopped(
        ExplorerBuildError(refused), STEP, OpenRelease(own_release)
    )
    assert said == f'The rebuild stopped at the step "{STEP}": {refused}'


def machine(monkeypatch, *, free_gb: float, memory_gib: float = 64) -> None:
    monkeypatch.setattr(rebuild_module, "free_disk", lambda _: int(free_gb * 10**9))
    monkeypatch.setattr(rebuild_module, "total_memory_bytes", lambda: int(memory_gib * 2**30))


def needed(release: Path) -> tuple[float, float]:
    """What open-altio doctor checks for this release (rule machine-needs): the demo's numbers
    for one quarter, a build of every quarter's for more."""
    quarters = json.loads((release / "manifest.json").read_text(encoding="utf-8"))["quarters"]
    which = "demo" if len(quarters) == 1 else "build"
    return tuple(
        float(rulebook.value("machine-needs", f"{which}_{what}_gb")) for what in ("disk", "memory")
    )


def test_the_rules_page_says_what_a_rebuild_needs_of_this_machine(
    own_client, own_release, monkeypatch
):
    disk, memory = needed(own_release)
    machine(monkeypatch, free_gb=disk + 50, memory_gib=memory + 4)
    said = own_client.get("/api/rules").json()["needs"]
    assert said["says"] == (
        f"A rebuild of this release needs about {disk:g} GB of free disk and {memory:g} GB of "
        f"memory. This computer has {disk + 50:.0f} GB free where the release is and "
        f"{memory + 4:.0f} GB of memory."
    )
    assert said["refused"] is None
    machine(monkeypatch, free_gb=disk + 50, memory_gib=memory / 2)
    said = own_client.get("/api/rules").json()["needs"]
    assert said["says"].endswith("With less memory than that the rebuild is slow and may stop.")
    assert said["refused"] is None  # memory is said, not refused: the build is held to its limit


def test_a_rebuild_will_not_start_on_less_free_disk_than_it_needs(
    own_client, own_release, monkeypatch
):
    disk, _ = needed(own_release)
    machine(monkeypatch, free_gb=1.5)
    refused = own_client.post("/api/rules/rebuild", json={})
    assert refused.status_code == 409
    assert refused.json()["problem"] == (
        f"A rebuild of this release needs about {disk:g} GB of free disk, and the disk that holds "
        f"{own_release.parent} has 1.5 GB free. Make room there, then rebuild."
    )
    assert own_client.get("/api/rules").json()["needs"]["refused"] == refused.json()["problem"]
    assert own_client.get("/api/rules/rebuild").json() == {"state": "idle"}


@pytest.mark.parametrize("width", (390, 1440))
def test_the_bar_says_what_a_rebuild_needs_and_will_not_start_without_the_room(
    chromium, explorer_app, own_release, fake_input, monkeypatch, width
):
    disk, _ = needed(own_release)
    with served(explorer_app(own_release, fda_dir=fake_input)) as base:
        machine(monkeypatch, free_gb=disk + 50)
        page = open_page(chromium, f"{base}/methods?open=after_deleted_lists", width=width)
        # the bar shows the change at once and saves it just after: the reload below must find
        # it saved
        with page.expect_response(
            lambda r: r.url.endswith("/api/rules") and r.request.method == "PUT"
        ):
            page.locator("#rule-deleted-cases .oa-rule-switch").click()
        page.wait_for_selector(".oa-rebuild-bar [data-needs]")
        says = page.inner_text(".oa-rebuild-bar [data-needs]")
        assert says.startswith(f"A rebuild of this release needs about {disk:g} GB of free disk")
        assert page.locator("[data-act='rules-rebuild']").is_enabled()
        machine(monkeypatch, free_gb=1.5)
        page.reload()
        drawn(page)
        page.wait_for_selector(".oa-rebuild-bar [data-needs]")
        assert page.inner_text(".oa-rebuild-bar [data-needs]").endswith(
            "Make room there, then rebuild."
        )
        assert page.locator("[data-act='rules-rebuild']").is_disabled()
        assert not page.evaluate("document.scrollingElement.scrollWidth > window.innerWidth")
        page.context.close()


def test_a_rebuild_needs_fdas_files(explorer_app, own_release, tmp_path):
    for fda_dir, said in (
        (None, "started without the folder of FDA's quarterly files"),
        (tmp_path / "gone", "FDA's quarterly files are not in"),
    ):
        web = TestClient(explorer_app(own_release, fda_dir=fda_dir))
        refused = web.post("/api/rules/rebuild", json={})
        assert refused.status_code == 409
        assert said in refused.json()["problem"]
        assert web.get("/api/rules/rebuild").json() == {"state": "idle"}


def test_a_rebuild_writes_to_the_folder_named_by_its_release(explorer_app, own_release, fake_input):
    renamed = own_release.parent / "mine"
    shutil.move(own_release, renamed)
    refused = TestClient(explorer_app(renamed, fda_dir=fake_input)).post(
        "/api/rules/rebuild", json={}
    )
    assert refused.status_code == 409
    assert f"Rename this folder to {own_release.name} first." in refused.json()["problem"]


def test_a_rebuild_starts_from_json_only(own_client, held):
    """A form on another site cannot start a rebuild: it cannot send JSON."""
    got = own_client.post(
        "/api/rules/rebuild",
        content="go=1",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert got.status_code == 415
    assert own_client.get("/api/rules/rebuild").json() == {"state": "idle"}


def test_the_tiny_release_is_rebuilt_beside_the_open_one_and_the_explorer_opens_it(
    own_client, own_release, held_open
):
    live = explorer_of(own_client.app).release
    before = live.current()
    held_open.append(own_release)
    untouched = (own_release / "explorer.duckdb").stat()
    saved = own_client.put("/api/rules", json=OFF_AND_CHANGED).json()["saved"]
    assert own_client.post("/api/rules/rebuild", json={}).status_code == 202
    assert follow(own_client) == {"state": "done", "release": own_release.name}
    got = own_client.get("/api/rules").json()
    assert got["built"] == got["saved"] == saved
    assert live.current() is not before  # the explorer answers from the new release
    assert live.current().folder == rebuilt_of(own_release).resolve()
    assert live.current().manifest["user_rules"] == saved
    assert own_client.get("/api/release").json()["release"] == own_release.name
    assert (own_release / "explorer.duckdb").stat().st_mtime_ns == untouched.st_mtime_ns


def test_with_the_classes_switched_off_the_rebuild_leaves_them_out_and_keeps_their_switch(
    own_client, own_release, fake_diana, tmp_path, monkeypatch
):
    """The drug classes' one switch off: the rebuilt release carries no classes, every page
    answers without them, and the rules page keeps their section, switched off, so they can be
    switched on again."""
    monkeypatch.setenv(DIANA_ENV, str(fake_diana))  # the drug names the classes join on
    assert own_client.get("/api/classes").status_code == 200
    with fakediana.pinned(fake_diana, tmp_path):
        own_client.put("/api/rules", json={"off": ["atc-index"]})
        own_client.post("/api/rules/rebuild", json={})
        assert follow(own_client) == {"state": "done", "release": own_release.name}
    rebuilt = json.loads((rebuilt_of(own_release) / "manifest.json").read_text())
    assert rebuilt["classes"]["present"] is False
    assert rebuilt["classes"]["reason"] == "switched off in your rules"
    assert not [t for t in rebuilt["tables"] if t.startswith("atc_")]
    assert own_client.get("/api/classes").status_code == 404
    got = own_client.get("/api/rules").json()
    assert got["built"] == got["saved"] == {"off": ["atc-index"], "changed": []}
    assert got["classes"]["present"] is False and got["classes"]["cases"] is None
    assert [r["name"] for r in got["rules"] if r["step"]["switch"]] == [
        "atc-index",
        "atc-spelling-bridges",
        "atc-group-classes",
        "atc-class-choice",
        "statistics-classes",
    ]


def test_a_rebuild_reads_the_release_to_its_meddra_again_as_a_first_build_does(
    explorer_app, licensed_release, fake_input, fake_diana, tmp_path, monkeypatch, ask
):
    """The rebuild gives the build the MedDRA files the explorer was started with, so the
    rebuilt release has the same licensed tables, the SMQs and LLTs, and statistics by PT."""
    mine = tmp_path / "releases" / licensed_release.name
    shutil.copytree(licensed_release, mine)
    monkeypatch.setenv(DIANA_ENV, str(fake_diana))  # the drug names, so there are statistics
    meddra = write_meddra(tmp_path / "meddra", "29.1")
    web = TestClient(explorer_app(mine, fda_dir=fake_input, inputs=Inputs(meddra=meddra)))
    smqs = ask(web, "/api/terms?q=&kind=smq&meddra=1")["totals"]["smq"]
    with fakediana.pinned(fake_diana, tmp_path):
        web.put("/api/rules", json=OFF_AND_CHANGED)
        web.post("/api/rules/rebuild", json={})
        assert follow(web) == {"state": "done", "release": mine.name}
    assert ask(web, "/api/me")["tiers"]["meddra"] is True
    assert ask(web, "/api/terms?q=&kind=smq&meddra=1")["totals"]["smq"] == smqs > 0
    assert ask(web, "/api/terms?q=head&kind=all&meddra=1")["llts"][0][:2] == [
        "Head pain",
        "Headache",
    ]
    [(version, before)] = read_licensed_manifest(mine)["meddra"]["versions"].items()
    [(again, after)] = read_licensed_manifest(rebuilt_of(mine))["meddra"]["versions"].items()
    assert again == version and after["source_files"] == before["source_files"]
    assert set(after["tables"]) == set(before["tables"])
    for name, table in before["tables"].items():
        if table["kind"] == "meddra":
            assert after["tables"][name]["rows"] == table["rows"]
    rebuilt = json.loads((rebuilt_of(mine) / "manifest.json").read_text())
    assert rebuilt["user_rules"]["off"] == ["deleted-cases"]
    assert rebuilt["statistics"]["reaction_key"] == "meddra_pt"


def test_a_release_read_to_meddra_is_not_rebuilt_without_its_files(
    explorer_app, licensed_release, fake_input
):
    refused = TestClient(explorer_app(licensed_release, fda_dir=fake_input)).post(
        "/api/rules/rebuild", json={}
    )
    assert refused.status_code == 409
    assert refused.json()["problem"] == (
        "This release is read to MedDRA 29.1, and a rebuild reads MedDRA's files again. "
        "Start the explorer with --meddra and the folder of MedDRA 29.1, then rebuild."
    )


def test_a_second_rebuild_writes_into_the_copy_the_explorer_no_longer_serves(
    own_client, own_release, held
):
    live = explorer_of(own_client.app).release
    held.go.set()
    for serves in (rebuilt_of(own_release), own_release):
        own_client.post("/api/rules/rebuild", json={})
        assert follow(own_client)["state"] == "done"
        assert live.current().folder == serves.resolve()
        assert pointer_of(own_release).read_text(encoding="utf-8").strip() == serves.name


def test_settling_puts_the_live_copy_under_the_release_s_own_name(own_client, own_release, held):
    own_client.put("/api/rules", json=OFF_AND_CHANGED)
    own_client.post("/api/rules/rebuild", json={})
    held.go.set()
    follow(own_client)
    # settling is for when no explorer has either copy open: Windows renames no folder in use
    explorer_of(own_client.app).release.current().close()
    settle(own_release.parent, own_release.name)
    assert json.loads((own_release / "manifest.json").read_text())["user_rules"]["off"] == [
        "deleted-cases"
    ]
    assert not rebuilt_of(own_release).exists() and not pointer_of(own_release).exists()


def test_settling_after_two_rebuilds_keeps_the_named_copy_and_removes_the_other(
    own_client, own_release, held
):
    held.go.set()
    for _ in range(2):
        own_client.post("/api/rules/rebuild", json={})
        follow(own_client)
    settle(own_release.parent, own_release.name)
    assert (own_release / "manifest.json").is_file()
    assert not rebuilt_of(own_release).exists() and not pointer_of(own_release).exists()


def test_settling_a_release_no_rebuild_touched_changes_nothing(own_release):
    settle(own_release.parent, own_release.name)
    assert [p.name for p in own_release.parent.iterdir()] == [own_release.name]


def first_build(out: Path, inputs: Inputs, fda: Path, diana: Path, rules: UserRules) -> Path:
    """A release as a person first builds it with every file: the build, then the labels step
    with their groups file and EMA's list, both under their rules."""
    with fakediana.pinned(diana, out.parent / f"{out.name}-rules"):
        built = build_release(
            fda,
            out,
            diana_dictionary=diana,
            meddra_dir=inputs.meddra,
            rxnorm_dir=inputs.rxnorm,
            labels=inputs.labels,
            user_rules=rules,
        )
    groups = out.parent / "label_groups.json"
    groups.write_text(json.dumps(GROUPS), encoding="utf-8")
    with rulebook.use_user_rules(rules):
        install_groups(built, groups)
        build_label_terms(built)
        build_release_flags(built, ime=inputs.ime)
    return built


@pytest.fixture(scope="module")
def every_file(tmp_path_factory) -> Inputs:
    """The person's own MedDRA, RxNorm, labels folder and EMA's list, invented."""
    folder = tmp_path_factory.mktemp("their-files")
    return Inputs(
        meddra=write_meddra(folder / "meddra", "29.1"),
        rxnorm=write_rxnorm(folder / "rxnorm"),
        labels=write_labels(folder / "labels"),
        ime=write_ime_workbook(folder / "ime.xlsx", ["94000001"], []),
    )


@pytest.fixture(scope="module")
def flagged_release(every_file, fake_input, fake_diana, tmp_path_factory) -> Path:
    """A release built with every file and flagged on FDA's labels. Shared: copy it to write."""
    out = tmp_path_factory.mktemp("flagged") / "releases"
    return first_build(out, every_file, fake_input, fake_diana, UserRules())


def layers(release: Path) -> dict:
    """What a release holds, without when or how fast it was built."""
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    [(version, meddra)] = read_licensed_manifest(release)["meddra"]["versions"].items()
    groups = licensed_dir(release) / "meddra" / version / LABEL_GROUPS_FILE
    return {
        "tables": {name: t["rows"] for name, t in manifest["tables"].items()},
        "licensed": {name: t["rows"] for name, t in meddra["tables"].items()},
        "rxnorm": manifest["rxnorm"],
        "labels": {k: v for k, v in manifest["labels"].items() if k != "seconds"},
        "label_flags": manifest["label_flags"],
        "groups": json.loads(groups.read_text(encoding="utf-8")),
        "user_rules": manifest["user_rules"],
    }


def test_a_rebuild_comes_out_as_a_first_build_with_the_same_files_label_flags_included(
    explorer_app, flagged_release, every_file, fake_input, fake_diana, tmp_path, monkeypatch, ask
):
    """Started with the files the release was built with, the rebuild reads MedDRA, RxNorm and
    FDA's labels again and flags the reactions again, with the groups file the release keeps:
    the rebuilt release holds what a first build with those files and rules holds."""
    mine = tmp_path / "releases" / flagged_release.name
    shutil.copytree(flagged_release, mine)
    monkeypatch.setenv(DIANA_ENV, str(fake_diana))
    web = TestClient(explorer_app(mine, fda_dir=fake_input, inputs=every_file))
    assert ask(web, CODED_CASE)["drugs"]
    with fakediana.pinned(fake_diana, tmp_path / "pinned"):
        web.put("/api/rules", json=OFF_AND_CHANGED)
        web.post("/api/rules/rebuild", json={})
        assert follow(web) == {"state": "done", "release": mine.name}
    rules = rulebook.load_user_rules(mine.parent / rulebook.FILE_NAME)
    again = first_build(tmp_path / "first", every_file, fake_input, fake_diana, rules)
    rebuilt = layers(rebuilt_of(mine))
    assert rebuilt == layers(again)
    assert {"drug_rxnorm_T", "label_candidates_T", "label_sections_T", "label_flags_T"} <= set(
        rebuilt["tables"]
    )
    assert rebuilt["label_flags"]["important_medical_events"] == 1
    assert rebuilt["user_rules"]["off"] == ["deleted-cases"]
    got = ask(web, CODED_CASE)
    assert got["drugs"] and got == ask(TestClient(explorer_app(again)), CODED_CASE)


@pytest.mark.parametrize(
    ("left_out", "said"),
    [
        (
            "rxnorm",
            "This release codes its drugs to RxNorm, and a rebuild reads RxNorm's files again. "
            "Start the explorer with --rxnorm and the folder "
            f"RxNorm_full_prescribe_{rulebook.value('rxnorm-ingredients', 'release')}.zip "
            "unzips to, then rebuild.",
        ),
        (
            "labels",
            "This release holds FDA's labels, and a rebuild reads them again. "
            "Start the explorer with --labels and the folder labels-fetch filled, then rebuild.",
        ),
        (
            "ime",
            "This release flags its reactions with EMA's Important Medical Events, and a rebuild "
            "reads EMA's file again. Start the explorer with --ime and EMA's Important Medical "
            "Events file for MedDRA 29.1, then rebuild.",
        ),
    ],
)
def test_a_release_is_not_rebuilt_without_a_file_it_was_built_with(
    explorer_app, flagged_release, every_file, fake_input, tmp_path, monkeypatch, left_out, said
):
    """The rebuild says which file to give rather than drop the layer the file built."""
    monkeypatch.setenv("OPEN_ALTIO_RXNORM_DIR", str(tmp_path / "no-rxnorm"))  # none by default
    given = Inputs(**{**vars(every_file), left_out: None})
    refused = TestClient(explorer_app(flagged_release, fda_dir=fake_input, inputs=given)).post(
        "/api/rules/rebuild", json={}
    )
    assert refused.status_code == 409
    assert refused.json()["problem"] == said
