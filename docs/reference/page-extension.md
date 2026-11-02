# The page's extension points

For anyone building a product on Open Altio: how a product's page modules add screens, places and choices to the explorer's page.

Contract version 1.0: the keys, places and imports on this page are part of Open Altio's [written contract](contract.md).

The page is small ES modules with no build step. A product lists its page modules in its access hook (`Access.modules`, [the access hook](access-hook.md)); the explorer writes them into the page after its own, and starts the page once every module has run. Each module imports only from `/ui/app.js` and calls `extend()` once as it loads:

```js
import { extend, framed, sidePlace, railPlace } from '/ui/app.js';

extend({
  brand: 'Acme Safety',
  routes: [(parts) => (parts[0] === 'acme' ? { page: 'acme' } : null)],
  addresses: [(parts) => parts[0] === 'acme'],
  pages: { acme: (route, app) => { app.innerHTML = framed('<main><h1>Acme</h1></main>', 'acme'); } },
  slots: {
    'side-places': (here) => sidePlace('/acme', 'admin', 'Acme', here === 'acme'),
    'rail-places': (here) => railPlace('/acme', 'admin', 'Acme', here === 'acme'),
  },
});
```

## What `extend()` takes: `EXTEND_KEYS`

`extend()` throws `extend() takes no key "<name>"` for a key not on this list, and changes nothing. The first nine add to what is there; the others take the product's place in the page.

