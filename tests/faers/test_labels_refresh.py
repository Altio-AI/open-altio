"""Labels kept current between releases (rules label-refresh and label-source): a day's file of
changed labels is read, only what it changed is chosen and read again, the flags follow, a
reviewed coding survives, and a refresh that fails leaves the release as it was.

Built on a fake release built with the invented labels folder (open_altio.testing.fakelabels)
and the invented MedDRA, and an invented DailyMed serving one day's file at a time."""

from __future__ import annotations

import dataclasses
import json
import shutil
import zipfile
from datetime import timedelta
from pathlib import Path

import duckdb
import httpx
import pytest

from open_altio import rulebook
from open_altio.faers import build_release
from open_altio.faers.__main__ import main
from open_altio.faers.labeldict import CODINGS_FILE, build_label_terms, build_release_flags, join
from open_altio.faers.labels import build as label_build
from open_altio.faers.labels import daily, fetch, folder, refresh, switch
from open_altio.faers.labels.folder import find
from open_altio.faers.labels.refresh import RefreshRefused, refresh_labels
from open_altio.testing import fakediana
from open_altio.testing import fakelabels as fake
from open_altio.testing.fakelabeltables import add_label_groups, add_record_tables
from open_altio.testing.fakemeddra import write_meddra
from open_altio.testing.rules import rules_with

VERSION = "29.1"
LABELS = fake.labels()
ZENTORA, VALMOREX_ANDA, VALMORA_KIT, LID_PATCH = (LABELS[i] for i in (0, 4, 10, 16))
SEP = rulebook.value("label-sections", "cell_separator")
HEADACHE_ROW = f"Headache{SEP}8%{SEP}7%"  # a row of Zentora's table, the same in both versions
REVIEWED = {  # a person's reading of that row: it states no reaction
    "item_id": "reviewed-row",
    "set_id": ZENTORA.set_id,
    "section": "adverse_reactions",
    "sentence": HEADACHE_ROW,
    "pts": [],
    "none_reason": "invented",
    "agent": "invented",
    "instructions_version": "1",
    "reviewed_at": "",
}
NEW_ID = "00000099-aaaa-4bbb-8ccc-000000000099"
FLAGS = "label_flags_T"


@pytest.fixture(autouse=True)
def no_waiting(tmp_path):
    """Tests ask the invented DailyMed without waiting between requests."""
    with rules_with(tmp_path, {"label-source": {"seconds_between_requests": 0}}):
        yield


@pytest.fixture(scope="module")
def built(tmp_path_factory, fake_input, fake_diana):
    """A release built with the invented labels and MedDRA, with a person's reviewed coding,
    flagged on its drug records: warfarin's read as zentoprine, digoxin's as valmorex, by mouth."""
    root = tmp_path_factory.mktemp("refresh")
    labels = fake.write_labels(root / "labels")
    meddra = write_meddra(root / "meddra" / VERSION, VERSION)
    with fakediana.pinned(fake_diana, root / "scratch"):
        release = build_release(
            fake_input,
            root / "releases",
            diana_dictionary=fake_diana,
            meddra_dir=meddra,
            labels=labels,
        )
    add_label_groups(release, VERSION, {"not_a_medical_event": [], "procedure": []})
    # valsartan's records, alone and in their combination, are read as valmorex too
    codes = {"warfarin": fake.ZENTOPRINE, "digoxin": fake.VALMOREX, "valsartan": fake.VALMOREX}
    add_record_tables(
        release,
        codes | {"sacubitril;valsartan": fake.ZEN_VAL},
        {drug: ["by_mouth"] for drug in [*codes, "sacubitril;valsartan"]},
    )
    version = release / "licensed" / "meddra" / VERSION
    (version / CODINGS_FILE).write_text(json.dumps(REVIEWED) + "\n", encoding="utf-8")
    build_label_terms(release)
    build_release_flags(release)
    return release, labels


@pytest.fixture
def copy(built, tmp_path):
    release, labels = built
    shutil.copytree(release, tmp_path / "release")
    shutil.copytree(labels, tmp_path / "labels")
    return tmp_path / "release", tmp_path / "labels"


