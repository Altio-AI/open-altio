"""Invented label flags for the fake release, in the shape the label flags step writes them,
with the record tables the explorer reads them through (open_altio.explorer.labels):
`drug_rxnorm_T` (each drug record's RxNorm code), `ingredient_rxnorm_T` (each ingredient's own
code), `drug_route_T` (its route families), `label_flags_T` (each code, route families and
reaction's flag) and `label_candidates_T` (each label's title, ingredients, date and the route
families it was chosen for, which name it). The release's own `drug_substance_T` is kept, with
one record marked a trial product.

    from open_altio.testing.fakelabelflags import add_label_flags
    add_label_flags(release_dir)   # writes the tables and lists them in its manifest

The codes are RxNorm's; the labels, their set IDs, dates and every flag are made up, so each
flag the screens show has a row to show:

- Acetylsalicylic acid's records are taken by mouth, except case 9013013's, whose form nothing
  says (no families), and case 9110011's, which could be on the skin or by mouth: their
  Headache is judged against both of its labels and they differ (Forms differ). The BAYER LOW
  DOSE record is marked a trial product, so it has no flag. Vomiting was decided by a model's
  suggestion nobody has checked, so it shows as Uncertain.
- Case 9026026's acetylsalicylic acid record was read to a combination's code (`COMBINED`),
  whose newer label agrees with aspirin's own on its Nausea and Haemorrhage: the drug's row
  still names aspirin's own label (rule explorer-label-flags, label_tiebreak).
- Aspirin's own label names its product (ASPIRINEX), as warfarin's and metformin's do; the
  combination's is a generic's and digoxin's has no Highlights, so each is named by its
  ingredients (rule explorer-label-names).
- Entresto's record (sacubitril and valsartan) is coded as the combination, whose own label has
  its Headache on it; valsartan's own label does not (Not listed), and sacubitril has a code of
  its own but no label (Not compared, no label found). Valsartan's own records have no code, so
  on the page of valsartan alone their Headache finds no label, while a page counting any
  product containing valsartan reads them, and Entresto's, on valsartan's own label.
- Warfarin, metformin and digoxin have one label each; ibuprofen has none (No label found).
  DOXORUBICIN, a spelling with no ingredient, has an injection label only, so its record taken
  by mouth is read on that label (`judged_on_T` injected). A record with no RxNorm code, such
  as BLEOMYCIN SULFATE's, has the row the step writes for it: no code, No label found.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from open_altio.rulebook import value

KEY = ("era_T", "primaryid", "quarter_T", "drug_seq")
CODES = {  # an ingredient, or a spelling with no ingredient, and its RxNorm code
    "acetylsalicylic acid": "1191",
    "warfarin": "11289",
    "metformin": "6809",
    "digoxin": "3407",
    "ibuprofen": "5640",
    "DOXORUBICIN": "3639",
}
# an ingredient's own code (ingredient_rxnorm_T): the ingredients above, and valsartan's and
# sacubitril's, which their own records do not carry here; every other ingredient has none
OWN = {
    **{k: v for k, v in CODES.items() if k.islower()},
    "valsartan": "69749",
    "sacubitril": "1656328",
}
# an ingredient set and its RxNorm code for the combination (MIN)
SETS = {"sacubitril;valsartan": "1656339"}
KEPT = ("drug_latest_T", "drug_substance_T")  # the release's own tables the fake reads
ROUTE_COLUMNS = ("route_T", "route_source_T", "route_family_T", "route_families_T")
TRIAL = {"BAYER LOW DOSE"}  # drug names marked a trial product
# (era_T, primaryid) of a record read to a combination's code, and that code
COMBINED = {("faers", "90260261"): "999901"}
# (era_T, primaryid) -> the route families its records could be in
FORMS = {("faers", "90130131"): [], ("faers", "91100111"): ["skin", "by_mouth"]}
# the DailyMed day the labels are as of, as a build or a refresh records it (rule label-refresh)
LABELS_AS_OF = date(2026, 6, 30)
LABELS = {  # set ID -> its effective date
    "aspirin-by-mouth": date(2024, 3, 1),
    "aspirin-skin": date(2025, 9, 12),
    "warfarin-by-mouth": date(2023, 8, 8),
    "metformin-by-mouth": date(2026, 4, 22),
    "digoxin-by-mouth": date(2022, 1, 5),
    "doxorubicin-injected": date(2025, 2, 2),
    "aspirin-combination": date(2026, 5, 1),
    "valsartan-by-mouth": date(2026, 8, 11),
    "entresto-by-mouth": date(2026, 7, 6),
}
# set ID -> (RxNorm code, RxNorm's ingredients, the label's title, its route families)
TITLES = {
    "aspirin-by-mouth": (
        "1191",
        "aspirin",
        "These highlights do not include all the information needed to use ASPIRINEX® safely "
        "and effectively. See full prescribing information for ASPIRINEX. ASPIRINEX® (aspirin) "
        "tablets, for oral use",
        ["by_mouth", "under_tongue"],
    ),
    "aspirin-skin": (
        "1191",
        "aspirin",
        "See full prescribing information for ASPIRINEX TOPICAL. ASPIRINEX TOPICAL (aspirin)",
        ["skin"],
    ),
    "warfarin-by-mouth": (
        "11289",
        "warfarin",
        "See full prescribing information for WARFAREX. WARFAREX® (warfarin sodium) tablets",
        ["by_mouth", "under_tongue"],
    ),
    "metformin-by-mouth": (
        "6809",
        "metformin",
        "See full prescribing information for METFORA XR. METFORA XR (metformin) tablets",
        ["by_mouth", "under_tongue"],
    ),
    "digoxin-by-mouth": ("3407", "digoxin", "DIGOXIN TABLETS, USP Rx only", ["by_mouth"]),
    "doxorubicin-injected": ("3639", "doxorubicin", "", ["injected"]),
    "aspirin-combination": (
        "999901",
        "aspirin / caffeine",
        "See full prescribing information for ASPIRIN AND CAFFEINE TABLETS.",
        ["by_mouth"],
    ),
    "valsartan-by-mouth": (
        "69749",
        "valsartan",
        "See full prescribing information for DIOVAN. DIOVAN® (valsartan) tablets, for oral use",
        ["by_mouth", "under_tongue"],
    ),
    "entresto-by-mouth": (
        "1656339",
        "sacubitril / valsartan",
        "See full prescribing information for ENTRESTO. ENTRESTO® (sacubitril and valsartan) "
        "tablets, for oral use",
        ["by_mouth", "under_tongue"],
    ),
}


@dataclass(frozen=True)
class Flag:
    """One row of label_flags_T, by the reaction as FDA published it; `forms` is the record's
    route families as the step keys them, sorted and joined with ";" ('' when none is known)."""

    rxcui: str | None
    forms: str
    pt: str
    outcome: str
    section: str | None = None
    setid: str | None = None
    decided_by: str = "rule"
    families: str | None = None
    judged_on: str | None = None  # the family label or labels that decided; its own by default

    @property
    def judged(self) -> str | None:
        return self.judged_on or (self.forms if self.setid else None)


ASPIRIN, ASPIRIN_SKIN, WARFARIN = "aspirin-by-mouth", "aspirin-skin", "warfarin-by-mouth"
DOXORUBICIN = "doxorubicin-injected"
SPLIT = {
    "outcome": "forms_differ",
    "families": "by_mouth: on_label; skin: not_on_label",
    "judged_on": "by_mouth; skin",
}
FLAGS = [
    Flag("1191", "by_mouth", "Headache", "on_label", "adverse_reactions", ASPIRIN),
    Flag("1191", "skin", "Headache", "not_on_label", setid=ASPIRIN_SKIN),
    Flag("1191", "", "Headache", **SPLIT),
    Flag("1191", "by_mouth;skin", "Headache", **SPLIT),
    Flag("1191", "by_mouth", "HEADACHE", "on_label", "adverse_reactions", ASPIRIN),
    Flag(
        "1191", "by_mouth", "Vomiting", "on_label", "adverse_reactions", ASPIRIN, "model_suggested"
    ),
    Flag(
        "1191", "by_mouth", "Hepatic enzyme INCREASED", "related", None, ASPIRIN, "model_reviewed"
    ),
    Flag("1191", "by_mouth", "Nausea", "not_on_label", setid=ASPIRIN),
    Flag("1191", "by_mouth", "Haemorrhage", "on_label", "warnings_and_precautions", ASPIRIN),
    # the combination's newer label agrees with aspirin's own
    Flag("999901", "by_mouth", "Nausea", "not_on_label", setid="aspirin-combination"),
    Flag(
        "999901",
        "by_mouth",
        "Haemorrhage",
        "on_label",
        "warnings_and_precautions",
        "aspirin-combination",
    ),
    Flag("11289", "by_mouth", "Haemorrhage", "on_label", "boxed_warning", WARFARIN),
    Flag("11289", "by_mouth", "Nausea", "related", None, WARFARIN, "rule: umbrella"),
    Flag("6809", "by_mouth", "Lactic acidosis", "on_label", "boxed_warning", "metformin-by-mouth"),
    Flag("3407", "by_mouth", "Arrhythmia", "treated_disease", setid="digoxin-by-mouth"),
    Flag("3407", "by_mouth", "ARRHYTHMIA", "treated_disease", setid="digoxin-by-mouth"),
    # Entresto's own label lists its Headache; valsartan's own does not; sacubitril has none
    Flag("1656339", "by_mouth", "Headache", "on_label", "adverse_reactions", "entresto-by-mouth"),
    Flag("69749", "by_mouth", "Headache", "not_on_label", setid="valsartan-by-mouth"),
    Flag("1656328", "by_mouth", "Headache", "no_label"),
    Flag("5640", "by_mouth", "Headache", "no_label"),
    Flag("5640", "by_mouth", "HEADACHE", "no_label"),
    # doxorubicin has an injection label only, so a record taken by mouth is read on it
    Flag(
        "3639",
        "by_mouth",
        "Headache",
        "on_label",
        "adverse_reactions",
        DOXORUBICIN,
        judged_on="injected",
    ),
    # a record with no RxNorm code: no label can be found for it
    Flag(None, "by_mouth", "Headache", "no_label"),
    Flag(None, "by_mouth", "HEADACHE", "no_label"),
]

_RECORDS = f"""
SELECT DISTINCT {", ".join(f"d.{k}" for k in KEY)}, d.drugname_norm_T AS name, s.substance_T,
  s.substance_source_T
