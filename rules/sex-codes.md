---
rule: sex-codes
line: Only F and M name a sex; FDA's other codes, such as NS (not specified) and UNK (unknown), read as not given.
values:
  known: [F, M]
always_on: true
why_locked: The explorer and the statistics read the sex it gives, and FDA's own code stays beside it as published.
enforced_in:
  - src/open_altio/faers/derive.py
  - src/open_altio/faers/duplicates.py
  - src/open_altio/explorer/statistics.py
  - tests/faers/test_demographics.py
  - tests/explorer/test_filters.py
---
# Sex: female, male or not given

A patient's sex is female (`F`) or male (`M`); every other code FDA uses means the sex is not known. The explorer's sex filter and the statistics read this sex, `sex_T`. FDA's own code stays in `sex`, as published.

`sex_T` is FDA's `sex`, trimmed and in capitals, when it is one of `known`, and empty otherwise. `NS` (not specified), `UNK` (unknown), the rare `P`, `I`, `T` and `YR`, and an empty field all leave `sex_T` empty. The first duplicate rule's key reads `sex_T`, so a sex that is not known is never compared (`dedup-default`, `not-given`); the manufacturer number rule still reads FDA's own `sex` where it checks two copies for a clash (`dup-manufacturer-number`).

**Why:** `NS` is how FDA wrote an empty field from 2013Q1 to 2014Q2, and `UNK` comes and goes with the quarter, so neither says more than "not known" (`notebooks/faers/07_demographics_units`, section 1). DiAna reads sex the same way. ICH E2B(R3) codes sex as 1 (male) and 2 (female), with null flavours for unknown, so FDA's two letters map one to one.
