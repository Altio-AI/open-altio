"""A tiny invented RxNorm release in NLM's RRF format, for tests.

The names and codes (9xxxxx) are invented, apart from `acetaminophen` and
`aspirin`, the RxNorm names reviewed name pairs give for `paracetamol` and
`acetylsalicylic acid`, `warfarin`, a drug name of the fake FDA files, and two conjugates
RxNorm files under their antibody, with their brands: `enfortumab vedotin`
(Padcev), which the reviewed list keeps on its parent's code, and
`trastuzumab deruxtecan` (Enhertu), which it does not; and `divalproex sodium`
(Depakote), the same drug as `valproate` under another name, which it keeps; and
`potassium` with its salt `potassium chloride`, two ingredients as RxNorm names them,
the element being one of the rule's bare elements; `glucose`, which FDA writes dextrose, with
`sodium chloride` and their set. The folder looks
as NLM's prescribable zip unpacks: its Readme, dated by the release the rule
pins (or `release`), and rrf/RXNCONSO.RRF and rrf/RXNREL.RRF.

    zorbatide            IN; its salt "zorbatide sodium" (PIN) and brand "Glimmerex" (BN),
                         which sells the salt
    quintelamab, veltrozine  INs; "quintelamab / veltrozine" (MIN) and its brand "Duotrel"
    "veltrozine / zorbatide sodium"  a MIN listing a salt as a part
    acetaminophen, dronecodone  INs; "acetaminophen / dronecodone" (MIN)
    plorinate            IN, which "plorinic acid" spells by the acid ending rule
    alpha 1-sorbase      IN, which "alpha-1-sorbase" spells once hyphens and spaces go
    vexamine, vex-amine  two INs with one spelling, so "vex amine" finds neither
    osmerdostat          IN, near "osmedrostat" but never matched to it
    kelodrate            IN; "kelodric acid" (PIN) is its acid, the same drug
    olvidase alfa        IN; "olvidase alfa-xqzt" (PIN) is it with FDA's suffix, the same drug
    trelumab             IN; "trelumab vexotecan" (PIN), a conjugate RxNorm files under it
    netazine             IN; "fosnetazine" (PIN), a prodrug RxNorm files under it

Lines NLM suppresses ("zorbatide old"), names from another source ("lumirex")
and the reverse relations NLM also ships are written too, so a test shows
they are not read.

    from open_altio.testing.fakerxnorm import write_rxnorm, CODES
    folder = write_rxnorm(tmp_path / "rxnorm")
"""

from __future__ import annotations

from pathlib import Path

from open_altio import rulebook

