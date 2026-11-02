/* An opened event's + Add a filter (event.js): one menu in the Filters menu's layout and markup
   (filtermenu.js: the fields on the left, the open field's values on the right; on a phone one pane
   at a time under the sheet bar). The left lists the fields of the cases the explorer filters by, in
   the groups the cases' columns use, Find a field narrowing them as it is typed. Hovering a field,
   pressing it or reaching it with the arrow keys opens its values: its own heading, each value with
   its count among the event's cases in the window under its other filters, and the foot, Deselect
   all or Show all, always drawn so nothing moves. A pick is the event's own filter, so the line
   names it with its x and every pane counts under it. */

import { NONE, OUTCOME, REPORTER, ROLE, SEX, labelOf } from './codes.js';
import { countryName } from './countries.js';
import { icon } from './icons.js';
import { openPane } from './filtermenu.js';
import { choice, onClosing, place, popMenu } from './overlays.js';
import { api } from './server.js';
import { ages } from './state.js';
import { companyName, esc, focusBox, hovered, trim } from './util.js';
import { MORE_FIELDS } from './event-fields.js';

// Each field: its words, the filter it sets (the explorer's own parameter), the heading over its
// values, how it reads a value, and whether one value at a time is picked
export const FIELDS = {
  age: { words: 'Age', heading: 'Show the cases whose age is', name: (v) => labelOf(ages(), v), by: 'age' },
  sex: { words: 'Sex', heading: 'Show the cases whose sex is', name: (v) => labelOf(SEX, v), by: 'sex' },
  country: { words: 'Country', heading: 'Show the cases from', name: (v) => (v === NONE ? 'Not given' : countryName(v)), by: 'country' },
  prole: { words: 'Role', heading: 'Show the cases where the drug is', name: (v) => ROLE[v] || v, roles: true },
  outcome: { words: 'Seriousness', heading: 'Show the cases with', name: (v) => labelOf(OUTCOME, v), by: 'outcome' },
  reporter: { words: 'Reporter', heading: 'Show the cases reported by', name: (v) => labelOf(REPORTER, v), by: 'reporter' },
  sender: { words: 'Company', heading: 'Show the cases sent by', name: (v) => companyName(v), one: true },
  ...MORE_FIELDS,
};
// the menu's groups, in plain words, and their fields in its order
export const GROUPS = [
  ['Patient', ['age', 'sex', 'country']],
  ['Drugs', ['other_drug', 'prole', 'dose', 'route', 'dose_form', 'indication', 'lot']],
  ['Course', ['onset', 'dechal', 'rechal', 'outcome']],
  ['Report', ['reporter', 'report_type', 'sender', 'other_reaction']],
];
const ALL = GROUPS.flatMap(([, ids]) => ids);
const ROLES = ['PS', 'SS', 'I', 'C'];

// a filter's values in words, as the line and a field's row say them
export const valueWords = (field, values) => values.map((v) => FIELDS[field]?.name(v) ?? v).join(', ');

// Each value of a field among the event's cases in the window under its other filters, each
// [value, cases], most first: a count by the field, each role asked as the drug's roles, and the
// companies that sent the most of these cases
async function valuesOf(ev, id) {
  const asked = ev.queryWithout(id);
  const f = FIELDS[id];
  if (f.values) return f.values(ev, id);
  if (f.by) {
    const got = await api(`/api/count?by=${f.by}&${asked}&${ev.reactionsAs('pt')}`);
    return got.counts.map(([v, n]) => [v ?? NONE, n]);
  }
  if (f.roles) {
    const one = async (r) => [r, (await api(`/api/events/group?${asked}&prole=${r}&${ev.reactionsAs('reaction')}`)).cases];
    return Promise.all(ROLES.map(one));
  }
  const got = await api(`/api/summary?${asked}&${ev.reactionsAs('pt')}`);
  return (got.sender || []).map(([v, n]) => [v ?? NONE, n]);
}

// the menu open now: { ev, menu, row, find, asked: { [field]: [value, cases][] or 'loading' } }
let af = null;
onClosing(() => { af = null; });

