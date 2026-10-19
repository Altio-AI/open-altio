"""The drug classes layer (rules atc-index and atc-class-choice), on a small
invented class table and drug records made for each rule, and the standard dose
rules on our committed table."""

from __future__ import annotations

import csv
import json
import re

import duckdb
import pytest

from open_altio import rulebook
from open_altio.faers import route
from open_altio.faers.atc import layer
from open_altio.faers.rxnorm.layer import FDA_WORDS
from open_altio.testing.fakewho import write_classes
from open_altio.testing.rules import rules_with

YEAR = int(rulebook.value("atc-index", "index_year"))
# invented bounds for the invented quorpirin (low dose B01ZZ01, full dose N02ZZ01)
QUORPIRIN = [
    {"substance": "quorpirin", "unit": "MG", "at_most": 80, "code": "B01ZZ01"},
    {"substance": "quorpirin", "unit": "MG", "at_least": 400, "code": "N02ZZ01"},
]

# drug record -> (case, substance, its rows as (route, dose_amt, dose_unit[, dose_freq]))
RECORDS = {
    "eye": ("c1", "zelotolol", [("OPHTHALMIC", None, None)]),
    "tablet": ("c2", "zelotolol", [("ORAL", "20", "MG")]),
    "tablet_and_unknown": ("c2", "zelotolol", [("ORAL", None, None), ("UNKNOWN", None, None)]),
    "no_route": ("c3", "zelotolol", [(None, None, None)]),
    "unknown_route": ("c3", "zelotolol", [("UNKNOWN", None, None)]),
    "two_routes": ("c4", "zelotolol", [("ORAL", None, None), ("OPHTHALMIC", None, None)]),
    "one_code": ("c5", "plenivir", [(None, None, None)]),
    "set": ("c5", "dostavir;plenivir", [(None, None, None)]),
    "split": ("c6", "plenivir;unlistedium", [("ORAL", None, None)]),
    "low_dose": ("c7", "quorpirin", [("ORAL", "75", "MG"), ("ORAL", "50", "MG")]),
    "full_dose": ("c7", "quorpirin", [("ORAL", "450", "MG")]),
    "middle_dose": ("c8", "quorpirin", [("ORAL", "250", "MG")]),
    "mixed_units": ("c8", "quorpirin", [("ORAL", "75", "MG"), ("ORAL", "1", "G")]),
    "uncoded": ("c9", "unlistedium", [("ORAL", None, None)]),
    "no_substance": ("c9", None, [("ORAL", None, None)]),
    "eye_drops": ("c10", "ombrafloxacin", [("OPHTHALMIC", None, None)]),
    "ear_drops": ("c10", "ombrafloxacin", [("AURICULAR (OTIC)", None, None)]),
    "eye_drops_no_ear_code": ("c10", "otomycin", [("OPHTHALMIC", None, None)]),
    "ear_drops_no_ear_code": ("c10", "otomycin", [("AURICULAR (OTIC)", None, None)]),
    "steroid": ("c11", "velucort", [("TOPICAL", None, None)]),
    "steroid_in_a_mix": ("c11", "plenivir;velucort", [("TOPICAL", None, None)]),
    "level_4": ("c12", "ravuvir", [(None, None, None)]),
    "level_3": ("c12", "brenolol", [(None, None, None)]),
    "level_2": ("c12", "miravist", [(None, None, None)]),
    "level_1": ("c13", "lipotolol", [(None, None, None)]),
    "split_sharing": ("c13", "plenivir;ravuvir", [(None, None, None)]),
    "split_sharing_nothing": ("c13", "plenivir;quorpirin", [(None, None, None)]),
    "no_dose": ("c8", "quorpirin", [("ORAL", None, None)]),
    "nasal_spray": ("c14", "flutizone", [("NASAL", None, None)]),
    "spray_no_route": ("c14", "flutizone", [(None, None, None)]),
    "spray_by_mouth": ("c14", "flutizone", [("ORAL", None, None)]),
    "spray_two_routes": ("c14", "flutizone", [("NASAL", None, None), ("TOPICAL", None, None)]),
    "into_the_eye": ("c1", "zelotolol", [("Intravitreal use", None, None)]),
    "two_injections": (
        "c3",
        "zelotolol",
        [("SUBCUTANEOUS", None, None), ("INTRAVENOUS", None, None)],
    ),
}
# an invented class for mixes, in place of WHO's classes the rule lists
MIX_CLASSES = ["D07ZY"]


