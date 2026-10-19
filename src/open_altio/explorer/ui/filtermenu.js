/* The filters menu: one row per filter, and the open row's options beside it (on a phone, a sheet
   with one pane at a time). Each choice filters at once; its count is the cases under the other filters.
   The Reactions row's options are terms.js's, Label status's labels.js's. */

import { classesPane, paintClassResults, searchClasses } from './classes.js';
import { NONE, labelOf } from './codes.js';
import { countryName } from './countries.js';
import { drugsPane, paintDrugResults, paintSpellings, searchDrugs, searchSpellings, spellingsPane } from './drugs.js';
import { actions } from './events.js';
import { FILTERS, filterWords, filtersFor, rolesWords } from './filters.js';
import { icon } from './icons.js';
import { isUnexpectedOnly, labelPane, labelRules } from './labels.js';
import { choice, closeMenus, onClosing, openedBy, place, popMenu } from './overlays.js';
import { refresh, scopeNow } from './scope.js';
import { eraSpan, eras, fieldNotes, listLength, productLabel, releaseEnd, releaseEndYear } from './state.js';
import { paintTermResults, reactionsPane } from './terms.js';
import { companyName, esc, focusBox, foundFirst, foundOrder, hovered, trim, typedCompany } from './util.js';

// the menu open now: { sc, row, anchor, find, termQ, termResult, kind, open, details, pending, drugQ,
// drugResult, spellQ, spellResult, classQ, classResult, classOpen, classShut, classKids }
export let menuState = null;
onClosing(() => { menuState = null; });

function openFilters(sc, anchor, row) {
  const menu = popMenu(anchor, `<div class="oa-sheet-bar"><button type="button" class="btn btn-quiet oa-sheet-back" data-act="sheet-back">${icon('arrowLeft')}<span>Filters</span></button><span class="oa-sheet-title">Filters</span><button type="button" class="btn btn-primary oa-sheet-done" data-act="sheet-done">Done</button></div><div class="oa-filter-rows" id="oa-filter-rows"></div><div class="oa-filter-options" id="oa-filter-options"></div>`, 'oa-filter-menu');
  menu.id = 'oa-filter-menu';
  menu.dataset.pane = 'rows';
  menu.addEventListener('toggle', (e) => { if (e.newState === 'closed') menuState = null; });
  menuState = { sc, row: row || filtersFor(sc)[0].key, anchor, find: '', termQ: '', termResult: null, kind: 'all', open: new Set(), details: {}, pending: new Set(), classQ: '', classOpen: new Set(), classShut: new Set(), classKids: {} };
  paintMenu();
  // always under its button: the menu is taller than the room above it
  place(menu, anchor);
  findBox();
  // opened at one filter (its line in the strip, a chart's note): on a phone, straight to its options
  if (row) openPane(menu.querySelector(`.oa-filter-row[data-row="${row}"]`));
}

// the open filter's search box takes the typing, except on a touch screen
function findBox() {
  const id = { reactions: 'oa-term-find', spellings: 'oa-spell-find', atc: 'oa-class-find' }[menuState.row];
  if (id) focusBox(document.getElementById(id), { preventScroll: true });
}

export function refreshMenu() { if (menuState) paintMenu({ keepInput: true }); }

export function paintRows() {
  const rowsEl = document.getElementById('oa-filter-rows');
  if (!rowsEl || !menuState) return;
  const { sc, row } = menuState;
  rowsEl.innerHTML = filtersFor(sc).map((d) => `<button type="button" class="menu-item oa-filter-row" data-act="filter-row" data-row="${d.key}" aria-expanded="${d.key === row}">
    <span>${d.label}</span><span class="filter-value">${esc(trim(filterWords(sc, d), 22))}</span>${icon('chevronRight')}</button>`).join('');
}