export function addFilter(ev, anchor, row) {
  const menu = popMenu(anchor, `<div class="oa-sheet-bar"><button type="button" class="btn btn-quiet oa-sheet-back" data-act="sheet-back">${icon('arrowLeft')}<span>Filters</span></button><span class="oa-sheet-title">Filters</span><button type="button" class="btn btn-primary oa-sheet-done" data-act="sheet-done">Done</button></div>
    <div class="oa-filter-rows"><div class="search-bar oa-ev-af-find"><span class="search-icon">${icon('search')}</span><input class="search-input" type="search" placeholder="Find a field" aria-label="Find a field" autocomplete="off" spellcheck="false"></div><div class="oa-ev-af-fields"></div></div>
    <div class="oa-filter-options"></div>`, 'oa-filter-menu oa-ev-af-menu');
  menu.dataset.pane = 'rows';
  af = { ev, menu, row: row && ALL.includes(row) ? row : ALL[0], find: '', asked: {} };
  menu.addEventListener('toggle', (e) => { if (e.newState === 'closed' && af?.menu === menu) af = null; });
  paintRows();
  paintOptions();
  // on a phone the sheet fills the screen, as the explorer's Filters do; elsewhere it fits the window
  if (menu.querySelector('.oa-sheet-bar')?.offsetHeight) place(menu, anchor); else place(menu, anchor, { fit: true });
  focusBox(menu.querySelector('.oa-ev-af-find input'), { preventScroll: true });
  if (row) openPane(menu.querySelector(`.oa-filter-row[data-row="${row}"]`));
}

// the fields, each under its group; Find a field leaves those whose words hold what is typed
function paintRows() {
  const box = af?.menu.querySelector('.oa-ev-af-fields');
  if (!box) return;
  const typed = af.find.trim().toLowerCase();
  const row = (id) => `<button type="button" class="menu-item oa-filter-row" data-act="ev-af-row" data-row="${id}" aria-expanded="${id === af.row}">
    <span>${esc(FIELDS[id].words)}</span><span class="filter-value">${esc(trim(pickedOf(id), 22))}</span>${icon('chevronRight')}</button>`;
  box.innerHTML = GROUPS.map(([words, ids]) => {
    const shown = ids.filter((id) => !typed || FIELDS[id].words.toLowerCase().includes(typed));
    return shown.length ? `<p class="menu-heading">${esc(words)}</p>${shown.map(row).join('')}` : '';
  }).join('') || '<p class="oa-pane-none">No field by that name.</p>';
}
// what a field's row says is picked under it: its values, None after Deselect all
function pickedOf(id) {
  const values = af.ev.filters.get(id);
  if (!values) return '';
  return values.length ? valueWords(id, values) : 'None';
}

// the open field's values, its counts asked once for each state of the event's filters
function paintOptions() {
  const opts = af?.menu.querySelector('.oa-filter-options');
  if (!opts) return;
  const { ev, row: id } = af;
  const key = `${id}|${ev.queryWithout(id)}`;
  if (af.asked[key] === undefined) {
    af.asked[key] = 'loading';
    const asked = af;
    valuesOf(ev, id).then((got) => { asked.asked[key] = got; if (af === asked) paintOptions(); })
      .catch(() => { asked.asked[key] = []; if (af === asked) paintOptions(); });
  }
  const got = af.asked[key];
  const values = ev.filters.get(id);
  const every = values === undefined;
  const on = (v) => every || values.includes(v);
  let list;
  if (got === 'loading') list = '<span class="skeleton skeleton-row"></span>'.repeat(4);
  else {
    // a picked value no case of these gives still shows, so it can be unticked
    const rows = [...got, ...(values || []).filter((v) => !got.some(([x]) => x === v)).map((v) => [v, 0])];
    list = rows.map(([v, n]) => choice(FIELDS[id].one ? !every && on(v) : on(v), FIELDS[id].name(v), n, `data-act="ev-af-pick" data-v="${esc(v)}"`, { radio: !!FIELDS[id].one })).join('')
      || '<p class="oa-pane-none">No case gives this field.</p>';
  }
  const foot = FIELDS[id].one ? '' : `<p class="menu-footnote oa-ev-af-foot"><button type="button" class="oa-link" data-act="ev-af-all" data-all="${every ? 'none' : 'every'}">${every ? 'Deselect all' : 'Show all'}</button></p>`;
  opts.innerHTML = `<p class="menu-heading">${esc(FIELDS[id].heading)}</p><div class="oa-choices oa-ev-af-list">${list}</div>${foot}`;
}

