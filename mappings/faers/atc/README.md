# Drug classes: WHO's ATC codes by substance

Source: WHO Collaborating Centre for Drug Statistics Methodology, ATC classification index with DDDs, 2026. Oslo, Norway, 2025. ATC codes and names are WHO's; use of all or part of them requires reference to the WHO Collaborating Centre for Drug Statistics Methodology. This table is built from the index Altio bought; the index itself is not in this repository.

| File | What it holds |
|---|---|
| `classes.csv` | Our drug-to-class table, built from WHO's 2026 index. The release reads it (rule `atc-index`). |
| `bridges.csv` | The reviewed bridges between WHO's words and the substance dictionary's (rule `atc-spelling-bridges`). |
| `groups.csv` | The reviewed classes of the dictionary's group words (rule `atc-group-classes`). |

## classes.csv

One row per substance and WHO code, and one row per class above those codes.

| Column | What |
|---|---|
| `ingredient` | The substance as a drug record names it: one ingredient in lower case as the DiAna dictionary writes it (`levothyroxine`), or a combination's ingredients sorted and joined with `;` (`sacubitril;valsartan`), or a spelling FDA writes in its own fields (`tozinameran`). Empty on a class row. |
| `atc_code` | WHO's ATC code. A substance has a 7-character code; a class row has a code of 1, 3, 4 or 5 characters, and so does a combination WHO codes only by its class (`calcium;vitamin d, unspecified`, A12AX). |
| `who_name` | WHO's name for the code, exactly as WHO writes it. |
| `level` | The ATC level, 1 to 5. |
| `index_year` | The year of WHO's index the row comes from. |

A substance with two uses has two rows (`timolol`: C07AA06 and S01ED01); how one is chosen for each drug record is rule `atc-class-choice`. A substance joins WHO's own name for it, in lower case, and every spelling a bridge gives that name, so `ciclosporin` and `cyclosporine` both find L04AD01 and S01XA18. A combination joins WHO's combination code through its whole set of ingredients: `valsartan and sacubitril` (C09DX04) is the row `sacubitril;valsartan`. A combination WHO names only by a class that has no bridge, or as "combinations" (`paracetamol, combinations excl. psycholeptics`), names no ingredient set and has no row.

## bridges.csv

| Column | What |
|---|---|
| `who_name` | A word as WHO writes it, in lower case: a substance's name, or a part of a combination's name. |
| `substance` | A substance as the dictionary writes it, which the word also stands for. |
| `evidence` | Why the two are the same. |

A bridge adds a spelling; WHO's own word keeps joining too. A class word in a combination name (`decarboxylase inhibitor`) has one row per substance it stands for in products reported to FAERS (`carbidopa`, `benserazide`). `substance` may be a set of ingredients joined with `;`. A row on WHO's whole name for a combination (`buprenorphine, combinations`) joins that code to the substance or set it names; a row on a class's name joins the class to a set only (`calcium, combinations with vitamin d and/or other drugs` for `calcium;vitamin d, unspecified`).

## groups.csv

| Column | What |
|---|---|
| `substance` | A group word as the dictionary writes it (`insulin`), or a combination's ingredients joined with `;`. Listed once. |
| `atc_code` | The one WHO class it gets: a code of level 2, 3 or 4 (3, 4 or 5 characters). |
| `reason` | Why the class fits every product the word stands for. |

A record gets its group word's class only when neither its substance nor FDA's own words on it found a code. `python -m open_altio.faers atc-table` writes the classes this list names into `classes.csv`, so add a row before building the table.

## Refreshing for a new index year

Once a year, with WHO's new index in a folder of its own:

```sh
OPEN_ALTIO_WHO_DIR=<folder> python -m open_altio.faers atc-table
```

It refuses a file whose name gives another year than rule `atc-index`'s `index_year`, so change the year there first. It prints what it wrote, including the combination codes left out, and the new table is reviewed as any change to this folder is: `notebooks/faers/09_drug_classes` measures what it codes.