def _drug_tables(con: duckdb.DuckDBPyConnection, records=RECORDS, *, routes=True) -> None:
    """A record is (case, substance, rows), then optionally (drug name, active ingredient), FDA's
    words as drugname_norm_T and prod_ai_norm_T write them, and the indications the report
    gives for it. Each record's route is the one the route step reads (rule drug-route)."""
    key = "era_T VARCHAR, primaryid VARCHAR, quarter_T VARCHAR"
    con.execute(
        f"CREATE TABLE drug_latest_T ({key}, drug_seq VARCHAR, route VARCHAR, "
        "dose_amt VARCHAR, dose_unit VARCHAR, dose_freq VARCHAR, drugname_norm_T VARCHAR, "
        "prod_ai_norm_T VARCHAR, dose_form VARCHAR)"
    )
    con.execute(f"CREATE TABLE drug_substance_T ({key}, drug_seq VARCHAR, substance_T VARCHAR)")
    con.execute(
        f"CREATE TABLE case_latest_T ({key}, case_key_T VARCHAR, dup_kept_T BOOLEAN DEFAULT TRUE)"
    )
    con.execute(f"CREATE TABLE indi_latest_T ({key}, indi_drug_seq VARCHAR, indi_pt VARCHAR)")
    for case in sorted({c for c, *_ in records.values()}):
        con.execute(
            "INSERT INTO case_latest_T (era_T, primaryid, quarter_T, case_key_T) "
            "VALUES ('faers', ?, '2026q2', ?)",
            [case, case],
        )
    for seq, (case, substance, rows, *extra) in enumerate(records.values(), 1):
        name, active = extra[0] if extra else (None, None)
        for indication in extra[1] if len(extra) > 1 else []:
            con.execute(
                "INSERT INTO indi_latest_T VALUES ('faers', ?, '2026q2', ?, ?)",
                [case, str(seq), indication],
            )
        con.execute(
            "INSERT INTO drug_substance_T VALUES ('faers', ?, '2026q2', ?, ?)",
            [case, str(seq), substance],
        )
        for way, amount, unit, *freq in rows:
            con.execute(
                "INSERT INTO drug_latest_T VALUES "
                "('faers', ?, '2026q2', ?, ?, ?, ?, ?, ?, ?, NULL)",
                [case, str(seq), way, amount, unit, freq[0] if freq else None, name, active],
            )
    if routes:
        route.build(con)


@pytest.fixture
def table(tmp_path):
    return write_classes(tmp_path / "classes.csv")


@pytest.fixture
def groups(tmp_path):
    """No group classes: the repository's list names classes the invented table does not hold."""
    return _groups(tmp_path / "no_groups.csv", [])


@pytest.fixture
def built(table, groups, tmp_path):
    con = duckdb.connect()
    _drug_tables(con)
    choice = {"dose_rules": QUORPIRIN, "mix_classes": MIX_CLASSES}
    with rules_with(tmp_path, {"atc-class-choice": choice}):
        entry = layer.build(con, table, groups)
    return con, entry


def _drug(con, name: str) -> dict | None:
    seq = str(list(RECORDS).index(name) + 1)
    cur = con.execute("SELECT * FROM atc_drug_T WHERE drug_seq = ?", [seq])
    row = cur.fetchone()
    return dict(zip([d[0] for d in cur.description], row, strict=True)) if row else None


def _codes(con, name: str) -> list[tuple]:
    seq = str(list(RECORDS).index(name) + 1)
    return con.execute(
        "SELECT atc_ingredient_T, atc_code_T, atc_chosen_T FROM atc_drug_codes_T "
        "WHERE drug_seq = ? ORDER BY atc_code_T",
        [seq],
    ).fetchall()


# the choice (rule atc-class-choice) ------------------------------------------------


def test_one_code_is_the_class(built):
    con, _ = built
    row = _drug(con, "one_code")
    assert (row["atc_code_T"], row["atc_chosen_by_T"], row["atc_possible_codes_T"]) == (
        "J05ZZ01",
        "only_code",
        1,
    )


@pytest.mark.parametrize(
    "name, code", [("eye", "S01ZZ01"), ("tablet", "C07ZZ01"), ("into_the_eye", "S01ZZ01")]
)
def test_the_route_chooses_between_two_uses(built, name, code):
    con, _ = built
    row = _drug(con, name)
    assert (row["atc_code_T"], row["atc_chosen_by_T"], row["atc_possible_codes_T"]) == (
        code,
        "route",
        2,
    )


@pytest.mark.parametrize(
    "name, code",
    [
        ("eye_drops", "S01ZZ02"),
        ("ear_drops", "S02ZZ01"),
        ("eye_drops_no_ear_code", "S01ZZ03"),
        ("ear_drops_no_ear_code", "S03ZZ02"),
    ],
)
def test_eye_drops_take_the_eye_code_ear_drops_the_ear_code_and_the_eye_and_ear_code_is_last(
    built, name, code
):
    con, _ = built
    row = _drug(con, name)
    assert (row["atc_code_T"], row["atc_chosen_by_T"]) == (code, "route")


# rows giving two routes, even of one group or one of them Unknown, are a record the route step
# reads as Unknown
@pytest.mark.parametrize(
    "name", ["no_route", "unknown_route", "two_routes", "tablet_and_unknown", "two_injections"]
)
def test_a_report_that_does_not_say_which_use_is_cant_tell(built, name):
    con, _ = built
    row = _drug(con, name)
    assert (row["atc_code_T"], row["atc_level_T"], row["atc_chosen_by_T"]) == (
        None,
        None,
        "cannot_tell",
    )
    assert [c for _, c, _ in _codes(con, name)] == [
        "C07ZZ01",
        "S01ZZ01",
    ]  # both possible codes kept


@pytest.mark.parametrize("name, code", [("low_dose", "B01ZZ01"), ("full_dose", "N02ZZ01")])
def test_every_stated_dose_within_a_bound_chooses_by_dose(built, name, code):
    con, _ = built
    row = _drug(con, name)
    assert (row["atc_code_T"], row["atc_chosen_by_T"]) == (code, "dose")


@pytest.mark.parametrize("name", ["middle_dose", "mixed_units", "no_dose"])
def test_a_dose_between_the_bounds_in_two_units_or_none_decides_nothing(built, name):
    con, _ = built
    assert _drug(con, name)["atc_chosen_by_T"] == "cannot_tell"  # by mouth fits both codes


def test_a_combination_gets_its_combination_code_before_any_splitting(built):
    con, _ = built
    row = _drug(con, "set")
    assert (row["atc_code_T"], row["atc_matched_on_T"], row["atc_chosen_by_T"]) == (
        "J05ZZ51",
        "ingredient_set",
        "only_code",
    )
    assert _codes(con, "set") == [("dostavir;plenivir", "J05ZZ51", True)]