class DailyMed:
    """DailyMed's release files, invented: each file by its name, and what was asked."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.asked: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        self.asked.append((request.method, name))
        body = self.files.get(name)
        if body is None:
            return httpx.Response(404)
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": str(len(body))})
        return httpx.Response(200, content=body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def base_day(labels: Path):
    return folder.newest_day(find(labels).parts)


def changed_zentora(day) -> fake.FakeLabel:
    """Zentora's next version: a row added to its table that does not line up with the header,
    which the rules cannot read."""
    row = "<tr><td>Vomiting</td><td>3%</td><td>0</td><td>1%</td></tr></tbody>"
    sections = fake.rich_sections().replace("</tbody>", row)
    return dataclasses.replace(ZENTORA, version=4, effective=day, sections=sections)


def new_valmorex(day) -> fake.FakeLabel:
    """A new originator's label for valmorex, under an earlier application than the kit's."""
    return fake.FakeLabel(
        NEW_ID,
        "VALMOREX FIRST (valmorex) tablets",
        "NDA",
        "NDA010100",
        day,
        ("ORAL",),
        "TABLET",
        (fake.VAL_TAB,),
        fake.old_format_sections(),
        1,
    )


def one_day(labels: Path, *, deleted=()) -> tuple[DailyMed, object]:
    """DailyMed with the file of the day after the full release: Zentora changed, a new label,
    Lidoderma as it was, and a label of another kind; and the mapping file that day."""
    day = base_day(labels) + timedelta(days=1)
    other = dataclasses.replace(LABELS[6], set_id="00000098-aaaa-4bbb-8ccc-000000000098")
    changed = [changed_zentora(day), new_valmorex(day), LID_PATCH]
    files = {
        daily.file_name(day): fake.daily_zip(changed, [ZENTORA, *deleted], [other]),
        rulebook.value("label-source", "mapping_file"): fake.mapping_zip([*LABELS, *changed]),
    }
    return DailyMed(files), day


def table(release: Path, name: str) -> list[dict]:
    manifest = json.loads((release / "manifest.json").read_text())
    path = release / manifest["tables"][name]["path"]
    return duckdb.sql(f"SELECT * FROM '{path}'").df().to_dict("records")


def chosen(release: Path) -> dict[tuple[str, str], tuple[str, int]]:
    return {
        (r["rxcui_T"], r["route_family_T"]): (r["setid_T"], r["spl_version_T"])
        for r in table(release, "label_candidates_T")
    }


def files_of(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def licensed(release: Path) -> Path:
    return release / "licensed" / "meddra" / VERSION


def test_a_days_changed_labels_are_read_chosen_again_and_flagged(copy, monkeypatch):
    release, labels = copy
    dailymed, day = one_day(labels)
    read = []
    real = label_build.read_sections_of

    def reading(part, members, *rest):
        read.extend(folder.set_of(m) for m in members)
        return real(part, members, *rest)

    monkeypatch.setattr(label_build, "read_sections_of", reading)
    before = chosen(release)
    done = refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))

    assert done["daily_files"] == [daily.file_name(day)]
    assert done["labels_changed"] == 3  # Zentora, the new label and Lidoderma; not the other kind
    assert sorted(read) == sorted([ZENTORA.set_id, NEW_ID])  # Lidoderma's lines are kept
    after = chosen(release)
    assert after[(fake.ZENTOPRINE, "by_mouth")] == (ZENTORA.set_id, 4)
    assert after[(fake.VALMOREX, "by_mouth")] == (NEW_ID, 3)
    assert {k: v for k, v in after.items() if k[0] == fake.LIDORINE} == {
        k: v for k, v in before.items() if k[0] == fake.LIDORINE
    }
    changes = {(c["rxcui"], c["family"]): (c["old"], c["new"]) for c in done["changed"]}
    assert changes[(fake.ZENTOPRINE, "by_mouth")] == (
        {"setid": ZENTORA.set_id, "version": 3},
        {"setid": ZENTORA.set_id, "version": 4},
    )
    assert changes[(fake.VALMOREX, "by_mouth")] == (
        {"setid": VALMORA_KIT.set_id, "version": 3},
        {"setid": NEW_ID, "version": 3},
    )
    assert not {k for k in changes if k[0] == fake.LIDORINE}
    assert {
        r["setid_T"] for r in table(release, "label_flags_T") if r["rxcui_T"] == fake.VALMOREX
    } == {NEW_ID}
    labels_entry = json.loads((release / "manifest.json").read_text())["labels"]
    assert labels_entry["as_of"] == day.isoformat()
    assert labels_entry["refreshes"][-1]["changed"] == done["changed"]
    assert done["flags"] == "flagged again"
    assert not (release / refresh.STAGING).exists()


def test_flagging_again_writes_what_the_labels_step_writes(copy, tmp_path):
    """Every table the labels step reads is read where it is in the release, so the refreshed
    flags are the step's own on the refreshed labels, row for row and count for count."""
    release, labels = copy
    dailymed, day = one_day(labels)
    refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    again = tmp_path / "again"
    shutil.copytree(release, again)
    build_label_terms(again)
    build_release_flags(again)

    def flags(folder):
        return sorted(map(str, table(folder, "label_flags_T")))

    assert flags(release) == flags(again)
    entry = json.loads((release / "manifest.json").read_text())["label_flags"]
    assert entry == json.loads((again / "manifest.json").read_text())["label_flags"]


