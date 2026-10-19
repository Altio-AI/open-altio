"""The explorer: a release's cases, filtered, counted and read, in the browser.

app.py       create_app: the explorer over one release folder, with an access hook
access.py    the access hook: who is viewing and what they may see; LocalAccess by default
context.py   what every route works with, as FastAPI dependencies
api.py       the /api routes the page reads its data from
answers.py   how /api answers: JSON, never cached, refusals as {"problem": ...}
downloads.py the filtered export and a SQL result as files, each told to the access hook
filters.py   the filter model: URL query string <-> Filters -> SQL and plain words
release.py   the one reader of the live release: its folder (or the pointer to it), database
explore.py   the questions the pages ask: counts, charts, the case list, one case
search.py    the searches for products, drugs and reactions
classes.py   WHO's drug classes: the class filter, its classes, the breakdown, each drug's class
labels.py    the label flags of a drug's reactions, of one case and of its Statistics pairs
labelnames.py how a label read is named: product, ingredients and, where they differ, forms
facts.py     what the pages need from a release that no filter changes, worked out once
warm.py      the live release made ready before anyone asks, so the first page is quick
tables.py    the release's tables and views, and read-only SQL over them
export.py    the filtered export's zip
sql.py       read-only SQL over the release, within rule sql-limits
sql_files.py a whole SQL result as a file, within its row limits
meddra.py    the release's licensed MedDRA part, where it has one
reactions.py what a reaction is: its current PT where the release holds MedDRA, else FDA's text
rules_api.py the methods page's /api: the rules, the person's choices and the rebuild with them
rebuild.py   the release rebuilt with the rules saved beside it, in the background
statistics.py the Statistics tab's answers: the release's statistics, screened, sorted and paged
pages.py     the page, its files and its addresses
outbox.py    Improve this on a copy: each note kept until the page has sent it to Altio
"""
