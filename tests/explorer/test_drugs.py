"""How the explorer counts a drug (rule explorer-drug-counts), asked through the /api the page
reads: finding a drug by its ingredient or a spelling, the spellings a product page counts and
FDA's spellings with no ingredient it can add, any product containing the drug or that product
alone, FDA's role codes as tick boxes, and the older addresses that name FDA's active ingredient.

What each answer should hold is read from the release's own files through `rel`: its drug records
(`drug_latest_T`, d) with the ingredients the drug-name step read them to (`drug_substance_T`, s).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from open_altio.explorer.filters import ROLES
from open_altio.rulebook import value
from open_altio.testing.rules import rules_with

RULE = "explorer-drug-counts"
SUSPECT = "d.role_cod IN ('PS', 'SS')"
HOLDS_VALSARTAN = "list_contains(string_split(s.substance_T, ';'), 'valsartan')"


def named(rel, cond: str) -> set[str]:
    """era/case_key of the kept cases with a drug record matching `cond`."""
    got = rel.rows(
        "SELECT DISTINCT c.era_T, c.case_key_T FROM case_latest_T c "
        "JOIN drug_latest_T d USING (era_T, primaryid, quarter_T) "
        "JOIN drug_substance_T s USING (era_T, primaryid, quarter_T, drug_seq) "
        f"WHERE c.dup_kept_T AND ({cond})"
    )
    return {f"{e}/{k}" for e, k in got}


def listed_page() -> int:
    return int(value("explorer-page-size", "cases_per_page"))


@pytest.fixture
def counted(ask):
    """counted(client, **params): the cases a page counts, by its count line and its list (the
    fake release fits one page)."""

    def cases(client: TestClient, **params) -> set[str]:
        listed = ask(client, "/api/cases", **params)["cases"]
        assert ask(client, "/api/summary", **params)["cases"] == len(listed) < listed_page()
        return {f"{c['era_T']}/{c['case_key_T']}" for c in listed}

    return cases


# finding a drug -----------------------------------------------------------------------------------


def test_a_search_finds_ingredients_and_combinations_by_name_or_spelling(client, rel, ask):
    found = ask(client, "/api/products", q="valsar")["drugs"]
    assert [d["name"] for d in found] == ["valsartan", "sacubitril;valsartan"]
    valsartan = found[0]
    assert valsartan["title"] == "Valsartan"
    assert valsartan["cases"] == len(named(rel, f"{HOLDS_VALSARTAN} AND {SUSPECT}"))
    assert set(valsartan["reported"]) == {"VALSARTAN", "DIOVAN", "ENTRESTO"}
    assert found[1]["title"] == "Sacubitril and valsartan"
    by_brand = [d["name"] for d in ask(client, "/api/products", q=" diovan ")["drugs"]]
    assert by_brand == ["valsartan"]
    assert "sacubitril;valsartan" in [
        d["name"] for d in ask(client, "/api/products", q="entresto")["drugs"]
    ]
    assert ask(client, "/api/products", q="no such drug at all") == {
        "q": "no such drug at all",
        "drugs": [],
        "unmapped": [],
    }


def test_with_nothing_typed_the_drugs_with_the_most_cases_come_first(client, rel, ask):
    got = ask(client, "/api/products")["drugs"]
    assert 0 < len(got) <= value("explorer-lists", "products_found")
    assert [d["cases"] for d in got] == sorted((d["cases"] for d in got), reverse=True)
    aspirin = next(d for d in got if d["name"] == "acetylsalicylic acid")
    holds = "list_contains(string_split(s.substance_T, ';'), 'acetylsalicylic acid')"
    assert aspirin["cases"] == len(named(rel, f"{holds} AND {SUSPECT}"))


def test_a_search_offers_fdas_spellings_that_have_no_ingredient(client, rel, ask):
    unmapped = ask(client, "/api/products", q="valsar")["unmapped"]
    want = named(rel, f"d.drugname = 'VALSARTAN TEVA' AND s.substance_T IS NULL AND {SUSPECT}")
    assert unmapped == [["VALSARTAN TEVA", len(want)]] and want
    # a spelling the dictionary reads is the drug's, never offered as one with no ingredient
    assert ask(client, "/api/products", q="diovan")["unmapped"] == []


def test_a_spelling_with_no_cases_in_the_release_is_not_offered(
    client, explorer_app, release, rel, tmp_path, ask
):
    """A spelling finds a drug, or is offered with no ingredient, only with cases as a page
    counts them. OMEPRAZOLE is named only as a concomitant drug; VALSARTAN TEVA only as a
    suspect."""
    assert named(rel, "d.drugname = 'OMEPRAZOLE'")
    assert not named(rel, f"d.drugname = 'OMEPRAZOLE' AND {SUSPECT}")
    [omeprazole] = ask(client, "/api/products", q="omeprazole")["drugs"]  # by its ingredient
    assert omeprazole["cases"] == 0 and omeprazole["reported"] == []
    with rules_with(tmp_path, {RULE: {"default_roles": ["C"]}}):
        concomitant = ask(TestClient(explorer_app(release)), "/api/products", q="valsar")
    reported = {d["name"]: d["reported"] for d in concomitant["drugs"]}
    assert reported["valsartan"] == ["DIOVAN"]
    assert concomitant["unmapped"] == []


# a drug's page: its spellings, the unit and the roles ------------------------------------------


def test_a_drug_page_lists_every_spelling_with_its_cases(client, rel, ask):
    got = ask(client, "/api/spellings", product="valsartan")
    assert got["total"] == 3
    for spelling, cases in got["spellings"]:
        assert cases == len(
            named(rel, f"{HOLDS_VALSARTAN} AND {SUSPECT} AND d.drugname = '{spelling}'")
        )
    assert {s for s, _ in got["spellings"]} == {"VALSARTAN", "DIOVAN", "ENTRESTO"}
    alone = ask(client, "/api/spellings", product="valsartan", unit="exact")
    assert {s for s, _ in alone["spellings"]} == {"VALSARTAN", "DIOVAN"}
    assert [
        s for s, _ in ask(client, "/api/spellings", product="valsartan", q="dio")["spellings"]
    ] == ["DIOVAN"]


def test_typing_on_a_drug_page_finds_spellings_with_no_ingredient_to_add(client, ask):
    got = ask(client, "/api/spellings", product="valsartan", q="valsar")
    assert [s for s, _ in got["spellings"]] == ["VALSARTAN"]
    assert [s for s, _ in got["unmapped"]] == ["VALSARTAN TEVA"]
    added = ask(client, "/api/spellings", product="valsartan", q="valsar", include="VALSARTAN TEVA")
    assert added["unmapped"] == [] and [s for s, _ in added["included"]] == ["VALSARTAN TEVA"]


def test_a_spelling_left_out_or_added_changes_what_the_page_counts(client, rel, ask, counted):
    every = named(rel, f"{HOLDS_VALSARTAN} AND {SUSPECT}")
    entresto = named(rel, f"d.drugname = 'ENTRESTO' AND {SUSPECT}")
    teva = named(rel, f"d.drugname = 'VALSARTAN TEVA' AND {SUSPECT}")
    assert counted(client, product="valsartan") == every
    assert counted(client, product="valsartan", exclude="ENTRESTO") == every - entresto
    assert counted(client, product="valsartan", include="VALSARTAN TEVA") == every | teva
    assert ask(client, "/api/summary", product="valsartan", exclude="ENTRESTO")["spellings"] == 2
    assert (
        ask(client, "/api/summary", product="valsartan", include="VALSARTAN TEVA")["spellings"] == 4
    )
    left_out = ask(client, "/api/spellings", product="valsartan", exclude="ENTRESTO")
    assert left_out["excluded"] == [["ENTRESTO", len(entresto)]]


def test_any_product_containing_counts_combinations_and_the_exact_product_does_not(
    client, rel, ask, counted
):
    combined = named(rel, f"s.substance_T = 'sacubitril;valsartan' AND {SUSPECT}")
    alone = named(rel, f"s.substance_T = 'valsartan' AND {SUSPECT}")
    assert combined and alone
    assert counted(client, product="valsartan") == alone | combined
    assert counted(client, product="valsartan", unit="exact") == alone
    assert counted(client, product="sacubitril;valsartan") == combined
    assert counted(client, product="sacubitril", unit="exact") == set()
    assert ask(client, "/api/summary", 400, product="valsartan", unit="some")["problem"]


def test_the_roles_are_fdas_codes_with_their_names_ps_and_ss_ticked(client, ask):
    drugs = ask(client, "/api/release")["drugs"]
    assert drugs["roles"] == [[code, ROLES[code]] for code in value(RULE, "roles")]
    assert [code for code, _ in drugs["roles"]] == ["PS", "SS", "I", "C"]
    assert drugs["default_roles"] == value(RULE, "default_roles") == ["PS", "SS"]
    assert drugs["units"] == [["any", "Any product containing"], ["exact", "Exact product"]]
    assert drugs["default_unit"] == value(RULE, "default_unit")


@pytest.mark.parametrize("roles", [["PS"], ["SS"], ["I"], ["C"], ["PS", "SS", "I", "C"]])
def test_each_role_counts_the_records_fda_coded_so(client, rel, roles, counted):
    codes = ", ".join(f"'{r}'" for r in roles)
    want = named(rel, f"{HOLDS_VALSARTAN} AND d.role_cod IN ({codes})")
    assert want
    assert counted(client, product="valsartan", prole=roles) == want


def test_the_default_roles_are_ps_and_ss_and_an_interacting_drug_is_never_a_suspect(
    client, rel, ask, counted
):
    suspect = counted(client, product="valsartan")
    assert suspect == counted(client, product="valsartan", prole=["SS", "PS"])
    interacting = named(rel, f"{HOLDS_VALSARTAN} AND d.role_cod = 'I'")
    assert interacting and not interacting & suspect
    assert ask(client, "/api/summary", 400, product="valsartan", prole="X")["problem"] == (
        "Drug roles are FDA's codes: PS, SS, I, C."
    )


def test_the_rule_sets_the_roles_and_the_unit_a_page_opens_with(
    explorer_app, release, rel, tmp_path, ask, counted
):
    with rules_with(tmp_path, {RULE: {"default_roles": ["C"], "default_unit": "exact"}}):
        client = TestClient(explorer_app(release))
        want = named(rel, "s.substance_T = 'valsartan' AND d.role_cod = 'C'")
        assert want and counted(client, product="valsartan") == want
        assert ask(client, "/api/release")["drugs"]["default_roles"] == ["C"]


def test_the_case_list_shows_fdas_role_codes_as_published(client, ask):
    rows = ask(client, "/api/cases", product="valsartan", prole=["PS", "SS", "I", "C"])["cases"]
    roles = {d[2] for c in rows for d in c["drugs"] if d[0] in ("VALSARTAN", "DIOVAN")}
    assert roles == {"PS", "SS", "I", "C"}


# older addresses and FDA's spellings with no ingredient ----------------------------------------


@pytest.mark.parametrize(
    "asked, kind, name",
    [
        ("valsartan", "ingredient", "valsartan"),
        ("VALSARTAN", "ingredient", "valsartan"),
        ("ASPIRIN", "ingredient", "acetylsalicylic acid"),  # FDA's active ingredient, as before
        ("SACUBITRIL\\VALSARTAN", "ingredient", "sacubitril;valsartan"),
        ("humira", "ingredient", "adalimumab"),  # a brand opens its drug
        ("Valsartan Teva", "spelling", "VALSARTAN TEVA"),
    ],
)
def test_a_name_opens_the_drug_it_is_read_to(client, asked, kind, name, ask):
    got = ask(client, "/api/product", product=asked)
    assert (got["kind"], got["name"]) == (kind, name)


def test_a_drugs_page_names_its_ingredients_a_combinations_each(client, ask):
    combined = ask(client, "/api/product", product="sacubitril;valsartan")
    assert combined["ingredients"] == ["sacubitril", "valsartan"]
    assert ask(client, "/api/product", product="valsartan")["ingredients"] == ["valsartan"]


def test_an_older_address_counts_what_its_drug_counts(client, ask, counted):
    assert counted(client, product="ASPIRIN") == counted(client, product="acetylsalicylic acid")
    assert ask(client, "/api/product", 404, product="NO SUCH DRUG")["problem"] == "not found"


def test_a_page_of_fdas_spelling_with_no_ingredient_counts_that_spelling(client, rel, ask, counted):
    want = named(rel, f"d.drugname = 'VALSARTAN TEVA' AND {SUSPECT}")
    assert counted(client, product="VALSARTAN TEVA") == want
    got = ask(client, "/api/product", product="VALSARTAN TEVA")
    assert got["title"] == "VALSARTAN TEVA" and got["about"] == "FDA's spelling with no ingredient"
    assert got["ingredients"] == []
    assert ask(client, "/api/spellings", product="VALSARTAN TEVA")["spellings"] == [
        ["VALSARTAN TEVA", len(want)]
    ]


# All cases: the Drugs filter and the chart of ingredients ---------------------------------------


def test_the_drugs_filter_counts_ingredients_and_spellings_in_the_ticked_roles(
    client, rel, counted
):
    teva = named(rel, f"d.drugname = 'VALSARTAN TEVA' AND {SUSPECT}")
    want = named(rel, f"{HOLDS_VALSARTAN} AND {SUSPECT}") | teva
    assert counted(client, dprod=["valsartan", "VALSARTAN TEVA"]) == want
    concomitant = named(rel, f"{HOLDS_VALSARTAN} AND d.role_cod = 'C'")
    assert counted(client, dprod="valsartan", drole="C") == concomitant
    assert counted(client, dprod="ASPIRIN") == counted(client, dprod="acetylsalicylic acid")


def test_the_drug_search_counts_cases_under_the_other_filters_in_the_ticked_roles(client, rel, ask):
    got = ask(client, "/api/drugs", q="valsar", drole="C")
    counts = {d["name"]: d["cases"] for d in got["drugs"]}
    assert counts["valsartan"] == len(named(rel, f"{HOLDS_VALSARTAN} AND d.role_cod = 'C'"))
    assert got["unmapped"] == [["VALSARTAN TEVA", 0]]  # a primary suspect, never concomitant


def test_all_cases_charts_the_ingredients_reported_most_in_the_default_roles(client, rel, ask):
    chart = ask(client, "/api/summary")["drugs"]
    assert 0 < len(chart) <= value("explorer-lists", "top_drugs")
    for name, cases, title in chart:
        holds = f"list_contains(string_split(s.substance_T, ';'), '{name}')"
        assert cases == len(named(rel, f"{holds} AND {SUSPECT}")), name
        assert title == name[:1].upper() + name[1:]