@pytest.mark.parametrize("name", ["split", "split_sharing", "split_sharing_nothing"])
def test_a_combination_without_a_code_is_split_and_cant_tell_even_when_its_codes_share_a_class(
    built, name
):
    con, _ = built
    row = _drug(con, name)
    assert (row["atc_code_T"], row["atc_level_T"], row["atc_matched_on_T"]) == (
        None,
        None,
        "each_ingredient",
    )
    assert row["atc_chosen_by_T"] == "cannot_tell"
    assert not any(chosen for _, _, chosen in _codes(con, name))
    assert _codes(con, "split") == [("plenivir", "J05ZZ01", False)]  # its codes stay listed


# the standard dose rules, on our committed table (rule atc-class-choice) ------------

DOSE_RULES = rulebook.value("atc-class-choice", "dose_rules")
WEEKLY = next(d for d in DOSE_RULES if d.get("freq"))


def _at_bound(rule: dict) -> tuple:
    """A row stating `rule`'s substance at its bound, in its unit, with no route, and with
    the first of its frequencies when it names any."""
    bound = rule["at_most"] if "at_most" in rule else rule["at_least"]
    return (None, f"{bound:g}", rule["unit"].lower(), (rule.get("freq") or [None])[0])


def _standard(records: dict) -> dict:
    """Each record's (class, how it was chosen) under the standard rules and our table."""
    con = duckdb.connect()
    _drug_tables(con, records)
    layer.build(con)
    got = con.execute("SELECT drug_seq, atc_code_T, atc_chosen_by_T FROM atc_drug_T").fetchall()
    names = {str(seq): name for seq, name in enumerate(records, 1)}
    return {names[seq]: (code, chosen_by) for seq, code, chosen_by in got}


def _rule_name(rule: dict) -> str:
    bound = (
        f"at_most {rule['at_most']:g}" if "at_most" in rule else f"at_least {rule['at_least']:g}"
    )
    return f"{rule['substance']} {rule['unit']} {bound}"


def test_every_dose_rule_chooses_its_code_for_a_record_at_its_bound():
    """A rule whose substance our table does not hold, or whose code is not one of that
    substance's codes, chooses nothing, and fails here."""
    records = {_rule_name(d): ("c1", d["substance"], [_at_bound(d)]) for d in DOSE_RULES}
    got = _standard(records)
    wrong = {
        name: got.get(name)
        for name, d in zip(records, DOSE_RULES, strict=True)
        if got.get(name) != (d["code"], "dose")
    }
    assert wrong == {}


def test_a_rule_with_frequencies_needs_every_stated_frequency_in_its_list():
    weekly, other = WEEKLY["freq"]
    row = _at_bound(WEEKLY)[:3]
    got = _standard(
        {
            "weekly": ("c1", WEEKLY["substance"], [(*row, weekly)]),
            "both weekly spellings": ("c1", WEEKLY["substance"], [(*row, weekly), (*row, other)]),
            "daily": ("c1", WEEKLY["substance"], [(*row, "QD")]),
            "weekly and daily": ("c1", WEEKLY["substance"], [(*row, weekly), (*row, "QD")]),
            "no frequency": ("c1", WEEKLY["substance"], [(*row, None)]),
        }
    )
    chosen = {name: by == "dose" for name, (_, by) in got.items()}
    assert chosen == {
        "weekly": True,
        "both weekly spellings": True,
        "daily": False,
        "weekly and daily": False,
        "no frequency": False,
    }


def test_aspirin_at_a_painkillers_dose_is_not_chosen_by_dose():
    """Many aspirin records at a painkiller's dose are for the heart, so no rule reads that
    dose as a painkiller; only the low dose decides."""
    low = next(d for d in DOSE_RULES if d["substance"] == "acetylsalicylic acid")
    assert [d for d in DOSE_RULES if d["substance"] == "acetylsalicylic acid"] == [low]
    got = _standard(
        {
            "low": ("c1", "acetylsalicylic acid", [_at_bound(low)]),
            "full": ("c1", "acetylsalicylic acid", [(None, "500", "MG")]),
        }
    )
    assert got == {"low": (low["code"], "dose"), "full": (None, "cannot_tell")}


# codes WHO reserves for mixes (rule atc-class-choice, mix_classes) ----------------


def test_a_single_ingredient_never_takes_a_code_under_a_class_for_mixes(built):
    con, _ = built
    row = _drug(con, "steroid")
    assert (row["atc_code_T"], row["atc_chosen_by_T"], row["atc_possible_codes_T"]) == (
        "D07ZZ01",
        "only_code",
        1,
    )
    assert [c for _, c, _ in _codes(con, "steroid")] == ["D07ZZ01"]


def test_a_combination_split_into_its_ingredients_keeps_the_codes_for_mixes(built):
    con, _ = built
    assert [c for _, c, _ in _codes(con, "steroid_in_a_mix")] == ["D07ZY01", "D07ZZ01", "J05ZZ01"]


def test_a_class_the_rule_does_not_list_is_not_read_as_one_for_mixes(table, groups, tmp_path):
    con = duckdb.connect()
    _drug_tables(con)
    with rules_with(tmp_path, {"atc-class-choice": {"mix_classes": []}}):
        layer.build(con, table, groups)
    row = _drug(con, "steroid")
    assert (row["atc_possible_codes_T"], row["atc_chosen_by_T"]) == (2, "shared_class")