FROM read_parquet(?) d JOIN read_parquet(?) s USING ({", ".join(KEY)}) ORDER BY ALL
"""


def _write(release_dir: Path, manifest: dict, name: str, table: pa.Table) -> None:
    path = f"parquet/{name}.parquet"
    pq.write_table(table, release_dir / path)
    manifest["tables"][name] = {
        "path": path,
        "kind": "derived",
        "rows": table.num_rows,
        "bytes": (release_dir / path).stat().st_size,
    }


def add_label_flags(release_dir: str | Path) -> Path:
    """Write the invented tables into a release and list them in its manifest."""
    release_dir = Path(release_dir)
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [str(release_dir / manifest["tables"][t]["path"]) for t in KEPT]
    records = duckdb.execute(_RECORDS, paths).fetchall()
    keys = {k: [r[i] for r in records] for i, k in enumerate(KEY)}
    codes = [
        COMBINED.get((r[0], r[1]))
        or SETS.get(r[5])
        or CODES.get(r[5])
        or (CODES.get(r[4]) if r[5] is None else None)
        for r in records
    ]
    sets = {*COMBINED.values(), *SETS.values()}
    forms = [FORMS.get((r[0], r[1]), ["by_mouth"]) for r in records]
    _write(
        release_dir,
        manifest,
        "drug_substance_T",
        pa.table(
            keys
            | {
                "substance_T": [r[5] for r in records],
                "substance_source_T": [r[6] for r in records],
                "diana_trial_T": [r[4] in TRIAL for r in records],
            }
        ),
    )
    _write(
        release_dir,
        manifest,
        "drug_rxnorm_T",
        pa.table(
            keys
            | {
                "rxcui_T": codes,
                "rxnorm_name_T": [r[5] if c else None for r, c in zip(records, codes, strict=True)],
                "tty_T": [None if not c else "MIN" if c in sets else "IN" for c in codes],
                "matched_by_T": ["substance" if c else "none" for c in codes],
                "no_code_reason_T": [None if c else "no RxNorm name" for c in codes],
            }
        ),
    )
    _write(
        release_dir,
        manifest,
        "drug_route_T",
        pa.table(
            keys
            | {
                "route_T": ["048" if f == ["by_mouth"] else "065" for f in forms],
                "route_source_T": ["route" if f == ["by_mouth"] else "disagree" for f in forms],
                "route_family_T": [f[0] if len(f) == 1 else "unknown" for f in forms],
                # as the route step writes them: sorted and joined with ";", empty when none
                "route_families_T": [";".join(sorted(f)) or None for f in forms],
            },
            pa.schema([(c, pa.string()) for c in (*KEY, *ROUTE_COLUMNS)]),
        ),
    )
    ingredients = sorted({i for r in records if r[5] for i in r[5].split(";")})
    _write(
        release_dir,
        manifest,
        "ingredient_rxnorm_T",
        pa.table(
            {
                "ingredient_T": ingredients,
                "rxcui_T": [OWN.get(i) for i in ingredients],
                "rxnorm_name_T": [i if i in OWN else None for i in ingredients],
                "tty_T": ["IN" if i in OWN else None for i in ingredients],
                "no_code_reason_T": [None if i in OWN else "no RxNorm name" for i in ingredients],
            }
        ),
    )
    columns = {
        "rxcui": "rxcui_T",
        "forms": "route_families_T",
        "pt": "pt_T",
        "outcome": "outcome_T",
        "section": "section_T",
        "setid": "setid_T",
        "decided_by": "decided_by_T",
        "families": "family_outcomes_T",
        "judged": "judged_on_T",
    }
    flags = {c: [getattr(f, k) for f in FLAGS] for k, c in columns.items()}
    expectedness = value("label-flags", "expectedness")  # as the label flags step reads each
    flags["expectedness_T"] = [expectedness[f.outcome] for f in FLAGS]
    flags["label_date_T"] = [LABELS.get(f.setid) if f.setid else None for f in FLAGS]
    _write(
        release_dir,
        manifest,
        "label_flags_T",
        pa.table(
            flags,
            pa.schema([(c, pa.date32() if c == "label_date_T" else pa.string()) for c in flags]),
        ),
    )
    _write(release_dir, manifest, "label_candidates_T", _candidates())
    manifest["labels"] = {"as_of": LABELS_AS_OF.isoformat()}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return release_dir


def _candidates() -> pa.Table:
    """label_candidates_T, one row per label and route family it was chosen for."""
    rows = [
        (setid, code, ingredient, title, family)
        for setid, (code, ingredient, title, families) in TITLES.items()
        for family in families
    ]
    return pa.table(
        {
            "rxcui_T": [r[1] for r in rows],
            "ingredient_T": [r[2] for r in rows],
            "route_family_T": [r[4] for r in rows],
            "setid_T": [r[0] for r in rows],
            "spl_version_T": pa.array([1] * len(rows), pa.int32()),
            "title_T": [r[3] for r in rows],
            "effective_date_T": pa.array([LABELS[r[0]] for r in rows], pa.date32()),
        }
    )


__all__ = [
    "CODES",
    "COMBINED",
    "FLAGS",
    "FORMS",
    "LABELS",
    "LABELS_AS_OF",
    "OWN",
    "SETS",
    "TITLES",
    "TRIAL",
    "Flag",
    "add_label_flags",
]
