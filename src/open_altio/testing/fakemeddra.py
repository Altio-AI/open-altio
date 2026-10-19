"""A tiny invented MedDRA release in MedDRA's ASCII format, for tests.

Nothing here is MedDRA content: the codes (9xxxxxxx), the SOC, HLGT, HLT
and SMQ names are invented. A few PT names are the words the fake FDA files
use (fakefda.py) for reactions and indications, so FDA's text maps to codes.

Three versions differ the way real ones do:

    28.1  Older than the fake FDA files: "Lactic acidosis" is not in it, so
          the licensed step refuses it.
    29.0  "Lactic acidosis" is a new PT. Arrhythmia is a PT (under the
          nervous SOC, through HLT 93000005).
    29.1  Arrhythmia is demoted: its code stays, as a non-current LLT of the
          new PT "Heart rhythm abnormal". "Lactic acidosis" is renamed
          "Acidosis lactic", so FDA's older text reaches it only through the
          history file.

In each, "Head pain" is a current LLT of Headache, "Sickness" a
non-current LLT of Nausea and "Convulsion" a current LLT of Seizure.
"Pain" (an indication) and "Parkinson's disease" (which FDA's
drug_rec_act writes "Parkinson^s disease") are PTs, and "Dyspepsia",
an indication, is in no version.

For the label dictionary: "Renal failure" and "Renal failure acute" share
one HLT; "Acute renal failure", "Kidney failure" and the capitals-only "ARF"
are current LLTs below them; "Lead" is a current LLT of "Blood lead", an
everyday word in label text. "Invented site reaction" is an umbrella term, named as
the singular of its HLT, over "Invented site pain" and "Invented site necrosis".

The history file, meddra_history_english.asc, records each term's additions,
demotions and renames up to the version, as MedDRA's does: every term is
added in an invented 27.0.

SMQs: 96000001 "Invented bleeding events (SMQ)" holds Haemorrhage narrow,
Nausea broad and Headache narrow but inactive. 96000002 "Invented
gastrointestinal events (SMQ)" holds the sub-SMQ 96000003, which holds
Vomiting narrow and the LLT Sickness broad.

    from open_altio.testing.fakemeddra import write_meddra
    folder = write_meddra(tmp_path / "meddra", "29.1")   # folder/MedAscii/*.asc

MSSO ships each release as one zip locked with a password (classic zip
encryption). `write_meddra_zip` makes one the same shape from the invented
files, locked with a made-up password, for the upload in Settings:

    from open_altio.testing.fakemeddra import write_meddra_zip
    path = write_meddra_zip(tmp_path / "MedDRA_29_1_English.zip", "a made-up password")
"""

from __future__ import annotations

import random
import struct
import zlib
from pathlib import Path

from open_altio.faers.meddra import (
    DERIVED_TABLES,
    licensed_dir,
    read_licensed_manifest,
    write_licensed_manifest,
)

