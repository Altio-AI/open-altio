/* The one events table: a row per event of a drug, from /api/events with each event's statistics
   from /api/events/statistics and its EBGM at the quarter before from /api/events/prior-quarter, or
   the rows a host gives, of one drug or of several. It opens on the newest quarter against the one
   before, the most cases first. Each head's menu sorts or narrows it, the arrow of a chosen sort turning it over
   (eventmenus.js), and thresholds are the At least values those menus open with (eventthresholds.js).
   Columns picks the statistics and the
   facts about the cases it shows, Trend draws each event's cases by year, and Label answers whether
   today's label lists the event. One line per cell, the event's name held in view as the table scrolls sideways, and
   nothing moves when a menu opens: a choice redraws the rows under heads that stay, and a column
   never narrows once drawn. A host gives its own columns, a class, a key and a drug for each row,
   what a press on a row does and its own pager, and may open one row at a time, drawing in a cell
   under it that the table keeps as its rows are drawn again; the person's columns and bounds are
   kept as view choices (this browser, or where a host's `kept` keeps them), never the sort or the
   thresholds. */

import { OPENS_WITH, fixedColumns, listedColumns } from './eventcolumns.js';
import { columnsMenu, formsMenu, headMenu } from './eventmenus.js';
import { actions } from './events.js';
import { countWords, hiddenWords, limitsOf, limitsWords, meetsThresholds, quartersHtml, screenOfLimits } from './eventthresholds.js';
import { conditionWords } from './screens.js';
import { icon } from './icons.js';
import { labelsOn } from './labels.js';
import { api } from './server.js';
import { S, keepView, listLength, releaseQuarter, viewChoice } from './state.js';
import { esc, num, skeletonRows, sortMark, tip } from './util.js';

// A drug's events, as the table asks for them: /api/events under `query` (the page's filters, the
// drug named), each row given its statistics where the drug has them, named by both answers' own
// columns. `statistics` says why there are none, where there are none.
const named = (got) => got.rows.map((row) => Object.fromEntries(got.columns.map((c, i) => [c, row[i]])));
export async function drugEvents(drug, query = `product=${encodeURIComponent(drug)}`) {
  const stats = S.me?.statistics === false ? Promise.resolve({ why: 'Statistics are not open to you here.' })
    : api(`/api/events/statistics?product=${encodeURIComponent(drug)}`).then((got) => ({ got }), (err) => ({ why: err.message }));
  const [events, st] = await Promise.all([api(`/api/events?${query}`), stats]);
  // the statistics' own count of cases is the pair's over the whole release: the row keeps its own
  const by = new Map((st.got ? named(st.got) : []).map(({ cases, ...s }) => [s.pt.toLowerCase(), s]));
  const rows = named(events).map((e) => ({ ...by.get(e.pt.toLowerCase()), ...e, product: drug }));
  return { rows, statistics: st.why || null, missing: events.not_available || {} };
}

// Each event's EBGM at the quarter before, added to the rows given as it comes: it takes longer than
// the rows, which do not wait for it. None for a drug with no statistics, or a release that cannot say.
async function priorQuarter(drug) {
  const got = await api(`/api/events/prior-quarter?product=${encodeURIComponent(drug)}`).catch(() => null);
  return new Map((got ? named(got) : []).map((r) => [r.pt.toLowerCase(), r]));
}

// each table drawn, by its own box, so a table drawn again in a page drawn again is still found
let made = 0;
const tables = new WeakMap();
const tableOf = (el) => tables.get(el?.closest?.('[data-et]'));

class Table {
  constructor(el, o) {
    this.id = String(++made);
    this.el = el;
    this.o = o;
    this.view = o.view || 'events';
    this.rows = o.rows || null;
    this.noStats = o.rows ? o.noStatistics ?? null : null;
    this.whyNoLabel = o.notAvailable?.label || '';
    this.find = '';
    this.ticks = {};
    this.widths = {};
    this.drawnCols = '';
    this.shown = this.pageSize();
    this.openAs(o.opened?.key);
    // what was kept, where it is of the kind kept; anything else reads as the table opens
    const kept = (k, fallback, ok) => { const v = viewChoice(`${this.view}.${k}`, fallback); return ok(v) ? v : fallback; };
    this.on = kept('columns', o.shown || OPENS_WITH, Array.isArray).filter((id) => this.listedColumns().some((c) => c.id === id));
    this.sort = null;
    this.bounds = kept('bounds', {}, (v) => !!v && typeof v === 'object' && Object.values(v).every((n) => typeof n === 'number'));
    this.limits = limitsOf(o.thresholds);
  }

