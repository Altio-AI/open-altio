---
rule: label-groups
line: The groups three label rules use, such as product problems or procedures, come from a file you make from your own copy of MedDRA, the licensed drug-safety dictionary.
values:
  catch_all_hlt_only: true
enforced_in:
- src/open_altio/faers/labeldict/groups.py
- tests/faers/test_label_groups.py
---
# Groups the label rules read

Three label rules name MedDRA groups: which hold terms that are no medical event, which body-system class holds procedures, and which are catch-alls that never make a pair related. MedDRA's group names are MedDRA content, so they live in a file you make from your own MedDRA release, never in this repository, and the labels step reads it from where you say.

`python -m open_altio.faers labels --release <release> --groups <file>` checks the file against the release's MedDRA version and writes it into the release's licensed part, beside that version's tables (`licensed/meddra/<version>/label_groups.json`), where the flags read it. Rebuilding the same MedDRA version keeps it. A release without it gets no flags, and the step says why.

The file is one JSON mapping with exactly three keys, each the key a rule names, and each a list of MedDRA group names or codes:

- the `groups_key` of `rules/label-not-a-medical-event.md`: the groups whose terms name no health effect, at any level (a body-system class, a group term or a high level term): product problems, medication and product use errors, off label use and misuse, overdoses and underdoses, exposure and its routes, and the social circumstances that are not health effects (crimes and their victims, money, work, schooling, housing);
- the `groups_key` of `rules/label-procedure.md`: the body-system class MedDRA keeps for surgical and medical procedures;
- the `catch_all_key` of `rules/label-flags.md`: the catch-all groups, high level terms only with `catch_all_hlt_only`, the level related reads: every high level term MedDRA marks as not elsewhere classified, and its general signs and symptoms, except the seven that each hold one family of close terms (the kinds of rash, hepatitis, arthritis, oedema, sepsis, heart failure and seizure).

The step refuses a file with any other keys, a value that is not a list of names or codes, or a name or code the release's MedDRA version does not hold, and says which. It writes each group as MedDRA names it, so a code in the file becomes its name.

**Why:** the flags must be rebuilt from one command, with nothing copied by hand, and MedDRA's names may not be published. A file you make from your own licence, checked on every build, does both. The evidence is in notebook `notebooks/faers/10_label_flags`: the accuracy checks (section 7) and its closing section, which sets out what was decided.
