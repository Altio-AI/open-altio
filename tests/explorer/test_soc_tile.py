"""The Overview tile of cases by MedDRA system organ class (src/open_altio/explorer/socs.py): its
counts, the filter a bar sets, and its being a licensed part, so only a viewer with MedDRA has
the tile, the filter and the API field."""

from __future__ import annotations

import pytest

from open_altio.rulebook import value
from open_altio.testing.browser import settle

WIDTHS = [320, 768, 1024, 1440]
TILE = '.oa-chart:has([data-key="soc"])'


def listed(client, ask, **params):
    return ask(client, "/api/cases", size=1000, **params)["cases"]


def test_each_class_counts_the_cases_with_a_reaction_in_it(licensed_client, ask):
    tile = ask(licensed_client, "/api/summary")["soc"]
    every = listed(licensed_client, ask)
    assert tile and len({k for k, _ in tile}) == len(tile)
    for name, n in tile:
        assert n == sum(name in c["socs_T"] for c in every)
    # a case with reactions in two classes counts in both
    assert any(len(c["socs_T"]) > 1 for c in every)


def test_the_tile_counts_under_the_other_filters_and_not_its_own(licensed_client, ask):
    one = ask(licensed_client, "/api/summary", sex="F")
    want = {}
    for c in listed(licensed_client, ask, sex="F"):
        for s in c["socs_T"]:
            want[s] = want.get(s, 0) + 1
    assert dict(map(tuple, one["soc"])) == want
    name = one["soc"][0][0]
    chosen = ask(licensed_client, "/api/summary", soc=name)
    assert dict(map(tuple, chosen["soc"])) == dict(
        map(tuple, ask(licensed_client, "/api/summary")["soc"])
    )


def test_how_many_cases_the_class_is_found_for_is_counted(licensed_client, ask):
    every = listed(licensed_client, ask)
    found, cases = ask(licensed_client, "/api/summary")["given"]["soc"]
    assert (found, cases) == (sum(bool(c["socs_T"]) for c in every), len(every))


def test_a_class_filter_keeps_the_cases_with_any_reaction_in_it(licensed_client, ask):
    every = listed(licensed_client, ask)
    name = ask(licensed_client, "/api/summary")["soc"][0][0]
    kept = {c["case_key_T"] for c in every if name in c["socs_T"]}
    assert ask(licensed_client, "/api/summary", soc=name)["cases"] == len(kept)
    assert {c["case_key_T"] for c in listed(licensed_client, ask, soc=name)} == kept
    two = [n for n, _ in ask(licensed_client, "/api/summary")["soc"][:2]]
    both = {c["case_key_T"] for c in every if set(two) & set(c["socs_T"])}
    assert ask(licensed_client, "/api/summary", soc=two)["cases"] == len(both)


def test_a_name_that_is_no_class_is_refused(licensed_client, ask):
    ask(licensed_client, "/api/summary", status=400, soc="Not a class")


@pytest.mark.parametrize("who", ["ann", "ann+meddra"])
def test_only_a_viewer_with_the_licensed_part_has_the_field_and_the_filter(
    people, licensed_release, ask, who
):
    web = people(licensed_release)
    seen = {"X-Viewer": who}
    summary = ask(web, "/api/summary", headers=seen)
    if who == "ann":
        assert "soc" not in summary and "soc" not in summary["given"]
        ask(web, "/api/summary", headers=seen, status=403, soc="Anything")
    else:
        assert summary["soc"] and "soc" in summary["given"]


def test_a_release_without_meddra_has_none(client, ask):
    assert "soc" not in ask(client, "/api/summary")


def tile_state(page):
    return page.evaluate(
        """(sel) => {
        const t = document.querySelector(sel).getBoundingClientRect();
        const others = [...document.querySelectorAll('.oa-charts > .oa-chart')]
          .filter((e) => !e.matches(sel)).map((e) => e.getBoundingClientRect());
        const hit = others.some((o) => o.left < t.right && t.left < o.right
          && o.top < t.bottom && t.top < o.bottom);
        return { right: t.right, left: t.left, hit };
      }""",
        TILE,
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_the_tile_sits_in_the_overview_and_nothing_overflows_or_overlaps(site, opened, ask, width):
    page = opened("/all/overview", base=site, width=width)
    page.wait_for_selector(TILE)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    got = tile_state(page)
    assert got["left"] >= 0 and got["right"] <= width and not got["hit"], got
    order = page.eval_on_selector_all(
        ".oa-charts > .oa-chart [data-key], .oa-charts > .oa-chart .chart-lead",
        "(els) => els.filter((e) => e.dataset.key).map((e) => e.dataset.key)",
    )
    firsts = list(dict.fromkeys(order))
    assert firsts.index("reaction") < firsts.index("soc") < firsts.index("outcome")
    assert "found for" in page.inner_text(TILE)
    # titled and cut like the other tiles: a label line, then the most-reported classes
    assert " ".join(page.inner_text(TILE).split()).startswith("System organ classes reported most")
    assert page.locator(f"{TILE} [data-key]").count() <= value("explorer-lists", "socs_charted")


def test_pressing_a_bar_filters_to_the_cases_with_a_reaction_in_that_class(
    site, opened, licensed_client, ask
):
    page = opened("/all/overview", base=site)
    page.wait_for_selector(TILE)
    name = page.get_attribute(f"{TILE} .chart-track", "data-v")
    want = ask(licensed_client, "/api/summary", soc=name)["cases"]
    page.click(f"{TILE} .chart-track")
    page.wait_for_function(
        f"() => document.querySelector('#oa-countline strong')?.textContent === '{want:,}'"
    )
    settle(page)
    assert page.get_attribute(f"{TILE} li", "data-state") == "chosen"
    assert "System organ class" in page.inner_text("body") and name in page.inner_text("body")


@pytest.mark.parametrize("width", WIDTHS)
def test_a_viewer_without_the_part_has_no_tile(demo_site, opened, width):
    page = opened("/all/overview", base=demo_site, width=width)
    page.wait_for_selector(".oa-charts")
    assert page.locator(TILE).count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
