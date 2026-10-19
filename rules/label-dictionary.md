---
rule: label-dictionary
line: Each label's safety sections are read once for every reaction they name, in the words of MedDRA, the drug-safety dictionary, however the label spells it; the next rules decide which it really lists.
values:
  sections:
  - boxed_warning
  - warnings_and_precautions
  - warnings
  - precautions
  - adverse_reactions
  - contraindications
  sentence_ends:
  - .
  - ;
  - '!'
  - '?'
  - •
  not_sentence_ends:
  - e.g.
  - i.e.
  - vs.
  - approx.
  capitals_match_capitals: true
  shortest_name: 2
  spellings:
  - - ae
    - e
  - - oe
    - e
  - - sulph
    - sulf
  - - tumour
    - tumor
  - - colour
    - color
  - - behaviour
    - behavior
  - - odour
    - odor
  - - labour
    - labor
  plural_last_word: true
  prose_order:
    increased:
    - increased
    - elevated
    - raised
    - high
    - increase in
    - increases in
    - increase of
    - elevation of
    - elevations of
    - elevation in
    - elevations in
    - rise in
    decreased:
    - decreased
    - reduced
    - low
    - decrease in
    - decreases in
    - decrease of
    - reduction in
    - reductions in
    - reduction of
    - fall in
  site_lists:
    read: true
    sites: [injection, infusion, application, administration, implant, implantation, catheter,
            insertion, instillation, vaccination, inoculation, incision]
    heads: [reaction, reactions, disorder, disorders, event, events, complication, complications,
            symptom, symptoms, irritation, finding, findings]
    starts: ["(", ":", including, includes, included, such as, described as, manifested by,
             manifested as, consisting of, characterized by, e.g., i.e., reported as,
             presenting as]
    ends: [";", ".", "|"]
    not_after: [conditions]
    reach_words: 6
  boilerplate_names:
  - adverse reaction
  - adverse event
  - adverse drug reaction
  - adverse experience
  - side effect
  body_system_headings: true
  heading_words: [Nervous]
  cross_reference_words:
  - see
  list_words:
  - and
  - or
  list_gap_words: 2
  scope_ends:
  - but
  - however
  - although
  - though
  - except
  - whereas
  - while
  everyday_names:
    lead:
    - to
    nervous:
    - system
settable:
  plural_last_word:
    label: Read a plural as the term (rashes as rash)
enforced_in:
- src/open_altio/faers/labeldict/text.py
- src/open_altio/faers/labeldict/terms.py
- src/open_altio/faers/labeldict/sites.py
- src/open_altio/faers/labeldict/scope.py
- src/open_altio/faers/labeldict/coding.py
- tests/faers/test_label_terms.py
- tests/faers/test_label_coding.py
---
# Reactions a label names

We read the safety sections of each drug's FDA label once and find every reaction it names, in MedDRA's own words and synonyms. A reaction counts however the label spells it, and a specific reaction is never also counted as a broader one. The rules after this one decide which of these the label really lists.

