"""The filtered export (GET /api/export): exactly the cases the page selects,
with their drugs and reactions, in a file that cannot be mistaken for the
full release (rules export-csv-row-cap and filtered-vs-full-export).

What each export should hold is read from the release's own Parquet through
`rel` (case_latest_T and its child _latest_T tables). The CSV cap is read
from the rule; to pass it without millions of rows a test runs under
rules_with, a copy of the rules where the cap is low.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from urllib.parse import parse_qs, urlencode

from open_altio.explorer import filters as F
from open_altio.rulebook import value
from open_altio.testing import fakefda
from open_altio.testing.fakelabelflags import LABELS_AS_OF
from open_altio.testing.rules import rules_with

MANIFEST_KEYS = {
    "kind",
    "note",
    "release",
    "exported_at",
    "format",
    "rows",
    "files",
    "query",
    "filters",
    "described",
}


def marker() -> str:
    return value("filtered-vs-full-export", "filtered_filename_marker")


def manifest_name() -> str:
    return value("filtered-vs-full-export", "filtered_manifest")


def product_cases(rel, ingredient: str) -> set[str]:
    """era/case_key of the kept cases naming a product containing `ingredient` as primary or
    secondary suspect."""
    return rel.case_keys(
        "EXISTS (SELECT 1 FROM drug_latest_T d JOIN drug_substance_T s "
        f"USING (era_T, primaryid, quarter_T, drug_seq) WHERE {rel.case_join('d')} "
        "AND d.role_cod IN ('PS', 'SS') AND list_contains(string_split(s.substance_T, ';'), ?))",
        ingredient,
    )


def child_rows(rel, table: str, cases: set[str]) -> int:
    rows = rel.rows(
        f"SELECT c.era_T, c.case_key_T FROM case_latest_T c JOIN {table} d ON {rel.case_join('d')}"
    )
    return sum(1 for e, k in rows if f"{e}/{k}" in cases)


def largest_csv_lines(rel, cases: set[str]) -> int:
    """Lines in the biggest CSV of an export of `cases`, header included."""
    return (
        max(
            len(cases),
            child_rows(rel, "drug_latest_T", cases),
            child_rows(rel, "reac_latest_T", cases),
        )
        + 1
    )


def sizes(client, **params) -> dict:
    """What the page asks before offering CSV: rows in each file (/api/exportsize)."""
    got = client.get("/api/exportsize?" + urlencode(params, doseq=True))
    assert got.status_code == 200, got.text
    return got.json()


def csv_fits(client, **params) -> bool:
    return max(sizes(client, **params).values()) + 1 <= value("export-csv-row-cap", "csv_row_cap")


def export(client, fmt: str, **params):
    return client.get("/api/export?" + urlencode({**params, "format": fmt}, doseq=True))


def unzip(response) -> tuple[str, dict[str, bytes]]:
    """The zip's single folder name and its files by name."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(response.content))
    folders = {n.split("/")[0] for n in z.namelist()}
    assert len(folders) == 1, z.namelist()
    folder = folders.pop()
    return folder, {n.split("/", 1)[1]: z.read(n) for n in z.namelist()}


