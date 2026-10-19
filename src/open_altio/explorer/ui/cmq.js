/* A person's own query, a custom MedDRA query (CMQ): in the end a list of preferred terms, since
   FAERS records only those. It is built from typed PTs, LLTs (their PT), SMQs (narrow or broad, or
   single terms) and the person's other CMQs, or those a group shares with them; each term remembers
   where it came from. Kept where queries.js keeps them: in this browser, or in the person's account,
   where one switch shares a query with the person's group. A colleague's shared query opens to be used
   or copied. */

import { actions } from './events.js';
import { icon } from './icons.js';
import { choice, closeMenus, dialog, toast } from './overlays.js';
import { dropQuery, fromQuery, inAccount, isMine, keepQuery, notesOf, queryGroups, queryNote, shareGroup } from './queries.js';
import { refresh, scopeNow } from './scope.js';
import { api } from './server.js';
import { S, meddraOn } from './state.js';
import { KINDS, kindHint, settleTerms } from './terms.js';
import { day, esc, focusBox, num, skeletonRows, tip } from './util.js';

let draft = null; // { id, name, terms, src, shared, by, q, kind, result, open, details }
const byId = (id) => S.cmqs.find((x) => x.id === id);

// the switch that shares a query with the person's group, and who may change it then
const shareSwitch = () => `<div class="field"><p><button type="button" class="switch oa-rule-switch" role="switch" aria-checked="${draft.shared}" data-act="cmq-share"><span class="switch-track"></span><span class="oa-switch-word">Share with ${esc(shareGroup())}</span></button></p>
      <p class="note-faint">Everyone in ${esc(shareGroup())} can use it; only ${draft.by ? esc(draft.by) : 'you'} and its admins can change it.</p></div>`;

// a query of the person's to edit, a new one, or a new copy of one (named as their copy, not shared)
function openCmq(id, { copyOf = null } = {}) {
  closeMenus();
  const q = id ? byId(id) : null;
  const from = q || (copyOf ? byId(copyOf) : null);
  draft = { id: q?.id || null, name: q ? q.name : from ? `${from.name} (my copy)` : '', terms: [...(from?.terms || [])], src: from ? notesOf(from) : {}, shared: !!q?.shared, by: q && !isMine(q) ? q.by : null, q: '', kind: 'all', result: null, open: new Set(), details: {} };
  const dlg = dialog(q ? 'Custom MedDRA query (CMQ)' : 'New custom MedDRA query (CMQ)', `
    <p class="oa-dialog-lead">Your own named group of preferred terms, kept ${inAccount() ? 'in your account' : 'for you'} and used like an SMQ. Build it from preferred terms${meddraOn() ? ', lower-level terms, SMQs' : ''} and your other queries; a case counts when it has any of its terms.</p>
    <label class="field"><span class="field-label">Its name, as your filters will show it</span><input class="field-input" id="oa-cmq-name" value="${esc(draft.name)}" placeholder="For example: Gastrointestinal upset" autocomplete="off"></label>
    <div class="oa-cmq-cols">
      <div class="oa-cmq-col">
        <p class="menu-heading oa-cmq-add">Add terms to it</p>
        <input class="field-input" id="oa-cmq-find" type="search" placeholder="${meddraOn() ? 'Type a term, an SMQ or another query' : 'Type a preferred term or another query'}" autocomplete="off" aria-label="Find terms to add">
        <div class="tabs-line oa-kinds" id="oa-cmq-kinds" role="tablist" aria-label="Which kind of term"></div>
        <div class="oa-choices oa-cmq-list" id="oa-cmq-found"></div>
      </div>
      <div class="oa-cmq-col">
        <div class="oa-cmq-head"><p class="menu-heading" id="oa-cmq-count">In the query</p><button type="button" class="oa-link" data-act="cmq-clear">Remove all</button></div>
        <div class="oa-choices oa-cmq-list oa-cmq-in" id="oa-cmq-terms"></div>
      </div>
    </div>
    <p class="note-faint">Counts are cases in the whole release.${inAccount() ? '' : ' Kept in this browser.'}</p>
    ${shareGroup() ? shareSwitch() : ''}`,
  `${q ? '<button type="button" class="btn oa-danger-btn" data-act="cmq-delete">Delete</button>' : ''}<button type="button" class="btn" data-act="close-dialog">Cancel</button><button type="button" class="btn btn-primary" data-act="cmq-save">Save and run</button>`);
  dlg.classList.add('oa-cmq-dialog');
  dlg.addEventListener('close', () => { draft = null; });
  paintDraft();
  searchDraft();
  focusBox(dlg.querySelector('#oa-cmq-name'));
}

function addToDraft(terms, source) {
  for (const t of terms) {
    if (!draft.terms.includes(t)) { draft.terms.push(t); draft.src[t] = source; }
  }
}

