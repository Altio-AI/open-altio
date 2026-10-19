---
rule: label-negation
line: "'No cases of hepatitis were reported' does not put hepatitis on the label; a sentence we cannot read for sure goes to a person."
values:
  before:
  - not indicated for
  - not indicated in
  - no cases of
  - no reports of
  - no evidence of
  - no instances of
  - no episodes of
  - no occurrence of
  - no increase in
  - no increased risk of
  after:
  - was not observed
  - were not observed
  - has not been observed
  - have not been observed
  - was not seen
  - were not seen
  - did not occur
  - has not occurred
  - have not occurred
  - was not reported
  - were not reported
  - has not been reported
  - have not been reported
  window_words: 4
  bare_comma_items: kept_off
  unread_words:
  - 'no'
  - not
  - never
  - none
  - neither
  - nor
  - without
  unread_window_words: 3
  unstated_negation:
    words: ["no", not, without, never, none, neither, nor, cannot]
    contraction: "n't"
    chars: 70
  unstated_either_way: with or without
  unstated_unless: [reported, occurred, developed, observed, incidence, events, "%", increased,
                    cases, seen]
  exclusion:
  - does not include
  - do not include
  - did not include
  - not including
  - excluding
  - excludes
  - excl
  exclusion_ends: [";", ".", "|", ":"]
  exclusion_clause_words: [was, were, is, are, occurred, occurring, reported, that, which, there,
                           compared, respectively]
settable:
  window_words:
    label: Words allowed between the phrase and the reaction
    minimum: 0
enforced_in:
- src/open_altio/faers/labeldict/scope.py
- tests/faers/test_label_coding.py
---
# Reactions the label rules out

Labels often say what was looked for and not found: "no cases of hepatitis were reported". Such a sentence does not list the reaction, so it does not put the reaction on the label. A sentence we cannot read for sure is left for a person to decide.

A hit is kept off the label (`kept` false, `rule` naming this file) when the same sentence says the reaction did not happen:

- **A phrase before it.** One of `before` is followed, within `window_words` words, by the term, and by every term listed with it (`rules/label-dictionary.md` says how a list is read). Here a term after a bare comma is also kept off (`bare_comma_items`), because "no cases of hepatitis, jaundice may occur" is not English.
- **A phrase after it.** The term comes at most `window_words` words before one of `after`, and so do the terms listed before it.

**An exclusion clause.** A term after one of `exclusion` ("Dizziness (excluding vertigo)", "Does not include injection site erythema, itching, pain and swelling") is kept off, up to the bracket that closes the clause, one of `exclusion_ends`, or a comma followed by one of `exclusion_clause_words` ("excluding akathisia, was 6%"). The term the clause qualifies (dizziness) stays on the label, and a term kept off here never cancels another line that keeps it.

A word of `unread_words` no phrase above reads, within `unread_window_words` words before a hit that no rule keeps off, makes the hit uncertain: the label may be saying it did not happen, in words the rules do not know.

**A negation no phrase reads.** A line that is still uncertain, and whose term has one of `unstated_negation`'s `words` (or a word ending in its `contraction`) within `chars` characters before it, states nothing and is kept off (rule label-population gives the same for a patient's condition). Two things stop that: the sentence says "with or without" (`unstated_either_way`), or holds any of `unstated_unless`, which say the event was seen (reported, occurred, incidence, a percentage, increased, cases). "There were no deaths in the trial" is such a line.

Examples:

| Sentence | Term | Kept |
|---|---|---|
| "No cases of hepatitis were reported." | hepatitis | off |
| "No cases of hepatitis, jaundice or liver failure were reported." | each of the three | off |
| "Hepatitis was not observed." | hepatitis | off |
| "Nausea was common, but hepatitis was not observed." | nausea | kept: "but" ends the list |
| "Nausea was common, hepatitis was not observed." | nausea | kept: "common" is not a term, so the list stops |
| "No cases of hepatitis were reported, and nausea was common." | nausea | kept: "were" is not a term, so the list stops |
| "Patients did not report hepatitis." | hepatitis | uncertain: "not" is not in a known phrase |
| "The dose is not confused with the other strength." | confused | off: a negation before it that no phrase reads, and nothing says it was seen |

**Why:** labels often say what was looked for and not found. Reading such a sentence as naming the reaction would put on the label a reaction the label rules out, and a report of it would wrongly count as expected. The evidence is in notebook `notebooks/faers/10_label_flags`: the accuracy checks (section 7) and its closing section, which sets out what was decided.