function paintMenu({ keepInput = false } = {}) {
  if (!menuState) return;
  paintRows();
  const opts = document.getElementById('oa-filter-options');
  if (!opts) return;
  const def = filtersFor(menuState.sc).find((d) => d.key === menuState.row) || filtersFor(menuState.sc)[0];
  // typing stays in its box: only the results under it are drawn again
  if (keepInput && def.kind === 'reactions' && document.getElementById('oa-term-results')) { paintTermResults(); return; }
  if (keepInput && def.kind === 'drugs' && document.getElementById('oa-drug-results')) { paintDrugResults(); return; }
  if (keepInput && def.kind === 'spellings' && document.getElementById('oa-spell-results')) { searchSpellings(); return; }
  if (keepInput && def.kind === 'atc' && document.getElementById('oa-class-results')) { searchClasses(); return; }
  if (keepInput && def.kind === 'sender' && document.getElementById('oa-sender-list')) { document.getElementById('oa-sender-list').innerHTML = senderChoices(menuState.sc); return; }
  if (keepInput && def.country && document.getElementById('oa-menu-find')) { document.getElementById('oa-country-list').innerHTML = countryChoices(menuState.sc, def); return; }
  opts.dataset.kind = def.kind;
  opts.innerHTML = options(menuState.sc, def);
  if (def.kind === 'reactions') paintTermResults();
  if (def.kind === 'drugs') { paintDrugResults(); if (menuState.drugQ) searchDrugs(); }
  if (def.kind === 'spellings') { paintSpellings(); searchSpellings(); }
  if (def.kind === 'atc') { paintClassResults(); searchClasses(); }
}

function countryChoices(sc, def) {
  const s = sc.summary, f = sc.f;
  const facet = new Map((s?.country || []).map(([k, n]) => [k ?? NONE, n]));
  let keys = [...facet.keys()];
  for (const k of f.country) if (!keys.includes(k)) keys.unshift(k);
  const q = menuState.find.trim().toLowerCase();
  keys = foundFirst(keys, q, (k) => (String(k).toLowerCase() === q ? 0 : foundOrder(q, countryName(k))));
  return keys.slice(0, listLength('countries_offered')).map((k) => choice(f.country.includes(k), countryName(k), facet.get(k) ?? 0, `data-act="opt" data-key="country" data-v="${esc(k)}"`)).join('') || '<p class="oa-pane-none">No country by that name.</p>';
}

// the companies listed, those whose name holds what is typed in the box as it is typed
function senderChoices(sc) {
  const f = sc.f, q = (menuState.senderFind || '').trim().toLowerCase();
  const listed = foundFirst(sc.summary?.sender || [], q, ([k]) => foundOrder(q, companyName(k)));
  return listed.map(([k, n]) => choice(f.sender === (k ?? NONE), companyName(k), n, `data-act="opt-sender" data-v="${esc(k ?? NONE)}"`, { radio: true })).join('');
}