function draftGroup(key, rowHtml) {
  const open = draft.open.has(key);
  const btn = `<button type="button" class="icon-btn oa-expand" data-act="cmq-expand" data-key="${key}" aria-expanded="${open}" aria-label="${open ? 'Hide' : 'Show'} its terms" ${tip(open ? 'Hide its terms' : 'Show its terms, to add single ones')}>${icon('chevronDown')}</button>`;
  let body = '';
  if (open) {
    const d = draft.details[key];
    if (!d) { loadDraftGroup(key); body = `<div class="oa-group-terms">${skeletonRows(1)}</div>`; }
    else {
      body = `<div class="oa-group-terms">${d.terms.map(([t, n, note]) => choice(draft.terms.includes(t), t, n, `data-act="cmq-one" data-v="${esc(t)}" data-from="${esc(d.from)}"`, { note: note || '' })).join('')}</div>`;
    }
  }
  return `<div class="oa-group" data-open="${open}"><div class="oa-group-row">${rowHtml}${btn}</div>${body}</div>`;
}

async function loadDraftGroup(key) {
  const d = draft;
  if (key.startsWith('smq:')) {
    const r = await api(`/api/smq?code=${key.slice(4)}`);
    if (draft === d) { d.details[key] = { from: r.name, terms: r.terms.map(([t, scope, n]) => [t, n, scope === 'broad' ? 'broad' : 'narrow']) }; paintDraft(); }
  } else {
    const q = byId(key.slice(4));
    const r = await api(`/api/termcounts?${(q?.terms || []).map((t) => `pt=${encodeURIComponent(t)}`).join('&')}`);
    if (draft === d) { d.details[key] = { from: fromQuery(q), terms: r.terms.map(([t, n]) => [t, n, '']) }; paintDraft(); }
  }
}

function paintDraft() {
  if (!draft) return;
  const found = document.getElementById('oa-cmq-found');
  const terms = document.getElementById('oa-cmq-terms');
  const kinds = document.getElementById('oa-cmq-kinds');
  if (!found || !terms) return;
  const q = draft.q.trim().toLowerCase();
  const r = draft.result && draft.result.q === q && draft.result.kind === draft.kind ? draft.result : null;
  const others = S.cmqs.filter((x) => x.id !== draft.id && (!q || x.name.toLowerCase().includes(q)));
  const totals = draft.totals && draft.totalsQ === q ? draft.totals : null;
  kinds.innerHTML = KINDS.filter((k) => !k[3] || meddraOn()).map(([id, label, hint]) => {
    const n = totals ? (id === 'all' ? totals.pt + (meddraOn() ? totals.llt + totals.smq : 0) + others.length : id === 'cmq' ? others.length : totals[id]) : null;
    return `<button type="button" class="tabs-line-tab oa-kind" role="tab" aria-selected="${draft.kind === id}" data-act="cmq-kind" data-v="${id}" ${tip(kindHint(id, hint))}>${label}${n == null ? '' : `<span class="oa-kind-count">${num(n)}</span>`}</button>`;
  }).join('');
  const show = (k) => draft.kind === 'all' || draft.kind === k;
  const heading = (text) => (draft.kind === 'all' ? `<p class="menu-heading">${text}</p>` : '');
  const parts = [];
  const otherRows = (list) => list.map((x) => draftGroup(`cmq:${x.id}`, `<div class="oa-smq"><span class="oa-smq-name">${esc(x.name)} <span class="oa-choice-note">${esc(queryNote(x))}</span></span>
      <span class="oa-smq-scopes"><button type="button" class="oa-smq-scope" data-act="cmq-cmq" data-id="${x.id}">Add its ${num(x.terms.length)} terms</button></span></div>`)).join('');
  // the person's other queries, then a group's, each under its heading where there is a group or more kinds
  const otherParts = (headed) => queryGroups(others, { other: true }).map(([words, list]) => `${headed ? `<p class="menu-heading">${esc(words)}</p>` : ''}${otherRows(list)}`).join('');
  if (draft.kind === 'cmq') {
    parts.push(others.length ? otherParts(!!shareGroup()) : '<p class="oa-pane-none">No other queries to build from yet.</p>');
  } else if (!q && draft.kind !== 'smq') {
    parts.push(`<p class="oa-pane-none">Type to find ${meddraOn() ? 'preferred terms, lower-level terms and SMQs' : 'preferred terms'}.</p>`);
    if (draft.kind === 'all') parts.push(otherParts(true));
  } else if (!r) {
    parts.push(skeletonRows(3));
  } else {
    if (show('pt') && r.terms.length) parts.push(`${heading('Preferred terms')}${r.terms.map(([t, n]) => choice(draft.terms.includes(t), t, n, `data-act="cmq-term" data-v="${esc(t)}"`)).join('')}`);
    if (show('llt') && meddraOn() && r.llts?.length) parts.push(`${heading('Lower-level terms')}${r.llts.map(([llt, pt, n]) => choice(draft.terms.includes(pt), llt, n, `data-act="cmq-llt" data-v="${esc(pt)}" data-llt="${esc(llt)}"`, { note: `adds ${pt}` })).join('')}`);
    if (show('smq') && meddraOn() && r.smqs?.length) parts.push(`${heading('SMQs')}${r.smqs.map(([code, name, narrow, broad]) => draftGroup(`smq:${code}`, `<div class="oa-smq"><span class="oa-smq-name">${esc(name)}</span>
        <span class="oa-smq-scopes"><button type="button" class="oa-smq-scope" data-act="cmq-smq" data-code="${code}" data-name="${esc(name)}" data-scope="narrow" ${tip('Add every narrow term')}>Add narrow · ${num(narrow)}</button><button type="button" class="oa-smq-scope" data-act="cmq-smq" data-code="${code}" data-name="${esc(name)}" data-scope="broad" ${tip('Add every narrow and broad term')}>Add broad · ${num(broad)}</button></span></div>`)).join('')}`);
    if (draft.kind === 'all' && others.length) parts.push(otherParts(true));
    if (!parts.length) parts.push(`<p class="oa-pane-none">Nothing has "${esc(draft.q.trim())}" in it.</p>`);
  }
  found.innerHTML = parts.join('');
  terms.innerHTML = draft.terms.length
    ? draft.terms.map((t) => choice(true, t, null, `data-act="cmq-term" data-v="${esc(t)}"`, { note: draft.src[t] && draft.src[t] !== 'typed' ? draft.src[t] : '' })).join('')
    : '<p class="oa-pane-none">None yet. Tick terms on the left, or add a whole SMQ or query.</p>';
  document.getElementById('oa-cmq-count').textContent = `In the query (${draft.terms.length})`;
}

