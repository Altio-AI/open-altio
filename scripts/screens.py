"""Screenshots of every screen the explorer draws, and a pixel diff of two sets of them: the check
that a change to the page's code or styles leaves its look alone.

    uv run python scripts/screens.py shoot <out> [--only <name>]  # every screen, light and dark
    uv run python scripts/screens.py diff <before> <after> <out>  # an image a pair, report.md

The explorer runs on the fake release (open_altio.testing.fakefda) with its MedDRA part and its
build time stamped to one fixed moment; the browser's clock, time zone and kept choices are fixed
too (open_altio.testing.browser), so two runs of the same code give the same pixels. Each screen
is shot at 390, 1024 and 1440 px wide; a page is shot whole, as tall as its content. Needs
Playwright and its headless shell (`uv run playwright install --only-shell chromium`).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from open_altio.testing.browser import HEIGHTS, NOW, open_page, served, settle

WIDTHS = (390, 1024, 1440)
THEMES = ("light", "dark")
# a colour channel that moves by no more than this is anti-aliasing, not a change
NOISE = 24


@dataclass(frozen=True)
class Shot:
    name: str
    path: str
    act: Callable[[Any], None] | None = None  # what a person does once the page is drawn
    widths: Sequence[int] = WIDTHS
    whole: bool = True  # the whole page, as tall as its content; False for a dialog or a menu
    kept: dict[str, Any] = field(default_factory=dict)  # what this browser keeps, over the set's


# ---- the release --------------------------------------------------------------------------------


class FixedClock:
    def now(self) -> datetime:
        return NOW


# one folder, the same on every run, since the Tables page names where the release's files are
WORK = Path(tempfile.gettempdir()) / "open-altio-screens"


def fake_release(work: Path = WORK) -> Path:
    """The fake release with both invented MedDRA versions, built into `work`, its build time
    stamped to NOW so the pages that show it never change between runs."""
    import duckdb

    from open_altio.faers import EXPLORER_FILE, build_release
    from open_altio.faers.meddra import build_licensed
    from open_altio.testing import fakediana, fakefda
    from open_altio.testing.fakemeddra import write_meddra

    diana = fakediana.write_dictionary(work / "diana" / "DiAna_dictionary.csv")
    with fakediana.pinned(diana, work):
        release = build_release(
            fakefda.write_input(work / "zips"),
            work / "releases",
            overwrite=True,
            diana_dictionary=diana,
        )
    for version in ("29.0", "29.1"):
        build_licensed(release, write_meddra(work / "meddra" / version, version))
    manifest = release / "manifest.json"
    manifest.write_text(
        json.dumps(json.loads(manifest.read_text()) | {"built_at": NOW.isoformat()}, indent=2)
    )
    with duckdb.connect(str(release / EXPLORER_FILE)) as con:
        con.execute("UPDATE explorer_release_T SET built_at_T = ?", [NOW.replace(tzinfo=None)])
    return release


# ---- shooting ------------------------------------------------------------------------------------


def shoot(
    base: str,
    shots: Sequence[Shot],
    out: Path,
    *,
    cookies: Sequence[dict[str, str]] = (),
    kept: dict[str, Any] | None = None,
    only: str = "",
) -> int:
    """Every shot at its widths in both themes, as <name>-<width>-<theme>.png in `out`. Answers
    how many failed; one that fails leaves the others."""
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for shot in (s for s in shots if only in s.name):
            for width in shot.widths:
                for theme in THEMES:
                    path = out / f"{shot.name}-{width}-{theme}.png"
                    try:
                        take(
                            browser,
                            base,
                            shot,
                            width,
                            theme,
                            {**(kept or {}), **shot.kept},
                            cookies,
                            path,
                        )
                        print(path.name, flush=True)
                    except Exception as exc:  # reported, and the next shot goes on
                        failed += 1
                        print(f"FAIL {path.name}: {str(exc).splitlines()[0]}", flush=True)
        browser.close()
    return failed


def take(
    browser: Any,
    base: str,
    shot: Shot,
    width: int,
    theme: str,
    kept: dict[str, Any],
    cookies: Sequence[dict[str, str]],
    path: Path,
) -> None:
    page = open_page(
        browser, base + shot.path, width=width, theme=theme, kept=kept, cookies=cookies
    )
    try:
        if shot.act:
            shot.act(page)
            settle(page)
        page.mouse.move(0, HEIGHTS[width] - 1)  # no hover, no tip
        page.evaluate(
            "() => { const t = document.getElementById('oa-tip'); if (t) t.hidden = true; }"
        )
        if shot.whole:
            page.set_viewport_size({"width": width, "height": whole_height(page, width)})
            settle(page)
        page.screenshot(path=str(path), animations="disabled", caret="hide")
    finally:
        page.context.close()


def whole_height(page: Any, width: int) -> int:
    """How tall the window must be to show the page's scroller without scrolling."""
    return int(
        page.evaluate(
            """(h) => {
      const s = document.querySelector('.frame-page') || document.scrollingElement;
      return Math.max(h, Math.ceil(s.scrollHeight + (window.innerHeight - s.clientHeight)));
    }""",
            HEIGHTS[width],
        )
    )