# name -> (rxcui, term type)
CODES = {
    "zorbatide": ("900001", "IN"),
    "quintelamab": ("900002", "IN"),
    "veltrozine": ("900003", "IN"),
    "acetaminophen": ("900004", "IN"),
    "dronecodone": ("900005", "IN"),
    "plorinate": ("900006", "IN"),
    "alpha 1-sorbase": ("900007", "IN"),
    "vexamine": ("900008", "IN"),
    "vex-amine": ("900009", "IN"),
    "osmerdostat": ("900010", "IN"),
    "kelodrate": ("900013", "IN"),
    "olvidase alfa": ("900014", "IN"),
    "trelumab": ("900015", "IN"),
    "netazine": ("900016", "IN"),
    "enfortumab": ("900017", "IN"),
    "trastuzumab": ("900018", "IN"),
    "valproate": ("900019", "IN"),
    "aspirin": ("900020", "IN"),
    "warfarin": ("900021", "IN"),
    "potassium": ("900022", "IN"),
    "potassium chloride": ("900023", "IN"),
    "glucose": ("900024", "IN"),
    "sodium chloride": ("900025", "IN"),
    "zorbatide sodium": ("900101", "PIN"),
    "kelodric acid": ("900102", "PIN"),
    "olvidase alfa-xqzt": ("900103", "PIN"),
    "trelumab vexotecan": ("900104", "PIN"),
    "fosnetazine": ("900105", "PIN"),
    "enfortumab vedotin": ("900106", "PIN"),
    "trastuzumab deruxtecan": ("900107", "PIN"),
    "divalproex sodium": ("900108", "PIN"),
    "quintelamab / veltrozine": ("900201", "MIN"),
    "acetaminophen / dronecodone": ("900202", "MIN"),
    "veltrozine / zorbatide sodium": ("900203", "MIN"),
    "glucose / sodium chloride": ("900204", "MIN"),
    "Glimmerex": ("900301", "BN"),
    "Duotrel": ("900302", "BN"),
    "Padcev": ("900303", "BN"),
    "Enhertu": ("900304", "BN"),
    "Depakote": ("900305", "BN"),
}
# (RXCUI1, relation, RXCUI2) as RXNREL.RRF writes a line, which says "RXCUI2 relation RXCUI1"
RELATIONS = [
    ("zorbatide sodium", "has_form", "zorbatide"),
    ("kelodric acid", "has_form", "kelodrate"),
    ("olvidase alfa-xqzt", "has_form", "olvidase alfa"),
    ("trelumab vexotecan", "has_form", "trelumab"),
    ("fosnetazine", "has_form", "netazine"),
    ("enfortumab vedotin", "has_form", "enfortumab"),
    ("trastuzumab deruxtecan", "has_form", "trastuzumab"),
    ("quintelamab / veltrozine", "part_of", "quintelamab"),
    ("quintelamab / veltrozine", "part_of", "veltrozine"),
    ("acetaminophen / dronecodone", "part_of", "acetaminophen"),
    ("acetaminophen / dronecodone", "part_of", "dronecodone"),
    ("veltrozine / zorbatide sodium", "part_of", "veltrozine"),
    ("veltrozine / zorbatide sodium", "part_of", "zorbatide sodium"),
    ("glucose / sodium chloride", "part_of", "glucose"),
    ("glucose / sodium chloride", "part_of", "sodium chloride"),
    ("Glimmerex", "has_tradename", "zorbatide"),
    ("Duotrel", "has_tradename", "quintelamab"),
    ("Duotrel", "has_tradename", "veltrozine"),
    ("zorbatide sodium", "has_precise_ingredient", "Glimmerex"),
    ("Padcev", "has_tradename", "enfortumab"),
    ("enfortumab vedotin", "has_precise_ingredient", "Padcev"),
    ("Enhertu", "has_tradename", "trastuzumab"),
    ("trastuzumab deruxtecan", "has_precise_ingredient", "Enhertu"),
    ("divalproex sodium", "has_form", "valproate"),
    ("Depakote", "has_tradename", "valproate"),
    ("divalproex sodium", "has_precise_ingredient", "Depakote"),
]
REVERSE = {
    "has_form": "form_of",
    "part_of": "has_part",
    "has_tradename": "tradename_of",
    "has_precise_ingredient": "precise_ingredient_of",
}
SUPPRESSED = ("900011", "IN", "zorbatide old")
OTHER_SOURCE = ("900012", "SU", "lumirex")


def _conso(rxcui: str, tty: str, name: str, source: str = "RXNORM", suppress: str = "N") -> str:
    fields = [rxcui, "ENG"] + [""] * 9 + [source, tty, rxcui, name, "", suppress, "4096"]
    return "|".join(fields) + "|\n"


def _rel(one: str, rela: str, two: str) -> str:
    fields = [one, "", "CUI", "RO", two, "", "CUI", rela, "", "", "RXNORM"] + [""] * 4 + ["4096"]
    return "|".join(fields) + "|\n"


def write_rxnorm(folder: Path, release: str | None = None) -> Path:
    """Write the invented release into `folder` and return it."""
    release = release or str(rulebook.value("rxnorm-ingredients", "release"))
    (folder / "rrf").mkdir(parents=True, exist_ok=True)
    (folder / f"Readme_Full_Prescribe_{release}.txt").write_text("Invented RxNorm release\n")
    lines = [_conso(rxcui, tty, name) for name, (rxcui, tty) in CODES.items()]
    lines += [_conso(*SUPPRESSED, suppress="O"), _conso(*OTHER_SOURCE, source="MTHSPL")]
    (folder / "rrf" / "RXNCONSO.RRF").write_text("".join(lines), encoding="utf-8")
    rels = []
    for one, rela, two in RELATIONS:
        rels.append(_rel(CODES[one][0], rela, CODES[two][0]))
        rels.append(_rel(CODES[two][0], REVERSE[rela], CODES[one][0]))
    (folder / "rrf" / "RXNREL.RRF").write_text("".join(rels), encoding="utf-8")
    return folder


__all__ = ["CODES", "RELATIONS", "write_rxnorm"]