let draftTimer = 0;
function searchDraft() {
  clearTimeout(draftTimer);
  const d = draft;
  if (!d) return;
  const q = d.q.trim();
  paintDraft();
  if ((!q && d.kind !== 'smq') || d.kind === 'cmq') return;
  const kind = d.kind;
  draftTimer = setTimeout(async () => {
    const meddra = meddraOn() ? '&meddra=1' : '';
    const r = await api(`/api/terms?q=${encodeURIComponent(q)}&kind=${kind}${meddra}`);
    if (q) api(`/api/terms?q=${encodeURIComponent(q)}&kind=all${meddra}`).then((a) => { if (draft === d && d.q.trim().toLowerCase() === a.q) { d.totals = a.totals; d.totalsQ = a.q; paintDraft(); } }).catch(() => {});
    if (draft === d && d.q.trim().toLowerCase() === r.q && d.kind === kind) { d.result = { ...r, kind }; paintDraft(); }
  }, 110);
}

// a term in or out of the query, remembering where it came from
const toggleTerm = (v, source) => {
  if (draft.terms.includes(v)) { draft.terms = draft.terms.filter((x) => x !== v); delete draft.src[v]; } else addToDraft([v], source);
  paintDraft();
};

// a query chosen under Reactions on the page in view
function choose(q) {
  const sc = scopeNow();
  if (sc && !sc.f.cmqs.includes(q.id)) { sc.f.cmqs.push(q.id); refresh(sc); }
}

// a colleague's shared query, which the person may use or copy but not change
function openShared(id) {
  closeMenus();
  const q = byId(id);
  if (!q) return;
  const notes = notesOf(q);
  const note = (t) => (notes[t] && notes[t] !== 'typed' ? `<div class="oa-choice-note">${esc(notes[t])}</div>` : '');
  dialog('Custom MedDRA query (CMQ)', `<p class="oa-dialog-lead">Shared with ${esc(shareGroup())}. Use it in your filters as it is, or copy it to your own queries and change your copy.</p>
    <div class="field"><span class="field-label">Its name, as your filters show it</span><span class="oa-setting-name">${esc(q.name)}</span>
      <span class="note-faint">Made by ${esc(q.by)} on ${day(q.made)}</span></div>
    <div><h3 class="case-section">In the query (${num(q.terms.length)})</h3>
      <ul class="oa-list">${q.terms.map((t) => `<li>${esc(t)}${note(t)}</li>`).join('')}</ul></div>
    <p class="note-faint">Only ${esc(q.by)}, who made it, and ${esc(shareGroup())}'s admins can change or delete it.</p>`,
  `<button type="button" class="btn" data-act="cmq-copy" data-id="${q.id}">Copy to my queries</button><button type="button" class="btn" data-act="close-dialog">Cancel</button><button type="button" class="btn btn-primary" data-act="cmq-use" data-id="${q.id}">Use</button>`).classList.add('oa-cmq-shared');
}

