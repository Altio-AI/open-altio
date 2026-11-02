/* The events table's menus (eventstable.js), and the tick-box menu any page may open. A head's
   menu sorts the whole table and narrows it, to the rows at or above a bound typed in it or to the
   values ticked; Columns shows or hides the statistics and the facts about the cases; an event
   whose forms' labels differ lists each form's answer. Every menu is placed inside the window
   (place's fit) and draws itself again in place as its choices change, keeping its height. */

import { actions } from './events.js';
import { limitName, limitText, opWords, wholeLimit } from './eventthresholds.js';
import { icon } from './icons.js';
import { formsSplit, labelLink, labelRules } from './labels.js';
import { choice, place, popMenu } from './overlays.js';
import { api } from './server.js';
import { S } from './state.js';
import { esc, tip } from './util.js';

let at = null; // the menu open: { menu, draw, table?, col?, tick?, all? }

function open(anchor, cls, state) {
  const menu = popMenu(anchor, state.draw(), `oa-et-menu ${cls}`);
  place(menu, anchor, { fit: true });
  at = { ...state, menu };
  menu.addEventListener('toggle', (e) => { if (e.newState === 'closed' && at?.menu === menu) at = null; });
  return menu;
}

// the open menu drawn again in place, the control pressed keeping the focus
function redraw() {
  if (!at?.menu.isConnected) return;
  const had = document.activeElement?.closest?.('.oa-et-menu [data-act]');
  const which = had && `[data-act="${had.dataset.act}"]${had.dataset.v ? `[data-v="${CSS.escape(had.dataset.v)}"]` : ''}${had.dataset.dir ? `[data-dir="${had.dataset.dir}"]` : ''}`;
  at.menu.innerHTML = at.draw();
  if (which) at.menu.querySelector(which)?.focus({ preventScroll: true });
}

// The values ticked after one is pressed: null while every value is ticked.
function toggled(ticked, v, all) {
  const now = ticked ?? all;
  const next = now.includes(v) ? now.filter((x) => x !== v) : all.filter((x) => x === v || now.includes(x));
  return next.length === all.length ? null : next;
}

// Tick boxes, each value with its count, then Deselect all while every box is ticked and Show all
// once any is not: one of them is always drawn, so ticking never changes the menu's height.
function ticksHtml(heading, values, ticked) {
  const on = (v) => ticked == null || ticked.includes(v);
  const every = values.every((x) => on(x.value));
  return `${heading ? `<p class="menu-heading">${esc(heading)}</p>` : ''}
    <div class="oa-choices">${values.map((x) => choice(on(x.value), x.words, x.count ?? null, `data-act="et-tick" data-v="${esc(x.value)}"${x.tip ? ` ${tip(x.tip)}` : ''}`)).join('')}</div>
    <p class="oa-et-menu-line"><button type="button" class="oa-link" data-act="et-tick-all">${every ? 'Deselect all' : 'Show all'}</button></p>`;
}

// A menu of tick boxes under `anchor`: `values` [{ value, words, count, tip }] (or a function that
// gives them each time the menu draws), `ticked` the values ticked (null: every one), `heading`
// above the boxes, `foot` (html) under them, and `onChange(ticked)` told each change, with null
// once every value is ticked again.
export function tickMenu(anchor, { values, ticked = null, heading = '', foot = '', onChange = () => {} }) {
  let now = ticked;
  const list = () => (typeof values === 'function' ? values() : values);
  const set = (next) => { now = next; onChange(now); };
  return open(anchor, 'oa-tick-menu', {
    draw: () => `${ticksHtml(heading, list(), now)}${foot ? `<p class="menu-footnote">${foot}</p>` : ''}`,
    tick: (v) => set(toggled(now, v, list().map((x) => x.value))),
    all: () => set(now == null ? [] : null),
  });
}

// A head's menu ----------------------------------------------------------------------------------

const flip = (dir) => (dir === 'desc' ? 'asc' : 'desc');

