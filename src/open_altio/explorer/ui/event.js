/* An event opened under its row: what a host draws in the cell an events table opens under a row
   (eventstable.js `opened`), with openedEvent(element, { drug, row, ... }), on a drug's Events tab
   (scope.js) and wherever a host mounts it. Top down: the row's copy, its numbers under the table's
   heads; the line, the window's dates (event-dates.js), then each filter with its x and + Add a filter
   (event-filters.js), and Clear all; the bar, the tabs Overview, Compared and Cases with its count,
   and a host's place at the right; a host's line under the bar; then the pane of the tab shown.
   Row, line and bar stay at the top while the event is in view (event-stick.js), and the event is no
   taller than the window, the tab showing scrolling inside it (event.css).

   Each pane is drawn by the part registered for it, registerEventPane(name, { label, order, draw }):
   draw(pane, ctx) once as its tab first shows, giving back { update(ctx), close() }, either one
   optional; update is told each change of the dates or the filters, for every pane drawn, shown or
   not, and close as the event closes. A pane no part registered shows a plain placeholder. A pane
   registered as `case`, with no tab, shows a case in place of the panes (ctx.openCase). ctx is in
   docs/reference/page-extension.md. Each event keeps its window, its date and its filters while
   the page is open, so a filter stays with the event it was set on. */

import { ACTS, actions } from './events.js';
import { slot } from './host.js';
import { icon } from './icons.js';
import { closeMenus, closedByThisClick, openedBy } from './overlays.js';
import { api } from './server.js';
import { productLabel, whoOn } from './state.js';
import { esc, num, tip } from './util.js';
import { DATES_ACTS, datesLine, datesMenu, hostWindowNow, windowOf } from './event-dates.js';
import { FIELDS, FILTER_ACTS, addFilter, valueWords } from './event-filters.js';
import { COPY, restack, stick, stickY, sticks } from './event-stick.js';

// a drug and an event as a sentence says them: valsartan's hypotension
const drugWords = (drug) => { const t = productLabel(drug); return /^[A-Z][a-z]/.test(t) ? t[0].toLowerCase() + t.slice(1) : t; };
const inSentence = (words) => (/^[A-Z][a-z]/.test(words) ? words[0].toLowerCase() + words.slice(1) : words);

// ---- the panes ------------------------------------------------------------------------------------
const PANES = new Map();
const TABS = { overview: { label: 'Overview', order: 1 }, compared: { label: 'Compared', order: 2 }, cases: { label: 'Cases', order: 3 } };
export function registerEventPane(name, { label, order, draw }) {
  PANES.set(name, { label: label ?? TABS[name]?.label ?? name, order: order ?? TABS[name]?.order ?? 9, draw });
}
// the tabs in order: the three every event has, and any other a part registered with a label
function tabs() {
  const all = new Map(Object.entries(TABS));
  for (const [name, p] of PANES) if (name !== 'case') all.set(name, { label: p.label, order: p.order });
  return [...all].sort(([, a], [, b]) => a.order - b.order);
}
// an address may name the tab an event opens on (?tab=cases)
const tabAsked = () => { const t = new URLSearchParams(location.search).get('tab'); return tabs().some(([v]) => v === t) ? t : ''; };

// whether an opened event is capped to the window, its tab scrolling inside (event.css): a pane then
// holds no room of its own
const capped = () => window.matchMedia('(min-height: 480px)').matches;

// ---- each event's own state ---------------------------------------------------------------------
const kept = new Map(); // key -> what the event keeps while the page is open
const opened = new Map(); // the box -> the event drawn in it
const eventOf = (el) => opened.get(el.closest('.oa-ev')?.parentElement);

