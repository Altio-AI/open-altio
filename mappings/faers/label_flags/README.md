# Drugs named two ways by the label flags

For anyone checking why a record keeps its RxNorm code's label although the code's name is not the ingredient it is counted under.

The label flags read a record on its code's label only when the code names the drug the record is counted under (`rules/label-flags.md`). Most names that differ are paired already for RxNorm (`mappings/faers/rxnorm/name_pairs.csv`). `same_drug.csv` holds the few more where both names are RxNorm's own, for one drug: a prodrug and the drug it becomes.

| Column | What |
|---|---|
| `counted_name` | The ingredient as the drug names step counts it, in lower case |
| `rxnorm_name` | RxNorm's name of the code that is the same drug, in lower case |
| `evidence` | Why the two are one drug |

A row only lets the flags read a record on its code's label; it never changes a code or what a record is counted under. A new row is a reviewed change with its evidence.
