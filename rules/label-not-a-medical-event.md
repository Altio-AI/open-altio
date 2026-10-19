---
rule: label-not-a-medical-event
line: Terms such as drug ineffective, off-label use, a faulty product or exposure name no health effect, so they are set aside, not judged against the label; a real reaction gets its own flag.
values:
  pts:
  - No adverse event
  - Drug ineffective
  - Drug ineffective for unapproved indication
  - Product ineffective
  - Product ineffective for unapproved use
  - Therapeutic response decreased
  - Drug effect incomplete
  - Drug effect less than expected
  - Treatment failure
  - Therapy non-responder
  - Therapy partial responder
  - Loss of therapeutic response
  - Therapeutic product effect incomplete
  - Therapeutic product effect decreased
  - Therapeutic product effect delayed
  - Therapeutic response shortened
  - Drug level decreased
  - Self-medication
  - Therapy interrupted
  - Therapy cessation
  - Therapy change
  - Product used for unknown indication
  compared_pts:
  - Device expulsion
  - Drug resistance
  - Vaccination failure
  groups_key: not_a_medical_event
enforced_in:
- src/open_altio/faers/labeldict/flagbuild.py
- src/open_altio/faers/labeldict/groups.py
- tests/faers/test_label_build.py
---
# Not a health effect

Some report terms name no health effect: the drug did not work, it was used off label or by mistake, the product was faulty, or someone was exposed to it. These are set aside rather than judged against the label. A real reaction in such a report is its own term and gets its own flag.

Some reaction terms in FAERS name no health effect: the drug did not work, it was used off label or wrongly, the product was faulty, or someone was exposed to it. They cannot be on or off a label as a reaction, so the pair's outcome is `not_a_medical_event` (shown as "Not a medical event"), decided before the label is compared (`rules/label-flags.md`) and set aside from expectedness. A real reaction in such a case is reported as its own term and gets its own flag.

A reported term is not a medical event when its current preferred term (PT) is not one of `compared_pts` and:

- is one of `pts`, written as FDA publishes them (lack of effect, no adverse event, self-medication, a treatment paused, stopped or changed); a term named here is not a medical event even where MedDRA files it under procedures; or
- sits, on its primary path in MedDRA, under one of the groups the licensed part lists under `groups_key` in `label_groups.json`, beside the MedDRA version's tables: a body-system class, a group term or a high level term. MedDRA's group names are MedDRA content, so they are kept there and never in this repository. The groups hold product problems, medication and product use errors, off label use and misuse, overdoses and underdoses, exposure and its routes ("Exposure via skin contact", "Accidental exposure to product"), and the social circumstances that are not health effects: crimes and their victims, money, work, schooling and housing ("Theft", "Unemployment").

Death (sudden death, death unexplained and the like) and the disease getting worse (condition aggravated, disease progression) are health effects and are compared with the label like any other event: they usually come out not on the label and stay in triage, because a cluster of deaths can be a real signal.

Three terms the groups or lists would set aside are real effects and are compared with the label like any other, on the exact PT alone (`compared_pts`): a device that came out, a germ or disease that resists the drug, and a vaccine that did not protect. The label either keeps the PT (Listed) or does not (Not listed); a neighbour in the same group never makes the pair Possibly listed, because the group holds such unlike terms as drug tolerance and treatment failure. "Product used for unknown indication" says only that no indication was recorded, so it is on `pts`.

Groups that also hold health effects are left out on purpose: poisoning and harm from chemicals, conditions of a foetus or newborn after exposure, the effects of stopping a drug, and the responses to treatment other than lack of effect ("paradoxical drug reaction" stays a reaction).

Examples:

| Reported term | Outcome |
|---|---|
| Drug ineffective | not_a_medical_event: on `pts` |
| Off label use | not_a_medical_event: under a listed group |
| Exposure via skin contact | not_a_medical_event: under a listed group |
| Theft | not_a_medical_event: under a listed group |
| Self-medication | not_a_medical_event: on `pts`, though MedDRA files it under procedures |
| Therapy interrupted, Therapy cessation, Therapy change | not_a_medical_event: on `pts`, though MedDRA files them under procedures; every other procedure stays a procedure |
| Drug resistance, Device expulsion, Vaccination failure | Listed when the label keeps the PT, else Not listed: exact PT only |
| Paradoxical drug reaction | compared with the label as usual |
| Death | compared with the label as usual |
| Condition aggravated | compared with the label as usual |

**Why:** lack of effect, product use errors and exposure terms were a large share of the terms the label comparison could not place, and they are not reactions to judge against a label. Setting them aside by a fixed list keeps every flag reproducible. The list and groups are a proposal to approve. The evidence is in notebook `notebooks/faers/10_label_flags`: the accuracy checks (section 7) and its closing section, which sets out what was decided.