class Event {
  constructor(box, o) {
    this.box = box;
    this.drug = o.drug;
    this.row = o.row;
    this.reactions = o.reaction ? [o.reaction].flat() : o.row.reactions || [o.row.pt];
    this.base = o.query || `product=${encodeURIComponent(o.drug)}`;
    this.screens = o.screens || [];
    this.classes = o.classes !== false;
    this.key = `${o.drug}|${this.reactions.join('|').toLowerCase()}`;
    // a read-only view keeps nothing: what the person set on that drug's own event stays its own
    const was = (!o.from && kept.get(this.key)) || { window: null, dateField: 'received', filters: new Map(), tab: '', first: {} };
    if (!o.from) kept.set(this.key, was);
    this.was = was;
    this.tab = o.tab || tabAsked() || was.tab || 'overview';
    // opened from another drug's event, read only: it starts with that event's window, date and
    // filters, each time it is opened from it, and on its Overview
    this.from = o.from || null;
    this.back = o.back || null;
    if (this.from) {
      was.dateField = this.from.dateField;
      was.filters = new Map(this.from.filters.map(({ field, values }) => [field, [...values]]));
      was.window = null;
      const { received_from: rf, received_to: rt, event_from: ef, event_to: et } = this.from.window;
      this.carried = { kind: this.from.kind, compared: this.from.compared || 'before', days: { from: rf || ef, to: rt || et } };
      this.tab = o.tab || 'overview';
    }
    this.cases = null;
    this.drawn = new Map(); // pane name -> what its draw gave back
    this.caseId = null;
  }

  get window() { return this.was.window; }
  get dateField() { return this.was.dateField; }
  get filters() { return this.was.filters; }
  get first() { return this.was.first; }

  reactionsAs(name) { return this.reactions.map((r) => `${name}=${encodeURIComponent(r)}`).join('&'); }
  // a field with no value ticked: no case shows
  get none() { return [...this.filters.values()].some((v) => !v.length); }
  // the window's days under the names of the date that counts, and the period before it
  windowDays() {
    const w = this.window;
    if (!w) return {};
    return this.dateField === 'event' ? { event_from: w.from, event_to: w.to } : { received_from: w.from, received_to: w.to };
  }
  // the product's settings and the filters, and the window's days unless `period` is 'all'
  query(extra = {}, { period = 'window', without = '' } = {}) {
    const p = new URLSearchParams(this.base);
    for (const [field, values] of this.filters) {
      if (field === without) continue;
      p.delete(field);
      values.forEach((v) => p.append(field, v));
    }
    if (period === 'window') for (const [k, v] of Object.entries(this.windowDays())) p.set(k, v);
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return p.toString();
  }
  queryWithout(field) { return this.query({}, { without: field }); }

  // What every pane is handed (docs/reference/page-extension.md), made again for each change.
  context() {
    const w = this.window;
    return {
      drug: this.drug,
      reaction: [...this.reactions],
      row: this.row,
      window: this.windowDays(),
      before: { before_from: w?.before?.from || '', before_to: w?.before?.to || '' },
      dateField: this.dateField,
      kind: w?.kind || '',
      compared: w?.compared || 'before',
      filters: [...this.filters].map(([field, values]) => ({ field, values: [...values] })),
      none: this.none,
      cases: this.cases,
      screens: this.screens,
      classes: this.classes && whoOn(),
      caseId: this.caseId,
      from: this.from && { drug: this.from.drug, reaction: [...this.from.reaction] },
      query: (extra, how) => this.query(extra, how),
      setFilter: (field, values) => this.setFilter(field, values),
      clearFilter: (field) => this.setFilter(field, null),
      openCase: (caseId) => this.openCase(caseId),
      back: () => this.showTab('cases'),
      slot: (name) => slot(name, this.context()),
      // a host's mark beside a drug's name in a pane's table
      drugMark: (drug) => slot('event-drug-mark', { ...this.context(), drug }),
    };
  }