  pageSize() { return listLength('events_shown'); }
  productOf(r) { return this.o.product ? this.o.product(r) : r.product || this.o.drug || ''; }
  keyOf(r) { return this.o.rowKey ? String(this.o.rowKey(r)) : `${this.productOf(r)}|${r.pt.toLowerCase()}`; }
  rowAt(key) { return this.rows?.find((r) => this.keyOf(r) === key); }
  // a part of this table's own, never one of a table a host draws inside its open row
  part(sel) { return this.el.querySelector(`[data-et="${this.id}"]`)?.querySelector(`:scope > ${sel}`); }

  // the columns every table draws, those its rows can fill
  own() { return fixedColumns().filter((c) => this.available(c)); }
  // what Columns lists: a host's marked `listed`, then the table's own
  listedColumns() { return [...(this.o.columns || []).filter((c) => c.listed).map((c) => this.hostColumn(c)), ...listedColumns()]; }

  available(c) { return this.noStats == null || (c.group !== 'statistics' && !c.stats); }
  always() { return this.o.always?.columns || []; }
  // a column the table always draws shows; one Columns lists shows where it may and is chosen
  showing(c) { return this.available(c) && (this.always().includes(c.id) || this.on.includes(c.id)); }
  hostColumn(c) { return { words: ['Most first', 'Fewest first'], first: 'desc', group: 'cases', menuWords: c.head, ...c, value: c.sort || null, held: c.after === 'start' }; }

  // the columns of the table, in their order: a host's with `after: 'start'` before the event's
  // name and held with it, one with `after` naming a column after that one, the rest at the end
  columns() {
    const host = (this.o.columns || []).filter((c) => !c.listed || this.on.includes(c.id)).map((c) => this.hostColumn(c));
    const chosen = this.listedColumns().filter((c) => !c.listed && this.showing(c));
    // all the statistics together, then what else is chosen, and Trend after them, never between
    const own = this.own();
    const all = [...host.filter((c) => c.after === 'start'), ...own.filter((c) => c.id !== 'trend'),
      ...chosen.filter((c) => c.group === 'statistics'), ...chosen.filter((c) => c.group !== 'statistics'), ...own.filter((c) => c.id === 'trend')];
    host.filter((c) => c.after && c.after !== 'start').forEach((c) => {
      const at = all.findIndex((x) => x.id === c.after);
      all.splice(at < 0 ? all.length : at + 1, 0, c);
    });
    return [...all, ...host.filter((c) => !c.after)];
  }
  column(id) { return [...this.columns(), ...this.listedColumns()].find((c) => c.id === id); }
  // what Columns lists: each column it shows or hides, and whether it shows, always or at all
  optional() { return this.listedColumns().map((c) => ({ c, on: this.showing(c), always: this.always().includes(c.id), available: this.available(c) })); }
  // a ticked column's values, in its order, each with the rows it keeps under every other narrowing
  tickValues(c) {
    const counts = new Map();
    this.listed(c.id).forEach((r) => { const v = c.ticks.value(r); counts.set(v, (counts.get(v) || 0) + 1); });
    // every value a row holds is listed, so the menu keeps its length as other heads narrow
    const held = new Set((this.rows || []).map((r) => c.ticks.value(r)));
    const order = c.ticks.order || [...held].sort();
    return order.filter((v) => held.has(v)).map((v) => ({ value: v, words: v, count: counts.get(v) || 0, tip: c.ticks.tips?.[v] }));
  }