The label step reads the safety sections of each FDA label (`sections`, from `label_sections_T`) and finds every current MedDRA lowest level term (LLT, `llt_currency` Y) named in them. Each hit gives that LLT's preferred term (PT). The result is the label's dictionary: the PTs this label names, each with the sentence that names it. It lives in the licensed part of a release (MedDRA's licensed part of the release), because which PT a phrase codes to is MedDRA content.

How text is matched:

- **Sentences.** Text is cut into sentences after any of `sentence_ends` followed by a space, except after one of `not_sentence_ends`. A table row is one sentence. A match never crosses a sentence.
- **Words.** A word is a run of letters and digits, with any hyphen inside it, so "extra-pulmonary tuberculosis" never holds "pulmonary tuberculosis". Apostrophes count as spaces. Every other character that is not a letter, a digit or a space (commas, brackets, slashes, table cell borders, plus signs, per cent signs) is a mark a match cannot cross unless the LLT name holds the same mark, so "Mg++" never matches the unit "mg". A name with fewer than `shortest_name` letters and digits ("K") is never matched. Accents are ignored (Sjogren matches Sjögren).
- **Spelling.** MedDRA spells the British way and US labels the American way. Before comparing, both sides are spelt one way by replacing each pair of `spellings` in turn ("haemorrhage" and "hemorrhage" both become "hemorrhage", "gynaecomastia" and "gynecomastia" meet).
- **Letter case.** Matching ignores capitals, except that an LLT name MedDRA writes all in capitals (an abbreviation such as ARF or ADD) matches only text written in capitals (`capitals_match_capitals`), so the word "add" is never read as a disorder.
- **Other forms of a name.** With `plural_last_word`, each name also matches with its last word in the plural ("rashes", "infections", "seizures"). A name ending in a word of `prose_order` also matches in the order prose uses, with that word first and any of its listed forms, a word or a phrase: "ALT increased" also matches "increased ALT", "elevated ALT" and "elevation of ALT", "Platelet count decreased" also matches "decreased platelet count", "low platelet counts" and "a decrease in platelet count". A name as MedDRA writes it always wins over another name's other form.
- **Longest first.** Reading left to right, the longest LLT name that starts at a word wins, and matching resumes after it: "acute renal failure" is one hit (its PT is the acute one), never "renal failure" as well. When two current LLTs have the same words, the one that is the PT itself wins, then the lowest code.
- **Boilerplate.** The general words for side effects (`boilerplate_names`, "adverse reaction rates observed in clinical trials") are LLT names too, but name no reaction, so a hit on one is kept off.
- **Headings.** With `body_system_headings`, a hit inside one of MedDRA's body-system class names, in the singular or plural (a table heading, or a footnote that names the class), is a heading, not a reaction, and is kept off. The names are read from the licensed part. A line still uncertain whose matched text is exactly one of `heading_words` ("Nervous:" opening a list of reactions) is a heading too.
- **Cross-references.** A hit inside brackets that open with one of `cross_reference_words` ("[see Warnings and Precautions (5.1)]") names another part of the label, not a reaction, and is kept off.
- **A site governing a list.** With `site_lists`, a site phrase (one of `sites` followed by "site", then any of `heads`: "injection site reactions", "infusion site events") that opens a list, with one of `starts` at most `reach_words` words on ("(", "including", "such as", "manifested by", ":"), governs the terms of that list up to its closing bracket, or outside brackets to one of `ends` or the end of the sentence. Each such term names a reaction at that site, so it codes to the site's own term ("injection site reactions (erythema, itching)": Injection site erythema, Injection site pruritus), else to the site's umbrella term (Injection site reaction); a term with neither is kept off. A term that already names a site is read as written. "Administration site conditions", a body-system class, is no site phrase (`not_after`).
- **Everyday words.** A few LLT names are also everyday English (`everyday_names`). A hit on one of them followed by a word that shows the everyday sense is kept off the label ("may lead to liver injury": "lead" is a verb, not blood lead; "nervous system" is not nervousness). Any other hit on one of them is uncertain.

Examples:

| Text | Hit | Why |
|---|---|---|
| "Acute renal failure occurred in 2%." | Acute renal failure | longest name wins over renal failure |
| "Kidney failure was reported." | Kidney failure, PT Renal failure | an LLT gives its PT |
| "ARF was more common at 20 mg." | ARF | written in capitals, as MedDRA writes it |
| "Add one tablet." | none | "add" is not in capitals |
| "Gynecomastia has been reported." | Gynecomastia, PT Gynaecomastia | one spelling |
| "Elevated ALT was seen in 3%." | ALT increased | prose order |
| "decrease in hemoglobin" | Hemoglobin decreased | prose order, a phrase first |
| "injection site reactions (erythema, itching, pain)" | Injection site erythema, Injection site pruritus, Injection site pain | a site governs the list |
| "General disorders and administration site conditions: asthenia" | Asthenia | no site phrase |
| "extra-pulmonary tuberculosis" | none for pulmonary tuberculosis | the hyphen keeps one word |
| "adverse reaction rates observed in clinical trials" | Adverse reaction, kept off | boilerplate |
| "may lead to hospitalization" | Lead, kept off | "lead to" is the everyday sense |

Each hit is then kept or kept off by `rules/label-negation.md`, `rules/label-population.md` and `rules/label-table-rows.md`. Those rules read lists the same way: after a term, a comma or one of `list_words` (with at most `list_gap_words` other words before the next term) continues the list; one of `scope_ends`, a semicolon, a colon or the end of the sentence ends it.

A hit no rule keeps off is kept, with `rule` naming this file. Anything the rules cannot settle is uncertain, never guessed: it goes to `label_uncertain.jsonl` for a person to decide (`rules/label-flags.md`).

**Why:** a label is coded once, by fixed rules anyone can read and rerun, so every build gives the same dictionary and nothing depends on a model at build time. Matching LLT names rather than only PT names finds a reaction however the label words it, and the longest match keeps a specific reaction from also counting as its broader one. The evidence is in notebook `notebooks/faers/10_label_flags`: the label lines the rules could not read (section 3) and how accurate the coding is (section 7).
