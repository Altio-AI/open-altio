# The `open_altio` package

| Package | What it does |
|---|---|
| `faers/` | FAERS: find and load FDA's quarterly files verbatim, keep the latest version of each case, apply deleted-case lists, flag duplicates, build a release folder. `insights/` turns notebook findings into the methods page's data |
| `explorer/` | A release in the browser: the data API (`/api`) and the page that draws every screen from it (`ui/`). `create_app(release_dir, access=...)` builds it; the access hook says who is viewing and what they may see |
| `cli/` | The `open-altio` command: demo, fetch, build, serve, doctor and report (`docs/reference/cli.md`) |
| `stats/` | Statistics over counts of cases from any source: EBGM, PRR, ROR, RRR and IC, and the screens a pair may meet. The build's statistics step (`faers/statistics/`) counts a release for them |
| `labelreview/` | The label review: any agent codes each label phrase the label rules leave uncertain into MedDRA preferred terms, file in and file out; one reviewer checks on a page on their own machine, gates decide when batches grow, and decided codings are frozen so a build runs no agent. Also the hand check of a random sample of rule-made flags |
| `rulebook/` | Reads rule values from `rules/`, and from any folder a host adds; the only way code reads a policy value |
| `paths.py`, `machine.py` | Where the data folder is on each platform, and memory facts read the same way on Windows |
| `testing/` | The fake FDA files and MedDRA release tests build from, the release reader tests check with, and the rules helpers |

## Direction of imports

```
cli  ──runs──>  explorer
cli  ──builds with──>  faers (build, fda)
explorer  ──reads──>  a release folder (through faers.reader)
faers  ──counts for──>  stats
faers, explorer, stats  ──use──>  rulebook
labelreview  ──uses──>  rulebook; the label step reads its frozen file
nothing here imports a host
```

A host (the hosted service is one) imports `open_altio.explorer`, hands `create_app` its own access hook and adds its own rules folder with `rulebook.add_rules_dir`; `tests/test_open_package_alone.py` checks that nothing here imports it back.
