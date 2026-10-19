/* How a drug counts, on its page and in All cases' Drugs filter (rule explorer-drug-counts, in
   /api/release's words): FDA's role codes as tick boxes, any product containing the drug or that
   product alone, and the Spellings filter, which lists every spelling of the drug with its cases,
   ticked, and finds FDA's spellings with no ingredient to add. */

import { ACTS, actions } from './events.js';
import { query, rolesWords } from './filters.js';
import { menuState, openPane, otherFilters, paintRows } from './filtermenu.js';
import { picked } from './host.js';
import { choice, showProblem } from './overlays.js';
import { refresh, scopeNow } from './scope.js';
import { api } from './server.js';
import { drugWords, learnTitles, productLabel } from './state.js';
import { esc, num, skeletonRows, tip } from './util.js';


// The Statistics tab counts by the ingredient alone (rule statistics-cases), so there the drug's line
// stands where it stands, disabled, with one tip over the whole line saying why
const STATISTICS_COUNT = 'Statistics count every product containing the ingredient, as primary or secondary suspect';
const offHere = (sc) => (sc.tab === 'statistics' ? 'aria-disabled="true"' : '');

// FDA's role codes, each a tick box with FDA's name for it on hover; `act` says whose roles they are,
// `off` the group's aria-disabled when ticking them changes nothing
export function roleTicks(chosen, act, off = '') {
  const ticks = drugWords().roles.map(([code, name]) => choice(chosen.includes(code), code, null, `data-act="${act}" data-v="${code}" ${off ? 'aria-disabled="true"' : tip(name)}`, { role: 'checkbox' }));
  return `<span class="oa-roles" role="group" aria-label="Drug roles" ${off}><span class="field-label">Roles</span>${ticks.join('')}</span>`;
}

// a role ticked or not; the last one ticked stays, so a count always has a role
export function toggled(roles, code) {
  if (!roles.includes(code)) return drugWords().roles.map(([c]) => c).filter((c) => c === code || roles.includes(c));
  return roles.length > 1 ? roles.filter((c) => c !== code) : roles;
}
// the tick boxes drawn again in place, as one is ticked
const paintTicks = (group, roles, act) => { if (group) group.outerHTML = roleTicks(roles, act); };

// any product containing the drug, or that product alone; FDA's spelling with no ingredient is its own
export function unitSwitch(sc) {
  const units = drugWords().units;
  const fixed = sc.info?.kind === 'spelling';
  const on = fixed ? units.at(-1)[0] : sc.unit;
  const off = offHere(sc);
  const why = off || (fixed ? `aria-disabled="true" ${tip("FDA's spelling with no ingredient is a product of its own")}` : '');
  return `<span class="view-switch oa-unit" role="tablist" aria-label="Which products count" data-state="${on === units[0][0] ? 'first' : 'second'}" ${off ? 'aria-disabled="true"' : ''}>${units.map(([id, words]) => `<button type="button" role="tab" class="view-switch-half" aria-selected="${on === id}" data-act="unit" data-v="${id}" ${why}>${esc(words)}</button>`).join('')}</span>`;
}

// the drug's line on its page: which products count, and in which roles; one box, so the
// Statistics tab's one tip covers all of it
export const drugBar = (sc) => `<span class="oa-drugline"${sc.tab === 'statistics' ? ` ${tip(STATISTICS_COUNT)}` : ''}>${unitSwitch(sc)}${roleTicks(sc.roles, 'prole', offHere(sc))}</span>`;

// ---- the Spellings filter, on a product's page --------------------------------------------------

export function spellingsPane(sc) {
  return `<p class="menu-heading">Spellings of ${esc(productLabel(sc.product))}</p>
    <input class="field-input oa-menu-search" id="oa-spell-find" type="search" autocomplete="off" spellcheck="false" aria-label="Find a spelling" placeholder="Find a spelling, or one with no ingredient to add" value="${esc(menuState.spellQ || '')}">
    <div class="oa-term-results" id="oa-spell-results"></div>
    <p class="menu-footnote">${otherFilters(sc, 'spellings')}A case counts when it names a ticked spelling. A spelling with no ingredient is FDA's own words, which the drug-name dictionary does not name.</p>`;
}

// what the spellings' counts depend on: everything but the ticks themselves, and what was typed
const spellKey = (sc) => `${query({ ...sc, exclude: [], include: [] })}|${(menuState.spellQ || '').trim().toLowerCase()}`;
const rows = (list, on, act) => `<div class="oa-choices">${list.map(([k, n]) => choice(on(k), k, n, `data-act="${act}" data-v="${esc(k)}"`)).join('')}</div>`;

