---
rule: label-refresh
values:
  checked_at_utc: "02:15"
  catch_up_days: 31
enforced_in:
  - src/open_altio/faers/labels/refresh.py
  - src/open_altio/explorer/labels.py
  - tests/faers/test_labels_refresh.py
  - tests/explorer/test_labels_api.py
  - tests/explorer/test_labels_page.py
---
# Labels kept current between releases

A release reads FDA's labels from DailyMed's full release when it is built (rules label-source, label-choice and label-sections), and labels change every day. Between releases the release's labels are brought up to date from DailyMed's daily update files, without building FAERS again:

```sh
python -m open_altio.faers labels-refresh --release releases/2026Q2 --labels ~/faers-labels [--ime FILE]
```

A host runs it once a day at `checked_at_utc` (UTC), after DailyMed's file of the day before is out; anyone can run it on their own copy at any time.

- **Which days.** The release records the DailyMed day its labels are as of (`labels.as_of` in `manifest.json`): at the build, the newest day a label of the full release was published; then the newest daily file applied. The refresh reads every day's file from that day up to yesterday that it has not applied yet (`labels.daily_files`), so a day the refresh missed is caught up the next time. The day the labels are as of is read again until its own file is applied, since a full release can be cut before all of that day's changes reach it. A release more than `catch_up_days` days behind is refused: fetch the full release again (`labels-fetch`), and the next refresh reads every label anew, as it does whenever the labels folder holds another full release than the one the release was read from.
- **Which labels.** Each prescription label a day's file holds is compared by set ID and version with the labels the release uses. DailyMed's mapping file is fetched again with each day's file, so a new set ID finds its RxNorm codes, and a label whose products in the mapping file changed since the release was keyed is chosen again as a changed label is, so a label is placed once DailyMed maps it. DailyMed maps a label's new version some days after it publishes it, and until then the mapping file has no row for its set ID at all: a label the release chose keeps the key it was read with until its rows come back. A label whose codes the mapping file or the current RxNorm does not hold, a new one among them, is keyed by its own ingredients (rule label-own-ingredients), as at the build. The new mapping file replaces the one in the labels folder only once the labels are switched in.
- **Which choices.** Every ingredient or combination a changed, new or withdrawn label belongs to, before the change or after it, is chosen again among all its labels, by rule label-choice; every other keeps the label it had. Only a label newly chosen, or chosen at a new version, is read for its sections; every other keeps its lines.
- **What changed.** Each refresh that applied a file adds one entry to `labels.refreshes`: when it ran, the day the labels are now as of, the files it read, how many prescription labels they changed and withdrew, and for each ingredient (or combination) and route family whose label changed, its old and new set ID and version.
- **The flags.** When a label the flags read changed, the labels step runs again, coding and then flags (rules label-dictionary and label-flags), under the rules the release was built with, with the groups file and the reviewed codings the release keeps, and with EMA's Important Medical Events file where its flags read it. Every table the step reads (the drug records' RxNorm codes and routes, each ingredient's own code in `ingredient_rxnorm_T`) is read where it is in the release, so the flags written are the step's own, a combination's reactions on each ingredient's own label among them. A reviewed coding keeps deciding a sentence the label still says in the same section; a sentence that changed is a new uncertain item, which reads Can't tell (rule explorer-label-words) until it is reviewed.
- **Never half updated.** The new label tables, codings and flags are built beside the release and switched in only when every one is whole. A refresh that fails leaves the release with the labels it had and says why; a switch stopped by a crash is finished at the start of the next refresh.
- **Labels as of.** The screens say which day the labels are as of: on the methods page's first line, in each flag's tip, and in an export's `manifest.json` ("Labels as of 2-Mar-2026"). Each label's link opens the version of the label the flags were read from, and says so, with the time the labels are checked each day, `checked_at_utc`.

**Why:** a flag says whether today's label lists a reaction, and DailyMed changes tens to hundreds of prescription labels on a working day. In the daily file of the day the 2026Q2 full release was cut, none of the 123 prescription labels it changed had a row in that day's mapping file, so a changed label cannot wait for its mapping to keep its place. Reading only the day's changes keeps the flags true to today's label without rebuilding FAERS or reading 50,000 labels again; choosing again only where a label changed keeps every other flag as it was; and building beside the release means a reader never sees new labels with old flags.