actions({
  'cmq-new': () => openCmq(null),
  'cmq-edit': (el) => openCmq(el.dataset.id),
  'cmq-term': (el) => toggleTerm(el.dataset.v, 'typed'),
  'cmq-llt': (el) => toggleTerm(el.dataset.v, `via LLT ${el.dataset.llt}`),
  'cmq-one': (el) => toggleTerm(el.dataset.v, `from ${el.dataset.from}`),
  'cmq-smq': async (el) => {
    const d = draft; const { code, name, scope } = el.dataset;
    const r = await api(`/api/smq?code=${code}`);
    if (draft !== d) return;
    const terms = r.terms.filter(([, sc]) => scope === 'broad' || sc === 'narrow').map(([t]) => t);
    const before = d.terms.length;
    addToDraft(terms, `from ${name}, ${scope}`);
    paintDraft();
    toast(`${num(d.terms.length - before)} terms added from ${name}, ${scope}${d.terms.length - before < terms.length ? ` (${num(terms.length - (d.terms.length - before))} were already in)` : ''}.`);
  },
  'cmq-cmq': (el) => {
    const q = byId(el.dataset.id);
    const before = draft.terms.length;
    addToDraft(q.terms, `from ${fromQuery(q)}`);
    paintDraft();
    toast(`${num(draft.terms.length - before)} terms added from ${q.name}.`);
  },
  'cmq-kind': (el) => { draft.kind = el.dataset.v; draft.result = null; searchDraft(); focusBox(document.getElementById('oa-cmq-find'), { preventScroll: true }); },
  'cmq-expand': (el) => { const k = el.dataset.key; if (draft.open.has(k)) draft.open.delete(k); else draft.open.add(k); paintDraft(); },
  'cmq-clear': () => { draft.terms = []; draft.src = {}; paintDraft(); },
  'cmq-share': (el) => { draft.shared = !draft.shared; el.setAttribute('aria-checked', String(draft.shared)); },
  'cmq-save': async (el) => {
    const d = draft;
    if (d.saving) return;
    d.name = document.getElementById('oa-cmq-name').value.trim();
    if (!d.name) { toast('Give the query a name.'); return; }
    if (!d.terms.length) { toast('Add at least one preferred term.'); return; }
    const was = byId(d.id);
    const asked = { ...was, id: d.id, name: d.name, terms: d.terms, src: Object.fromEntries(d.terms.map((t) => [t, d.src[t] || 'typed'])) };
    if (inAccount()) asked.shared = d.shared;
    d.saving = true;
    const q = await keepQuery(asked).finally(() => { d.saving = false; });
    if (q.problem) { toast(q.problem); return; }
    Object.values(S.scopes).forEach((one) => { if (one.f.cmqs.includes(q.id)) { one.summaryKey = null; settleTerms(one.f); } });
    el.closest('dialog').close();
    choose(q);
    toast(`CMQ ${q.name}: ${q.terms.length} terms, chosen under Reactions.${q.shared && !was?.shared && shareGroup() ? ` Shared with ${shareGroup()}.` : ''}`);
  },
  'cmq-delete': async (el) => {
    const q = byId(draft.id);
    const done = await dropQuery(q);
    if (done.problem) { toast(done.problem); return; }
    Object.values(S.scopes).forEach((sc) => { sc.f.cmqs = sc.f.cmqs.filter((x) => x !== q.id); settleTerms(sc.f); });
    el.closest('dialog').close();
    const sc = scopeNow(); if (sc) refresh(sc);
    if (q.shared && shareGroup()) toast(`${q.name} is deleted. ${shareGroup()}'s people no longer see it.`);
  },
  // a colleague's shared query: opened, used as it is, or copied to the person's own
  'cmq-open': (el) => openShared(el.dataset.id),
  'cmq-use': (el) => {
    const q = byId(el.dataset.id);
    el.closest('dialog').close();
    choose(q);
    toast(`CMQ ${q.name}: ${q.terms.length} terms, chosen under Reactions.`);
  },
  'cmq-copy': (el) => { el.closest('dialog').close(); openCmq(null, { copyOf: el.dataset.id }); },
});

// ticking a choice keeps the typing where it was, so a person can go on typing
document.addEventListener('mousedown', (e) => {
  if (e.target.closest('.oa-cmq-dialog .oa-choice, .oa-cmq-dialog .oa-kind, .oa-cmq-dialog .oa-expand, .oa-cmq-dialog .oa-smq-scope')) e.preventDefault();
});
document.addEventListener('input', (e) => {
  if (e.target.id === 'oa-cmq-find' && draft) { draft.q = e.target.value; draft.result = null; searchDraft(); }
});