def test_flagging_again_keeps_each_ingredients_own_rows(copy):
    """ingredient_rxnorm_T, written by the RxNorm step, is read where it is in the release: after a
    refresh a combination's reactions are still flagged on each ingredient's own label."""
    release, labels = copy
    assert join.INGREDIENTS in json.loads((release / "manifest.json").read_text())["tables"]
    dailymed, day = one_day(labels)
    refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    sc = join.scope(release)
    notes = json.loads((release / "manifest.json").read_text())["label_flags"]["notes"]
    assert sc.ingredients and join.WITHOUT_INGREDIENTS not in notes
    path = release / json.loads((release / "manifest.json").read_text())["tables"][FLAGS]["path"]
    sql = f"SELECT rxcui_T, route_families_T, pt_T FROM '{path}'"
    flagged = set(duckdb.sql(sql).fetchall())
    own = set(join.pairs(release, sc))
    assert flagged == own
    assert own - set(join.pairs(release, dataclasses.replace(sc, ingredients=False)))


def test_a_reviewed_coding_survives_and_a_changed_phrase_waits_for_review(copy):
    release, labels = copy
    dailymed, day = one_day(labels)
    refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    terms = duckdb.sql(
        f"SELECT kept_T, decided_by_T FROM '{licensed(release) / 'label_terms_T.parquet'}'"
        " WHERE setid_T = ? AND sentence_T = ?",
        params=[ZENTORA.set_id, HEADACHE_ROW],
    ).fetchall()
    assert terms and all(t == (False, "reviewer") for t in terms)
    items = [json.loads(line) for line in (licensed(release) / "label_uncertain.jsonl").open()]
    added = f"Vomiting{SEP}3%{SEP}0{SEP}1%"
    assert [i["candidate_pt"] for i in items if i["sentence"] == added] == ["Vomiting"]


def test_a_withdrawn_label_leaves_and_its_ingredient_is_chosen_again(copy):
    release, labels = copy
    dailymed, day = one_day(labels, deleted=[VALMORA_KIT])
    done = refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    assert done["labels_withdrawn"] == 1
    after = chosen(release)
    assert VALMORA_KIT.set_id not in {s for s, _ in after.values()}
    changes = {(c["rxcui"], c["family"]): c["new"] for c in done["changed"]}
    assert changes[(fake.VALMOREX, "injected")] is None  # the kit was its only injected label


