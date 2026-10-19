# The dictionary's names paired with RxNorm's

For anyone checking why a substance has the RxNorm code it has.

The substances drug records name come from the DiAna dictionary, which writes international names (INN) and names vitamins by letter. RxNorm writes US names (USAN). Most substances are written the same way in both and find their code by exact name. `name_pairs.csv` pairs the names the two write differently, so those find their code too (`rules/rxnorm-ingredients.md`). Each row is one substance under two names; nothing here changes a substance or FDA's drug name.

## The file

| Column | What |
|---|---|
| `dictionary_name` | The name as the dictionary writes it, in lower case |
| `rxnorm_name` | RxNorm's name for the same substance, in lower case |
| `evidence` | Why the two are one substance: a US name and an international name, a British and a US spelling, a vitamin's letter, the same name in another word order, or a form the dictionary leaves unnamed |

A name has one row. A pair is used only where the exact name finds nothing; a name the spelling rule already joins (spaces, hyphens, `-ic acid` and `-ate`) needs no row.

## How it was checked

- The pairs are the most frequent disagreements between the dictionary and RxNorm on the drug rows of the 2026Q2 release, read pair by pair (`notebooks/faers/05_drug_names`, section 3), and the vitamins the dictionary names by letter where RxNorm does not (`vitamin b9` is `folic acid`). RxNorm writes `vitamin B12`, `vitamin B6` and `vitamin K1` as the dictionary does, so those need no row.
- Three more were read among the substances with the most drug rows and no code: `oxybate sodium` (RxNorm's `sodium oxybate`), `certolizumab` (RxNorm's `certolizumab pegol`, the only certolizumab there is) and `vitamin d, unspecified` (RxNorm's `vitamin D`, which also names no form).
- Left out on purpose: `macrogol`, which names three RxNorm ingredients (`polyethylene glycol 3350`, `polyethylene glycol 4000` and `polyethylene glycols`), so pairing it would pick one; and `flumetasone`, which the prescribable subset does not hold.
- On the 2026Q2 release, the pairs give a code to 192 substances, carried by 6,370,810 drug rows: 8.6% of the rows whose drug name the dictionary maps to a substance. Three pairs carry the most: `acetylsalicylic acid` (aspirin), `paracetamol` (acetaminophen) and `salbutamol` (albuterol).

## prod_ai_pairs.csv

FDA's active ingredient (`prod_ai`) is matched to RxNorm exactly, with no spelling rule (`rules/rxnorm-ingredients.md`). This short list gives RxNorm's name for a name FDA writes differently for the same substance, so a record whose active ingredient FDA writes that way is still coded.

| Column | What |
|---|---|
| `fda_name` | The name as FDA's active ingredient writes it, in lower case |
| `rxnorm_name` | RxNorm's name for the same substance, in lower case |
| `evidence` | Why the two are one substance |

It holds `dextrose`, RxNorm's `glucose`: on the 2026Q2 release it gives DIANEAL's peritoneal dialysis solutions their own combination code. A row is added only after a person has read it, as for the dictionary's pairs.

## keeps_parent_code.csv

RxNorm files some distinct drugs under a parent drug, and those get no code, so no drug is checked against a different drug's label (`rules/rxnorm-ingredients.md`). A precise ingredient on this list keeps its parent's code anyway, because that code can lead to no other drug; so does a brand that sells it (`PADCEV`).

| Column | What |
|---|---|
| `rxnorm_name` | The precise ingredient as RxNorm names it, without FDA's four-letter suffix, in lower case |
| `reason` | Why its parent's code is its own: a conjugate that is the only product of its antibody in RxNorm, a salt or ester whose name the rule's form words do not reach, or the same drug under another name (`divalproex sodium` for valproate) |

Each conjugate here was checked in the RxNorm release the rule pins: every clinical drug under its antibody is that conjugate, under one brand. A conjugate whose antibody is a drug of its own (`trastuzumab deruxtecan`, under `trastuzumab`) is never listed.

## Changing it

A new row, or a change to one, is a reviewed change with its evidence. A release's manifest lists every pair whose RxNorm name the RxNorm release it read does not hold (`rxnorm.unused_name_pairs`), so a pair a newer RxNorm release drops is seen in the first release built from it.
