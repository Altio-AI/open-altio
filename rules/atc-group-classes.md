---
rule: atc-group-classes
line: A drug named only as a group, such as insulin or iron, gets WHO's class for the whole group when nothing more exact gives one, marked as a group class.
values:
  mapping: mappings/faers/atc/groups.csv
enforced_in:
  - src/open_altio/faers/atc/table.py
  - src/open_altio/faers/atc/layer.py
  - tests/faers/atc/test_table.py
  - tests/faers/atc/test_layer.py
---
# Group names get the group's class

Some reports name a drug only as a group, such as insulin or iron, and WHO codes only each product. When nothing else gives such a drug record a class, it gets WHO's class for the whole group, marked as a group class.

The substance dictionary writes some products only as a group: Lantus, Humalog and plain "insulin" all become `insulin`, and ferrous sulfate becomes `iron`. WHO codes no group word, only each product. A drug record whose substance is a group word, and which neither its substance nor FDA's own words on it could code (rule atc-index), gets the one WHO class the reviewed list in `mapping` gives that word: `insulin` is A10A, insulins and analogues.

Each row of the list is a substance as the dictionary writes it (a group word, or a combination's ingredients joined with `;`), one WHO class code of level 2, 3 or 4, never level 1, which names only a body system, and the reason the class fits every product the word stands for. A word with no row gets no class.

The record's `atc_chosen_by_T` is `group_class` and its `atc_level_T` the class's level, so a group class is never shown as one drug's code. The class is certain but coarse: it says what kind of drug the reporter named, not which one.

**Why:** the dictionary's group words are most of the drug records without a class, insulin alone more than 900,000 of them. FDA's own words name the exact product for many of them and come first; for the rest, WHO's class one level up is what the report does say. A row is added only once the cases it codes have been counted on the release and checked to fit the class (`notebooks/faers/09_drug_classes`).