def test_a_failure_leaves_the_release_with_the_labels_it_had(copy, monkeypatch):
    release, labels = copy
    dailymed, day = one_day(labels)
    before = files_of(release)

    def stopped(*_args, **_kwargs):
        raise RuntimeError("the flags stopped")

    monkeypatch.setattr(refresh, "build_release_flags", stopped)
    with pytest.raises(RuntimeError, match="the flags stopped"):
        refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    assert files_of(release) == before


def test_a_switch_that_fails_half_way_puts_every_file_back(copy, monkeypatch):
    release, labels = copy
    dailymed, day = one_day(labels)
    before = files_of(release)
    real, calls = switch._move_in, []

    def failing(staged, target):
        calls.append(target)
        if len(calls) == 3:
            raise OSError("the disk is full")
        real(staged, target)

    monkeypatch.setattr(switch, "_move_in", failing)
    with pytest.raises(OSError, match="the disk is full"):
        refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    assert files_of(release) == before


def test_a_switch_a_crash_stopped_is_finished_by_the_next_refresh(copy, monkeypatch):
    release, labels = copy
    dailymed, day = one_day(labels)
    real, calls = switch._move_in, []

    def crashing(staged, target):
        calls.append(target)
        if len(calls) == 3:
            raise KeyboardInterrupt
        real(staged, target)

    monkeypatch.setattr(switch, "_move_in", crashing)
    with pytest.raises(KeyboardInterrupt):
        refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    assert (release / refresh.STAGING / switch.MOVES).is_file()
    monkeypatch.setattr(switch, "_move_in", real)
    done = refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    assert done["daily_files"] == []  # up to date: the stopped refresh's switch was finished
    assert chosen(release)[(fake.VALMOREX, "by_mouth")] == (NEW_ID, 3)
    assert json.loads((release / "manifest.json").read_text())["labels"]["as_of"] == day.isoformat()
    assert not (release / refresh.STAGING).exists()


def test_an_up_to_date_release_is_left_alone(copy):
    release, labels = copy
    dailymed, day = one_day(labels)
    today = day + timedelta(days=1)
    refresh_labels(release, labels, client=dailymed.client(), today=today)
    before, dailymed.asked = files_of(release), []
    assert (
        refresh_labels(release, labels, client=dailymed.client(), today=today)["daily_files"] == []
    )
    assert files_of(release) == before and dailymed.asked == []


def test_a_day_with_no_prescription_label_moves_the_day_on_only(copy):
    release, labels = copy
    day = base_day(labels) + timedelta(days=1)
    other = dataclasses.replace(LABELS[6], set_id="00000098-aaaa-4bbb-8ccc-000000000098")
    dailymed = DailyMed(
        {
            daily.file_name(day): fake.daily_zip([], [], [other]),
            rulebook.value("label-source", "mapping_file"): fake.mapping_zip(LABELS),
        }
    )
    tables = {
        n: files_of(release)[f"parquet/{n}.parquet"]
        for n in ("label_candidates_T", "label_flags_T")
    }
    done = refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    assert (done["labels_changed"], done["flags"]) == (0, "unchanged")
    assert {n: files_of(release)[f"parquet/{n}.parquet"] for n in tables} == tables
    assert json.loads((release / "manifest.json").read_text())["labels"]["as_of"] == day.isoformat()


def test_missed_days_are_caught_up_in_order_and_a_day_without_a_file_is_passed_over(copy):
    release, labels = copy
    base = base_day(labels)
    first, third = base + timedelta(days=1), base + timedelta(days=3)
    dailymed = DailyMed(
        {
            daily.file_name(first): fake.daily_zip([new_valmorex(first)]),
            daily.file_name(third): fake.daily_zip([changed_zentora(third)]),
            rulebook.value("label-source", "mapping_file"): fake.mapping_zip(
                [*LABELS, new_valmorex(first)]
            ),
        }
    )
    done = refresh_labels(
        release, labels, client=dailymed.client(), today=third + timedelta(days=1)
    )
    assert done["daily_files"] == [daily.file_name(first), daily.file_name(third)]
    heads = [name for method, name in dailymed.asked if method == "HEAD" and "daily" in name]
    assert heads == [daily.file_name(base + timedelta(days=n)) for n in range(4)]
    after = chosen(release)
    assert after[(fake.VALMOREX, "by_mouth")] == (NEW_ID, 3)
    assert after[(fake.ZENTOPRINE, "by_mouth")] == (ZENTORA.set_id, 4)


