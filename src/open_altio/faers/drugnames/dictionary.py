"""The DiAna dictionary as the drug-name step reads it (rule drug-names).

    from open_altio.faers.drugnames import dictionary
    facts = dictionary.load(con, "reference/DiAna_dictionary.csv")   # fetched first if missing
    dictionary.held()   # the file `open-altio build` reads, when it is on this machine
    dictionary.fetch(dictionary.default_path())   # what `open-altio fetch` and `demo` do

The file is DiAna's, read where the person keeps it and never copied into
the repository. Its checksum must be the one the rule pins: a different file
stops the build, so taking a DiAna update is always a reviewed change to the
rule. `load` writes the scratch table `diana_names_T`, one row per dictionary
key that has a substance, with our reviewed names and corrections applied:

    key_T          DiAna's key for a drug name (`key_sql`)
    substance_T    the ingredients, each once, sorted and joined with ';'
    trial_T        DiAna marks the product as a trial product (`, trial`)
    corrected_T    our names or corrections changed DiAna's answer
"""

from __future__ import annotations

import csv
import os
import shutil
import urllib.request
from pathlib import Path
from urllib.error import URLError

import duckdb

from open_altio import paths, rulebook

from ..reader import quoted
from ..sources import sha256

RULE = "drug-names"
DIANA_ENV = "OPEN_ALTIO_DIANA_DICTIONARY"
TABLE = "diana_names_T"
SEPARATOR = ";"  # between the ingredients of a combination, in DiAna's file and ours
TRIAL = r",\s*trial"  # DiAna's mark on a trial product: `pomalidomide, trial`, `trametinib,trial`
_SEP, _TRIAL = quoted(SEPARATOR), quoted(TRIAL)  # as SQL string literals
CORRECTION_COLUMNS = ("diana_substance", "spelling", "substance", "reason", "evidence")
NAME_COLUMNS = ("diana_name", "name", "reason", "evidence")

# DiAna's 2023 key (DiAna_cleaning, Cleaning_script.R, lines 314 to 320), in R's
# own terms: trimws strips [ \t\r\n], \s is [[:space:]], [:punct:] is ASCII
# punctuation. Trailing punctuation is stripped except ')', leading except
# '(', twice, so a bracketed name keeps its brackets.
_PUNCT = r"""!"#$%&'*+,\-./:;<=>?@\[\\\]^_`{|}~"""


def _trimws(x: str) -> str:
    return rf"regexp_replace({x}, '^[ \t\r\n]+|[ \t\r\n]+$', '', 'g')"


def key_sql(column: str) -> str:
    """DiAna's key for a drug name, as a SQL expression over `column`."""
    x = _trimws(rf"regexp_replace({_trimws(f'lower({column})')}, '\.$', '')")
    x = rf"regexp_replace({x}, '[ \t\n\v\f\r]+', ' ', 'g')"
    for _ in range(2):
        x = _trimws(f"regexp_replace({x}, {quoted(f'[{_PUNCT}(]+$')}, '')")
        x = _trimws(f"regexp_replace({x}, {quoted(f'^[{_PUNCT})]+')}, '')")
    return f"nullif(replace(replace({x}, '( ', '('), ' )', ')'), '')"


class DictionaryRefused(Exception):
    """The dictionary file or our mappings cannot be used as they stand; the message says why."""


def default_path() -> Path:
    """Where the dictionary is kept: $OPEN_ALTIO_DIANA_DICTIONARY, else reference/ in Open
    Altio's data folder, beside FDA's files."""
    chosen = os.environ.get(DIANA_ENV)
    return (
        Path(chosen).expanduser()
        if chosen
        else paths.data_folder() / "reference" / "DiAna_dictionary.csv"
    )


def held() -> Path | None:
    """The dictionary when it is on this machine, else None: a build never downloads it unasked."""
    path = default_path()
    return path if path.is_file() else None


def fetch(target: Path) -> None:
    """Download the rule's file to `target`, kept only when its checksum is the rule's."""
    url = rulebook.value(RULE, "download")
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        timeout = rulebook.value(RULE, "download_timeout_seconds")
        with urllib.request.urlopen(url, timeout=timeout) as response, part.open("wb") as out:
            shutil.copyfileobj(response, out, 1 << 20)
    except (URLError, OSError) as e:
        part.unlink(missing_ok=True)
        raise DictionaryRefused(
            f"could not download the DiAna dictionary from {url} ({e}); "
            f"download it yourself to {target}"
        ) from None
    got = sha256(part)
    if got != rulebook.value(RULE, "sha256"):
        part.unlink()
        raise DictionaryRefused(
            f"the file downloaded from {url} has sha256 {got}, not the one rule {RULE} pins"
        )
    part.rename(target)


def checked_file(path: str | Path) -> Path:
    """The dictionary at `path`, downloaded from the rule's address first when it is
    not there yet. A file whose checksum is not the rule's is refused."""
    path = Path(path).expanduser()
    if not path.exists():
        fetch(path)
    got, want = sha256(path), rulebook.value(RULE, "sha256")
    if got != want:
        raise DictionaryRefused(
            f"{path} has sha256 {got}, but rule {RULE} pins {want}. DiAna may have published a new "
            "dictionary: check our corrections against it, then move the rule to its checksum."
        )
    return path


def _canonical(substance: str) -> bool:
    parts = substance.split(SEPARATOR)
    return (
        bool(substance) and parts == sorted(set(parts)) and all(p == p.strip() and p for p in parts)
    )


def read_mapping(value: str, columns: tuple[str, ...]) -> list[dict[str, str]]:
    """One of our mapping files the rule names, its rows checked for the columns it needs."""
    path = rulebook.data_root() / rulebook.value(RULE, value)
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for n, row in enumerate(rows, 2):
        empty = [c for c in columns if not row.get(c) and c != "spelling"]
        if empty:
            raise DictionaryRefused(f"{path.name} line {n}: {', '.join(empty)} empty")
    return rows