export function paintSpellings() {
  const box = document.getElementById('oa-spell-results');
  if (!box || !menuState) return;
  const { sc, spellResult: r } = menuState;
  if (!r || r.key !== spellKey(sc)) { box.innerHTML = skeletonRows(2); return; }
  const ticked = (k) => !sc.exclude.includes(k);
  const added = (k) => sc.include.includes(k);
  const listed = new Set([...r.spellings, ...r.unmapped].map(([k]) => k));
  const counts = new Map([...r.excluded, ...r.included, ...r.unmapped]);
  const parts = [];
  const extra = sc.include.filter((k) => !listed.has(k)).map((k) => [k, counts.get(k) ?? 0]);
  if (extra.length) parts.push(`<p class="menu-heading">Added, with no ingredient</p>${rows(extra, added, 'spell-add')}`);
  const out = sc.exclude.filter((k) => !listed.has(k)).map((k) => [k, counts.get(k) ?? 0]);
  if (out.length) parts.push(`<p class="menu-heading">Left out</p>${rows(out, ticked, 'spell')}`);
  if (sc.info?.kind === 'spelling') {
    parts.push(`<p class="menu-heading">This page's spelling</p><div class="oa-choices">${r.spellings.map(([k, n]) => choice(true, k, n, 'aria-disabled="true"')).join('')}</div>`);
  } else if (r.spellings.length) {
    const head = r.q ? `Its spellings holding "${esc(r.q)}"` : r.spellings.length < r.total ? `The ${num(r.spellings.length)} of its ${num(r.total)} spellings with the most cases; type to find any other` : `All ${num(r.total)} of its spellings, most cases first`;
    parts.push(`<p class="menu-heading">${head}</p>${rows(r.spellings, ticked, 'spell')}`);
  } else if (r.q) parts.push(`<p class="oa-pane-none">No spelling of it holds "${esc(r.q)}".</p>`);
  if (r.unmapped.length) parts.push(`<p class="menu-heading">With no ingredient: tick one to count it here</p>${rows(r.unmapped, added, 'spell-add')}`);
  else if (r.q) parts.push(`<p class="oa-pane-none">No spelling with no ingredient holds "${esc(r.q)}".</p>`);
  box.innerHTML = parts.join('');
}

let spellTimer = 0;
export function searchSpellings() {
  clearTimeout(spellTimer);
  const ms = menuState;
  if (!ms) return;
  const key = spellKey(ms.sc);
  if (ms.spellResult?.key === key) { paintSpellings(); return; }
  paintSpellings();
  spellTimer = setTimeout(async () => {
    try {
      const q = (ms.spellQ || '').trim();
      const r = await api(`/api/spellings?${query(ms.sc, q ? { q } : {})}`);
      if (menuState === ms && spellKey(ms.sc) === key) { ms.spellResult = { ...r, key }; paintSpellings(); }
    } catch (err) { showProblem(err); }
  }, 110);
}

// ---- the Drugs filter, on All cases ---------------------------------------------------------------

export function drugsPane(sc) {
  return `<p class="menu-heading">Drugs</p>
    <input class="field-input oa-menu-search" id="oa-drug-find" type="search" autocomplete="off" spellcheck="false" aria-label="Find a drug" placeholder="Type an ingredient or a name it is reported under" value="${esc(menuState.drugQ || '')}">
    ${roleTicks(sc.f.droles, 'drole')}
    <div class="oa-term-results" id="oa-drug-results"></div>
    <p class="menu-footnote">${otherFilters(sc, 'drugs')}A case counts when it names any of the chosen drugs in a ticked role, in ${esc(unitWords().toLowerCase())} it.</p>`;
}
const unitWords = () => Object.fromEntries(drugWords().units)[drugWords().default_unit];

function drugRow(name, n, names, on) {
  return choice(on, productLabel(name), n, `data-act="dprod" data-v="${esc(name)}"`, { note: names?.length ? `reported as ${names.slice(0, 2).join(', ')}` : '' });
}

