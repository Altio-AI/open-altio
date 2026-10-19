"""How a label read is named (open_altio.explorer.labelnames, rule explorer-label-names): the
product its title names, its ingredients, and its forms only where the labels read for a page
differ by form. The words the page makes of them are test_labels_page.py's."""

from __future__ import annotations

from datetime import date

import pytest

from open_altio.explorer.labelnames import parts, product
from open_altio.rulebook import value

RULE = "explorer-label-names"
SAYS = value(RULE, "product_from")  # the Highlights' sentence that names the product


def highlights(name: str, rest: str = "") -> str:
    return (
        f"These highlights do not include all the information needed to use {name} safely and "
        f"effectively. {SAYS} {name}.{rest}"
    )


@pytest.mark.parametrize(
    "title, ingredients, named",
    [
        # a brand in capitals, in title case; a short word after the first keeps its capitals
        (highlights("DIOVAN", " DIOVAN® (valsartan) tablets"), "valsartan", "Diovan"),
        (highlights("DIOVAN HCT"), "hydrochlorothiazide / valsartan", "Diovan HCT"),
        (highlights("ZOMIG-ZMT"), "zolmitriptan", "Zomig-ZMT"),
        # a small word is written small; an abbreviation's own full stops are kept
        (highlights("EMEND FOR INJECTION"), "fosaprepitant", "Emend for Injection"),
        (f"{SAYS} PROTONIX I.V. Initial U.S. Approval", "pantoprazole", "Protonix I.V."),
        # trademark marks are taken out; a name written twice is written once
        (highlights("HEMADY®"), "dexamethasone", "Hemady"),
        (f"{SAYS} IHEEZO TM. IHEEZO", "chloroprocaine", "Iheezo"),
        (
            f"{SAYS} LOPRESSOR HCT LOPRESSOR HCT.",
            "hydrochlorothiazide / metoprolol",
            "Lopressor HCT",
        ),
        # the name stops at the first word with a small letter
        (highlights("SUBOXONE sublingual film"), "buprenorphine / naloxone", "Suboxone"),
    ],
)
def test_a_labels_product_is_the_brand_its_highlights_name_in_title_case(title, ingredients, named):
    assert product(title, ingredients) == named


@pytest.mark.parametrize(
    "title, ingredients",
    [
        (highlights("VALSARTAN TABLETS"), "valsartan"),  # a generic's name: its ingredient
        (highlights("Calcium Acetate Capsules"), "calcium acetate"),  # not in capitals
        ("Maxidex (dexamethasone ophthalmic suspension) 0.1% Sterile", "dexamethasone"),
        ("", "dexamethasone"),  # an older label: no Highlights
        (None, "dexamethasone"),
    ],
)
def test_a_label_without_a_brand_in_its_highlights_has_no_product(title, ingredients):
    assert product(title, ingredients) is None


def row(setid, rxcui, ingredient, title, families, day=date(2026, 1, 1), version=7):
    """A label's row as named() reads it from label_candidates_T."""
    return (setid, rxcui, ingredient, title, day, version, families)


def test_two_products_one_label_each_are_named_by_product_with_no_forms():
    """Valsartan's reports read on Diovan's label and on Diovan HCT's: one label for each code,
    so neither says its forms, though Diovan's stands for by mouth and under the tongue."""
    got = parts(
        [
            row("own", "69749", "valsartan", highlights("DIOVAN"), ["by_mouth", "under_tongue"]),
            row("hct", "214626", "hydrochlorothiazide / valsartan", highlights("DIOVAN HCT"), []),
        ]
    )
    assert got["own"] == {
        "setid": "own",
        "version": 7,
        "date": date(2026, 1, 1),
        "product": "Diovan",
        "ingredients": ["valsartan"],
        "forms": [],
    }
    assert (got["hct"]["product"], got["hct"]["ingredients"], got["hct"]["forms"]) == (
        "Diovan HCT",
        ["hydrochlorothiazide", "valsartan"],
        [],
    )


def test_a_drug_with_one_label_says_nothing_of_its_forms():
    (only,) = parts([row("one", "11289", "warfarin", "", ["by_mouth", "under_tongue"])]).values()
    assert (only["product"], only["ingredients"], only["forms"]) == (None, ["warfarin"], [])


def test_labels_of_one_code_for_different_forms_each_name_their_forms():
    """Dexamethasone's reports read on its tablets', its eye drops' and its injection's labels:
    one code, three set IDs, so each names the route families it was chosen for."""
    got = parts(
        [
            row("tab", "3264", "dexamethasone", highlights("HEMADY"), ["under_tongue", "by_mouth"]),
            row("eye", "3264", "dexamethasone", highlights("DEXTENZA"), ["eye"]),
            row("inj", "3264", "dexamethasone", "", ["injected"]),
            row("otic", "465397", "ciprofloxacin / dexamethasone", "", ["ear"]),
        ]
    )
    assert {k: (v["product"], v["forms"]) for k, v in got.items()} == {
        "tab": ("Hemady", ["by_mouth", "under_tongue"]),
        "eye": ("Dextenza", ["eye"]),
        "inj": (None, ["injected"]),
        "otic": (None, []),  # a combination's code with one label read
    }
