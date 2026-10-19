---
rule: drug-route
line: From FDA's route, the dose form and words in the drug name, each drug gets every way it could have been given, such as by mouth or injected, so it is read against the right label.
values:
  fill_in: true
  sources: [route, dose_form, drugname]
  families: [by_mouth, under_tongue, injected, inhaled, nasal, rectal, vaginal, transdermal, skin, eye, ear,
             other]
  unknown: unknown
  unknown_code: "065"
  disagree: disagree
  none: none
  families_table: mappings/faers/route/families.csv
  route_table: mappings/faers/route/route.csv
  e2b_table: mappings/faers/route/e2b_route.csv
  atc_group_table: mappings/faers/route/atc_group.csv
settable:
  fill_in:
    label: Read the dose form and the drug name as well as FDA's route
enforced_in:
  - src/open_altio/faers/route/tables.py
  - src/open_altio/faers/route/clean.py
  - tests/faers/route/test_route_tables.py
  - tests/faers/route/test_route_clean.py
  - tests/faers/route/test_route_release.py
---
# How each drug was given

FDA records how each drug was given in the reporter's words, and often only as Unknown or not at all. We give each drug record the route families it could be in, read from FDA's route, its dose form and the form words of its drug name, and one family when they leave only one. The label flags compare a report with the labels whose families overlap the report's, and FDA's own text is not changed.

`drug_route_T` has one row per drug record, keyed by (`era_T`, `primaryid`, `quarter_T`, `drug_seq`), however many rows FDA wrote for the record:

| Column | What |
|---|---|
| `route_T` | FDA's route as an ICH E2B route code (`048` Oral, `058` Subcutaneous, `065` Unknown); `unknown_code` when the record's rows give different routes; empty when FDA gave none |
| `route_source_T` | Which of FDA's fields said something on any row, in the order of `sources`, joined with `+` (`route+dose_form`); `disagree` when they contradict each other on a row; `none` when none said anything |
| `route_families_T` | Every family the record could be in, sorted and joined with `;`; empty when nothing is known |
| `route_family_T` | That family when there is exactly one, else `unknown` |

