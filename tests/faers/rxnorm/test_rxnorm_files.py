"""Reading NLM's RxNorm files (rule rxnorm-ingredients), on an invented release."""

from __future__ import annotations

import pytest

from open_altio import rulebook
from open_altio.faers.rxnorm.rrf import RxNormRefused, read_rxnorm
from open_altio.testing.fakerxnorm import CODES, SUPPRESSED, write_rxnorm


def code(name: str) -> str:
    return CODES[name][0]


@pytest.fixture
def rx(tmp_path):
    return read_rxnorm(write_rxnorm(tmp_path / "rxnorm"))


def test_reads_rxnorms_own_names_of_the_four_types(rx):
    assert rx.release == str(rulebook.value("rxnorm-ingredients", "release"))
    assert {rx.names[c] for c, _ in CODES.values()} == {(n, t) for n, (_, t) in CODES.items()}
    assert rx.by_name["glimmerex"] == code("Glimmerex")


def test_ignores_suppressed_lines_and_names_from_other_sources(rx):
    assert SUPPRESSED[0] not in rx.names
    assert "zorbatide old" not in rx.by_name
    assert "lumirex" not in rx.by_name


def test_every_name_stands_for_its_ingredients(rx):
    assert rx.ingredients[code("zorbatide sodium")] == {code("zorbatide")}
    assert rx.ingredients[code("Glimmerex")] == {code("zorbatide")}
    assert rx.ingredients[code("Duotrel")] == {code("quintelamab"), code("veltrozine")}


def test_reads_the_drug_each_brand_sells(rx):
    assert rx.brand_salts[code("Enhertu")] == {code("trastuzumab deruxtecan")}
    assert code("Duotrel") not in rx.brand_salts


def test_a_multiple_ingredient_listing_a_salt_counts_the_salts_ingredient(rx):
    both = frozenset({code("veltrozine"), code("zorbatide")})
    assert rx.sets[both] == code("veltrozine / zorbatide sodium")


def test_refuses_another_release_than_the_rule_pins(tmp_path):
    folder = write_rxnorm(tmp_path / "rxnorm", release="01012000")
    with pytest.raises(RxNormRefused, match="01012000 release"):
        read_rxnorm(folder)


def test_refuses_a_folder_without_nlms_readme_or_files(tmp_path):
    folder = write_rxnorm(tmp_path / "rxnorm")
    (folder / "rrf" / "RXNREL.RRF").unlink()
    with pytest.raises(RxNormRefused, match="RXNREL.RRF is missing"):
        read_rxnorm(folder)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RxNormRefused, match="Readme"):
        read_rxnorm(empty)
    with pytest.raises(RxNormRefused, match="not a folder"):
        read_rxnorm(tmp_path / "nowhere")


def test_the_default_folder_is_rxnorm_in_the_data_folder_unless_moved(tmp_path, monkeypatch):
    from open_altio import paths

    monkeypatch.delenv(paths.RXNORM_ENV, raising=False)
    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path))
    assert paths.rxnorm_folder() == tmp_path / "rxnorm"
    monkeypatch.setenv(paths.RXNORM_ENV, str(tmp_path / "elsewhere"))
    assert paths.rxnorm_folder() == tmp_path / "elsewhere"
