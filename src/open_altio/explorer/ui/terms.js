/* The Reactions filter: type and the matching terms appear at once, by kind (preferred terms, and
   with MedDRA's licensed part lower-level terms and SMQs; the person's own queries too). Only terms
   that exist can be picked. An SMQ or a query opens in place to show its preferred terms, ticked as
   a tree: a chosen one ticks its terms, and unticking one leaves it out (a dash on the group). */

import { actions } from './events.js';
import { query } from './filters.js';
import { menuState, otherFilters, paintRows } from './filtermenu.js';
import { picked } from './host.js';
import { icon } from './icons.js';
import { choice, showProblem } from './overlays.js';
import { isMine, mayChange, queryGroups, queryNote, shareGroup } from './queries.js';
import { refresh, scopeNow } from './scope.js';
import { api } from './server.js';
import { S, listLength, meddraOn, ptLine, ptVersion } from './state.js';
import { esc, focusBox, num, skeletonRows, tip } from './util.js';

export function reactionsPane(sc) {
  return `<div class="oa-pane-head"><p class="menu-heading">Reactions</p>
      <button type="button" class="icon-btn oa-plus" data-act="cmq-new" ${tip('New custom MedDRA query (CMQ): your own named group of preferred terms')} aria-label="New custom MedDRA query (CMQ)">${icon('plus')}</button></div>
    <input class="field-input oa-menu-search" id="oa-term-find" type="search" autocomplete="off" spellcheck="false" aria-label="Find reactions" placeholder="${meddraOn() ? 'Type a term or an SMQ' : 'Type a preferred term'}" value="${esc(menuState.termQ)}">
    <div class="tabs-line oa-kinds" id="oa-kinds" role="tablist" aria-label="Which kind of term"></div>
    <div class="oa-term-results" id="oa-term-results"></div>
    <p class="menu-footnote">${otherFilters(sc, 'reactions')}A case counts when it has any of the chosen terms.${ptVersion() ? ` Each term is a current PT in MedDRA ${esc(ptVersion())} and counts the cases FDA wrote under its older terms too.` : ''}${ptLine() ? ` ${esc(ptLine())}` : ''}</p>`;
}

// ---- one tick per preferred term, wherever it shows -----------------------------------------------
// A term is ticked when it is chosen on its own (f.pts) or is in a chosen SMQ or query, and is not left
// out (f.ptsOut). A group's tick follows its terms: all ticked, some (a dash), or none.

const smqTerms = new Map(); // an SMQ's terms as /api/smq names them: code -> [[term, 'narrow'|'broad']]
const low = (t) => String(t).toLowerCase();
const has = (list, t) => list.some((x) => low(x) === low(t));
// a group: { smq: code, scope } or { cmq: id }; its terms, or null while they are not known
function termsOf(g) {
  if (g.cmq) return S.cmqs.find((q) => q.id === g.cmq)?.terms || null;
  const all = smqTerms.get(g.smq);
  return all ? all.filter(([, scope]) => g.scope === 'broad' || scope === 'narrow').map(([t]) => t) : null;
}
const chosenGroups = (f) => [...f.smqs.map((x) => ({ smq: x.code, scope: x.scope })), ...f.cmqs.map((id) => ({ cmq: id }))];
const covered = (f, t) => chosenGroups(f).some((g) => has(termsOf(g) || [], t));
export const termOn = (f, t) => !has(f.ptsOut, t) && (has(f.pts, t) || covered(f, t));
function groupTick(f, g) {
  const terms = termsOf(g);
  const chosen = g.cmq ? f.cmqs.includes(g.cmq) : f.smqs.some((x) => x.code === g.smq && x.scope === g.scope);
  if (!terms?.length) return chosen;
  const on = terms.filter((t) => termOn(f, t)).length;
  return on === terms.length ? true : on ? 'mixed' : false;
}
// a chosen group with every term unticked is no longer chosen; a term no chosen group holds is no
// longer left out
export function settleTerms(f) {
  const none = (g) => { const terms = termsOf(g); return !!terms?.length && terms.every((t) => !termOn(f, t)); };
  f.smqs = f.smqs.filter((x) => !none({ smq: x.code, scope: x.scope }));
  f.cmqs = f.cmqs.filter((id) => !none({ cmq: id }));
  f.ptsOut = f.ptsOut.filter((t) => covered(f, t));
}
export function pressTerm(f, t) {
  if (termOn(f, t)) {
    f.pts = f.pts.filter((x) => low(x) !== low(t));
    if (covered(f, t)) f.ptsOut = [...f.ptsOut, t];
  } else if (has(f.ptsOut, t)) f.ptsOut = f.ptsOut.filter((x) => low(x) !== low(t));
  else f.pts = [...f.pts, t];
  settleTerms(f);
}
// a group pressed ticks all its terms, or unticks them all when they all are
function pressGroup(f, g, name) {
  const mine = termsOf(g) || [];
  const theirs = (t) => !has(mine, t);
  if (groupTick(f, g) === true) {
    f.pts = f.pts.filter(theirs);
    if (g.cmq) f.cmqs = f.cmqs.filter((id) => id !== g.cmq); else f.smqs = f.smqs.filter((x) => x.code !== g.smq);
    f.ptsOut = [...f.ptsOut.filter(theirs), ...mine.filter((t) => covered(f, t))];
    settleTerms(f);
  } else chooseGroup(f, g, name);
}
// a group chosen whole: its terms are ticked through it, none left out
function chooseGroup(f, g, name) {
  const theirs = (t) => !has(termsOf(g) || [], t);
  if (g.cmq) f.cmqs = [...f.cmqs.filter((id) => id !== g.cmq), g.cmq];
  else f.smqs = [...f.smqs.filter((x) => x.code !== g.smq), { code: g.smq, name, scope: g.scope }];
  f.pts = f.pts.filter(theirs);
  f.ptsOut = f.ptsOut.filter(theirs);
  settleTerms(f);
}

