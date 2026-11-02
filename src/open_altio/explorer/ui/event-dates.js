/* An opened event's dates (event.js): the window every pane counts in, the period it is compared
   with and which date counts a case, said at the start of the event's line and changed in one Dates
   menu. The window opens on the release's newest quarter; the menu offers the last four quarters,
   all dates and days picked on a calendar, and a host's own windows (slot event-window) between
   them. Before the window is every day from the event's first case, or the same length just
   before it. Counted by the date the event began, only the reports that give that date to the day
   count, and the menu says what share of the event's cases that is. */

import { esc, tip } from './util.js';
import { choice, closeMenus, closedByThisClick, openedBy, place, popMenu } from './overlays.js';
import { icon } from './icons.js';
import { slot } from './host.js';
import { S, releaseEnd } from './state.js';
import { MONTHS, quarterStart } from './util.js';

// a day as the line writes it: 4 Jan 2004
export const plainDay = (iso) => { const [y, m, d] = iso.split('-'); return `${+d} ${MONTHS[+m - 1]} ${y}`; };
const atUtc = (d) => Date.parse(`${d}T00:00:00Z`);
const isoDay = (t) => new Date(t).toISOString().slice(0, 10);
const dayBefore = (iso) => isoDay(atUtc(iso) - 864e5);
const quarterWords = (iso) => `${iso.slice(0, 4)} Q${Math.ceil(+iso.slice(5, 7) / 3)}`; // 2026 Q2
const latestQuarter = () => quarterStart(S.release.quarters[1]);
// the first day of each of the last n quarters, the newest first
function lastQuarters(n) {
  const out = [latestQuarter()];
  while (out.length < n) { const t = new Date(atUtc(out.at(-1))); t.setUTCMonth(t.getUTCMonth() - 3); out.push(isoDay(t)); }
  return out;
}

// the first day the window can start: the event's first case by the date that counts
export const firstDay = (ev) => ev.first[ev.dateField] || ev.first.received || quarterStart(S.release.quarters[0]);

// The window of a kind: { kind, from, to, before: { from, to } or null, compared, said }. A host's
// window comes with its own days and words.
export function windowOf(ev, kind, compared, days = null) {
  const end = releaseEnd(), first = firstDay(ev);
  const from = kind === 'quarter' ? latestQuarter() : kind === 'four' ? lastQuarters(4).at(-1) : kind === 'all' ? first : days.from;
  const to = (days && days.to) || end;
  const start = from < first ? first : from;
  let before = null;
  if (kind !== 'all' && start > first) {
    const len = Math.round((atUtc(to) - atUtc(start)) / 864e5) + 1;
    before = compared === 'same' ? { from: isoDay(atUtc(start) - len * 864e5), to: dayBefore(start) } : { from: first, to: dayBefore(start) };
  }
  return { kind, from: start, to, before, compared, said: days?.said ?? KIND_WORDS[kind] ?? '' };
}

// While the event's first day is on its way the line holds these words, unseen: the window's as they
// will most likely read, its first day the widest there is, so the words wrap as the dates will and
// nothing under the line moves when they come.
function heldWords(ev) {
  const from = latestQuarter(), by = ev.dateField === 'event' ? BY_EVENT : '';
  return `Before 28 May 2001 to ${plainDay(dayBefore(from))} → window ${plainDay(from)} to ${plainDay(releaseEnd())}${KIND_WORDS[ev.carried?.kind] ?? KIND_WORDS.quarter}${by}`;
}

// The line's dates, in time order: "Before 12 Jul 2001 to 31 Mar 2026 → window 1 Apr 2026 to
// 30 Jun 2026, the newest quarter", pressed for the Dates menu
const KIND_WORDS = { quarter: ', the newest quarter', four: ', the last four quarters', all: ', all dates', days: '' };
const BY_EVENT = ', counted by the date the reaction started';
export function datesLine(ev) {
  const w = ev.window;
  if (!w) return `<span class="oa-ev-dates" aria-hidden="true"><span class="skeleton oa-ev-dates-skeleton">${esc(heldWords(ev))}</span>${icon('chevronDown')}</span>`;
  const day = (iso, k = '') => `<span class="oa-ev-day"${k ? ` data-k="${k}"` : ''}>${esc(plainDay(iso))}</span>`;
  const before = w.before ? `Before ${day(w.before.from)} to ${day(w.before.to)} → window ` : 'Window ';
  const by = ev.dateField === 'event' ? BY_EVENT : '';
  const said = `${w.before ? `Before ${plainDay(w.before.from)} to ${plainDay(w.before.to)}, then the window` : 'The window'} ${plainDay(w.from)} to ${plainDay(w.to)}${w.said}${by}`;
  return `<button type="button" class="oa-ev-dates" data-act="ev-dates" aria-haspopup="menu" aria-label="${esc(said)}. Press to change the dates">${before}${day(w.from, 'from')} to ${day(w.to, 'to')}${esc(w.said)}${by}${icon('chevronDown')}</button>`;
}

// ---- the Dates menu: the window, what it is compared with, and which date counts a case ----------

