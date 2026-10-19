"""The rules page walked in a browser, on a person's own copy, at 390, 1024 and 1440 px: the page
as built, a row opened, a rule switched off and two values changed (and a wrong value refused),
the rebuild with its progress, then the new counts beside Altio's, the "Your rules" notice on the
rules page, All cases and Home, All cases opening as the changed rules say, and the rules file
downloaded.

    .venv/bin/python tests/walks/rules_page.py --out <folder for the shots>

For each width it starts its own explorer (tests/walks/rules_server.py) over a fresh fake release
in a scratch folder, and stops it after. It uses Playwright's headless shell
(python -m playwright install --only-shell chromium). Prints one line per check and exits 1 if
any fails.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Browser, ConsoleMessage, Page, Response, sync_playwright

from open_altio.testing.browser import HEIGHTS, free_port

HERE = Path(__file__).resolve().parent
OFF = "deleted-cases"  # switched off on the walk
CHANGED = ("dup-manufacturer-number", "max_age_gap_years")  # the value changed
SHOWN = ("dedup-default", "explorer_default")  # set to show probable duplicates when a page opens

failures: list[str] = []


def check(ok: bool, what: str, detail: object = "") -> None:
    print(
        f"{'ok  ' if ok else 'FAIL'} {what}" + (f": {detail}" if detail and not ok else ""),
        flush=True,
    )
    if not ok:
        failures.append(what)


def start_explorer(python: str, work: Path) -> tuple[subprocess.Popen, str]:
    port = free_port()
    server = subprocess.Popen(
        [
            python,
            str(HERE / "rules_server.py"),
            "--port",
            str(port),
            "--work",
            str(work),
            "--step-seconds",
            "0.6",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert server.stdout is not None
    for line in server.stdout:
        if "rules walk explorer on" in line:
            break
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return server, url
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("the explorer did not start")


def shot(page: Page, out: Path, name: str, width: int, whole: bool = False) -> None:
    page.wait_for_timeout(250)  # a row's chevron turns as it opens
    if whole:
        tall = page.evaluate("document.querySelector('.frame-page').scrollHeight")
        page.set_viewport_size({"width": width, "height": tall})
        page.wait_for_timeout(250)
    page.screenshot(path=str(out / f"{name}-{width}.png"))
    if whole:
        page.set_viewport_size({"width": width, "height": HEIGHTS[width]})


def saved_rules(work: Path, holding: str) -> str:
    """The rules file beside the release once it holds the last choice, saved as it was made."""
    path = work / "releases" / "rules.toml"
    for _ in range(50):
        text = path.read_text() if path.is_file() else ""
        if holding in text:
            break
        time.sleep(0.1)
    return text


def place(page: Page, selector: str) -> list[float]:
    """Where an element sits on the page itself, wherever the page is scrolled to."""
    return page.evaluate(
        """(sel) => { const r = document.querySelector(sel).getBoundingClientRect();
          const s = document.querySelector('.frame-page');
          return [r.left, r.top + s.scrollTop, r.width, r.height]; }""",
        selector,
    )


def no_sideways_scroll(page: Page, where: str, width: int) -> None:
    wide = page.evaluate(
        "Math.max(document.documentElement.scrollWidth, "
        "document.querySelector('.frame-page')?.scrollWidth || 0)"
    )
    check(wide <= width, f"{width}: no sideways scroll on {where}", wide)


def walk(page: Page, url: str, out: Path, width: int, work: Path) -> None:
    rule, key = CHANGED
    page.goto(f"{url}/rules", wait_until="networkidle")
    page.wait_for_selector(".oa-journey")
    check(
        page.locator(".oa-journey-steps > li").count() == 4,
        f"{width}: the journey has a box per step",
    )
    check(
        page.locator(".oa-rule[id^='rule-']:not(.oa-rule-doc)").count() >= 10,
        f"{width}: every rule has its row",
    )
    check(
        page.locator(".oa-rule-switch").count() >= 7
        and page.locator(".oa-rule-state .oa-chip").count() == 3,
        f"{width}: rules have switches, always-on ones are locked",
    )
    check(
        page.locator("#oa-rebuild").inner_text().strip() == "", f"{width}: no bar before any change"
    )
    no_sideways_scroll(page, "the rules page", width)
    shot(page, out, "01-rules", width, whole=True)

    # a row opens in place; nothing above it moves
    head = page.locator(f"#rule-{rule} .oa-rule-head")
    above = place(page, f"#rule-{OFF} .oa-rule-head")
    head.click()
    page.wait_for_selector(f"#rule-{rule} .oa-rule-body")
    check(
        place(page, f"#rule-{OFF} .oa-rule-head") == above,
        f"{width}: opening a row moves nothing above it",
    )
    check("open=" in page.url, f"{width}: the address names the open row")
    head.scroll_into_view_if_needed()
    shot(page, out, "02-row-open", width)

    # switch a rule off: its word changes in its own width, and the bar counts it
    below = place(page, "#rule-dedup-default .oa-rule-head")
    switch = page.locator(f"#rule-{OFF} .oa-rule-switch")
    switch.click()
    check(
        switch.get_attribute("aria-checked") == "false" and switch.inner_text().strip() == "Off",
        f"{width}: the switch turns the rule off",
    )
    check(
        place(page, "#rule-dedup-default .oa-rule-head") == below,
        f"{width}: switching moves no row",
    )
    page.wait_for_selector(".oa-rebuild-bar")
    check(
        "You changed 1 rule." in page.locator(".oa-rebuild-bar").inner_text(),
        f"{width}: the bar counts the change",
    )

    # a value: a wrong one is refused in plain words and Rebuild waits; a right one is kept
    box = page.locator(f"#rule-{rule} .oa-value-input[data-key='{key}']")
    box.fill("two")
    page.wait_for_selector(f"#rule-{rule} .oa-rule-value-problem:not([hidden])")
    said = page.locator(f"#rule-{rule} .oa-rule-value-problem:not([hidden])").inner_text()
    check(
        "must be a number" in said,
        f"{width}: a value that is not a number is refused, saying why",
        said,
    )
    check(
        page.locator("[data-act='rules-rebuild']").is_disabled(),
        f"{width}: Rebuild waits for the value to be fixed",
    )
    box.fill("5")
    problems = f"[...document.querySelectorAll('#rule-{rule} .oa-rule-value-problem')]"
    page.wait_for_function(f"!{problems}.some((p) => !p.hidden)")
    page.wait_for_function("!document.querySelector(\"[data-act='rules-rebuild']\").disabled")
    words = page.locator(f"#rule-{rule} .oa-switch-word").inner_text()
    check(words == "On, changed", f"{width}: the row says it is changed", words)
    check(
        "Altio: 2" in page.locator(f"#rule-{rule} .oa-rule-value-set").first.inner_text(),
        f"{width}: Altio's value shows beside the changed one",
    )
    check(
        "You changed 2 rules." in page.locator(".oa-rebuild-bar").inner_text(),
        f"{width}: the bar counts both",
    )

    # a choice: probable duplicates shown when a page opens
    page.locator(f"#rule-{SHOWN[0]} .oa-rule-head").click()
    page.locator(f"#rule-{SHOWN[0]} [data-key='{SHOWN[1]}'][data-i='1']").click()
    page.wait_for_function(
        "/You changed 3 rules/.test(document.querySelector('.oa-rebuild-bar').innerText)"
    )
    saved = saved_rules(work, f'{SHOWN[1]} = "all"')
    check(
        "[deleted-cases]" in saved
        and "on = false" in saved
        and f"{key} = 5" in saved
        and f'{SHOWN[1]} = "all"' in saved,
        f"{width}: the choices are saved in rules.toml beside the release",
        saved,
    )
    no_sideways_scroll(page, "the changed rules", width)
    page.locator(f"#rule-{OFF}").scroll_into_view_if_needed()
    shot(page, out, "03-changed", width)

    # rebuild: progress in the bar, then the explorer opens on the new release
    page.locator("[data-act='rules-rebuild']").click()
    page.wait_for_selector(".oa-rebuild-bar[data-state='running'] .oa-rebuild-track i")
    page.wait_for_function("/Step [2-9]/.test(document.querySelector('.oa-rebuild-bar').innerText)")
    check(
        "Rebuilding with your rules" in page.locator(".oa-rebuild-bar").inner_text(),
        f"{width}: the rebuild shows its progress",
    )
    shot(page, out, "04-rebuilding", width)
    with page.expect_navigation(timeout=60000):
        pass
    page.wait_for_selector(".oa-yours")
    page.wait_for_selector(".oa-toast")
    check(
        "Rebuilt with your rules" in page.locator(".oa-toast").inner_text(),
        f"{width}: the rebuild says it is done",
    )
    notice = page.locator(".oa-yours-head").inner_text()
    check(
        notice == "Your rules: 1 off, 2 changed",
        f"{width}: the rules page names the release's rules",
        notice,
    )
    altio = page.locator(".oa-jstep-altio .oa-fda").all_inner_texts()
    check(
        bool(altio) and all(t.startswith("Altio: ") for t in altio),
        f"{width}: the rebuilt counts differ, with Altio's beside them",
        altio,
    )
    moved = page.locator(f"#rule-{OFF} .oa-rule-moved").inner_text()
    check(
        moved.startswith("None") and "Altio:" in moved,
        f"{width}: the rule switched off moved nothing, Altio's count beside",
        moved,
    )
    check(
        "with your rules" in page.locator(".oa-subtitle").inner_text(),
        f"{width}: the release says it was built with them",
    )
    check(
        page.locator("#oa-rebuild").inner_text().strip() == "",
        f"{width}: no bar once the release has the rules",
    )
    no_sideways_scroll(page, "the rebuilt rules page", width)
    page.evaluate("document.querySelector('.frame-page').scrollTo(0, 0)")
    shot(page, out, "05-rebuilt", width)
    with page.expect_download() as got:
        page.locator("[data-act='rules-download']").click()
    text = Path(got.value.path()).read_text()
    check(
        got.value.suggested_filename == "rules.toml" and "on = false" in text,
        f"{width}: Download your rules",
    )

    # the notice on every page with counts
    page.goto(f"{url}/all/overview", wait_until="networkidle")
    page.wait_for_selector(".oa-yours-notice")
    check(
        page.locator(".oa-yours-notice").inner_text() == notice,
        f"{width}: All cases carries the notice",
    )
    page.locator(".oa-yours-notice").click()
    menu = page.locator(".oa-yours-menu")
    menu.wait_for()
    check(
        menu.locator(".menu-item").count() == 3, f"{width}: the notice lists each rule that differs"
    )
    line = page.locator("#oa-countline").inner_text()
    check(
        page.locator("#oa-dups").is_checked(),
        f"{width}: All cases opens with probable duplicates, as chosen",
        line,
    )
    shot(page, out, "06-notice-all-cases", width)
    page.goto(f"{url}/", wait_until="networkidle")
    page.wait_for_selector(".oa-release-card .oa-yours-notice")
    check(True, f"{width}: Home's release card carries the notice")
    no_sideways_scroll(page, "Home", width)


def walk_at(browser: Browser, python: str, out: Path, width: int, errors: list[str]) -> None:
    """The walk at one width, on an explorer of its own over a fresh fake release."""
    with tempfile.TemporaryDirectory() as scratch:
        server, url = start_explorer(python, Path(scratch))
        try:
            page = browser.new_page(
                viewport={"width": width, "height": HEIGHTS[width]}, accept_downloads=True
            )
            refused: list[tuple[str, str, int]] = []

            def answered(r: Response) -> None:
                if r.status >= 400:
                    refused.append((r.request.method, r.url.removeprefix(url), r.status))

            def said(m: ConsoleMessage) -> None:
                # the browser logs a refused answer too; those are counted as answers
                if m.type == "error" and not m.text.startswith("Failed to load resource"):
                    errors.append(f"{width}: {m.text}")

            page.on("pageerror", lambda e: errors.append(f"{width}: {e}"))
            page.on("console", said)
            page.on("response", answered)
            walk(page, url, out, width, Path(scratch))
            check(
                refused == [("PUT", "/api/rules", 400)],
                f"{width}: the one refusal is the wrong value",
                refused,
            )
            page.close()
        finally:
            server.terminate()
            server.wait(10)


def main() -> None:
    asked = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    asked.add_argument("--python", default=sys.executable, help="the Python that runs the explorer")
    asked.add_argument("--out", type=Path, required=True)
    args = asked.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in HEIGHTS:
            walk_at(browser, args.python, args.out, width, errors)
        browser.close()
    check(not errors, "no console errors", errors)
    print(f"{len(failures)} failed; shots in {args.out}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
