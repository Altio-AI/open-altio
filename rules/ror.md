---
rule: ror
line: Compares the odds that an ingredient's cases report a reaction with the same odds among every other case; an ROR of 3 means three times the odds.
values:
  z: 1.96
  presets:
    - id: lower-bound-above-1-three-cases
      label: Lower 95% bound above 1, at least 3 cases
      source: van Puijenbroek et al. 2002, with the three cases of Evans, Waller and Davis 2001
      default: true
      when:
        - {column: ror_lower, above: 1}
        - {column: cases, at_least: 3}
    - id: lower-bound-above-1
      label: Lower 95% bound above 1
      source: van Puijenbroek et al. 2002
      when:
        - {column: ror_lower, above: 1}
always_on: true
why_locked: The statistics take no case out of the release; the thresholds you read them against are set on the Statistics tab.
enforced_in:
  - src/open_altio/stats/disproportionality.py
  - tests/stats/test_disproportionality.py
  - tests/stats/test_screen.py
---
# ROR: odds of a reaction

The odds that a case naming this ingredient reports this reaction, against the same odds for the cases that do not name it. An ROR of 3 means the reaction is three times as likely, in odds, among the ingredient's cases. The 95% interval says how far that could move by chance alone; its lower bound is what a threshold reads.

**Formula**, on the table of cases drawn in `prr`:

    ROR = (a / b) / (c / d) = ad / bc
    lower, upper = exp(ln(ROR) -/+ z sqrt(1/a + 1/b + 1/c + 1/d))

`z` is 1.96 for a 95% interval (Woolf's interval, on the log scale).

**When it is empty:** when any of a, b, c or d is 0, the ROR and its bounds are left empty, never infinity or zero. No correction, such as adding 0.5 to every cell, is made.

**Presets** (`presets`; change any number on the Statistics tab, or set your own):
- **Lower 95% bound above 1, at least 3 cases** (the default): the threshold of van Puijenbroek et al. (2002), with the floor of three cases beside it.
- **Lower 95% bound above 1**: the bound alone, as van Puijenbroek et al. (2002) state it.

**Source:** van Puijenbroek EP, Bate A, Leufkens HGM, Lindquist M, Orre R, Egberts ACG. A comparison of measures of disproportionality for signal detection in spontaneous reporting systems for adverse drug reactions. Pharmacoepidemiology and Drug Safety 2002;11:3-10.

**Not a signal:** see `prr`. Code: `src/open_altio/stats/disproportionality.py`.
