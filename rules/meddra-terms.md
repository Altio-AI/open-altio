---
rule: meddra-terms
line: Reactions are terms of MedDRA, the medical dictionary for drug safety, which renames terms over time; with MedDRA in the release, each counts under today's term unless the host shows it as FDA wrote it, so Seizure also finds Convulsion. The link from FDA's text to it is shown to MedDRA subscribers.
always_on: true
why_locked: A release counts in one MedDRA version, and the version reads every term FDA wrote.
values:
  apostrophe_as_caret: [drug_rec_act]
  stops_when_unmapped: [pt]
enforced_in:
  - src/open_altio/faers/meddra/terms.py
  - src/open_altio/faers/meddra/licensed.py
  - src/open_altio/faers/release.py
  - src/open_altio/explorer/reactions.py
  - src/open_altio/explorer/meddra.py
  - src/open_altio/explorer/explore.py
  - tests/explorer/test_soc.py
  - tests/faers/test_meddra_terms.py
  - tests/faers/test_meddra_licensed.py
  - tests/explorer/test_reactions.py
  - tests/explorer/test_public_reactions.py
---
# Old reaction terms read to today's

Each FAERS quarterly file keeps its MedDRA terms in the version FDA coded it in, so an older report can name a term MedDRA has since demoted or renamed, and a search on today's term misses it. Where a release has MedDRA, every term FDA wrote is read to the preferred term (PT) it belongs to today, so each reaction can be counted under its current PT. FDA's text is not changed.

FAERS holds MedDRA terms in three columns: `pt` (a reaction), `drug_rec_act` (the reaction that came back when the drug was given again, FAERS only) and `indi_pt` (an indication). Each distinct text, compared the way the explorer compares reactions (lower case, runs of spaces made one), is matched to the release's one MedDRA version (`rules/meddra-version.md`) in this order: a PT; else a lower level term, a current one first; else a name MedDRA used for the term before renaming it, from MedDRA's history file (`meddra_history_english.asc`, in the same download). In the columns `apostrophe_as_caret`, FDA writes an apostrophe as `^` (`Crohn^s disease`), and it is read as an apostrophe before matching. One piece of code maps all three columns. Every link it makes is MedDRA's own: the term file names each term's PT, and the history file each old name's term. None is our judgement.

The mapping is MedDRA's licensed content, so it lives in the release's licensed part (`licensed/meddra/<version>/`: `reac_meddra_T`, `drug_rec_act_meddra_T` and `indi_meddra_T`, one row per distinct text), never in the public tables, the downloads or the explorer database. The public release carries FDA's text only.

A text in the columns `stops_when_unmapped` that matches nothing stops the build. FAERS's reaction field holds only MedDRA terms, so a reaction that matches nothing means the MedDRA file is older than the data; the message says so, and the newest version is needed. In the other columns, the build reports how many texts and rows match nothing and leaves them as FDA wrote them, with no hand review. The build also reports any quarter whose reactions fit no single MedDRA version.

**What it is for.** Statistics, label flags, charts and the reaction search count each reaction under its current PT, named by PT names, for everyone who views the release, so a search for Seizure also finds the cases FDA wrote as Convulsion. Indications and the reaction that came back when the drug was given again are read the same way. The case list shows FDA's text as written. The link itself, which current PT a text of FDA's reads to, is MedDRA's content: only a viewer with MedDRA's licensed part (a verified MedDRA subscriber on the hosted service, or a copy run with its own MedDRA files) sees the current PT beside FDA's text in the case list and the case, with the release's MedDRA version, and finds a reaction by any lower level term. The same viewer sees each reaction's primary system organ class (MedDRA's own hierarchy, read from the licensed part): as a grey line under the reaction in the case, and as a column of the case list, the first class in full and the number of others beside it. Nobody else is shown one, in the pages or the API. Downloads and exports carry FDA's text only. A host may instead show a viewer without MedDRA's licensed part the release as one built without MedDRA (the explorer's access hook, `Viewer.todays_names`; on open.altioai.com rule meddra-licensed-tier says when): every reaction by FDA's text, everywhere, with the statistics counted by FDA's text (rule statistics-cases), so Seizure and Convulsion are two reactions for them. A copy run on someone's own machine names reactions by today's PT when it has MedDRA files and by FDA's text when it has none. Indication texts that match no MedDRA name are free text, shown as FDA wrote them.

Two things the mapping cannot do. It cannot undo a split: when MedDRA later makes a narrower PT out of an existing term, the reports coded before stay under the term they were coded in, so search with the SMQ to find them all. 2017Q2, the one quarter coded in MedDRA 20.0, holds 1,545 rows of Drug use disorder where the quarters around it say Drug abuse or Drug dependence; all three are current PTs, and MedDRA's SMQ for drug abuse and dependence holds all three. And it cannot check FDA's own coding, because FDA does not publish the reporter's words.

**Why:** on the 2026Q2 release, 1,502,008 cases (7.3%) carry a reaction term that is not a current PT in MedDRA 29.1, and a search on today's PT misses 1,493,379 of them; Seizure is written as the PT on 112,546 cases and under older terms on 57,730 more. Every reaction text is a MedDRA name: all but 44 are names in 29.1, and those 44 (2,979 rows, 2,957 cases) are older names the history file resolves. 74 indication texts (105 rows) are free text no MedDRA name covers. The evidence is `notebooks/faers/06_meddra_versions`.
