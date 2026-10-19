---
rule: label-procedure
line: Terms that name what was done to the patient, such as a liver transplant or dialysis, are flagged as procedures rather than judged against the label, and stay in view.
values:
  groups_key: procedure
enforced_in:
- src/open_altio/faers/labeldict/flagbuild.py
- src/open_altio/faers/labeldict/groups.py
- tests/faers/test_label_build.py
---
# Procedures, not reactions

Some report terms name what was done to the patient, such as a liver transplant or dialysis. Labels list reactions, not their treatment, so these are flagged as procedures instead of being judged against the label. They stay in view, because a procedure can be the only trace of serious harm.

Some reaction terms in FAERS name what was done to the patient, not what happened to them: a nasal polypectomy, a liver transplant, dialysis. When the reported term's current preferred term (PT) has its primary path in the body-system class MedDRA keeps for procedures, named in the licensed part under `groups_key` in `label_groups.json` (MedDRA's group names are MedDRA content, so they are never in this repository), the pair's outcome is `procedure` (shown as "Not compared", a procedure), decided first, before the label is compared (`rules/label-flags.md`), and read as unexpected (`expectedness` in `rules/label-flags.md`). A term `rules/label-not-a-medical-event.md` names itself (self-medication, and the three treatment-pause terms) is not a medical event, not a procedure.

A procedure is not compared with the label, because labels name reactions, not the treatment of them. It is not set aside either: a procedure can be the only trace of serious harm in a report (a transplant after liver failure), so it counts as unexpected, as a reaction does until a label lists it, and the triage view shows procedures by default.

Examples:

| Reported term | Outcome |
|---|---|
| Liver transplant | procedure |
| Dialysis | procedure |
| Hepatic failure | compared with the label as usual |

**Why:** a procedure on the label's terms would almost always come out "not on the label", which reads as an unexpected reaction when it is the care given for one. Flagging it apart keeps it visible without counting it as a reaction.
