---
rule: weight-in-kg
line: Pounds and grams are read in kilograms; a weight with no unit or an unknown one, of zero, or over 635 kg is no weight.
values:
  units:
    KG: [1, 1]
    KGS: [1, 1]
    LBS: [0.45359237, 1]
    GMS: [1, 1000]
  max_kg: 635
always_on: true
why_locked: The explorer reads the weight it gives, and FDA's own weight and unit stay beside it as published.
enforced_in:
  - src/open_altio/faers/derive.py
  - tests/faers/test_demographics.py
  - tests/faers/test_derive.py
---
# Weights read in kilograms

A patient's weight is read in kilograms from FDA's `wt` and its unit, `wt_cod`. A weight with no unit, in a unit FDA does not define, of zero or over 635 kg is no weight. FDA's `wt` and `wt_cod` stay as published.

`wt_kg_T` is `wt` times the first number of its unit in `units`, divided by the second: a pound is exactly 0.45359237 kg, the international pound, and a gram a thousandth of a kilogram. `KGS`, on a handful of cases, is kilograms. A weight with no unit or another unit, of zero, or over `max_kg` once converted, is no weight. The number is read as `age-in-years` reads one, so `.9` is 0.9.

**Why:** weights with no unit are a mix of kilograms and pounds (their median sits between the two), so neither reading is safe; the other units are typing slips. Above 635 kg, the heaviest person on record, every weight is an error, such as a stray digit or a misplaced decimal point. A weight of zero is no weight. All of it is in `notebooks/faers/07_demographics_units`, section 6.