// A value typed where it stands: changed from where it started it reads bold, with a reset arrow
// whose room is always kept.
function typed({ attrs, label, value, words, unit, changed, whole, max, reset }) {
  return `<label class="oa-et-bound"><span>${esc(words)}</span><input class="oa-et-typeover" type="number" min="0"${max == null ? '' : ` max="${max}"`} step="${whole ? 1 : S.release.event_thresholds.threshold_step}" inputmode="${whole ? 'numeric' : 'decimal'}" ${attrs} data-changed="${changed}" value="${value}" aria-label="${esc(label)}">${unit ? `<span>${esc(unit)}</span>` : ''}<button type="button" class="icon-btn oa-et-reset" ${reset} data-state="${changed ? 'on' : 'off'}" aria-label="${esc(`Put back ${label}`)}" ${tip('Put it back')}>${icon('reset')}</button></label>`;
}

// each value of the column's thresholds, or its one At least value; Show every event takes every screen off
function boundHtml(t, c) {
  const limits = t.limitsOn(c);
  const on = t.boundOn(c) || t.screens().length > 0;
  const line = `<p class="oa-et-menu-line"><button type="button" class="oa-link" data-act="et-unbound" data-state="${on ? 'on' : 'off'}">Show every event</button></p>`;
  if (limits.length) {
    return `<p class="menu-heading">Show only</p>${limits.map((l, i) => {
      const words = `${limitName(l)} ${opWords(l)}`;
      return typed({ attrs: `data-et-limit="${esc(c.id)}" data-i="${i}"`, label: words, value: limitText(l), words, changed: l.at !== l.start, whole: wholeLimit(l), reset: `data-act="et-relimit" data-i="${i}"` });
    }).join('')}${line}`;
  }
  const b = t.bounds[c.id];
  const { words = 'At least', unit = '', whole = false, max = null } = c.bound;
  return `<p class="menu-heading">Show only</p>${typed({ attrs: `data-et-bound="${esc(c.id)}"`, label: `${c.head}: ${words}${unit ? `, ${unit}` : ''}`, value: b ?? '', words, unit, changed: b != null, whole, max, reset: 'data-act="et-unbound"' })}${line}`;
}

function headHtml(t, c) {
  const parts = [];
  if (c.value && c.words) {
    const s = t.sorting();
    const pick = (dir, words) => choice(s.by === c.id && s.dir === dir, words, null, `data-act="et-sort" data-dir="${dir}"`, { radio: true });
    parts.push(`<p class="menu-heading">Sort</p><div class="oa-choices">${pick(c.first, c.words[0])}${pick(flip(c.first), c.words[1])}</div>`);
  }
  if (c.ticks) parts.push(ticksHtml(c.ticks.heading, t.tickValues(c), t.ticks[c.id] ?? null));
  else if (c.bound) parts.push(boundHtml(t, c));
  const own = c.ticks ? `${c.ticks.foot ? `${esc(c.ticks.foot)} ` : ''}Counts are events in the list before ${esc(c.head)} narrows it.`
    : '';
  const foot = [t.o.foot?.(c.id) || '', own].filter(Boolean).join(' ');
  return `${parts.join('')}${foot ? `<p class="menu-footnote">${foot}</p>` : ''}`;
}

export function headMenu(anchor, t, c) {
  const values = () => t.tickValues(c).map((x) => x.value);
  return open(anchor, 'oa-et-head-menu', {
    table: t,
    col: c,
    draw: () => headHtml(t, c),
    tick: (v) => t.setTicks(c.id, toggled(t.ticks[c.id] ?? null, v, values())),
    all: () => t.setTicks(c.id, t.ticks[c.id] == null ? [] : null),
  });
}

// Columns ----------------------------------------------------------------------------------------

