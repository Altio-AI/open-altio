"""The labels step: FDA labels in, one per ingredient and route family, safety sections as lines.

Built from the invented labels folder in open_altio.testing.fakelabels.
"""

from __future__ import annotations

import io
import json
import zipfile

import duckdb
import httpx
import pytest

from open_altio import rulebook
from open_altio.faers import build_release, route
from open_altio.faers.labels import choose, fetch
from open_altio.faers.labels.build import LABEL_TABLES, build_labels
from open_altio.faers.labels.folder import LabelsFolderError, find
from open_altio.faers.labels.lookup import LabelLookup
from open_altio.faers.labels.spl import LabelFacts
from open_altio.faers.route import label_families
from open_altio.rulebook import UserRules
from open_altio.testing import fakelabels as fake
from open_altio.testing.rules import rules_with

L = fake.labels()
(
    ZENTORA,
    ZEN_ANDA,
    ZEN_EYE,
    ZEN_OLD,
    VALMOREX,
    ZENVAL,
    QUORBITAL,
    UNMAPPED,
    ZEN_SILENT,
    ZEN_KIT,
    VALMORA_KIT,
    TEDURA_KIT,
    PLOVIRA,
    LUMETRA,
    ZEN_UNMAPPED,
    ZEN_NEAR_NAME,
    LID_PATCH,
    LID_EYE,
    LID_MOUTH,
    DIC_GEL,
    DIC_PATCH,
    DIC_EYE,
) = (x.set_id for x in L)
SEPARATOR = rulebook.value("label-sections", "cell_separator")


@pytest.fixture(scope="module")
def labels_folder(tmp_path_factory):
    return fake.write_labels(tmp_path_factory.mktemp("labels"))


@pytest.fixture(scope="module")
def built(labels_folder):
    return build_labels(labels_folder)


def _lines(built, set_id):
    return [r for r in built.sections.to_pylist() if r["setid_T"] == set_id]


def _chosen(table, **where):
    rows = [r for r in table.to_pylist() if all(r[k] == v for k, v in where.items())]
    assert len(rows) == 1, (where, rows)
    return rows[0]


# --------------------------------------------------------------- sections
def test_sections_are_found_by_code_keep_subsections_and_skip_highlights_and_pictures(
    built,
):
    got = [(r["section_T"], r["text_T"]) for r in _lines(built, ZENTORA) if not r["is_table_row_T"]]
    assert got == [
        ("boxed_warning", "WARNING: SERIOUS LIVER INJURY"),
        ("boxed_warning", "Zentora can cause severe liver injury."),
        ("indications", "1 INDICATIONS AND USAGE"),
        ("indications", "Zentora is indicated for chronic plaque fatigue."),
        ("contraindications", "4 CONTRAINDICATIONS"),
        ("contraindications", "• Known hypersensitivity to zentoprine"),
        ("warnings_and_precautions", "5 WARNINGS AND PRECAUTIONS"),
        ("warnings_and_precautions", "5.1 Hepatotoxicity"),
        ("warnings_and_precautions", "Monitor liver tests. Stop if jaundice."),
        ("adverse_reactions", "6 ADVERSE REACTIONS"),
        ("adverse_reactions", "Table 1 lists reactions."),
        ("adverse_reactions", "Table 1: Adverse reactions in 2% or more"),
    ]
    texts = " ".join(r["text_T"] for r in built.sections.to_pylist())
    assert "Highlights copy" not in texts  # the short repeat of a full section
    assert "Not read." not in texts  # dosage is not a wanted section
    loinc = {str(k): v for k, v in rulebook.value("label-sections", "sections").items()}
    assert all(loinc[r["loinc_T"]] == r["section_T"] for r in built.sections.to_pylist())


def test_a_subsection_with_its_own_wanted_code_belongs_to_that_code(built):
    rows = _lines(built, ZEN_EYE)
    by_text = {r["text_T"]: r["section_T"] for r in rows}
    assert by_text["Avoid strong inhibitors."] == "precautions"  # kept with its parent
    assert by_text["Dizziness."] == "adverse_reactions"  # not counted under precautions too
    assert [r["ordinal_T"] for r in rows] == list(range(1, len(rows) + 1))


