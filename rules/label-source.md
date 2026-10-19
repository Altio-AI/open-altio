---
rule: label-source
line: Labels come from DailyMed, the US library of FDA drug labels, in its monthly release; only human prescription labels are read, never over-the-counter or animal ones.
values:
  labels_from: DailyMed's monthly full release, human prescription labels only
  release_files_url: https://dailymed-data.nlm.nih.gov/public-release-files/
  release_file_pattern: dm_spl_release_human_rx_part{n}.zip
  release_file_glob: dm_spl_release_human_rx_part*.zip
  mapping_file: rxnorm_mappings.zip
  rxnorm_url: https://download.nlm.nih.gov/rxnorm/RxNorm_full_prescribe_current.zip
  rxnorm_file_glob: RxNorm_full_prescribe_*.zip
  seconds_between_requests: 2
  user_agent: open-altio labels fetch (https://github.com/Altio-AI/open-altio)
  daily_file_pattern: "dm_spl_daily_update_{day:%m%d%Y}.zip"
  daily_label_folder: prescription
  daily_deleted_list: files_deleted.txt
enforced_in:
  - src/open_altio/faers/labels/fetch.py
  - src/open_altio/faers/labels/folder.py
  - src/open_altio/faers/labels/daily.py
  - tests/faers/test_labels.py
  - tests/faers/test_labels_refresh.py
---
# Where drug labels come from

The labels step reads FDA drug labels as DailyMed publishes them, in Structured Product Labeling (SPL) XML, and the files that link each label to RxNorm. Only human prescription labels are read: DailyMed ships them as their own set of zips (`release_file_pattern`), numbered from 1, so OTC, animal and other labels never enter.

Three things are downloaded, into a folder of their own outside the repository, and none is committed:

- **The labels.** Every part of the human prescription full release, from `release_files_url`. The parts are fetched from 1 upward until DailyMed answers that the next one does not exist, because the number of parts changes from month to month.
- **Labels to RxNorm.** DailyMed's `mapping_file`: for each label (set ID) and version, the RxNorm codes of the products it covers. These are product codes (a strength and a form, such as "apixaban 5 MG Oral Tablet"), not ingredient codes.
- **RxNorm's current prescribable content,** from `rxnorm_url`. It holds RxNorm's own links from a product to its ingredients, so each label can be keyed by ingredient. NLM publishes it with no licence or sign-in.

The fetch asks for one file at a time and waits `seconds_between_requests` between requests, with `user_agent` naming the project. A file is written beside its final name and renamed only once it is whole and opens as a zip, so a broken download never looks like a label file. A file already downloaded at full size is not fetched again; a partial one carries on from where it stopped.

## The daily update files

Between full releases DailyMed publishes one file a day of every label it changed that day, `daily_file_pattern` at `release_files_url`, named by the day as month, day and year (`dm_spl_daily_update_03022026.zip` holds the changes of 2 March 2026). One file holds every kind of label, each kind in a folder of its own, and each label is a zip named by the day and its set ID, as in the full release. Only the folder `daily_label_folder` is read: human prescription labels, the folder the full release's labels are in. The file's list `daily_deleted_list` names the label files the day takes out of the full release; a prescription set ID it takes out and does not add back in the same folder (a label withdrawn, or moved to over the counter) leaves the labels. A weekend or a holiday has no file, and the file of a day comes out after the day ends, usually in the first hours of the next day in UTC. Rule label-refresh says how these files keep a release's labels current. They are fetched as the full release is, one file at a time, `seconds_between_requests` apart, with `user_agent`, into the labels folder, and none is committed.

**Why the full release and not the web services:** choosing one label per ingredient means looking at every candidate label's marketing category and date, and those are inside each label. DailyMed's web services would need one call per candidate label, tens of thousands of calls, each of which can fail. The full release is a handful of large files, refreshed monthly, that hold every current label at once. The release holds only each label's current version, which is the label the method uses: today's label, not the label at the time of a report.

One RxNorm loader: the product-to-ingredient reading in `src/open_altio/faers/labels/rxnorm.py` moves into the shared RxNorm module (`open_altio.faers.rxnorm.rrf`) once that module is in this tree, which then also needs RxNorm's product term types (SCD, SBD, GPCK, BPCK) and their links (consists_of, has_ingredient, contains).

**Source:** DailyMed, the National Library of Medicine's site for the labels FDA receives (dailymed.nlm.nih.gov, "SPL resources: Download All Drug Labels", which lists the full release, the monthly, weekly and daily updates, and "mapping files" pages). RxNorm current prescribable content (nlm.nih.gov/research/umls/rxnorm, "RxNorm files").