function options(sc, def) {
  const s = sc.summary;
  const f = sc.f;
  const head = `<p class="menu-heading">${def.label}</p>`;
  if (def.kind === 'reactions') return reactionsPane(sc);
  if (def.kind === 'label') return labelPane(sc, otherFilters(sc, 'label'));
  if (def.kind === 'codes' && def.country) {
    return `${head}<input class="field-input oa-menu-search" id="oa-menu-find" type="search" aria-label="Find a country" placeholder="Find a country" value="${esc(menuState.find)}" autocomplete="off">
      <div class="oa-choices" id="oa-country-list">${countryChoices(sc, def)}</div>
      <p class="menu-footnote">Where the event happened, else the reporter's country. Counts are cases under the other filters.</p>`;
  }
  if (def.kind === 'codes') {
    const facet = new Map((s?.[def.key] || []).map(([k, n]) => [k ?? NONE, n]));
    const keys = def.order ? def.order.filter((k) => facet.has(k) || f[def.key].includes(k)) : [...facet.keys()];
    for (const k of f[def.key]) if (!keys.includes(k)) keys.push(k);
    return `${head}<div class="oa-choices">${keys.map((k) => choice(f[def.key].includes(k), labelOf(def.map, k), facet.get(k) ?? 0, `data-act="opt" data-key="${def.key}" data-v="${esc(k)}"`)).join('')}</div>
      <p class="menu-footnote">Counts are cases under the other filters. ${def.note || 'Not given means FDA\'s field is blank, says unknown or holds a filler number.'}</p>${fieldNotes(def.field, f).map((n) => `<p class="menu-footnote">${esc(n)}</p>`).join('')}`;
  }
  if (def.kind === 'sender') {
    return `${head}<input class="field-input oa-menu-search" id="oa-sender-find" type="search" aria-label="A company, or FDA's spelling of it" placeholder="A company, or FDA's spelling of it" value="${esc(f.sender === NONE ? '' : companyName(f.sender))}" autocomplete="off">
      <div class="oa-choices" id="oa-sender-list">${senderChoices(sc)}</div>
      <p class="menu-footnote">The companies that sent the most of these cases. Each of FDA's spellings of a company counts under its name: type any of them and press Enter.</p>`;
  }
  if (def.kind === 'drugs') return drugsPane(sc);
  if (def.kind === 'spellings') return spellingsPane(sc);
  if (def.kind === 'atc') return classesPane(sc);
  if (def.kind === 'days') {
    // a day is the smallest unit FDA gives: its dates carry no time
    const box = (name, label, v) => `<label class="field"><span class="field-label">${label}</span><input class="field-input oa-day" type="date" data-act="days" data-k="${name}" max="${releaseEnd()}" value="${esc(v)}"></label>`;
    // the release's last years, latest first
    const years = Array.from({ length: listLength('years_offered') }, (_, i) => releaseEndYear() - i);
    const isYear = (y) => f[def.lo] === `${y}-01-01` && f[def.hi] === `${y}-12-31`;
    const partial = def.key === 'event' ? '<p class="oa-day-note">When FDA gives only the month or the year of the event, the case cannot be placed on a day, so it is left out while this filter is on.</p>' : '';
    return `${head}<div class="oa-years-pick">${box(def.lo, 'On or after', f[def.lo])}${box(def.hi, 'On or before', f[def.hi])}</div>
      <p class="oa-day-note">Both days are included: a case counts when ${def.what} on either day or between them.</p>${partial}
      <p class="menu-heading">A whole year</p><div class="oa-year-quick">${years.map((y) => `<button type="button" class="oa-smq-scope" data-act="year" data-def="${def.key}" data-v="${y}" aria-pressed="${isYear(y)}">${y}</button>`).join('')}</div>
      <p class="menu-footnote">To the day, the smallest unit FDA records: its dates carry no time.</p>`;
  }
  if (def.kind === 'era') {
    const facet = Object.fromEntries((s?.era || []).map(([k, n]) => [k, n]));
    const on = f.era || ['AERS', 'FAERS'];
    return `${head}<div class="oa-choices">${choice(on.includes('FAERS'), `FAERS, ${eraSpan('FAERS')}`, facet.faers ?? 0, 'data-act="opt-era" data-v="FAERS"')}${choice(on.includes('AERS'), `AERS, ${eraSpan('AERS')}`, facet.legacy ?? 0, 'data-act="opt-era" data-v="AERS"')}</div>
      <p class="menu-footnote oa-era-note">A case counts once, in the system of its latest version: the cases FDA carried from AERS into FAERS in ${eras().FAERS[0].slice(0, 4)} count as FAERS cases, though many were first received years before. For cases first reported before FAERS, use <button type="button" class="oa-link" data-act="filter-goto" data-row="received">Received by FDA</button>.</p>`;
  }
  if (def.kind === 'dedup') {
    return `${head}<div class="oa-choices">${choice(f.dedup === 'kept_only', 'Leave out probable duplicates', null, 'data-act="dups" data-v="kept_only"', { radio: true })}${choice(f.dedup === 'all', 'Include them, flagged', null, 'data-act="dups" data-v="all"', { radio: true })}</div>
      <p class="menu-footnote">Probable duplicates share the event date, age, sex, country, drugs and reactions, or the manufacturer case number from one sender. The latest received copy is shown. They are flagged, never deleted.</p>`;
  }
  return head;
}

// the counts in a menu are under every other filter; say which, so a small number is never a puzzle
export function otherFilters(sc, own) {
  const on = filtersFor(sc).filter((d) => d.key !== own && filterWords(sc, d)).map((d) => d.label);
  const base = sc.product ? `${productLabel(sc.product)} as ${rolesWords(sc.roles)}` : 'all cases';
  return on.length ? `<strong class="oa-under">Counts are within ${esc(base)} and your other filters: ${esc(on.join(', '))}.</strong> ` : `Counts are within ${esc(base)}. `;
}

// on a phone the filter sheet shows one pane at a time: clicking a filter opens its options
export function openPane(el) {
  const m = el?.closest('.oa-filter-menu');
  if (!m) return;
  m.dataset.pane = 'options';
  const title = m.querySelector('.oa-sheet-title');
  if (title) title.textContent = el.querySelector('span')?.textContent || 'Filters';
}

function showRow(row) {
  if (!menuState || menuState.row === row) return;
  menuState.row = row; menuState.find = '';
  paintMenu();
  findBox();
}