def test_the_classes_for_mixes_are_classes_of_our_table_whose_name_says_combinations():
    """The list was read from WHO's class names in our table: each says its products are
    combinations; none says it excludes or includes them, holds plain products, or is a
    class of "Combinations of" products that name every ingredient or are one substance."""
    names = {}
    path = rulebook.data_root() / rulebook.value("atc-index", "table")
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if not row["ingredient"]:
                names[row["atc_code"]] = row["who_name"].lower()
    listed = rulebook.value("atc-class-choice", "mix_classes")
    for code in listed:
        assert "combination" in names[code] and not names[code].startswith("combination"), code
        assert not re.search(r"(excl\.|incl\.|plain and in) combination", names[code]), code
    for code in ("A11C", "A11D", "A11G", "A02AD", "J01CR04"):  # vitamins, antacids, a prodrug
        assert not any(code.startswith(m) for m in listed), code


# the broadest class a record's possible codes share (rule atc-class-choice) --------


@pytest.mark.parametrize(
    "name, code, level",
    [
        ("level_4", "J05ZZ", 4),
        ("level_3", "C07Z", 3),
        ("level_2", "S01", 2),
    ],
)
def test_a_record_it_cannot_tell_gets_the_deepest_class_its_codes_share(built, name, code, level):
    con, _ = built
    row = _drug(con, name)
    assert (row["atc_code_T"], row["atc_level_T"], row["atc_chosen_by_T"]) == (
        code,
        level,
        "shared_class",
    )
    assert row["atc_possible_codes_T"] == len(_codes(con, name)) > 1  # every possible code kept
    assert not any(chosen for _, _, chosen in _codes(con, name))


def test_the_codes_its_one_route_group_fits_give_the_class_when_two_or_more_fit(built):
    con, _ = built
    row = _drug(con, "nasal_spray")
    assert (row["atc_code_T"], row["atc_level_T"], row["atc_chosen_by_T"]) == (
        "R01ZZ",
        4,
        "shared_class",
    )
    assert row["atc_possible_codes_T"] == 3  # the skin code stays a possible code


@pytest.mark.parametrize("name", ["spray_no_route", "spray_by_mouth", "spray_two_routes"])
def test_with_no_route_one_no_code_fits_or_two_groups_all_its_codes_must_share_the_class(
    built, name
):
    con, _ = built
    row = _drug(con, name)
    assert (row["atc_code_T"], row["atc_chosen_by_T"]) == (None, "cannot_tell")


def test_codes_that_share_only_the_first_letter_give_no_class(built):
    con, _ = built
    row = _drug(con, "level_1")
    assert (row["atc_code_T"], row["atc_chosen_by_T"]) == (None, "cannot_tell")


def test_records_with_no_coded_substance_have_no_class_row(built):
    con, _ = built
    assert _drug(con, "uncoded") is None and _drug(con, "no_substance") is None


# the tables and their provenance (rule atc-index) ----------------------------------


def test_the_layer_is_its_own_tables_with_one_prefix(built):
    con, entry = built
    prefix = rulebook.value("atc-index", "table_prefix")
    assert entry["tables"] == list(layer.TABLES) and all(t.startswith(prefix) for t in layer.TABLES)
    have = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    assert {t for t in have if t.startswith(prefix)} == set(layer.TABLES)  # scratch tables are gone


def test_every_class_row_carries_its_provenance(built):
    con, _ = built
    columns = [r[0] for r in con.execute("DESCRIBE atc_drug_T").fetchall()]
    assert columns == list(layer.RECORD) + [
        "atc_code_T",
        "atc_level_T",
        "atc_index_year_T",
        "atc_chosen_by_T",
        "atc_possible_codes_T",
        "atc_matched_on_T",
    ]
    assert con.execute("SELECT DISTINCT atc_index_year_T FROM atc_drug_T").fetchall() == [(YEAR,)]
    assert con.execute(
        "SELECT DISTINCT atc_level_T FROM atc_drug_T WHERE atc_chosen_by_T <> 'shared_class'"
        " AND atc_code_T IS NOT NULL"
    ).fetchall() == [(5,)]
    assert con.execute(
        "SELECT count(*) FROM atc_drug_T WHERE length(atc_code_T) <> CASE atc_level_T"
        " WHEN 5 THEN 7 WHEN 4 THEN 5 WHEN 3 THEN 4 WHEN 2 THEN 3 END"
    ).fetchone() == (0,)


def test_the_all_codes_table_marks_exactly_the_chosen_code(built):
    con, _ = built
    wrong = con.execute("""SELECT count(*) FROM atc_drug_T d
        JOIN atc_drug_codes_T c USING (era_T, primaryid, quarter_T, drug_seq)
        WHERE c.atc_chosen_T AND c.atc_code_T IS DISTINCT FROM d.atc_code_T""").fetchone()
    assert wrong == (0,)
    chosen = con.execute("SELECT count(*) FROM atc_drug_codes_T WHERE atc_chosen_T").fetchone()[0]
    exact = (
        "SELECT count(*) FROM atc_drug_T WHERE atc_chosen_by_T IN "
        "('only_code', 'dose', 'route', 'indication', 'group_class')"
    )
    assert chosen == con.execute(exact).fetchone()[0]


def test_the_index_names_every_code_at_every_level(built):
    con, _ = built
    assert con.execute(
        """SELECT count(*) FROM atc_drug_codes_T c ANTI JOIN atc_index_T i USING (atc_code_T)"""
    ).fetchone() == (0,)
    assert con.execute(
        "SELECT atc_name_T, atc_level_T FROM atc_index_T WHERE atc_code_T = 'S01'"
    ).fetchone() == ("INVENTED EYE MEDICINES", 2)