  // this column's thresholds, none where it has none
  limitsOn(c) { return this.limits[c.id] || []; }
  // The screens that apply, each as its head's values now stand: every one given, whether or not its
  // column shows, or with `screensOfColumns` those of the columns showing; none where the rows have
  // no statistics to read them on.
  screens() {
    if (this.noStats != null) return [];
    const showing = this.o.screensOfColumns ? new Set(this.columns().map((c) => c.id)) : null;
    return Object.entries(this.limits).filter(([id]) => !showing || showing.has(id)).map(([, on]) => screenOfLimits(on)).filter((when) => when.length);
  }
  // the rows under every narrowing but the column `except` names: a host's own, the words found,
  // the bounds of the columns showing, the ticks and, unless `all`, the thresholds: every screen,
  // which a row the host's `beyond` keeps passes
  listed(except = null, all = false) {
    if (!this.rows) return [];
    const typed = this.find.trim().toLowerCase();
    const cols = this.columns().filter((c) => c.id !== except);
    const bounded = cols.filter((c) => c.bound && this.bounds[c.id] != null);
    const ticked = cols.filter((c) => c.ticks && this.ticks[c.id]);
    const screens = this.screens();
    return this.rows.filter((r) => (!this.o.only || this.o.only(r))
      && (!typed || r.pt.toLowerCase().includes(typed))
      && bounded.every((c) => { const v = c.value(r); return v != null && v >= this.bounds[c.id]; })
      && ticked.every((c) => this.ticks[c.id].includes(c.ticks.value(r)))
      && (all || this.o.beyond?.(r) || meetsThresholds(r, screens)));
  }

  // how many rows meet every threshold, whether or not a host's `beyond` keeps others in view too
  meeting() { const screens = this.screens(); return this.listed(null, true).filter((r) => meetsThresholds(r, screens)).length; }

  // the order: the column the person sorts by, then the table's own order (a host's `order`, else
  // the most cases this quarter first and then by name); an empty value last either way
  order() { return this.o.order || [['newest', 'desc'], ['event', 'asc']]; }
  // the person's sort holds while its column shows
  sorting() {
    const s = this.sort && this.columns().find((c) => c.id === this.sort.by)?.value ? this.sort : null;
    return s || { by: this.order()[0][0], dir: this.order()[0][1] };
  }
  sorted() {
    const keys = [[this.sorting().by, this.sorting().dir], ...this.order()].map(([by, dir]) => [this.column(by)?.value, dir]).filter(([v]) => v);
    const cmp = (a, b, dir) => {
      if (a == null || a === '' || b == null || b === '') return (a == null || a === '') - (b == null || b === '');
      const d = typeof a === 'string' ? a.localeCompare(b) : a - b;
      return dir === 'desc' ? -d : d;
    };
    return this.listed().map((r) => [keys.map(([v]) => v(r)), r])
      .sort((a, b) => keys.reduce((d, [, dir], i) => d || cmp(a[0][i], b[0][i], dir), 0)).map(([, r]) => r);
  }

  // the person's columns and bounds, kept for their next visit
  keep(k, v) { keepView(`${this.view}.${k}`, v); }
  setSort(by, dir) { this.sort = { by, dir }; this.paint(); }
  // a head's arrow: the column's own first way, the other, then the table's own order
  cycleSort(c) {
    const s = this.sorting();
    if (s.by !== c.id) this.setSort(c.id, c.first);
    else if (s.dir === c.first) this.setSort(c.id, c.first === 'desc' ? 'asc' : 'desc');
    else { this.sort = null; this.paint(); }
  }
  // one of a column's thresholds typed, put back or (none) taken off
  setLimit(id, i, at) {
    this.limits = { ...this.limits, [id]: this.limits[id].map((l, j) => (j === i ? { ...l, at } : l)) };
    this.shown = this.pageSize();
    this.paint();
  }
  clearLimits() {
    this.limits = Object.fromEntries(Object.entries(this.limits).map(([id, on]) => [id, on.map((l) => ({ ...l, at: null }))]));
    this.shown = this.pageSize();
    this.paint();
  }
  setBound(id, v) {
    const next = { ...this.bounds };
    if (v == null) delete next[id]; else next[id] = v;
    this.bounds = next;
    this.keep('bounds', next);
    this.shown = this.pageSize();
    this.paint();
  }
  setTicks(id, ticked) { this.ticks = { ...this.ticks, [id]: ticked }; this.shown = this.pageSize(); this.paint(); }
  toggle(id) {
    this.on = this.listedColumns().map((c) => c.id).filter((x) => (x === id ? !this.on.includes(x) : this.on.includes(x)));
    this.keep('columns', this.on);
    this.paint();
  }
  // a head is pressed while it leads the order or narrows the table
  pressed(c) { return this.sorting().by === c.id || this.boundOn(c) || !!this.ticks[c.id]; }
  boundOn(c) { return (!!c.bound && this.bounds[c.id] != null) || this.limitsOn(c).some((l) => l.at != null); }
  sortState(c) { const s = this.sorting(); return s.by === c.id ? s.dir : 'none'; }
  sorts(c) { return !!(c.value && c.words); }
  headTip(c) {
    const b = this.bounds[c.id];
    const limited = limitsWords(this.limitsOn(c));
    const bound = limited ? `Showing only those with ${limited}.` : b != null && c.bound ? `Showing only those ${c.bound.words.toLowerCase()} ${num(b)}${c.bound.unit ? ` ${c.bound.unit}` : ''}.` : '';
    return [c.tip, bound].filter(Boolean).map((s) => (/[.:]$/.test(s) ? s : `${s}.`)).join(' ');
  }

