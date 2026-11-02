/* The heads of an opened event's cases table. Every head shows its chevron at all times and opens
   one menu, built as the events table's head menu is (eventmenus.js): Sort, the column's two
   orders in its own words (Oldest first and Youngest first for Age), then Show only, the column's
   values with their counts and Not given, where the explorer has a filter for the field. A case
   that gives no value sorts last both ways (casecolumns.py). A value ticked sets the event's own
   filter through the pane (setTicks), so the line names it and every tab counts under it; the
   counts are the event's cases in the window under its other filters (/api/summary counts each
   field so; a field read from the drug's records or the report, as + Add a filter counts it
   (event-fields.js)). Received has no Show only (the window in the line sets its days) and Case none (Find a
   case by its number does). */

import { actions } from './events.js';
import { NONE, OUTCOME, REPORTER, ROLE, SEX, labelOf } from './codes.js';
import { countryName } from './countries.js';
import { icon } from './icons.js';
import { choice, closedByThisClick, openedBy, place, popMenu } from './overlays.js';
import { ages } from './state.js';
import { esc, tip } from './util.js';
import { COLUMNS, shownColumns } from './event-cols.js';
import { MORE_FIELDS } from './event-fields.js';

// each column's two orders: the order /api/cases takes for the menu's first choice, its words, the
// second's words, and its order where it is not the first's with -asc
export const SORTS = {
  case: ['case', 'Highest number first', 'Lowest number first'],
  received: ['newest', 'Newest first', 'Oldest first', 'oldest'],
  event: ['event', 'Newest first', 'Oldest first'],
  start: ['start', 'Newest first', 'Oldest first'],
  stop: ['stop', 'Newest first', 'Oldest first'],
  age: ['age', 'Oldest first', 'Youngest first'],
  sex: ['sex', 'Female first', 'Male first'],
  weight: ['weight', 'Heaviest first', 'Lightest first'],
  drugs: ['drugs', 'Most suspect drugs first', 'Fewest first'],
  role: ['role', 'Primary suspect first', 'Primary suspect last'],
  indication: ['indication', 'A to Z', 'Z to A'],
  onset: ['onset', 'Longest first', 'Shortest first'],
  dechal: ['dechal', 'Positive first', 'Negative first'],
  reporter: ['reporter', 'Health professionals first', 'Consumers first'],
  outcome: ['serious', 'Most serious first', 'Least serious first'],
};
export const orders = (id) => { const s = SORTS[id]; return s ? [s[0], s[3] || `${s[0]}-asc`] : []; };
const sortWordsOf = (sort) => {
  for (const [id, s] of Object.entries(SORTS)) { const [a, b] = orders(id); if (sort === a) return [id, s[1]]; if (sort === b) return [id, s[2]]; }
  return [null, ''];
};
const TIPS = { case: "The case's number at FDA" };
export const SHOWN_AT_MOST = 15; // a long list shows the most named first, with a find box
const FIND_WORDS = {
  country: 'Find a country', drugs: 'Find a drug', dose: 'Find a dose', route: 'Find a route', dose_form: 'Find a dose form',
  indication: 'Find a reason', lot: 'Find a lot', reactions: 'Find a reaction',
};
export const keyOf = (id) => COLUMNS[id]?.filter || null;

// ---- each head's values, with their counts --------------------------------------------------------
const facet = (s, name) => (s?.[name] || []).map(([k, n]) => [k ?? NONE, n]);
const countOf = (list, k) => list.filter(([x]) => x === k).reduce((n, [, c]) => n + c, 0);
const notGiven = (k) => (k === NONE ? 'Not given' : null);

// A field read from the drug's records or the report: its values and counts come as + Add a filter
// gets them (event-fields.js), under the event's other filters, Not given last, a value picked that
// no case gives kept at none so it can be unticked
function fieldValues(P, key, more) {
  const rows = P.fieldCounts(key, more);
  if (!rows) return null;
  const ticked = P.ticked(key) || [];
  const all = [...rows, ...ticked.filter((v) => !rows.some(([x]) => x === v)).map((v) => [v, 0])];
  return [...all.filter(([v]) => v !== NONE), ...all.filter(([v]) => v === NONE)].map(([v, n]) => [v, more.name(v), n]);
}

