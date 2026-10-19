"""An invented WHO ATC index in WHO's spreadsheet layout, and a small class
table in ours, for tests.

Nothing here is WHO content: every name is made up, and every substance code
sits in a fourth level WHO does not use (`ZZ`). The codes start with WHO's
first letters and groups (B01, C07, J05, N02, S01) so the route groups of
rule atc-class-choice apply to them as they do to WHO's.

    from open_altio.testing.fakewho import write_index, write_classes
    folder = write_index(tmp_path / "who")          # folder/2026 ATC index with DDDs_english.xlsx
    table = write_classes(tmp_path / "classes.csv")  # the table the release step reads

The index holds what the builder must handle:

    zelotolol        C07ZZ01 (tablets) and S01ZZ01 (eye drops): two uses
    plenivir         J05ZZ01, with two dose rows repeating its code and name
    dostavir         J05ZZ02
    plenivir and dostavir     J05ZZ51: a combination of two coded substances
    plenivir and boosters     J05ZZ52: a combination named by a class word
    korvastatin calcium       C10ZZ01: a salt, which a bridge names korvastatin
    lumavir                   J05ZZ53 "lumavir and plenivir": lumavir is coded only here
    plenivir, combinations    J05ZZ54: names no ingredient set
    quorpirin        B01ZZ01 (low dose) and N02ZZ01 (full dose)

with a non-breaking space after one code and a zero-width space in one name,
as WHO's file has.

The class table adds, for the choice of one class per drug record:

    ombrafloxacin    S01ZZ02 (eye), S02ZZ01 (ear) and S03ZZ01 (eye and ear)
    otomycin         S01ZZ03 (eye) and S03ZZ02 (eye and ear): no ear code of its own
    velucort         D07ZZ01 (plain) and D07ZY01, a class for mixes named after it
    pelacort         D07ZY02 "pelacort and plenivir", a code for mixes named after the product,
                     which a bridge lets its one part stand for
    ravuvir          J05ZZ03 and J05ZZ04: two codes in one fourth level
    brenolol         C07ZZ02 and C07ZY01: two codes in one third level
    miravist         S01ZZ04 and S01YY01: two codes in one second level
    lipotolol        C07ZZ03 and C10ZZ02: two codes that share only the first letter
    flutizone        R01ZZ01 and R01ZZ02 (two nasal sprays) and D07ZZ02 (skin)
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook

FILE_NAME = "2026 ATC index with DDDs_english.xlsx"
SHEET = "ATC index with DDDs 2026"
HEADING = ("ATC code", "ATC level name", "DDD", "Unit", "Adm.R", "Comment")

# (code, name, ddd, unit, route, comment), in WHO's order: each class before its codes
INDEX = [
    ("B", "INVENTED BLOOD MEDICINES", "", "", "", ""),
    ("B01", "INVENTED CLOT MEDICINES", "", "", "", ""),
    ("B01Z", "INVENTED ANTITHROMBOTIC AGENTS", "", "", "", ""),
    ("B01ZZ", "Invented platelet inhibitors", "", "", "", ""),
    ("B01ZZ01", "quorpirin", "1", "tablet", "O", ""),
    ("C", "INVENTED HEART MEDICINES", "", "", "", ""),
    ("C07", "INVENTED HEART RATE MEDICINES", "", "", "", ""),
    ("C07Z", "INVENTED BETA BLOCKING AGENTS", "", "", "", ""),
    ("C07ZZ", "Invented beta blocking agents, plain", "", "", "", ""),
    ("C07ZZ01\u00a0", "zelotolol", "20", "mg", "O", ""),
    ("C10", "INVENTED LIPID MEDICINES", "", "", "", ""),
    ("C10Z", "INVENTED LIPID MODIFYING AGENTS", "", "", "", ""),
    ("C10ZZ", "Invented statins", "", "", "", ""),
    ("C10ZZ01", "korvastatin calcium", "10", "mg", "O", ""),
    ("J", "INVENTED ANTIINFECTIVES", "", "", "", ""),
    ("J05", "INVENTED ANTIVIRAL MEDICINES", "", "", "", ""),
    ("J05Z", "INVENTED ANTIVIRALS", "", "", "", ""),
    ("J05ZZ", "Invented antivirals", "", "", "", ""),
    ("J05ZZ01", "plenivir", "0.3", "g", "O", ""),
    ("J05ZZ01", "plenivir", "0.2", "g", "P", ""),
    ("J05ZZ02", "dostavir", "50", "mg", "O", ""),
    ("J05ZZ51", "plenivir and dostavir", "", "", "", ""),
    ("J05ZZ52", "plenivir and boosters", "", "", "", ""),
    ("J05ZZ53", "lumavir and plenivir", "", "", "", ""),
    ("J05ZZ54", "plenivir, combinations", "", "", "", ""),
    ("N", "INVENTED NERVE MEDICINES", "", "", "", ""),
    ("N02", "INVENTED PAIN MEDICINES", "", "", "", ""),
    ("N02Z", "INVENTED ANALGESICS", "", "", "", ""),
    ("N02ZZ", "Invented analgesics\u200b", "", "", "", ""),
    ("N02ZZ01", "quorpirin", "3", "g", "O", ""),
    ("S", "INVENTED SENSE ORGAN MEDICINES", "", "", "", ""),
    ("S01", "INVENTED EYE MEDICINES", "", "", "", ""),
    ("S01Z", "INVENTED OPHTHALMOLOGICALS", "", "", "", ""),
    ("S01ZZ", "Invented antiglaucoma preparations", "", "", "", ""),
    ("S01ZZ01", "zelotolol", "", "", "", ""),
]
BRIDGES = [
    ("who_name", "substance", "evidence"),
    (
        "korvastatin calcium",
        "korvastatin",
        "WHO names the salt; the dictionary names the active part",
    ),
    ("lumavir", "lumavir", "WHO codes it only in combinations"),
]
# The table the release step tests read: ingredient (or set), code, WHO's name, level, year
CLASSES = [
    ("", "C", "INVENTED HEART MEDICINES", 1),
    ("", "C07", "INVENTED HEART RATE MEDICINES", 2),
    ("", "C07Z", "INVENTED BETA BLOCKING AGENTS", 3),
    ("", "C07ZZ", "Invented beta blocking agents, plain", 4),
    ("", "J", "INVENTED ANTIINFECTIVES", 1),
    ("", "J05", "INVENTED ANTIVIRAL MEDICINES", 2),
    ("", "J05Z", "INVENTED ANTIVIRALS", 3),
    ("", "J05ZZ", "Invented antivirals", 4),
    ("", "S", "INVENTED SENSE ORGAN MEDICINES", 1),
    ("", "S01", "INVENTED EYE MEDICINES", 2),
    ("", "S01Z", "INVENTED OPHTHALMOLOGICALS", 3),
    ("", "S01ZZ", "Invented antiglaucoma preparations", 4),
    ("dostavir", "J05ZZ02", "dostavir", 5),
    ("dostavir;plenivir", "J05ZZ51", "plenivir and dostavir", 5),
    ("plenivir", "J05ZZ01", "plenivir", 5),
    ("quorpirin", "B01ZZ01", "quorpirin", 5),
    ("quorpirin", "N02ZZ01", "quorpirin", 5),
    ("", "B", "INVENTED BLOOD MEDICINES", 1),
    ("", "B01", "INVENTED CLOT MEDICINES", 2),
    ("", "B01Z", "INVENTED ANTITHROMBOTIC AGENTS", 3),
    ("", "B01ZZ", "Invented platelet inhibitors", 4),
    ("", "N", "INVENTED NERVE MEDICINES", 1),
    ("", "N02", "INVENTED PAIN MEDICINES", 2),
    ("", "N02Z", "INVENTED ANALGESICS", 3),
    ("", "N02ZZ", "Invented analgesics", 4),
    ("zelotolol", "C07ZZ01", "zelotolol", 5),
    ("zelotolol", "S01ZZ01", "zelotolol", 5),
    ("", "C07ZY", "Invented beta blocking agents, selective", 4),
    ("", "C10", "INVENTED LIPID MEDICINES", 2),
    ("", "C10Z", "INVENTED LIPID MODIFYING AGENTS", 3),
    ("", "C10ZZ", "Invented statins", 4),
    ("", "D", "INVENTED SKIN MEDICINES", 1),
    ("", "D07", "INVENTED CORTICOSTEROIDS, DERMATOLOGICAL PREPARATIONS", 2),
    ("", "D07Z", "INVENTED CORTICOSTEROIDS", 3),
    ("", "D07ZZ", "Invented corticosteroids, plain", 4),
    ("", "D07ZY", "Invented corticosteroids, other combinations", 4),
    ("", "S01Y", "INVENTED OTHER OPHTHALMOLOGICALS", 3),
    ("", "S01YY", "Invented decongestants", 4),
    ("", "S02", "INVENTED EAR MEDICINES", 2),
    ("", "S02Z", "INVENTED OTOLOGICALS", 3),
    ("", "S02ZZ", "Invented antiinfectives", 4),
    ("", "S03", "INVENTED EYE AND EAR MEDICINES", 2),
    ("", "S03Z", "INVENTED OPHTHALMOLOGICAL AND OTOLOGICAL PREPARATIONS", 3),
    ("", "S03ZZ", "Invented antiinfectives", 4),
    ("brenolol", "C07ZY01", "brenolol", 5),
    ("brenolol", "C07ZZ02", "brenolol", 5),
    ("lipotolol", "C07ZZ03", "lipotolol", 5),
    ("lipotolol", "C10ZZ02", "lipotolol", 5),
    ("miravist", "S01YY01", "miravist", 5),
    ("miravist", "S01ZZ04", "miravist", 5),
    ("ombrafloxacin", "S01ZZ02", "ombrafloxacin", 5),
    ("ombrafloxacin", "S02ZZ01", "ombrafloxacin", 5),
    ("ombrafloxacin", "S03ZZ01", "ombrafloxacin", 5),
    ("otomycin", "S01ZZ03", "otomycin", 5),
    ("otomycin", "S03ZZ02", "otomycin", 5),
    ("ravuvir", "J05ZZ03", "ravuvir", 5),
    ("ravuvir", "J05ZZ04", "ravuvir", 5),
    ("velucort", "D07ZY01", "velucort", 5),
    ("velucort", "D07ZZ01", "velucort", 5),
    ("pelacort", "D07ZY02", "pelacort and plenivir", 5),
    ("", "R", "INVENTED RESPIRATORY MEDICINES", 1),
    ("", "R01", "INVENTED NASAL PREPARATIONS", 2),
    ("", "R01Z", "INVENTED DECONGESTANTS FOR TOPICAL USE", 3),
    ("", "R01ZZ", "Invented corticosteroids", 4),
    ("flutizone", "D07ZZ02", "flutizone", 5),
    ("flutizone", "R01ZZ01", "flutizone", 5),
    ("flutizone", "R01ZZ02", "flutizone", 5),
]
YEAR = 2026


def write_index(
    folder: Path, *, file_name: str = FILE_NAME, rows: Sequence[tuple[str, ...]] = INDEX
) -> Path:
    """The invented index as WHO's spreadsheet, alone in `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    sheet.append(HEADING)
    for row in rows:
        sheet.append(row)
    book.create_sheet("Copyright").append(("Invented for tests; not WHO's material.",))
    book.save(folder / file_name)
    return folder


def write_bridges(path: Path) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(BRIDGES)
    return path


def write_classes(path: Path, *, year: int = YEAR) -> Path:
    """The small class table, in our table's layout."""
    with path.open("w", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh, lineterminator="\n")
        out.writerow(("ingredient", "atc_code", "who_name", "level", "index_year"))
        out.writerows((*row, year) for row in CLASSES)
    return path


__all__ = [
    "BRIDGES",
    "CLASSES",
    "FILE_NAME",
    "INDEX",
    "YEAR",
    "write_bridges",
    "write_classes",
    "write_index",
]
