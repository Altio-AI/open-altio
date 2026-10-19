"""How we clean FAERS in a browser: every rule lives in exactly one box of the story, a box says
how many of its rules can be changed and how many are fixed, and opens on them; WHO's drug
classes are a section of their own, with one switch in its head for all five of their rules, and
nothing of them where the host hides the classes or the release carries none. Over the fake
release with the invented classes layer (open_altio.testing.fakeclasses)."""

from __future__ import annotations

import re
import shutil
import time

import pytest
from fastapi.requests import Request

from open_altio.explorer.access import LOCAL, LocalAccess, Viewer
from open_altio.explorer.app import create_app
from open_altio.explorer.pages import UI
from open_altio.faers.insights.cards.drug_classes import NB09
from open_altio.faers.insights.cards.drug_classes import RULE as CARDS_FOR
from open_altio.rulebook import catalogue, load_user_rules
from open_altio.testing import fakeclasses
from open_altio.testing.browser import served

WIDTHS = [320, 768, 1024, 1440]
SECTION = "#step-drug_classes"
RULES = [
    "atc-index",
    "atc-spelling-bridges",
    "atc-group-classes",
    "atc-class-choice",
    "statistics-classes",
]


class NoClasses(LocalAccess):
    """A copy whose host hides WHO's classes, as the hosted switch does when off."""

    def viewer(self, request: Request) -> Viewer:
        return Viewer(id=LOCAL.id, meddra=True, who=False)


@pytest.fixture
def own_classes(classes_release, tmp_path):
    """The classes release, copied so a switch turned on the page saves beside the copy."""
    copy = tmp_path / "releases" / classes_release.name
    shutil.copytree(classes_release, copy)
    with served(create_app(copy)) as base:
        yield base, copy


def wide_enough(page) -> bool:
    return page.evaluate(
        "[document.scrollingElement, ...document.querySelectorAll('.frame-page, dialog[open]')]"
        ".every((e) => e.scrollWidth <= e.clientWidth + 1)"
    )


def boxes_and_their_rules(page) -> dict[str, list[str]]:
    """Open every box of the story, each question's path in turn, and read the rules it holds."""
    held: dict[str, list[str]] = {}
    for q in page.locator('[data-act="m-pick"]').evaluate_all("els => els.map((e) => e.dataset.q)"):
        page.click(f'[data-act="m-pick"][data-q="{q}"]')
        ids = page.locator('[data-act="m-box"]').evaluate_all(
            "els => [...new Set(els.map((e) => e.dataset.item))]"
        )
        for box in ids:
            if box in held:
                continue
            page.locator(f'[data-act="m-box"][data-item="{box}"]').first.click()
            dialog = page.locator("dialog.oa-m-dialog[open]")
            dialog.wait_for()
            held[box] = dialog.locator('.oa-rule[id^="rule-"]:not(.oa-rule-doc)').evaluate_all(
                "els => els.map((e) => e.id.slice(5))"
            )
            page.keyboard.press("Escape")
            dialog.wait_for(state="detached")
    return held


@pytest.mark.parametrize("width", WIDTHS)
def test_every_rule_lives_in_exactly_one_box(opened, classes_site, width):
    page = opened("/methods", base=classes_site, width=width)
    held = boxes_and_their_rules(page)
    said = page.evaluate("() => fetch('/api/rules').then((r) => r.json())")
    every = [r["name"] for r in said["rules"]] + [r["name"] for r in said["named"]]
    # every rule of rules/steps.yaml, with the classes this release carries, and the rules the
    # story names beside them
    assert {r.name for r in catalogue()} <= set(every)
    found = [name for names in held.values() for name in names]
    missing = sorted(set(every) - set(found))
    twice = sorted({n for n in found if found.count(n) > 1})
    assert not missing and not twice, (missing, twice)
    assert sorted(found) == sorted(every)
    assert wide_enough(page)


