# Browser walks

Walks prove in a real browser what the suite cannot: the page drawn, clicked and changed at the widths
people use. They run Playwright's headless shell (`.venv/bin/python -m playwright install --only-shell
chromium`, once) against an explorer each walk starts for itself.

```sh
.venv/bin/python tests/walks/rules_page.py --out <folder>
```

- `rules_page.py`: the rules page on a person's own copy at 390, 1024 and 1440 px. A row opens in
  place, a rule is switched off and a value changed (a wrong value is refused in plain words), the
  rebuild shows its progress and the explorer opens on the new release, then "Your rules" shows on
  the rules page, All cases and Home, and Download your rules gives the file. Nothing moves when a
  row opens or a switch turns, and no page scrolls sideways. Shots of each state go to `--out`.
- `rules_server.py`: the explorer the walk starts for each width, over a fresh fake release told
  where its fake FDA files are, with each rebuild step held a moment so the progress shows.

Each prints one line per check and exits 1 if any fails.