def test_a_set_aside_duplicate_is_not_counted(table, groups, tmp_path):
    con = duckdb.connect()
    _drug_tables(con)
    con.execute("UPDATE case_latest_T SET dup_kept_T = FALSE WHERE primaryid = 'c1'")
    choice = {"dose_rules": QUORPIRIN, "mix_classes": MIX_CLASSES}
    with rules_with(tmp_path, {"atc-class-choice": choice}):
        entry = layer.build(con, table, groups)
    # c1 names several drugs with a class; set aside, it drops out of all the counts it was in
    assert entry["cases"] == {
        "with_a_coded_drug": 12,
        "with_a_class": 7,
        "with_a_shared_class": 2,
        "with_cannot_tell": 8,
    }


def test_counts_are_of_cases_not_rows(built):
    _, entry = built
    # every case but c9 names a coded drug; c1, c5, c7, c10 and c12 have several drugs with a
    # class, each case counted once; c12 (three) and c14 have a shared class; c2, c3, c4, c6, c8,
    # c11, c13 and c14 have a drug it cannot tell (c3, c8, c13 and c14 more than one)
    assert entry["cases"] == {
        "with_a_coded_drug": 13,
        "with_a_class": 8,
        "with_a_shared_class": 2,
        "with_cannot_tell": 8,
    }
    assert entry["present"] and entry["index_year"] == YEAR
    assert entry["citation"] == rulebook.value("atc-index", "citation")


def test_a_route_group_the_rule_gives_no_codes_for_stops_the_build(table, groups, tmp_path):
    con = duckdb.connect()
    _drug_tables(con)
    fits = {
        g: s for g, s in rulebook.value("atc-class-choice", "route_groups").items() if g != "ear"
    }
    with (
        rules_with(tmp_path, {"atc-class-choice": {"route_groups": fits}}),
        pytest.raises(layer.LayerRefused, match="no codes for the route groups ear"),
    ):
        layer.build(con, table, groups)


def test_without_the_route_step_nothing_is_written_and_the_entry_says_why(table, groups):
    con = duckdb.connect()
    _drug_tables(con, routes=False)
    entry = layer.build(con, table, groups)
    assert entry["present"] is False and route.TABLE in entry["reason"]


# the indication, after dose and route (rule atc-class-choice) ------------------------

INDICATION_RULES = [
    {
        "substance": "zelotolol",
        "indications": ["glaucoma", "intraocular pressure increased"],
        "code": "S01ZZ01",
    },
    {"substance": "zelotolol", "indications": ["hypertension"], "code": "C07ZZ01"},
    {"substance": "quorpirin", "indications": ["headache"], "code": "N02ZZ01"},
    {"substance": "plenivir", "indications": ["glaucoma"], "code": "S01ZZ01"},  # not its code
    {"substance": "flutizone", "indications": ["rhinitis allergic"], "code": "R01ZZ01"},
    {"substance": "flutizone", "indications": ["eczema"], "code": "D07ZZ02"},
]
NO_WORDS = (None, None)
# drug record -> (case, substance, its rows, FDA's words, the indications given for it)
INDICATED = {
    "glaucoma": ("i1", "zelotolol", [(None, None, None)], NO_WORDS, ["Glaucoma"]),
    "two_indications_one_use": (
        "i1",
        "zelotolol",
        [(None, None, None)],
        NO_WORDS,
        ["Glaucoma", "Intraocular pressure increased"],
    ),
    "an_unmatched_indication_says_nothing": (
        "i2",
        "zelotolol",
        [(None, None, None)],
        NO_WORDS,
        ["Glaucoma", "Product used for unknown indication"],
    ),
    "capitals_and_edge_spaces": (
        "i2",
        "zelotolol",
        [(None, None, None)],
        NO_WORDS,
        [" INTRAOCULAR PRESSURE INCREASED "],
    ),
    "two_uses": ("i3", "zelotolol", [(None, None, None)], NO_WORDS, ["Glaucoma", "Hypertension"]),
    "part_of_a_word": ("i3", "zelotolol", [(None, None, None)], NO_WORDS, ["Glaucomatous disc"]),
    "a_term_inside_a_longer_term": (
        "i3",
        "zelotolol",
        [(None, None, None)],
        NO_WORDS,
        ["Angle closure glaucoma"],
    ),
    "route_first": ("i4", "zelotolol", [("ORAL", None, None)], NO_WORDS, ["Glaucoma"]),
    "dose_first": ("i4", "quorpirin", [("ORAL", "75", "MG")], NO_WORDS, ["Headache"]),
    "among_the_codes_its_route_fits": (
        "i6",
        "flutizone",
        [("NASAL", None, None)],
        NO_WORDS,
        ["Rhinitis allergic"],
    ),
    "a_code_its_route_does_not_fit": (
        "i6",
        "flutizone",
        [("NASAL", None, None)],
        NO_WORDS,
        ["Eczema"],
    ),
    "a_route_that_fits_none_of_its_codes": (
        "i7",
        "zelotolol",
        [("TOPICAL", None, None)],
        NO_WORDS,
        ["Glaucoma"],
    ),
    "no_route_any_of_its_codes": ("i7", "flutizone", [(None, None, None)], NO_WORDS, ["Eczema"]),
    "by_mouth_both_codes_fit": ("i8", "quorpirin", [("ORAL", None, None)], NO_WORDS, ["Headache"]),
    "no_indication": ("i5", "zelotolol", [(None, None, None)]),
    "another_drugs_indication": ("i5", "plenivir", [(None, None, None)], NO_WORDS, ["Glaucoma"]),
}