// the chosen terms and groups as the pane opened or the search last changed: they keep their rows
// while ticks change, so nothing moves under the pointer
function pinned(ms) {
  const key = `${low(ms.termQ.trim())}|${ms.kind}`;
  const f = ms.sc.f;
  if (ms.termPin?.key !== key) ms.termPin = { key, pts: [...f.pts], smqs: f.smqs.map((x) => ({ ...x })), cmqs: [...f.cmqs] };
  return ms.termPin;
}

// the kinds of term: id, tab label, what it is, and whether only MedDRA's licensed part has it
export const KINDS = [
  ['all', 'All', 'Everything at once'],
  ['pt', 'PTs', 'Preferred terms: what FAERS reports'],
  ['llt', 'LLTs', 'Lower-level terms: each picks the preferred term it is coded to', true],
  ['smq', 'SMQs', 'Standardised MedDRA Queries', true],
  ['cmq', 'CMQs', 'Custom MedDRA queries: your own named groups of preferred terms'],
];
// what a kind is, with the queries a group shares where the person has one
export const kindHint = (id, hint) => (id === 'cmq' && shareGroup() ? `${hint}, and the ones ${shareGroup()}'s people share` : hint);

function paintKinds() {
  const box = document.getElementById('oa-kinds');
  if (!box || !menuState) return;
  const { termQ, termResult, kind } = menuState;
  const q = termQ.trim().toLowerCase();
  const ready = q && termResult && termResult.q === q && termResult.kind === 'all';
  const mineCount = S.cmqs.filter((x) => !q || x.name.toLowerCase().includes(q)).length;
  if (ready) menuState.totals = { ...termResult.totals, cmq: mineCount };
  const counts = q && menuState.totals && menuState.totalsQ === q ? menuState.totals : (ready ? menuState.totals : null);
  if (ready) menuState.totalsQ = q;
  const all = counts ? counts.pt + (meddraOn() ? counts.llt + counts.smq : 0) + counts.cmq : 0;
  box.innerHTML = KINDS.filter((k) => !k[3] || meddraOn()).map(([id, label, hint]) => `<button type="button" class="tabs-line-tab oa-kind" role="tab" aria-selected="${kind === id}" data-act="kind" data-v="${id}" ${tip(kindHint(id, hint))}>${label}${counts ? `<span class="oa-kind-count">${num(id === 'all' ? all : counts[id])}</span>` : ''}</button>`).join('');
}

