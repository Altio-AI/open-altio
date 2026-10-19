"""FDA's files as the build loads them, checked through the release folder only: every value
verbatim, the one renaming of columns across eras, run-on lines, and the inputs refused."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from open_altio import rulebook
from open_altio.faers import COLUMN_UNIFICATION, RAW_COLUMNS, SourceError, build_release
from open_altio.faers.schema import TABLES
from open_altio.testing import fakediana, fakefda
from open_altio.testing.releasereader import ReleaseReader

README = Path(__file__).resolve().parents[2] / "src" / "open_altio" / "faers" / "README.md"


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("quarter", fakefda.QUARTERS)
def test_raw_values_are_identical_to_the_input_file(rel, quarter, table):
    cols = RAW_COLUMNS[table]
    expected = Counter(
        tuple(row.get(c) for c in cols) + (quarter, fakefda.LAYOUTS[quarter].era)
        for row in fakefda.parsed_rows(quarter, table)
    )
    select = ", ".join(f'"{c}"' for c in cols + ("quarter_T", "era_T"))
    got = Counter(rel.rows(f"SELECT {select} FROM {table} WHERE quarter_T = ?", quarter))
    assert got == expected


def test_deleted_lists_are_kept_verbatim(rel):
    expected = Counter()
    for q, path, lines in fakefda.DELETED_LISTS:
        tag = f"pre{q}" if "AllDeleted" in path else q
        expected.update((line, tag) for line in lines if line.strip())
    assert Counter(rel.rows("SELECT caseid, quarter_T FROM deleted")) == expected


def test_raw_column_names_are_fdas_except_the_documented_unification(rel):
    # the renames the pipeline makes are exactly the ones its README documents
    assert COLUMN_UNIFICATION == fakefda.EXPECTED_RENAMES
    readme = README.read_text(encoding="utf-8")
    for renames in COLUMN_UNIFICATION.values():
        for old, new in renames.items():
            assert f"`{old}`" in readme and f"`{new}`" in readme, (old, new)
    # every column FDA published lands, under its own name or its documented one
    for q in fakefda.QUARTERS:
        for t in TABLES:
            assert set(fakefda.header_columns(q, t)) <= set(rel.columns(t)), (q, t)


def test_manifest_lists_the_renames_each_file_needed(rel):
    by_file = {(i["table"], i["quarter"]): i for i in rel.manifest["inputs"]}
    demo_2012q4 = by_file[("demo", "2012q4")]
    assert demo_2012q4["renamed"] == {"gndr_cod": "sex"}
    assert by_file[("demo", "2012q2")]["renamed"] == {
        "ISR": "primaryid",
        "CASE": "caseid",
        "I_F_COD": "i_f_code",
        "GNDR_COD": "sex",
    }
    assert by_file[("demo", "2026q2")]["renamed"] == {}
    assert all(isinstance(i["overflow_values"], int) for i in rel.manifest["inputs"])


def _input(rel, table: str, quarter: str) -> dict:
    return next(i for i in rel.manifest["inputs"] if (i["table"], i["quarter"]) == (table, quarter))


def test_a_line_holding_two_whole_records_is_split_back_into_both(rel):
    """FDA's 2011Q2, 2011Q3 and 2011Q4 DRUG files each have one line where a
    record runs on into the next with no line break (rules/overlong-lines.md).
    Both records load; the manifest names the line."""
    assert rulebook.is_on("overlong-lines")
    assert rel.rows(
        "SELECT drug_seq, drugname FROM drug WHERE primaryid = '4100010' ORDER BY drug_seq"
    ) == [("1", "BLEOMYCIN SULFATE"), ("2", "DOXORUBICIN")]
    entry = _input(rel, "drug", "2012q3")
    assert entry["rejected_lines"] == 0
    [repair] = entry["overlong_lines"]
    assert (repair["fields"], repair["records"]) == (2 * 12 + 1, 2)
    _, data = fakefda.text_file("2012q3", "drug")
    line = data.decode("latin-1").splitlines()[repair["line"] - 1]
    assert "BLEOMYCIN SULFATE" in line and "DOXORUBICIN" in line


def test_any_other_overlong_line_keeps_its_first_fields_and_is_recorded(rel):
    """FDA's 2012Q1 DEMO has one line with a `$` inside mfr_num, so the values
    after it sit one column right. The row is kept as read, and the text past
    the last column is written into the manifest, never lost silently."""
    assert rel.dicts(
        "SELECT mfr_num, mfr_sndr, reporter_country FROM demo WHERE primaryid = '4100011'"
    ) == [{"mfr_num": "JP-ACME-", "mfr_sndr": "E2B0000000182", "reporter_country": None}]
    [cut] = _input(rel, "demo", "2012q3")["overlong_lines"]
    assert (cut["fields"], cut["records"], cut["dropped"]) == (23 + 2, 1, "UNITED STATES$")
    assert [i["source"] for i in rel.manifest["inputs"] if i.get("overlong_lines")] == [
        _input(rel, "demo", "2012q3")["source"],
        _input(rel, "drug", "2012q3")["source"],
    ]


def test_extracted_folders_build_the_same_release_as_zips(rel, fake_diana, tmp_path):
    folders = fakefda.write_input(tmp_path / "raw", as_zips=False)
    with fakediana.pinned(fake_diana, tmp_path):
        other = ReleaseReader(build_release(folders, tmp_path / "out", diana_dictionary=fake_diana))
    assert other.manifest["inputs_hash"] == rel.manifest["inputs_hash"]
    assert other.funnel == rel.funnel
    assert {t: e["rows"] for t, e in other.manifest["tables"].items()} == {
        t: e["rows"] for t, e in rel.manifest["tables"].items()
    }


def test_a_column_fda_never_published_is_refused_by_name(tmp_path):
    folder = fakefda.write_input(tmp_path / "raw", as_zips=False, quarters=("2019q1",))
    demo = folder / "2019q1" / "ascii" / "DEMO19Q1.txt"
    lines = demo.read_bytes().split(b"\r\n")
    lines = [lines[0] + b"$surprise"] + [line + b"$x" if line else line for line in lines[1:]]
    demo.write_bytes(b"\r\n".join(lines))
    with pytest.raises(SourceError, match="surprise"):
        build_release(folder, tmp_path / "out")
    assert not (tmp_path / "out" / "2019Q1").exists()


def test_the_same_quarter_twice_in_the_input_is_refused(tmp_path):
    fakefda.write_input(tmp_path / "in", as_zips=True, quarters=("2019q1",))
    fakefda.write_input(tmp_path / "in", as_zips=False, quarters=("2019q1",))
    with pytest.raises(SourceError, match="twice"):
        build_release(tmp_path / "in", tmp_path / "out")