  // ---- what changes it ----------------------------------------------------------------------------
  setWindow(kind, { compared = this.window?.compared || 'before', days = null, quiet = false } = {}) {
    this.was.window = windowOf(this, kind, compared, days);
    if (!quiet) this.changed();
  }
  setFilter(field, values) {
    if (values == null) this.filters.delete(field); else this.filters.set(field, [...values]);
    this.changed();
  }
  async setDateField(field) {
    if (field === this.dateField) return;
    this.was.dateField = field;
    if (!this.first[field]) await this.firstDay(field).catch(() => {});
    const w = this.window;
    // a host's window is asked for again on the other date, the last four quarters where it has none
    const own = ['quarter', 'four', 'all', 'days'].includes(w.kind);
    const days = own ? w : hostWindowNow(this, w.kind);
    this.setWindow(days || own ? w.kind : 'four', { days: days || null });
  }
  // the event's first day by a date, as its row counts it: no filter moves the window
  async firstDay(field) {
    const by = field === 'event' ? '&by=event' : '';
    const t = await api(`/api/timeline?grain=day${by}&${this.base}&${this.reactionsAs('pt')}`);
    this.first[field] = t.rows[0]?.[0] || '';
  }
  // the share of the event's cases under its filters that give the date the reaction started
  async datedShare() {
    const t = await api(`/api/timeline?grain=year&by=event&${this.query({}, { period: 'all' })}&${this.reactionsAs('pt')}`);
    const dated = t.rows.reduce((a, [, n]) => a + n, 0), all = dated + (t.undated || 0);
    if (t.rows[0] && !this.first.event) this.first.event = t.rows[0][0];
    return all ? Math.round((100 * dated) / all) : 0;
  }

  // the line, the count and every pane drawn follow a change
  changed() {
    this.cases = null;
    this.box.querySelector('.oa-ev-line')?.style.removeProperty('min-height');
    this.paintLine();
    this.paintCount();
    this.count();
    const ctx = this.context();
    for (const [, got] of this.drawn) got?.update?.(ctx);
    restack();
  }
  // the Cases tab's count: the event's cases in the window under its filters
  async count() {
    const asked = this.query();
    this.asked = asked;
    let n = 0;
    if (!this.none) n = (await api(`/api/events/group?${asked}&${this.reactionsAs('reaction')}`).catch(() => ({ cases: null }))).cases;
    if (this.asked !== asked) return;
    this.cases = n;
    this.paintCount();
  }

