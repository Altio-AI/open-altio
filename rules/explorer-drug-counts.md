---
rule: explorer-drug-counts
line: A drug's cases count it where the report names it as the main or another suspect (FDA's PS and SS), in any product containing it; other roles are one click away.
values:
  roles: [PS, SS, I, C]
  default_roles: [PS, SS]
  units: [any, exact]
  default_unit: any
enforced_in:
  - src/open_altio/explorer/drugs.py
  - src/open_altio/explorer/classes.py
  - src/open_altio/faers/insights/numbers.py
  - tests/explorer/test_drugs.py
---
# Which drugs a count takes

A product page and the Drugs filter count a drug by its ingredient (rule `drug-names`), in any product containing it, where FDA codes it the primary or a secondary suspect. Every other role, and the product alone, is one click away.

**The roles** are FDA's own codes for how a drug was involved, never recoded: `PS` primary suspect, `SS` secondary suspect, `I` interacting, `C` concomitant (taken alongside, not suspected). `roles` are the tick boxes offered, in that order; `default_roles` are ticked when a page opens. A case counts when it names the drug in any ticked role. A drug with another code, or none (820 of the 75 million drug rows on the 2026Q2 release), counts under no tick box.

**The unit** is what one drug means. `any` counts every product containing the ingredient, so valsartan's cases include those naming Entresto (sacubitril and valsartan); `exact` counts the product of exactly those ingredients, valsartan alone. A combination is a drug of its own too: Entresto's page counts sacubitril and valsartan together, and in `any`, every product holding both. `default_unit` is the one a page opens with; the Drugs filter always counts in it.

**Drug classes.** The Drug class filter counts a WHO class the same way: a case counts when it names a drug of that class in a ticked role, the same tick boxes, PS and SS ticked when a page opens.

**Spellings.** Every count covers all of FDA's spellings of the drug, each listed with its cases and ticked; a person may untick one, and may add FDA's spellings that carry no ingredient (DiAna does not name them), which a search finds by their words. The counts are of cases, never of FDA's rows.

**Why:** statistics and the label checks count the suspect drugs, PS and SS, so a medicine many people take alongside does not become a frequent suspect: counted in every role, a background drug has many times its suspect cases (`notebooks/faers/05_drug_names`, and the methods page). DiAna's own tool counts every role by default, so its counts run higher than ours. Counting any product containing the ingredient keeps one medicine together whatever it is sold with, which is what a safety question about an ingredient asks.
