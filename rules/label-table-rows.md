---
rule: label-table-rows
line: A reaction in a label's table that only the placebo or comparison group had is not the drug's, so it is not on the label; a row that does not line up goes to a person.
values:
  comparator_words:
  - placebo
  - vehicle
  - comparator
  - control
  - sham
  - usual care
  - standard of care
  zero_marks:
  - '0'
  - '-'
  - "\u2013"
  - "\u2014"
  - none
  unnamed_row_sections:
  - adverse_reactions
enforced_in:
- src/open_altio/faers/labeldict/tables.py
- tests/faers/test_label_coding.py
---
# Reactions only placebo had

Labels list reactions in tables, one column per treatment group. When only the placebo or comparator group had a reaction, it is not a reaction of the drug, so it does not put the reaction on the label. A row we cannot line up with its columns is left for a person.

Labels list reactions in tables, one row per reaction, one column per treatment arm. `label_sections_T` gives each row as one line of text with its cells joined by " | ". Consecutive rows of one section are one table.

A row is a header when one of its cells after the first names a comparator (`comparator_words`, whole words, in any capitals). The columns of those cells are the comparator's; every other column is the drug's. A later header row replaces the columns from then on. A term in a header row names an arm, not a reaction, and is kept off.

A row with no value in any cell after the first (a heading, a caption or a footnote) is read as a sentence, by the rules for text.

For a term in a row of a table with a header:

- Every value above zero keeps the term, however the row lines up: whichever columns are the drug's, they have it.
- Otherwise the row is read only when it has as many cells as the header; if not, it is uncertain.
- A cell's value is its first number ("12 (3%)" is 12, "<1" counts as more than zero), or zero for one of `zero_marks`. Other cells hold no value.
- A value above zero in a drug column keeps the term.
- Every drug value zero and a comparator value above zero keeps it off: only placebo or the comparator had it.
- Anything else (no drug value, or every value zero) is uncertain.

In a table with no comparator header every column is the drug's, so a term in any row is kept.

A row of a table with a comparator header, in one of `unnamed_row_sections`, that has values but no term anywhere, and whose first cell holds a word, is an uncertain item with no term: the label lists a reaction the dictionary cannot name.

Examples, under the header " | Drug 10 mg | Placebo":

| Row | Kept |
|---|---|
| "Nausea \| 12 (3%) \| 4 (1%)" | kept |
| "Hepatitis \| 0 \| 2 (0.5%)" | off: only placebo |
| "Headache \| <1 \| 0" | kept |
| "Vomiting \| 0 \| 0" | uncertain |
| "Haemorrhage \| 3%" | kept: every value is above zero |
| "Haemorrhage \| 3% \| 0 \| 1%" | uncertain: four cells under a three-cell header, and a zero |
| "Injection site pain \| 20% \| 14%" (no LLT matches) | an uncertain item with no term |

**Why:** a reaction that only the placebo or comparator arm had is not a reaction of the drug, though its name sits in the drug's label. Tables flattened to text cannot always be read cell by cell, so a row that does not line up with its header goes to a person rather than being guessed. The evidence is in notebook `notebooks/faers/10_label_flags`, its closing section, which sets out what was decided and why.
