"""The statistics of each WHO class (src/open_altio/faers/statistics/classes.py and step.py, rule
statistics-classes): counted by hand on seven cases, written into a built release beside the
classes layer, and added to a release already built by the command, exactly as a full build
writes them."""

from __future__ import annotations

import json
import shutil

import duckdb
import numpy as np
import pytest

from open_altio import rulebook
from open_altio.faers import build_explorer_db, read_manifest
from open_altio.faers.__main__ import main
from open_altio.faers.explorer_db import CLASS_STATISTICS_TABLES
from open_altio.faers.statistics import (
    CLASS_COLUMNS,
    CLASS_TABLES,
    TABLE,
    build_classes,
    cases,
    classes,
    record_classes,
)
from open_altio.testing.releasereader import ReleaseReader

SUFFIX = rulebook.value("transformed-suffix-T", "derived_suffix")
KEY = "era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR"

# Counted: cases 1 to 5 (6 is a duplicate set aside, 7 names no reaction). Case 1 names two ACE
# inhibitors; case 3 a drug known only to the ACE inhibitors' level 3 class, which could be
# either of two level 4 classes; case 4 an aspirin that could be a blood thinner or a
# painkiller; case 5 a suspect with no class and an ACE inhibitor taken alongside.
STORY = {
    "case_latest_T": [
        ("1", "adult", "F", 2020, True),
        ("2", "adult", "F", 2020, True),
        ("3", "older", "M", 2021, True),
        ("4", "adult", "F", 2020, True),
        ("5", "adult", "F", 2020, True),
        ("6", "adult", "F", 2020, False),
        ("7", "adult", "F", 2020, True),
    ],
    "drug_latest_T": [
        ("1", "1", "PS"), ("1", "2", "SS"), ("2", "1", "PS"), ("3", "1", "PS"), ("4", "1", "PS"),
        ("5", "1", "PS"), ("5", "2", "C"), ("6", "1", "PS"), ("7", "1", "PS"),
    ],
    "drug_ingredient_T": [
        ("1", "1", "lisinopril"), ("1", "2", "enalapril"), ("2", "1", "valsartan"),
        ("3", "1", "ace mix"), ("4", "1", "aspirin"), ("5", "1", "metformin"),
        ("5", "2", "lisinopril"), ("6", "1", "lisinopril"), ("7", "1", "lisinopril"),
    ],
    "reac_latest_T": [
        ("1", "Angioedema"), ("1", "Cough"), ("2", "Angioedema"), ("3", "Cough"),
        ("4", "Bleeding"), ("5", "Nausea"), ("6", "Angioedema"),
    ],
}  # fmt: skip
# primaryid, drug_seq, the record's one class, its level, how it was chosen
CHOSEN = [
    ("1", "1", "C09AA03", 5, "only_code"),
    ("1", "2", "C09AA02", 5, "only_code"),
    ("2", "1", "C09CA03", 5, "only_code"),
    ("3", "1", "C09A", 3, "shared_class"),
    ("4", "1", None, None, "cannot_tell"),
    ("5", "2", "C09AA03", 5, "only_code"),
    ("6", "1", "C09AA03", 5, "only_code"),
    ("7", "1", "C09AA03", 5, "only_code"),
]
# primaryid, drug_seq, a possible code, its level
POSSIBLE = [
    ("1", "1", "C09AA03", 5), ("1", "2", "C09AA02", 5), ("2", "1", "C09CA03", 5),
    ("3", "1", "C09AA05", 5), ("3", "1", "C09BA05", 5),
    ("4", "1", "B01AC06", 5), ("4", "1", "N02BA01", 5), ("5", "2", "C09AA03", 5),
]  # fmt: skip
# (class, reaction): cases, at each level, for the records whose class reaches it
CERTAIN = {
    2: {("C09", "angioedema"): 2, ("C09", "cough"): 2},
    3: {("C09A", "angioedema"): 1, ("C09A", "cough"): 2, ("C09C", "angioedema"): 1},
    4: {("C09AA", "angioedema"): 1, ("C09AA", "cough"): 1, ("C09CA", "angioedema"): 1},
}
# what the records that could be a class add, where the rule counts them
COULD_BE = {
    2: {("B01", "bleeding"): 1, ("N02", "bleeding"): 1},
    3: {("B01A", "bleeding"): 1, ("N02B", "bleeding"): 1},
    4: {("C09AA", "cough"): 2, ("C09BA", "cough"): 1, ("B01AC", "bleeding"): 1,
        ("N02BA", "bleeding"): 1},
}  # fmt: skip


