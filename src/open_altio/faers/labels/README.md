# Labels

FDA drug labels for the release: for each RxNorm ingredient (or combination), the originator's current prescription label per route family, and the safety sections of each as lines of plain text. A later step compares FAERS reactions with these lines.

```sh
python -m open_altio.faers labels-fetch --into ~/faers-labels      # about 18 GB, one file at a time
python -m open_altio.faers build --input ~/faers-zips --out releases --labels ~/faers-labels
```

Without `--labels` the build skips the step and says so (`labels: skipped, no labels folder given`); the manifest's `labels` entry says the same.

Between releases the labels are brought up to date from DailyMed's daily update files, without building FAERS again (rule label-refresh):

```sh
python -m open_altio.faers labels-refresh --release releases/2026Q2 --labels ~/faers-labels [--ime FILE]
```

```
src/open_altio/faers/labels/
  fetch.py     download DailyMed's prescription release, its RxNorm mapping file and RxNorm's
               prescribable release into one folder (rule label-source)
  folder.py    find those files in the folder and read them: labels from the nested zips, the mapping
  spl.py       read one SPL XML: the facts a choice needs, the wanted sections as lines
  rxnorm.py    RxNorm's links from a product code to its ingredients and their MIN
  choose.py    one label per ingredient and route family (rule label-choice)
  lookup.py    an ingredient's label per route family, and whether they differ
  build.py     the step: every label's facts, the choice, then the chosen labels' sections
  daily.py     DailyMed's daily update files: which days are due, fetching them, what each changed
  update.py    the label tables made again where a label changed, choosing again only there
  switch.py    files built beside a release moved into it as one change, or not at all
  refresh.py   labels-refresh: the days' files, the tables, the flags again, then the switch
```

## The tables

Both are written into the release's `parquet/` and listed in `manifest.json` as derived tables. Their names and every column end in `_T`, values copied from DailyMed and RxNorm included, so a label's set ID is `setid_T` (rule transformed-suffix-T); the build refuses a release where one does not.

| Table | One row per | Columns |
|---|---|---|
| `label_candidates_T` | ingredient (or combination) and route family: the label for that family | `rxcui_T` (RxNorm IN or MIN), `ingredient_T` (RxNorm's name), `route_family_T` (a family of rule drug-route's shared route table: by_mouth, under_tongue, injected, inhaled, nasal, rectal, vaginal, transdermal, skin, eye, ear, other; unknown for a label whose routes give none), `setid_T`, `spl_version_T` (integer), `title_T`, `effective_date_T` (date), `application_T` (NDA, BLA, ANDA or other), `routes_T` and `dosage_form_T` (lists of FDA's terms), `chosen_because_T`, `forms_differ_T` (true when two of the ingredient's families' labels have different safety sections), `keyed_by_T` (`mapping_file`, or `label_ingredients` for a label the mapping file misses, keyed by its own active ingredients: rule label-own-ingredients) |
| `label_sections_T` | line of a wanted section of any label above | `setid_T`, `section_T` (boxed_warning, warnings_and_precautions, warnings, precautions, adverse_reactions, contraindications, indications), `loinc_T`, `ordinal_T` (order in the label), `is_table_row_T`, `text_T` (a table row's cells joined by `" \| "`) |

A FAERS drug record gets the label for its ingredient's RxNorm code and its route family. There is no default label: a record whose family is unknown is compared with every family's label, and `forms_differ_T` says whether they can disagree. `lookup.LabelLookup` reads this, and its docstring gives the same in SQL.

The manifest's `labels` entry counts what the step did: label files in the release, distinct labels read (a set the release holds twice is read at its highest version) and unreadable, how each label was keyed (`IN`, `MIN`, `no_code`, `no_min`), what its own ingredients added (`keyed_by_own_ingredients`: labels, ingredients given a label, labels chosen and how many of those are older than `recent_from`), ingredients and combinations with a label, labels whose safety sections hold no words (in the whole release, and among the labels chosen, where no other label of the ingredient has any; with how many of those file sections as unclassified), labels whose sections were read, the lines per section, and the files read (names and sizes, never paths). It also says the DailyMed day the labels are as of (`as_of`, at the build the newest day a label of the full release was published); a refresh moves it on, lists the daily files it applied (`daily_files`) and adds what it changed to `refreshes`. The counts of what the build read stay as the build counted them; the counts of the tables are made again with each refresh.

## Adding one more

- **A section:** one more `LOINC: name` line in `rules/label-sections.md`. The code reads the list from there.
- **A route:** a label's routes are read through the shared route table of rule drug-route (`open_altio.faers.route.label_families`); a route it lacks is placed there by `mappings/faers/route/review/instructions.md`, never in the labels code. The manifest's `labels.routes_not_in_route_table` lists the ones a build met.
- **A step in the choice:** `choose._order` and `choose._STEPS` together, with the rule text in `rules/label-choice.md` and a test in `tests/faers/test_labels.py`.

The downloaded files are never committed; tests use the invented folder in `open_altio.testing.fakelabels`.