def test_a_closed_box_says_how_many_rules_can_be_changed_and_how_many_are_fixed(
    opened, classes_site
):
    page = opened("/methods", base=classes_site)
    tile = page.locator('.oa-m-tile[data-item="demographics"] .oa-m-rules-mark')
    assert re.fullmatch(r"\d+ rules? you can change · \d+ fixed", tile.inner_text())
    page.click('.oa-m-tile[data-item="demographics"]')
    dialog = page.locator("dialog.oa-m-dialog[open]")
    can, fixed = (int(n) for n in re.findall(r"\d+", tile.inner_text()))
    groups = dialog.locator(".oa-m-rules-group")
    assert groups.nth(0).locator(".oa-card-sub").inner_text().lower() == "you can change"
    assert groups.nth(0).locator(".oa-rule").count() == can
    assert groups.nth(1).locator(".oa-card-sub").inner_text().lower() == "fixed"
    assert groups.nth(1).locator(".oa-rule").count() == fixed
    # a rule you can change says what Off changes where the release counts it, and nothing
    # where it does not (its row already says Not counted); each fixed one says why
    for row in groups.nth(0).locator(".oa-rule").all():
        assert row.locator(".oa-rule-switch").count() == 1
        under = row.locator(".oa-m-under")
        assert under.count() == 0 or under.inner_text().startswith("Off:")
    for row in groups.nth(1).locator(".oa-rule").all():
        assert row.locator(".oa-m-under").inner_text().startswith("Fixed:")


def test_a_rule_opens_on_its_decision_its_why_and_its_foot(opened, classes_site):
    page = opened("/methods?open=dup-manufacturer-number", base=classes_site)
    row = page.locator('#rule-dup-manufacturer-number[data-open="true"]')
    row.wait_for()
    assert row.locator(".oa-m-decide .oa-rule-value").count() == 2
    card = row.locator(".oa-m-why .oa-m-card").first
    # no subtitle under the title: Shows says what a bar or row is
    assert card.locator(".oa-m-title").inner_text() and card.locator(".oa-m-read").count() == 0
    card.locator(".oa-evidence-chart > *").first.wait_for()  # drawn at the width it has
    assert card.locator(".oa-m-lines dt").all_inner_texts() == [
        "Shows",
        "Why it matters",
        "What we did",
    ]
    shows = card.locator(".oa-m-lines dd").first.inner_text().lower()
    reads = (
        r"\b(each|every|one) (bar|row|line|point|dot|column|cell|square)\b|^(bars?|lines?|areas?):"
    )
    assert re.search(reads, shows), shows
    assert "in this release." not in row.inner_text()
    assert "does not count what it would change" not in page.inner_text("body")
    foot = row.locator(".oa-m-rule-foot").inner_text()
    assert "The rule file" in foot and "The code" in foot


def test_a_rule_named_in_the_address_opens_its_box_on_it(opened, classes_site):
    page = opened("/methods?open=label-table-rows", base=classes_site)
    page.locator('dialog.oa-m-dialog[open][data-box="a_flags"]').wait_for()
    page.locator('#rule-label-table-rows[data-open="true"]').wait_for()


def test_the_page_has_no_step_guide_and_no_search_box(opened, classes_site):
    page = opened("/methods", base=classes_site)
    assert page.locator(".oa-m-guide, .oa-m-find, .oa-m-find-input, .oa-m-intro").count() == 0
    assert page.locator("#narrow, #read, #answer").count() == 3
    for question in ("find", "label", "class", "signal"):
        page = opened(f"/methods#{question}", base=classes_site)
        assert (
            page.locator('[data-act="m-pick"][aria-selected="true"]').get_attribute("data-q")
            == question
        )


@pytest.mark.parametrize("width", WIDTHS)
def test_the_page_fits_the_width_and_nothing_overlaps(opened, classes_site, width):
    page = opened("/methods", base=classes_site, width=width)
    assert wide_enough(page)
    levels = page.evaluate(
        "() => [...document.querySelectorAll('.oa-m-level')].map((e) => e.getBoundingClientRect())"
        ".map((r) => [r.top, r.bottom])"
    )
    for (_, bottom), (top, _) in zip(levels, levels[1:], strict=False):
        assert bottom <= top + 1


