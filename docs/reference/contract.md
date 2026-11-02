# The written contract

For anyone building a product on Open Altio: the names a product may build on, and how they change.

Contract version 1.0, as `open_altio.CONTRACT_VERSION` says.

A product built on Open Altio uses Open Altio's code through a few seams: the release folder it reads, the questions it asks, the access hook it plugs in, the page it extends, the rules it adds and the routes it serves. Each seam's page below lists the names a product may use. Anything not on these pages (any other module, function, global or page export) is outside the contract and may change in any release.

## How the contract changes

- **Each change has a version.** The minor version rises when a name is added, the major when a name is renamed or goes. Each change to a listed name carries a CHANGELOG line under the release that makes it, naming the new contract version.
- **Open Altio checks it first.** The contract's own tests (`tests/contract/`) run in every check Open Altio's changes pass (`scripts/check.py --all`), against the invented release. A change that fails them either keeps the old names, or raises `CONTRACT_VERSION` and writes the snapshot of the answers again with `scripts/contract_snapshot.py`, which refuses to drop a name unless the major version rises.
- **A product pins its version.** It names the exact `open-altio` version in its `pyproject.toml` and checks `open_altio.CONTRACT_VERSION` in its own tests, so it moves to a new contract version on purpose, never by an update.

## The release folder

A release folder is the only hand-off: its manifest names its `source` and its `format_version`, and every reader refuses a folder it does not read. [What a product may read](data-dictionary.md#what-a-product-may-read) lists its names.

## The questions and their answers

Every question a product may ask of a release, over HTTP or in its own process, with the function that answers it and the keys of its answer, each answer naming the release it was counted on. [The questions and their answers](api.md) lists them.

## The access hook

Who is viewing and what they may see (`Viewer`, `Access`), and what the explorer tells a product they did: the kinds the server announces (`RECORDED`, through `Explorer.announce`, which refuses any other with `ContractError`) and the kinds the page reports (`REPORTED`). A product announces kinds of its own from its own code. [The access hook](access-hook.md) lists them.

## The SQL service

A product may keep its own read-only SQL instance over a release: `SqlService(release, limits=None, home=None)` (the same on `SqlDatabase`), with `Viewer.sql` and the outcomes `Refused`, `Busy` and `LimitHit` it answers with, all from `open_altio.explorer.sql`. `limits` are DuckDB settings (`memory_limit`, `threads`, `max_temp_directory_size`) in place of rule `sql-limits`' memory and threads, and such an instance spills to a folder of its own, under `home` when given. A query needing more than the spill limit ends as `LimitHit`. The time limit, `rows_shown`, the query slots and the lockdown are as for any instance. These names are part of the contract: renaming one raises the major version.

## The page's extension points

A product's page modules import only from `/ui/app.js`, whose export list is the contract, and each calls `extend()` with keys from `EXTEND_KEYS`: its screens, its name (`brand`), where a person's view choices are kept (`kept`), where their own queries are kept and in what words the query builder says so (`queries`, with its optional `words`) and the rest. It draws only in the places `SLOTS` lists, each named for where it sits (the top right of every page among them, for its own buttons). An unknown key or place throws at once, so a product finds out the moment it loads. A product finds events by term with `termSearch(el, { products, onPick, tabs })`, Open Altio's own search mounted on its page, draws Open Altio's events table with `eventsTable(el, options)`, opening one row at a time under which it draws its own cell (`opened`) or Open Altio's opened event (`openedEvent`, its panes drawn by `registerEventPane`, its Overview's sections by `overviewSection`), and links to a drug's Cases or Statistics narrowed to one event with a product page's address `?reaction=<preferred term>`. [The page's extension points](page-extension.md) lists them.

## Rules from other folders

A product keeps its own numbers and policies as rule files in a folder of its own, added with `rulebook.add_rules_dir(path, prefix)` and read with `rulebook.value`, like Open Altio's. Every rule name in that folder starts with the product's prefix, and a name lives in one folder only. [Rules from other folders](rules.md#rules-from-other-folders) says how.

## Server routes

A product serves its own routes with the explorer behind them. It builds its own FastAPI app, adds every route of its own, then hands it the explorer with `host` from `open_altio.explorer.app`:

```python
from fastapi import FastAPI

from open_altio.explorer import pages
from open_altio.explorer.app import create_app, host

explorer = create_app(release_dir, access=my_access)
app = FastAPI()
app.include_router(my_routes)  # its own API, under /api/acme/
app.add_api_route("/acme-admin", pages.index, methods=["GET"])  # a page of its own
host(app, explorer)
```

- **The product's routes answer first,** and the explorer answers every request they do not. Every answer, the product's too, carries the explorer's `HEADERS`: the pages are never framed by another site, and links leak no address.
- **The explorer's paths are its own.** `RESERVED` lists them: `/` (Home) itself, and every path at or under `/api`, `/ui`, `/all`, `/product`, `/release`, `/sql`, `/downloads`, `/methods` and `/rules`. A product's own API sits under `/api/<its prefix>/`, a prefix none of the explorer's `/api` routes starts with. `host` raises `ContractError`, naming the route, when a route of the product's would answer one of the explorer's paths.
- **A page of the product's own** is served at an address of its own through `pages.index`, the same page with the product's page modules on it. To draw its own screen at one of the explorer's addresses (its own Home at `/`, say), a product uses `routes` on the page ([the page's extension points](page-extension.md)), never a server route.
- **Outside the contract:** putting routes ahead of the explorer's, replacing or removing the explorer's routes, and changing a module's globals at run time. Any of them may break in any release.