SOCS = {
    "91000001": ("Invented nervous system disorders", "Inerv"),
    "91000002": ("Invented gastrointestinal disorders", "Igast"),
    "91000003": ("Invented vascular disorders", "Ivasc"),
    "91000004": ("Invented investigations", "Iinv"),
}
HLGTS = {  # code -> (name, soc)
    "92000001": ("Invented headaches HLGT", "91000001"),
    "92000002": ("Invented gastrointestinal signs HLGT", "91000002"),
    "92000003": ("Invented bleeding HLGT", "91000003"),
    "92000004": ("Invented enzyme tests HLGT", "91000004"),
    "92000005": ("Invented rhythm HLGT", "91000001"),
}
HLTS = {  # code -> (name, hlgt)
    "93000001": ("Invented headaches NEC", "92000001"),
    "93000002": ("Invented nausea and vomiting symptoms", "92000002"),
    "93000003": ("Invented haemorrhages NEC", "92000003"),
    "93000004": ("Invented liver function analyses", "92000004"),
    "93000005": ("Invented rate and rhythm disorders", "92000005"),
    "93000006": ("Invented kidney failures NEC", "92000003"),
    "93000007": ("Invented site reactions", "92000002"),
}
COMMON_PTS = {  # code -> (name, hlt)
    "94000001": ("Headache", "93000001"),
    "94000002": ("Nausea", "93000002"),
    "94000003": ("Vomiting", "93000002"),
    "94000004": ("Haemorrhage", "93000003"),
    "94000005": ("Hepatic enzyme increased", "93000004"),
    "94000009": ("Pain", "93000001"),
    "94000010": ("Parkinson's disease", "93000001"),
    "94000021": ("Renal failure", "93000006"),
    "94000022": ("Renal failure acute", "93000006"),
    "94000023": ("Blood lead", "93000004"),
    "94000024": ("Invented site reaction", "93000007"),
    "94000025": ("Invented site pain", "93000007"),
    "94000026": ("Invented site necrosis", "93000007"),
    "94000027": ("Seizure", "93000001"),
}
COMMON_LLTS = {  # code -> (name, pt, current)
    "95000001": ("Head pain", "94000001", "Y"),
    "95000002": ("Sickness", "94000002", "N"),
    "95000003": ("Acute renal failure", "94000022", "Y"),
    "95000004": ("ARF", "94000022", "Y"),
    "95000005": ("Kidney failure", "94000021", "Y"),
    "95000006": ("Lead", "94000023", "Y"),
    "95000007": ("Convulsion", "94000027", "Y"),
}
ARRHYTHMIA, HEART_RHYTHM, LACTIC = "94000006", "94000007", "94000008"
SMQS = {  # code -> (name, level)
    "96000001": ("Invented bleeding events (SMQ)", "1"),
    "96000002": ("Invented gastrointestinal events (SMQ)", "1"),
    "96000003": ("Invented vomiting sub-search (SMQ)", "2"),
}
# smq, term code, term level (MedDRA's: 4 PT, 5 LLT, 0 sub-SMQ), scope (2 narrow, 1 broad,
# 0 n/a), status
SMQ_CONTENT = [
    ("96000001", "94000004", "4", "2", "A"),
    ("96000001", "94000002", "4", "1", "A"),
    ("96000001", "94000001", "4", "2", "I"),
    ("96000002", "96000003", "0", "0", "A"),
    ("96000003", "94000003", "4", "2", "A"),
    ("96000003", "95000002", "5", "1", "A"),
]


def _at_least(version: str, major: int, minor: int) -> bool:
    return tuple(int(x) for x in version.split(".")) >= (major, minor)


def _terms(
    version: str,
) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str, str]], list[tuple[str, ...]]]:
    """The version's PTs (code -> name, hlt), LLTs (code -> name, pt, current) and history
    records (code, name, version, term type, currency, action)."""
    pts = dict(COMMON_PTS)
    llts = dict(COMMON_LLTS)
    history: list[tuple[str, ...]] = [
        (c, n, "27.0", "PT", "", "A") for c, (n, _h) in COMMON_PTS.items()
    ]
    history += [(c, n, "27.0", "LLT", "Y", "A") for c, (n, _h) in COMMON_PTS.items()]
    history += [(c, n, "27.0", "LLT", cur, "A") for c, (n, _p, cur) in COMMON_LLTS.items()]
    history += [
        (ARRHYTHMIA, "Arrhythmia", "27.0", "PT", "", "A"),
        (ARRHYTHMIA, "Arrhythmia", "27.0", "LLT", "Y", "A"),
    ]
    if not _at_least(version, 29, 1):
        pts[ARRHYTHMIA] = ("Arrhythmia", "93000005")
    else:
        pts[HEART_RHYTHM] = ("Heart rhythm abnormal", "93000005")
        llts[ARRHYTHMIA] = ("Arrhythmia", HEART_RHYTHM, "N")
        history += [
            (ARRHYTHMIA, "Arrhythmia", "29.1", "PT", "", "D"),
            (ARRHYTHMIA, "Arrhythmia", "29.1", "LLT", "N", "U"),
            (HEART_RHYTHM, "Heart rhythm abnormal", "29.1", "PT", "", "A"),
            (HEART_RHYTHM, "Heart rhythm abnormal", "29.1", "LLT", "Y", "A"),
        ]
    if _at_least(version, 29, 0):
        renamed = _at_least(version, 29, 1)
        pts[LACTIC] = ("Acidosis lactic" if renamed else "Lactic acidosis", "93000004")
        history += [
            (LACTIC, "Lactic acidosis", "29.0", "PT", "", "A"),
            (LACTIC, "Lactic acidosis", "29.0", "LLT", "Y", "A"),
        ]
        if renamed:
            history += [
                (LACTIC, "Acidosis lactic", "29.1", "PT", "", "U"),
                (LACTIC, "Acidosis lactic", "29.1", "LLT", "Y", "U"),
            ]
    for code, (name, _hlt) in pts.items():  # every PT is also its own current LLT
        llts[code] = (name, code, "Y")
    return pts, llts, history


