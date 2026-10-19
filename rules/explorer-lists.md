---
rule: explorer-lists
values:
  products_found: 12
  names_shown: 4
  spellings_shown: 100
  unmapped_found: 8
  top_reactions: 12
  top_drugs: 10
  terms_found: 30
  terms_found_one_kind: 150
  llts_found: 15
  llts_found_one_kind: 150
  smqs_found: 12
  smqs_found_one_kind: 300
  home_tiles: 4
  names_on_page: 3
  countries_charted: 8
  companies_charted: 8
  reactions_suggested: 8
  years_offered: 7
  countries_offered: 80
  statistics_shown: 100
  classes_found: 40
  top_classes: 12
  socs_charted: 12
enforced_in:
  - src/open_altio/explorer/facts.py
  - src/open_altio/explorer/statistics.py
  - src/open_altio/explorer/found.py
  - src/open_altio/explorer/explore.py
  - src/open_altio/explorer/ui/home.js
  - src/open_altio/explorer/ui/scope.js
  - src/open_altio/explorer/ui/charts.js
  - src/open_altio/explorer/ui/terms.js
  - src/open_altio/explorer/ui/filtermenu.js
  - tests/explorer/test_search.py
  - tests/explorer/test_page.py
---
# How long the explorer's lists are

The explorer's searches and short lists stop at these lengths. A person who needs more narrows the search, opens the product, or uses SQL.

- `products_found`: ingredients and combinations a search for a product shows (by their name or a spelling FDA has for them).
- `names_shown`: the spellings a product is reported under most, shown beside its name; a product search looks in them too.
- `spellings_shown`: the spellings a product page lists before anything is typed, most cases first; typing finds any other.
- `unmapped_found`: FDA's spellings with no ingredient a search offers, most cases first.
- `top_reactions`: reactions on a page's Overview, most cases first.
- `top_drugs`: ingredients on All cases' Overview, most cases in the default roles first.
- `classes_found`: WHO drug classes a search in the Drug class filter shows (by their code or name), each with the classes above it.
- `socs_charted`: MedDRA system organ classes on a page's Overview, most cases first, for a viewer who may see MedDRA.
- `top_classes`: classes on All cases' Overview, most cases first, beside the one bar of cases whose drug could be several.
- `companies_charted`: companies on a page's Overview, most cases first, then the cases whose sender is not given.
- `statistics_shown`: ingredient and reaction pairs the Statistics tab lists at a time, and how many more each click shows.
- `terms_found`, `llts_found`, `smqs_found`: preferred terms, lower-level terms and SMQs a reaction search shows of each kind; `..._one_kind` when the person asks for one kind only.

The page reads the rest from `/api/release`:

- `home_tiles`: products on Home, the ones opened most lately or, on a first visit, those reported most as a suspect.
- `names_on_page`: of a product's other names, how many its tile, a search's result and its page's title line show.
- `countries_charted`: countries on a page's Overview, most cases first.
- `countries_offered`: countries the Country filter lists, most cases first, of those that match what is typed.
- `reactions_suggested`: reactions the Reactions filter suggests before anything is typed; under PTs alone, all `top_reactions`.
- `years_offered`: whole years the date filters offer at a click, the release's last first.

**Search order:** every search box lists what it finds in three groups: the name typed, whole, first; then the names that start with it; then the rest that hold it. Within each group the list keeps its own order (most cases first, or the column a table is sorted by, or by code). A class above others comes where the first class found under it does, so the tree keeps that order. Clearing the box lists everything in that own order again.

**Why:** short lists load fast on a phone and stay readable; every list says how to see more. The name typed comes first because a person who types Seizure on a drug's Statistics wants Seizure, not the reaction with the highest score that holds the word.
