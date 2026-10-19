---
rule: statistics-classes
line: EBGM, PRR, ROR, RRR and IC are worked out again with each drug's WHO class in place of its ingredient, at three levels of the class, so a reaction reported for a whole class can be told from one drug's.
values:
  levels:
    - {level: 2, name: Therapeutic subgroup}
    - {level: 3, name: Pharmacological subgroup}
    - {level: 4, name: Chemical subgroup}
  could_be: false
enforced_in:
  - src/open_altio/faers/statistics/classes.py
  - src/open_altio/explorer/statistics.py
  - tests/faers/statistics/test_statistics_classes.py
  - tests/explorer/test_class_statistics.py
  - tests/explorer/test_public_reactions.py
---
# Statistics for each drug class

The statistics of each ingredient and reaction are worked out again for each WHO class and reaction, at three levels of the class: its therapeutic subgroup (level 2, such as psychoanaleptics), its pharmacological subgroup (level 3, antidepressants) and its chemical subgroup (level 4, selective serotonin reuptake inhibitors). Beside a drug's own numbers, its class's show whether a reaction stands out for the one drug or for every drug of its kind.

**Cases**: the same cases as the ingredient statistics (`statistics-cases`), each counted once: the kept cases that name a suspect ingredient and a reaction. The total N and the cells c and d are counted over them, with each reaction counted the same way (under its current preferred term where the release holds MedDRA), so a class's numbers stand beside its drugs'. They have no second set counted by FDA's text, so anyone shown reactions as FDA wrote them is not given them.

**Class**: a case names a class when one of its drug records in the roles `statistics-cases` counts (primary or secondary suspect) is in the class at that level. A record's class is its one class in `atc_drug_T` (rule `atc-class-choice`), cut to the level's code: sertraline, N06AB06, is N06 at level 2, N06A at level 3 and N06AB at level 4. A record counts at every level its class is certain at, and nowhere else: a record whose class is a full code counts at all three; one known only to a shared class or a group class of level 3 counts at levels 3 and 2, never at 4; a "can't tell" record counts at none. A class it only could be is left out (`could_be` false); set true, a record whose class does not reach a level would also count there under each class its possible codes (`atc_drug_codes_T`) give at that level, so a "can't tell" aspirin would count under both its blood thinner's and its painkiller's class. Two drugs of one class in a case count once for it.

**Each level is counted on its own**: its classes and the reactions of the cases are scored as the ingredients are, with PRR, ROR, RRR and IC from each pair's table of cases, and EBGM under a prior fitted on that level's cells alone, with rule `ebgm`'s settings. The levels are never fitted together, since a class at level 2 holds its classes at level 3.

`atc_statistics_T` holds one row for each class and reaction named together in at least one counted case, with the level (`level_T`), the class's code (`class_T`), the cases naming the class (`class_cases_T`) and every column of `statistics_T` but the ingredient and the time to onset. `atc_statistics_ingredients_T` holds, for each level, each ingredient's classes there and the cases in which a record of the ingredient was counted under the class, so a drug's page can show its class's numbers. Both are tables of the drug classes layer: a release built without the classes has neither, and a viewer the classes are hidden from sees neither. `python -m open_altio.faers class-statistics --release R` adds them to a release already built, as a full build writes them.

**Why:** a reaction that stands out for one ACE inhibitor and for the ACE inhibitors alike is likely the class's; one that stands out for one drug alone points at the drug. Counting on the ingredient statistics' own cases keeps the two sets of numbers on one table of cases, and three levels show how far up the class a reaction is shared. Each level gets its own prior because its cells are not drawn from the same mixture as another level's. A record counts only where its class is certain, so no class's numbers rest on a guess at which use the report meant.