def test_each_table_row_is_one_line_with_its_cells_joined(built):
    rows = [r["text_T"] for r in _lines(built, ZENTORA) if r["is_table_row_T"]]
    head, *body = rows
    assert head.split(SEPARATOR) == [
        "",
        "Zentora N=100",
        "Placebo N=100",
    ]  # empty cell kept
    assert body == [
        SEPARATOR.join(["Nausea*", "12%", "3%"]),
        SEPARATOR.join(["Headache", "8%", "7%"]),
        "* Includes nausea and vomiting",  # the foot comes after the body, as printed
    ]


# --------------------------------------------------------------- choice
def _family(built, rxcui, family):
    return _chosen(built.candidates, rxcui_T=rxcui, route_family_T=family)


def test_one_label_per_ingredient_and_family_the_recent_originator(built):
    zen = _family(built, fake.ZENTOPRINE, "by_mouth")
    # over a newer ANDA and an old copy with a lower number
    assert zen["setid_T"] == ZENTORA
    assert zen["application_T"] == "NDA"
    assert zen["ingredient_T"] == "zentoprine"
    assert zen["routes_T"] == ["ORAL"]
    assert zen["dosage_form_T"] == ["TABLET, FILM COATED"]
    assert "NDA before ANDA" in zen["chosen_because_T"]
    assert ZEN_OLD not in {r["setid_T"] for r in built.candidates.to_pylist()}


def test_each_route_family_has_its_own_label_and_there_is_no_default(built):
    """A label is a candidate in every family the shared route table gives its routes:
    the tablets' ORAL is by mouth or under the tongue, and the eye drop's OPHTHALMIC is the
    eye or an injection into it. The eye drop has the lowest recent NDA, as MAXIDEX has for
    dexamethasone, so it is the eye's label; the injected family's is the injection, whose
    INTRAVENOUS route is that family alone."""
    rows = [r for r in built.candidates.to_pylist() if r["rxcui_T"] == fake.ZENTOPRINE]
    by_family = {r["route_family_T"]: r["setid_T"] for r in rows}
    assert by_family == {
        "by_mouth": ZENTORA,
        "under_tongue": ZENTORA,
        "eye": ZEN_EYE,
        "injected": ZEN_KIT,
    }
    assert (
        "its route is closest to injected"
        in _family(built, fake.ZENTOPRINE, "injected")["chosen_because_T"]
    )
    assert "no_route_default_T" not in built.candidates.column_names
    # the families FAERS drug records get, from the same table, so the two join
    for r in built.candidates.to_pylist():
        assert r["route_family_T"] in label_families(r["routes_T"])


def test_forms_differ_when_two_families_labels_have_different_safety_sections(built):
    zen = {
        r["forms_differ_T"] for r in built.candidates.to_pylist() if r["rxcui_T"] == fake.ZENTOPRINE
    }
    assert zen == {True}  # the tablets' and the eye drop's sections differ
    # VALMORA's one label serves both its families, so they cannot disagree
    val = [r for r in built.candidates.to_pylist() if r["rxcui_T"] == fake.VALMOREX]
    assert {r["route_family_T"] for r in val} == {"by_mouth", "under_tongue", "injected"}
    assert {r["setid_T"] for r in val} == {VALMORA_KIT}
    assert {r["forms_differ_T"] for r in val} == {False}
    rows = built.candidates.to_pylist()
    several = {k for k in {r["rxcui_T"] for r in rows} if sum(r["rxcui_T"] == k for r in rows) > 1}
    assert built.summary["with_several_families"] == len(several)
    assert built.summary["several_families_forms_differ"] == 2  # zentoprine's and diclorin's