actions({
  filters: (el) => { const sc = scopeNow(); if (sc) { openFilters(sc, document.querySelector('.oa-filters-btn') || el, el.dataset.row); openedBy(el); } },
  // the pane opens from the row pressed, before the rows are drawn again
  'filter-row': (el) => { openPane(el); showRow(el.dataset.row); },
  // a filter's note pointing to another filter opens that one, as its row does
  'filter-goto': (el) => { showRow(el.dataset.row); const row = document.querySelector(`.oa-filter-row[data-row="${el.dataset.row}"]`); if (row) openPane(row); },
  'sheet-back': (el) => { const m = el.closest('.oa-filter-menu'); if (m) m.dataset.pane = 'rows'; },
  'sheet-done': () => closeMenus(),
  opt: (el) => {
    const sc = menuState?.sc || scopeNow();
    const list = sc.f[el.dataset.key];
    const v = el.dataset.v;
    sc.f[el.dataset.key] = list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
    paintMenu({ keepInput: true }); refresh(sc);
  },
  year: (el) => {
    const sc = menuState.sc; const y = el.dataset.v;
    const def = FILTERS.find((d) => d.key === el.dataset.def);
    const same = sc.f[def.lo] === `${y}-01-01` && sc.f[def.hi] === `${y}-12-31`;
    sc.f[def.lo] = same ? '' : `${y}-01-01`; sc.f[def.hi] = same ? '' : `${y}-12-31`;
    paintMenu(); refresh(sc);
  },
  'opt-era': (el) => {
    const sc = menuState.sc;
    const on = sc.f.era || ['AERS', 'FAERS'];
    const next = on.includes(el.dataset.v) ? on.filter((x) => x !== el.dataset.v) : [...on, el.dataset.v];
    sc.f.era = next.length === 2 ? null : next;
    paintMenu(); refresh(sc);
  },
  'opt-sender': (el) => {
    const sc = menuState?.sc || scopeNow();
    sc.f.sender = sc.f.sender === el.dataset.v ? '' : el.dataset.v;
    paintMenu(); refresh(sc);
  },
  dups: (el) => { const sc = menuState?.sc || scopeNow(); if (!sc) return; sc.f.dedup = el.dataset.v; paintMenu(); refresh(sc); },
  // Label status: every tick on is no filter (null), so the list keeps its true total
  'opt-label': (el) => {
    const sc = menuState.sc; const all = labelRules().outcomes; const on = sc.f.label || all; const v = el.dataset.v;
    const next = all.filter((k) => (k === v ? !on.includes(k) : on.includes(k)));
    sc.f.label = next.length === all.length ? null : next;
    paintMenu(); refresh(sc);
  },
  'label-unexpected': () => {
    const sc = menuState.sc;
    if (!isUnexpectedOnly(sc.f.label)) { sc.f.label = [...labelRules().unexpected_only]; paintMenu(); refresh(sc); }
  },
});

// hovering a filter's row opens its options, as a menu does; a tap opens them by its click alone
document.addEventListener('pointerover', (e) => {
  const row = hovered(e) && e.target.closest?.('.oa-filter-row');
  if (row && menuState) showRow(row.dataset.row);
});
// ticking a choice keeps the typing where it was, so a person can go on typing
document.addEventListener('mousedown', (e) => {
  if (e.target.closest('.oa-filter-menu .oa-choice, .oa-filter-menu .oa-filter-row, .oa-filter-menu .oa-smq-scope, .oa-filter-menu .oa-expand, .oa-filter-menu .oa-kind')) e.preventDefault();
});
document.addEventListener('change', (e) => {
  const el = e.target;
  if (el.id === 'oa-sender-find' && menuState) { menuState.sc.f.sender = typedCompany(el.value); menuState.senderFind = ''; paintMenu(); refresh(menuState.sc); return; }
  if (el.dataset.act !== 'days') return;
  const sc = menuState?.sc; if (!sc) return;
  sc.f[el.dataset.k] = el.value;
  for (const [lo, hi] of [['from', 'to'], ['efrom', 'eto']]) if (sc.f[lo] && sc.f[hi] && sc.f[lo] > sc.f[hi]) [sc.f[lo], sc.f[hi]] = [sc.f[hi], sc.f[lo]];
  paintRows(); refresh(sc);
});
document.addEventListener('input', (e) => {
  const el = e.target;
  if (el.id === 'oa-menu-find' && menuState) { menuState.find = el.value; paintMenu({ keepInput: true }); }
  if (el.id === 'oa-sender-find' && menuState) { menuState.senderFind = el.value; paintMenu({ keepInput: true }); }
});