  shell() {
    const find = this.o.find === false ? '' : `<div class="search-bar oa-et-find"><span class="search-icon">${icon('search')}</span><input class="search-input" type="search" data-et-find autocomplete="off" aria-label="Find an event" placeholder="Find an event"></div>`;
    return `<div class="oa-et" data-et="${this.id}">
      <div class="oa-et-tools">${find}<p class="oa-et-count"></p>${this.o.thresholds ? quartersHtml(releaseQuarter(), releaseQuarter(1)) : ''}
        <button type="button" class="btn oa-et-columns" data-act="et-columns" aria-haspopup="menu">${icon('bullets')}<span class="oa-et-columns-words">Columns</span></button></div>
      <div class="dashboard-frame oa-et-frame"></div>
      <div class="oa-et-foot"></div></div>`;
  }

  headHtml(c, i) {
    const cls = [c.cls, c.held && 'oa-et-held', c.name && 'oa-et-name'].filter(Boolean).join(' ');
    const at = c.held && i ? ` style="left: var(--et-held-${i}, 0px)"` : '';
    const menu = c.menu !== false && c.menu !== null;
    const words = menu
      ? `<button type="button" class="oa-et-head" data-act="et-head" data-col="${esc(c.id)}" aria-haspopup="menu" aria-pressed="${this.pressed(c)}" ${tip(this.headTip(c))}>${esc(c.head)}${this.sorts(c) ? '' : icon('chevronDown')}</button>`
      : `<span class="oa-et-head" ${tip(this.headTip(c))}>${esc(c.head)}</span>`;
    const arrow = this.sorts(c) ? `<button type="button" class="oa-et-sorter" data-act="et-cycle" data-col="${esc(c.id)}" aria-label="${esc(`Sort by ${c.head}`)}">${sortMark(this.sortState(c))}</button>` : '';
    const sort = { asc: 'ascending', desc: 'descending' }[this.sortState(c)];
    return `<th scope="col" data-col="${esc(c.id)}"${cls ? ` class="${cls}"` : ''}${sort ? ` aria-sort="${sort}"` : ''}${at}><span class="oa-et-headline">${words}${arrow}</span></th>`;
  }

  // With `markMeeting`, a row that meets every threshold the table was given (of the columns
  // showing, with `screensOfColumns`) has each statistic whose own threshold that is marked, as a
  // host marks one past its threshold: the same rows whether the table shows only those or every
  // event, whatever the heads' values are now.
  pastGiven(r, c) {
    if (!this.o.markMeeting || c.group !== 'statistics' || this.noStats != null) return '';
    const showing = this.o.screensOfColumns ? new Set(this.columns().map((col) => col.id)) : null;
    const given = (this.o.thresholds || []).filter((when) => !showing || showing.has(when[0].column));
    const own = given.find((when) => when[0].column === c.id);
    return own && meetsThresholds(r, given) ? `Past its threshold: ${conditionWords(own)}` : '';
  }