def test_a_release_too_far_behind_is_refused_before_anything_is_fetched(copy):
    release, labels = copy
    dailymed, _ = one_day(labels)
    late = base_day(labels) + timedelta(
        days=int(rulebook.value("label-refresh", "catch_up_days")) + 1
    )
    with pytest.raises(RefreshRefused, match="behind DailyMed"):
        refresh_labels(release, labels, client=dailymed.client(), today=late)
    assert dailymed.asked == []


def test_another_full_release_in_the_folder_reads_every_label_again(copy):
    release, labels = copy
    day = base_day(labels)
    part = find(labels).parts[0]
    name, inner = fake._member(new_valmorex(day))
    with zipfile.ZipFile(part, "a") as z:
        z.writestr(name, inner)
    mapping = rulebook.value("label-source", "mapping_file")
    dailymed = DailyMed({mapping: fake.mapping_zip([*LABELS, new_valmorex(day)])})
    done = refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    assert done["full_release_read"] and done["labels_read"] > len(LABELS) // 2
    assert chosen(release)[(fake.VALMOREX, "by_mouth")] == (NEW_ID, 3)


def test_flags_read_with_emas_list_are_not_refreshed_without_it(copy):
    release, labels = copy
    manifest = json.loads((release / "manifest.json").read_text())
    manifest["label_flags"]["important_medical_events"] = 1
    (release / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RefreshRefused, match="Important Medical Events"):
        refresh_labels(release, labels, client=DailyMed({}).client())


def test_the_command_refreshes_and_refuses_in_plain_words(copy, monkeypatch, capsys):
    release, labels = copy
    dailymed, _ = one_day(labels)
    monkeypatch.setattr(fetch, "new_client", dailymed.client)
    argv = ["labels-refresh", "--release", str(release), "--labels", str(labels)]
    assert main(argv) == 2  # today is long after the invented full release
    assert "behind DailyMed" in capsys.readouterr().err


def test_a_chosen_label_its_mapping_has_no_row_for_yet_keeps_its_place(copy):
    """DailyMed maps a new version some days after publishing it: Zentora's new version has no
    row in that day's mapping file, and stays zentoprine's label."""
    release, labels = copy
    day = base_day(labels) + timedelta(days=1)
    unmapped = [label for label in LABELS if label.set_id != ZENTORA.set_id]
    dailymed = DailyMed(
        {
            daily.file_name(day): fake.daily_zip([changed_zentora(day)]),
            rulebook.value("label-source", "mapping_file"): fake.mapping_zip(unmapped),
        }
    )
    refresh_labels(release, labels, client=dailymed.client(), today=day + timedelta(days=1))
    assert chosen(release)[(fake.ZENTOPRINE, "by_mouth")] == (ZENTORA.set_id, 4)


def test_a_label_is_placed_once_its_mapping_arrives(copy):
    release, labels = copy
    first = base_day(labels) + timedelta(days=1)
    second = first + timedelta(days=1)
    mapping = rulebook.value("label-source", "mapping_file")
    dailymed = DailyMed(
        {
            daily.file_name(first): fake.daily_zip([new_valmorex(first)]),
            mapping: fake.mapping_zip(LABELS),
        }
    )
    refresh_labels(release, labels, client=dailymed.client(), today=second)
    assert chosen(release)[(fake.VALMOREX, "by_mouth")] == (VALMORA_KIT.set_id, 3)
    dailymed.files[daily.file_name(second)] = fake.daily_zip([])
    dailymed.files[mapping] = fake.mapping_zip([*LABELS, new_valmorex(first)])
    done = refresh_labels(
        release, labels, client=dailymed.client(), today=second + timedelta(days=1)
    )
    assert done["labels_remapped"] == 1
    assert chosen(release)[(fake.VALMOREX, "by_mouth")] == (NEW_ID, 3)