def current_llts(version: str = "29.1") -> list[tuple[str, str, str, str]]:
    """(llt code, llt name, pt code, pt name) of every current LLT, as the label
    dictionary reads them from a release's licensed part."""
    pts, llts, _history = _terms(version)
    return [(c, n, p, pts[p][0]) for c, (n, p, cur) in llts.items() if cur == "Y"]


def _line(*fields: str) -> str:
    return "$".join(fields) + "$\n"


def _hierarchy(code: str, name: str, hlt: str, soc: str) -> str:
    """One mdhier.asc line: a PT with its HLT, HLGT and primary SOC, their codes then names."""
    hlt_name, hlgt = HLTS[hlt]
    soc_name, soc_abbrev = SOCS[soc]
    return _line(
        code, hlt, hlgt, soc, name, hlt_name, HLGTS[hlgt][0], soc_name, soc_abbrev, "", soc, "Y"
    )


def meddra_files(version: str = "29.1", language: str = "English") -> dict[str, str]:
    """The invented release's MedAscii files: name -> text."""
    pts, llts, history = _terms(version)
    pt_soc = {c: HLGTS[HLTS[h][1]][1] for c, (_n, h) in pts.items()}
    files = {
        "meddra_release.asc": _line(version, language, "", "", ""),
        "soc.asc": "".join(_line(c, n, a, *[""] * 7) for c, (n, a) in SOCS.items()),
        "hlgt.asc": "".join(_line(c, n, *[""] * 6) for c, (n, _s) in HLGTS.items()),
        "hlt.asc": "".join(_line(c, n, *[""] * 6) for c, (n, _g) in HLTS.items()),
        "pt.asc": "".join(_line(c, n, "", pt_soc[c], *[""] * 7) for c, (n, _h) in pts.items()),
        "llt.asc": "".join(_line(c, n, p, *[""] * 6, cur, "") for c, (n, p, cur) in llts.items()),
        "mdhier.asc": "".join(_hierarchy(c, n, h, pt_soc[c]) for c, (n, h) in pts.items()),
        "soc_hlgt.asc": "".join(_line(s, g) for g, (_n, s) in HLGTS.items()),
        "hlgt_hlt.asc": "".join(_line(g, h) for h, (_n, g) in HLTS.items()),
        "hlt_pt.asc": "".join(_line(h, c) for c, (_n, h) in pts.items()),
        "smq_list.asc": "".join(
            _line(c, n, lvl, "Invented for tests.", "", "", version, "A", "N")
            for c, (n, lvl) in SMQS.items()
        ),
        "smq_content.asc": "".join(
            _line(s, t, lvl, scope, "A", "0", status, "1.0", version)
            for s, t, lvl, scope, status in SMQ_CONTENT
        ),
        # MedDRA writes this file without the closing $ the others have
        "meddra_history_english.asc": "".join("$".join(r) + "\r\n" for r in history),
    }
    return files


def write_meddra(folder: Path, version: str = "29.1", language: str = "English") -> Path:
    """Write the invented release into folder/MedAscii and return `folder`."""
    out = Path(folder) / "MedAscii"
    out.mkdir(parents=True, exist_ok=True)
    for name, text in meddra_files(version, language).items():
        (out / name).write_text(text, encoding="latin-1")
    return Path(folder)


# MSSO's zip, made up: classic zip encryption ------------------------------------------------


def _crc_table() -> list[int]:
    table = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
        table.append(c)
    return table


_CRC = _crc_table()


