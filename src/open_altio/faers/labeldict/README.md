# The label dictionary

Codes each FDA label of a release into MedDRA once, by fixed rules, then says for each drug, route group and reaction whether the reaction is on the label. The rules are the home of every method: `rules/label-dictionary.md`, `label-negation.md`, `label-population.md`, `label-table-rows.md`, `label-treated-disease.md`, `label-umbrella.md`, `label-not-a-medical-event.md`, `label-procedure.md` and `label-flags.md`.

```sh
python -m open_altio.faers meddra --release releases/2026Q2 --meddra ~/MedDRA_29_1_English   # or build with --meddra
python -m open_altio.faers labels --release releases/2026Q2 --groups FILE [--codings FILE] [--ranks FILE] [--ime FILE]
```

```python
from open_altio.faers.labeldict import build_label_flags, build_label_terms

build_label_terms("releases/2026Q2")  # licensed outputs
build_release_flags("releases/2026Q2")  # public flags, from the release's drug records
build_label_flags("releases/2026Q2", [("1234", "by_mouth", "Nausea")])  # or from given pairs
```

## What it reads and writes

| | Where | Who sees it |
|---|---|---|
| `labels_T`, `label_candidates_T`, `label_sections_T` | the public release, from the labels step | everyone |
| current LLTs, PTs, body-system names, primary paths, `reac_meddra_T` | `licensed/meddra/<version>/` | staff |
| `label_terms_T`: one row per term, label section, sentence and verdict | `licensed/meddra/<version>/` | staff |
| `label_uncertain.jsonl`: one item per thing the rules cannot settle | `licensed/meddra/<version>/` | staff |
| `label_codings_frozen.jsonl`: reviewed codings of uncertain items, if any, written by the label review (`src/open_altio/labelreview/`) | `licensed/meddra/<version>/`, kept when the version is rebuilt, with the review's own files | staff |
| `label_groups.json`: the MedDRA groups `not_a_medical_event` and `procedure` read, and the catch-all groups that never make a pair related; written by the step from `--groups` after checking it (`groups.py`, rule label-groups) | `licensed/meddra/<version>/`, kept when the version is rebuilt | staff |
| EMA's Important Medical Events file for the version | a folder you name, like MedDRA's files (`build_label_flags(ime=...)`) | you |
| `label_flags_T` | `parquet/`, listed in `manifest.json` | everyone |

The coded rows and items are MedDRA content (`rules/meddra-licensed-tier.md`): which term a phrase codes to. They are written beside the MedDRA version they were coded with and listed in the licensed manifest (`tables.label_terms_T`, `label_uncertain`), never in `parquet/` or `manifest.json`. Run the step again after `meddra` rebuilds a version. MedDRA's group names are MedDRA content too, so the groups the set-aside outcomes read, and the catch-all groups related never comes from, are named only in `label_groups.json` (`{"not_a_medical_event": [...], "procedure": [...], "catch_all": [...]}`, the keys the rules' `groups_key` and `catch_all_key` give); `build_label_flags` refuses a version without it.

Every table column ends in `_T` (`rules/transformed-suffix-T.md`; the label's set ID is `setid_T`), and the step refuses to write one that does not. `label_terms_T` columns: `setid_T`, `section_T`, `pt_code_T`, `pt_name_T`, `llt_code_T`, `matched_text_T`, `sentence_T`, `kept_T` (true, false, or empty when uncertain), `rule_T` (the rule file that decided), `decided_by_T` (`rule`, `reviewer`; empty when uncertain), `item_id_T` (the uncertain item, if any).

`label_uncertain.jsonl` fields (a file, not a table, so plain names): `item_id` (a hash of label, section, sentence, candidate and reason, so it stays the same while the label says the same thing), `set_id`, `rxcui` and `drug` (";" between several), `label_date`, `rank` (the highest rank given for the label's drug and the candidate term, from `--ranks`, a Parquet of `rxcui`, `pt`, `rank` such as the pair's EB05; empty when none is known), `section`, `sentence`, `candidate_pt`, `candidate_pt_code`, `matched_text`, `why_uncertain`. A table row naming something no term matches has no candidate.

A frozen coding is one JSON object a line: `item_id`, `set_id`, `section`, `sentence`, `pts` (the PTs the phrase states, as codes or names; empty when it states none), `none_reason`, `agent`, `instructions_version`, `reviewed_at`. A coding with PTs keeps them on the label from that sentence (`decided_by` reviewer); an empty one keeps every term of the sentence off, rule hits included. Either way the item leaves the uncertain list. Builds read these files and never call a model.

`label_flags_T` columns: `rxcui_T`, `route_families_T` (the record's candidate route families, sorted and joined with ";": one when the form is certain, empty when nothing is known), `pt_T` (the reaction text as FDA published it), `outcome_T`, `expectedness_T` (`expected`, `unexpected` or `set_aside`), `section_T`, `setid_T`, `label_date_T`, `decided_by_T`, `family_outcomes_T` (each family's outcome, when more than one label was read), `judged_on_T` (the family label or labels that decided). `Comparison` in `flags.py` takes (rxcui, route families, reaction text) triples: only the candidates' labels are read when each has one, otherwise every family's label, and `resolve()` gives one outcome or `forms_differ` (rule label-flags). `join.py` reads the triples from the release's drug records by the record tables' contracts: suspect records (PS and SS) of `drug_latest_T` as distinct keys, trial products left out (`drug_substance_T`), the RxNorm code (`drug_rxnorm_T`) and route families (`drug_route_T`) of each, with every reaction of its case, and again by the own code of each ingredient the record is counted under (`ingredient_rxnorm_T`), a triple met both ways read once. `build_release_flags` writes the flags in batches and the manifest's `label_flags` entry: the suspect records and cases by how far each got (trial product, no RxNorm code, no label, a label), and what a missing `drug_route_T` or `ingredient_rxnorm_T` meant. Without `drug_rxnorm_T` or `drug_substance_T` it writes no flags and says why.

## Files

| File | Job |
|---|---|
| `text.py` | Sentences and words: spelling, accents, hyphens |
| `terms.py` | Current LLT names as a tree of words, longest match first; body-system headings |
| `scope.py` | The sentence rules: negation, populations, boilerplate, everyday words |
| `tables.py` | Table rows: header, comparator columns, values |
| `coding.py` | One label's sections in, coded rows and uncertain items out |
| `flags.py` | The comparison, plain functions |
| `join.py` | The pairs of a release's drug records, and how far each record got |
| `codings.py` | Reviewed codings of uncertain phrases, frozen as data |
| `ime.py` | EMA's Important Medical Events list, read from its workbook |
| `groups.py` | The groups file a person makes from their own MedDRA release, checked and written beside the version |
| `release_io.py` | Reading the release and its licensed part; column names |
| `flagbuild.py` | Writing the public flags |
| `build.py` | Coding the labels into the licensed part |
