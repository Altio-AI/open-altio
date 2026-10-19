---
rule: label-umbrella
line: A label that names an injection site reaction covers the mild reactions under it, such as pain or redness where the drug went in, but not a serious form.
values:
  severe_words:
  - failure
  - necrosis
  - necrotising
  - rupture
  - perforation
  - gangrene
  - fulminant
  - stevens-johnson
  - toxic epidermal necrolysis
  - anaphylactic
  - anaphylaxis
  - shock
  - death
  - fatal
  - life-threatening
  - abscess
  - agranulocytosis
  - purpura
  - thrombotic
  - sepsis
  - septic
enforced_in:
- src/open_altio/faers/labeldict/flags.py
- src/open_altio/faers/labeldict/flagbuild.py
- tests/faers/test_label_flags.py
- tests/faers/test_label_build.py
---
# Umbrella terms cover milder ones

A label often names a group of reactions by one word, such as an injection site reaction. Then the mild reactions in that group, like pain or redness where the drug was injected, count as on the label too. A serious form, such as one on EMA's list of important medical events, does not.

Labels often name a group of reactions by one word: an injection site reaction for pain, redness, swelling and itching where the drug was injected. MedDRA has such umbrella terms too: a preferred term (PT) whose name is the singular of the name of its high level term (HLT), the group it sits in, as the PT "Injection site reaction" is. The build finds them in the MedDRA files of the licensed part; no group is named here.

When the label keeps an umbrella PT (`rules/label-dictionary.md`), a reported PT whose primary HLT is that umbrella's HLT is `on_label` too, with `decided_by` "rule: umbrella", unless it is a serious form:

- it is on EMA's list of Important Medical Events (IME) for the MedDRA version, which EMA publishes free and the build reads from a file the user names, like MedDRA's own files; or
- its name holds one of `severe_words` (whole words, in any capitals, a hyphen read as a space), which also covers a build run without the list.

A serious form is not covered by a label that names only the umbrella: it is compared as usual and comes out `related` (`rules/label-flags.md`).

Examples, for a label that says "an injection site reaction occurred in 20% of patients":

| Reported term | Outcome |
|---|---|
| Injection site pain | on_label, by the umbrella rule |
| Injection site erythema | on_label, by the umbrella rule |
| Injection site necrosis | related: "necrosis" names a severe form |
| Immune thrombocytopenia, for a label that names "thrombocytopenia" | related: on EMA's list |

**Why:** a label that says an injection site reaction occurred in 20% of patients states the mild local reactions, and reading each one as unexpected would flood the triage view with what the label says. A severe form is not what a reader of that sentence expects, so under ICH E2A it stays unexpected.
