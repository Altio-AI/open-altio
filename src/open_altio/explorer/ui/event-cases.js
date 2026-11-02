/* An opened event's Cases tab, drawn in the pane the opened event gives it (registerEventPane). A
   toolbar: Find a case by its number, how many cases in the window, Include duplicates with how many
   there are, Columns, Download these cases. Then the cases, in a table that fills the rest of the
   screen and scrolls inside, its heads stuck at its top and the pager always in view under it;
   each head's menu sorts and shows only some (event-heads.js); a case's duplicates open as rows
   under it (event-dups.js); a row opens its case in place (event-case.js, through ctx.openCase),
   ‹ Cases or Escape bringing the table back at the same page with the row marked.

   The tab lists the event's cases in the window the line sets, under the event's filters, from the
   published questions: /api/summary for the counts and each head's values, /api/cases for the
   pages (detail=columns, case_number, sort), /api/timeline for a count alone. A head's pick is the
   event's own filter (ctx.setFilter), so the line names it and every tab counts under it. */

import { registerEventPane } from './event.js';
import { actions } from './events.js';
import { exportDialog } from './exports.js';
import { icon } from './icons.js';
import { closeMenus, closedByThisClick, openedBy, place, popMenu, showProblem } from './overlays.js';
import { api } from './server.js';
import { drugWords, productLabel } from './state.js';
import { esc, num, tip } from './util.js';
import { cellOf, changedColumns, columnsMenu, flipColumn, shownColumns, tableWidth } from './event-cols.js';
import { dupRows, dupsUnder, fitDupLines, keyOf, setAside, toggleDups } from './event-dups.js';
import { filterLines } from './event-words.js';
import { headRow, openHead, paintMenu } from './event-heads.js';
import { PER_MOST, keepPerPage, pagerHtml, pagesOf, perHtml, perPage } from './event-pager.js';
import { sticks, stickY } from './event-stick.js';
const ROOM_UNDER = 12; // under the pager, to the window's foot
const LEAST = 220; // a short window still shows a few cases
const panes = new Set();
// what each event's tab was showing, so a tab drawn again (back from a case) shows the same page
const memory = new Map();