let open = null; // { ev, menu, anchor, dated }
const pick = (on, words, attrs, off = '', note = '') => choice(on, words, null, `${attrs}${off ? ` aria-disabled="true" ${tip(off)}` : ''}`, { radio: true, note });
function menuHtml(d) {
  const { ev } = d, w = ev.window;
  const kind = (k, words) => pick(w.kind === k, words, `data-act="ev-window" data-k="${k}"`);
  // a host's windows after each of the frame's own, as `after` names it
  const host = (after) => slot('event-window', { ...ev.context(), after });
  const sameOff = w.kind === 'all' ? 'All dates leave nothing before the window' : '';
  const dated = d.dated == null ? '' : `Only reports that give this date can be counted: ${d.dated}% of these cases`;
  return `<p class="menu-heading">The window</p><div class="oa-choices">
      ${kind('quarter', `The newest quarter (${quarterWords(latestQuarter())})`)}${host('quarter')}
      ${kind('four', 'The last four quarters')}${host('four')}
      ${kind('all', 'All dates')}${host('all')}
      ${pick(w.kind === 'days', 'Pick days…', 'data-act="ev-window" data-k="days"')}</div>
    <p class="menu-heading">Compared with</p><div class="oa-choices">
      ${pick(w.compared === 'before' && w.kind !== 'all', 'The period before the window', 'data-act="ev-compared" data-v="before"', sameOff)}
      ${pick(w.compared === 'same' && w.kind !== 'all', 'The same length just before', 'data-act="ev-compared" data-v="same"', sameOff)}</div>
    <p class="menu-heading">Count cases by</p><div class="oa-choices oa-ev-countby">
      ${pick(ev.dateField === 'received', 'The date FDA received the report', 'data-act="ev-countby" data-v="received"')}
      ${pick(ev.dateField === 'event', 'The date the reaction started', 'data-act="ev-countby" data-v="event"', '', dated || ' ')}</div>`;
}
export function datesMenu(el, ev) {
  if (!ev?.window || closedByThisClick()) return; // pressing the line again closes its menu
  const d = { ev, menu: null, anchor: el, dated: null };
  d.menu = popMenu(el, menuHtml(d), 'oa-ev-dates-menu');
  place(d.menu, el, { fit: true });
  openedBy(el);
  open = d;
  d.menu.addEventListener('toggle', (e) => { if (e.newState === 'closed' && open === d) open = null; });
  ev.datedShare().then((n) => { d.dated = n; if (open === d) d.menu.innerHTML = menuHtml(d); }).catch(() => {});
}

// a host's window as its choice carries it: its kind, its first day, its last (the release's end
// when not given) and the words the line says after the dates
export const hostWindow = (el) => ({ from: el.dataset.from, to: el.dataset.to || '', said: el.dataset.said || '' });
// a host's window of `kind` as the menu would offer it now, for the window to follow the date that
// counts; null when the host offers none or it is greyed
export function hostWindowNow(ev, kind) {
  const box = document.createElement('div');
  box.innerHTML = ['quarter', 'four', 'all'].map((after) => slot('event-window', { ...ev.context(), after })).join('');
  const el = [...box.querySelectorAll('[data-act="ev-window"]')].find((x) => x.dataset.k === kind && x.getAttribute('aria-disabled') !== 'true');
  return el ? hostWindow(el) : null;
}