def csv_rows(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def keys(rows: list[dict]) -> list[str]:
    return [f"{r['era_T']}/{r['case_key_T']}" for r in rows]


# what the page is told -----------------------------------------------------------------------


def test_the_page_is_told_the_rows_each_file_will_hold(client, rel):
    want = rel.case_keys("coalesce(c.occr_country, c.reporter_country) IN ('CA', 'CANADA')")
    got = sizes(client, country="CA")
    assert got == {
        "cases": len(want),
        "drugs": child_rows(rel, "drug_latest_T", want),
        "reactions": child_rows(rel, "reac_latest_T", want),
    }
    _, files = unzip(export(client, "csv", country="CA"))
    assert len(csv_rows(files["cases.csv"])) == got["cases"]
    assert len(csv_rows(files["drugs.csv"])) == got["drugs"]
    assert len(csv_rows(files["reactions.csv"])) == got["reactions"]


# what the export holds -------------------------------------------------------------------


def test_csv_export_holds_exactly_the_filtered_cases_and_their_drugs_and_reactions(client, rel):
    want = rel.case_keys("coalesce(c.occr_country, c.reporter_country) IN ('CA', 'CANADA')")
    assert want
    _, files = unzip(export(client, "csv", country="CA"))
    assert set(files) == {"cases.csv", "drugs.csv", "reactions.csv", manifest_name()}
    assert sorted(keys(csv_rows(files["cases.csv"]))) == sorted(want)
    drugs, reacs = csv_rows(files["drugs.csv"]), csv_rows(files["reactions.csv"])
    assert set(keys(drugs)) <= want and set(keys(reacs)) <= want
    assert len(drugs) == child_rows(rel, "drug_latest_T", want)
    assert len(reacs) == child_rows(rel, "reac_latest_T", want)
    assert "drugname" in drugs[0] and "pt" in reacs[0]


def test_parquet_export_holds_exactly_the_filtered_cases(client, rel, parquet_rows):
    want = rel.case_keys("c.sex = 'M'")
    _, files = unzip(export(client, "parquet", sex="M"))
    assert sorted(keys(parquet_rows(files["cases.parquet"]))) == sorted(want)
    drugs = parquet_rows(files["drugs.parquet"])
    assert len(drugs) == child_rows(rel, "drug_latest_T", want)
    reacs = parquet_rows(files["reactions.parquet"])
    assert len(reacs) == child_rows(rel, "reac_latest_T", want)


def test_a_products_cases_export_with_their_drugs_and_reactions(client, rel, parquet_rows):
    want = product_cases(rel, "acetylsalicylic acid")
    assert want
    _, files = unzip(export(client, "parquet", product="acetylsalicylic acid"))
    assert set(files) == {"cases.parquet", "drugs.parquet", "reactions.parquet", manifest_name()}
    cases = parquet_rows(files["cases.parquet"])
    assert set(keys(cases)) == want and len(cases) == len(want)
    counted = sizes(client, product="acetylsalicylic acid")
    drugs = parquet_rows(files["drugs.parquet"])
    assert len(drugs) == counted["drugs"] and set(keys(drugs)) == want
    assert len(parquet_rows(files["reactions.parquet"])) == counted["reactions"]


def test_name_carries_filtered_the_release_and_the_time(client, rel, clock):
    response = export(client, "csv", sex="F")
    name = f"{marker()}_{rel.manifest['release']}_{clock.now().strftime('%Y%m%dT%H%M%SZ')}"
    assert f'filename="{name}.zip"' in response.headers["content-disposition"]
    folder, _ = unzip(response)
    assert folder == name


def test_manifest_records_filters_release_time_counts_and_that_it_is_filtered(client, rel, clock):
    query = {"drug": "aspirin", "sex": ["F", "M"], "dedup": "all"}
    _, files = unzip(export(client, "csv", **query))
    manifest = json.loads(files[manifest_name()])
    filters = F.parse(parse_qs(urlencode(query, doseq=True)))
    no_scope = {
        "product": None,
        "reactions": [],
        "reactions_counted": {"counted_by": "fda_text", "meddra_version": None},
        "smqs": [],
        "reactions_left_out": [],
        "drugs": [],
        "classes": None,
    }
    assert manifest["filters"] == filters.manifest()["filters"] | no_scope
    assert manifest["query"] == urlencode(query, doseq=True)
    assert manifest["described"] == filters.manifest()["described"]
    assert manifest["release"] == rel.manifest["release"]
    assert manifest["exported_at"] == clock.now().isoformat()
    assert manifest["format"] == "csv"
    assert manifest["rows"]["cases"] == len(csv_rows(files["cases.csv"]))
    assert manifest["rows"]["drugs"] == len(csv_rows(files["drugs.csv"]))
    assert manifest["rows"]["reactions"] == len(csv_rows(files["reactions.csv"]))
    assert marker() in manifest["note"] and "not the full release" in manifest["note"]
    # LocalAccess adds no terms of use; WHO's citation comes with the classes a release carries
    classes = {"classes"} if (rel.manifest.get("classes") or {}).get("present") else set()
    assert set(manifest) == MANIFEST_KEYS | classes


def test_the_manifest_names_the_product_as_counted_and_the_reactions_in_words(client, rel):
    asked = {
        "product": "valsartan",
        "prole": ["PS", "C"],
        "exclude": "ENTRESTO",
        "pt": ["Headache"],
    }
    _, files = unzip(export(client, "csv", **asked, sex="F"))
    manifest = json.loads(files[manifest_name()])
    assert (
        "Product: Valsartan, any product containing it, as PS (Primary suspect) or C (Concomitant);"
        " spellings left out: ENTRESTO"
    ) in manifest["described"]
    assert "Reactions: Headache" in manifest["described"]
    assert any(line.startswith("Sex: F") for line in manifest["described"])
    assert manifest["filters"]["product"] == {
        "drug": "valsartan",
        "unit": "any",
        "roles": ["PS", "C"],
        "spellings_left_out": ["ENTRESTO"],
        "spellings_added": [],
    }
    assert manifest["filters"]["reactions"] == ["Headache"]
    assert "format" not in manifest["query"] and "product=valsartan" in manifest["query"]


def test_the_manifest_names_the_drugs_filter_as_counted(client):
    asked = {"dprod": ["valsartan", "VALSARTAN TEVA"], "drole": "SS"}
    _, files = unzip(export(client, "csv", **asked))
    manifest = json.loads(files[manifest_name()])
    assert (
        "Drugs: Valsartan, any product containing it, as SS (Secondary suspect); VALSARTAN TEVA, "
        "FDA's spelling with no ingredient, as SS (Secondary suspect)"
    ) in manifest["described"]
    assert [d["drug"] for d in manifest["filters"]["drugs"]] == ["valsartan", None]


def test_an_smqs_export_names_it_in_words(licensed_client, client, rel):
    _, files = unzip(export(licensed_client, "csv", smq="96000001:narrow"))
    manifest = json.loads(files[manifest_name()])
    assert "SMQ: Invented bleeding events (SMQ) (96000001), narrow" in manifest["described"]
    assert manifest["filters"]["smqs"] == ["96000001:narrow"]
    reacs = f"EXISTS (SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')} AND r.pt = ?)"
    haemorrhage = rel.case_keys(reacs, "Haemorrhage")
    assert set(keys(csv_rows(files["cases.csv"]))) == haemorrhage
    assert export(client, "csv", smq="96000001:narrow").status_code == 403  # no MedDRA here
    # a term left out of the SMQ is named too
    _, files = unzip(export(licensed_client, "csv", smq="96000001:broad", pt_out="Nausea"))
    manifest = json.loads(files[manifest_name()])
    assert "Reactions left out: Nausea" in manifest["described"]
    assert manifest["filters"]["reactions_left_out"] == ["Nausea"]


def test_duplicates_follow_the_dedup_switch(client, rel):
    _, kept = unzip(export(client, "csv"))
    _, every = unzip(export(client, "csv", dedup="all"))
    assert sorted(keys(csv_rows(kept["cases.csv"]))) == sorted(rel.case_keys())
    assert len(csv_rows(every["cases.csv"])) == rel.rows("SELECT count(*) FROM case_latest_T")[0][0]


def test_cases_carry_the_shown_copy_the_rules_and_the_group_date(client):
    _, every = unzip(export(client, "csv", dedup="all"))
    rows = {r["case_key_T"]: r for r in csv_rows(every["cases.csv"])}
    aside, shown = rows["9020020"], rows["9021021"]
    assert (aside["dup_kept_T"], aside["dup_shown_case_T"], aside["dup_rule_T"]) == (
        "false",
        "9021021",
        "aeolus",
    )
    assert (shown["dup_other_cases_T"], shown["group_first_dt_T"], shown["first_fda_dt_T"]) == (
        "9020020",
        "2019-02-10",
        "2026-05-15",
    )
    # newest first by the date of the group, not of the copy
    dates = [r["group_first_dt_T"] for r in csv_rows(every["cases.csv"]) if r["group_first_dt_T"]]
    assert dates == sorted(dates, reverse=True)


def test_cases_carry_the_company_beside_fdas_sender(client, rel):
    _, every = unzip(export(client, "csv", dedup="all"))
    header = every["cases.csv"].decode("utf-8").splitlines()[0].split(",")
    assert header[header.index("mfr_sndr") + 1] == "company_T"
    rows = {r["case_key_T"]: r for r in csv_rows(every["cases.csv"])}
    want = dict(rel.rows("SELECT case_key_T, company_T FROM case_latest_T"))
    assert (rows["9120012"]["mfr_sndr"], rows["9120012"]["company_T"]) == (
        fakefda.LILLY[1],
        want["9120012"],
    )
    assert rows["9130013"]["company_T"] == ""


def test_an_unknown_format_is_refused(client):
    got = export(client, "xlsx")
    assert got.status_code == 400 and got.json()["problem"]


# the CSV cap -------------------------------------------------------------------------------


def test_csv_is_refused_above_the_cap_and_parquet_still_offered(
    client, rel, tmp_path, parquet_rows
):
    want = rel.case_keys()
    cap = largest_csv_lines(rel, want) - 1
    with rules_with(tmp_path, {"export-csv-row-cap": {"csv_row_cap": cap}}):
        assert not csv_fits(client)
        refused = export(client, "csv")
        assert refused.status_code == 409
        problem = refused.json()["problem"]
        assert (
            "Too large for CSV" in problem and f"{cap:,}" in problem and "Choose Parquet" in problem
        )
        _, files = unzip(export(client, "parquet"))
        assert sorted(keys(parquet_rows(files["cases.parquet"]))) == sorted(want)


def test_csv_is_offered_while_the_largest_file_fits_the_cap(client, rel, tmp_path):
    want = rel.case_keys()
    with rules_with(
        tmp_path, {"export-csv-row-cap": {"csv_row_cap": largest_csv_lines(rel, want)}}
    ):
        assert csv_fits(client)
        _, files = unzip(export(client, "csv"))
        assert sorted(keys(csv_rows(files["cases.csv"]))) == sorted(want)


def test_a_narrow_selection_still_gets_csv_under_a_low_cap(client, rel, tmp_path):
    with rules_with(
        tmp_path,
        {"export-csv-row-cap": {"csv_row_cap": largest_csv_lines(rel, rel.case_keys()) - 1}},
    ):
        assert csv_fits(client, drug="Bayer Low Dose")
        _, files = unzip(export(client, "csv", drug="Bayer Low Dose"))
        assert keys(csv_rows(files["cases.csv"])) == ["faers/9004004"]


def test_an_export_of_a_pt_carries_fdas_text_and_no_link_to_the_pt(licensed_client, client, rel):
    _, files = unzip(export(licensed_client, "csv", pt="Heart rhythm abnormal"))
    manifest = json.loads(files[manifest_name()])
    assert (
        "Reactions: Heart rhythm abnormal, each by its current PT in MedDRA 29.1"
        in manifest["described"]
    )
    assert manifest["filters"]["reactions_counted"] == {
        "counted_by": "current_pt",
        "meddra_version": "29.1",
    }
    reacs = f"EXISTS (SELECT 1 FROM reac_latest_T r WHERE {rel.case_join('r')} AND lower(r.pt) = ?)"
    assert set(keys(csv_rows(files["cases.csv"]))) == rel.case_keys(reacs, "arrhythmia")
    written = csv_rows(files["reactions.csv"])
    assert {r["pt"] for r in written} == {"ARRHYTHMIA", "Arrhythmia"}  # as FDA wrote them
    assert not [v for r in written for v in r.values() if "Heart rhythm" in v]
    _, plain = unzip(export(client, "csv", pt="Arrhythmia"))  # a release with no MedDRA
    assert set(written[0]) == set(csv_rows(plain["reactions.csv"])[0])


def test_the_manifest_of_a_release_with_labels_says_the_day_they_are_as_of(label_client):
    """Rule label-refresh: an export of a release with labels names the DailyMed day its labels
    are as of; a release without them names none (above)."""
    _, files = unzip(export(label_client, "parquet", drug="aspirin"))
    manifest = json.loads(files[manifest_name()])
    assert manifest["labels_as_of"] == LABELS_AS_OF.isoformat()
