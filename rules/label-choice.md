---
rule: label-choice
line: Each ingredient is read against its original maker's current label, one for each way it is taken, such as tablet or injection; finding no label is a normal outcome.
values:
  one_label_per: RxNorm ingredient, or the full ingredient set (RxNorm MIN) for a combination label
  marketing_categories:
    C73594: NDA
    C73585: BLA
    C73584: ANDA
  not_counted_beside_others: [inert ingredients, isopropyl alcohol, povidone-iodine, ferrous fumarate, ferrous bisglycinate,
                              ethanol, alcohol]
  application_order: [[NDA, BLA], [ANDA], [other]]
  readable_sections: [boxed_warning, warnings_and_precautions, warnings, precautions, adverse_reactions, contraindications]
  kit_form: KIT
  recent_from: 2020-01-01
  then: lowest application number, then newest effective date, then set ID
enforced_in:
  - src/open_altio/faers/labels/choose.py
  - src/open_altio/faers/labels/build.py
  - src/open_altio/faers/labels/update.py
  - tests/faers/test_labels.py
---
# Which label a drug is read against

A FAERS drug reaches a label through its ingredient: drug name, then active ingredient, then RxNorm ingredient code, then the label. This rule says which label an ingredient gets, so every flag reads the same label and anyone can see why. Finding no label is a normal outcome, not an error.

## Which labels belong to an ingredient

A label's ingredients are worked out from RxNorm, not from its title: DailyMed's mapping file gives the RxNorm codes of the products the label covers, and RxNorm links each product to its ingredients (rule label-source). A pack counts every product inside it.

