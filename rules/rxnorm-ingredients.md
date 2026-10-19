---
rule: rxnorm-ingredients
line: Each drug gets its code from RxNorm, the US list of prescribable drugs, which joins it to its FDA label; a code is never guessed, so no drug is read against another drug's label.
values:
  source: RxNorm Current Prescribable Content, U.S. National Library of Medicine
  release: "10052026"  # text: the date in NLM's file names, month day year; not a limit
  download: https://download.nlm.nih.gov/rxnorm/RxNorm_full_prescribe_{release}.zip
  name_pairs: mappings/faers/rxnorm/name_pairs.csv
  prod_ai_pairs: mappings/faers/rxnorm/prod_ai_pairs.csv
  keeps_parent_code: mappings/faers/rxnorm/keeps_parent_code.csv
  acid_endings: {"aic acid": "ate", "ic acid": "ate", "ous acid": "ite"}
  ignored_characters: [" ", "-"]
  form_endings: ["ate", "ide", "ite"]
  form_words: [sodium, disodium, trisodium, potassium, dipotassium, calcium, magnesium, lithium,
               zinc, ammonium, aluminum, arginine, lysine, meglumine, tromethamine, choline,
               strontium, benzathine, procaine, diolamine, olamine, erbumine, epolamine,
               dimeglumine, polistirex, mofetil, medoxomil, kamedoxomil, medocaril, axetil, pivoxil,
               dipivoxil, cilexetil, proxetil, anhydrous, human, modified, macrocrystals, alfa]
  biologic_suffix: "-[a-z]{4}$"
  bare_elements: [aluminum, bismuth, boron, calcium, chlorine, copper, iodine, iron, lithium,
                  magnesium, manganese, molybdenum, potassium, selenium, silver, sodium, strontium,
                  titanium, zinc, zirconium]
