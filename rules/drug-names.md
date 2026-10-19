---
rule: drug-names
line: "HUMIRA and 'Humira 40 mg/0.8 ml pen' both count as adalimumab: every spelling is read to its ingredients through the open DiAna drug dictionary and our reviewed fixes."
values:
  source: DiAna dictionary (Fusaroli et al., University of Bologna), CC BY 4.0
  page: https://osf.io/zqu89/
  download: https://osf.io/download/n2dgz/
  download_timeout_seconds: 60
  published: "2026-03-20"  # text: the date OSF gives the file
  sha256: 549162fd93d981048657aa25290181da7cc0df8b73db14120db4a11b4b32f212
  corrections: mappings/faers/drug_names/corrections.csv
  names: mappings/faers/drug_names/names.csv
enforced_in:
  - src/open_altio/faers/drugnames/dictionary.py
  - src/open_altio/faers/drugnames/substances.py
  - tests/faers/drugnames/test_drugnames_dictionary.py
  - tests/faers/drugnames/test_drugnames_substances.py
  - tests/faers/drugnames/test_drugnames_release.py
  - src/open_altio/faers/build.py
  - src/open_altio/cli/data.py
  - src/open_altio/cli/doctor.py
---
# Drug names read to their ingredients

FDA publishes each drug name as the reporter or company typed it: `HUMIRA`, `Humira 40 mg/0.8 ml pen`, `ADALIMUMAB-AATY`. We read each one to its ingredients through the open DiAna dictionary and our own reviewed corrections, so one medicine is counted together whatever the spelling. FDA's own names are not changed.

`drug_substance_T` gives each drug record, one drug of one report, its ingredients: `substance_T` holds them in lower case, as international names (INN) without their salts, a combination's ingredients sorted and joined with `;` (`sacubitril;valsartan`). `drug_ingredient_T` has one row per drug record and ingredient. FDA's `drugname` and `prod_ai` are never changed. Switched off, the release has neither table.

**The dictionary.** The open DiAna dictionary (`source`), published on OSF (`page`), file dated `published`, from `download`. `open-altio fetch` and `open-altio demo` download it to `reference/DiAna_dictionary.csv` in Open Altio's data folder, or to the file `OPEN_ALTIO_DIANA_DICTIONARY` names, and `open-altio doctor` says whether it is there; `open-altio build` reads it from there and builds without drug ingredients when there is none. `python -m open_altio.faers build --diana FILE` downloads it to that file first when it is not there yet. A download that stalls for `download_timeout_seconds` is stopped. Its SHA-256 must be `sha256`, or the build stops and says so: a new DiAna file is taken by checking our corrections against it and moving `sha256` to it, in one reviewed change. Nothing of DiAna's is kept in the repository. A release built without the file has neither table, and its manifest says why.

**The key.** A drug name meets the dictionary through DiAna's own key (its 2023 cleaning script, lines 314 to 320): lower case; one trailing period removed; runs of spaces made one; leading and trailing punctuation stripped twice, keeping an opening bracket at the start and a closing bracket at the end; no space just inside a bracket. A dictionary entry of `NA` means DiAna saw the name and gave no ingredient.

**Where the name has none.** FDA's `prod_ai` (filled from 2014Q3) is looked up by the same key: whole, else split on FDA's `\`, with every part found. A part that is itself a combination adds all its ingredients, and the set is sorted again.

**What is taken from DiAna's answer.** Its trial mark, `, trial`, is removed from the ingredient, so a study drug counts under its ingredient. Whether DiAna marked the record a trial product (a named study drug, placebo or a blinded drug) is kept in `diana_trial_T`. It is not shown on screen, because the mark fades from 2021 on, when DiAna stopped mapping most new trial spellings. Every combination is sorted, each ingredient once, though 64 of DiAna's are not.

**Our corrections.** DiAna's file is never edited. Our reviewed corrections sit beside it, each one line with its reason and its evidence (`mappings/faers/drug_names/README.md`):

- `names`: an ingredient DiAna writes two ways, or whose spaces its file mis-encodes, takes one name wherever it appears, alone or in a combination (`cyclosporine` is `ciclosporin`, `ostilodrostat` is `osilodrostat`).
- `corrections`: DiAna's answer for a family of spellings is replaced: those whose DiAna answer is `diana_substance` and that contain the `spelling` pattern (a regular expression; empty means every such spelling). Two corrections that name one spelling stop the build. The manifest lists each correction with the dictionary keys it changed, so one DiAna has since fixed shows as unused and is dropped.

DiAna's groupings stay as DiAna has them: every insulin is `insulin`, tenofovir disoproxil and tenofovir alafenamide are `tenofovir`; splitting them for counting would be a change of its own.

**Where it came from.** `substance_source_T` says, per record: `diana_name` (DiAna, by the drug name), `diana_prod_ai` (DiAna, by FDA's `prod_ai`), `correction` (one of our names or corrections changed DiAna's answer) or `none`. A record with `none` keeps FDA's spelling only, and a text search over drug names still finds it. The case window shows each record's ingredients beside FDA's spelling, labelled with where they came from and linked to this rule, and `No ingredient` for a record with none.

**Why:** on the 2026Q2 release DiAna maps 98.46% of FAERS drug records by name and 98.64% with `prod_ai`, against 74.7% for an exact RxNorm match, and its hand-checked core (18,886 spellings) carries 96% of the records. It is open, cited and kept up by its authors, so reading it by checksum gives everyone the same answer and takes their updates as reviewed changes. What it leaves unmapped is mostly rare: 482,738 spellings, 357,621 of them seen once. Counts are of drug records, one drug of one report, never of FDA's rows: since 2024Q4 FDA writes some records on one row per dose, and `drug_substance_T` gives them one row. The evidence is `notebooks/faers/05_drug_names`.