Some ingredients come with a drug rather than being one (`not_counted_beside_others`): the placebo tablets of a contraceptive pack (RxNorm's "inert ingredients"), its iron reminder tablets, and the alcohol or iodine pad in an injection kit, whose alcohol RxNorm names `isopropyl alcohol` or `ethanol` and a label may write `alcohol`. They are not counted while the label has any other ingredient, so HUMIRA's label, which DailyMed also maps to the alcohol pad in its kit, is an adalimumab label, GATTEX's, mapped to the ethanol pad in its kit too, is a teduglutide label, and a contraceptive pack is keyed by its two hormones. A label of one of them alone keeps it.

- **One ingredient.** A label whose products together hold exactly one ingredient is a candidate for that ingredient, keyed by its RxNorm ingredient code (term type IN). Salt forms share their ingredient, as RxNorm has it: a label for apixaban and one for a salt of it are candidates for the same ingredient.
- **A combination.** A label whose products together hold two or more ingredients is a candidate for that whole set, keyed by RxNorm's code for the set (term type MIN). It is never a candidate for any one of its ingredients: an ingredient is judged against its own single-ingredient label, so valsartan's reports, Entresto's included, are read against valsartan's label, and Entresto's own reports against Entresto's. A set RxNorm has no MIN for gets no label, and is counted.
- **No code.** A label with no RxNorm code in the mapping file, or only codes the current RxNorm does not hold, is counted, and keyed by its own active ingredients only where the mapping file gives its ingredient no label (rule label-own-ingredients); otherwise it is left out.

## Which candidate wins

In each route family, in this order, the first that separates them decides:

1. **Closest route.** A label whose own routes name the family more closely comes first: of its routes that allow the family, the one with the fewest families in the shared route table (rule drug-route) counts. A route that is that family alone (`INTRAVENOUS` for injected) beats one that reaches it only as one of several (`OPHTHALMIC`, the eye or an injection into it; `TOPICAL`, nine families). So dexamethasone's injected family is read against its injection's label, not MAXIDEX's eye drops, lidocaine's eye family against an eye gel, not LIDODERM's patch, and diclofenac's transdermal family against its patch, not its gel. A family that only a broad route reaches keeps that label.
2. **Readable.** A label whose safety sections (`readable_sections`, as rule label-sections finds them) hold no words is set aside while the ingredient has one that does. Some labels file every section as unclassified, or carry the section codes with nothing in them; such a label cannot be compared with, however original it is. Which labels these are is counted, never guessed from headings.
3. **A pharmacy's kit.** A label whose products are all kits (FDA's dosage form `kit_form`) is set aside when another label among the candidates, not a kit, is marketed under one of the kit's own application numbers: the kit bundles a product that has its own label, and that label is the one to read. A pharmacy's convenience kit bundles another company's injection with swabs and syringes and carries every application in the bundle, so without this step it would win on the lowest number: dexamethasone's intravenous and intramuscular label would be a kit's, not an injection's. An originator sold only as kits (HUMIRA's pens, ABILIFY MAINTENA, GLUCAGEN) has no label of its own application outside its kits, so it stays the originator. Otherwise a kit takes its place by the steps below.
4. **Recent.** Labels effective before `recent_from` are set aside while the ingredient has any label from that date on. An old copy, often a repackager's, never wins over a current one.
5. **Originator.** By the label's marketing category, read from FDA's codes in the label (`marketing_categories`), in `application_order`: an NDA or BLA first, then an ANDA (a generic), then anything else (unapproved drugs, authorised generics, others). A label with products in several categories takes its best.
6. **Earliest application.** Among them, the lowest application number. The first application approved for an ingredient has the lowest number, so this picks the originator's product over a later reformulation or a biosimilar.
7. **Newest.** The label with the newest effective date.
8. **Set ID,** so the choice is the same on every run.

`label_candidates_T.chosen_because_T` says, in a few words, which step decided and how many candidates there were.

## One label per route family

FAERS pools every product of an ingredient, but its labels can differ by form: diclofenac's gel and tablets, dexamethasone's eye drops and tablets. So the steps above pick one label for each route family the ingredient's labels can be in. A label's families come from the one shared route table FAERS drug records are read with (rule drug-route, `open_altio.faers.route.label_families`): each route a label names maps to the set of families a drug given that way could be in, so `ORAL` is by mouth or under the tongue and `OPHTHALMIC` is the eye or an injection into it, and the label is a candidate in every family of every route it names. One label can therefore serve several families, and the choice in each family is the one above. A kit part holding only the ingredients that are not counted beside others (`not_counted_beside_others`: an alcohol or iodine pad, placebo tablets) or no active ingredient at all adds no route, and neither does the kit's own route list where it repeats such a part's route, unless the label has no other: HUMIRA's alcohol pad does not make it a skin label, nor does a pharmacy kit's swab make one for dexamethasone. `routes_T` lists the routes that count.

No family is made up here for a route the shared table does not hold: such a route gives none, and the manifest lists it (`labels.routes_not_in_route_table`, with how many labels name it) for the table's own review. A label whose routes give no family, or that names no route, is kept under rule drug-route's unknown key, so a record reaches it only where the record's own families have no label of their own (`labels.labels_with_no_route_family` counts them). On the 2026Q2 labels every route a keyed label names is in the table.

`label_candidates_T` holds one row per ingredient (or combination) and family. There is no default label: when a record's family is unknown, the comparison checks it against every family's label and shows a split where they disagree, never a guess. `forms_differ_T`, the same on every row of an ingredient, is true when two of its families' labels have different safety sections (rule label-sections, all but indications, compared with case and spacing ignored); one label serving every family, or labels with the same safety text, give false. On the 2026Q2 labels 1,450 of 2,128 ingredients and combinations have labels in more than one family, and for 260 of them the families' safety sections differ. `open_altio.faers.labels.lookup.LabelLookup` reads it.

The safety sections of every one of these labels are read (rule label-sections).

**Known case:** DailyMed maps TYSABRI's label to no RxNorm code, so natalizumab's label is its biosimilar's (TYRUKO). A biosimilar's label mirrors the reference product's, so this stands until DailyMed maps it.

**Why:** a route the shared table lets be several families is honest about what FAERS's words can mean, but a label written for one form should not stand in for a form that has its own label, so the closest route decides first; the originator's label is the fullest and the one generics copy, and biosimilars mirror their reference product, so no company matching is needed, which FAERS often could not support anyway; reading it per route family keeps a report about tablets from being compared with an eye drop's label; today's label is the one a reader can open and check. The evidence is in notebook `notebooks/faers/10_label_flags`, section 4: which form's label decides, and where forms differ.