const GROUPS = [['statistics', 'Statistics'], ['cases', 'About the cases']];
function columnsHtml(t) {
  const listed = t.optional();
  const groups = GROUPS.map(([group, heading]) => {
    const own = listed.filter((x) => x.c.group === group);
    const shown = own.filter((x) => x.available);
    const body = !shown.length ? `<p class="menu-note">${esc(t.noStats || 'None for these rows.')}</p>`
      : `<div class="oa-choices">${shown.map((x) => (x.always
        ? `<div class="menu-item oa-choice oa-et-always" ${tip(t.o.always?.tip || 'Always shown')}><span class="oa-et-no-tick" aria-hidden="true"></span><span class="menu-choice-words">${esc(x.c.menuWords)}</span></div>`
        : choice(x.on, x.c.menuWords, null, `data-act="et-col" data-v="${x.c.id}"`))).join('')}</div>`;
    return `<p class="menu-heading">${heading}</p>${body}`;
  }).join('');
  const foot = t.o.foot?.('columns');
  return `${groups}${foot ? `<p class="menu-footnote">${foot}</p>` : ''}`;
}

export function columnsMenu(anchor, t) {
  return open(anchor, 'oa-et-columns-menu', { table: t, draw: () => columnsHtml(t) });
}

// Forms differ: each label read for the drug's forms, linked, with what it says of the event; a form
// with no label read says so in the flags' own words
export async function formsMenu(anchor, t, row) {
  const got = await api(`/api/labels/product?product=${encodeURIComponent(t.productOf(row))}`).catch(() => ({}));
  const families = row.label?.forms || [];
  const labels = (got.labels || []).filter((l) => l.forms.some((f) => families.some(([form]) => form === f)));
  const said = (forms) => families.filter(([form]) => forms.includes(form)).map(([, answer]) => labelRules().words[answer]);
  const linked = labels.map((l) => `<p class="oa-et-form">${labelLink(l)}: ${esc([...new Set(said(l.forms))].join(', '))}</p>`);
  const alone = families.filter(([form]) => !labels.some((l) => l.forms.includes(form)))
    .map((f) => { const w = formsSplit({ families: [f] }); return `<p class="oa-et-form">${esc(w.charAt(0).toUpperCase() + w.slice(1))}</p>`; });
  const html = `<p class="menu-heading">Each form's label</p>${[...linked, ...alone].join('')}`;
  return open(anchor, 'oa-et-forms-menu', { draw: () => html });
}

// What a press in the open menu does --------------------------------------------------------------

actions({
  'et-tick': (el) => { at?.tick?.(el.dataset.v); redraw(); },
  'et-tick-all': () => { at?.all?.(); redraw(); },
  'et-sort': (el) => { at.table.setSort(at.col.id, el.dataset.dir); redraw(); },
  'et-unbound': () => {
    const t = at.table, id = at.col.id;
    t.clearLimits();
    t.setBound(id, null);
    redraw();
  },
  'et-relimit': (el) => { at.table.setLimit(at.col.id, +el.dataset.i, at.table.limitsOn(at.col)[+el.dataset.i].start); redraw(); },
  'et-col': (el) => { at.table.toggle(el.dataset.v); redraw(); },
});

// a number typed narrows the table at once; one it cannot take marks the box and changes nothing
document.addEventListener('input', (e) => {
  const d = e.target.dataset;
  if ((!d?.etBound && !d?.etLimit) || !at?.table) return;
  const limit = d.etLimit ? at.table.limitsOn(at.col)[+d.i] : null;
  const { whole = false, max = null } = limit ? { whole: wholeLimit(limit) } : at.col.bound;
  const raw = e.target.value.trim();
  const v = raw === '' ? null : Number(raw);
  const bad = e.target.validity.badInput || (v != null && (!Number.isFinite(v) || v < 0 || (max != null && v > max) || (whole && !Number.isInteger(v))));
  e.target.setAttribute('aria-invalid', String(bad));
  if (bad) return;
  if (limit) at.table.setLimit(at.col.id, +d.i, v); else at.table.setBound(d.etBound, v);
  at.menu.querySelector('[data-act="et-unbound"][data-state]:not(.oa-et-reset)')?.setAttribute('data-state', at.table.boundOn(at.col) || at.table.screens().length ? 'on' : 'off');
  const changed = limit ? v !== limit.start : v != null;
  e.target.dataset.changed = String(changed);
  e.target.closest('.oa-et-bound').querySelector('.oa-et-reset').setAttribute('data-state', changed ? 'on' : 'off');
});
