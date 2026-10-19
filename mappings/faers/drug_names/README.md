# Our corrections beside the DiAna dictionary

For anyone checking why a drug record has the ingredients it has.

Drug names are read to their ingredients through the open DiAna dictionary (`rules/drug-names.md`). DiAna's file is never copied here or edited: the build reads it by its checksum. These two files are our reviewed corrections to its answers. Each is one line with its reason and its evidence, and every record a correction changes says so (`substance_source_T` is `correction`). FDA's drug names are never changed. The list is also what we send to DiAna's authors; once DiAna fixes one, the release's manifest lists the correction as unused (`drug_names.unused_corrections`) and the line is dropped.

## names.csv

An ingredient DiAna writes two ways, or whose spaces its file mis-encodes, takes one name wherever it appears, alone or as part of a combination.

| Column | What |
|---|---|
| `diana_name` | The ingredient as DiAna's file writes it |
| `name` | The one name we give it: DiAna's own spelling elsewhere, the international name (INN) where DiAna writes both |
| `reason` | Why the two are one ingredient |
| `evidence` | The drug records each spelling carries on the 2026Q2 release |

Seven ingredients are written two ways (`cyclosporine` and `ciclosporin`, `ostilodrostat` and `osilodrostat`, ...), which split one ingredient's count in two. Two radiopharmaceuticals, in four dictionary entries, hold a non-breaking space written twice over as UTF-8 (`technetium` + `Â` + a non-breaking space + `tc` ...); DiAna's other file, `drugnames_standardized.csv`, has their plain names.

## corrections.csv

DiAna's whole answer for a family of spellings is replaced.

| Column | What |
|---|---|
| `diana_substance` | DiAna's answer the correction replaces, as the step writes it: its trial mark off, `names.csv` applied, sorted |
| `spelling` | A regular expression a spelling must contain (DiAna's key: lower case, spaces made one). Empty: every spelling DiAna gives that answer |
| `substance` | Ours, written the same way |
| `reason` | What the product is, and why DiAna's answer is not it |
| `evidence` | Spellings and drug records on the 2026Q2 release, and how often FDA's own `prod_ai` agrees with ours |

A correction changes only the spellings whose DiAna answer is `diana_substance`, so a spelling DiAna already answers differently is never touched, and a spelling DiAna leaves without an ingredient gets none from here. Two corrections that name one spelling stop the build.

## How they were checked

Each correction was read on the 2026Q2 release: the spellings it names, listed one by one, and FDA's own `prod_ai` on the same drug records wherever FDA filled it (from 2014Q3). A drug record is one drug of one report; FDA writes some on one row per dose, and they count once. Where `prod_ai` is empty (Cartia, Fleet Phospho-soda, which left the market in 2008) the reason says what the product is. Cartia is the one family with two products under one name: plain Cartia is diltiazem in the US (Cartia XT) and aspirin in Australia and Israel, and 451 of its 622 drug records come from US reports; it follows the US product, as DiAna does for brands that differ between countries. The 64 combinations DiAna writes out of order need no line: the step sorts every combination.

Left as DiAna has them, on purpose: every insulin is `insulin` and both tenofovir prodrugs are `tenofovir`; splitting them for counting is its own change.

## Changing it

A new line, or a change to one, is a reviewed change with its evidence, measured on a release in `notebooks/faers/05_drug_names`. Proposals not yet reviewed go in `proposals/`, which the build never reads.