class _ZipCrypto:
    """PKWARE's traditional zip encryption (APPNOTE 6.1), which zipfile can only read."""

    def __init__(self, password: bytes) -> None:
        self.keys = [0x12345678, 0x23456789, 0x34567890]
        for b in password:
            self._update(b)

    def _update(self, b: int) -> None:
        k0, k1, k2 = self.keys
        k0 = _CRC[(k0 ^ b) & 0xFF] ^ (k0 >> 8)
        k1 = ((k1 + (k0 & 0xFF)) * 134775813 + 1) & 0xFFFFFFFF
        k2 = _CRC[(k2 ^ (k1 >> 24)) & 0xFF] ^ (k2 >> 8)
        self.keys = [k0, k1, k2]

    def encrypt(self, data: bytes) -> bytes:
        out = bytearray()
        for b in data:
            t = (self.keys[2] | 2) & 0xFFFF
            out.append(b ^ (((t * (t ^ 1)) >> 8) & 0xFF))
            self._update(b)
        return bytes(out)


def write_zip(
    path: Path, files: dict[str, bytes], password: str | None = None, *, seed: int = 7
) -> Path:
    """Write a zip of `files` (name -> bytes), deflated, each locked with `password` the way
    MSSO's are when one is given. The same arguments always give the same bytes."""
    rng = random.Random(seed)
    body, central = bytearray(), bytearray()
    when_time, when_date = (12 << 11) | (0 << 5), ((2026 - 1980) << 9) | (9 << 5) | 1
    for name, data in files.items():
        raw_name = name.encode("utf-8")
        crc = zlib.crc32(data)
        packer = zlib.compressobj(6, zlib.DEFLATED, -15)
        packed = packer.compress(data) + packer.flush()
        flags = 0
        if password is not None:
            flags = 0x1
            cipher = _ZipCrypto(password.encode("utf-8"))
            head = bytes(rng.randrange(256) for _ in range(11)) + bytes([(crc >> 24) & 0xFF])
            packed = cipher.encrypt(head) + cipher.encrypt(packed)
        offset = len(body)
        # what the local and the central header share: version needed, flags, method, time,
        # date, crc, both sizes and the name's length
        shared = (20, flags, 8, when_time, when_date, crc, len(packed), len(data), len(raw_name))
        body += struct.pack("<IHHHHHIIIHH", 0x04034B50, *shared, 0) + raw_name + packed
        header = struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, *shared, 0, 0, 0, 0, 0, offset)
        central += header + raw_name
    end = struct.pack(
        "<IHHHHIIH", 0x06054B50, 0, 0, len(files), len(files), len(central), len(body), 0
    )
    Path(path).write_bytes(bytes(body + central + end))
    return Path(path)


def write_meddra_zip(
    path: Path,
    password: str | None,
    *,
    version: str = "29.1",
    language: str = "English",
    drop: tuple[str, ...] = (),
    change: dict[str, str] | None = None,
    readme: str = "",
) -> Path:
    """A zip shaped like MSSO's (a readme beside the MedAscii folder) holding the invented
    release, locked with `password`. `drop` leaves files out, `change` replaces a file's text,
    `readme` changes the readme (and so the zip's bytes) without changing the release."""
    tag = f"{version.replace('.', '_')}_{language}"
    readme = readme or f"Invented for tests: MedDRA {version}, {language}.\n"
    files = {f"!!readme_{tag}.txt": readme.encode()}
    texts = {**meddra_files(version, language), **(change or {})}
    files.update({f"MedAscii/{n}": t.encode("latin-1") for n, t in texts.items() if n not in drop})
    return write_zip(path, files, password)


def as_an_older_version_wrote_it(release_dir: Path) -> Path:
    """`release_dir`'s licensed part as an Open Altio from before the terms report wrote it: each
    version's entry without the report and without the text to PT tables. Changes the release
    given, so give it a copy."""
    manifest = read_licensed_manifest(release_dir)
    assert manifest is not None, f"{release_dir} has no licensed part"
    for entry in manifest["meddra"]["versions"].values():
        entry.pop("terms")
        for table in DERIVED_TABLES:
            (licensed_dir(release_dir) / entry["tables"].pop(table)["path"]).unlink()
    write_licensed_manifest(release_dir, manifest)
    return release_dir
