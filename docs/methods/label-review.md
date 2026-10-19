# Label phrases a person coded

For anyone deciding whether to trust a label flag: how a person coded the label phrases the fixed rules could not read, and how the rules' own accuracy is measured.

FAERS reports are suspected events, not proven reactions; the flag only says whether today's label lists the event.

The charts and every number are in the notebook `notebooks/faers/10_label_flags`.

Fixed rules code each drug label's safety sections into MedDRA terms, and comparison rules turn those terms into the flags for every drug and reaction pair. Some label phrases defeat the coding rules: they read like reactions but match no term, or a rule's match may be wrong (a population, a heading, words inside a longer term). Those phrases go to one reviewer, who answers one question for each.

## How each phrase is coded

1. The question is: which MedDRA preferred term or terms does this phrase state as a reaction to this drug? The answer is a list of preferred terms, or none with one reason: it states no reaction (a heading, a table row naming none of its own, standard wording, advice on giving the drug, what the drug does not treat, or words pointing back to a reaction named elsewhere), a population or who should not take the drug, it did not happen, it was not studied or is unknown, not with this drug (placebo or another treatment only, no more often than placebo, or off the drug), or other with a note. What counts as stating a reaction, and examples of each reason, are one rule: [label-coding](https://github.com/Altio-AI/open-altio/blob/main/rules/label-coding.md).
2. An agent answers first. Any agent works, from a command line or a local model: it is handed a folder with the instructions and the phrases, and writes its answers back to a file. Every term it names is checked against MedDRA's current preferred terms. The instructions are public: `src/open_altio/labelreview/instructions/`, followed by the coding rules word for word ([label-agent](https://github.com/Altio-AI/open-altio/blob/main/rules/label-agent.md)). A phrase it leaves unanswered goes to the reviewer as "no answer", or "refused" after the retries.
3. The reviewer accepts the agent's coding or gives the right one.
4. Coded phrases are frozen. A release build reads them and never runs an agent, so a rebuild codes the same. The comparison rules then make the flags, the same way as for everything the fixed rules coded. Nobody decides a flag by hand.

## When the agent is trusted with more

Phrases are reviewed in batches. Each batch holds every label section, reason for uncertainty, label age and ranking in about the share the phrases not yet reviewed have it, from as many drugs as possible. Phrases from the indications are never reviewed: the disease a drug treats is decided by its own fixed rule ([label-review](https://github.com/Altio-AI/open-altio/blob/main/rules/label-review.md)). Batches start at 100 phrases and grow by 100. A bigger batch starts only when the reviewer coded every phrase of the last one, "other" stayed under 1%, and the agent named the same terms as the reviewer on every phrase, or said none where the reviewer did ([label-review-gates](https://github.com/Altio-AI/open-altio/blob/main/rules/label-review-gates.md)). A phrase the agent left unanswered counts as a disagreement. Any disagreement is fixed in the coding rules, a fixed rule or the instructions, and the batch is asked again.

## How accurate the fixed rules are

A seeded random sample of the flags the rules made is checked by hand, shared across the outcomes. For each outcome the release states how many were checked, how many were wrong, and the range the true error rate likely lies in ([label-rule-check](https://github.com/Altio-AI/open-altio/blob/main/rules/label-rule-check.md)).

The coded phrases tie label text to MedDRA terms, so they live only in a release's licensed part, never in the public data. The flags themselves are public.
