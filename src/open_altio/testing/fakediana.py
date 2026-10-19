"""An invented DiAna dictionary in DiAna's own file format: a byte order mark,
a `;` between the two columns, Windows line ends, quotes around a substance
that holds the separator, and `NA` for a name DiAna saw and gave no substance.

    path = write_dictionary(tmp_path / "DiAna_dictionary.csv")

ENTRIES covers the fake FDA quarters' drug names (fakefda) and every case the
drug-name step handles: a trial mark with and without its space, a combination
out of order, a name DiAna writes two ways, a mis-encoded name, and spellings
our reviewed corrections change. The real dictionary's content is DiAna's and
is never copied here.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

from open_altio.faers.drugnames import dictionary
from open_altio.testing.rules import rules_with

# a non-breaking space written twice over as UTF-8, as DiAna's file has it
MISENCODED_SPACE = "\u00c2\u00a0"

ENTRIES: list[tuple[str, str]] = [
    ("aspirin", "acetylsalicylic acid"),
    ("ibuprofen", "ibuprofen"),
    ("warfarin", "warfarin"),
    ("omeprazole", "omeprazole"),
    ("metformin", "metformin"),
    ("digoxin", "digoxin"),
    ("lisinopril", "lisinopril"),
    ("bayer low dose", "NA"),
    ("humira", "adalimumab"),
    ("humira (adalimumab)", "adalimumab"),
    ("entresto", "valsartan;sacubitril"),
    ("sacubitril", "sacubitril"),
    ("valsartan", "valsartan"),
    ("diovan", "valsartan"),
    ("lipitor", "atorvastatin"),
    ("blinded lcz696", "sacubitril;valsartan, trial"),
    ("study drug", "unspecified, trial"),
    ("trametinib", "trametinib,trial"),
    ("vevye", "cyclosporine"),
    ("neoral", "ciclosporin"),
    ("tecfidera", "fumaric acid"),
    ("fumaderm", "fumaric acid"),
    ("valstar", "hydrochlorothiazide;valsartan"),
    ("co valstar", "hydrochlorothiazide;valsartan"),
    ("cortisone (hydrocortisone)", "cortisone"),
    ("cortisone acetate", "cortisone"),
    ("isopropanolamine", "isopropanol"),
    ("lorax", "loratadine"),
    ("lorax (lorazepam)", "loratadine"),
    ("lorax (loratadine)", "loratadine"),
    ("refresh p.m", "polyvinyl alcohol;povidone"),
    ("refresh tears", "polyvinyl alcohol;povidone"),
    (
        "alka-seltzer plus maximum strength day and night cold and flu powermax gels",
        "acetylsalicylic acid",
    ),
    ("brexafemme", "oteseconazole"),
    ("hyoscine butylbromide", "scopolamine"),
    ("hyoscine butylbromide/metamizole", "metamizole;scopolamine"),
    ("levolet (levothyroxine sodium)", "levofloxacin"),
    ("levolet", "levofloxacin"),
    (
        "tetrofosmin",
        f"technetium{MISENCODED_SPACE}tc{MISENCODED_SPACE}99m{MISENCODED_SPACE}tetrofosmin",
    ),
    ("aspirin", "acetylsalicylic acid"),  # DiAna's file repeats a few lines
]


def _line(key: str, substance: str) -> str:
    return f'{key};"{substance}"' if ";" in substance else f"{key};{substance}"


def write_dictionary(path: Path, entries: list[tuple[str, str]] = ENTRIES) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["drugname;Substance"] + [_line(k, s) for k, s in entries]
    path.write_bytes(("\ufeff" + "\r\n".join(lines) + "\r\n").encode("utf-8"))
    return path


@contextlib.contextmanager
def pinned(path: Path, scratch: Path) -> Iterator[Path]:
    """Run code with rule drug-names pinning the checksum of the invented dictionary at
    `path`, under a copy of the rules made in `scratch`."""
    with rules_with(scratch, {dictionary.RULE: {"sha256": dictionary.sha256(path)}}):
        yield path
