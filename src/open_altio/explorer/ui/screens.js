/* The screens the Statistics tab reads its pairs with: for each statistic one of its presets (from
   its rule, through /api/statistics/about), the person's own numbers, or none; and which screen
   narrows the list. Chosen in the Thresholds menu, laid out as the filters menu is, and kept in this
   browser. A cell is marked where its statistic's screen holds for the pair. */

import { actions } from './events.js';
import { openPane } from './filtermenu.js';
import { icon } from './icons.js';
import { choice, place, popMenu } from './overlays.js';
import { esc, store } from './util.js';

const KEPT = 'statistics-screens';
export const WORDS = {
  cases: 'Cases', expected: 'Expected', ebgm: 'EBGM', eb05: 'EB05', eb95: 'EB95', prr: 'PRR',
  chi_square: 'Chi-square', chi_square_yates: 'Chi-square, Yates', ror: 'ROR', ror_lower: 'ROR lower bound',
  ror_upper: 'ROR upper bound', rrr: 'RRR', ic: 'IC', ic025: 'IC025',
};
const COMPARE = { at_least: 'at least', above: 'above', at_most: 'at most', below: 'below' };
const TESTS = { at_least: (v, t) => v >= t, above: (v, t) => v > t, at_most: (v, t) => v <= t, below: (v, t) => v < t };

let about = null; // the release's statistics, as /api/statistics/about says
let kept = store.get(KEPT, {}); // { list: statistic or 'all', by: { statistic: { preset, when } } }
// the table starts on every drug and reaction: a Rows shown kept from when it started on EBGM's
// threshold is let go once, and each statistic's own numbers stay
if (kept.start !== 'every') { kept = { by: kept.by, start: 'every' }; store.set(KEPT, kept); }
let changed = () => {}; // the tab's repaint, told whether the list itself changes
let row = 'list'; // the menu's open row

export function useScreens(found, onChange) { about = found; changed = onChange; }

const statistic = (id) => about.statistics.find((s) => s.id === id);
const opOf = (cond) => Object.keys(cond).find((k) => k !== 'column');

export function screenOf(id) {
  const mine = kept.by?.[id];
  if (mine) return mine;
  const preset = statistic(id).presets.find((p) => p.default);
  return preset ? { preset: preset.id, when: preset.when } : { preset: 'none', when: statistic(id).start };
}

export const listedBy = () => kept.list || 'all';

// whether the pair meets the statistic's screen; an empty value meets no condition
export function passes(id, pair) {
  const sc = screenOf(id);
  return sc.preset !== 'none' && sc.when.every((c) => pair[c.column] != null && TESTS[opOf(c)](pair[c.column], c[opOf(c)]));
}

// the screen that narrows the list, as /api/statistics reads it
export function passParam() {
  const list = listedBy();
  if (list === 'all' || screenOf(list).preset === 'none') return '';
  return screenOf(list).when.map((c) => `${c.column}:${opOf(c)}:${c[opOf(c)]}`).join(',');
}

const conditionWords = (when) => when.map((c) => `${WORDS[c.column]} ${COMPARE[opOf(c)]} ${c[opOf(c)]}`).join(', ');
export function screenWords(id) {
  const sc = screenOf(id);
  if (sc.preset === 'none') return 'None';
  return statistic(id).presets.find((p) => p.id === sc.preset)?.label || conditionWords(sc.when);
}

// the rows shown, in words: which drug and reaction rows the table keeps
export function listWords() {
  const list = listedBy();
  return list === 'all' || screenOf(list).preset === 'none' ? 'Every drug and reaction' : `Only those that pass ${list}'s threshold`;
}

// the list holds every pair, or the pairs it holds as it opens: the Statistics filters' Only
// reactions that pass the cutoffs (labelstats.js)
export function everyPair(every) { kept = { ...kept, list: every ? 'all' : 'EBGM' }; store.set(KEPT, kept); paint(); changed(true); }

function keep(id, screen, listChanges) {
  kept = { ...kept, by: { ...kept.by, [id]: screen } };
  store.set(KEPT, kept);
  paint();
  changed(listChanges);
}

function rowsHtml() {
  const line = (id, label, value) => `<button type="button" class="menu-item oa-filter-row" data-act="screen-row" data-row="${id}" aria-expanded="${row === id}"><span>${esc(label)}</span><span class="filter-value">${esc(value)}</span>${icon('chevronRight')}</button>`;
  return line('list', 'Rows shown', listWords()) + about.statistics.map((s) => line(s.id, s.id, screenWords(s.id))).join('');
}