`route_families_T` is the honest answer: one family when the record is certain, several when its values allow several (FDA's route `Oral` allows `by_mouth` and `under_tongue`), contradict each other or its rows give different families, and empty when nothing is known. `route_family_T` stays a single value, `unknown` whenever there is not exactly one family, so a filter on it never counts a record twice.

## The families

Twelve families, named in `families`, following the administration routes of the World Health Organization's ATC index with defined daily doses (WHO Collaborating Centre for Drug Statistics Methodology, Oslo): oral (`by_mouth`), sublingual and buccal (`under_tongue`), parenteral (`injected`), inhaled, nasal, rectal, vaginal and transdermal; to them are added the forms WHO gives no doses for: `skin`, `eye` and `ear`, and `other` for a real way of giving a drug that fits none of them, such as into the bladder or a dialysis fluid.

## The rule

1. **Each value is a set of families.** `families_table` gives every value FDA writes, by where it is written (`route`, `dose_form`, a form word in the drug name `drugname`, or a route name on a label `label`), every family a drug given that way could be in: one family only when no other is plausible, several when a real product of another family is given that way too (a plain tablet can be swallowed, held under the tongue or placed in the vagina), and none when the value says nothing about how the drug was given (`Unknown`, `Other`, `Transplacental`). A value is looked up in lower case, spaces collapsed, spaces and double quotes trimmed; a value the table does not hold says nothing.
2. **On each row, the sources that say something intersect.** A row's sources are FDA's route and dose form on that row and each form word of its drug name, found as a whole word in `drugname_norm_T`. A source that says nothing is left out. The row could be in the families that every source that says something allows: FDA's route `Oral` (`by_mouth`, `under_tongue`) with the dose form `Film-coated tablet` (`by_mouth`, `vaginal`) leaves `by_mouth`.
3. **Sources that contradict each other give their union.** When a row's sources allow no family in common, the row could be in any family one of them names; `route_source_T` is `disagree` and `route_family_T` is `unknown`.
4. **A record could be in every family one of its rows could be in.** FDA writes one row per dosage regimen, and two regimens of one drug can both be true: rows `Oral` and `Topical` leave every family either allows, not the one family they share (`under_tongue`). A row that says less is not narrowed by the other rows: `Oral` with `Film-coated tablet` on one row and `Film-coated tablet` alone on another leave `by_mouth` and `vaginal`.
5. **Nothing known.** When no source on any row says anything, `route_families_T` is empty, `route_family_T` is `unknown` and `route_source_T` is `none`.
6. **A label's families** are the union of the sets of its route names (`label` rows; a route name with no label row reads as the FAERS route word of the same name, which the table always places the same way). **A report matches a label when their families overlap**: a report that could be swallowed or held under the tongue matches an oral label and a sublingual one. `open_altio.faers.route.label_families(routes)` gives a label's families.

A table that lists a value twice for one source, names a family not in `families`, names a source other than the four, or gives a name word that is not one word, stops the build; so does a route word read as a code `e2b_table` does not hold.

With `fill_in` off, only FDA's route is read: the dose form and the name say nothing, and the record could be in every family one of its rows' routes allows. Switched off, no record has a cleaned route: `route_T` and `route_families_T` are empty, `route_source_T` is `none` and `route_family_T` is `unknown` on every record, so the label flags read every label.

## The drug-class groups

`atc_group_table` gives each E2B code at most one group of the WHO class choice: `eye`, `ear`, `nose`, `lungs`, `skin`, `vagina`, `mouth`, `injection`, `transdermal`, read from `route_T`. The class choice (rule atc-class-choice) reads a record's group here, and gives each group the WHO codes it fits; a code in no group says nothing.

## Why

A wrong route would compare a report with the wrong label, or file it under the wrong class, without saying so. Most FDA values do not name one form: the route `Oral` is written for sublingual tablets too, a tablet can be vaginal, and a solution for injection can be injected into the eye. Listing every family a value allows, and keeping only the families every source on a row allows, settles a record where its sources together leave one family and says honestly where they do not. Rows are read apart because each is its own dosage regimen: intersecting a drug taken by mouth with the same drug put on the skin would make it certain under the tongue, which neither row says. A report compared with every label whose families overlap its own is never matched to a label of a form it cannot be.

## Evidence

The table was made by two independent runs of one written instruction (`mappings/faers/route/review/instructions.md`), joined by taking the union of the families each run gave a value, then checked by a reviewer, whose corrections are applied only where accepted (`review/corrections.csv`): a family is added to a value only when FAERS has real cases of it, and removed only where FAERS shows it is only ever a mistake (`review/evidence-removals.csv`), never because no record shows it or because no clue tells it apart from another family; `families_table` says for each row whether both runs agreed, the union decided it, a correction did, or FAERS evidence did. Notebook `notebooks/faers/11_drug_route` counts it on the 2026Q2 release, in drug records and cases, and `notebooks/faers/10_label_flags`, section 4, counts how often the form is known well enough to pick one label.

- Of the 41.0 million suspect (PS or SS) drug records in the default case set, 34.2% end with exactly one family, 35.0% with two or more (34.8% because their values allow several or their rows give different families, 0.2% because their sources contradict each other on a row) and 30.7% with none known. The commonest answers are `injected` (22.3%), `by_mouth;under_tongue` (18.4%, FDA's `Oral` with nothing to narrow it) and `by_mouth` (8.6%).
- Reading each row alone, rather than intersecting a record's rows, changes 11,998 records (0.03%). 3,367 that were certain of a family no row gives alone (rows `Oral` and `Topical` left only `under_tongue`) now keep every family their rows allow; 2,203 whose rows gave different families are no longer contradictions. The cost: 4,312 records with one row that leaves one family and another that says less (`Subcutaneous use` with `Solution for injection` on one row, the same dose form with no route on another) are no longer certain.
- On the label step's test labels, 195 ingredients have labels that differ by form; they hold 16.8% of suspect drug records and 19.9% of cases. Where labels differ, 42.6% of their records match exactly one label and 14.7% several.
