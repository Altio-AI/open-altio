# The access hook

For anyone building a product on Open Altio: who is viewing, what they may see, and what the explorer tells a product they did.

Contract version 1.0: the names on this page are part of Open Altio's [written contract](contract.md).

The explorer never decides who may view or what they may see. `create_app(release_dir, access=hook)` hands it an access hook, and the explorer asks it on every request. Without one, `LocalAccess` answers: one person on their own machine, who sees everything the release holds, and nothing they do is recorded. Every name below lives in `open_altio.explorer.access`.

## Who is viewing: `Viewer`

A frozen dataclass, one for each person asking.

| Field | Default | What it says |
|---|---|---|
| `id` | | Who is asking, as the product's usage log knows them. SQL runs one query at a time for each `id`. |
| `meddra` | | Whether they may see MedDRA's licensed part (SMQs, lower level terms, the hierarchy), where the release holds one, its tables in SQL included. |
| `who` | | Whether they may see WHO's drug classes on the pages: the class filter and each drug's class. |
| `sql` | `True` | Read-only SQL, and its whole result as a file. |
| `exports` | `True` | The filtered export. |
| `statistics` | `True` | The statistics: EBGM, PRR, ROR, RRR and IC for each pair, on the Signals tab and in an opened event. |
| `who_files` | `False` | WHO's drug classes in files: the class tables in SQL and on the Tables page, and each drug's class in a filtered export. A product may give it apart from `who`, as a licence asks. |
| `todays_names` | `True` | Reactions named and counted by the release's MedDRA version, each under its current preferred term, for a viewer without `meddra` too. `False` shows them as FDA wrote them. |
| `fda_text_line` | `""` | The line the pages show where reactions are listed, for a viewer shown FDA's text in a release that holds MedDRA. |
| `why_no_smqs` | a plain sentence | Why they are shown no SMQs, for when they ask for one. |
| `why_no_classes` | a plain sentence | Why they are shown no drug classes, for when they ask for one, in a release that holds them (a release holding none says so instead). |

`Viewer.named_by_meddra` is true when `meddra` or `todays_names` is.

## The hook: `Access`

A protocol: a product's hook is any object with these members.

| Member | What it answers |
|---|---|
| `modules` | The page modules loaded after the explorer's own, by their address ([the page's extension points](page-extension.md)). |
| `terms` | What a filtered export's manifest says about the terms it is used under. |
| `edits_rules` | Whether the methods page saves a person's choices beside the release and rebuilds it. |
| `viewer(request)` | The `Viewer` asking, or an `HTTPException` (401 or 403) when nobody may view. |
| `about(request, viewer)` | What `/api/me` adds about the viewer, for the product's own screens. |
| `record(viewer, kind, **fields)` | What the viewer did with the data: one of the kinds below, with its fields. |

`LocalAccess` is the hook for one person on their own machine, and `LOCAL` the viewer it answers.

## What the server announces: `RECORDED`

The explorer tells the hook what a person did through `Explorer.announce(viewer, kind, **fields)`, and only there. `RECORDED` maps each kind to its fields. `announce` raises `ContractError` for a kind not listed, or a field a kind does not list or lacks, so the request fails in a product's tests rather than writing a record nobody reads.

| Kind | When | Fields |
|---|---|---|
| `search` | A search with words typed in it answered: products, drugs, spellings, reactions or classes. A list asked for with no words is not a search. | `search` (which one), `words` (as typed), `results` (how many it shows) |
| `export_started` | The export dialog asked how many rows it would write. | `rows` (the rows of each file) |
| `filtered_export` | A filtered export written. | `release`, `query` (its query string), `described` (its filters in words), `format`, `rows`, `at` (the moment it was made) |
| `sql` | A SQL query run, or its whole result downloaded. | `sql`, `outcome` (`ok`, or why it stopped), `rows`, `seconds`, and `download` (the format) only when the whole result was downloaded |

`OPTIONAL` lists the fields a kind carries only sometimes: today `download`, on `sql`.

Viewing a published question announces nothing, so a person's own view of the data writes no record. Downloading whole tables of a release is a product's own route (the explorer serves none), so a product records it itself.

## What the page reports: `REPORTED`

What a person does that the server cannot see, the page tells the product's page modules through `host.report(kind, detail)` ([the page's extension points](page-extension.md)). The kinds are a closed list, `REPORTED` in `ui/host.js` and the same list in `open_altio.explorer.access.REPORTED`; the page sends no other kind.

| Kind | When | Detail |
|---|---|---|
| `screen` | A screen or a tab opened, once each time it is | `screen`, `tab`, `product` |
| `rule` | A rule read on How we clean FAERS | `rule` |
| `pick` | A result picked from a search with words typed in it | `search`, `words`, and `picked` (an open name) or `level` and `code` (a licensed MedDRA level or a WHO class) |
| `improve_opened` | Improve this opened | `page` |

## A product's own kinds

A product announces what its own screens and routes do from its own code, under its own names, straight to its own usage log. It never sends one of the kinds above for something else, and never adds a kind to these lists: a kind Open Altio adds later would then mean two things.
