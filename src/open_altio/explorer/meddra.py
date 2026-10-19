"""The live release's licensed MedDRA part, as the explorer reads it.

    licensed = LicensedMeddra(live)      # live: the explorer's LiveRelease
    served = licensed.served()           # the release's MedDRA version, or None
    served.smqs(), served.llts()         # what the reaction search offers a viewer allowed them
    served.read("pt")                    # FDA's text -> its current PT, and how it matched
    served.texts_of()                    # a PT (lower case) -> FDA's reaction texts read to it
    served.pt_names()                    # a PT (lower case) -> as MedDRA writes it
    served.soc_of("pt", "Arrhythmia")    # the PT's primary system organ class, or None
    served.current("pt", "Arrhythmia")   # {"name", "matched_as"} where the PT is another name

The text to PT link counts and finds reactions for each viewer they are named by it for
(explorer/reactions.py), but is shown only to a viewer the access hook allows, as are SMQs and
lower level terms.

A release holds one MedDRA version, the newest held when it was built, and everything in it
uses that one (rule meddra-version), so the explorer serves the version the licensed manifest
names. It asks on every request, so a release read to a new version is served without a restart.
A part an older Open Altio added, without the terms report and the text to PT tables, is not
served: the release is shown without MedDRA, and `licensed.older()` says how to add it again.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from open_altio.faers.explorer_db import reaction_term
from open_altio.faers.meddra import (
    COLUMNS,
    licensed_dir,
    newest,
    older_part,
    older_words,
    read_licensed_manifest,
    term_key,
)
from open_altio.faers.reader import quoted

from .release import LiveRelease, NotLive, read_connection


class ServedMeddra:
    """One MedDRA version of the live release's licensed part, opened in memory."""

    def __init__(self, folder: Path, entry: dict) -> None:
        self.version: str = entry["version"]
        # what the build reported of each column (texts, and texts and rows matching nothing)
        self.report: dict = entry["terms"]
        # the counts the methods page shows that need MedDRA (written by the methods command)
        self.numbers: dict = entry.get("numbers") or {}
        self._con = read_connection(self)  # held to the explorer's memory limit
        for table, spec in entry["tables"].items():
            self._con.execute(
                f"CREATE VIEW {table} AS SELECT * FROM "
                f"read_parquet({quoted(str(folder / spec['path']))})"
            )
        self._lock = threading.Lock()
        self._smqs: dict[str, dict] | None = None
        self._llts: list[tuple[str, str, bool, str]] | None = None
        self._read: dict[str, dict[str, tuple[str, str]]] = {}
        self._texts: dict[str, tuple[str, ...]] | None = None
        self._pt_names: dict[str, str] | None = None
        self._socs: dict[str, str] | None = None
        self._soc_texts: dict[str, str] | None = None

    def _run(self, sql: str, params: list[Any] | None = None) -> list[tuple]:
        cur = self._con.cursor()
        try:
            return cur.execute(sql, params or []).fetchall()
        finally:
            cur.close()

    def smqs(self) -> dict[str, dict]:
        """Every active SMQ: code -> {code, name, level, narrow, broad}, where
        narrow and broad are the names of its active PTs in lower case (broad
        holds both scopes) with its active sub-SMQs folded in. Worked out once."""
        with self._lock:
            if self._smqs is None:
                self._smqs = self._fold_smqs()
            return self._smqs

    def llts(self) -> list[tuple[str, str, bool, str]]:
        """Every LLT whose name is not its PT's: (LLT name, its PT's name in
        lower case, current or not, LLT code), in MedDRA's file order. Worked out once."""
        with self._lock:
            if self._llts is None:
                pt_name = dict(self._run("SELECT pt_code, pt_name FROM meddra_pt"))
                out = []
                for name, pt_code, currency, code in self._run(
                    "SELECT llt_name, pt_code, llt_currency, llt_code FROM meddra_llt"
                ):
                    pt = pt_name.get(pt_code)
                    if pt and name.lower() != pt.lower():
                        out.append((name, pt.lower(), currency == "Y", code))
                self._llts = out
            return self._llts

    def read(self, column: str) -> dict[str, tuple[str, str]]:
        """FDA's MedDRA column (pt, drug_rec_act or indi_pt) read to this version: each text,
        keyed as faers.meddra.term_key keys it, -> (its current PT as MedDRA writes it, how it
        matched: pt, llt or former_name). A text that matches nothing is not in it. Worked out
        once a column."""
        with self._lock:
            if column not in self._read:
                spec = COLUMNS[column]
                self._read[column] = {
                    text: (pt, how)
                    for text, pt, how in self._run(
                        f"SELECT m.{spec.term}, p.pt_name, m.matched_as_T FROM {spec.table} m "
                        "JOIN meddra_pt p ON p.pt_code = m.pt_code_T"
                    )
                }
            return self._read[column]

    def current(self, column: str, text: str | None) -> dict[str, str] | None:
        """The current PT one of FDA's texts in `column` reads to, and how it matched, where its
        name is not the text itself whatever the capitals; None where it is, or where the text
        matches no MedDRA name."""
        found = self.read(column).get(term_key(column, text) or "") if text else None
        if found is None or found[0].lower() == reaction_term(text or ""):
            return None
        return {"name": found[0], "matched_as": found[1]}

    def pt_names(self) -> dict[str, str]:
        """Every PT of this version in lower case -> its name as MedDRA writes it. Made once."""
        with self._lock:
            if self._pt_names is None:
                self._pt_names = {
                    name.lower(): name for (name,) in self._run("SELECT pt_name FROM meddra_pt")
                }
            return self._pt_names

    def socs(self) -> dict[str, str]:
        """Each current PT of this version in lower case -> its primary system organ class as
        MedDRA writes it. Worked out once a served version."""
        with self._lock:
            if self._socs is None:
                self._socs = {
                    pt.lower(): soc
                    for pt, soc in self._run(
                        "SELECT pt_name, soc_name FROM meddra_mdhier WHERE primary_soc_fg = 'Y'"
                    )
                }
            return self._socs

    def soc_of(self, column: str, text: str | None) -> str | None:
        """The primary system organ class of the current PT one of FDA's texts in `column`
        reads to; None where the text matches no MedDRA name."""
        found = self.read(column).get(term_key(column, text) or "") if text else None
        return self.socs().get(found[0].lower()) if found else None

    def soc_by_text(self) -> dict[str, str]:
        """Each reaction text of the pt column that reads to a PT with a primary system organ
        class -> that class as MedDRA writes it. Worked out once."""
        read = self.read("pt")
        socs = self.socs()
        with self._lock:
            if self._soc_texts is None:
                self._soc_texts = {
                    text: socs[pt.lower()] for text, (pt, _) in read.items() if pt.lower() in socs
                }
            return self._soc_texts

    def texts_of(self) -> dict[str, tuple[str, ...]]:
        """Each current PT FDA's reactions read to, in lower case -> the reaction texts read to
        it (keyed as the explorer's reaction terms are), in order. Worked out once."""
        read = self.read("pt")
        with self._lock:
            if self._texts is None:
                texts: dict[str, list[str]] = {}
                for text, (pt, _) in sorted(read.items()):
                    texts.setdefault(pt.lower(), []).append(text)
                self._texts = {pt: tuple(t) for pt, t in texts.items()}
            return self._texts

    def _fold_smqs(self) -> dict[str, dict]:
        pt_name = dict(self._run("SELECT pt_code, pt_name FROM meddra_pt"))
        smqs: dict[str, dict] = {}
        for code, name, level in self._run(
            "SELECT smq_code, smq_name, smq_level FROM meddra_smq_list WHERE status = 'A'"
        ):
            smqs[code] = {
                "code": code,
                "name": name,
                "level": int(level),
                "narrow": set(),
                "broad": set(),
                "children": [],
            }
        for smq, term, level, scope in self._run(
            "SELECT smq_code, term_code, term_level, term_scope FROM meddra_smq_content "
            "WHERE term_status = 'A'"
        ):
            if smq not in smqs:
                continue
            if level == "0":
                smqs[smq]["children"].append(term)
            elif level == "4" and term in pt_name:  # MedDRA's term_level 4 is a PT
                name = pt_name[term].lower()
                smqs[smq]["broad"].add(name)
                if scope == "2":  # term_scope 2 is narrow
                    smqs[smq]["narrow"].add(name)

        def fold(code: str, seen: tuple = ()) -> tuple[set, set]:
            q = smqs.get(code)
            if not q or code in seen:
                return set(), set()
            narrow, broad = set(q["narrow"]), set(q["broad"])
            for child in q["children"]:
                n, b = fold(child, seen + (code,))
                narrow |= n
                broad |= b
            return narrow, broad

        folded = {code: fold(code) for code in smqs}
        for code, q in smqs.items():
            q["narrow"], q["broad"] = folded[code]
            del q["children"]
        return smqs