export function paintTermResults() {
  const box = document.getElementById('oa-term-results');
  if (!box || !menuState) return;
  paintKinds();
  const { sc, termQ, termResult, kind } = menuState;
  const f = sc.f;
  const pin = pinned(menuState);
  const show = (k) => kind === 'all' || kind === k;
  const heading = (text) => (kind === 'all' ? `<p class="menu-heading">${text}</p>` : '');
  const parts = [];
  const q = termQ.trim().toLowerCase();
  // a term's row: its tick wherever it shows, and its cases, so a term of none changes nothing
  const termRow = (t, n, attrs = '', how = {}) => choice(termOn(f, t), how.label || t, n, `data-act="pt" data-v="${esc(t)}" data-cases="${n ?? ''}" ${attrs}`, how);
  const mine = S.cmqs.filter((x) => (!q || x.name.toLowerCase().includes(q)) && (kind !== 'all' || !pin.cmqs.includes(x.id)));
  const queryRows = (list) => list.map((x) => group(`cmq:${x.id}`, choice(groupTick(f, { cmq: x.id }), x.name, null, `data-act="cmq" data-id="${x.id}"`, { note: queryNote(x) }))).join('');
  // the person's own queries, then a group's, each under its heading
  const queryParts = (head) => queryGroups(mine).map(([words, list]) => `${head(esc(words))}<div class="oa-choices">${queryRows(list)}</div>`).join('');
  const smqRows = (list) => list.filter(([code]) => kind !== 'all' || !pin.smqs.some((x) => x.code === code)).map(([code, name, narrow, broad]) => group(`smq:${code}`, `<div class="oa-smq">
      <span class="oa-smq-name">${esc(name)}${f.smqs.some((x) => x.code === code) ? ` <span class="oa-choice-note">chosen, ${f.smqs.find((x) => x.code === code).scope}</span>` : ''}</span>
      <span class="oa-smq-scopes"><button type="button" class="oa-smq-scope" data-act="smq-add" data-code="${code}" data-name="${esc(name)}" data-scope="narrow" ${tip('Narrow: the terms most specific to the condition')}>Narrow · ${num(narrow)}</button><button type="button" class="oa-smq-scope" data-act="smq-add" data-code="${code}" data-name="${esc(name)}" data-scope="broad" ${tip('Broad: narrow plus the less specific terms')}>Broad · ${num(broad)}</button></span>
    </div>`)).join('');
  if (kind === 'all') {
    const chosen = [
      ...pin.pts.map((t) => termRow(t, null)),
      ...pin.smqs.map((x) => group(`smq:${x.code}`, choice(groupTick(f, { smq: x.code, scope: x.scope }), x.name, null, `data-act="smq-tick" data-code="${x.code}" data-name="${esc(x.name)}" data-scope="${x.scope}"`, { note: x.scope }))),
      ...pin.cmqs.map((id) => { const x = S.cmqs.find((y) => y.id === id); return x ? group(`cmq:${id}`, choice(groupTick(f, { cmq: id }), x.name, null, `data-act="cmq" data-id="${id}"`, { note: isMine(x) ? `your CMQ, ${x.terms.length} terms` : queryNote(x) })) : ''; }),
    ];
    if (chosen.length) parts.push(`<p class="menu-heading">Chosen</p><div class="oa-choices">${chosen.join('')}</div>`);
  }
  const browseSmq = !q && kind === 'smq';
  const ready = termResult && termResult.q === q && termResult.kind === kind;
  if (kind === 'cmq') {
    const rows = shareGroup() ? queryParts((words) => `<p class="menu-heading">${words}</p>`) : mine.length ? `<div class="oa-choices">${queryRows(mine)}</div>` : '';
    parts.push(rows || (q ? `<p class="oa-pane-none">None of your queries has "${esc(termQ.trim())}" in its name.</p>` : '<p class="oa-pane-none">You have no custom MedDRA queries yet. Press + beside Reactions to make one.</p>'));
  } else if ((q || browseSmq) && !ready) {
    parts.push(skeletonRows(3));
  } else if (q || browseSmq) {
    const r = termResult;
    if (show('pt')) {
      const terms = r.terms.filter(([t]) => kind !== 'all' || !has(pin.pts, t));
      if (terms.length) parts.push(`${heading('Preferred terms')}<div class="oa-choices">${terms.map(([t, n]) => termRow(t, n)).join('')}</div>`);
      else if (kind === 'pt' || !(r.llts?.length || r.smqs?.length || mine.length)) parts.push(`<p class="oa-pane-none">No preferred term in this release has "${esc(termQ.trim())}" in it.</p>`);
    }
    if (show('llt') && meddraOn()) {
      if (r.llts?.length) parts.push(`${heading('Lower-level terms')}<div class="oa-choices">${r.llts.map(([llt, pt, n, currentLlt, code]) => termRow(pt, n, `data-llt="${esc(code)}" ${tip(`FAERS gives only preferred terms, so this picks ${pt}; the count is that term's cases`)}`, { label: llt, note: `coded to ${pt}${currentLlt ? '' : ', no longer current'}` })).join('')}</div>`);
      else if (kind === 'llt') parts.push(`<p class="oa-pane-none">No lower-level term has "${esc(termQ.trim())}" in it.</p>`);
    }
    if (show('smq') && meddraOn()) {
      const rows = smqRows(r.smqs);
      if (rows) parts.push(`${heading('SMQs')}${rows}`);
      else if (kind === 'smq') parts.push(`<p class="oa-pane-none">No SMQ has "${esc(termQ.trim())}" in its name.</p>`);
    }
    if (kind === 'all') parts.push(queryParts(heading));
  } else if (kind === 'all' || kind === 'pt') {
    // under PTs every reaction the Overview charts; under All the few reported most, less those chosen
    const reported = sc.summary?.reactions || [];
    const top = kind === 'pt' ? reported : reported.filter(([t]) => !has(pin.pts, t)).slice(0, listLength('reactions_suggested'));
    if (top.length) parts.push(`<p class="menu-heading">Reported most here</p><div class="oa-choices">${top.map(([t, n]) => termRow(t, n)).join('')}</div>`);
    if (kind === 'all') parts.push(queryParts((words) => `<p class="menu-heading">${words}</p>`));
  } else if (kind === 'llt') {
    parts.push('<p class="oa-pane-none">Type to find a lower-level term. Each one picks the preferred term it is coded to.</p>');
  }
  box.innerHTML = parts.join('');
}

