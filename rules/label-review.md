---
rule: label-review
values:
  first_batch_size: 100
  batch_size_step: 100
  blind_redo_items: 50
  pattern_min_items: 3
  pattern_opening_words: 3
  page_host: 127.0.0.1
  page_port: 8537
  not_reviewed_sections: [indications]
settable:
  first_batch_size:
    label: First batch (items)
    minimum: 1
  batch_size_step:
    label: Each later batch adds (items)
    minimum: 0
enforced_in:
  - src/open_altio/labelreview/batches.py
  - src/open_altio/labelreview/redo.py
  - src/open_altio/labelreview/patterns.py
  - src/open_altio/labelreview/__main__.py
  - src/open_altio/labelreview/page.py
  - tests/labelreview/test_batches.py
  - tests/labelreview/test_redo.py
---
# Label review batches

The label phrases the label rules leave uncertain (rule label-coding) are reviewed in batches. The first batch holds `first_batch_size` items and each batch after it `batch_size_step` more (100, 200, 300 and so on). A batch is picked as a mix of the items not yet reviewed: each label section, each reason the rules were unsure, older and newer labels, and higher and lower ranking items (when the items carry a ranking) in about the share those items have, every one at least once, and within that as many different drugs as possible. Older and newer, and higher and lower, split at the middle of the items not yet reviewed.

Phrases from the sections in `not_reviewed_sections` never reach review. The indications name the disease the drug treats, which a fixed rule decides from them, so there is nothing to code.

The next batch starts only when the current one passes its gates (rule label-review-gates). Otherwise starting it is refused, with the reasons.

An agent codes each item, file in and file out (rule label-agent). On the review page the reviewer sees one item at a time, or the whole batch as a list: the drug, the label section and date, the phrase, the rules' guess, and the agent's coding with its evidence and reason, or "no answer" or "refused". Accept takes the agent's coding. Reject, the only choice for "no answer" and "refused", takes the reviewer's own: the preferred terms the phrase states, each checked against MedDRA's current preferred terms, or one reason for none. A note is optional, except for the reason "other". Each decision is written with who made it and when. The page runs on the reviewer's own machine, at `page_host` and `page_port`.

After each batch, the tool lists repeated patterns among the decided items: the same reason for uncertainty, the same section, the same rules' guess or the same first `pattern_opening_words` words of the phrase (enough to catch "contraindicated in patients" or "no cases of"), coded the same way at least `pattern_min_items` times, with no decided item coded otherwise. A person turns a pattern into a fixed rule; the tool only points at candidates.

Once, the reviewer redoes `blind_redo_items` earlier items without seeing their first answers or the agent's codings, and the tool lists where the codings differ, and apart from them where only the reason for none differs, so the coding rules can be tightened.

Decided items are frozen into `label_codings_frozen.jsonl`, which the label step reads, so a rebuild codes the same and never runs an agent. The comparison rules, not the reviewer, turn the coded terms into flags. A batch keeps its own copy of its phrases, because the label step writes the uncertain list again each time it runs and a phrase a frozen coding decided leaves it.

Every file the review writes ties label text to MedDRA terms, so it lives only in a folder named `licensed`, such as a release's MedDRA version folder `licensed/meddra/<version>/`, never in the public tree (rule meddra-licensed-tier). The codings name the preferred terms of that version, and the label step reads them from that folder. Building that MedDRA version again keeps the frozen codings and every file the review keeps its work in.

**Why:** a person decides how each phrase is coded. The agent only speeds the reading, and it is trusted with more items only after it has matched the person on every item of the batch before. The evidence is in notebook `notebooks/faers/10_label_flags`, its closing section, which sets out what was decided and why.