@dataclass(frozen=True)
class _Key:
    folder: Path
    version: str
    built_at: str


class LicensedMeddra:
    """Asks the live release for its folder on each call and keeps the served
    version open until the folder, the version or its build changes."""

    def __init__(self, release: LiveRelease) -> None:
        self.release = release
        self._lock = threading.Lock()
        self._open: dict[_Key, ServedMeddra] = {}

    def _live(self) -> tuple[Path | None, dict[str, dict]]:
        """The live release folder and the versions its licensed part holds (none without one)."""
        try:
            folder = self.release.folder()
        except NotLive:
            return None, {}
        manifest = read_licensed_manifest(folder)
        return folder, dict(manifest["meddra"]["versions"]) if manifest else {}

    def served(self) -> ServedMeddra | None:
        """The live release's MedDRA version, opened, or None when it holds none, or only one
        an older Open Altio added (`older`)."""
        release_folder, versions = self._live()
        chosen = newest(versions)
        if chosen is None or release_folder is None or older_part(versions[chosen]):
            return None
        folder = licensed_dir(release_folder)
        key = _Key(folder, chosen, versions[chosen].get("built_at", ""))
        with self._lock:
            if key not in self._open:
                self._open = {key: ServedMeddra(folder, versions[chosen])}
            return self._open[key]

    def older(self) -> str | None:
        """What to say when the live release's MedDRA part was added by an older Open Altio, and
        so is not served: that, and how to add it again. None otherwise."""
        _, versions = self._live()
        chosen = newest(versions)
        return older_words(chosen) if chosen and older_part(versions[chosen]) else None


__all__ = ["LicensedMeddra", "ServedMeddra"]