# ---- what a person does on a screen --------------------------------------------------------------


def click(selector: str, wait: str = "") -> Callable[[Any], None]:
    def act(page: Any) -> None:
        page.click(selector)
        if wait:
            page.wait_for_selector(wait)

    return act


def typed(selector: str, text: str) -> Callable[[Any], None]:
    def act(page: Any) -> None:
        page.fill(selector, text)
        page.wait_for_timeout(400)  # the searches wait for typing to pause

    return act


def key(name: str) -> Callable[[Any], None]:
    return lambda page: page.keyboard.press(name)


def steps(*acts: Callable[[Any], None]) -> Callable[[Any], None]:
    def act(page: Any) -> None:
        for one in acts:
            one(page)
            settle(page)

    return act


def filters(row: str = "reactions") -> Callable[[Any], None]:
    """The filters menu, open on one filter's options (on a phone, the sheet's options pane)."""
    return steps(
        click(".oa-filters-btn", "#oa-filter-menu"),
        click(f'#oa-filter-menu [data-act="filter-row"][data-row="{row}"]'),
    )


def kept_products(*names: str) -> dict[str, Any]:
    """Products a person opened earlier, an hour apart, the first most lately."""
    opened = NOW - timedelta(hours=2)
    return {
        "products": [
            {
                "name": n,
                "label": "",
                "opened": int((opened - timedelta(hours=i)).timestamp() * 1000),
            }
            for i, n in enumerate(names)
        ]
    }


PRODUCTS = kept_products("acetylsalicylic acid", "valsartan")

EXPLORER = [
    Shot("home", "/"),
    Shot("home-first-visit", "/", kept={"products": []}),
    Shot("home-find", "/", typed("#oa-find", "valsar")),
    Shot("all-overview", "/all/overview"),
    Shot("all-cases", "/all/cases"),
    Shot("all-month", "/all/overview", click('[data-act="grain"][data-v="month"]')),
    Shot("reaction", "/all/overview", click('#oa-body [data-act="chart"][data-key="reaction"]')),
    Shot("product-overview", "/product/valsartan/overview"),
    Shot("product-cases", "/product/valsartan/cases"),
    Shot(
        "product-roles",
        "/product/valsartan/overview",
        steps(click('[data-act="prole"][data-v="I"]'), click('[data-act="prole"][data-v="C"]')),
    ),
    Shot(
        "product-exact", "/product/valsartan/overview", click('[data-act="unit"][data-v="exact"]')
    ),
    Shot(
        "product-spellings",
        "/product/valsartan/overview",
        click(".oa-title-spellings"),
        whole=False,
    ),
    Shot(
        "product-spellings-find",
        "/product/valsartan/overview",
        steps(
            click(".oa-title-spellings"),
            click('[data-act="spell"][data-v="ENTRESTO"]'),
            typed("#oa-spell-find", "valsar"),
            click('[data-act="spell-add"][data-v="VALSARTAN TEVA"]'),
        ),
        whole=False,
    ),
    Shot("product-no-ingredient", "/product/VALSARTAN%20TEVA/overview"),
    Shot("filters", "/all/overview", filters(), whole=False),
    Shot(
        "filters-terms", "/all/overview", steps(filters(), typed("#oa-term-find", "a")), whole=False
    ),
    Shot(
        "filters-smqs",
        "/all/overview",
        steps(filters(), click('[data-act="kind"][data-v="smq"]')),
        whole=False,
    ),
    Shot("filters-drugs", "/all/overview", filters("drugs"), whole=False),
    Shot(
        "filters-drugs-find",
        "/all/overview",
        steps(filters("drugs"), typed("#oa-drug-find", "valsar")),
        whole=False,
    ),
    Shot("filters-received", "/all/overview", filters("received"), whole=False),
    Shot("filters-country", "/all/overview", filters("country"), whole=False),
    Shot("filters-outcome", "/product/valsartan/overview", filters("outcome"), whole=False),
    Shot("filters-era", "/all/overview", filters("era"), whole=False),
    Shot("filters-dedup", "/all/overview", filters("dedup"), whole=False),
    Shot(
        "filtered",
        "/all/cases",
        steps(filters("sex"), click('[data-act="opt"][data-key="sex"]'), key("Escape")),
    ),
    Shot(
        "cmq",
        "/all/overview",
        steps(filters(), click('[data-act="cmq-new"]', "#oa-cmq-find"), typed("#oa-cmq-find", "a")),
        whole=False,
    ),
    Shot(
        "case-dialog",
        "/all/cases",
        click('tr[data-act="case"]', "#oa-case .oa-case-lead"),
        whole=False,
    ),
    Shot(
        "case-dialog-legacy-term",
        "/all/cases",
        click('tr[data-act="case"]:has(.case-key:text-is("5100009"))', "#oa-case .oa-case-lead"),
        whole=False,
    ),
    Shot(
        "case-dialog-came-back",
        "/all/cases",
        click('tr[data-act="case"]:has(.case-key:text-is("9013013"))', "#oa-case .oa-case-lead"),
        whole=False,
    ),
    Shot(
        "statistics-by-pt",
        "/product/metformin/statistics",
        kept={"statistics-screens": {"list": "all"}},
    ),
    Shot("rules-meddra-terms", "/rules?open=meddra-terms"),
    Shot(
        "export",
        "/product/valsartan/cases",
        click('[data-act="export"]', "#oa-export-format .slide-switch"),
        whole=False,
    ),
    Shot("settings", "/", click('[data-act="settings"]:visible'), whole=False, widths=(1024, 1440)),
    Shot("tables", "/release"),
    Shot("tables-column-find", "/release", typed("#oa-col-find", "dt")),
    Shot("sql-result", "/release", click('[data-act="sql-run"]', ".oa-sql-bar")),
    Shot(
        "sql-examples", "/release", click('[data-act="sql-examples"]', ".oa-examples"), whole=False
    ),
    Shot("cite", "/release", click('[data-act="cite"]', ".oa-cite-text"), whole=False),
    Shot(
        "product-menu",
        "/",
        steps(
            lambda page: page.hover(".oa-prod-row"), click('.oa-prod-row [data-act="prod-menu"]')
        ),
        whole=False,
        widths=(1440,),
    ),
    Shot(
        "rail-products",
        "/",
        click('.oa-rail [data-act="rail-products"]'),
        whole=False,
        widths=(1024,),
    ),
    Shot("drawer", "/", click('.oa-topbar [data-act="side-open"]'), whole=False, widths=(390,)),
]


