---
rule: label-own-ingredients
line: A current label that DailyMed, the US label library, links to no drug code, such as TECENTRIQ's, is matched by the ingredients it lists itself, where no other label covers them.
values:
  names_tried: [substance, active_moiety]
enforced_in:
  - src/open_altio/faers/labels/build.py
  - tests/faers/test_labels.py
---
# Labels with no drug code

Rule label-choice reaches a label through DailyMed's mapping file, which links each label to RxNorm's product codes. Some current labels are missing from that file (TECENTRIQ's), and some are linked only to product codes the current RxNorm no longer holds (an old AVANDIA label); without more, their ingredients would show "No label found" although FDA has a label for them. Such a label is keyed instead by the active ingredients it lists itself, each matched exactly to one RxNorm ingredient's name.

**When.** Only a label the mapping file gives no product code the current RxNorm holds, and only for an ingredient, or combination, that no label in the mapping file reaches: a label the file maps always wins, so this never adds a second label beside one the file gives. A label the file maps to codes whose ingredients have no RxNorm set of their own is not keyed this way either.

**How.** Each active ingredient the label lists, in any of its products or kit parts, is looked up by name in RxNorm's ingredients, ignoring case: first the substance's name as the label writes it, then its active moiety (`names_tried`), so a salt written `METFORMIN HYDROCHLORIDE` with its moiety `METFORMIN` finds metformin. A name two RxNorm ingredients share finds neither, and a name close to an ingredient's but not equal finds nothing. A kit's pad (the ingredients rule label-choice does not count beside others) is not counted while the label lists anything else. One ingredient gives its code; several give the code of exactly that set, when RxNorm has one. If any ingredient finds no name, the label stays without a code. The label then takes part in the choice of rule label-choice like any other.

`label_candidates_T.keyed_by_T` says how each label found its key: `mapping_file` or `label_ingredients`. The manifest's `labels.keyed_by_own_ingredients` counts the labels keyed this way, the ingredients they give a label, and how many of the labels chosen are older than rule label-choice's `recent_from`, since an ingredient whose only label is old keeps that label.

**Why:** the mapping file is DailyMed's own link and the first choice, but a label it misses is still FDA's label for the drug. The label's own list of active ingredients is FDA's structured statement of what the product holds, so an exact match to RxNorm's ingredient names keys it without a guess, and "No label found" stays for drugs FDA truly has no label for. The evidence is in notebook `notebooks/faers/10_label_flags`, section 2: what an ingredient's own label says about the reactions of products containing it.