class CasesPane {
  constructor(el, ctx) {
    this.el = el;
    this.asked = 0;
    this.pages = {};
    this.counts = {};
    this.take(ctx);
    const kept = memory.get(this.eventKey) || {};
    this.sort = kept.sort || 'newest';
    this.find = kept.find || '';
    this.page = kept.page || 1;
    this.marked = kept.marked || '';
    this.back = !!kept.marked; // drawn again back from a case: its row is focused once the page shows
    this.shown = 0; // the page drawn, 0 while the first comes
    el.innerHTML = this.shell();
    panes.add(this);
    this.sized = new ResizeObserver(() => this.fit());
    this.sized.observe(el.querySelector('.oa-ec-tools'));
    // shown again, back from a case read in its place: the row of that case in view and focused
    this.seen = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && this.away) { this.away = false; this.cameBack(); }
      if (!e.isIntersecting && el.hidden) this.away = true;
    });
    this.seen.observe(el);
    this.load();
    this.openAsked();
  }

  take(ctx) {
    this.ctx = ctx;
    this.filters = ctx.filters || [];
    this.eventKey = `${ctx.drug}|${(ctx.reaction || []).join('|')}`;
  }
  // the fields whose every box is unticked: no case shows
  get none() { return new Set(this.filters.filter((f) => !f.values.length).map((f) => f.field)); }
  // a case the address names (a copied link) opens in place as the tab first shows
  openAsked() {
    const p = new URLSearchParams(location.search), key = p.get('case');
    if (key && !this.ctx.caseId) this.ctx.openCase(`${p.get('era') || ''}/${key}`);
  }

  remember() { memory.set(this.eventKey, { sort: this.sort, find: this.find, page: this.page, marked: this.marked }); }

  // ---- the question ------------------------------------------------------------------------------
  // the event's question: its drug's settings, its window, its filters and its reactions; `filtered`
  // false leaves out the filters the line names (whether duplicates are in stays)
  question(extra = {}, { filtered = true } = {}) {
    const p = new URLSearchParams(this.ctx.query());
    if (!filtered) this.filters.filter((f) => f.field !== 'dedup').forEach((f) => p.delete(f.field));
    (this.ctx.reaction || []).forEach((r) => p.append('pt', r));
    for (const [k, v] of Object.entries(extra)) { p.delete(k); [v].flat().forEach((x) => p.append(k, x)); }
    return p.toString();
  }
  ticked(key) { return this.filters.find((f) => f.field === key)?.values ?? null; }
  eventName() { return (this.ctx.reaction || []).join(', '); }
  // every role FDA codes, as + Add a filter offers them (rule explorer-drug-counts)
  roles() { return drugWords().roles.map(([code]) => code); }
  dedupAll() { return (this.ticked('dedup') || new URLSearchParams(this.ctx.query()).getAll('dedup')).includes('all'); }

  // ---- asking /api -------------------------------------------------------------------------------
  // everything the tab shows, for the event's question as it is now
  load({ keepPage = false } = {}) {
    // the opened event sets its window as it starts: the tab asks once it has one
    if (!Object.keys(this.ctx.window || {}).length) return;
    const seq = ++this.asked;
    const q = this.question();
    this.summary = null;
    this.pages = {};
    if (!keepPage) this.page = 1;
    this.paint('count', 'tools', 'heads');
    this.el.querySelector('.oa-ec-cases')?.setAttribute('data-state', 'loading');
    api(`/api/summary?${q}`).then((s) => {
      if (seq !== this.asked) return;
      this.summary = s;
      this.paint('count', 'tools', 'heads', 'pager');
      paintMenu(this);
    }).catch(showProblem);
    const clean = this.question({}, { filtered: false });
    if (this.allKey !== clean) {
      this.all = null;
      this.counted(clean).then((n) => { if (this.question({}, { filtered: false }) === clean) { this.all = n; this.allKey = clean; this.paint('count'); } }).catch(showProblem);
    }
    if (this.find) this.countFound();
    this.showPage(this.page);
  }
  // how many cases a question holds, from its counts by year
  counted(q) {
    return (this.counts[q] ??= api(`/api/timeline?grain=year&${q}`).then((t) => t.rows.reduce((a, [, n]) => a + n, 0) + (t.undated || 0)));
  }
  async countFound() {
    const find = this.find;
    const got = await api(`/api/cases?${this.question({ case_number: find })}`).catch(showProblem);
    if (got && this.find === find) { this.found = got.total; this.paint('count', 'pager'); }
  }
  // each role, alone, under the other filters: the Role head's counts; null while they come
  roleCounts() {
    const q = this.question();
    if (this.roleAsk?.q === q) return this.roleAsk.n;
    const ask = { q, n: null };
    this.roleAsk = ask;
    Promise.all(this.roles().map((r) => this.counted(this.question({ prole: r })).then((n) => [r, n])))
      .then((got) => { if (this.roleAsk === ask) { ask.n = Object.fromEntries(got); paintMenu(this); } }).catch(showProblem);
    return null;
  }
  // A field read from the drug's records or the report, its values and counts as + Add a filter asks
  // for them (event-fields.js) under the event's other filters; null while they come
  fieldCounts(key, more) {
    const ctx = this.ctx, reactions = ctx.reaction || [];
    const ev = {
      reactions,
      context: () => ctx,
      queryWithout: (f) => ctx.query({}, { without: f }),
      reactionsAs: (name) => reactions.map((r) => `${name}=${encodeURIComponent(r)}`).join('&'),
    };
    const at = `${key}|${ev.queryWithout(key)}|${ev.reactionsAs('pt')}`;
    const got = (this.fields ??= new Map());
    if (!got.has(at)) {
      got.set(at, null);
      more.values(ev, key).then((rows) => { got.set(at, rows); paintMenu(this); this.paint('heads'); })
        .catch((e) => { got.delete(at); showProblem(e); });
    }
    return got.get(at);
  }
  // one of /api's pages of cases (rule explorer-page-size), kept while the question, sort and find stay
  apiPage(n) {
    const q = this.question({ page: n, sort: this.sort, detail: 'columns', ...(this.find ? { case_number: this.find } : {}) });
    return (this.pages[q] ??= api(`/api/cases?${q}`).catch((e) => { delete this.pages[q]; throw e; }));
  }
  // the cases of the pager's page `p` at this person's cases a page: /api's pages that hold them
  async loadPage(p) {
    const per = perPage();
    const first = await this.apiPage(1);
    const lo = (p - 1) * per, hi = p * per;
    const want = [];
    for (let n = Math.floor(lo / first.size) + 1; (n - 1) * first.size < hi; n += 1) want.push(n);
    const got = await Promise.all(want.map((n) => (n === 1 ? first : this.apiPage(n))));
    const from = lo - (want[0] - 1) * first.size;
    return { cases: got.flatMap((g) => g.cases).slice(from, from + per), total: first.total };
  }
  total() { return this.none.size ? 0 : this.find ? this.found : this.summary?.cases; }
  async showPage(p, then = null) {
    const seq = this.asked, find = this.find, sort = this.sort, per = perPage();
    this.page = p;
    this.remember();
    if (this.none.size) { this.list = []; this.shown = p; this.paint('cases', 'pager', 'count'); then?.(); return; }
    try {
      const got = await this.loadPage(p);
      if (seq !== this.asked || find !== this.find || sort !== this.sort || per !== perPage() || this.page !== p) return;
      this.list = got.cases;
      this.shown = p;
      this.paint('cases', 'pager');
      if (this.back) { this.back = false; this.cameBack(); }
      then?.();
    } catch (err) { showProblem(err); }
  }

  // ---- what a press changes ----------------------------------------------------------------------
  sortBy(v) {
    if (this.sort === v) return;
    this.sort = v;
    this.paint('heads');
    this.el.querySelector('.oa-ec-cases')?.setAttribute('data-state', 'loading');
    this.showPage(1);
  }
  // a head's pick, the event's own filter (the opened event then tells every pane, this one too):
  // null every value (no filter), [] none (no case shows), else those values
  setTicks(key, values) {
    if (values) this.ctx.setFilter(key, values); else this.ctx.clearFilter(key);
  }
  update(ctx) {
    this.take(ctx);
    this.load();
  }
  close() {
    panes.delete(this);
    this.sized.disconnect();
    this.seen.disconnect();
    this.remember();
  }

  // ---- drawing -----------------------------------------------------------------------------------
  shell() {
    return `<div class="oa-ec">
      <div class="oa-et-tools oa-ec-tools">${this.toolsHtml()}</div>
      <div class="oa-ec-cases" data-state="loading"><div class="oa-ec-body">${this.tableHtml()}</div><div class="oa-ec-pager">${pagerHtml(this.page, null)}</div></div></div>`;
  }
  toolsHtml() {
    return `<div class="search-bar oa-et-find oa-ec-find"><span class="search-icon">${icon('search')}</span><input class="search-input oa-ec-find-input" type="search" inputmode="numeric" autocomplete="off" spellcheck="false" aria-label="Find a case by its number" placeholder="Find a case by its number" value="${esc(this.find)}"></div>
      <p class="oa-et-count oa-ec-count">${this.countLine()}</p>
      <label class="oa-ec-dupinc" ${tip('Show the reports the release treats as duplicates of a case too, each marked, and count them. Every report can then be seen and cited.')}><input type="checkbox" class="oa-ec-dupinc-box"${this.dedupAll() ? ' checked' : ''}><span>Include duplicates</span><span class="choice-count oa-ec-dupn">${this.dupCount()}</span></label>
      <div class="oa-ec-buttons"><button type="button" class="btn oa-ec-columns" data-act="ec-columns" aria-haspopup="menu" aria-pressed="${changedColumns()}" ${tip("Pick the columns of this event's cases")}>${icon('bullets')}<span>Columns</span></button><button type="button" class="btn oa-ec-download" data-act="ec-download" ${tip("Download this event's cases in the window, with its filters")}>${icon('download')}<span>Download these cases</span></button></div>`;
  }
  dupCount() { return this.summary ? num(this.summary.set_aside) : ''; }
  // the count: the cases shown of the window's cases (N of M), or of those a typed number finds
  countLine() {
    const s = this.summary, cases = (n) => (n === 1 ? 'case' : 'cases');
    const n = this.none.size ? 0 : this.find ? this.found : s?.cases, of = this.find ? s?.cases : this.all;
    if (n == null || of == null) return '<span class="skeleton oa-count-skeleton"></span>';
    if (n === of && !this.find) return `<strong>${num(n)}</strong> ${cases(n)} in the window`;
    return `<strong>${num(n)}</strong> of ${num(of)} ${cases(of)} in the window`;
  }
  tableHtml() {
    const cols = shownColumns();
    const colgroup = `<colgroup>${['case', ...cols].map((id) => `<col class="oa-ec-c-${id}">`).join('')}</colgroup>`;
    let body;
    if (!this.shown) body = `<tr><td colspan="${cols.length + 1}" class="oa-ec-skeleton">${'<span class="skeleton skeleton-row"></span>'.repeat(3)}</td></tr>`;
    else if (!this.list.length) body = `<tr><td colspan="${cols.length + 1}" class="oa-ec-none">${this.find ? 'No case of this event in the window has a number starting with those digits.' : 'No cases in the window match these filters.'}</td></tr>`;
    else body = this.list.map((c, i) => this.rowHtml(c, i, cols)).join('');
    return `<table class="case-table oa-ec-table" style="min-width:${tableWidth()}">${colgroup}<thead>${headRow(this)}</thead><tbody>${body}</tbody></table>`;
  }
  rowHtml(c, i, cols) {
    const td = (id) => { const [html, cls] = cellOf(id, c); return `<td${cls ? ` class="${cls}"` : ''}>${html}</td>`; };
    const aers = c.era_T === 'legacy' ? ` <span class="oa-era" ${tip("From AERS, FDA's system before FAERS")}>AERS</span>` : '';
    return `<tr class="oa-ec-row" data-act="ec-case" data-i="${i}" data-key="${esc(keyOf(c))}" tabindex="0"${this.marked === keyOf(c) ? ' aria-current="true"' : ''}${setAside(c) ? ' data-aside="true"' : ''}>
      <td><span class="case-key">${esc(c.case_key_T)}</span>${aers}${dupsUnder(this, c)}</td>${cols.map(td).join('')}</tr>${dupRows(this, c, cols)}`;
  }
  paint(...parts) {
    const at = (sel) => this.el.querySelector(sel);
    for (const part of parts) {
      if (part === 'count') { const el = at('.oa-ec-count'); if (el) el.innerHTML = this.countLine(); }
      if (part === 'tools') {
        const box = at('.oa-ec-dupinc-box'); if (box) box.checked = this.dedupAll();
        const n = at('.oa-ec-dupn'); if (n) n.textContent = this.dupCount();
        at('.oa-ec-columns')?.setAttribute('aria-pressed', String(changedColumns()));
      }
      if (part === 'heads') { const head = at('.oa-ec-table thead'); if (head) head.innerHTML = headRow(this); }
      if (part === 'pager') { const el = at('.oa-ec-pager'); if (el) el.innerHTML = pagerHtml(this.shown || this.page, this.total()); }
      if (part === 'cases') {
        // a new page keeps the cases where they were scrolled sideways, its first case at the top
        const body = at('.oa-ec-body');
        if (!body) continue;
        const left = body.scrollLeft;
        body.innerHTML = this.tableHtml();
        body.scrollLeft = left;
        body.scrollTop = 0;
        at('.oa-ec-cases').removeAttribute('data-state');
        fitDupLines(body);
        this.fit();
      }
      if (part === 'rows') {
        const body = at('.oa-ec-table tbody'), cols = shownColumns();
        if (body && this.list?.length) body.innerHTML = this.list.map((c, i) => this.rowHtml(c, i, cols)).join('');
        fitDupLines(at('.oa-ec-body'));
      }
    }
  }
  // The frame takes the height left between the toolbar and the pager once the event's layers have
  // stuck at the window's top (ctx.stuck(), the bottom of those layers, where the opened event gives
  // it), so the pager is always in view and the cases scroll inside it; as tall as its cases at most
  fit() {
    const body = this.el.querySelector('.oa-ec-body'), pager = this.el.querySelector('.oa-ec-pager'), tools = this.el.querySelector('.oa-ec-tools');
    if (!body || !pager || !tools || !this.el.isConnected) return;
    const under = sticks(this.el) ? stickY(this.el, 4) : 0;
    const h = Math.max(LEAST, Math.floor(window.innerHeight - ROOM_UNDER - under - tools.offsetHeight - pager.offsetHeight - 16));
    body.style.height = this.shown ? '' : `${h}px`;
    body.style.maxHeight = `${h}px`;
  }

  // ---- the case in place, back from it, the keyboard -------------------------------------------------
  openAt(i) {
    const c = this.list?.[i];
    if (!c) return;
    this.marked = keyOf(c);
    this.remember();
    this.el.querySelectorAll('tr.oa-ec-row').forEach((r) => { if (r.dataset.key === this.marked) r.setAttribute('aria-current', 'true'); else r.removeAttribute('aria-current'); });
    this.ctx.openCase(`${c.era_T}/${c.case_key_T}`);
  }
  // back from a case: the table as it was, the case's row marked, focused for the arrows and in view
  cameBack() {
    const row = this.el.querySelector(`tr.oa-ec-row[data-key="${CSS.escape(this.marked)}"]`);
    this.fit();
    if (row) { row.focus({ preventScroll: true }); inView(row); }
  }
}

