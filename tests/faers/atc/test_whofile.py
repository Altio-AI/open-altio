"""Reading WHO's ATC index spreadsheet, on an invented index in WHO's layout."""

from __future__ import annotations

import pytest

from open_altio.faers.atc.whofile import WhoRefused, read_index
from open_altio.testing.fakewho import INDEX, write_index


def test_every_code_is_read_once_with_its_name_and_no_stray_spaces(tmp_path):
    codes = dict(read_index(write_index(tmp_path / "who")))
    assert len(codes) == len({row[0].strip() for row in INDEX})
    assert codes["C07ZZ01"] == "zelotolol"  # WHO's cell ends in a non-breaking space
    assert codes["N02ZZ"] == "Invented analgesics"  # and here in a zero-width space
    assert codes["J05ZZ01"] == "plenivir"  # two dose rows, one code


def test_a_folder_without_exactly_one_spreadsheet_is_refused(tmp_path):
    with pytest.raises(WhoRefused, match="exactly one"):
        read_index(tmp_path)
    write_index(tmp_path, file_name="a.xlsx")
    write_index(tmp_path, file_name="b.xlsx")
    with pytest.raises(WhoRefused, match="exactly one"):
        read_index(tmp_path)


def test_a_sheet_without_WHOs_headings_is_refused(tmp_path):
    from openpyxl import Workbook

    tmp_path.mkdir(exist_ok=True)
    book = Workbook()
    book.active.append(("Code", "Title"))
    book.save(tmp_path / "index.xlsx")
    with pytest.raises(WhoRefused, match="heading row"):
        read_index(tmp_path)


def test_a_cell_that_is_not_an_atc_code_is_refused(tmp_path):
    with pytest.raises(WhoRefused, match="not an ATC code"):
        read_index(write_index(tmp_path, rows=[*INDEX, ("C07ZZ1", "short code", "", "", "", "")]))


def test_one_code_named_two_ways_is_refused(tmp_path):
    with pytest.raises(WhoRefused, match="named both"):
        read_index(
            write_index(tmp_path, rows=[*INDEX, ("J05ZZ01", "plenivir sodium", "", "", "", "")])
        )