def test_a_kits_alcohol_pad_adds_no_route_family(built):
    """ZEN_KIT is a pharmacy's kit with a swab, as NEUROMAQUEL is for
    dexamethasone, and VALMORA an originator's kit with an alcohol pad, as
    HUMIRA is: the pads' topical route gives neither ingredient a skin label."""
    pads = {x.set_id for x in L if x.pad_route}
    assert {ZENTORA, ZEN_KIT, VALMORA_KIT} <= pads
    families = {(r["rxcui_T"], r["route_family_T"]) for r in built.candidates.to_pylist()}
    assert (fake.ZENTOPRINE, "skin") not in families
    assert (fake.VALMOREX, "skin") not in families
    # the pad's route is not the drug's
    assert _family(built, fake.VALMOREX, "injected")["routes_T"] == [
        "INTRAVENOUS",
        "ORAL",
    ]
    assert _family(built, fake.ZENTOPRINE, "by_mouth")["routes_T"] == ["ORAL"]
    # the pharmacy kit's own route list repeats its pad's route, as real kits do
    kit = next(x for x in L if x.set_id == ZEN_KIT)
    assert "TOPICAL" in kit.routes
    facts = LabelFacts(
        kit.set_id,
        1,
        kit.title,
        kit.effective,
        "",
        (),
        kit.routes,
        route_parts=(("TOPICAL", ("isopropyl alcohol",)), *((r, None) for r in kit.routes)),
    )
    assert choose.Policy.read().routes_of(facts) == ("INTRAVENOUS", "ORAL")


def test_a_label_routes_families_come_from_the_shared_route_table():
    policy = choose.Policy.read()
    patch = LabelFacts("p", 1, "p", policy.recent_from, "", (), ("TRANSDERMAL", "ORAL"))
    assert policy.families_of(patch) == set(label_families(["TRANSDERMAL", "ORAL"]))
    assert policy.unplaced(patch) == []


def test_a_route_the_shared_table_lacks_gives_no_family_and_is_listed(built):
    """No family is made up for a route the table does not hold: the label is kept under
    the unknown key, read only where a record's own families have no label, and the route
    is listed for the table's review. So is a label naming no route."""
    policy = choose.Policy.read()
    facts = LabelFacts("x", 1, "x", policy.recent_from, "", (), ("NOT A ROUTE",))
    assert policy.families_of(facts) == {policy.no_family} == {route.families()[-1]}
    assert policy.unplaced(facts) == ["NOT A ROUTE"]
    no_route = LabelFacts("y", 1, "y", policy.recent_from, "", (), ())
    assert policy.families_of(no_route) == {policy.no_family}
    assert built.summary["routes_not_in_route_table"] == {}
    assert built.summary["labels_with_no_route_family"] == {"labels": 0, "ingredients": 0}


def test_a_label_whose_safety_sections_hold_no_words_is_set_aside(built):
    """ZEN_SILENT has the lowest NDA number but files every section as unclassified."""
    assert _family(built, fake.ZENTOPRINE, "by_mouth")["setid_T"] == ZENTORA
    assert ZEN_SILENT not in {r["setid_T"] for r in built.candidates.to_pylist()}
    assert built.summary["labels_without_safety_text"] == 2  # it and QUORBITAL's


def test_a_pharmacy_kit_loses_to_its_own_products_label(built):
    """ZEN_KIT carries a lower NDA number than ZENTORA (another drug's in the
    bundle) and the generic's ANDA, whose own label is not a kit: the case of
    dexamethasone's injection in a pharmacy's kit."""
    assert _family(built, fake.ZENTOPRINE, "by_mouth")["setid_T"] == ZENTORA
    assert _family(built, fake.ZENTOPRINE, "under_tongue")["setid_T"] == ZENTORA
    # the only label whose route is injected alone is the kit, so the kit stays for that family
    iv = _family(built, fake.ZENTOPRINE, "injected")
    assert iv["setid_T"] == ZEN_KIT
    assert iv["dosage_form_T"] == [rulebook.value("label-choice", "kit_form")]


def test_in_each_family_a_route_of_that_family_alone_beats_a_broad_one(built):
    """LIDODERMA's patch is TOPICAL, which the shared table lets be nine families, and has
    the lowest NDA; the eye gel and the mouth solution name their family more closely, as
    lidocaine's do. DICLORA's gel is TOPICAL too; its patch is TRANSDERMAL and its eye drops
    OPHTHALMIC, as diclofenac's are."""
    lid = {
        r["route_family_T"]: r
        for r in built.candidates.to_pylist()
        if r["rxcui_T"] == fake.LIDORINE
    }
    assert lid["eye"]["setid_T"] == LID_EYE
    assert lid["under_tongue"]["setid_T"] == LID_MOUTH
    assert lid["skin"]["setid_T"] == LID_PATCH  # no closer label reaches the skin
    assert "its route is closest to eye" in lid["eye"]["chosen_because_T"]
    dic = {
        r["route_family_T"]: r
        for r in built.candidates.to_pylist()
        if r["rxcui_T"] == fake.DICLORIN
    }
    assert dic["transdermal"]["setid_T"] == DIC_PATCH
    assert dic["eye"]["setid_T"] == DIC_EYE
    assert dic["ear"]["setid_T"] == DIC_GEL  # only the broad route reaches the ear
    policy = choose.Policy.read()
    patch = LabelFacts("p", 1, "p", policy.recent_from, "", (), ("TOPICAL",))
    assert policy.reach(patch, "eye") == len(label_families(["TOPICAL"])) > 1