  cellHtml(c, r, i) {
    const marked = c.name ? '' : this.o.mark?.(r, c.id) || this.pastGiven(r, c);
    const cls = [c.cls, c.held && 'oa-et-held', c.name && 'oa-et-name', marked && 'oa-et-marked'].filter(Boolean).join(' ');
    const at = c.held && i ? ` style="left: var(--et-held-${i}, 0px)"` : '';
    const tag = c.name ? 'th scope="row"' : 'td';
    return `<${tag}${cls ? ` class="${cls}"` : ''}${at}${marked ? ` ${tip(marked)}` : ''}>${c.cell(r, this)}</${c.name ? 'th' : 'td'}>`;
  }

  rowHtml(r, cols) {
    const cls = this.o.rowClass?.(r) || '';
    const press = this.o.open ? ' data-act="et-row" tabindex="0"' : '';
    const open = this.o.opened ? ` aria-expanded="${this.keyOf(r) === this.openKey}"` : '';
    return `<tr data-key="${esc(this.keyOf(r))}"${cls ? ` class="${esc(cls)}"` : ''}${press}${open}>${cols.map((c, i) => this.cellHtml(c, r, i)).join('')}</tr>`;
  }

  // the rows of the page shown, by the host's pager or the table's own: the first page, and more
  // with each press of Show more
  page(rows) {
    if (this.o.pager) return this.o.pager(rows);
    const more = rows.length > this.shown ? ` <span class="oa-dot">·</span> <button type="button" class="oa-link" data-act="et-more">Show ${num(Math.min(this.pageSize(), rows.length - this.shown))} more</button>` : '';
    return { rows: rows.slice(0, this.shown), html: more ? `<span>Showing ${num(this.shown)} of ${num(rows.length)}${more}</span>` : '' };
  }

  bodyHtml(cols) {
    if (this.problem) return `<tr><td colspan="${cols.length}" class="oa-faint">${esc(this.problem)}</td></tr>`;
    if (!this.rows) return `<tr class="oa-et-loading"><td colspan="${cols.length}">${skeletonRows(4)}</td></tr>`;
    const rows = this.sorted();
    const page = this.page(rows);
    this.footing = page.html || '';
    if (!rows.length) {
      const why = !this.rows.length ? 'No event is reported with these filters.' : this.find.trim() ? `No event matches "${esc(this.find.trim())}".` : 'No event is left. Change a choice in a head\'s menu.';
      return `<tr><td colspan="${cols.length}" class="oa-faint oa-et-none">${why}</td></tr>`;
    }
    return page.rows.map((r) => this.rowHtml(r, cols)).join('');
  }

  // what the thresholds hide, in one line at the table's foot
  limitWords() {
    if (!this.o.thresholds || !this.rows) return '';
    return `<span class="oa-et-limit-words">${hiddenWords(this.listed(null, true).length - this.listed().length)}</span>`;
  }

  footHtml() {
    const stats = this.noStats ? `<span class="oa-faint">${esc(this.noStats)}</span>`
      : this.columns().some((c) => c.group === 'statistics') ? `<span>The statistics are worked out once for the whole release. <a class="oa-link" href="/methods?open=ebgm">How these are worked out</a></span>` : '';
    return `${this.footing || ''}${this.limitWords()}${stats}`;
  }