@pytest.fixture
def counted(small_release):
    con = small_release(**STORY)
    con.execute(
        f"CREATE TABLE atc_drug_T ({KEY}, drug_seq VARCHAR, atc_code_T VARCHAR, "
        "atc_level_T INTEGER, atc_chosen_by_T VARCHAR)"
    )
    con.executemany("INSERT INTO atc_drug_T VALUES ('faers', ?, '2026q2', ?, ?, ?, ?)", CHOSEN)
    con.execute(
        f"CREATE TABLE atc_drug_codes_T ({KEY}, drug_seq VARCHAR, atc_code_T VARCHAR, "
        "atc_level_T INTEGER)"
    )
    con.executemany("INSERT INTO atc_drug_codes_T VALUES ('faers', ?, '2026q2', ?, ?, ?)", POSSIBLE)
    counts = cases.count(con)
    classes.prepare(con)
    return counts, {v["level"]: classes.at_level(con, counts, v["level"]) for v in classes.levels()}


def named(counts: cases.Counts) -> dict[tuple[str, str], int]:
    p, e, n = (counts.pairs[k] for k in ("product", "event", "n"))
    return {
        (counts.ingredients[i], counts.reactions[j]): int(k)
        for i, j, k in zip(p, e, n, strict=True)
    }


def expected(level: int) -> dict[tuple[str, str], int]:
    return CERTAIN[level] | (COULD_BE[level] if classes.could_be() else {})


def test_each_level_counts_the_classes_its_records_reach(counted):
    _, found = counted
    assert sorted(found) == [v["level"] for v in classes.levels()]
    for level, (counts, _links, _named) in found.items():
        assert named(counts) == expected(level), level


def test_a_class_counts_each_case_once_whatever_its_drugs_of_the_class(counted):
    _, found = counted
    counts = found[4][0]
    by = counts.ingredient_strata
    margins = np.bincount(by["product"], weights=by["n"], minlength=len(counts.ingredients))
    c09aa = list(counts.ingredients).index("C09AA")
    # case 1's two ACE inhibitors are one case of the class (case 3 adds one where it could be)
    assert margins[c09aa] == (2 if classes.could_be() else 1)


def test_the_classes_are_counted_on_the_ingredient_statistics_own_cases(counted):
    ingredients, found = counted
    for counts, _links, _named in found.values():
        # case 5 names no class, yet stays in the table, as every case the ingredients count
        assert counts.cases == ingredients.cases == 5
        assert counts.strata is ingredients.strata
        assert counts.reaction_strata is ingredients.reaction_strata


def test_a_drug_taken_alongside_names_no_class(counted):
    _, found = counted
    assert all(("C09AA", "nausea") not in named(c) for c, _l, _n in found.values())


def test_each_ingredient_is_linked_to_its_own_records_classes(counted):
    _, found = counted
    _counts, links, with_class = found[4]
    got = {
        (i, c): int(n)
        for i, c, n in zip(*(links[k] for k in ("ingredient", "class", "cases")), strict=True)
    }
    certain = {("enalapril", "C09AA"): 1, ("lisinopril", "C09AA"): 1, ("valsartan", "C09CA"): 1}
    could = {("ace mix", "C09AA"): 1, ("ace mix", "C09BA"): 1, ("aspirin", "B01AC"): 1}
    could |= {("aspirin", "N02BA"): 1}
    assert got == certain | (could if classes.could_be() else {})
    assert set(links["level"]) == {4}
    assert with_class == (4 if classes.could_be() else 2)


# ----------------------------------------------------------------- written into a release


@pytest.fixture(scope="module")
def stats(stats_release) -> ReleaseReader:
    return ReleaseReader(stats_release)


def test_the_release_carries_them_as_tables_of_the_classes_layer(stats):
    entry = stats.manifest["class_statistics"]
    assert entry["present"] and entry["tables"] == list(CLASS_TABLES)
    assert set(CLASS_TABLES) <= set(stats.manifest["classes"]["tables"])
    for table in CLASS_TABLES:
        assert stats.manifest["tables"][table]["kind"] == "classes"
    assert stats.columns(classes.TABLE) == [name + SUFFIX for name in CLASS_COLUMNS]
    assert entry["counted"]["cases"] == stats.manifest["statistics"]["counted"]["cases"]
    assert [(v["level"], v["name"]) for v in entry["levels"]] == [
        (v["level"], v["name"]) for v in classes.levels()
    ]
    per_level = dict(stats.rows(f"SELECT level_T, count(*) FROM {classes.TABLE} GROUP BY 1"))
    assert {v["level"]: v["pairs"] for v in entry["levels"]} == per_level
    assert all(v["ebgm"]["fitted"] for v in entry["levels"])  # each level's own prior
    priors = [tuple(v["ebgm"]["prior"].values()) for v in entry["levels"]]
    assert len(set(priors)) == len(priors)