def test_an_originator_sold_only_as_kits_stays_the_originator(built):
    """VALMORA is valmorex's NDA, sold only as kits, as HUMIRA is; the generic
    has its own ANDA, so the kit is not a pharmacy's and wins as originator."""
    oral = _family(built, fake.VALMOREX, "by_mouth")
    assert oral["setid_T"] == VALMORA_KIT
    assert "NDA before ANDA" in oral["chosen_because_T"]
    assert VALMOREX in {x.set_id for x in L if x.category == "ANDA"}


def test_the_lookup_gives_a_familys_label_or_every_familys(built):
    lookup = LabelLookup.from_rows(built.candidates.to_pylist())
    zen = fake.ZENTOPRINE
    assert lookup.set_id(zen, "eye") == ZEN_EYE
    assert lookup.set_id(zen, "by_mouth") == ZENTORA
    assert lookup.set_id(zen, "skin") is None  # no skin label: no guess
    assert lookup.families(zen) == {
        "by_mouth": ZENTORA,
        "under_tongue": ZENTORA,
        "eye": ZEN_EYE,
        "injected": ZEN_KIT,
    }
    assert lookup.forms_differ(zen) and not lookup.forms_differ(fake.VALMOREX)
    assert lookup.families(fake.NOT_IN_RXNORM) == {}  # no label is an outcome


def test_the_lookup_reads_a_built_release(fake_input, labels_folder, tmp_path):
    lookup = LabelLookup.read(build_release(fake_input, tmp_path, labels=labels_folder))
    assert lookup.set_id(fake.ZENTOPRINE, "eye") == ZEN_EYE
    assert lookup.forms_differ(fake.ZENTOPRINE)


def test_a_kits_alcohol_pad_does_not_make_a_label_a_combination(built):
    """ZENTORA's label is also mapped to the alcohol pad in its kit."""
    assert fake.PAD_PRODUCT in next(x.products for x in L if x.set_id == ZENTORA)
    assert _family(built, fake.ZENTOPRINE, "by_mouth")["setid_T"] == ZENTORA
    assert fake.PAD not in {r["rxcui_T"] for r in built.candidates.to_pylist()}


def test_a_kits_ethanol_pad_neither_makes_a_combination_nor_a_skin_label(
    built, labels_folder, tmp_path
):
    """TEDURA is mapped to its vial and to the ethanol pad in its kit, as GATTEX is, and the
    label writes the pad's ingredient as alcohol: it is teduvarin's injected label alone."""
    aside = rulebook.value("label-choice", "not_counted_beside_others")
    assert {"ethanol", "alcohol"} <= set(aside)
    rows = [r for r in built.candidates.to_pylist() if r["setid_T"] == TEDURA_KIT]
    assert [(r["rxcui_T"], r["route_family_T"]) for r in rows] == [(fake.TEDUVARIN, "injected")]
    without = [n for n in aside if n not in ("ethanol", "alcohol")]
    with rules_with(tmp_path, {"label-choice": {"not_counted_beside_others": without}}):
        again = build_labels(labels_folder)
    assert TEDURA_KIT not in {r["setid_T"] for r in again.candidates.to_pylist()}
    assert again.summary["rxnorm_keys"]["no_min"] == built.summary["rxnorm_keys"]["no_min"] + 1


