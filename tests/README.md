# Tests

The suite mirrors `src/open_altio/`:

- `faers/`: building a release from FDA's quarterly files, one module for each module it tests: `test_load.py` (FDA's files read verbatim), `test_derive.py` and `test_eras.py` (the derived steps), `test_duplicates.py`, `test_release.py` (the release folder), `test_user_rules.py` (a build under a person's own rules), `test_explorer_db.py`, `test_meddra_licensed.py`, `test_build.py`, `test_fda.py`, `test_formats.py`; `drugnames/` (the drug-name step), `insights/` (`methods.json` and the insight cards), `test_notebooks.py` (the committed notebooks, and running them over a real release) and `test_parity.py` (a full build against counts made apart from this code).
- `explorer/`: the explorer run on its own, as one person runs it on their own machine (LocalAccess, no sign-in), one module for each module it tests: `test_filters.py` (each filter, and the product, reactions and drugs a page adds), `test_explore.py` (counts, charts, the case list, one case), `test_search.py`, `test_meddra.py`, `test_live_release.py` (release.py: where the live release is), `test_sql.py`, `test_export.py`, `test_downloads.py`, `test_api.py`, `test_access.py` (the access hook a host plugs in), `test_pages.py`, `test_app.py` and `test_page.py` (the page in a browser: addresses, clicks, keys, the side panel and a host's page modules, in Playwright's headless Chromium, skipped where it is not installed), `test_rules_api.py` and `test_rebuild.py` (the rules page's choices and the rebuild with them), `test_outbox.py` and `test_outbox_browser.py` (Improve this on someone's own machine: the outbox, and the page sending to a fake of Altio's service in the browser). `explorer/conftest.py` lists its fixtures.
- `rulebook/`: reading rule files, the catalogue of data rules, and a person's own rules (`rules.toml`).
- `cli/`: the command line, one module for each command module: `test_data.py` (demo, fetch and build, against FDA's server faked on 127.0.0.1 by `open_altio.testing.fdaserver`), `test_serve.py`, `test_doctor.py`, `test_report.py` (the bug form's own fields), and `test_cli.py` (tasks, help, refusals and crashes).
- `labelreview/`: the label review: the coding question, batches, gates, the agent hand-over and its retries with a fake agent, terms checked against the fake MedDRA, decisions, the blind redo, freezing, the rule check and the review page.
- At the top: the rules folder, where files live (`test_paths.py`), memory facts (`test_machine.py`), Windows by simulation (`test_windows.py`: every module imports without the Unix-only modules; that no path is typed with a separator is a code gate in `scripts/check.py`), and that the open package stands alone (`test_open_package_alone.py`: no module imports the hosted service, and the package installs as a wheel and runs without it).

Run from the repository root:

```sh
uv run pytest -q              # fast suite, a few minutes
uv run pytest -q -m slow      # over the real FAERS quarters, and a fresh install
```

The browser tests need Playwright's headless shell (`uv run playwright install --only-shell chromium`). Without it they skip, unless `OPEN_ALTIO_REQUIRE_BROWSER` is set, as CI sets it: then they fail, so a green suite has drawn every page.

- How the pages look is checked by screenshots, not by tests that read the CSS: `scripts/screens.py` shoots every screen before and after a change and compares them pixel by pixel.
- One seam: a fake FDA release built once per session (`open_altio.testing.fakefda`), with its fixtures in `open_altio.testing.fixtures` (`release`, `rel`, `licensed_release`, ...), which `conftest.py` imports. What a test expects is read from the release's own files through `rel`, so the code is checked against the release and not against itself.
- Every limit a test uses is read from `rules/` with `rulebook.value(...)`, never typed in; `test_rules.py` fails if a test of a rule types one of its values. A test that needs another limit runs under `open_altio.testing.rules.rules_with`; a build with other data rules takes `user_rules=UserRules(...)`, as a person's `rules.toml` gives it.
- A test names what it proves in its name and docstring, and tests both what the code does and what it refuses.

Browser walks (`walks/`) click through a page in headless Chrome at three widths; `walks/README.md`
says how to run them.

## The hosted service

`service/` is the hosted service, with a suite of its own in `service/tests/`: sign-in, the people Altio approves, staff and Administration, the usage log, the download store, emails and the service's page modules. It builds the explorer with its own access hook, so what the explorer does with the data is tested here, not there. Install both packages into one environment and run it from `service/`:

```sh
uv pip install -e service
cd service && uv run --project .. pytest -q
```