// ---- the calendar for the window's days (Pick days): the first day, then the last ---------------
const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
let cal = null; // { ev, k, view: 'days' | 'months' | 'years', y, m, menu, anchor, then }
const ymd = (iso) => iso.split('-').map(Number);
const bounds = (ev) => ({ first: firstDay(ev), last: releaseEnd(), from: ev.window.from, to: ev.window.to });
function calHtml() {
  const { ev, k, view, y, m } = cal;
  const b = bounds(ev);
  const [fy] = ymd(b.first), [ly] = ymd(b.last);
  const head = (words, prev, next, act) => `<div class="oa-ev-cal-head">
      <button type="button" class="icon-btn oa-ev-cal-step" data-act="ev-cal-step" data-d="-1" aria-label="Earlier" ${prev ? '' : 'disabled'}><span class="oa-ev-cal-back">${icon('chevronRight')}</span></button>
      <button type="button" class="oa-ev-cal-title" data-act="${act}" ${act ? '' : 'disabled'}>${words}</button>
      <button type="button" class="icon-btn oa-ev-cal-step" data-act="ev-cal-step" data-d="1" aria-label="Later" ${next ? '' : 'disabled'}>${icon('chevronRight')}</button></div>`;
  const words = k === 'from' ? 'The window starts on' : 'The window ends on';
  if (view === 'years') {
    const ys = Array.from({ length: ly - fy + 1 }, (_, i) => fy + i);
    return `<p class="menu-heading">${words}</p>${head(`${fy} to ${ly}`, false, false, '')}
      <div class="oa-ev-cal-grid oa-ev-cal-years">${ys.map((x) => `<button type="button" class="oa-ev-cal-cell" data-act="ev-cal-year" data-v="${x}" aria-pressed="${x === y}">${x}</button>`).join('')}</div>`;
  }
  if (view === 'months') {
    const mm = (i) => String(i + 1).padStart(2, '0');
    return `<p class="menu-heading">${words}</p>${head(String(y), y > fy, y < ly, 'ev-cal-years')}
      <div class="oa-ev-cal-grid oa-ev-cal-wide">${MONTHS.map((w, i) => {
        const out = `${y}-${mm(i)}-31` < b.first || `${y}-${mm(i)}-01` > b.last;
        return `<button type="button" class="oa-ev-cal-cell" data-act="ev-cal-month" data-v="${i + 1}" aria-pressed="${i + 1 === m}" ${out ? 'disabled' : ''}>${w}</button>`;
      }).join('')}</div>`;
  }
  const lead = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7; // Monday first
  const count = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const iso = (d) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  const picked = k === 'from' ? b.from : b.to;
  const cells = Array.from({ length: lead }, () => '<span class="oa-ev-cal-cell oa-ev-cal-blank"></span>');
  for (let d = 1; d <= count; d += 1) {
    const v = iso(d), out = v < b.first || v > b.last, inSpan = v >= b.from && v <= b.to;
    cells.push(`<button type="button" class="oa-ev-cal-cell" data-act="ev-cal-day" data-v="${v}" aria-pressed="${v === picked}" ${inSpan ? 'data-span="true"' : ''} ${out ? 'disabled' : ''} aria-label="${plainDay(v)}">${d}</button>`);
  }
  return `<p class="menu-heading">${words}</p>${head(`${MONTHS[m - 1]} ${y}`, iso(1) > b.first, iso(count) < b.last, 'ev-cal-months')}
    <div class="oa-ev-cal-grid">${WEEKDAYS.map((w) => `<span class="oa-ev-cal-wd">${w}</span>`).join('')}${cells.join('')}</div>`;
}
const calPaint = () => { if (cal?.menu?.isConnected) { cal.menu.innerHTML = calHtml(); place(cal.menu, cal.anchor, { fit: true }); } };
// the calendar hangs from the window's first or last day in the line
export function calOpen(el, ev, k, then = false) {
  const b = bounds(ev);
  const [y, m] = ymd(k === 'from' ? b.from : b.to);
  cal = { ev, k, view: 'days', y, m, menu: null, anchor: el, then };
  cal.menu = popMenu(el, calHtml(), 'oa-ev-cal');
  place(cal.menu, el, { fit: true });
  el.setAttribute('aria-expanded', 'true');
  cal.menu.addEventListener('toggle', (e) => { if (e.newState === 'closed') el.setAttribute('aria-expanded', 'false'); });
}
// a day picked sets that end of the window, the other kept, the two in order; Pick days asks the last next
function calPick(v) {
  const { ev, k, then } = cal;
  const b = bounds(ev);
  let from = k === 'from' ? v : b.from, to = k === 'to' ? v : b.to;
  if (from > to) [from, to] = [to, from];
  closeMenus();
  cal = null;
  ev.setWindow('days', { days: { from, to } });
  if (then) requestAnimationFrame(() => { const el = ev.box.querySelector('.oa-ev-day[data-k="to"]'); if (el) calOpen(el, ev, 'to'); });
}

// what a press in the Dates menu or the calendar does
export const DATES_ACTS = {
  'ev-window': (el) => {
    const d = open;
    if (!d || el.getAttribute('aria-disabled') === 'true') return;
    const { ev } = d, k = el.dataset.k;
    closeMenus();
    if (k === 'days') { const from = ev.box.querySelector('.oa-ev-day[data-k="from"]'); if (from) calOpen(from, ev, 'from', true); return; }
    ev.setWindow(k, el.dataset.from ? { days: hostWindow(el) } : {});
  },
  'ev-compared': (el) => {
    const d = open;
    if (!d || el.getAttribute('aria-disabled') === 'true') return;
    const w = d.ev.window;
    closeMenus();
    if (w.compared !== el.dataset.v) d.ev.setWindow(w.kind, { compared: el.dataset.v, days: w });
  },
  'ev-countby': (el) => { const d = open; if (!d) return; closeMenus(); d.ev.setDateField(el.dataset.v); },
  'ev-cal-step': (el) => {
    if (!cal) return;
    const d = +el.dataset.d;
    if (cal.view === 'days') { const t = new Date(Date.UTC(cal.y, cal.m - 1 + d, 1)); cal.y = t.getUTCFullYear(); cal.m = t.getUTCMonth() + 1; } else cal.y += d;
    calPaint();
  },
  'ev-cal-months': () => { if (cal) { cal.view = 'months'; calPaint(); } },
  'ev-cal-years': () => { if (cal) { cal.view = 'years'; calPaint(); } },
  'ev-cal-year': (el) => { if (cal) { cal.y = +el.dataset.v; cal.view = 'months'; calPaint(); } },
  'ev-cal-month': (el) => { if (cal) { cal.m = +el.dataset.v; cal.view = 'days'; calPaint(); } },
  'ev-cal-day': (el) => { if (cal) calPick(el.dataset.v); },
};