@pytest.fixture
def indicated(table, groups, tmp_path):
    con = duckdb.connect()
    _drug_tables(con, INDICATED)
    choice = {"dose_rules": QUORPIRIN, "indication_rules": INDICATION_RULES}
    with rules_with(tmp_path, {"atc-class-choice": choice}):
        layer.build(con, table, groups)
    names = {str(seq): name for seq, name in enumerate(INDICATED, 1)}
    got = con.execute("SELECT drug_seq, atc_code_T, atc_chosen_by_T FROM atc_drug_T").fetchall()
    return {names[seq]: (code, by) for seq, code, by in got}


@pytest.mark.parametrize(
    "name",
    [
        "glaucoma",
        "two_indications_one_use",
        "an_unmatched_indication_says_nothing",
        "capitals_and_edge_spaces",
    ],
)
def test_indications_that_all_point_to_one_of_its_codes_choose_it(indicated, name):
    assert indicated[name] == ("S01ZZ01", "indication")


@pytest.mark.parametrize(
    "name", ["two_uses", "part_of_a_word", "a_term_inside_a_longer_term", "no_indication"]
)
def test_indications_of_two_uses_a_term_inside_a_longer_one_or_none_decide_nothing(indicated, name):
    # "Angle closure glaucoma" is not the term "glaucoma": a term matches only as a whole
    assert indicated[name] == (None, "cannot_tell")


def test_the_indication_chooses_only_among_the_codes_its_one_route_group_fits(indicated):
    assert indicated["among_the_codes_its_route_fits"] == ("R01ZZ01", "indication")
    assert indicated["by_mouth_both_codes_fit"] == ("N02ZZ01", "indication")
    # a nasal spray for eczema keeps the class its nasal codes share, never the skin code
    assert indicated["a_code_its_route_does_not_fit"] == ("R01ZZ", "shared_class")
    # an eye code is never given to a record stated on the skin, which fits none of its codes
    assert indicated["a_route_that_fits_none_of_its_codes"] == (None, "cannot_tell")


def test_with_no_route_the_indication_chooses_among_all_its_codes(indicated):
    assert indicated["no_route_any_of_its_codes"] == ("D07ZZ02", "indication")


class _Profiled:
    """A connection that profiles the indication step's query: the most rows any of its
    operators puts out."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self.con, self.most_rows = con, None

    def __getattr__(self, name: str):
        return getattr(self.con, name)

    def execute(self, sql: str, *args):
        if not sql.lstrip().startswith("CREATE TABLE atc_indicated_T"):
            return self.con.execute(sql, *args)
        self.con.execute("PRAGMA enable_profiling = 'no_output'")
        done = self.con.execute(sql, *args)
        plan = json.loads(self.con.get_profiling_information())
        self.con.execute("PRAGMA disable_profiling")

        def most(node: dict) -> int:
            return max([node.get("operator_cardinality") or 0, *map(most, node["children"])])

        self.most_rows = most(plan)
        return done


def test_the_indication_step_grows_with_the_indications_given_not_the_rules_terms(
    table, groups, tmp_path
):
    """Each indication is looked up among the rules' terms by equality, so no step of the query
    holds more rows than the indications given: 2,000 records giving 5 each, against rules of
    1,000 terms per code, never 2,000 x 5 x 2 codes x 1,000 terms, which on the whole release
    outgrew the build's memory and scratch disk."""
    records, given, terms = 2000, 5, 1000
    con = duckdb.connect()
    _drug_tables(con, {}, routes=False)
    for sql in (
        "INSERT INTO case_latest_T (era_T, primaryid, quarter_T, case_key_T) "
        "SELECT 'faers', 'm' || i, '2026q2', 'm' || i FROM range(?) t(i)",
        "INSERT INTO drug_substance_T SELECT 'faers', 'm' || i, '2026q2', '1', 'zelotolol' "
        "FROM range(?) t(i)",
        "INSERT INTO drug_latest_T SELECT 'faers', 'm' || i, '2026q2', '1', NULL, NULL, NULL, "
        "NULL, NULL, NULL, NULL FROM range(?) t(i)",
    ):
        con.execute(sql, [records])
    route.build(con)
    con.execute(
        "INSERT INTO indi_latest_T SELECT 'faers', 'm' || i, '2026q2', '1', 'Reason ' || j "
        "FROM range(?) t(i), range(?) u(j)",
        [records, given],
    )
    rules = [
        {
            "substance": "zelotolol",
            "code": "S01ZZ01",
            "indications": [f"eye {n}" for n in range(terms)],
        },
        {
            "substance": "zelotolol",
            "code": "C07ZZ01",
            "indications": ["reason 1", *[f"heart {n}" for n in range(terms)]],
        },
    ]
    profiled = _Profiled(con)
    with rules_with(tmp_path, {"atc-class-choice": {"indication_rules": rules}}):
        layer.build(profiled, table, groups)  # type: ignore[arg-type]
    assert profiled.most_rows is not None and profiled.most_rows <= records * given
    assert con.execute(
        "SELECT atc_code_T, atc_chosen_by_T, count(*) FROM atc_drug_T GROUP BY ALL"
    ).fetchall() == [("C07ZZ01", "indication", records)]


def test_dose_and_route_choose_before_the_indication(indicated):
    assert indicated["route_first"] == ("C07ZZ01", "route")
    assert indicated["dose_first"] == ("B01ZZ01", "dose")