  // ---- drawing ------------------------------------------------------------------------------------
  html() {
    const id = this.key.replace(/[^A-Za-z0-9]+/g, '-');
    const tab = ([v, t]) => `<button type="button" class="tabs-line-tab oa-ev-tab" role="tab" id="oa-ev-tab-${v}-${esc(id)}" aria-selected="${this.tab === v}" aria-controls="oa-ev-pane-${v}-${esc(id)}" data-act="ev-tab" data-v="${v}">${esc(t.label)}${v === 'cases' ? ' <span class="oa-kind-count oa-ev-count"></span>' : ''}</button>`;
    const pane = ([v]) => `<div class="oa-ev-pane" data-pane="${v}" id="oa-ev-pane-${v}-${esc(id)}" role="tabpanel" aria-labelledby="oa-ev-tab-${v}-${esc(id)}" hidden></div>`;
    return `${COPY}<div class="oa-ev">
      <div class="oa-ev-linewrap"><div class="oa-strip oa-ev-line"></div></div>
      <div class="oa-ev-bar"><div class="tabs-line oa-ev-tabs" role="tablist" aria-label="${esc(this.row.pt || this.reactions.join(', '))}">${tabs().map(tab).join('')}</div>
        <span class="oa-ev-acts">${this.from ? this.backHtml() : slot('event-bar-end', this.context())}</span></div>
      <div class="oa-ev-under">${slot('event-under-bar', this.context())}</div>
      ${tabs().map(pane).join('')}<div class="oa-ev-pane" data-pane="case" hidden></div>
    </div>`;
  }
  // Back to the event it was opened from: a read-only view has no next step of a host's
  backHtml() {
    if (!this.from || !this.back) return '';
    const event = this.from.row?.pt || this.from.reaction.join(', ');
    const words = `Back to ${drugWords(this.from.drug)}'s ${inSentence(event)}`;
    return `<button type="button" class="btn oa-ev-back" data-act="ev-back" ${tip(`${words}, on its Compared tab`)}>${esc(words)}</button>`;
  }
  paintLine() {
    const line = this.box.querySelector('.oa-ev-line');
    if (!line) return;
    // whether duplicates are in (the Cases tab's Include duplicates) is no field of the line
    const items = [...this.filters].filter(([field]) => FIELDS[field]).map(([field, values]) => {
      const name = FIELDS[field]?.words || field, words = values.length ? valueWords(field, values) : 'None';
      return `<span class="oa-strip-item"><button type="button" class="oa-strip-edit" data-act="ev-addfilter" data-row="${esc(field)}" aria-haspopup="menu" ${tip(`${name}: ${words}`)}><span class="oa-strip-name">${esc(name)}</span><span class="oa-strip-value">${esc(words)}</span></button>
        <button type="button" class="icon-btn oa-strip-x" data-act="ev-unfilter" data-row="${esc(field)}" aria-label="Remove the ${esc(name)} filter">${icon('close')}</button></span>`;
    });
    // a host's quiet note in the line where no filter is on
    const note = items.length ? '' : slot('event-line-note', this.context());
    const add = '<button type="button" class="oa-link oa-ev-addfilter" data-act="ev-addfilter" aria-haspopup="menu">+ Add a filter</button>';
    const others = items.length ? `<span class="oa-strip-items oa-ev-items">${items.join('')}</span>` : note;
    line.innerHTML = `${datesLine(this)}<span class="oa-ev-others"><span class="oa-dot">·</span>${others}${add}</span>${items.length ? '<button type="button" class="oa-link oa-clear oa-ev-clear" data-act="ev-clear">Clear all</button>' : ''}`;
  }
  paintCount() {
    const el = this.box.querySelector('.oa-ev-count');
    if (el) el.innerHTML = this.cases == null ? '<span class="skeleton oa-ev-count-skeleton"></span>' : num(this.cases);
  }
  // a pane shown: drawn by its part the first time, the placeholder where no part drew it
  showPane(v) {
    const pane = this.box.querySelector(`.oa-ev-pane[data-pane="${v}"]`);
    this.box.querySelectorAll('.oa-ev-pane').forEach((x) => { x.hidden = x !== pane; });
    if (this.drawn.has(v)) return pane;
    const part = PANES.get(v);
    if (part?.draw) this.drawn.set(v, part.draw(pane, this.context()) || null);
    else pane.innerHTML = '<p class="oa-faint oa-ev-placeholder">Nothing is shown here yet.</p>';
    if (!part?.draw) this.drawn.set(v, null);
    return pane;
  }
  // A tab shown: the bar stays where it is. Once the bar has stuck at the top, the new tab starts
  // right under the layers that stay there; before it has, nothing above the tab changes, and a
  // shorter tab keeps the room it needs so the page cannot shrink under the reader.
  showTab(v) {
    if (!tabs().some(([t]) => t === v)) return;
    const bar = this.box.querySelector('.oa-ev-bar'), page = this.box.closest('.frame-page') || document.scrollingElement;
    const before = bar.getBoundingClientRect().top;
    const stuck = sticks(this.box) && Math.abs(before - stickY(this.box, 3)) < 1;
    this.tab = v;
    this.was.tab = v;
    // a case read in place closes as a tab shows, so it hears of the event's changes no more
    if (this.caseId) { this.drawn.get('case')?.close?.(); this.drawn.delete('case'); }
    this.caseId = null;
    this.box.querySelectorAll('.oa-ev-tab').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.v === v)));
    this.box.querySelectorAll('.oa-ev-pane').forEach((x) => { x.style.minHeight = ''; });
    const pane = this.showPane(v);
    if (stuck) {
      const under = stickY(this.box, 4);
      if (!capped()) pane.style.minHeight = `${Math.max(0, window.innerHeight - under)}px`;
      page.scrollTop += pane.getBoundingClientRect().top - under;
    }
    const moved = bar.getBoundingClientRect().top - before;
    if (Math.abs(moved) > 0.5) { if (!capped()) pane.style.minHeight = `${pane.offsetHeight + Math.abs(moved)}px`; page.scrollTop += moved; }
    restack();
  }
  // a case read in place, in the pane registered as `case`, else in the case window
  openCase(caseId) {
    const [era, key] = String(caseId).split('/');
    if (!PANES.get('case')?.draw) { ACTS['case-jump']({ dataset: { era, key } }); return; }
    this.caseId = `${era}/${key}`;
    this.drawn.get('case')?.close?.();
    this.drawn.delete('case');
    this.showPane('case');
  }

  // the event as it opens: its first day, then its window (the newest quarter), its count and its tab
  async start() {
    this.box.innerHTML = this.html();
    opened.set(this.box, this);
    this.paintLine();
    this.paintCount();
    this.showPane(this.tab);
    stick(this.box);
    if (!this.first.received) await this.firstDay('received').catch(() => {});
    if (this.dateField === 'event' && !this.first.event) await this.firstDay('event').catch(() => {});
    if (this.carried && !this.window) this.carryWindow();
    if (!this.window) this.setWindow('quarter', { quiet: true });
    if (!this.box.isConnected) return;
    const line = this.box.querySelector('.oa-ev-line'), held = line.getBoundingClientRect().height;
    this.changed();
    // dates shorter than the words the line held keep that room as the event opens, so nothing under
    // the line moves; the next change of the line fits its own words
    if (line.getBoundingClientRect().height < held) { line.style.minHeight = `${held}px`; restack(); }
  }
  // the window carried from the event it was opened from: one of the frame's own kinds as that
  // kind, a host's asked of the host again for this drug, else its days
  carryWindow() {
    const { kind, compared, days } = this.carried;
    if (['quarter', 'four', 'all'].includes(kind)) { this.setWindow(kind, { compared, quiet: true }); return; }
    const host = kind === 'days' ? null : hostWindowNow(this, kind);
    this.setWindow(host ? kind : 'days', { compared, days: host || days, quiet: true });
  }
  close() {
    for (const [, got] of this.drawn) got?.close?.();
    this.drawn.clear();
    opened.delete(this.box);
  }
}