| Key | What it is |
|---|---|
| `acts` | `{ name: (element, event) => ... }`: what a click on an element with `data-act="name"` does. |
| `pages` | `{ page: (route, app) => ... }`: draws a route's page into `app`, in place of the explorer's own page of that name. |
| `slots` | `{ place: (here) => html }`: what the product draws in one of the places below. A place not on the list throws `extend() takes no slot "<name>"`. |
| `routes` | `[(parts) => route or null]`: the route an address's parts open, asked before the explorer's own. This is how a product draws its own screen at one of the explorer's addresses. |
| `addresses` | `[(parts) => true or false]`: whether an address is one of the product's screens, so a link to it opens in place. |
| `after` | `[(route) => ...]`: run once a page is drawn. |
| `noted` | `[() => ...]`: run once an Improve this note is kept. |
| `closing` | `[() => ...]`: run when the open menus close. |
| `cards` | CSS selectors of the product's tables read row by row, which become cards on phones. |
| `brand` | The product's name, at the top of the frame and in the page's title. `'Open Altio'` by default. |
| `improve` | Whether Improve this is offered. A product that takes the notes says so. |
| `start` | `async () => ...`: decides who is here and fills `S.me` and `S.release`, in place of the explorer's own `/api/me` and `/api/release`. |
| `sendNote` | `async (note) => { said } or { problem }`: sends an Improve this note to the product, in place of the explorer's own. |
| `queries` | Where the person's own MedDRA queries are kept, in place of this browser: `{ group, save: async (query) => the query as kept or { problem }, remove: async (query) => {} or { problem }, words }`. `words` is optional, for a product that keeps queries somewhere other than "your account": `{ intro, save, saved }`, the sentence at the top of the query builder, the label of its save button and `(query) => line`, the line shown once a query is saved or chosen. Any left out says what it says without a host. |
| `kept` | Where the person's view choices are kept, in place of this browser: `{ load: async () => ({ choice: value }), save: async (choice, value) => ... }`. Below. |
| `hideAsOf` | `(here) => true or false`: true where the corner and the top bar leave out the line "FDA data through ...", for a host that says how current its data is in its own words. Every page shows it when none is given. |
| `signedOut` | `() => ...`: an answer said the person is no longer signed in. |
| `freshLinks` | `() => true or false`: true while links must load as a browser loads them, not in place. |
| `report` | `(kind, detail) => ...`: what the person did that the server cannot see, one of the kinds [the access hook](access-hook.md#what-the-page-reports-reported) lists. |

## The places a product draws in: `SLOTS`

`slot(name)` throws `slot() takes no slot "<name>"` for a place not on this list. Each is named for where it sits, and each function is handed `here`: where the frame is, `'home'`, `'all'`, `'p:<product>'` or the page's name. The places in an opened event are handed the event instead ([An opened event](#an-opened-event-openedevent)).

| Place | Where it sits |
|---|---|
| `side-places` | The side panel, after the explorer's own places and before Products. |
| `side-you` | The side panel's foot, before Settings. |
| `side-you-end` | The side panel's foot, after Settings. |
| `rail-places` | The folded rail, after the explorer's own places and before Products. |
| `rail-you` | The rail's foot, before Settings. |
| `rail-you-end` | The rail's foot, after Settings. |
| `export-note` | The export dialog, under its choices. |
| `sql-download-note` | The SQL download dialog, in place of its line on what a download takes. |
| `note-head` | The Improve this dialog, above the note. |
| `note-fields` | The Improve this dialog, under the note. |
| `settings` | The Settings dialog, after its own rows. |
| `corner-end` | The top right of every page: beside Improve this on a wide page, and in the top bar, after Improve this, on a phone. It draws nothing on a page whose host does not fill it. A page keeps the room the custom property `--corner-end-room` names (a width, none by default) for a host that fills it after the page is first drawn, so the buttons arriving move nothing. |
| `event-bar-end` | An opened event's bar, at its right end, beside the tabs: a host's next step for the event. |
| `event-window` | An opened event's Dates menu, after each of its own windows: a host's own windows ([below](#an-opened-event-openedevent)). |
| `event-under-bar` | An opened event, a line under its bar, over every tab. |
| `event-line-note` | An opened event's line, after its dates, where no filter is on: a host's quiet note. |
| `event-drug-mark` | Beside a drug's name in an opened event's tables: a host's mark for one of its own drugs. |
| `event-after-evidence` | An opened event's Overview, under its sections: a host's own record of what the evidence shows. |

A new place joins the list in the same change that adds the screen it sits in.

## A place in the side panel

`sidePlace(href, icon, label, here)` and `railPlace(href, icon, label, here)` draw one place in the side panel and in its folded rail. Each writes `data-place` as the place's address, so a place keeps who it is when its label changes. The explorer's own places are `/`, `/all/overview`, `/release` and `/methods`.

## A person's view choices

A view choice is how a person leaves a view, kept for their next visit: today `side`, whether the side panel is open or folded on a wide screen (`'open'` or `'closed'`). By default each is kept in this browser. With `kept`, the explorer asks `kept.load()` once the product's `start` has run and before the first page is drawn, reads each choice from what it gives, and calls `kept.save(choice, value)` on each change, never writing this browser's storage. A choice `load` does not give, or every choice when `load` fails, shows its default. A product's own screens keep theirs the same way, with `viewChoice(choice, default)` and `keepView(choice, value)`.

## The events table

`eventsTable(element, options)` draws Open Altio's one events table into `element`: a row per event, opening on the newest quarter against the one before: Event, N, N prior, EBGM, EBGM prior, EB05 and a Trend line of its cases over the newest quarters, sorted by N. Each head's menu sorts it and takes an At least value or ticks, a chosen sort shows an arrow (up for highest first, down for lowest first, pressed to turn it over), and the Columns menu adds the other statistics, the facts about the cases and the label answer. It gives back a handle: `paint()` draws it again after the page's own state changed, `update(options)` takes new rows or options and draws it again, `listed()` gives the rows its narrowing keeps, and `opened()` the key of the row open, or `null`.

| Option | What it does |
|---|---|
| `drug` | The drug whose events it shows: it asks `/api/events`, `/api/events/statistics` and `/api/events/prior-quarter` for it, and draws its head and tools at once while the rows come. |
| `query` | The filters `/api/events` is asked with, the drug named (`product=` the drug when not given). |
| `rows` | The rows to show, in place of `drug`: each an object named by the columns of `/api/events` and `/api/events/statistics` (`pt`, `cases`, `newest`, `prior`, `recent`, `ebgm`, `ebgm_prior`, `years`, `busiest_year`, `death`, `label`, `dme`, `ime`, `eb05` and the rest), of one drug or several. |
| `noStatistics` | With `rows`, the words saying why the rows have no statistics: Columns then offers only the facts about the cases. |
| `notAvailable` | With `rows`, `/api/events`' `not_available`: its `label` is the tip of a row with no label answer. |
| `columns` | The product's own columns: `{ id, head, tip, cell: (row) => html, sort: (row) => value, words: [first, second], first, ticks, bound, after, menu, listed }`. `listed: true` puts it in Columns, hidden until it is ticked or named in `shown`. `sort` is what it sorts and bounds by (none: no sort), `words` its two sort choices, `first` the direction of the first (`'desc'` or `'asc'`), `ticks: { heading, value: (row) => value, order, tips, foot }` a tick box for each value, `bound: { words, unit, whole, max }` an At least box, `menu: null` a head that opens nothing. `after` names the column it follows; `'start'` puts it before the event's name, held in view with it; without it the column comes last. |
| `rowClass` | `(row) => class`: a row's class; `oa-tinted` tints it and marks its left edge. |
| `rowKey` | `(row) => text`: the key that names a row (`data-key`); the row's drug and its event by default. |
| `product` | `(row) => drug`: the drug a row is of, where the rows are of several; its labels are read for that drug. |
| `open` | `(row, event) => ...`: what a press on a row does; without it a row is not pressed. |
| `opened` | `{ key, draw: (element, row) => ..., gone: () => ... }`: `gone` is told when the row open has left the list and its cell closed. One row open at a time, with a cell under it across the row that the product draws in. `key` is the row open (its `rowKey`), none when not given; `update({ opened })` opens another or, with no `key`, closes it. `draw` is called once as a row opens, with the box to draw in, as wide as the table's frame shows and held in view as the table scrolls sideways. The cell is kept as drawn while its row is on the page, through a sort, a narrowing, `paint()` and `update()`, and closed once its row leaves the page. Each row says whether it is open (`aria-expanded`); with `open`, a press on a row opens it, or closes it if it is open, before `open` is told. |
| `only` | `(row) => true or false`: the product's own narrowing, before every head's. |
| `thresholds` | A list of screens, each a list of conditions as `GET /api/statistics/quarters` takes them, such as `[[{ column: 'eb05', at_least: 2 }, { column: 'cases', at_least: 3 }]]`. Each value opens in the head's menu of its screen's first column, to change there, with a reset arrow back to what was given, never kept. The thresholds are filters: a row is kept when every screen passes, all of each one's conditions together, whether or not its column shows; `meetsThresholds(row, screens)` reads the screens it is given the same way. The table says how many rows it hides, and `update({ thresholds })` starts them again. With this option the tools row also says the two quarters read, each with its days as its tip. |
| `screensOfColumns` | `true` applies only the screens of the columns showing, as Open Altio's own page does. |
| `beyond` | `(row) => true or false`: a row kept in view whatever the thresholds say, not counted as hidden nor as meeting them. |
| `find` | `false` draws no Find an event box, for a page that draws its own. |
| `pager` | `(rows) => ({ rows, html })`: the product's own pager: the rows of the page shown, and what it draws under the table. By default the table shows `events_shown` rows (rule `explorer-lists`) and Show more. |
| `view` | The name the person's choices are kept under: `<view>.columns` and `<view>.bounds` (`events` by default), through `viewChoice` and `keepView`, so a product's `kept` keeps them. A choice of the wrong kind reads as the table opens; ticks are not kept. |
| `shown` | The columns Columns opens with ticked: none by default. |
| `always` | `{ columns, tip }`: columns that always show, listed in Columns with no box and the tip. |
| `order` | The table's own order, `[[column, 'desc' or 'asc'], ...]`: the most cases this quarter first, then by name, by default. A column the person sorts by comes first, and an empty value comes last either way. |
| `mark` | `(row, column) => words`: a cell to mark, in the warning color, with the words as its tip. |
| `foot` | `(menu) => html`: the product's words at the foot of a menu, `'columns'` or a column's `id`, before the table's own. |

`place(menu, anchor, { fit: true })` keeps a menu inside the window, beside its control where nothing else fits; `beside: false` keeps it under or over the control. A menu from `popMenu` stays against its control as its rows change, and goes to the control's other side once it fits better there.

`tickMenu(anchor, { values, ticked, heading, foot, onChange })` opens a menu of tick boxes under `anchor`, inside the window: `values` is `[{ value, words, count, tip }]` or a function giving them, `ticked` the values ticked (`null`, every one), and `onChange(ticked)` is told each change, with `null` once every value is ticked again. Under the boxes it shows Deselect all while every box is ticked and Show all once any is not, so the menu keeps its height.

## An opened event: `openedEvent`

`openedEvent(element, options)` draws an event opened under its row into `element`, the box an events table's `opened.draw` is handed, and gives back its handle. A drug's Events tab opens one this way, and a product mounts it the same:

```js
eventsTable(el, { drug: 'valsartan', opened: { draw: (box, row) => openedEvent(box, { drug: 'valsartan', row }) } });
```

Top down it draws: a copy of the event's row, its numbers under the table's heads; the line, the window's dates and what they are compared with (pressed, the Dates menu), each filter with its x, + Add a filter and Clear all; the bar, the tabs Overview, Compared and Cases with the event's cases in the window, and `event-bar-end` at its right; `event-under-bar`; then the tab's pane. Row, line and bar stay at the top of the page while the event is in view, wherever the table fits its frame; a table wider than its frame scrolls sideways and nothing sticks. The event is no taller than the window, under the row, and the tab showing scrolls inside it; in a window under 480 pixels tall the page scrolls instead. Each event keeps its window, its counting date and its filters while the page is open.

| Option | What it is |
|---|---|
| `drug` | The drug, as `/api/events` names it. |
| `row` | The event's row, as the table has it (`pt`, `cases` and the rest). |
| `query` | The product's settings as the table asked `/api/events` (`product=` the drug when not given). |
| `reaction` | The event's preferred terms, where the row is a group of reactions (`[row.pt]` when not given). |
| `screens` | The host's thresholds, for the panes: a list of `{ name, conditions, words }`, each condition as `/api/statistics/quarters` reads a screen, `name` its strip's name and `words` the threshold in words (the conditions in words when not given); and the host's alarm on a share, `{ share, points }` (below). |
| `tab` | The tab it opens on: `overview` when not given, or the address's `?tab=`. |
| `classes` | `false` keeps WHO's drug classes out of the event's panes: Compared works with single drugs, asks for no class and draws none, and a class the person kept earlier stays kept, unread. When not given, the classes show where the release carries them and the viewer may see them. |

The handle gives `context()`, the event as its panes see it (below), `setFilter(field, values)`, `showTab(name)` and `paint()`.

**The window.** It opens on the release's newest quarter. The Dates menu offers The newest quarter, The last four quarters, All dates and Pick days (a calendar for its first day, then its last); compared with the period before the window (every day from the event's first case) or the same length just before; and cases counted by the date FDA received the report or by the date the reaction started, where only the reports that give that date to the day count. A host offers its own windows through `event-window`, drawn after each of the menu's own with `after` naming it (`'quarter'`, `'four'` or `'all'`): each a `choice(...)` with `data-act="ev-window"`, `data-k` its kind, `data-from` its first day, `data-to` its last (the release's end when left out) and `data-said`, the words the line says after its dates; one with `aria-disabled="true"` and a tip is shown and cannot be picked.

**Compared.** The event's numbers for its drug beside the rows a person adds, one table: cases, EB05 and PRR at the window's start and end with the change, Serious, Fatal and Label, every row counted the same way in the window and the line's filters. + Add a drug or class is the Drug class filter's tree with this event's counts, and finds drugs by name; a drug starts beside its chemical class, a class opens to the classes and drugs in it. A class's EB05 and PRR are the release's class statistics, on every case, so they stand only for a window to the release's end, at the levels the release scores. A drug's name opens its own read-only view of the event in place of the event's line and bar, with the same window, date and filters and Back: its row has no host column and its bar no `event-bar-end`. `event-under-bar` and `event-line-note` are still drawn, handed `from` (`{ drug, reaction }`, the event it was opened from), for what a host says about another drug; `event-drug-mark` marks a host's own drugs; a value turns the warning color only past one of the host's `screens`, and only on a drug.

**+ Add a filter** lists the fields of the cases the explorer filters by, in groups: Patient (Age, Sex, Country), Drugs (Role), Course (Seriousness), Report (Reporter, Company). Each field's values show with their counts among the event's cases in the window under its other filters; Deselect all leaves no value, so no case shows, and Show all brings every case back.

**Its panes: `registerEventPane`.** `registerEventPane(name, { label, order, draw })` gives the part that draws a pane: `overview`, `compared` and `cases` are the tabs every event has; another name with a label adds a tab in its `order`; `case`, with no tab, reads one case in place of the panes. `draw(pane, ctx)` is called once, as its tab first shows, and may give back `{ update(ctx), close() }`: `update` is told each change of the dates or the filters, for every pane drawn, shown or not; `close` as the event closes. A pane no part registered shows a plain placeholder.

What `ctx` holds:

| Key | What it is |
|---|---|
| `drug`, `row` | As given. |
| `reaction` | The event's preferred terms, a list. |
| `window` | The window's days under the names of the date that counts: `{ received_from, received_to }`, or `{ event_from, event_to }` while `dateField` is `event`. |
| `before` | `{ before_from, before_to }`, the period it is compared with, as `/api/breakdowns` reads it; both empty when the window takes every day. |
| `dateField` | `received` or `event`: which date counts a case. |
| `kind` | The window's kind: `quarter`, `four`, `all`, `days` or a host's. |
| `filters` | `[{ field, values }]`, each an explorer filter parameter (`age`, `sex`, `country`, `prole`, `outcome`, `reporter`, `sender`) and its values. |
| `none` | True while a field has no value ticked: no case shows, and a pane shows none without asking. |
| `cases` | The event's cases in the window under its filters, `null` while they are counted. |
| `screens` | As given. |
| `classes` | Whether the panes may show WHO's classes: not `false` as given, and the release carries them for this viewer. |
| `compared` | What the window is compared with: `before` or `same`. |
| `from` | Where a read-only view was opened from, `{ drug, reaction }`; null for the event itself. |
| `query(extra, { without })` | The product's settings, the filters and the window's days as one query string, with `extra`'s parameters set, and with the filter `without` names left out; the event's terms are not in it. |
| `setFilter(field, values)`, `clearFilter(field)` | Sets a filter, which the line then shows with its x, or takes it away. |
| `openCase(caseId)` | Opens a case, `<era>/<key>` as `/api/case/{era}/{key}` names it: in place, in the pane registered as `case` (its `ctx.caseId`, and `back()` to the Cases tab), else in the case window. |
| `slot(name)`, `drugMark(drug)` | What the host draws in one of the event's places; its mark beside `drug`. |

**The Overview.** Open Altio draws the Overview pane itself. On top, a chart of the event's cases by quarter over the years, by the date that counts, under its filters and over every date, the window's quarters dark under a Window mark, and under the bars one strip per threshold: a quarter in the warning color where every condition held on every case received by its end, deeper the further past, and grey below, darker the closer it came. Its title says which thresholds were passed and when their current stretch began. The strips are each statistic's usual threshold, its default preset (`/api/statistics/about`): EB05's and PRR's at first, others added from Statistics under the strips and kept as the person's view choice `event.strips`. Each of a host's `screens` with `conditions` is a strip too, in place of the usual one of the statistic its first condition reads, and the person's own beside a host's are drawn lighter. Beside the chart, four tiles, each the window against before it: Cases in the window, with the probable duplicates left out; EB05 and PRR during the window, on every case received up to the window's start and up to its end; and the serious and fatal shares. A number turns the warning color only through a host's `screens`: EB05 or PRR past a host's threshold of that statistic at the window's end, and a share, `serious` or `death`, that rose by at least a host's `{ share, points }` points with its rise past the chance test of `/api/breakdowns`, read where the date that counts is the day FDA received the report.

**The breakdowns.** Open Altio's own section under the chart: the groups of rule `breakdown-lines` (Clinical picture, Causality, Data quality), one line per field, from `/api/breakdowns` under the event's filters and window. A line shows the value its field's pick names, its share before the window and in it among the reports that give the field, the change in points and how many of the window's reports give the field. Pressing a line puts the value it shows on the event's line, as the line's `filter`, and opens every value of its field with a tick box and its cases in the window under the event's other filters; the foot is Deselect all while every box is ticked, else Show all. A line whose value is no value of a filter (Time to onset's median) adds no filter, and a line with no `filter` lists its values with nothing to change. A number turns the warning color only through a host's `screens`: an entry `{ breakdowns: { points, strength } }` asks `/api/breakdowns` with them and marks the lines whose `alarm` holds.

