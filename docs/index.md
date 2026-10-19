# Open Altio

For anyone deciding whether Open Altio is for them.

Open Altio makes public drug safety data usable by anyone, free and in the open.

Regulators publish reports of harm from medicines as raw files that take a specialist weeks to clean. Open Altio does that work once, openly, so anyone can look for themselves.

It starts with FDA's Adverse Event Reporting System (FAERS, and the legacy AERS before it, every quarter since 2004). More public sources will follow.

- **Cleaned and deduplicated** with the code, the rules and the evidence for every step.
- **FDA's values are kept exactly as published.**
- **Everything Open Altio works out sits beside them,** so you can always see what FDA said and what we did.

## Try it in 60 seconds

```sh
uv tool install open-altio
open-altio demo
```

No uv yet? [Install it first](use/explorer.md#install), with one line.

`demo` downloads FDA's latest quarter (about 65 MB) and DiAna's drug dictionary. It builds a release from them (about 30 seconds) and opens the explorer in your browser. It runs on your machine only, with no sign-in and no telemetry.

![The Open Altio explorer: a search for Dupixent, its eye reactions filtered, their statistics, label and drug class, a case in full, and conjunctivitis compared across drug classes](assets/explorer.webp#only-light)
![The Open Altio explorer: a search for Dupixent, its eye reactions filtered, their statistics, label and drug class, a case in full, and conjunctivitis compared across drug classes](assets/explorer-dark.webp#only-dark)

## Three ways in

1. **[Look at the data online](use/hosted.md)** on open.altioai.com. Apply for free access, then browse, filter, export and download every release. Nothing to install.
2. **[Run the explorer on your machine](use/explorer.md).** One command for the latest quarter; two more for all of FAERS.
3. **[Rebuild](customise/rebuild.md) or [customise](customise/rules.md) the release** from FDA's own files, by switching rules off or changing their values.

## What a release holds

On FDA's files from 2004Q1 to 2026Q2:

| Step | Cases |
|---|---|
| Report versions, as FDA published them | 24,812,425 |
| One latest version of each case, across AERS and FAERS | 20,692,690 |
| Less the cases on FDA's deleted-case lists | 20,588,529 |
| Kept after flagging probable duplicates (flagged, never deleted) | 20,296,653 |

Each step, its rule, what it moved and the evidence behind it are on [the methods page](methods/index.md).

## Where to go next

- **Using the data:** [FDA or Open Altio, reading the data](use/reading-the-data.md), then the [data dictionary](reference/data-dictionary.md).
- **Building your own:** [the `open-altio` command](reference/cli.md) and [changing a rule](customise/rules.md).
- **Checking our work:** [the methods page](methods/index.md) and the notebooks behind it.
- **Helping:** [how to help](contribute/index.md). We aim to answer within a week. A maintainer replies on your issue with the next step: confirmed with a label, a question, or a no with the reason.

FAERS reports do not establish that a product caused an event. FDA has not reviewed or endorsed Open Altio.