@pytest.mark.parametrize("width", WIDTHS)
def test_the_drug_classes_are_one_section_with_one_switch_and_their_evidence(
    opened, classes_site, width
):
    page = opened(f"/methods?open={CARDS_FOR}", base=classes_site, width=width)
    section = page.locator(SECTION)
    rows = section.locator(".oa-rule")
    assert rows.evaluate_all("els => els.map((e) => e.id)") == [f"rule-{r}" for r in RULES]
    for i in range(rows.count()):
        assert rows.nth(i).locator(".oa-rule-line").inner_text()
    switches = section.locator(".oa-rule-switch")
    assert switches.count() == 1 and switches.get_attribute("aria-label") == "WHO drug classes"
    assert section.locator(".oa-rule-group-head .oa-rule-switch").count() == 1
    assert fakeclasses.CITATION in section.locator(".oa-rule-group-head").inner_text()
    # the rule the classes' cards are evidence for opens on them
    assert page.locator(f"#rule-{CARDS_FOR} .oa-evidence").count() >= 1
    rows.nth(1).locator(".oa-rule-head").click()  # a row opens in place, like the others
    assert rows.nth(1).get_attribute("data-open") == "true"
    assert rows.nth(1).locator(".oa-m-why").inner_text()
    assert wide_enough(page)


def test_the_one_switch_turns_the_whole_section_off_and_saves_it(opened, own_classes):
    base, copy = own_classes
    page = opened("/methods?open=classes", base=base)
    assert page.locator("#oa-rebuild").inner_text() == ""
    page.click(f"{SECTION} .oa-rule-switch")
    # the Rebuild bar comes as soon as anything is changed, in the open box
    page.locator("dialog[open] #oa-rebuild", has_text="You changed 1 rule").wait_for()
    assert page.locator(f"{SECTION} .oa-switch-word").inner_text() == "Off"
    assert page.locator(f"{SECTION} .oa-rule").evaluate_all(
        "els => els.map((e) => e.dataset.on)"
    ) == ["false"] * len(RULES)
    saved = copy.parent / "rules.toml"
    for _ in range(100):  # the change is saved beside the release at once
        if saved.is_file():
            break
        time.sleep(0.05)
    assert load_user_rules(saved).off == {"atc-index"}
    page.keyboard.press("Escape")  # closed, the bar stays at the foot of the page
    page.locator("main #oa-rebuild", has_text="You changed 1 rule").wait_for()


@pytest.mark.parametrize("width", WIDTHS)
def test_where_the_host_hides_the_classes_the_page_shows_nothing_of_them(
    opened, classes_release, width
):
    with served(create_app(classes_release, access=NoClasses())) as base:
        page = opened("/methods", base=base, width=width)
        assert page.locator('[data-act="m-pick"]').count() == 3
        assert page.locator('[data-act="m-pick"][data-q="class"]').count() == 0
        held = boxes_and_their_rules(page)
        assert held and not {r for names in held.values() for r in names} & set(RULES)
        assert fakeclasses.CITATION not in page.inner_text("main")
        cards = page.evaluate(
            "() => fetch('/api/rules').then((r) => r.json()).then((d) => d.methods.insights)"
        )
        assert not [c for c in cards if c["notebook"] == NB09]
        assert wide_enough(page)


def test_a_release_without_the_classes_has_no_section(opened, bare_site):
    page = opened("/methods", base=bare_site)
    assert page.locator('[data-act="m-box"]').count() > 0
    assert page.locator('[data-act="m-pick"][data-q="class"]').count() == 0


def test_the_story_types_no_number_of_the_release():
    """Every count on the page comes from the release: none is typed into the page's code."""
    folder = UI / "rules"
    counts = re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{5,}\b|\b\d+\.\d+%")
    for name in ("page.js", "story.js", "homes.js", "words.js"):
        typed = counts.findall((folder / name).read_text(encoding="utf-8"))
        assert not typed, (name, typed)
