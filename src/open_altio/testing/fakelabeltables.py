"""Invented FDA labels in the shape of a release's label tables, for the label tests.

The drugs, set IDs and RxNorm codes are made up; the text uses the invented MedDRA
terms of fakemeddra.py, so each rule of the label dictionary has a line to act on.

    from open_altio.testing.fakelabeltables import add_labels, add_record_tables
    add_labels(release_dir)   # writes labels_T, label_candidates_T, label_sections_T
    add_record_tables(release_dir, {"warfarin": "900002"}, {"warfarin": ["by_mouth"]})
                              # drug_rxnorm_T and drug_route_T for its drug records

Inventamab (rxcui 900001) has a label taken by mouth (set-a) and one injected (set-b).
Fakeoxacin (900002) has a label taken by mouth (set-c) whose indications name headache
and nausea.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Collection, Mapping
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

LABELS = [  # rxcui, ingredient, set_id, effective date
    ("900001", "inventamab", "set-a", date(2025, 6, 1)),
    ("900002", "fakeoxacin", "set-c", date(2024, 2, 1)),
]
CANDIDATES = [  # rxcui, ingredient, route, route family, set_id, effective date
    ("900001", "inventamab", "ORAL", "by_mouth", "set-a", date(2025, 6, 1)),
    ("900001", "inventamab", "INTRAVENOUS", "injected", "set-b", date(2026, 1, 15)),
    ("900002", "fakeoxacin", "ORAL", "by_mouth", "set-c", date(2024, 2, 1)),
]
SECTIONS = {  # set_id -> [(section, is_table_row, text)] in label order
    "set-a": [
        (
            "boxed_warning",
            False,
            "WARNING: ACUTE RENAL FAILURE. Acute renal failure has occurred.",
        ),
        ("warnings_and_precautions", False, "Kidney failure may lead to dialysis."),
        ("warnings_and_precautions", False, "No cases of haemorrhage were reported."),
        (
            "warnings_and_precautions",
            False,
            "Heart rhythm abnormal was seen in two patients.",
        ),
        ("adverse_reactions", False, "Table 1 shows the adverse reactions in trial 1."),
        ("adverse_reactions", True, " | Inventamab 10 mg | Placebo"),
        ("adverse_reactions", True, "Headache | 12 (3%) | 4 (1%)"),
        ("adverse_reactions", True, "Vomiting | 0 | 2 (0.5%)"),
        ("adverse_reactions", True, "Nausea | 3% | 0 | 1%"),
        ("adverse_reactions", True, "Injection site wheal | 20% | 14%"),
        ("contraindications", False, "Contraindicated in patients with renal failure."),
        ("contraindications", False, "Severe nausea."),
    ],
    "set-b": [
        (
            "adverse_reactions",
            False,
            "Elevated hepatic enzymes occurred in 2% of patients.",
        ),
    ],
    "set-c": [
        (
            "indications",
            False,
            (
                "Fakeoxacin is indicated for the treatment of headache in adults "
                "with nausea. It is not indicated for the treatment of vomiting."
            ),
        ),
        ("adverse_reactions", False, "Headache occurred in 5% of patients."),
    ],
}


def _write(release_dir: Path, name: str, table: pa.Table) -> dict:
    path = f"parquet/{name}.parquet"
    pq.write_table(table, release_dir / path)
    return {
        "path": path,
        "kind": "derived",
        "rows": table.num_rows,
        "bytes": (release_dir / path).stat().st_size,
    }


def add_labels(release_dir: str | Path) -> Path:
    """Write the invented label tables into a release, with the columns the labels step
    writes, and list them in its manifest."""
    release_dir = Path(release_dir)
    labels = pa.table(
        {
            "rxcui_T": [r[0] for r in LABELS],
            "ingredient_T": [r[1] for r in LABELS],
            "setid_T": [r[2] for r in LABELS],
            "effective_date_T": [r[3] for r in LABELS],
            "chosen_because_T": ["invented"] * len(LABELS),
        }
    )
    candidates = pa.table(
        {
            "rxcui_T": [r[0] for r in CANDIDATES],
            "ingredient_T": [r[1] for r in CANDIDATES],
            "route_T": [r[2] for r in CANDIDATES],
            "route_family_T": [r[3] for r in CANDIDATES],
            "setid_T": [r[4] for r in CANDIDATES],
            "effective_date_T": [r[5] for r in CANDIDATES],
        }
    )
    rows = [
        (s, sec, n, table, text)
        for s, lines in SECTIONS.items()
        for n, (sec, table, text) in enumerate(lines, start=1)
    ]
    sections = pa.table(
        {
            "setid_T": [r[0] for r in rows],
            "section_T": [r[1] for r in rows],
            "loinc_T": [""] * len(rows),
            "ordinal_T": pa.array([r[2] for r in rows], pa.int32()),
            "is_table_row_T": [r[3] for r in rows],
            "text_T": [r[4] for r in rows],
        }
    )
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, table in (
        ("labels_T", labels),
        ("label_candidates_T", candidates),
        ("label_sections_T", sections),
    ):
        manifest["tables"][name] = _write(release_dir, name, table)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return release_dir


_KEY = ("era_T", "primaryid", "quarter_T", "drug_seq")


def _records(release_dir: Path) -> list[tuple]:
    """Each drug record of the release, with its ingredient: its key, then substance_T."""
    path = release_dir / "parquet" / "drug_substance_T.parquet"
    sql = f"SELECT {', '.join(_KEY)}, substance_T FROM read_parquet(?) ORDER BY ALL"
    return duckdb.execute(sql, [str(path)]).fetchall()


def _add(release_dir: Path, tables: dict[str, pa.Table], dropped: tuple[str, ...] = ()) -> None:
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in dropped:
        manifest["tables"].pop(name, None)
    for name, table in tables.items():
        manifest["tables"][name] = _write(release_dir, name, table)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def add_record_tables(
    release_dir: str | Path,
    codes: Mapping[str, str],
    families: Mapping[str, list[str]] | None,
    trial: Collection[str] = (),
    own: Mapping[str, str] | None = None,
) -> Path:
    """Write invented `drug_rxnorm_T`, `ingredient_rxnorm_T` and `drug_route_T` for a release's
    drug records, one row per record (or ingredient) in the columns their steps write, chosen by
    the record's ingredient: `codes` gives an ingredient its RxNorm code (others have none),
    `own` each ingredient its own code (by default its code in `codes`), `families` the families
    its form could be in (others: nothing known; None leaves the release with no
    drug_route_T, whatever its build wrote), and the records of an ingredient in `trial` are
    marked trial products in drug_substance_T."""
    release_dir = Path(release_dir)
    records = _records(release_dir)
    keys = {k: [r[i] for r in records] for i, k in enumerate(_KEY)}
    substance = [r[-1] for r in records]
    coded = [codes.get(s or "") for s in substance]
    own = codes if own is None else own
    ingredients = sorted({i for s in substance if s for i in s.split(";")})
    tables = {
        "ingredient_rxnorm_T": pa.table(
            {
                "ingredient_T": ingredients,
                "rxcui_T": [own.get(i) for i in ingredients],
                "rxnorm_name_T": [i if own.get(i) else None for i in ingredients],
                "tty_T": ["IN" if own.get(i) else None for i in ingredients],
                "no_code_reason_T": [
                    None if own.get(i) else "invented: no code" for i in ingredients
                ],
            }
        ),
        "drug_rxnorm_T": pa.table(
            {
                **keys,
                "rxcui_T": coded,
                "rxnorm_name_T": [s if c else None for s, c in zip(substance, coded, strict=True)],
                "tty_T": [
                    None if not c else "MIN" if ";" in (s or "") else "IN"
                    for s, c in zip(substance, coded, strict=True)
                ],
                "matched_by_T": ["substance" if c else "none" for c in coded],
                "no_code_reason_T": [None if c else "invented: no code" for c in coded],
            }
        ),
    }
    if families is not None:
        spans = [sorted(families[s]) if s in families else None for s in substance]
        tables["drug_route_T"] = pa.table(
            {
                **keys,
                "route_T": [None] * len(records),
                "route_source_T": ["route" if f else "none" for f in spans],
                "route_family_T": [f[0] if f and len(f) == 1 else "unknown" for f in spans],
                "route_families_T": [";".join(f) if f else None for f in spans],
            }
        )
    path = release_dir / "parquet" / "drug_substance_T.parquet"
    substances = pq.read_table(path)
    marked = [s in trial for s in substances.column("substance_T").to_pylist()]
    column = substances.schema.get_field_index("diana_trial_T")
    tables["drug_substance_T"] = substances.set_column(column, "diana_trial_T", pa.array(marked))
    _add(release_dir, tables, () if families is not None else ("drug_route_T",))
    return release_dir


def add_label_groups(release_dir: str | Path, version: str, groups: dict[str, list[str]]) -> Path:
    """Write the licensed part's list of MedDRA groups the label rules set aside, here
    invented group names of fakemeddra.py."""
    path = Path(release_dir) / "licensed" / "meddra" / version / "label_groups.json"
    path.write_text(json.dumps(groups, indent=2) + "\n", encoding="utf-8")
    return path


def write_ime_workbook(path: str | Path, codes: list[str], dropped: list[str]) -> Path:
    """A workbook shaped like EMA's Important Medical Events file: the list on the first
    sheet, after a few title rows, and the PTs it has dropped on a second sheet."""
    strings = ["Important medical events, invented", "MedDRA Code", "Term"]

    def sheet(values: list[str]) -> str:
        cells = "".join(
            f'<row r="{n}"><c r="A{n}"><v>{v}</v></c></row>' for n, v in enumerate(values, start=3)
        )
        title = '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        return f'<worksheet xmlns="{main}"><sheetData>{title}{cells}</sheetData></worksheet>'

    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    shared = "".join(f"<si><t>{t}</t></si>" for t in strings)
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("xl/sharedStrings.xml", f'<sst xmlns="{main}">{shared}</sst>')
        book.writestr("xl/worksheets/sheet1.xml", sheet(codes))
        book.writestr("xl/worksheets/sheet2.xml", sheet(dropped))
    return Path(path)