def shoot_explorer(out: Path, only: str = "") -> int:
    from open_altio.explorer.app import create_app

    with served(create_app(fake_release(), clock=FixedClock())) as base:
        return shoot(base, EXPLORER, out, kept=PRODUCTS, only=only)


# ---- the diff ------------------------------------------------------------------------------------


def diff(before: Path, after: Path, out: Path) -> list[tuple[str, float, float]]:
    """Each pair compared pixel by pixel: an image per pair (the after shot faded, every changed
    pixel in red) and report.md with the share of pixels changed, at all and beyond NOISE. Answers
    the rows, the most changed first."""
    from PIL import Image, ImageChops

    out.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, float, float]] = []
    missing = []
    for name in sorted(
        {p.name for p in before.glob("*.png")} | {p.name for p in after.glob("*.png")}
    ):
        if not ((before / name).is_file() and (after / name).is_file()):
            missing.append(f"{name}: only {'before' if (before / name).is_file() else 'after'}")
            continue
        one, two = Image.open(before / name).convert("RGB"), Image.open(after / name).convert("RGB")
        size = (max(one.width, two.width), max(one.height, two.height))
        one, two = padded(one, size), padded(two, size)
        red, green, blue = ImageChops.difference(one, two).split()
        most = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        moved = most.histogram()
        total = size[0] * size[1]
        rows.append((name, sum(moved[1:]) / total, sum(moved[NOISE + 1 :]) / total))
        picture = Image.blend(Image.new("RGB", size, "white"), two, 0.25)
        picture.paste(
            Image.new("RGB", size, (220, 0, 0)), mask=most.point(lambda v: 255 if v else 0)
        )
        picture.save(out / name)
    rows.sort(key=lambda r: (-r[2], -r[1], r[0]))
    lines = [
        "# Screens before and after",
        "",
        f"{len(rows)} pairs. A pixel counts as changed when any colour channel moved, and as",
        f"beyond noise when one moved by more than {NOISE} of 255. A pair of different heights is",
        "compared on the taller one, the shorter padded in magenta.",
        "",
        "| Shot | Changed | Beyond noise |",
        "|---|---:|---:|",
    ]
    lines += [f"| {n} | {c:.4%} | {b:.4%} |" for n, c, b in rows]
    if missing:
        lines += ["", "Not in both sets:", ""] + [f"- {m}" for m in missing]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    return rows


def padded(image: Any, size: tuple[int, int]) -> Any:
    from PIL import Image

    if image.size == size:
        return image
    canvas = Image.new("RGB", size, (255, 0, 255))
    canvas.paste(image, (0, 0))
    return canvas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("shoot", help="screenshots of every screen into a folder")
    one.add_argument("out", type=Path)
    one.add_argument("--only", default="", help="only the shots whose name holds this")
    two = sub.add_parser("diff", help="compare two folders of screenshots")
    two.add_argument("before", type=Path)
    two.add_argument("after", type=Path)
    two.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "shoot":
        return 1 if shoot_explorer(args.out, args.only) else 0
    for name, changed, beyond in diff(args.before, args.after, args.out)[:5]:
        print(f"{name}: {changed:.4%} changed, {beyond:.4%} beyond noise")
    return 0


if __name__ == "__main__":
    sys.exit(main())
