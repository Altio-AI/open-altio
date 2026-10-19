For anyone who runs the label flags on their own machine with their own MedDRA licence.

# Make the groups file for the label flags

The label flags set some reported terms aside and never call a pair possibly listed through a catch-all group. Which MedDRA groups those are is MedDRA content, so Open Altio does not ship them: you make a small file from your own MedDRA release and give it to the labels step. [Rule label-groups](../reference/rules.md) says what it holds and how it is checked.

## What goes in it

One JSON file with three keys, each a list of MedDRA group names or codes from your release:

```json
{
  "not_a_medical_event": ["<group>", "<group>"],
  "procedure": ["<body-system class>"],
  "catch_all": ["<high level term>", "<high level term>"]
}
```

- `not_a_medical_event`: the groups whose terms name no health effect, at any level: product problems, medication and product use errors, off label use and misuse, overdoses and underdoses, exposure and its routes, and the social circumstances that are not health effects (crimes and their victims, money, work, schooling, housing). Look them up in your release's `soc.asc`, `hlgt.asc` and `hlt.asc`.
- `procedure`: the one body-system class MedDRA keeps for surgical and medical procedures (`soc.asc`).
- `catch_all`: high level terms only: every one MedDRA marks as not elsewhere classified in `hlt.asc`, and its general signs and symptoms, except the seven that each hold one family of close terms (the kinds of rash, hepatitis, arthritis, oedema, sepsis, heart failure and seizure).

Keep the file with your MedDRA files, outside the repository. Never commit it or publish it.

## Use it

```sh
python -m open_altio.faers labels --release releases/2026Q2 --groups ~/meddra/label_groups.json
```

The step checks every name or code against the release's MedDRA version and refuses the file, saying why, when a key is missing or extra, a value is not a list, or a group is not in that version. A good file is written into the release's licensed part beside the version's tables, and rebuilding the same MedDRA version keeps it. Make a new file when you move to a new MedDRA version, because groups can be renamed or moved.
