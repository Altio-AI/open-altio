---
rule: label-sections
line: The sections on harm (boxed warning, warnings, adverse reactions, who must not take it) and on what the drug is for are found by FDA's section codes, never by their headings.
values:
  sections:
    34066-1: boxed_warning
    43685-7: warnings_and_precautions
    34071-1: warnings
    42232-9: precautions
    34084-4: adverse_reactions
    34070-3: contraindications
    34067-9: indications
  unclassified_section: 42229-5
  cell_separator: " | "
enforced_in:
  - src/open_altio/faers/labels/build.py
  - src/open_altio/faers/labels/update.py
  - tests/faers/test_labels.py
---
# A label's safety sections

From each label rule label-choice picks, one per route family, the labels step reads the sections that say what harm a drug can do, and what it is used for. A section is found by the LOINC code FDA's format gives it (`sections`), never by its heading, so a label from any company reads the same way:

| Section | LOINC | Found in |
|---|---|---|
| `boxed_warning` | 34066-1 | Any label with a boxed warning |
| `warnings_and_precautions` | 43685-7 | Labels in FDA's current format |
| `warnings` | 34071-1 | Labels in the older format |
| `precautions` | 42232-9 | Labels in the older format |
| `adverse_reactions` | 34084-4 | Every format |
| `contraindications` | 34070-3 | Every format |
| `indications` | 34067-9 | Every format: what the drug treats, so a later step can tell a reaction that is the disease treated from a drug reaction |

A section keeps its subsections, whatever their own codes (an old-format Precautions section holds Drug Interactions, Pregnancy and others). A subsection with a wanted code of its own belongs to that code instead, so no line is counted twice.

## How a section becomes lines

`label_sections_T` holds one row per line, numbered in label order (`ordinal_T`):

- a section or subsection heading, a paragraph and a list item (with its bullet or number) are each one line, with spaces collapsed;
- a table caption is one line, then each table row is one line, its cells joined by `cell_separator`, with `is_table_row_T` true, so a later step can tell rows of a table from prose. Header rows come first, then body rows, then the footnote rows, as the table is printed. An empty cell stays empty, so every row splits into all its cells;
- pictures are left out, and so is the short Highlights copy a full section repeats, which would count every warning twice.

The words are FDA's, unchanged apart from spacing.

## What is not guessed

Some labels file their sections under the code for an unclassified section (`unclassified_section`) instead of the section's own, and some carry a section's code with nothing in it. Their headings may say Warnings or Adverse Reactions, but the code does not, so no section is read from them. Rule label-choice prefers a label whose safety sections hold words; the build counts the labels that have none, in the whole release and among those chosen (where the ingredient has no other), and how many of the chosen file sections as unclassified, so they can be looked at by hand.

**Why:** a later step matches label text to reaction terms and needs to know which section a line came from and whether it is a row of an incidence table; a reaction found only under Indications is the disease the drug treats, not a drug reaction. Reading by code is exact; reading by heading would guess.

**Source:** FDA's SPL standard and its section codes (fda.gov, "Structured Product Labeling resources"; LOINC document section codes).