def corrections() -> list[dict[str, str]]:
    """corrections.csv, each substance written as the step writes one: sorted, each ingredient
    once."""
    rows = read_mapping("corrections", CORRECTION_COLUMNS)
    for n, row in enumerate(rows, 2):
        bad = [c for c in ("diana_substance", "substance") if not _canonical(row[c])]
        if bad:
            raise DictionaryRefused(
                f"corrections.csv line {n}: {', '.join(bad)} not sorted, or an ingredient twice"
            )
    return rows


# DiAna's file: one row per key that has a substance (`NA` means DiAna saw the
# name and gave none). Its repeated lines are identical, so any one is the answer.
_DIANA = """
CREATE TEMP TABLE diana_raw_T AS
SELECT drugname AS key_T, any_value(Substance) AS raw_T
FROM read_csv({path}, delim=';', header=true, quote='"', escape='"', all_varchar=true)
WHERE drugname IS NOT NULL AND Substance IS NOT NULL AND Substance <> 'NA'
GROUP BY 1
"""

# Each ingredient on its own, the trial mark removed and our name for it where
# names.csv gives one; then the set again, each ingredient once and sorted, so a
# combination has one spelling however DiAna ordered it.
_NAMES = f"""
CREATE TEMP TABLE {TABLE} AS
WITH parts AS (
  SELECT key_T, regexp_matches(raw_T, {_TRIAL}) AS trial_T,
         trim(unnest(string_split(regexp_replace(raw_T, {_TRIAL}, '', 'g'),
                                  {_SEP}))) AS part_T
  FROM diana_raw_T),
named AS (
  SELECT p.key_T, p.trial_T, coalesce(n.name, p.part_T) AS part_T, n.name IS NOT NULL AS renamed_T
  FROM parts p LEFT JOIN diana_renames_T n ON n.diana_name = p.part_T
  WHERE p.part_T <> '')
SELECT key_T, array_to_string(list_sort(list_distinct(list(part_T))), {_SEP}) AS substance_T,
       bool_or(trial_T) AS trial_T, bool_or(renamed_T) AS corrected_T
FROM named GROUP BY key_T
"""

# A correction replaces DiAna's whole answer for the keys it names: those whose
# substance is its `diana_substance` and that contain its `spelling` pattern
# (no pattern names every such key).
_MATCHED = f"""
CREATE TEMP TABLE diana_matched_T AS
SELECT d.key_T, c.row_T, c.substance FROM {TABLE} d JOIN diana_corrections_T c
  ON d.substance_T = c.diana_substance AND regexp_matches(d.key_T, c.spelling)
"""


def load(con: duckdb.DuckDBPyConnection, path: str | Path) -> dict:
    """Write `diana_names_T` on `con` from the checked dictionary at `path` and our
    mappings; return what the manifest records of the file and of each correction."""
    path = checked_file(path)
    fixes = corrections()
    con.execute("CREATE TEMP TABLE diana_renames_T (diana_name VARCHAR, name VARCHAR)")
    con.executemany(
        "INSERT INTO diana_renames_T VALUES (?, ?)",
        [(r["diana_name"], r["name"]) for r in read_mapping("names", NAME_COLUMNS)],
    )
    con.execute(
        "CREATE TEMP TABLE diana_corrections_T (row_T INTEGER, diana_substance VARCHAR, "
        "spelling VARCHAR, substance VARCHAR)"
    )
    con.executemany(
        "INSERT INTO diana_corrections_T VALUES (?, ?, ?, ?)",
        [
            (i, r["diana_substance"], r["spelling"] or "", r["substance"])
            for i, r in enumerate(fixes)
        ],
    )
    con.execute(_DIANA.format(path=quoted(path.as_posix())))
    con.execute(_NAMES)
    con.execute(_MATCHED)
    twice = [
        r[0]
        for r in con.execute(
            "SELECT key_T FROM diana_matched_T GROUP BY 1 HAVING count(*) > 1 ORDER BY 1 LIMIT 5"
        ).fetchall()
    ]
    if twice:
        raise DictionaryRefused(f"more than one correction names the dictionary keys {twice}")
    con.execute(
        f"UPDATE {TABLE} SET substance_T = m.substance, corrected_T = true "
        f"FROM diana_matched_T m WHERE {TABLE}.key_T = m.key_T"
    )
    keys = dict(con.execute("SELECT row_T, count(*) FROM diana_matched_T GROUP BY 1").fetchall())
    entries = con.execute("SELECT count(*) FROM diana_raw_T").fetchall()[0][0]
    for scratch in ("diana_raw_T", "diana_renames_T", "diana_corrections_T", "diana_matched_T"):
        con.execute(f"DROP TABLE {scratch}")
    return {
        "source": rulebook.value(RULE, "source"),
        "download": rulebook.value(RULE, "download"),
        "published": str(rulebook.value(RULE, "published")),
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": rulebook.value(RULE, "sha256"),
        "keys_with_a_substance": int(entries),
        "corrections": [
            {
                "diana_substance": r["diana_substance"],
                "spelling": r["spelling"] or "",
                "substance": r["substance"],
                "keys": int(keys.get(i, 0)),
            }
            for i, r in enumerate(fixes)
        ],
    }


__all__ = [
    "DIANA_ENV",
    "RULE",
    "SEPARATOR",
    "TABLE",
    "DictionaryRefused",
    "checked_file",
    "corrections",
    "default_path",
    "fetch",
    "held",
    "key_sql",
    "load",
    "read_mapping",
    "sha256",
]
