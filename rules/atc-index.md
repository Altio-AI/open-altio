---
rule: atc-index
line: Each drug gets its class in WHO's drug classification (ATC), such as antithrombotic agents, all from one year's edition, so a class means the same in 2004 as in 2026.
values:
  source: WHO ATC classification index with DDDs
  index_year: "2026"  # text: a year, not a limit
  citation: WHO Collaborating Centre for Drug Statistics Methodology, ATC classification index with DDDs, 2026. Oslo, Norway, 2025.
  table: mappings/faers/atc/classes.csv
  table_prefix: atc_
  counted_in: cases
enforced_in:
  - src/open_altio/faers/atc/table.py
  - src/open_altio/faers/atc/layer.py
  - tests/faers/atc/test_table.py
  - tests/faers/atc/test_layer.py
---
# WHO drug classes, from one year

Each drug record gets its class in WHO's Anatomical Therapeutic Chemical (ATC) system, with WHO's own name for it, so drugs can be counted together by what they treat. Every quarter is read with the same year's index, so a class means the same in 2004 as in 2026. The classes sit in tables of their own: switched off, the release is built without them and nothing else in it changes.

Each drug record's class is a code of WHO's Anatomical Therapeutic Chemical (ATC) classification, with WHO's own name for it, read from the index of `index_year` for every quarter of every release. ATC codes are revised every year; one index for all quarters means a class means the same thing in 2004 and in 2026, and a count by class over time compares like with like. The index year is stored on every class row of the release and in its manifest.

The release reads our drug-to-class table, `table`, not WHO's spreadsheet. The table is built once a year from the index WHO sells, which is never kept in the repository or a release: `python -m open_altio.faers atc-table` reads it from the folder `OPEN_ALTIO_WHO_DIR` names (`src/open_altio/faers/atc/table.py`). A substance joins WHO's name for it and its reviewed spellings (rule atc-spelling-bridges); a combination joins WHO's combination code through its whole set of ingredients. Where WHO names a combination only by a class, or as "combinations", the code names no ingredient set and is left out, unless a bridge names the set. How one class is chosen for each drug record is rule atc-class-choice.

**Where a record's classes come from, in this order.** Each drug record is looked up by the first of these that finds a code, and `atc_matched_on_T` says which:

1. **The substance dictionary's substance** (`drug_substance_T`): one ingredient (`substance`), the whole set of a combination's ingredients (`ingredient_set`), or, for a combination with no code of its own, each of its ingredients (`each_ingredient`). The table keys a substance and its reviewed spellings exactly as the RxNorm step keys the record's ingredient (rule rxnorm-ingredients), so the two read every record as the same ingredient.
2. **FDA's own words on the record,** when its substance has no code or it has none: FDA's drug name (`drug_name`), else FDA's active ingredient (`active_ingredient`), each as a whole name, in lower case with spaces tidied (`drugname_norm_T`, `prod_ai_norm_T`) and read exactly as the RxNorm step reads them, against the table's names, which are WHO's names and the bridged spellings. FDA separates a combination's active ingredients with `\`; such a value is read as a set of ingredients only when every part is a name the table holds: the set's own code (`active_ingredient_set`), else each part's codes (`each_active_ingredient`). A name is never matched in part: a kit whose active ingredients include an alcohol swab is not coded as the swab.
3. **A group class,** when neither found a code and the substance is a group word with a reviewed class (rule atc-group-classes).

A record none of them codes has no class row.

The classes are a layer of their own. They live in tables whose names start with `table_prefix`, listed in the manifest under `classes` with the index year and WHO's citation, `citation`, and the core release is complete without them. A release built without the table, without the substances the classes join on, or with this rule switched off in a person's rules, says so in its manifest and carries no class tables. This rule is the one switch of the drug classes' step in `rules/steps.yaml`: off, none of the four drug class rules acts, and none can be switched off alone.

Counts of classes are of `counted_in`, never of drug rows: a case naming one drug on three rows, or two drugs of one class, counts once for that class.

**Why:** WHO's codes and names are the standard drug classes of pharmacovigilance. A fixed table keyed by substance, as DiAna publishes its own on OSF, gives everyone who builds a release the same classes, and lets anyone read and check every join. The substance comes first because it is the cleaned reading of the record; FDA's words come next because they often name the exact product where the substance names only a group (FDA's active ingredient for Lantus reads "insulin glargine"), and a group class comes last because it is the coarsest (`notebooks/faers/09_drug_classes`).