// a row brought into view inside the frame, below its stuck heads
function inView(row) {
  const body = row.closest('.oa-ec-body');
  if (!body) return;
  const head = body.querySelector('thead')?.getBoundingClientRect().height || 0;
  const f = body.getBoundingClientRect(), r = row.getBoundingClientRect();
  if (r.top < f.top + head) body.scrollTop -= f.top + head - r.top;
  else if (r.bottom > f.bottom) body.scrollTop += r.bottom - f.bottom;
}

const paneOf = (el) => [...panes].find((P) => P.el.contains(el));
window.addEventListener('resize', () => panes.forEach((P) => P.fit()));

// cases a page, picked or typed: every tab keeps the first case it shows in view
let perTimer = 0;
function setPerPage(n) {
  if (!Number.isInteger(n) || n < 1 || n > PER_MOST || n === perPage()) return;
  const was = perPage();
  keepPerPage(n);
  for (const P of panes) { if (P.shown) P.showPage(Math.floor(((P.shown - 1) * was) / n) + 1); P.paint('pager'); }
  document.querySelectorAll('.oa-ec-permenu [data-act="ec-perpick"]').forEach((b) => b.setAttribute('aria-checked', String(+b.dataset.v === n)));
}
// Find a case by its number: the cases in the window whose number starts with what is typed
let findTimer = 0;
document.addEventListener('input', (e) => {
  if (e.target.matches?.('.oa-ec-perinput')) { clearTimeout(perTimer); const n = Number(e.target.value); perTimer = setTimeout(() => setPerPage(n), 450); return; }
  if (!e.target.matches?.('.oa-ec-find-input')) return;
  const P = paneOf(e.target);
  if (!P) return;
  clearTimeout(findTimer);
  const typed = e.target.value.replace(/\s+/g, '');
  findTimer = setTimeout(() => {
    if (typed === P.find) return;
    P.find = typed;
    P.found = null;
    P.pages = {};
    P.paint('count');
    if (typed) P.countFound();
    P.el.querySelector('.oa-ec-cases')?.setAttribute('data-state', 'loading');
    P.showPage(1);
  }, 220);
});
// Include duplicates: the event's own duplicates choice, as its other filters, so every count follows
document.addEventListener('change', (e) => {
  if (!e.target.matches?.('.oa-ec-dupinc-box')) return;
  const P = paneOf(e.target);
  if (P) P.setTicks('dedup', e.target.checked ? ['all'] : null);
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.target.matches?.('.oa-ec-perinput')) { clearTimeout(perTimer); setPerPage(Number(e.target.value)); closeMenus(); return; }
  // up and down move between the cases, on to the next or the last page at its edges
  if ((e.key !== 'ArrowDown' && e.key !== 'ArrowUp') || e.altKey || e.metaKey || e.ctrlKey) return;
  const row = e.target.closest?.('tr.oa-ec-row');
  const P = row && e.target === row && paneOf(row);
  if (!P) return;
  e.preventDefault();
  const down = e.key === 'ArrowDown';
  const rows = [...row.closest('tbody').querySelectorAll('tr.oa-ec-row')];
  const next = rows[rows.indexOf(row) + (down ? 1 : -1)];
  if (next) { next.focus({ preventScroll: true }); inView(next); return; }
  const p = P.shown + (down ? 1 : -1);
  if (p < 1 || p > pagesOf(P.total())) return;
  P.showPage(p, () => {
    const now = [...P.el.querySelectorAll('tr.oa-ec-row')];
    const to = down ? now[0] : now.at(-1);
    if (to) { to.focus({ preventScroll: true }); inView(to); }
  });
});