export function paintDrugResults() {
  const box = document.getElementById('oa-drug-results');
  if (!box || !menuState) return;
  const { sc, drugQ, drugResult } = menuState;
  const f = sc.f;
  const q = (drugQ || '').trim().toLowerCase();
  const parts = [];
  if (f.dprods.length) parts.push(`<p class="menu-heading">Chosen</p><div class="oa-choices">${f.dprods.map((d) => drugRow(d, null, null, true)).join('')}</div>`);
  if (q) {
    if (!drugResult || drugResult.q !== q) parts.push(skeletonRows(2));
    else {
      const found = drugResult.drugs.filter((d) => !f.dprods.includes(d.name));
      const spelled = drugResult.unmapped.filter(([k]) => !f.dprods.includes(k));
      if (found.length) parts.push(`<p class="menu-heading">Ingredients</p><div class="oa-choices">${found.map((d) => drugRow(d.name, d.cases, d.reported, false)).join('')}</div>`);
      if (spelled.length) parts.push(`<p class="menu-heading">With no ingredient</p><div class="oa-choices">${spelled.map(([k, n]) => drugRow(k, n, null, false)).join('')}</div>`);
      if (!drugResult.drugs.length && !drugResult.unmapped.length) parts.push(`<p class="oa-pane-none">FDA names no drug "${esc(drugQ.trim())}".</p>`);
    }
  } else {
    const top = (sc.summary?.drugs || []).filter(([d]) => !f.dprods.includes(d));
    if (top.length) parts.push(`<p class="menu-heading">Reported most here as ${rolesWords(drugWords().default_roles)}</p><div class="oa-choices">${top.map(([d, n]) => drugRow(d, n, null, false)).join('')}</div>`);
  }
  box.innerHTML = parts.join('');
}

let drugTimer = 0;
export function searchDrugs() {
  clearTimeout(drugTimer);
  const ms = menuState;
  if (!ms) return;
  const q = (ms.drugQ || '').trim();
  paintDrugResults();
  if (!q) return;
  drugTimer = setTimeout(async () => {
    try {
      const sc = ms.sc;
      const r = await api(`/api/drugs?${query({ ...sc, f: { ...sc.f, dprods: [] } })}&q=${encodeURIComponent(q)}&${sc.f.droles.map((x) => `drole=${x}`).join('&')}`);
      learnTitles(r.drugs);
      if (menuState === ms && (ms.drugQ || '').trim().toLowerCase() === r.q) { ms.drugResult = r; paintDrugResults(); }
    } catch (err) { showProblem(err); }
  }, 110);
}

// ---- what a click does ----------------------------------------------------------------------------

function toggle(list, v) { return list.includes(v) ? list.filter((x) => x !== v) : [...list, v]; }

actions({
  // the title's count of spellings opens them, on a phone straight at their pane
  spellings: (el) => {
    ACTS.filters(el);
    const row = document.querySelector('#oa-filter-menu [data-row="spellings"]');
    if (row) openPane(row);
  },
  prole: (el) => {
    const sc = scopeNow(); if (!sc || el.getAttribute('aria-disabled') === 'true') return;
    const next = toggled(sc.roles, el.dataset.v);
    if (next === sc.roles) return;
    sc.roles = next; paintTicks(el.closest('.oa-roles'), next, 'prole'); refresh(sc);
  },
  unit: (el) => {
    const sc = scopeNow();
    if (!sc || el.getAttribute('aria-disabled') === 'true' || sc.unit === el.dataset.v) return;
    sc.unit = el.dataset.v;
    const sw = el.closest('.view-switch');
    sw.dataset.state = sc.unit === drugWords().units[0][0] ? 'first' : 'second';
    sw.querySelectorAll('button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.v === sc.unit)));
    refresh(sc);
  },
  spell: (el) => { const sc = menuState.sc; sc.exclude = toggle(sc.exclude, el.dataset.v); paintSpellings(); paintRows(); refresh(sc); },
  'spell-add': (el) => {
    const sc = menuState.sc; sc.include = toggle(sc.include, el.dataset.v);
    if (sc.include.includes(el.dataset.v)) picked('spellings', menuState.spellQ, { picked: el.dataset.v });
    paintSpellings(); paintRows(); refresh(sc);
  },
  dprod: (el) => {
    const sc = menuState?.sc || scopeNow();
    sc.f.dprods = toggle(sc.f.dprods, el.dataset.v);
    if (sc.f.dprods.includes(el.dataset.v)) picked('drugs', menuState?.drugQ, { picked: el.dataset.v });
    if (menuState) { paintDrugResults(); paintRows(); }
    refresh(sc);
  },
  drole: (el) => {
    const sc = menuState.sc;
    const next = toggled(sc.f.droles, el.dataset.v);
    if (next === sc.f.droles) return;
    sc.f.droles = next; paintTicks(el.closest('.oa-roles'), next, 'drole');
    menuState.drugResult = null; searchDrugs(); paintRows();
    if (sc.f.dprods.length) refresh(sc);
  },
});

document.addEventListener('input', (e) => {
  const el = e.target;
  if (!menuState) return;
  if (el.id === 'oa-spell-find') { menuState.spellQ = el.value; searchSpellings(); }
  if (el.id === 'oa-drug-find') { menuState.drugQ = el.value; menuState.drugResult = null; searchDrugs(); }
});