// [[value, words, count]] for the head of column `id`, or null while its counts come
export function values(P, id) {
  const s = P.summary;
  if (id === 'role') {
    const n = P.roleCounts();
    return n && P.roles().map((r) => [r, ROLE[r] || r, n[r] || 0]);
  }
  const more = MORE_FIELDS[keyOf(id)];
  if (more) return fieldValues(P, keyOf(id), more);
  if (!s) return null;
  if (id === 'age') { const f = facet(s, 'age'); return [...new Set([...Object.keys(ages()), NONE])].map((k) => [k, notGiven(k) || ages()[k], countOf(f, k)]); }
  if (id === 'sex') { const f = facet(s, 'sex'); return ['F', 'M', NONE].map((k) => [k, notGiven(k) || labelOf(SEX, k), countOf(f, k)]); }
  if (id === 'reporter') { const f = facet(s, 'reporter'); return ['1', '2', '3', '4', '5', NONE].map((k) => [k, notGiven(k) || labelOf(REPORTER, k), countOf(f, k)]); }
  if (id === 'outcome') { const f = facet(s, 'outcome'); return [...Object.keys(OUTCOME).filter((k) => k !== NONE), NONE].map((k) => [k, notGiven(k) || labelOf(OUTCOME, k), countOf(f, k)]); }
  if (id === 'country') {
    const f = facet(s, 'country');
    const named = f.filter(([k]) => k !== NONE).map(([k, n]) => [k, countryName(k), n]);
    return [...named, ...f.filter(([k]) => k === NONE).map(([k, n]) => [k, 'Not given', n])];
  }
  return [];
}

// the values a head shows: a long list its most named first, those ticked kept, a find box narrowing them
function shownValues(P, id, typed) {
  const all = values(P, id);
  if (!all || !COLUMNS[id].many) return { parts: all, missed: false };
  const find = typed.trim().toLowerCase();
  const given = all.filter(([k]) => k !== NONE), none = all.filter(([k]) => k === NONE);
  const found = find ? given.filter(([k, w]) => w.toLowerCase().includes(find) || k.toLowerCase().includes(find)) : given;
  const shown = found.slice(0, SHOWN_AT_MOST);
  const ticked = P.ticked(keyOf(id)) || [];
  const kept = find ? [] : given.filter(([k]) => ticked.includes(k) && !shown.some(([x]) => x === k));
  return { parts: [...shown, ...kept, ...(find ? [] : none)], missed: !!find && !found.length };
}

// whether a value's box shows ticked: every box while the field is not filtered, none after Deselect all
const boxOn = (P, key, v) => !P.none.has(key) && (P.ticked(key) == null || P.ticked(key).includes(v));
const everyOn = (P, key) => !P.none.has(key) && P.ticked(key) == null;

// the words of what is ticked under a column, as its tip says them
function tickedWords(P, id) {
  const key = keyOf(id), now = key && P.ticked(key);
  if (!now) return [];
  const all = values(P, id) || [];
  return now.map((v) => all.find(([k]) => k === v)?.[1] || v);
}

// ---- the heads ---------------------------------------------------------------------------------
export function headRow(P) {
  return `<tr>${['case', ...shownColumns()].map((id) => head(P, id)).join('')}</tr>`;
}
function head(P, id) {
  const words = id === 'case' ? 'Case' : COLUMNS[id].words;
  const key = keyOf(id), picks = tickedWords(P, id), none = !!key && P.none.has(key);
  const [sortId, sortWords] = sortWordsOf(P.sort);
  const sorted = sortId === id && P.sort !== 'newest';
  const said = [`${TIPS[id] || COLUMNS[id].tip}.`, sortId === id ? `Sorted ${sortWords.toLowerCase()}.` : '', none ? 'Showing none.' : picks.length ? `Showing only ${picks.join(', ')}.` : '',
    SORTS[id] || key ? `Press to ${[SORTS[id] ? 'sort' : '', key ? 'show only some' : ''].filter(Boolean).join(' or ')}.` : ''].filter(Boolean).join(' ');
  const pressed = picks.length > 0 || none || sorted;
  const inside = SORTS[id] || key
    ? `<button type="button" class="oa-et-head oa-ec-head" data-act="ec-head" data-v="${id}" aria-haspopup="menu" aria-pressed="${pressed}" ${tip(said)}>${esc(words)}${icon('chevronDown')}</button>`
    : `<span class="oa-et-head oa-ec-head" ${tip(said)}>${esc(words)}</span>`;
  return `<th scope="col" class="oa-ec-c-${id}${COLUMNS[id]?.num ? ' oa-num' : ''}">${inside}</th>`;
}

// ---- the menu ----------------------------------------------------------------------------------
let at = null; // the menu open: { P, id, menu, find, anchor }