def test_a_label_the_mapping_file_misses_is_keyed_by_its_own_ingredients(built):
    """PLOVIRA is missing from the mapping file, as TECENTRIQ is; LUMETRA is mapped only to a
    code RxNorm no longer holds, as an old AVANDIA label is, and lists its salt with the
    moiety. Each takes the code its own ingredient names."""
    plovira = _family(built, fake.PLOVIZUMAB, "injected")
    assert (plovira["setid_T"], plovira["keyed_by_T"]) == (PLOVIRA, choose.OWN_INGREDIENTS)
    lumetra = _family(built, fake.LUMETRINE, "by_mouth")
    assert (lumetra["setid_T"], lumetra["keyed_by_T"]) == (LUMETRA, choose.OWN_INGREDIENTS)
    assert _family(built, fake.ZENTOPRINE, "by_mouth")["keyed_by_T"] == choose.MAPPING_FILE
    assert built.summary["keyed_by_own_ingredients"] == {
        "labels": 2,
        "ingredients_with_label": 2,
        "labels_chosen": 2,
        "labels_chosen_before_recent_from": 1,  # LUMETRA's, the only one its ingredient has
    }


def test_a_labels_own_ingredients_never_add_a_label_beside_a_mapped_one_nor_guess(built):
    """ZEN_UNMAPPED lists zentoprine, which mapped labels already reach; ZEN_NEAR_NAME lists a
    name one letter from it; UNMAPPED lists no ingredient at all."""
    keyed = {r["setid_T"] for r in built.candidates.to_pylist()}
    assert not {ZEN_UNMAPPED, ZEN_NEAR_NAME, UNMAPPED} & keyed
    zen = [r for r in built.candidates.to_pylist() if r["rxcui_T"] == fake.ZENTOPRINE]
    assert {r["keyed_by_T"] for r in zen} == {choose.MAPPING_FILE}


def test_switched_off_a_label_the_mapping_file_misses_stays_without_a_code(labels_folder):
    off = UserRules(off=frozenset({"label-own-ingredients"}))
    with rulebook.use_user_rules(off):
        again = build_labels(labels_folder)
    keyed = {r["setid_T"] for r in again.candidates.to_pylist()}
    assert not {PLOVIRA, LUMETRA} & keyed
    assert again.summary["keyed_by_own_ingredients"]["labels"] == 0


def test_an_old_label_wins_only_when_nothing_newer_exists(built, labels_folder, tmp_path):
    quorbital = _family(built, fake.QUORBITAL, "by_mouth")
    assert quorbital["setid_T"] == QUORBITAL
    assert quorbital["application_T"] == "other"
    old = next(x for x in L if x.set_id == ZEN_OLD)
    with rules_with(tmp_path, {"label-choice": {"recent_from": old.effective}}):
        again = build_labels(labels_folder)
    zen = _family(again, fake.ZENTOPRINE, "by_mouth")
    assert zen["setid_T"] == ZEN_OLD
    assert "lowest application number" in zen["chosen_because_T"]  # NDA019000 over NDA020001


def test_a_combination_is_judged_against_its_own_label_not_its_ingredients(built):
    combo = _family(built, fake.ZEN_VAL, "by_mouth")
    assert combo["setid_T"] == ZENVAL
    others = {r["setid_T"] for r in built.candidates.to_pylist() if r["rxcui_T"] != fake.ZEN_VAL}
    assert ZENVAL not in others  # never zentoprine's or valmorex's label
    read = {r["setid_T"] for r in built.sections.to_pylist()}
    assert {ZEN_EYE, ZEN_KIT, ZENVAL} <= read  # every family's label is read


def test_labels_with_no_code_unreadable_or_unclassified_are_counted_not_guessed(built):
    s = built.summary
    assert s["labels_read"] == len(L)
    assert s["unreadable"] == 1
    # UNMAPPED, and the four labels the mapping file misses or maps to a code RxNorm lacks
    assert s["rxnorm_keys"]["no_code"] == 5
    assert UNMAPPED not in {r["setid_T"] for r in built.candidates.to_pylist()}
    assert s["without_safety_sections"] == 1
    assert s["without_safety_sections_filing_unclassified"] == 1
    assert _lines(built, QUORBITAL) == []  # its headings say WARNINGS, its codes do not


