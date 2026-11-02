/* The term search a page can mount on its own: the Reactions search without the filters. It asks
   /api/terms for the products it is given, offers preferred terms and, to a viewer with MedDRA's
   licensed part, lower-level terms and SMQs, and hands each pick to the page. It keeps nothing and
   changes no filter. */

import { KINDS } from './terms.js';
import { picked } from './host.js';
import { choice, showProblem } from './overlays.js';
import { api } from './server.js';
import { meddraOn } from './state.js';
import { esc, num, skeletonRows, tip } from './util.js';

const WAIT = 110;

// el: where to draw. products: the drug names the counts are over (none: every case).
// onPick: ({ kind: 'pt', pt, llt? }) or ({ kind: 'smq', code, name, scope }).
// tabs: kinds of term to offer, from 'all', 'pt', 'llt', 'smq'; kinds only a licensed viewer has are left out for others.
export function termSearch(el, { products = [], onPick, tabs = ['all', 'pt', 'llt', 'smq'] } = {}) {
  if (typeof onPick !== 'function') throw new Error('termSearch() needs an onPick function');
  const licensed = meddraOn();
  const kinds = KINDS.filter(([id, , , lic]) => tabs.includes(id) && (!lic || licensed));
  const state = { q: '', kind: kinds[0][0], result: null, timer: 0, ask: 0 };
  el.classList.add('oa-term-search');
  el.innerHTML = `<input class="field-input oa-menu-search" type="search" autocomplete="off" spellcheck="false" aria-label="Find reactions" placeholder="${licensed ? 'Type a term or an SMQ' : 'Type a preferred term'}">
    <div class="tabs-line oa-kinds" role="tablist" aria-label="Which kind of term">${kinds.map(([id, label, hint]) => `<button type="button" class="tabs-line-tab oa-kind" role="tab" aria-selected="${id === state.kind}" data-kind="${id}" ${tip(hint)}>${label}</button>`).join('')}</div>
    <div class="oa-term-search-results" aria-live="polite"></div>`;
  const box = el.querySelector('input');
  const out = el.querySelector('.oa-term-search-results');
  const paintTabs = () => el.querySelectorAll('.oa-kind').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.kind === state.kind)));

  function paint() {
    const r = state.result;
    if (!state.q && state.kind !== 'smq') { out.innerHTML = '<p class="oa-pane-none">Type to find a term.</p>'; return; }
    if (!r) { out.innerHTML = skeletonRows(3); return; }
    const parts = r.why_no_licensed ? [`<p class="oa-term-why">${esc(r.why_no_licensed)}</p>`] : [];
    const head = (t) => (state.kind === 'all' ? `<p class="menu-heading">${t}</p>` : '');
    const row = (label, n, attrs, note) => choice(false, label, n, attrs, { note });
    if (r.terms.length) parts.push(`${head('Preferred terms')}<div class="oa-choices">${r.terms.map(([t, n]) => row(t, n, `data-pt="${esc(t)}"`)).join('')}</div>`);
    if (r.llts?.length) parts.push(`${head('Lower-level terms')}<div class="oa-choices">${r.llts.map(([llt, pt, n, current, code]) => row(llt, n, `data-pt="${esc(pt)}" data-llt="${esc(llt)}" data-code="${esc(code)}"`, `coded to ${pt}${current ? '' : ', no longer current'}`)).join('')}</div>`);
    if (r.smqs?.length) {
      parts.push(`${head('SMQs')}${r.smqs.map(([code, name, narrow, broad]) => `<div class="oa-smq"><span class="oa-smq-name">${esc(name)}</span><span class="oa-smq-scopes">${[['narrow', narrow], ['broad', broad]].map(([scope, n]) => `<button type="button" class="oa-smq-scope" data-smq="${esc(code)}" data-name="${esc(name)}" data-scope="${scope}">${scope === 'narrow' ? 'Narrow' : 'Broad'} · ${num(n)}</button>`).join('')}</span></div>`).join('')}`);
    }
    out.innerHTML = parts.join('') || `<p class="oa-pane-none">Nothing found for "${esc(state.q)}".</p>`;
  }

  function search() {
    clearTimeout(state.timer);
    state.result = null;
    paint();
    const q = state.q.trim();
    if (!q && state.kind !== 'smq') return;
    const mine = ++state.ask;
    state.timer = setTimeout(async () => {
      const p = new URLSearchParams({ q, kind: state.kind, meddra: '1' });
      products.forEach((d) => p.append('dprod', d));
      try {
        const r = await api(`/api/terms?${p}`);
        if (mine !== state.ask) return;
        state.result = r;
        paint();
      } catch (err) { showProblem(err); }
    }, WAIT);
  }

  box.addEventListener('input', () => { state.q = box.value; search(); });
  el.addEventListener('click', (e) => {
    const tab = e.target.closest('[data-kind]');
    if (tab) { state.kind = tab.dataset.kind; paintTabs(); search(); return; }
    const smq = e.target.closest('[data-smq]');
    if (smq) {
      const { smq: code, name, scope } = smq.dataset;
      picked('reactions', state.q, { level: 'smq', code });
      onPick({ kind: 'smq', code, name, scope });
      return;
    }
    const pt = e.target.closest('[data-pt]');
    if (!pt) return;
    const { pt: term, llt, code } = pt.dataset;
    picked('reactions', state.q, llt ? { level: 'llt', code } : { picked: term });
    onPick(llt ? { kind: 'pt', pt: term, llt } : { kind: 'pt', pt: term });
  });
  if (state.kind === 'smq') search(); else paint();
}