**Under the chart: `overviewSection`.** `overviewSection(name, { order, draw })` adds a section to the Overview under the chart and its tiles, in `order` among the others. `draw(box, ctx)` is called once as the Overview is drawn, with a box of its own and the same `ctx`, and may give back `{ update(ctx), close() }`, told as a pane is. A section registered again by the same name takes that place.

**The Cases tab and a case in place.** Open Altio registers `cases` and `case` itself. The Cases tab lists the event's cases in the window under its filters: Find a case by its number, how many cases are shown of the window's, Include duplicates (the event's `dedup`, which the line does not name), Columns (every field FAERS gives for a case, in five groups, kept as the view choice `event.columns`), Download these cases, and a table with a menu on every head that sorts it both ways and, for a field the explorer filters by, shows only some values, each with its count (its pick is the event's own filter, so the line names it). A case's probable duplicates open under it, each with a sentence of what the two reports agree on and what clashes. The pager keeps the cases a page as `event.casesPerPage`. A case pressed opens in place (`openCase`), the address naming it (`?case=`, so a copied link opens it there); ‹ Cases or Escape go back to the same page, the case's row marked. A host that registers `cases` or `case` draws its own instead.

## A product page's address: `?reaction=`

A product's page opened at an address with `?reaction=<preferred term>`, such as `/product/valsartan/cases?reaction=Headache`, sets its Reactions filter to that one term. On Statistics, whose figures no filter changes, the term is typed in Find, so its own row comes first. The address then shows the page without it, so the filter is the person's to change. An older name or a brand in the address carries the term to the drug's own page. All cases' address takes no reaction.