  paint() {
    if (!this.el.isConnected) return;
    if (!this.el.querySelector(`[data-et="${this.id}"]`)) {
      this.el.innerHTML = this.shell();
      tables.set(this.el.querySelector('[data-et]'), this);
    }
    const frame = this.part('.oa-et-frame');
    const cols = this.columns();
    const sig = cols.map((c) => c.id).join('|');
    const table = frame.querySelector(':scope > table');
    this.footing = '';
    if (table && sig === this.drawnCols) {
      // the same columns: the heads stay, so an open menu keeps its button, and only the rows change
      cols.forEach((c) => {
        const th = table.tHead.querySelector(`th[data-col="${CSS.escape(c.id)}"]`);
        const head = th.querySelector('[data-act="et-head"]');
        if (head) { head.setAttribute('aria-pressed', String(this.pressed(c))); head.dataset.tip = this.headTip(c); }
        th.querySelector('.oa-sort')?.setAttribute('data-sort', this.sortState(c));
        const sort = { asc: 'ascending', desc: 'descending' }[this.sortState(c)];
        if (sort) th.setAttribute('aria-sort', sort); else th.removeAttribute('aria-sort');
      });
      table.tBodies[0].innerHTML = this.bodyHtml(cols);
    } else {
      const x = frame.scrollLeft;
      frame.innerHTML = `<table class="dashboard-table oa-et-table"><thead><tr>${cols.map((c, i) => this.headHtml(c, i)).join('')}</tr></thead><tbody>${this.bodyHtml(cols)}</tbody></table>`;
      frame.scrollLeft = x;
      this.drawnCols = sig;
    }
    const n = this.listed().length;
    this.part('.oa-et-tools > .oa-et-count:not(.oa-et-quarters)').innerHTML = !this.rows ? '<span class="skeleton oa-count-skeleton"></span>'
      : this.o.thresholds && this.listed(null, true).length !== n ? countWords(this.meeting(), this.listed(null, true).length) : `<strong>${num(n)}</strong> ${n === 1 ? 'event' : 'events'}`;
    this.part('.oa-et-foot').innerHTML = this.footHtml();
    const added = this.on.filter((id) => !(this.o.shown || OPENS_WITH).includes(id) && this.available(this.column(id))).length;
    this.part('.oa-et-tools .oa-et-columns-words').textContent = added ? `Columns (${added})` : 'Columns';
    this.hold();
    this.placeOpen();
  }

  // The row a host opens: one at a time, so opening one closes any other. A row opened again is
  // drawn again; the same row staying open keeps its cell as the host drew it.
  openAs(key) {
    const k = key == null ? null : String(key);
    if (this.openRow && k === this.openKey) return;
    this.openRow?.remove();
    Object.assign(this, { openKey: k, openRow: null, openBox: null });
  }

  // a press on a row opens it, or closes it if it is open, and redraws no row, so nothing above moves
  openOrClose(key) {
    this.openAs(key === this.openKey ? null : key);
    [...(this.part('.oa-et-frame > table')?.tBodies[0].rows || [])].filter((r) => r.dataset.key)
      .forEach((r) => r.setAttribute('aria-expanded', String(r.dataset.key === this.openKey)));
    this.placeOpen();
  }

  // The open row's cell under its row each time the rows are drawn, spanning the row: the host
  // draws in it once, as it opens, and it is kept as the rows are sorted, narrowed or paged, and
  // closed once its row is not on the page. A row opened while the rows come opens once they have.
  placeOpen() {
    if (this.openKey == null || !this.o.opened) return;
    const table = this.part('.oa-et-frame > table');
    const row = [...(table?.tBodies[0].rows || [])].find((r) => r.dataset.key === this.openKey);
    if (!row) {
      if (!this.rows) return;
      // a row named from outside and further down the list than shown yet comes into the page
      const at = this.o.pager ? -1 : this.sorted().findIndex((r) => this.keyOf(r) === this.openKey);
      if (at >= this.shown && !this.openRow) { this.shown = at + 1; this.paint(); return; }
      this.openAs(null);
      this.o.opened.gone?.();
      return;
    }
    const fresh = !this.openRow;
    if (fresh) {
      this.openRow = document.createElement('tr');
      this.openRow.className = 'oa-et-opened';
      this.openRow.innerHTML = '<td><div class="oa-et-opened-box"></div></td>';
      this.openBox = this.openRow.cells[0].firstChild;
    }
    this.openRow.cells[0].colSpan = table.tHead.rows[0].cells.length;
    row.after(this.openRow);
    this.fitOpen();
    if (fresh) this.o.opened.draw(this.openBox, this.rowAt(this.openKey));
  }

  // the open row's box is as wide as the frame shows and held at its left, so it stays in view as
  // a wide table scrolls sideways, and keeps that width as the window changes
  fitOpen() {
    const frame = this.part('.oa-et-frame');
    if (!this.openBox || !frame) return;
    this.openBox.style.width = `${frame.clientWidth}px`;
    if (this.watched === frame) return;
    this.sizes ??= new ResizeObserver(() => this.fitOpen());
    this.sizes.observe(frame);
    this.watched = frame;
  }