def test_the_tables_have_the_agreed_columns(built):
    """Every column ends in the derived suffix, values copied from DailyMed and
    RxNorm included (rule transformed-suffix-T)."""
    assert built.candidates.column_names == [
        "rxcui_T",
        "ingredient_T",
        "route_family_T",
        "setid_T",
        "spl_version_T",
        "title_T",
        "effective_date_T",
        "application_T",
        "routes_T",
        "dosage_form_T",
        "chosen_because_T",
        "forms_differ_T",
        "keyed_by_T",
    ]
    assert built.sections.column_names == [
        "setid_T",
        "section_T",
        "loinc_T",
        "ordinal_T",
        "is_table_row_T",
        "text_T",
    ]
    suffix = rulebook.value("transformed-suffix-T", "derived_suffix")
    for table in (built.candidates, built.sections):
        assert all(c.endswith(suffix) for c in table.column_names)
    assert str(built.candidates.schema.field("effective_date_T").type) == "date32[day]"
    applications = {r["application_T"] for r in built.candidates.to_pylist()}
    assert applications <= {"NDA", "BLA", "ANDA", "other"}


# --------------------------------------------------------------- the folder and the release
def test_a_folder_missing_a_file_is_refused_by_name(tmp_path):
    with pytest.raises(LabelsFolderError, match=rulebook.value("label-source", "mapping_file")):
        find(tmp_path)


def test_the_command_refuses_a_labels_folder_missing_a_file(fake_input, tmp_path, capsys):
    from open_altio.faers.__main__ import main

    code = main(
        [
            "build",
            "--input",
            str(fake_input),
            "--out",
            str(tmp_path / "out"),
            "--labels",
            str(tmp_path),
        ]
    )
    assert code == 2
    assert "refused: labels folder" in capsys.readouterr().err
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())


def test_a_release_with_no_labels_folder_skips_the_step_and_says_so(fake_input, tmp_path):
    said: list[str] = []
    path = build_release(fake_input, tmp_path, say=said.append)
    manifest = json.loads((path / "manifest.json").read_text())
    assert "labels: skipped, no labels folder given" in said
    assert manifest["labels"] == {"skipped": "no labels folder given"}
    assert not set(LABEL_TABLES) & set(manifest["tables"])


def test_a_label_rule_switched_off_leaves_labels_out_and_says_so(
    fake_input, labels_folder, tmp_path
):
    said: list[str] = []
    rules = UserRules(off=frozenset({"label-choice"}))
    path = build_release(
        fake_input, tmp_path, labels=labels_folder, user_rules=rules, say=said.append
    )
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["labels"] == {"skipped": "rule label-choice switched off"}
    assert "labels: skipped, rule label-choice switched off" in said
    assert not set(LABEL_TABLES) & set(manifest["tables"])


def test_a_release_with_a_labels_folder_writes_the_label_tables(
    fake_input, labels_folder, tmp_path
):
    path = build_release(fake_input, tmp_path, labels=labels_folder)
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["labels"]["labels_read"] == len(L)
    for table in LABEL_TABLES:
        entry = manifest["tables"][table]
        assert entry["kind"] == "derived"
        rows = duckdb.sql(f"SELECT count(*) FROM '{path / entry['path']}'").fetchone()
        assert rows is not None and rows[0] == entry["rows"] > 0


# --------------------------------------------------------------- fetch
def _zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("a.txt", "label")
    return buffer.getvalue()


def test_a_download_carries_on_from_a_partial_file(tmp_path):
    body = _zip()
    asked = []

    def serve(request: httpx.Request) -> httpx.Response:
        asked.append(request.headers.get("range"))
        start = int(request.headers["range"].split("=")[1].rstrip("-"))
        return httpx.Response(206, content=body[start:])

    target = tmp_path / "part.zip"
    (tmp_path / "part.zip.part").write_bytes(body[:10])
    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        assert fetch.download(client, "https://example.org/part.zip", target, len(body))
        assert not fetch.download(client, "https://example.org/part.zip", target, len(body))
    assert target.read_bytes() == body and asked == ["bytes=10-"]


def test_a_download_that_is_not_a_zip_is_refused_and_not_kept(tmp_path):
    page = b"<html>not found</html>"
    serve = httpx.MockTransport(lambda r: httpx.Response(200, content=page))
    with (
        httpx.Client(transport=serve) as c,
        pytest.raises(OSError, match="not a whole zip"),
    ):
        fetch.download(c, "https://example.org/part.zip", tmp_path / "part.zip", len(page))
    assert list(tmp_path.iterdir()) == []
