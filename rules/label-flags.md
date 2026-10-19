---
rule: label-flags
line: "Each drug and reaction gets one flag: on the label, related (the label names something close), not on the label, or set aside, by fixed rules anyone can rerun."
values:
  outcomes:
  - on_label
  - related
  - not_on_label
  - forms_differ
  - treated_disease
  - not_a_medical_event
  - procedure
  - no_label
  - uncertain
  unknown_family: unknown
  closest_to_label:
  - on_label
  - uncertain
  - related
  - not_on_label
  - treated_disease
  - not_a_medical_event
  - procedure
  - no_label
  suspect_roles:
  - PS
  - SS
  trial_products: no_flag
  group_name_starts: ["vitamin ", "factor ", "von willebrand factor"]
  same_drug: mappings/faers/label_flags/same_drug.csv
  expectedness:
    on_label: expected
    related: unexpected
    not_on_label: unexpected
    forms_differ: unexpected
    uncertain: unexpected
    no_label: unexpected
    treated_disease: set_aside
    procedure: unexpected
    not_a_medical_event: set_aside
  related_by: primary_hlt
  same_meaning:
  - [Drug hypersensitivity, Hypersensitivity]
  - [Peripheral swelling, Oedema peripheral]
  - [Drug dependence, Dependence]
  - [Drug withdrawal syndrome, Withdrawal syndrome]
  opposite_direction:
    up_ends: increased
    down_ends: decreased
    up_starts: hyper
    down_starts: hypo
    shortest_stem: 4
    same_measure:
      blood glucose: glycaemia
      blood potassium: kalaemia
      blood sodium: natraemia
      blood calcium: calcaemia
      blood magnesium: magnesaemia
      blood pressure: tension
      blood cholesterol: cholesterolaemia
      blood triglycerides: triglyceridaemia
      blood phosphorus: phosphataemia
      blood uric acid: uricaemia
      blood thyroid stimulating hormone: thyroidism
      heart rate: cardia
      body temperature: thermia
  catch_all_key: catch_all
  section_order:
  - boxed_warning
  - warnings_and_precautions
  - warnings
  - precautions
  - adverse_reactions
  - contraindications
  decided_by:
    rule: rule
    reviewer: model_reviewed
    model suggestion: model_suggested
    umbrella: 'rule: umbrella'
settable:
  suspect_roles:
    label: The drug roles whose reactions get a label flag (PS, SS, I, C)
enforced_in:
- src/open_altio/faers/labeldict/flags.py
- src/open_altio/faers/insights/cards/rule_charts.py
- src/open_altio/faers/labeldict/flagbuild.py
- src/open_altio/faers/labeldict/join.py
- src/open_altio/faers/labeldict/groups.py
- tests/faers/test_label_flags.py
- tests/faers/test_label_build.py
- tests/faers/test_label_join.py
- src/open_altio/faers/rxnorm/layer.py
- src/open_altio/faers/labeldict/unit.py
- src/open_altio/faers/insights/numbers.py
---
# On the drug's label?

For each drug and reaction we say whether the drug's FDA label states the reaction, by fixed rules anyone can read and rerun. A reaction that is not on the label is the first thing a safety reviewer asks about. The flags hold no MedDRA codes, so everyone can see them.

`label_flags_T` has one row per drug (`rxcui_T`, the RxNorm ingredient code), the record's route families (`route_families_T`) and reaction (`pt_T`, the reaction text as FDA published it). A label belongs to one route family of the labels step (by_mouth, under_tongue, injected, inhaled, nasal, rectal, vaginal, transdermal, skin, eye, ear, other; `label_candidates_T`, rule label-choice). A record's route families are the families its form could be, sorted and joined with ";": one when the form is certain ("by_mouth"), several when it could be more ("by_mouth;under_tongue;vaginal" for a plain tablet), empty when nothing is known. `setid_T` says which label was read and `judged_on_T` which family's label or labels decided. Every column ends in `_T` (rule transformed-suffix-T); below they are named without it.

Which labels a record is judged on, so a flag is never guessed from one label silently:

- **One family, with a label:** that family's label.
- **Several families, each with a label:** only those families' labels, resolved as below, and `judged_on` lists them.
- **A family with no label of its own** (oral acetaminophen sold over the counter, whose only prescription label is an injection) counts as unknown, so the record is judged on every family's label: `judged_on` names the one or ones that decided ("injected": on the injection label, no label for tablets).
- **Nothing known** (no families, or `unknown_family`): every family's label.

One label can serve several families, when its routes span them (a label for intravenous and intraperitoneal use serves injected and other). A record is then read on every label whose families overlap its own, and a flag that one label decided names that label in `setid_T` however many of its families were read.