  // Each column keeps the widest it has been drawn, so narrowing the rows moves no head; the
  // columns held at the left stand at their offsets; a name cut short on a phone tips its whole.
  hold() {
    const table = this.part('.oa-et-frame > table');
    if (!table || !this.rows) return;
    const heads = [...table.tHead.rows[0].cells];
    heads.forEach((h) => {
      const id = h.dataset.col;
      const w = Math.max(this.widths[id] || 0, h.offsetWidth);
      this.widths[id] = w;
      h.style.minWidth = `${w}px`;
    });
    heads.filter((h) => h.classList.contains('oa-et-held')).forEach((h, i) => table.style.setProperty(`--et-held-${i}`, `${h.offsetLeft - heads[0].offsetLeft}px`));
    table.querySelectorAll(':scope > tbody > tr > .oa-et-name').forEach((cell) => {
      if (cell.scrollWidth > cell.clientWidth) cell.dataset.tip = cell.textContent.trim(); else delete cell.dataset.tip;
    });
  }

  async load() {
    const asked = `${this.o.drug}\n${this.o.query || ''}`;
    this.asked = asked;
    try {
      const got = await drugEvents(this.o.drug, this.o.query);
      if (this.asked !== asked) return;
      Object.assign(this, { rows: got.rows, noStats: got.statistics, whyNoLabel: got.missing.label, problem: '', priorDue: !got.statistics });
      if (!got.statistics) priorQuarter(this.o.drug).then((prior) => {
        if (this.asked !== asked) return;
        this.rows = this.rows.map((r) => { const p = prior.get(r.pt.toLowerCase()); return { ...r, ebgm_prior: p?.ebgm ?? null, eb05_prior: p?.eb05 ?? null }; });
        this.priorDue = false;
        this.paint();
      });
    } catch (err) {
      this.problem = `Could not load the events: ${err.message}`;
    }
    this.paint();
  }
}

// Draws the events table into `el` and gives back its handle: `paint()` draws it again after a
// host's own state changed, `update(options)` takes new rows or options, `listed()` the rows now
// narrowed to, in no order, and `opened()` the key of the row open. The options are listed on the
// page-extension page.
export function eventsTable(el, options = {}) {
  const t = new Table(el, options);
  t.paint();
  if (!options.rows && options.drug) t.load();
  return {
    paint: () => t.paint(),
    listed: () => t.listed(),
    opened: () => t.openKey,
    update(next) {
      Object.assign(t.o, next);
      if ('opened' in next) t.openAs(next.opened?.key);
      if ('thresholds' in next) {
        t.limits = limitsOf(next.thresholds);
        t.el.innerHTML = '';
        t.drawnCols = '';
      }
      if (next.rows) Object.assign(t, { rows: next.rows, noStats: next.noStatistics ?? null, whyNoLabel: next.notAvailable?.label || '' });
      if (next.drug || next.query) { t.rows = null; t.load(); }
      t.paint();
    },
  };
}

actions({
  'et-head': (el) => { const t = tableOf(el); headMenu(el, t, t.column(el.dataset.col)); },
  'et-cycle': (el) => { const t = tableOf(el); t.cycleSort(t.column(el.dataset.col)); },
  'et-columns': (el) => columnsMenu(el, tableOf(el)),
  'et-forms': (el) => { const t = tableOf(el); formsMenu(el, t, t.rowAt(el.closest('tr').dataset.key)); },
  'et-more': (el) => { const t = tableOf(el); t.shown += t.pageSize(); t.paint(); },
  // a press on a row opens or closes its cell, where the host draws in one, then does what the host
  // says; one on a link or a button in it does what that does
  'et-row': (el, e) => {
    if (e?.target?.closest?.('a, button, input, label')) return;
    const t = tableOf(el);
    if (t.o.opened) t.openOrClose(el.dataset.key);
    t.o.open?.(t.rowAt(el.dataset.key), e);
  },
});

document.addEventListener('input', (e) => {
  if (!e.target.matches?.('[data-et-find]')) return;
  const t = tableOf(e.target);
  t.find = e.target.value;
  t.shown = t.pageSize();
  t.paint();
});