def test_an_indication_counts_only_for_its_own_drug_and_a_code_of_that_drug(indicated):
    assert indicated["no_indication"] == (None, "cannot_tell")  # its case's other drug has one
    assert indicated["another_drugs_indication"] == ("J05ZZ01", "only_code")


# FDA's own words, then a group class (rule atc-index, rule atc-group-classes) -----------

GROUPS = [("invented group", "J05ZZ", "WHO's class for every invented antiviral")]
# drug record -> (case, substance, its rows, (FDA's drug name, FDA's active ingredient))
FDA_RECORDS = {
    "by_drug_name": ("f1", None, [(None, None, None)], ("PLENIVIR", None)),
    "drug_name_first": ("f1", "unlistedium", [(None, None, None)], ("DOSTAVIR", "PLENIVIR")),
    "by_active_ingredient": (
        "f2",
        "unlistedium",
        [("OPHTHALMIC", None, None)],
        ("BRAND X", "ZELOTOLOL"),
    ),
    "active_ingredient_dose": ("f2", None, [("ORAL", "75", "MG")], ("BRAND Y", "QUORPIRIN")),
    "active_ingredient_set": ("f3", None, [(None, None, None)], (None, "PLENIVIR\\DOSTAVIR")),
    "active_ingredients_split": (
        "f3",
        None,
        [(None, None, None)],
        (None, "PLENIVIR\\QUORPIRIN"),
    ),
    "kit_with_a_part_not_held": (
        "f4",
        None,
        [(None, None, None)],
        (None, "PLENIVIR\\ALCOHOL SWAB"),
    ),
    "name_in_part": ("f4", None, [(None, None, None)], ("PLENIVIR KIT", "PLENIVIR 300 MG")),
    "substance_first": ("f5", "zelotolol", [("ORAL", None, None)], ("DOSTAVIR", "DOSTAVIR")),
    "split_substance_first": (
        "f5",
        "plenivir;unlistedium",
        [(None, None, None)],
        (None, "DOSTAVIR"),
    ),
    "mix_code_by_name": ("f6", None, [("TOPICAL", None, None)], ("VELUCORT", None)),
    "group_word": ("f7", "invented group", [(None, None, None)], ("BRAND Z", None)),
    "group_word_named_by_fda": (
        "f7",
        "invented group",
        [(None, None, None)],
        ("BRAND Z", "DOSTAVIR"),
    ),
    "unlisted_group_word": ("f8", "other group", [(None, None, None)], (None, None)),
    "one_part_named_alone": ("f9", "pelacort", [(None, None, None)]),
}


def _groups(path, rows=GROUPS):
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows([("substance", "atc_code", "reason"), *rows])
    return path


@pytest.fixture
def fda_built(table, tmp_path):
    con = duckdb.connect()
    _drug_tables(con, FDA_RECORDS)
    choice = {"dose_rules": QUORPIRIN, "mix_classes": MIX_CLASSES}
    with rules_with(tmp_path, {"atc-class-choice": choice}):
        entry = layer.build(con, table, _groups(tmp_path / "groups.csv"))
    return con, entry


def _fda(con, name: str) -> tuple | None:
    seq = str(list(FDA_RECORDS).index(name) + 1)
    return con.execute(
        "SELECT atc_code_T, atc_level_T, atc_chosen_by_T, atc_matched_on_T FROM atc_drug_T "
        "WHERE drug_seq = ?",
        [seq],
    ).fetchone()


def _fda_codes(con, name: str) -> list[str]:
    seq = str(list(FDA_RECORDS).index(name) + 1)
    got = con.execute(
        "SELECT atc_code_T FROM atc_drug_codes_T WHERE drug_seq = ? ORDER BY 1", [seq]
    ).fetchall()
    return [c for (c,) in got]


@pytest.mark.parametrize(
    "name, expected",
    [
        ("by_drug_name", ("J05ZZ01", 5, "only_code", "drug_name")),
        ("drug_name_first", ("J05ZZ02", 5, "only_code", "drug_name")),
        ("by_active_ingredient", ("S01ZZ01", 5, "route", "active_ingredient")),
    ],
)
def test_a_record_its_substance_does_not_code_is_matched_by_fdas_drug_name_then_active_ingredient(
    fda_built, name, expected
):
    con, _ = fda_built
    assert _fda(con, name) == expected


def test_dose_and_route_choose_for_a_record_fdas_words_matched(fda_built):
    con, _ = fda_built
    assert _fda(con, "active_ingredient_dose") == ("B01ZZ01", 5, "dose", "active_ingredient")
    assert _fda_codes(con, "by_active_ingredient") == ["C07ZZ01", "S01ZZ01"]


def test_fdas_active_ingredients_are_a_set_only_when_every_part_is_a_name_the_table_holds(
    fda_built,
):
    con, _ = fda_built
    assert _fda(con, "active_ingredient_set") == (
        "J05ZZ51",
        5,
        "only_code",
        "active_ingredient_set",
    )
    assert _fda(con, "active_ingredients_split") == (
        None,
        None,
        "cannot_tell",
        "each_active_ingredient",
    )
    assert _fda_codes(con, "active_ingredients_split") == ["B01ZZ01", "J05ZZ01", "N02ZZ01"]
    assert _fda(con, "kit_with_a_part_not_held") is None  # plenivir alone is never read off it