The flags are written for the release's own drug records: every suspect record, `suspect_roles` (PS and SS, as every count does; a person can add I and C in their own rules), of the latest version of each case, with every reaction of its case. A drug record DiAna marks as a trial product (a named study drug, a placebo, a blinded product; `diana_trial_T` in `drug_substance_T`) gets no flag at all (`trial_products`): its label is not known. A record finds its label by its RxNorm code (`rxcui_T` in `drug_rxnorm_T`, rule rxnorm-ingredients): an ingredient's, or an exact combination's own. Its route families come from `route_families_T` in `drug_route_T` (rule drug-route). A record with no RxNorm code is flagged with an empty `rxcui_T`: no label can be found for it. The label follows the ingredient the record is counted under (`substance_T` of `drug_substance_T`), so a record whose code names another drug is flagged the same way, no_label (shown as "Not compared", no label found), never on the code's label: one whose counted ingredients and code share no ingredient, each counted ingredient being a drug some record of the release is coded as and no element named alone, read through the reviewed name pairs and acid endings of rule rxnorm-ingredients (a name inside the other's counts as shared, so `insulin` and `insulin glargine`, or `oxybate sodium` and `oxybate`, are one drug). FDA's active ingredient `DIAZEPAM` on a record counted as valproic acid is such a code. A counted ingredient whose name begins with one of `group_name_starts` names a group (a vitamin by its letter, a clotting factor by its number), and its code names one of the group (`pyridoxine` for vitamin B6, `efmoroctocog alfa` for factor VIII), so it is not compared. `same_drug` is the short reviewed list of drugs RxNorm names two ways, both its own, such as a prodrug and the drug it becomes (isavuconazole, whose label is CRESEMBA's isavuconazonium): either name counts as the counted ingredient's. The release's `label_other_drug_T` lists these records, with the code not read, its name, how it was found and the counted ingredient, and the screens read them the same way. A drug record's key (`era_T`, `primaryid`, `quarter_T`, `drug_seq`) repeats in `drug_latest_T`, one row per dose, so records are read as distinct keys, and any count after the join counts cases or distinct drug keys, never rows joined back to `drug_latest_T`.

**Each ingredient on its own label.** Each such record is also flagged by each ingredient it is counted under (`substance_T` of `drug_substance_T` split at ";": a combination counts for each of its ingredients, as the statistics count them), for the pages that count any product containing an ingredient (rule explorer-label-flags). The row is keyed by the ingredient's own code (`rxcui_T` in `ingredient_rxnorm_T`, the code the ingredient's own reading gives it, rule rxnorm-ingredients), with the record's route families, for every reaction of its case, so it reads the ingredient's own single-ingredient label (rule label-choice): the valsartan in a report of Entresto is judged against valsartan's label, beside Entresto's own flag on Entresto's label, and a record whose own code names another drug is judged there on the label of the ingredient it is counted under. A row an ingredient's code gives that a record's own code already gave is the same row, written once. An ingredient with no code of its own is flagged with an empty `rxcui_T`, and one whose code has no label gets no_label, as a record would. A release without `ingredient_rxnorm_T` is flagged by each record's own code alone, and its manifest says so.

A release without `drug_rxnorm_T`, or without `drug_substance_T`, gets no flags: no record could find its label, or none could be told apart from a trial product. A release without `drug_route_T` is flagged with no record's form known, so each is read on every family's label. Either way the release's manifest says so in its `label_flags` entry, which also counts the suspect records and their cases by how far each got: a trial product, no RxNorm code, a code that names another drug than the one counted, a code with no label in any family, or a label.

When more than one label is read, `family_outcomes` keeps each family's outcome ("by_mouth: on_label; skin: not_on_label"). When one family's label has the reaction on it and another's does not, the outcome is **forms_differ** (shown as "Listed on the tablet label, not listed on the gel label"), and `judged_on` names every family read. When every family agrees on expectedness, the outcome is the one closest to the label, in the order of `closest_to_label`: related beats not_on_label, and an uncertain phrase, which may state the reaction, beats both; `judged_on` names the families whose label gave it. Nothing is hidden, because every family's outcome reads the same way. Outcomes set aside are decided by the term alone, so they never differ by family. Plain uncertain is left for when nothing is known.

Its `outcome` is decided in this order, the first that fits:

- **uncertain** (shown as "Can't tell"), when the reaction text is not a MedDRA name the licensed part can map.
- **procedure** (shown as "Not compared", a procedure): the term names a surgical or medical procedure (`rules/label-procedure.md`).
- **not_a_medical_event** (shown as "Not compared", not a medical event): the term names no health effect (`rules/label-not-a-medical-event.md`).
- **no_label** (shown as "Not compared", no label found): there is no label for the drug in any family, or the record has no RxNorm code.
- **treated_disease** (shown as "Not compared", the disease it treats): the label's indications name the term's own PT, and the term names no worse form of it (`rules/label-treated-disease.md`). The indications never put a term on the label.
- **on_label** (shown as "Listed"): any phrase the rules keep, in any section read (`rules/label-dictionary.md`), the postmarketing list included, names the same preferred term (PT). One sentence that keeps a term off ("no cases of hepatitis were reported in the trial") never cancels another that names it. `section` says where: the first section in `section_order` that names it.
- **on_label** by a term that means the same: the label keeps no such PT, but it keeps the PT that `same_meaning` pairs with it, the second of a reviewed pair of PT names for one finding ("Drug hypersensitivity" and "Hypersensitivity"; "Peripheral swelling" and "Oedema peripheral"). The list is of pairs, never a pattern: MedDRA files the two in different groups, so no group rule would join them, and only the listed direction counts (the reported PT first, the label's PT second). `section` is where the label keeps the second PT.
- **on_label** by the umbrella rule: the label keeps an umbrella term whose group holds the PT, and the PT names no severe form (`rules/label-umbrella.md`).
- **uncertain**: the label names the PT only in a phrase the rules could not read and nobody has coded yet (`label_uncertain.jsonl`).
- **forms_differ**, when more than one label is read: one family's label has the reaction on it and another's does not (above).
- **related** (shown as "Possibly listed"): the label keeps no such PT, but it keeps a PT under the same primary MedDRA group (`related_by`, the PT's primary high level term). The group is never named in anything public. A group whose kept PTs are all the opposite direction of the reported PT's measure never makes a pair related (`opposite_direction`: a PT ending in "increased" or "decreased", or starting with "hyper" or "hypo", is a rise or a fall of its measure; `same_measure` joins a blood test to the word for the same measure): a label that names a fall of platelets says nothing about a rise of them, so that pair is not_on_label. A catch-all group never makes a pair related: MedDRA's "not elsewhere classified" groups and its general signs and symptoms hold terms that share no meaning, so a label naming one says nothing about another. Seven of the "not elsewhere classified" groups are left off that list: each holds one family of close terms (the kinds of rash, of hepatitis, of arthritis, of oedema, of sepsis, of heart failure and of seizure), so a label naming one says something about another. The licensed part lists those groups under `catch_all_key` in `label_groups.json`, beside the MedDRA version's tables, and such a pair is not_on_label.
- **not_on_label** (shown as "Not listed"): the label keeps neither the PT nor anything in its group.

`expectedness` reads the outcome as ICH E2A does, and as FDA defines an unexpected reaction, one "not listed in the current labeling for the drug product" (21 CFR 314.80): `expected` for on_label; `unexpected` for related, not_on_label, forms_differ, uncertain and no_label, because a reaction is unexpected until a label says otherwise, and for procedure, which is not compared with the label but can be the only trace of harm the report does not name (a transplant after liver failure); `set_aside` for treated_disease and not_a_medical_event. These are exactly the flags the explorer's Unexpected only ticks (rule explorer-label-flags, `unexpected_only`), so the data and the screens count the same unexpected pairs.

related (Possibly listed) is kept apart from on_label (Listed) on purpose. Under ICH E2A a reaction whose nature, severity or specificity is not consistent with the label is unexpected, even when the label names a broader or milder one: a label that names "hepatitis" does not make "hepatic necrosis" expected. So related counts as unexpected, and says only that the label names something nearby. Only a PT the label keeps counts for related; an uncertain PT nearby does not make the pair uncertain, because either way the reaction is unexpected.

Reactions are compared as current PTs. FDA published each reaction in the MedDRA version of its quarter, so an old term may since have become a lower level term of another PT. The licensed part's `reac_meddra_T` maps every reaction text to its current PT (MedDRA's licensed part of the release), and the comparison uses it, so an old term finds its label.

`set_id` and `label_date` (the label's effective date) are given whenever the drug has a label, so a reader can open the label that was read. `section` is given only for on_label.

`decided_by` says how the outcome was reached (`decided_by` maps the label row's value to the flag's): `rule` when fixed rules settled it, `model_reviewed` when a reviewed coding of a label phrase the rules could not settle decided it (`label_codings_frozen.jsonl` in the version's folder of the licensed part), `model_suggested` when only a model's suggestion decided it and nobody has checked it yet, `rule: umbrella` when the umbrella rule did. A label row a rule settled wins over one a person settled, and that over a suggestion.

The coded label rows (`label_terms_T`) and the uncertain items (`label_uncertain.jsonl`) are MedDRA content and live only in the licensed part of a release (`licensed/meddra/<version>/`). `label_flags_T` holds no MedDRA code, no lower level term and no group, and is public.

**Why:** a reaction that is not on the drug's label is the first thing a safety reviewer asks about a signal. Deciding it by fixed rules, once per label, makes every flag reproducible and lets anyone check it against the label text; a model only suggests where rules cannot read, and says so. The evidence is in notebook `notebooks/faers/10_label_flags`: how far records reach a label (section 1), what the flags say (section 2), a case-weighted hand check (section 6) and how accurate the flags are (section 7).
