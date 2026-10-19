# Testing

The fake data the tests build from, in one place, with the helpers tests share. Production code never imports this package. A host's own tests use it too, so a host's fakes for its outside world (mail, clock, object store) live with the host.

| Module | What it is |
|---|---|
| `fakefda.py` | FDA's quarterly files: six small quarters with every layout quirk of the real ones |
| `fakelabels.py` | A labels folder as `labels-fetch` leaves it: invented SPL labels in two release parts, DailyMed's mapping file and the RxNorm rows the labels step reads |
| `fakestats.py` | One quarter of invented reports drawn from EBGM's own model, enough for its prior to fit (`stats_release`) |
| `fakemeddra.py` | An invented MedDRA release in MedDRA's file format, with no MedDRA content |
| `fakewho.py` | An invented WHO ATC index in WHO's spreadsheet layout, and a small class table in ours, with no WHO content |
| `fakediana.py` | An invented DiAna drug dictionary in DiAna's file format, with none of DiAna's content |
| `fakeclasses.py` | An invented drug classes layer on a built release, with no WHO content, and the same release without it (`classes_release`, `bare_release`) |
| `fakelabelflags.py` | Invented label flags for the fake release, with the drug codes, routes and ingredients they are read through and the labels they name |
| `fdaserver.py` | FDA's download server on 127.0.0.1, answering ranges and missing files as FDA's does |
| `fakerxnorm.py` | An invented RxNorm release in NLM's file format, with each way a name finds its code |
| `releasereader.py` | A release folder opened only through its files, as a downstream reader would, with the cases a condition matches as the explorer addresses them |
| `rules.py` | `rules_with`: run code under a copy of every rules folder with some values changed |
| `rulecheck.py` | The checks that a rules folder and the code reading it agree, for any repository's `tests/test_rules.py` |
| `browser.py` | The page in a real browser: an app served on this machine, opened in Playwright's headless Chromium with the clock, time zone and kept choices fixed; and what its tables show: a wide table's first column held as it scrolls, and every cell holding its words, its row's first lines on one line and its grey lines under its value |
| `fixtures.py` | Pytest fixtures over these: the fake release and its licensed MedDRA part, built once per session, the release with and without invented drug classes, a second release of the duplicate rules' own cases, the invented DiAna dictionary, FDA's server faked, and the browser (`chromium`) |
| `fixtures.py` | Pytest fixtures over these: the fake release and its licensed MedDRA part, built once per session, a second release of the duplicate rules' own cases, the release with label flags, the invented DiAna dictionary, FDA's server faked, and the browser (`chromium`) |
| `fakelabeltables.py` | Invented FDA labels as a release's label tables, and invented RxNorm codes and route families for its drug records, for the label dictionary and flags |
| `fakereview.py` | The label review's outside world: invented uncertain label phrases, an agent that codes a batch folder (`answer_items`, and `write_agent` for a tiny agent command line), and a small `label_flags_T` |

The fixtures are taken into a conftest with `from open_altio.testing.fixtures import *`.
