---
rule: rechallenge-correction
line: Dechallenge and rechallenge are read through Not given before an event's shares are counted, and corrected no further until their notebook decides.
placeholder: true
values:
  correction: none
enforced_in:
  - src/open_altio/explorer/breakdowns/fields.py
  - tests/explorer/test_breakdowns.py
---
# Dechallenge and rechallenge, read before comparing

An event's Dechallenge and Rechallenge lines read FDA's `dechal` and `rechal` through rule `not-given` before any share is counted: FDA's U is Not given everywhere, and a rechallenge of D in FDA's files from 2012q4 to 2015q3, the filler those quarters carry, is Not given too. This rule holds any further correction of the two fields. Today there is none.

- `correction`: `none`, the only value the explorer reads: the two fields are counted as rule `not-given` reads them, and nothing more. Any other value refuses the question, naming this rule.

FDA's `dechal` and `rechal` stay as published. A correction, once decided, is a new column ending in `_T`, and ships as its own data release with the counts before and after.

**Not yet decided.** Notebook `notebooks/faers/16_breakdowns` will decide whether any correction is kept. No swap of the two columns was found in the quarters of the filler: there, rechallenge is filled on almost every drug record, mostly with D, while dechallenge keeps the shares it had before them.

**Why:** a filler read as an answer would make every event's rechallenge look changed in those quarters.