// an SMQ or a person's own query, with the arrow that opens its preferred terms in place
function group(key, rowHtml) {
  const open = menuState.open.has(key);
  const btn = `<button type="button" class="icon-btn oa-expand" data-act="expand" data-key="${key}" aria-expanded="${open}" aria-label="${open ? 'Hide' : 'Show'} its terms" ${tip(open ? 'Hide its terms' : 'Show its terms')}>${icon('chevronDown')}</button>`;
  return `<div class="oa-group" data-open="${open}"><div class="oa-group-row">${rowHtml}${btn}</div>${open ? groupTerms(key) : ''}</div>`;
}

function groupId(key) { return `${key}|${query(menuState.sc, {}, { noReactions: true })}`; }

function groupTerms(key) {
  const ms = menuState;
  const d = ms.details[groupId(key)];
  if (!d) { loadGroup(key); return `<div class="oa-group-terms">${skeletonRows(2)}</div>`; }
  const f = ms.sc.f;
  const smq = key.startsWith('smq:');
  const row = (t, n, note = '') => choice(termOn(f, t), t, n, `data-act="pt" data-v="${esc(t)}" data-cases="${n}"`, { note });
  const rows = d.terms.map((t) => (smq ? row(t[0], t[2], t[1] === 'broad' ? 'broad' : '') : row(t[0], t[1]))).join('');
  const cmq = smq ? null : S.cmqs.find((x) => x.id === key.slice(4));
  const edit = !cmq ? '' : mayChange(cmq) ? `<button type="button" class="oa-link oa-group-edit" data-act="cmq-edit" data-id="${cmq.id}">Edit this query</button>` : `<button type="button" class="oa-link oa-group-edit" data-act="cmq-open" data-id="${cmq.id}">Open this query</button>`;
  const chosen = smq ? f.smqs.some((x) => x.code === key.slice(4)) : f.cmqs.includes(key.slice(4));
  return `<div class="oa-group-terms"><p class="oa-group-note">${num(d.terms.length)} preferred terms${smq ? ', narrow first' : ''}. ${chosen ? 'Untick one to leave it out.' : 'Tick one to use it on its own.'}</p>${rows}${edit}</div>`;
}

async function loadGroup(key) {
  const ms = menuState;
  const id = groupId(key);
  if (ms.pending.has(id)) return;
  ms.pending.add(id);
  const base = query(ms.sc, {}, { noReactions: true });
  let path;
  if (key.startsWith('smq:')) path = `/api/smq?code=${key.slice(4)}&${base}`;
  else {
    const q = S.cmqs.find((x) => x.id === key.slice(4));
    path = `/api/termcounts?${(q?.terms || []).map((t) => `pt=${encodeURIComponent(t)}`).join('&')}&${base}`;
  }
  try {
    const r = await api(path);
    if (r.code) smqTerms.set(r.code, r.terms.map(([t, scope]) => [t, scope]));
    if (menuState === ms) { ms.details[id] = r; paintTermResults(); paintRows(); }
  } catch (err) { showProblem(err); }
}