settable:
  release:
    label: The RxNorm release to read (the date in NLM's file names, month day year)
enforced_in:
  - src/open_altio/faers/rxnorm/rrf.py
  - src/open_altio/faers/rxnorm/match.py
  - src/open_altio/faers/rxnorm/layer.py
  - src/open_altio/faers/labeldict/unit.py
  - tests/faers/rxnorm/test_rxnorm_files.py
  - tests/faers/rxnorm/test_rxnorm_match.py
  - tests/faers/rxnorm/test_rxnorm_layer.py
  - tests/faers/rxnorm/test_rxnorm_release.py
---
# US drug codes, from RxNorm

Each drug record gets the RxNorm code of its drug, from NLM's public list of drugs prescribable in the US, so a FAERS drug can be joined to its FDA label. The code comes from FDA's drug name when it is an RxNorm name, else from FDA's active ingredient when that is, else from the record's ingredient; it is never guessed, and a drug RxNorm files under a different drug, or a salt known only as its element, gets none, so it is never checked against another drug's label.

The drug names step gives each drug record an ingredient (`substance_T`): one ingredient as the DiAna dictionary writes it (an international name, INN, without its salt), or a combination's ingredients sorted and joined with `;`. `drug_rxnorm_T` gives each drug record, beside that ingredient, its RxNorm code: an ingredient code (IN) or a multiple-ingredient code (MIN). The record is still counted under the dictionary's ingredient; FDA's drug name and the ingredient are never changed. Switched off, the release has no `drug_rxnorm_T`.

**FDA's drug name first, FDA's active ingredient second, the dictionary's ingredient third.** A record's code comes first from FDA's drug name itself, when it is exactly one RxNorm name: an ingredient, a precise ingredient (read as its ingredient), a multiple ingredient, or a brand (read as its set of ingredients). No name pair and no spelling rule apply to a drug name. The code can then be more precise than the ingredient it is counted under: `LANTUS` is counted under `insulin` and coded `insulin glargine`; `TECFIDERA` is coded `dimethyl fumarate`; `TRUVADA` takes its multiple-ingredient code. When the drug name gives no code, FDA's active ingredient (`prod_ai`) is matched the same way, exactly: whole, or, for a combination FDA writes as names joined by `\`, every name exactly, taking the multiple-ingredient code of that set. A name of FDA's that RxNorm writes otherwise for the same substance is read through the short reviewed list `prod_ai_pairs`, each row with its evidence: FDA writes `DEXTROSE` where RxNorm writes `glucose`, so DIANEAL, whose active ingredient FDA writes `CALCIUM CHLORIDE\DEXTROSE\MAGNESIUM CHLORIDE\SODIUM CHLORIDE\SODIUM LACTATE`, takes its own multiple-ingredient code. No other pair and no spelling rule applies to FDA's names. So `KCL`, whose active ingredient FDA writes `POTASSIUM CHLORIDE`, is coded `potassium chloride`. Only when neither gives a code does the record's ingredient give one, as below. `matched_by_T` says which: `drug_name`, `prod_ai`, `substance` or `none`, and `no_code_reason_T` says why a record has none.

**Each ingredient's own code.** `ingredient_rxnorm_T` gives each ingredient a record is counted under (`ingredient_T`; a combination counts for each of its ingredients) the code its own reading gives it, as below: the code a record of that ingredient alone would take from its ingredient, whatever FDA's names on any record. The label flags read an ingredient's own label by it (rule label-flags).

**Source.** `source`, the release whose files are dated `release`, from `download`. NLM publishes this subset with no licence and no sign-in: it is public domain. It holds only drugs currently prescribable in the US: no obsolete drugs and no drugs sold only outside the US. One RxNorm release serves every quarter; a newer one is a change to `release`, which a person may also make for their own releases.

**Built with each release.** The release build reads NLM's files from the folder its zip unpacks to: `rxnorm/` in Open Altio's data folder, or the folder `OPEN_ALTIO_RXNORM_DIR` names (`--rxnorm` for `python -m open_altio.faers build`), and a folder holding another release than `release` refuses the build. The files are never kept in the repository; only the reviewed lists are. The release's manifest records the RxNorm release read, the download, each file's SHA-256 and the table's counts under `rxnorm`. A release built without the folder, or before its drug records carry an ingredient, has no `drug_rxnorm_T`, and its manifest says why.

**How an ingredient finds its code.** Only RxNorm's own names that NLM does not suppress are read, of four kinds: ingredients (IN), precise ingredients such as salts (PIN, read as their ingredient), multiple ingredients (MIN) and brand names (BN, read as their ingredients). Each name in an ingredient is looked up three ways, and the first that finds it wins:

1. **Exact.** The name is an RxNorm name, ignoring case.
2. **A reviewed name pair.** `name_pairs` gives RxNorm's name for a name the dictionary writes differently: a US name (USAN) for an international one (`acetaminophen` for `paracetamol`), a British spelling (`aluminium`), a vitamin the dictionary names by letter (`folic acid` for `vitamin b9`), or a form the dictionary leaves unnamed (`certolizumab pegol` for `certolizumab`). Each row says why the two are one substance.
3. **The same spelling.** The name and one RxNorm name are equal once both drop the characters in `ignored_characters` (spaces and hyphens) and write an ending in `acid_endings` as its salt (`alendronic acid` and `alendronate`, `azelaic acid` and `azelate`, `hypochlorous acid` and `hypochlorite`).

**A drug filed under a different parent has no code.** A precise ingredient takes its ingredient's code only when it is a salt, ester or other form of that same drug: once both names drop FDA's four-letter suffix (`biologic_suffix`, as in `olipudase alfa-rpcp`), write their acid ending and drop their salt and ester words, they spell the same. A salt or ester word is one in `form_words` (cations, organic counter-ions, ester groups, `anhydrous`, the source `human`, the forms `modified` and `macrocrystals`, and `alfa`, which an international name adds to some biologics) or one with an ending in `form_endings`, the endings chemistry gives an anion or an ester (`furoate`, `hydrochloride`, `nitrite`). `valproic acid`, `etrasimod arginine` and `isosorbide mononitrate` keep their ingredient's code. RxNorm also files distinct drugs as precise ingredients of a parent: an antibody-drug conjugate under its antibody (`trastuzumab deruxtecan` under `trastuzumab`), a prodrug or an enantiomer under its parent (`fosnetupitant`, `levoketoconazole`). Their names do not spell the parent's, so they get no code, and a label looked up by code says none was found rather than showing the parent's label. A brand is held to the drugs it sells: `ENHERTU` sells trastuzumab deruxtecan, so the brand takes no code either. Their reason is "RxNorm files it under a different parent drug". A drug name or active ingredient refused this way still lets the next source give a code, which the same test applies to.

The point is never to check a drug against a different drug's label, so a name whose parent's code can lead to no other drug keeps it. `keeps_parent_code` is the reviewed list of those precise ingredients, as RxNorm names them, each with its reason: a conjugate that is the only product of its antibody in RxNorm (`enfortumab vedotin`), a salt or ester whose name the form words do not reach (`sodium glycerophosphate`), or the same drug under another name (`divalproex sodium`, `ursodiol`, `glycopyrrolate`).

**An element alone is not a salt.** The dictionary writes a salt of an element as the element alone: `KCL`, `K-DUR` and `SLOW-K` are `potassium`, `TARDYFERON` is `iron`, `MILK OF MAGNESIA` is `magnesium`. RxNorm names each salt as an ingredient of its own (`potassium chloride`, `potassium citrate`, `ferrous sulfate`), with its own labels, and the dictionary does not say which salt it was. So a name of the dictionary's ingredient that leads to one of `bare_elements` gives no code, with the reason "the ingredient names an element, not which of its salts". The list holds the elements medicines carry as one of several salts or compounds; elements given as the element itself (`oxygen`, `nitrogen`, `helium`, `sulfur`) are not on it. FDA's own drug name or active ingredient naming the element (`POTASSIUM`) still gives the element's code, because that is what FDA wrote.

A one-ingredient name takes its ingredient's code. A combination takes the MIN whose ingredients are exactly the set its names give; when every name has a code but RxNorm lists no product with exactly that set (Paxlovid, which RxNorm lists only as packs of two drugs), the record has no code, with the reason "no US product has exactly these ingredients".

**Nothing is guessed.** A name close to an RxNorm name but not equal to it (`ostilodrostat` for `osilodrostat`) finds nothing. A spelling that two RxNorm ingredients share is evidence for neither, so it finds nothing. A name pair is used only once a person has read it and written its evidence.

**What has no code, and why.**

- **Products not sold in the US**, and drugs no longer prescribable there (rofecoxib, telaprevir): the subset holds only current US drugs, so their labels show none found.
- **Drugs RxNorm files under a different parent**, as above.
- **Herbals and other natural products** the dictionary names by genus (`senna spp`), which RxNorm names by preparation or not at all.
- **Vitamin, mineral and other groups** (`vitamins, unspecified`, `vitamin b, unspecified`), and the dictionary's other broad groups RxNorm splits: every insulin is `insulin`, every polyethylene glycol is `macrogol`, every botulinum toxin one name. A group names no one ingredient, so it takes no ingredient's code. Vitamin D of no stated form is the exception: RxNorm has an ingredient for it, `vitamin D`, and a name pair joins the two.
- **Devices and other things that are not drugs** (`intrauterine contraceptive device`), and unspecified or class terms (`contraceptives, unspecified`).
- **Salts known only as their element:** the dictionary's `potassium`, `iron`, `calcium` or `magnesium` where FDA's drug name and active ingredient name no RxNorm drug, as above.
- **Combinations** with any of these as a part, or whose exact set of ingredients no US product has.

**Why:** RxNorm is the US standard for naming drugs and is free for anyone to use, so a code from it lets anyone join our substances to FDA's labels and to other US data. Codes come only from an exact name, a reviewed pair or a fixed spelling rule, so anyone can check why a substance has its code, and a substance that has none says so rather than taking a near one. A missing label is better than the wrong one, so a drug RxNorm files under another drug takes no code. The element's code would join a salt to the labels of whatever happens to carry the element itself, so a salt the record names only as its element takes none, while FDA's own active ingredient, where it names the salt, gives the salt's code. The matching was measured against the dictionary and the release in `notebooks/faers/05_drug_names`, section 3.