def test_a_records_fda_words_are_the_ones_the_rxnorm_step_reads(table, groups, tmp_path):
    # FDA should write one drug name on every dose row of a record; where it wrote two, the
    # classes still read the one the RxNorm step reads, so the two never code it apart
    con = duckdb.connect()
    _drug_tables(con, {"two_names": ("f1", None, [(None, None, None)], ("PLENIVIR", None))})
    con.execute(
        "INSERT INTO drug_latest_T VALUES "
        "('faers', 'f1', '2026q2', '1', NULL, NULL, NULL, NULL, 'DOSTAVIR', NULL, NULL)"
    )
    choice = {"dose_rules": QUORPIRIN, "mix_classes": MIX_CLASSES}
    with rules_with(tmp_path, {"atc-class-choice": choice}):
        layer.build(con, table, groups)
    [(read,)] = con.execute(f"SELECT drug_name_T FROM ({FDA_WORDS})").fetchall()
    matched = con.execute("SELECT DISTINCT atc_ingredient_T FROM atc_drug_codes_T").fetchall()
    assert matched == [(read,)] == [("dostavir",)]


def test_fdas_words_are_never_matched_in_part(fda_built):
    con, _ = fda_built
    assert _fda(con, "name_in_part") is None


def test_fdas_words_are_read_only_when_the_substance_has_no_code(fda_built):
    con, _ = fda_built
    assert _fda(con, "substance_first") == ("C07ZZ01", 5, "route", "substance")
    assert _fda(con, "split_substance_first")[2:] == ("cannot_tell", "each_ingredient")


def test_a_single_name_from_fdas_words_never_takes_a_code_for_mixes(fda_built):
    con, _ = fda_built
    assert _fda(con, "mix_code_by_name") == ("D07ZZ01", 5, "only_code", "drug_name")
    assert _fda_codes(con, "mix_code_by_name") == ["D07ZZ01"]


def test_a_code_wHO_names_after_the_whole_product_is_not_read_as_one_for_mixes(fda_built):
    con, _ = fda_built
    assert _fda(con, "one_part_named_alone") == ("D07ZY02", 5, "only_code", "substance")


def test_a_group_word_gets_its_class_marked_as_a_group_class(fda_built):
    con, _ = fda_built
    assert _fda(con, "group_word") == ("J05ZZ", 4, "group_class", "substance")
    seq = str(list(FDA_RECORDS).index("group_word") + 1)
    assert con.execute(
        "SELECT atc_ingredient_T, atc_code_T, atc_level_T, atc_chosen_T FROM atc_drug_codes_T "
        "WHERE drug_seq = ?",
        [seq],
    ).fetchall() == [("invented group", "J05ZZ", 4, True)]


def test_fdas_words_come_before_a_group_class(fda_built):
    con, _ = fda_built
    assert _fda(con, "group_word_named_by_fda") == ("J05ZZ02", 5, "only_code", "active_ingredient")


def test_a_group_word_without_a_row_has_no_class(fda_built):
    con, _ = fda_built
    assert _fda(con, "unlisted_group_word") is None


def test_the_entry_records_the_group_classes_read(fda_built, tmp_path):
    _, entry = fda_built
    assert entry["groups"]["path"] == rulebook.value("atc-group-classes", "mapping")
    assert len(entry["groups"]["sha256"]) == 64


@pytest.mark.parametrize(
    "rows, match",
    [
        ([("invented group", "R03A", "")], "does not hold"),
        ([("invented group", "J", "")], "level 2 to 4"),
        ([("invented group", "J05ZZ01", "")], "level 2 to 4"),
        ([("invented group", "J05ZZ", ""), ("Invented Group ", "J05Z", "")], "twice"),
    ],
)
def test_group_classes_the_table_does_not_hold_of_another_level_or_listed_twice_are_refused(
    table, tmp_path, rows, match
):
    con = duckdb.connect()
    _drug_tables(con, FDA_RECORDS)
    with pytest.raises(layer.LayerRefused, match=match):
        layer.build(con, table, _groups(tmp_path / "groups.csv", rows))


# when the layer is absent ------------------------------------------------------------


def test_without_the_table_nothing_is_written_and_the_entry_says_why(tmp_path):
    con = duckdb.connect()
    _drug_tables(con)
    entry = layer.build(con, tmp_path / "missing.csv")
    assert entry["present"] is False and "no class table" in entry["reason"]
    assert not con.execute(
        "SELECT * FROM duckdb_tables() WHERE starts_with(table_name, 'atc_')"
    ).fetchall()


def test_switched_off_in_a_persons_rules_nothing_is_written_and_the_entry_says_so(table, groups):
    con = duckdb.connect()
    _drug_tables(con)
    with rulebook.use_user_rules(rulebook.UserRules(off=frozenset({"atc-index"}))):
        entry = layer.build(con, table, groups)
    assert entry == {
        "present": False,
        "source": rulebook.value("atc-index", "source"),
        "reason": "switched off in your rules",
    }
    assert not con.execute(
        "SELECT * FROM duckdb_tables() WHERE starts_with(table_name, 'atc_')"
    ).fetchall()
    assert layer.build(con, table, groups)["present"]  # Altio's standard builds them


def test_without_substances_nothing_is_written_and_the_entry_says_why(table):
    con = duckdb.connect()
    entry = layer.build(con, table)
    assert entry["present"] is False and layer.SUBSTANCES in entry["reason"]


def test_a_table_of_another_index_year_is_refused(tmp_path):
    con = duckdb.connect()
    _drug_tables(con)
    with pytest.raises(layer.LayerRefused, match="index years"):
        layer.build(con, write_classes(tmp_path / "old.csv", year=YEAR - 1))