let termTimer = 0;
function searchTerms() {
  clearTimeout(termTimer);
  const ms = menuState;
  if (!ms) return;
  const q = ms.termQ.trim();
  paintTermResults();
  if ((!q && ms.kind !== 'smq') || ms.kind === 'cmq') return;
  const kind = ms.kind;
  termTimer = setTimeout(async () => {
    try {
      const r = await api(`/api/terms?q=${encodeURIComponent(q)}&kind=${kind}${meddraOn() ? '&meddra=1' : ''}&${query(ms.sc, {}, { noReactions: true })}`);
      // the counts on the tabs come from All; a narrowed kind asks again for them
      if (kind !== 'all' && q) api(`/api/terms?q=${encodeURIComponent(q)}&kind=all${meddraOn() ? '&meddra=1' : ''}&${query(ms.sc, {}, { noReactions: true })}`).then((a) => { if (menuState === ms && ms.termQ.trim().toLowerCase() === a.q) { ms.totals = { ...a.totals, cmq: S.cmqs.filter((x) => x.name.toLowerCase().includes(a.q)).length }; ms.totalsQ = a.q; paintKinds(); } }).catch(() => {});
      if (menuState === ms && ms.termQ.trim().toLowerCase() === r.q && ms.kind === kind) { ms.termResult = { ...r, kind }; paintTermResults(); }
    } catch (err) { showProblem(err); }
  }, 110);
}

const sameSet = (a, b) => a.map(low).sort().join('\n') === b.map(low).sort().join('\n');
// what the reactions are, to tell a press that leaves out or puts back a term of no cases, which
// cannot change the cases
const chosenNow = (f) => [f.pts, f.smqs.map((x) => `${x.code}:${x.scope}`), f.cmqs].map((l) => [...l].map(low).sort().join('\n')).join('|');
function pressed(sc, was, el) {
  paintTermResults(); paintRows();
  const same = el.dataset.cases === '0' && was.chosen === chosenNow(sc.f) && sameSet(toggled(was.out, el.dataset.v), sc.f.ptsOut);
  refresh(sc, { same });
}
const toggled = (list, t) => (has(list, t) ? list.filter((x) => low(x) !== low(t)) : [...list, t]);
const before = (f) => ({ chosen: chosenNow(f), out: [...f.ptsOut] });

actions({
  pt: (el) => {
    const sc = menuState?.sc || scopeNow(); const was = before(sc.f); pressTerm(sc.f, el.dataset.v);
    if (termOn(sc.f, el.dataset.v)) picked('reactions', menuState?.termQ, el.dataset.llt ? { level: 'llt', code: el.dataset.llt } : { picked: el.dataset.v });
    pressed(sc, was, el);
  },
  'smq-add': (el) => {
    const sc = menuState.sc; const { code, name, scope } = el.dataset;
    if (groupTick(sc.f, { smq: code, scope }) === true && sc.f.smqs.some((x) => x.code === code && x.scope === scope)) return; // chosen whole already: nothing changes
    chooseGroup(sc.f, { smq: code, scope }, name);
    picked('reactions', menuState.termQ, { level: 'smq', code });
    if (!smqTerms.has(code)) loadGroup(`smq:${code}`);
    paintTermResults(); paintRows(); refresh(sc);
  },
  'smq-tick': (el) => { const sc = menuState.sc; const { code, name, scope } = el.dataset; pressGroup(sc.f, { smq: code, scope }, name); if (!smqTerms.has(code)) loadGroup(`smq:${code}`); paintTermResults(); paintRows(); refresh(sc); },
  cmq: (el) => { const sc = menuState.sc; pressGroup(sc.f, { cmq: el.dataset.id }); paintTermResults(); paintRows(); refresh(sc); },
  kind: (el) => { if (!menuState) return; menuState.kind = el.dataset.v; searchTerms(); focusBox(document.getElementById('oa-term-find'), { preventScroll: true }); },
  expand: (el) => {
    const key = el.dataset.key;
    if (menuState.open.has(key)) menuState.open.delete(key); else menuState.open.add(key);
    paintTermResults();
  },
});

document.addEventListener('input', (e) => {
  if (e.target.id === 'oa-term-find' && menuState) { menuState.termQ = e.target.value; menuState.termResult = null; searchTerms(); }
});