## Tables and SQL's address: `?query=`

Tables and SQL opened at an address with `?query=<statement>`, such as `/release?query=SELECT%201`, puts the statement in its query box once the page can run a query: its tables are listed and the box is drawn. The address then shows the page without `query`, so a reload or a shared link does not fill the box again, and any other parameter stays. The page runs nothing by itself; the person presses Run.

## What a page module may import

Only `/ui/app.js`, and only these names. Anything else on the page may change in any release.

| Name | What it is |
|---|---|
| `extend` | Adds the product's screens, places and choices (above). |
| `EXTEND_KEYS`, `SLOTS` | The lists above. |
| `framed(content, here)` | A page in the frame: the side panel, its rail and the top bar around `content`. |
| `sidePlace`, `railPlace` | A place in the side panel and in its rail (above). |
| `railButton(act, icon, label)` | A button in the rail. |
| `improveBtn()` | The Improve this button, where it is offered. |
| `ACTS` | Every `data-act` and what it does. |
| `openPane(element)` | Opens a filter's options on a phone's filter sheet. |
| `takeDownload(what)` | Downloads one table, a layer or every table, listing the files in a dialog. |
| `icon(name)`, `markSvg()` | An icon by name, and the mark beside the product's name. |
| `dialog(heading, body, foot)`, `layer()` | Opens a dialog; the element dialogs open in. |
| `popMenu(anchor, html, cls)`, `place(menu, anchor, options)`, `openedBy(element)`, `closeMenus()` | Opens a menu under its anchor; places one, with `{ fit: true }` inside the window (under its anchor, else over it, else beside it, else scrolling inside); names the control it was opened from; closes them all. A press outside an open menu only closes it. |
| `eventsTable(element, options)`, `tickMenu(anchor, options)`, `meetsThresholds(row, screens)` | The events table, a menu of tick boxes, and whether a row meets the table's thresholds (above). |
| `openedEvent(element, options)`, `registerEventPane(name, part)`, `overviewSection(name, part)` | An event opened under its row, the part that draws one of its panes, and a section of its Overview (above). |
| `choice(on, label, count, attrs, options)` | One choice in a menu, ticked or not, with its count. |
| `busy(button, on)`, `formProblem(box, message)`, `toast(text)`, `showProblem(error)` | A button waiting; a form's problem under it; a short message; a message for an answer that did not load. |
| `addressParts(path)`, `pageAt(parts)` | An address's parts; the explorer's own page an address names. |
| `current()`, `here()` | The route drawn now; the address shown. |
| `go(path)`, `putAddress(path)`, `render()` | Opens an address with a step in the history; shows one without; draws the page again. |
| `api(path)`, `post(path, body, method)` | An answer of the server's, kept for the page; a POST or another method, with the server's message as `problem`. |
| `S` | What the page knows: `S.me`, `S.release` and the person's choices. A page module adds its own fields. |
| `meddraOn()` | Whether this person may see MedDRA's licensed part. |
| `termSearch(el, { products, onPick, tabs })` | Draws Open Altio's term search into `el`. Below. |
| `viewChoice(choice, default)`, `keepView(choice, value)` | A view choice, read and kept where the product keeps them (above). |
| `rereadStored()` | Reads this browser's kept choices again, once a module has moved older ones into place. |
| `quartersOf(manifest)`, `rowsIn(manifest, table)` | A release's quarters in words; a table's rows, as the manifest counts them. |
| `esc`, `num`, `day`, `size`, `trim`, `tip`, `store` | Escapes text for the page; a number, a day and a file size as a person reads them; shortens text; a tip; this browser's storage, under the explorer's own prefix. |

## The term search: `termSearch`

`termSearch(el, { products, onPick, tabs })` draws the Reactions search into `el`, so a product's page finds events by term with Open Altio's own box and writes no second one. It asks `/api/terms` and keeps nothing: it saves no choice and changes no filter of the explorer.

| Option | What it is |
|---|---|
| `products` | The drug names the case counts beside each term are over, sent as `dprod`. Empty: every case. |
| `onPick` | Required. Called with the pick: `{ kind: 'pt', pt }` for a preferred term, `{ kind: 'pt', pt, llt }` for a lower-level term (`pt` is the preferred term it is coded to), `{ kind: 'smq', code, name, scope }` for an SMQ with its `scope`, `'narrow'` or `'broad'`. |
| `tabs` | The kinds to offer, from `'all'`, `'pt'`, `'llt'` and `'smq'`. The first listed opens first. Lower-level terms and SMQs are offered only to a viewer with MedDRA's licensed part. |

For a viewer without that part the box offers preferred terms only and shows the answer's `why_no_licensed` line in place. The results hold one height, so nothing else on the page moves when they open.