def test_a_class_of_one_ingredient_has_that_ingredients_numbers(stats):
    """The fixture's chemical subgroups each hold one ingredient, so each class's numbers, its
    EBGM under its own prior included, are its ingredient's."""
    deepest = classes.levels()[-1]["level"]
    numbers = [c for c in CLASS_COLUMNS if c not in ("class", "level", "reaction", "class_cases")]
    picked = ", ".join(f"s.{c}_T" for c in numbers)
    by_class = stats.rows(
        f"""SELECT l.ingredient_T, s.reaction_T, {picked} FROM {classes.TABLE} s
            JOIN {classes.INGREDIENTS_TABLE} l USING (level_T, class_T)
            WHERE s.level_T = {deepest} ORDER BY 1, 2"""
    )
    own = stats.rows(f"SELECT ingredient_T, reaction_T, {picked} FROM {TABLE} s ORDER BY 1, 2")
    assert len(by_class) == len(own) > 0
    for mine, theirs in zip(by_class, own, strict=True):
        assert mine[:3] == theirs[:3]
        assert np.allclose(
            np.array(mine[3:], dtype=float), np.array(theirs[3:], dtype=float), equal_nan=True
        )


def test_a_broader_class_counts_each_case_naming_any_of_its_drugs_once(stats):
    broadest = classes.levels()[0]["level"]
    [(code, n)] = stats.rows(
        f"""SELECT class_T, max(class_cases_T) FROM {classes.TABLE} WHERE level_T = {broadest}
            GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1"""
    )
    [(cases_of_its_drugs,)] = stats.rows(
        f"""SELECT count(DISTINCT primaryid) FROM drug_latest_T d
            JOIN atc_drug_T a USING (era_T, primaryid, quarter_T, drug_seq)
            JOIN case_latest_T c USING (era_T, primaryid, quarter_T)
            WHERE c.dup_kept_T AND upper(trim(d.role_cod)) IN ({cases.roles_sql()})
              AND starts_with(a.atc_code_T, '{code}')
              AND primaryid IN (SELECT primaryid FROM reac_latest_T)"""
    )
    assert n == cases_of_its_drugs


def test_a_release_without_classes_or_ingredients_has_none_and_says_why(tmp_path):
    written, entry = build_classes(tmp_path, {})
    assert written == {} and entry["present"] is False and "atc-index" in entry["reason"]
    written, entry = build_classes(tmp_path, {t: {} for t in classes.needs()})
    assert written == {} and "drug-names" in entry["reason"]


# ------------------------------------------- the command over a release already built


def _without_class_statistics(folder) -> None:
    """The release as a build before the class statistics wrote it: no tables, no entry, an
    explorer database without them."""
    manifest = read_manifest(folder)
    for table in CLASS_TABLES:
        (folder / manifest["tables"][table]["path"]).unlink()
    record_classes(manifest, {}, {})
    del manifest["class_statistics"]
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    build_explorer_db(folder)


def _explorer(folder) -> dict[str, list]:
    con = duckdb.connect(str(folder / "explorer.duckdb"), read_only=True)
    try:
        return {
            name: con.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall()
            for name in CLASS_STATISTICS_TABLES
        }
    finally:
        con.close()


def _entry(manifest: dict) -> dict:
    return {k: v for k, v in manifest["class_statistics"].items() if k != "seconds"}


def test_the_command_adds_what_a_full_build_writes(stats_release, stats, tmp_path, capsys):
    older = tmp_path / stats_release.name
    shutil.copytree(stats_release, older)
    _without_class_statistics(older)
    assert "class_statistics" not in read_manifest(older)
    assert not set(_explorer_names(older)) & set(CLASS_STATISTICS_TABLES)

    assert main(["class-statistics", "--release", str(older)]) == 0
    said = capsys.readouterr().out
    assert all(f"level {v['level']}, {v['name']}" in said for v in classes.levels())

    added = ReleaseReader(older)
    for table in CLASS_TABLES:
        every = f"SELECT * FROM {table} ORDER BY ALL"
        assert added.rows(every) == stats.rows(every) != [], table
        for key in ("path", "kind", "rows"):
            assert added.manifest["tables"][table][key] == stats.manifest["tables"][table][key]
    assert _entry(added.manifest) == _entry(stats.manifest)
    assert added.manifest["classes"] == stats.manifest["classes"]
    assert _explorer(older) == _explorer(stats_release)
    for name in CLASS_STATISTICS_TABLES:
        built = stats.manifest["explorer"]["tables"][name]
        assert added.manifest["explorer"]["tables"][name] == built
    assert not list(older.glob(".*"))  # no work folder left behind


def _explorer_names(folder) -> list[str]:
    con = duckdb.connect(str(folder / "explorer.duckdb"), read_only=True)
    try:
        return [r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()]
    finally:
        con.close()