function listHtml() {
  const { P, id, find } = at;
  const key = keyOf(id);
  const { parts, missed } = shownValues(P, id, find);
  if (!parts) return '<span class="skeleton skeleton-row"></span><span class="skeleton skeleton-row"></span>';
  return `${missed ? '<p class="menu-footnote">Nothing in these cases has those words.</p>' : ''}
    <div class="oa-choices">${parts.map(([v, words, n]) => choice(boxOn(P, key, v), words, n, `data-act="ec-hpick" data-v="${esc(v)}"`)).join('')}</div>`;
}
function menuHtml() {
  const { P, id } = at;
  const s = SORTS[id], key = keyOf(id);
  const [first, second] = orders(id);
  const sort = (v, words) => choice(P.sort === v, words, null, `data-act="ec-hsort" data-v="${v}"`, { radio: true });
  const sorting = s ? `<p class="menu-heading">Sort</p><div class="oa-choices">${sort(first, s[1])}${sort(second, s[2])}</div>` : '';
  const long = key && COLUMNS[id].many && (values(P, id)?.length || 0) > SHOWN_AT_MOST;
  const find = long ? `<input class="field-input oa-menu-search oa-ec-hfind" type="search" autocomplete="off" spellcheck="false" aria-label="${FIND_WORDS[id]}" placeholder="${FIND_WORDS[id]}" value="${esc(at.find)}">` : '';
  const all = key ? `<p class="oa-et-menu-line"><button type="button" class="oa-link" data-act="ec-hall">${everyOn(P, key) ? 'Deselect all' : 'Show all'}</button></p>` : '';
  const showing = key ? `<p class="menu-heading">Show only</p>${find}<div class="oa-ec-hlist">${listHtml()}</div>${all}` : '';
  const notes = [s && id !== 'case' && id !== 'received' ? 'Not given always sorts last.' : '',
    key ? "Counts are this event's cases in the window under its other filters." : '',
    id === 'received' ? 'The window in the line above sets the days shown.' : ''].filter(Boolean);
  return `${sorting}${showing}${notes.map((n) => `<p class="menu-footnote">${esc(n)}</p>`).join('')}`;
}
// the open menu drawn again in place: only its list while a word is typed in its find box, so the
// typing stays; `P` given, only that pane's menu
export function paintMenu(P = null) {
  const m = at?.menu;
  if (!m?.isConnected || (P && at.P !== P)) return;
  const list = m.querySelector('.oa-ec-hlist');
  if (list && document.activeElement?.matches('.oa-ec-hfind') && m.contains(document.activeElement)) list.innerHTML = listHtml();
  else {
    const had = document.activeElement?.closest?.('.oa-ec-hmenu [data-act]');
    const which = had && `[data-act="${had.dataset.act}"]${had.dataset.v ? `[data-v="${CSS.escape(had.dataset.v)}"]` : ''}`;
    m.innerHTML = menuHtml();
    if (which) m.querySelector(which)?.focus({ preventScroll: true });
  }
  place(m, at.anchor, { fit: true });
}
export function openHead(P, el) {
  if (closedByThisClick()) return; // pressing the head again closes its menu
  at = { P, id: el.dataset.v, menu: null, find: '', anchor: el };
  const menu = popMenu(el, menuHtml(), 'oa-et-menu oa-ec-hmenu');
  at.menu = menu;
  place(menu, el, { fit: true });
  openedBy(el);
  menu.addEventListener('toggle', (e) => { if (e.newState === 'closed' && at?.menu === menu) at = null; });
}
document.addEventListener('input', (e) => {
  if (!e.target.matches?.('.oa-ec-hfind') || !at) return;
  at.find = e.target.value;
  paintMenu();
});

// A value ticked or unticked. From every box ticked, the one unticked leaves the others picked;
// from none, the one ticked is the only one; the last box unticked is none (no case shows); every
// box ticked again is no filter.
function pick(P, id, v) {
  const key = keyOf(id), all = (values(P, id) || []).map(([k]) => k);
  const now = P.none.has(key) ? [] : P.ticked(key) ?? all;
  const next = now.includes(v) ? now.filter((x) => x !== v) : [...now, v];
  P.setTicks(key, next.length && all.every((x) => next.includes(x)) ? null : next);
}

actions({
  'ec-hsort': (el) => { if (!at) return; at.P.sortBy(el.dataset.v); paintMenu(); },
  'ec-hpick': (el) => { if (!at) return; pick(at.P, at.id, el.dataset.v); paintMenu(); },
  // the foot: Deselect all unticks every box (no case shows), Show all ticks them all again (no filter)
  'ec-hall': () => {
    if (!at) return;
    const key = keyOf(at.id);
    at.P.setTicks(key, everyOn(at.P, key) ? [] : null);
    paintMenu();
  },
});