// a field opened: its row marked, its values on the right
function show(row) {
  if (!af || af.row === row) return;
  af.row = row;
  af.menu.querySelectorAll('.oa-filter-row').forEach((b) => b.setAttribute('aria-expanded', String(b.dataset.row === row)));
  paintOptions();
}
// after a pick: the rows say it, the values show it, and the menu stays where it is
function picked() {
  af.menu.querySelectorAll('.oa-filter-row').forEach((b) => { b.querySelector('.filter-value').textContent = trim(pickedOf(b.dataset.row), 22); });
  paintOptions();
}

// The tick boxes: every box ticked while the field picks nothing; unticking one keeps the others;
// ticking the last one left out shows every case again; Deselect all leaves none ticked, so no case
// shows, and Show all ticks them all again. A company is picked one at a time.
function pickValue(v) {
  const { ev, row: id } = af;
  const got = Array.isArray(af.asked[`${id}|${ev.queryWithout(id)}`]) ? af.asked[`${id}|${ev.queryWithout(id)}`] : [];
  const values = ev.filters.get(id);
  let next;
  if (FIELDS[id].one) next = values?.[0] === v ? null : [v];
  else if (values === undefined) next = got.map(([x]) => x).filter((x) => x !== v);
  else if (values.includes(v)) next = values.filter((x) => x !== v);
  else next = [...values, v];
  if (next && !FIELDS[id].one && got.length && got.every(([x]) => next.includes(x))) next = null;
  ev.setFilter(id, next);
}

export const FILTER_ACTS = {
  'ev-af-row': (el) => { openPane(el); show(el.dataset.row); },
  'ev-af-pick': (el) => { if (!af) return; pickValue(el.dataset.v); picked(); },
  'ev-af-all': (el) => { if (!af) return; af.ev.setFilter(af.row, el.dataset.all === 'none' ? [] : null); picked(); },
};

// hovering a field opens its values, as the Filters menu does; while the arrow keys move through the
// fields, a pointer resting on the list does not take over as it scrolls under it
let keyed = false;
document.addEventListener('pointerover', (e) => {
  const row = af && !keyed && hovered(e) && e.target.closest?.('.oa-ev-af-menu .oa-filter-row');
  if (row) show(row.dataset.row);
});
document.addEventListener('pointermove', (e) => { if (e.movementX || e.movementY) keyed = false; });
document.addEventListener('input', (e) => {
  if (!af || !e.target.matches?.('.oa-ev-af-find input')) return;
  af.find = e.target.value;
  paintRows();
  const first = af.menu.querySelector('.oa-filter-row');
  if (first && !af.menu.querySelector(`.oa-filter-row[data-row="${af.row}"]`)) show(first.dataset.row);
});
// the arrow keys: down from Find a field to the fields, up and down the fields (each opening), right
// into its values and left back to its row
document.addEventListener('keydown', (e) => {
  const m = af && e.target.closest?.('.oa-ev-af-menu');
  if (!m) return;
  const rows = [...m.querySelectorAll('.oa-filter-row')];
  const go = (el) => { if (!el) return; e.preventDefault(); keyed = true; el.focus(); if (el.matches('.oa-filter-row')) show(el.dataset.row); };
  if (e.target.matches('.oa-ev-af-find input')) {
    if (e.key === 'ArrowDown' || e.key === 'Enter') go(rows.find((r) => r.dataset.row === af.row) || rows[0]);
    return;
  }
  const row = e.target.closest('.oa-filter-row');
  if (row) {
    const i = rows.indexOf(row);
    if (e.key === 'ArrowDown') go(rows[i + 1]);
    else if (e.key === 'ArrowUp') go(rows[i - 1] || m.querySelector('.oa-ev-af-find input'));
    else if (e.key === 'ArrowRight') go(m.querySelector('.oa-filter-options :is(.menu-item, .oa-link)'));
    return;
  }
  const items = [...m.querySelectorAll('.oa-filter-options :is(.menu-item, .oa-link)')];
  const i = items.indexOf(e.target);
  if (i < 0) return;
  if (e.key === 'ArrowDown') go(items[i + 1]);
  else if (e.key === 'ArrowUp') go(items[i - 1]);
  else if (e.key === 'ArrowLeft') go(m.querySelector(`.oa-filter-row[data-row="${af.row}"]`));
});
