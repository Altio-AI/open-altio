# Mappings

Cleaning decisions that rules alone cannot make, kept as reviewed, versioned data. Code says how a value is cleaned (`src/open_altio/faers/`); this folder holds the decisions a person accepted, so a reviewed mapping changes without a code change. The rule that reads a mapping names its file.

Topics so far: `faers/countries/` (legacy AERS country names as ISO codes, and the list of ISO codes), `faers/drug_names/` (our corrections beside the DiAna dictionary), `faers/atc/` (WHO's ATC drug classes by substance, with the bridges between WHO's words and the substance dictionary's), `faers/reporter_types/` (FDA's reporter codes as E2B(R3) reporter qualifications) `faers/rxnorm/` (the dictionary's ingredient names paired with RxNorm's, and the drugs that keep their parent's code) and `faers/label_flags/` (drugs RxNorm names two ways, which the label flags read as one). The shape, one folder per source and topic:

```
mappings/<source>/<topic>/
  *.csv          what the pipeline reads: each reviewed decision, one row with its evidence
  proposals/     candidates not yet reviewed, each with its evidence; the build never reads them
  README.md      what is mapped, coverage, how it was reviewed
```

## Rules

- Every accepted row names its evidence, and the topic's README says how its rows were reviewed.
- Proposals from a model are never read by the pipeline until a person accepts them.
- Nothing licensed (MedDRA codes or hierarchy) is stored here. The one file built from a bought source is `faers/atc/classes.csv`, our table of WHO's codes and names by substance; its README carries WHO's citation, and WHO's index itself is never stored.
- A mapping that changes which cases are kept is its own release with its own changelog entry.