function optionsHtml() {
  if (row === 'list') {
    const options = [['all', 'Every drug and reaction'], ...about.statistics.map((s) => [s.id, `Only those that pass ${s.id}'s threshold`])];
    return `<p class="menu-heading">Which drug and reaction rows the table shows</p>${options.map(([v, label]) => choice(listedBy() === v, label, null, `data-act="screen-list" data-v="${v}"`, { radio: true })).join('')}
      <p class="menu-footnote">The other thresholds still mark their numbers in the table.</p>`;
  }
  const s = statistic(row);
  const sc = screenOf(row);
  const presets = s.presets.map((p) => choice(sc.preset === p.id, p.label, null, `data-act="screen-preset" data-stat="${s.id}" data-v="${esc(p.id)}"`, { radio: true, note: p.source }));
  const numbers = sc.preset === 'none' ? '' : `<div class="oa-screen-numbers">${sc.when.map((c, i) => `<label class="oa-screen-number"><span>${esc(WORDS[c.column])} ${COMPARE[opOf(c)]}</span>
      <input class="field-input" type="number" step="any" inputmode="decimal" data-stat="${s.id}" data-i="${i}" value="${c[opOf(c)]}" aria-label="${esc(`${WORDS[c.column]} ${COMPARE[opOf(c)]}`)}"></label>`).join('')}</div>`;
  return `<p class="menu-heading">${esc(s.title)}</p><p class="oa-screen-line">${esc(s.line)}</p>
    ${presets.join('')}
    ${choice(sc.preset === 'own', 'Your own', null, `data-act="screen-preset" data-stat="${s.id}" data-v="own"`, { radio: true, note: 'set the numbers below' })}
    ${choice(sc.preset === 'none', 'None', null, `data-act="screen-preset" data-stat="${s.id}" data-v="none"`, { radio: true, note: 'mark nothing' })}
    ${numbers}
    <p class="menu-footnote"><a href="/methods?open=${encodeURIComponent(s.rule)}">How ${esc(s.id)} is worked out</a></p>`;
}

function paint() {
  const rows = document.getElementById('oa-screen-rows');
  const opts = document.getElementById('oa-screen-options');
  if (rows) rows.innerHTML = rowsHtml();
  if (opts) opts.innerHTML = optionsHtml();
}

function openScreens(anchor) {
  const menu = popMenu(anchor, `<div class="oa-sheet-bar"><button type="button" class="btn btn-quiet oa-sheet-back" data-act="sheet-back">${icon('arrowLeft')}<span>Thresholds</span></button><span class="oa-sheet-title">Thresholds</span><button type="button" class="btn btn-primary oa-sheet-done" data-act="sheet-done">Done</button></div><div class="oa-filter-rows" id="oa-screen-rows"></div><div class="oa-filter-options" id="oa-screen-options"></div>`, 'oa-filter-menu oa-screen-menu');
  menu.dataset.pane = 'rows';
  paint();
  place(menu, anchor);
}

actions({
  screens: (el) => { if (about?.present) openScreens(el); },
  // the pane opens from the row pressed, before the rows are drawn again
  'screen-row': (el) => { row = el.dataset.row; openPane(el); paint(); },
  'screen-list': (el) => { kept = { ...kept, list: el.dataset.v }; store.set(KEPT, kept); paint(); changed(true); },
  'screen-preset': (el) => {
    const id = el.dataset.stat;
    const s = statistic(id), was = screenOf(id), v = el.dataset.v;
    const preset = s.presets.find((p) => p.id === v);
    const when = preset ? preset.when : (was.preset === 'none' ? s.start : was.when);
    keep(id, { preset: v, when }, listedBy() === id);
  },
});

// a number typed into a screen makes it the person's own
document.addEventListener('input', (e) => {
  const el = e.target;
  if (!el.matches?.('.oa-screen-number input') || el.value === '' || !Number.isFinite(+el.value)) return;
  const id = el.dataset.stat;
  const when = screenOf(id).when.map((c, i) => (i === +el.dataset.i ? { column: c.column, [opOf(c)]: +el.value } : c));
  kept = { ...kept, by: { ...kept.by, [id]: { preset: 'own', when } } };
  store.set(KEPT, kept);
  document.getElementById('oa-screen-rows').innerHTML = rowsHtml();
  el.closest('.oa-filter-options').querySelectorAll(`[data-act="screen-preset"][data-stat="${id}"]`).forEach((b) => b.setAttribute('aria-checked', String(b.dataset.v === 'own')));
  changed(listedBy() === id);
});