// An event opened in `element`, the box an events table opened under its row: `drug` and `row` as the
// table has them; `query` the product's settings as /api/events was asked (product= the drug when
// not given); `reaction` the event's preferred terms where the row is a group; `screens` a host's
// thresholds for the panes; `tab` the tab it opens on; `classes` false to keep every drug class out
// of its panes. Gives back the event's handle.
export function openedEvent(element, options) {
  for (const [box, ev] of opened) if (!box.isConnected) ev.close();
  const ev = new Event(element, options);
  ev.start();
  // the table closes the row by taking its cell away: the panes are told
  const gone = new MutationObserver(() => { if (!element.isConnected) { ev.close(); gone.disconnect(); } });
  const body = element.closest('tbody');
  if (body) gone.observe(body, { childList: true });
  return {
    context: () => ev.context(),
    setFilter: (field, values) => ev.setFilter(field, values),
    showTab: (v) => ev.showTab(v),
    paint: () => { ev.paintLine(); restack(); },
  };
}

actions({
  ...DATES_ACTS,
  ...FILTER_ACTS,
  'ev-dates': (el) => datesMenu(el, eventOf(el)),
  'ev-tab': (el) => eventOf(el)?.showTab(el.dataset.v),
  // + Add a filter, or a filter's own words in the line, open the menu under + Add a filter
  'ev-addfilter': (el) => {
    const ev = eventOf(el);
    if (!ev) return;
    const anchor = ev.box.querySelector('.oa-ev-addfilter');
    if (closedByThisClick() && el === anchor) return;
    addFilter(ev, anchor, el.dataset.row);
    openedBy(anchor);
  },
  'ev-unfilter': (el) => eventOf(el)?.setFilter(el.dataset.row, null),
  'ev-back': (el) => eventOf(el)?.back?.(),
  // every filter goes; the window stays, as it is not a filter
  'ev-clear': (el) => { const ev = eventOf(el); if (!ev) return; closeMenus(); ev.filters.clear(); ev.changed(); },
});

