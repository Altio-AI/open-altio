---
rule: dose-strength
line: The Dose line shows the share of reports giving a dose whose dose as written reads to the highest strength, the one passed or else the highest that enough of them write.
placeholder: true
values:
  min_share: 0.05
  units: [mg, mcg, g, mL, mg/mL, mcg/mL, mg/5 mL, units]
  measures:
    mass: {mg: 1, mcg: 0.001, g: 1000}
    volume: {mL: 1}
    concentration: {mg/mL: 1, mcg/mL: 0.001, mg/5 mL: 0.2}
    units: {units: 1}
  spellings:
    milligram: mg
    milligrams: mg
    microgram: mcg
    micrograms: mcg
    "µg": mcg
    ug: mcg
    gram: g
    grams: g
    milliliter: mL
    milliliters: mL
    millilitre: mL
    millilitres: mL
    unit: units
    international units: units
    international unit: units
    iu: units
enforced_in:
  - src/open_altio/explorer/breakdowns/fields.py
  - src/open_altio/explorer/breakdowns/lines.py
  - tests/explorer/test_breakdowns.py
---
# Dose at the highest strength

An event's Dose line (rule `breakdown-lines`) shows the share of the reports giving a dose whose dose as written (FDA's `dose_vbm`) reads to the highest strength. A question may pass the product's strengths (`strength`, repeated, such as `40 mg`); the line takes the highest of them. With none passed, it takes the highest strength written in at least `min_share` of the reports giving a dose, before and in the window together.

- `units`: the units a strength is read in. A dose reads to a strength when it starts with a number and one of these units, whatever its capitals and spaces: `320 MG, QD` and `0.32 G` are both 320 mg. A number written with a comma, a unit not listed, and a unit followed by more of one, such as `mg/kg`, read to no strength.
- `measures`: the units of each measure, each with its size against the measure's unit of size 1, so strengths of one measure compare: 1 g is 1000 mg, and 250 mg/5 mL is 50 mg/mL. Each unit in `units` is in one measure, and each unit in a measure is in `units`; a rule where they differ refuses every question, naming the units.
- `spellings`: other ways a unit is written in FDA's files, each read as the unit it names.
- `min_share`: with no strength passed, a strength must be read from at least this share of the reports giving a dose to be taken.

Strengths are compared within what they measure (`measures`): a mass, a volume, a concentration or units. Strengths passed in different measures are refused. With none passed and the common strengths in several measures, the highest is taken in the measure most of those reports are in. A strength passed that cannot be read is refused, naming it. With no report giving a dose in a period, the share there is null, never 0.

**Not yet decided.** These values were chosen before their evidence. Notebook `notebooks/faers/16_breakdowns` will decide them, by showing on a real release how many doses each unit and spelling reads, and how often the highest strength written is the label's highest.

**Why:** a rise in reports at a product's highest strength can show a harm that grows with the dose. Reading the dose as the report writes it keeps the count checkable against FDA's files.
