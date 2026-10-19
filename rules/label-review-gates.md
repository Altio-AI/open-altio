---
rule: label-review-gates
values:
  other_share_below: 0.01
  agreement_at_least: 1.0
enforced_in:
  - src/open_altio/labelreview/gates.py
  - src/open_altio/labelreview/page.py
  - tests/labelreview/test_gates.py
---
# Gates before a bigger batch

Before the next, bigger batch of label review may start (rule label-review), the current batch must pass every gate:

- **Every item decided.** The reviewer has accepted or rejected each item in the batch.
- **"Other" is rare.** Items the reviewer coded as none for the reason "other" are fewer than `other_share_below` of the batch: under 1%, so none in a batch of 100.
- **The agent agreed on every item.** The share of items where the agent named the same preferred terms as the reviewer, or both said none, is at least `agreement_at_least`: 100%. Any disagreement blocks, and an item the agent left without an answer, or refused, counts as one. Where both said none for different reasons, the items are listed for tidying the reasons, and do not block.
- **The suggestions are current.** Every suggestion was made with today's instructions and coding rules (rule label-agent).

When a gate fails, the fix goes into the coding rules, a fixed rule or the agent's instructions, and the batch is rerun: `export` hands the agent every item whose suggestion is no longer current, `import` takes its answers back, and the agreement is measured again against the reviewer's decisions, which stand.

At each such milestone the reviewer reads the items coded none for "other" (the status command lists them with their notes), to add a reason or change one.

**Why:** the agent sees more items only after it has shown, on every item of a batch, that it codes the way the reviewer does.
