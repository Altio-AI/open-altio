"""FDA's quarterly files: names, the latest quarter, and downloads that resume and are checked."""

from __future__ import annotations

from datetime import date

import pytest

from open_altio.faers import fda
from open_altio.testing import fakefda


@pytest.fixture
def quarter_zip(tmp_path_factory) -> bytes:
    folder = fakefda.write_input(tmp_path_factory.mktemp("fda"), quarters=("2026q2",))
    return (folder / "faers_ascii_2026q2.zip").read_bytes()


def test_names_follow_fda_s_two_eras():
    assert fda.zip_name("2012q3") == "aers_ascii_2012q3.zip"
    assert fda.zip_name("2012q4") == "faers_ascii_2012q4.zip"


def test_quarters_run_from_fda_s_first_to_the_one_asked():
    quarters = fda.quarters_until("2026q2")
    assert (quarters[0], quarters[-1], len(quarters)) == ("2004q1", "2026q2", 90)
    assert fda.quarters_until("2005q1")[-2:] == ["2004q4", "2005q1"]


def test_the_latest_quarter_is_the_newest_fda_has_published(fake_fda):
    fake_fda.files["faers_ascii_2026q2.zip"] = b"PK"
    assert fda.latest_quarter(date(2026, 10, 17)) == "2026q2"
    asked = [name for name, _ in fake_fda.requests]
    assert asked == ["faers_ascii_2026q4.zip", "faers_ascii_2026q3.zip", "faers_ascii_2026q2.zip"]


def test_no_quarter_for_a_year_is_refused_as_fda_having_moved(fake_fda):
    with pytest.raises(fda.FetchError, match="FDA may have moved its files"):
        fda.latest_quarter(date(2026, 10, 17))


def test_fda_out_of_reach_says_to_check_the_connection(monkeypatch):
    monkeypatch.setattr(fda, "EXPORTS", "http://127.0.0.1:9/")
    with pytest.raises(fda.FetchError, match="Could not reach FDA .* internet connection"):
        fda.latest_quarter(date(2026, 10, 17))


def test_a_download_lands_whole_under_the_quarter_s_name(fake_fda, quarter_zip, tmp_path):
    fake_fda.files["faers_ascii_2026q2.zip"] = quarter_zip
    seen = []
    path = fda.download("2026q2", tmp_path, on_bytes=lambda done, total: seen.append((done, total)))
    assert path.read_bytes() == quarter_zip
    assert seen[-1] == (len(quarter_zip), len(quarter_zip))
    assert fda.downloaded(tmp_path) == ["2026q2"]
    fda.download("2026q2", tmp_path)
    assert len(fake_fda.downloads_of(path.name)) == 1  # a whole file is never fetched again


def test_a_stopped_download_carries_on_where_it_stopped(fake_fda, quarter_zip, tmp_path):
    name = "faers_ascii_2026q2.zip"
    fake_fda.files[name] = quarter_zip
    half = len(quarter_zip) // 2
    (tmp_path / f"{name}.part").write_bytes(quarter_zip[:half])
    assert fda.downloaded(tmp_path) == []
    assert fda.download("2026q2", tmp_path).read_bytes() == quarter_zip
    assert fake_fda.downloads_of(name) == [f"bytes={half}-"]
    assert not (tmp_path / f"{name}.part").exists()


def test_a_dropped_connection_is_picked_up_again(fake_fda, quarter_zip, tmp_path):
    name = "faers_ascii_2026q2.zip"
    fake_fda.files[name] = quarter_zip
    fake_fda.cut_after = 1000
    assert fda.download("2026q2", tmp_path).read_bytes() == quarter_zip
    assert fake_fda.downloads_of(name) == ["bytes=0-", "bytes=1000-"]


def test_a_damaged_download_never_takes_the_quarter_s_name(fake_fda, quarter_zip, tmp_path):
    name = "faers_ascii_2026q2.zip"
    damaged = bytearray(quarter_zip)
    damaged[len(damaged) // 3] ^= 0xFF  # inside a compressed file, so its checksum fails
    fake_fda.files[name] = bytes(damaged)
    with pytest.raises(fda.FetchError, match="download it afresh"):
        fda.download("2026q2", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_only_whole_zips_count_as_downloaded(tmp_path):
    (tmp_path / "aers_ascii_2004q1.zip").write_bytes(b"PK")
    (tmp_path / "faers_ascii_2026q2.zip.part").write_bytes(b"PK")
    (tmp_path / "notes.txt").write_text("2026q1")
    assert fda.downloaded(tmp_path) == ["2004q1"]
    assert fda.downloaded(tmp_path / "missing") == []