actions({
  'ec-head': (el) => { const P = paneOf(el); if (P) openHead(P, el); },
  // the Columns menu: a column ticked shows in every opened event's table, kept as a view choice
  'ec-columns': (el) => {
    if (closedByThisClick()) return;
    place(popMenu(el, columnsMenu(), 'oa-ec-colmenu'), el, { fit: true });
    openedBy(el);
  },
  'ec-col': (el) => {
    flipColumn(el.dataset.v);
    el.closest('.menu')?.querySelectorAll('[data-act="ec-col"]').forEach((x) => x.setAttribute('aria-checked', String(shownColumns().includes(x.dataset.v))));
    panes.forEach((P) => P.paint('tools', 'cases'));
  },
  'ec-download': (el) => {
    const P = paneOf(el);
    if (!P?.summary) return;
    exportDialog({ cases: P.summary.cases, query: P.question(), lines: [['Product', productLabel(P.ctx.drug)], ['Event', P.eventName()], ...filterLines(P)] });
  },
  // the pager: a page, or the one before or after; the cases then start at the frame's top
  'ec-page': (el) => {
    const P = paneOf(el);
    if (!P || el.getAttribute('aria-disabled') === 'true') return;
    const p = +el.dataset.v;
    if (p < 1 || p > pagesOf(P.total()) || p === P.shown) return;
    P.showPage(p);
  },
  'ec-per': (el) => {
    if (closedByThisClick()) return;
    place(popMenu(el, perHtml(), 'oa-ec-permenu'), el, { fit: true });
    openedBy(el);
  },
  'ec-perpick': (el) => { closeMenus(); setPerPage(+el.dataset.v); },
  'ec-dups': (el, e) => {
    e?.stopPropagation();
    const P = paneOf(el), c = P?.list?.find((x) => keyOf(x) === el.dataset.key);
    if (c) toggleDups(P, c, () => P.paint('rows'));
  },
  'ec-dupcase': (el, e) => { e?.stopPropagation(); paneOf(el)?.ctx.openCase(`${el.dataset.era}/${el.dataset.key}`); },
  'ec-case': (el, e) => {
    if (e?.target?.closest?.('button, a')) return; // a duplicate's own button does its own thing
    paneOf(el)?.openAt(+el.dataset.i);
  },
});

// The pane's part of the opened event's contract: draw(pane, ctx) -> { update(ctx), close() }
export function draw(el, ctx) {
  const P = new CasesPane(el, ctx);
  return { update: (next) => P.update(next), close: () => P.close() };
}
export const CASES_PANE = { label: 'Cases', order: 3, draw };

registerEventPane('cases', CASES_PANE);
