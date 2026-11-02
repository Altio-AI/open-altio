# Scripts

Small tools run by hand. Anything the release build or the service needs belongs in `src/`, not here.

- `check.py`: the checks every change passes. Alone, the text and code gates; with `--all`, also ruff, mypy, the docs site and the fast suite. See `AGENTS.md`.
- `run_nb.py`: run notebooks headless, or strip their outputs. See `notebooks/README.md`.
- `compare_explorer_db.py`: check that two `explorer.duckdb` files hold the same tables, rows and values, in the same storage order (row counts, order-independent MD5 sums per column and per row, and an order checksum of each sort key). Run it after any change to how the explorer database is built.
- `contract_snapshot.py`: write `tests/contract/snapshots/api.json`, the keys each published question answers on the invented release, under `open_altio.CONTRACT_VERSION`. Run it when a published answer gains a key or a route is published; it refuses to drop a name unless the contract's major version rises. See `docs/reference/contract.md`.
- `labels.sh OWNER/REPO`: create or update the repository's labels from `.github/labels.yml`, with the GitHub CLI.
- `screens.py`: screenshots of every screen the explorer draws, at three widths in light and dark, on the fake release with a fixed clock; and a pixel diff of two sets with a report. Run it before and after a change to the page's code or styles: the look must not move. Needs Playwright's headless shell (`uv run playwright install --only-shell chromium`).
