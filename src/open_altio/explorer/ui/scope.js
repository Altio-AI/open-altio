/* A product's page, or All cases: the title, the count line, the strip of filters on, and the
   Overview or Cases tab under them, drawn as /api answers and drawn again as the filters change.
   A product's page counts one drug, as its line above the count says (drugs.js). */

import { casesTable, caseSort } from './cases.js';
import { overview, scrollChartsToEnd } from './charts.js';
import { drugBar, unitSwitch } from './drugs.js';
import { actions } from './events.js';
import { FILTERS, ROLES, clearFilter, filterWords, filtersFor, query, rolesChanged } from './filters.js';
import { refreshMenu } from './filtermenu.js';
import { framed, repaintSide } from './frame.js';
import { icon } from './icons.js';
import { labelsOn } from './labels.js';
import { showProblem } from './overlays.js';
import { pinButton } from './products.js';
import { TABS, current, drawn, productPath, putAddress, render } from './router.js';
import { rulesNotice } from './rules/page.js';
import { api } from './server.js';
import { loadStatistics, loadStrata, paintStatistics, statisticsLead, statisticsToolbar } from './statistics.js';
import { S, keepProducts, learnTitles, listLength, productLabel, releaseSince, whoOn } from './state.js';
import { esc, num, skeletonRows, tip } from './util.js';

export const scopeNow = () => current()?.scope;

function scopePage(sc) {
  const base = sc.product ? `/product/${encodeURIComponent(sc.product)}` : '/all';
  return framed(`<main class="product-page oa-scope">
    <h1 class="product-title" id="oa-title">${title(sc)}</h1>
    <p class="oa-subtitle" id="oa-subtitle">${subtitle(sc)}</p>
    <div class="oa-tabs-row">
      <div class="product-tabs" role="tablist" aria-label="Sections">
        ${TABS.filter(([id]) => id !== 'statistics' || S.me?.statistics !== false).map(([id, label]) => `<a class="product-tab" role="tab" href="${base}/${id}" aria-selected="${sc.tab === id}">${label}</a>`).join('')}
      </div>
      ${sc.product ? `<div class="oa-drugbar" id="oa-drugbar">${drugBar(sc)}</div>` : ''}
    </div>
    <section class="product-panel oa-panel" role="tabpanel">
      <div class="oa-toolbar" id="oa-toolbar">${sc.tab === 'statistics' ? statisticsToolbar(sc) : toolbar(sc)}</div>
      <div class="oa-strip" id="oa-strip">${sc.tab === 'statistics' ? statisticsLead() : filterStrip(sc)}</div>
      <div id="oa-body">${bodySkeleton(sc)}</div>
    </section>
  </main>`, sc.product ? `p:${sc.product}` : 'all');
}

// a product's title: its drug, how many of FDA's spellings its page counts, which opens them, and its pin
function title(sc) {
  if (!sc.product) return 'All cases';
  const n = sc.summary?.spellings ?? sc.info?.spellings?.[sc.info.kind === 'spelling' ? 'exact' : sc.unit];
  const spellings = n == null ? '' : `<button type="button" class="oa-link oa-title-spellings" data-act="spellings" data-row="spellings" ${tip("FDA's spellings this page counts: open them to leave one out or add one")}>${num(n)} ${n === 1 ? 'spelling' : 'spellings'}</button>`;
  return `${esc(productLabel(sc.product))}<span class="oa-title-end">${spellings}${pinButton(sc.product)}</span>`;
}

function subtitle(sc) {
  if (!sc.product) return `Every case, from ${releaseSince()}.${rulesNotice()}`;
  const p = sc.info;
  if (!p) return '&nbsp;';
  const label = productLabel(sc.product);
  const parts = [label !== p.title ? `${esc(p.title)} <span class="oa-dot">·</span> ${esc(p.about)}` : esc(p.about)];
  if (p.reported.length) parts.push(`reported most as ${esc(p.reported.slice(0, listLength('names_on_page')).join(', '))}`);
  return parts.join(', ') + rulesNotice();
}

function toolbar(sc) {
  return `<button type="button" class="btn oa-filters-btn" data-act="filters" aria-haspopup="menu" aria-label="Filters">${icon('filter')}<span class="oa-btn-words">Filters</span></button>
    <p class="oa-countline" id="oa-countline">${countLine(sc)}</p>
    <button type="button" class="btn oa-export-btn" data-act="export" aria-label="Export">${icon('download')}<span class="oa-btn-words">Export</span></button>`;
}

// the counts, then one tick box: probable duplicates in or out. Its words never change, so the line
// does not move; the box shows whether they are included, and keeps its place while the counts load.
const DUP_TIP = 'Two rules: the same event date, age, sex, country, drugs and reactions, or the same manufacturer case number from one sender. The latest received copy is shown; the others are flagged, never deleted';
function dupTick(sc) {
  const n = sc.summary?.set_aside;
  if (!n) return '';
  return `<label class="oa-dup-tick"><input type="checkbox" id="oa-dups" data-act="dups-tick"${sc.f.dedup === 'all' ? ' checked' : ''}><span class="oa-tick" aria-hidden="true">${icon('check')}</span><span>Include <span class="oa-has-tip" ${tip(DUP_TIP)}>${num(n)} probable duplicates</span></span></label>`;
}

function countLine(sc, loading = false) {
  const s = sc.summary;
  if (loading) return `<span class="skeleton oa-count-skeleton"></span>${dupTick(sc)}`;
  if (!s) return '<span class="skeleton oa-count-skeleton"></span>';
  const parts = [`<strong>${num(s.cases)}</strong> cases`, `<span class="oa-has-tip" ${tip('Cases with any outcome: death, life-threatening, hospitalization, disability, congenital anomaly, intervention or other serious')}>${num(s.serious)} serious</span>`];
  const tick = dupTick(sc);
  if (tick) parts.push(tick);
  return parts.join('<span class="oa-dot">·</span>');
}

// the box keeps focus through the repaint
function paintCountLine(sc, loading = false) {
  const line = document.getElementById('oa-countline');
  if (!line) return;
  const had = document.activeElement?.id === 'oa-dups';
  line.innerHTML = countLine(sc, loading);
  if (had) document.getElementById('oa-dups')?.focus({ preventScroll: true });
}
document.addEventListener('change', (e) => {
  if (e.target.id !== 'oa-dups') return;
  const sc = scopeNow(); if (!sc) return;
  sc.f.dedup = e.target.checked ? 'all' : 'kept_only';
  refresh(sc);
});

// one line that always keeps its height, so adding or removing a filter never moves the page; a
// product page's roles join it while they differ from the ones it opens with (their ticks are the edit)
function filterStrip(sc) {
  const lines = [[ROLES, rolesChanged(sc)], ...filtersFor(sc).map((d) => [d, filterWords(sc, d)])].filter(([, w]) => w);
  if (!lines.length) return '<span class="oa-faint">No filters. Use Filters to narrow the cases, or press a bar in a chart.</span>';
  return `<div class="oa-strip-items">${lines.map(([d, w]) => `<span class="oa-strip-item">
      <button type="button" class="oa-strip-edit" ${d === ROLES ? 'data-act="roles-ticks"' : `data-act="filters" data-row="${d.key}"`} ${tip(`${d.label}: ${w}`)}><span class="oa-strip-name">${d.label}</span><span class="oa-strip-value">${esc(w)}</span></button>
      <button type="button" class="icon-btn oa-strip-x" data-act="unfilter" data-key="${d.key}" aria-label="Remove the ${d.label} filter">${icon('close')}</button></span>`).join('')}</div>
    <button type="button" class="oa-link oa-clear" data-act="unfilter-all">Clear all</button>`;
}

export function bodySkeleton(sc) {
  if (sc.tab === 'overview') {
    return `<div class="oa-charts">${['wide', '', '', '', '', '', '', ...(sc.product ? [] : ['']), ...(sc.product || !whoOn() ? [] : [''])].map((w) => `<section class="oa-chart ${w ? 'oa-chart-wide' : ''}"><span class="skeleton oa-chart-skeleton"></span></section>`).join('')}</div>`;
  }
  return `<div class="oa-table-skeleton">${skeletonRows(4)}</div>`;
}

let loadSeq = 0;
async function loadScope(sc) {
  const seq = ++loadSeq;
  const q = query(sc);
  const jobs = [];
  // a name the release does not hold is no page (noSuchProduct); any other of FDA's names opens its drug
  if (sc.product && !sc.info) jobs.push(api(`/api/product?product=${encodeURIComponent(sc.product)}`).then((p) => { sc.info = p; learnTitles([p]); }).catch((err) => { if (err.message === 'not found') sc.missing = true; else throw err; }));
  if (sc.tab === 'statistics') jobs.push(loadStatistics(sc));
  else jobs.push(api(`/api/summary?${q}`).then((s) => { sc.summary = s; sc.summaryKey = q; learnTitles((s.drugs || []).map(([name, , named]) => ({ name, title: named }))); }));
  if (sc.tab === 'overview') jobs.push(api(`/api/timeline?grain=${sc.grain || 'year'}&${q}`).then((t) => { sc.timeline = t; }));
  if (sc.tab === 'cases') jobs.push(api(`/api/cases?${query(sc, { page: sc.page, sort: caseSort(sc) })}`).then((c) => { sc.cases = c; }));
  if (sc.tab === 'cases') jobs.push(loadStrata(sc));
  if (sc.product && labelsOn()) loadLabelCounts(sc, q);
  const settled = await Promise.allSettled(jobs);
  if (seq !== loadSeq) return;
  if (sc.missing) { if (current()?.scope === sc) noSuchProduct(sc); return; }
  if (sc.info && sc.info.name !== sc.product) { if (current()?.scope === sc) openItsDrug(sc); return; }
  const failed = settled.find((x) => x.status === 'rejected');
  if (failed) { showProblem(failed.reason); return; }
  if (current()?.scope !== sc) return;
  keepTitle(sc);
  paintScope(sc);
}

// Label status's counts come on their own, so the page never waits for them
function loadLabelCounts(sc, q) {
  api(`/api/labels/cases?${q}`).then((r) => { if (query(sc) === q) { sc.labelCounts = r.cases; refreshMenu(); } }).catch(showProblem);
}

// a product FDA does not name: home, in the address's place, and off the person's list if this visit put it there
function noSuchProduct(sc) {
  delete S.scopes[sc.key];
  if (sc.added) { S.products = S.products.filter((p) => p.name !== sc.product); keepProducts(); }
  putAddress('/');
  render();
}

// an older address, or a brand: the page of the drug it names, in the address's place, and the
// person's list keeps the drug under its own name
function openItsDrug(sc) {
  const { name, title: named } = sc.info;
  const kept = S.products.find((p) => p.name === sc.product);
  if (kept) {
    const other = S.products.find((p) => p.name === name);
    if (other) { other.pinned ||= kept.pinned; S.products = S.products.filter((p) => p !== kept); } else Object.assign(kept, { name, title: named });
    keepProducts();
  }
  delete S.scopes[sc.key];
  putAddress(productPath(name, sc.tab));
  render();
}

function paintScope(sc) {
  const head = document.getElementById('oa-title');
  if (head) head.innerHTML = title(sc);
  const sub = document.getElementById('oa-subtitle');
  if (sub) sub.innerHTML = subtitle(sc);
  const unit = document.querySelector('#oa-drugbar .oa-unit');
  if (unit) unit.outerHTML = unitSwitch(sc);
  if (sc.tab === 'statistics') { paintStatistics(sc); return; }
  paintCountLine(sc);
  const strip = document.getElementById('oa-strip');
  if (strip) strip.innerHTML = filterStrip(sc);
  const body = document.getElementById('oa-body');
  if (!body) return;
  body.removeAttribute('data-state');
  if (sc.tab === 'overview') { body.innerHTML = overview(sc); scrollChartsToEnd(); }
  else body.innerHTML = casesTable(sc);
  refreshMenu();
}

// the scope's filters changed: the strip at once, then its counts and its tab as /api answers; a
// change that `same` says cannot change the cases (a class or term of no cases left out or put
// back) redraws only the strip, so nothing on the page seems to load
export function refresh(sc, { keepPage = false, same = false } = {}) {
  const strip = document.getElementById('oa-strip');
  if (same) {
    if (sc.summary && sc.summaryKey) sc.summaryKey = query(sc);
    if (strip && sc.tab !== 'statistics') strip.innerHTML = filterStrip(sc);
    return;
  }
  if (!keepPage) sc.page = 1;
  if (strip) strip.innerHTML = filterStrip(sc);
  paintCountLine(sc, true);
  document.getElementById('oa-body')?.setAttribute('data-state', 'loading');
  loadScope(sc);
}

function keepOpened(sc) {
  const now = Date.now();
  const found = S.products.find((p) => p.name === sc.product);
  if (found) found.opened = now;
  else S.products.push({ name: sc.product, label: '', opened: now, pinned: false });
  keepProducts();
}

// the drug's title kept with it on the person's list, once /api names it
function keepTitle(sc) {
  const found = S.products.find((p) => p.name === sc.product);
  if (found && sc.info && found.title !== sc.info.title) { found.title = sc.info.title; keepProducts(); repaintSide(); }
}

drawn('scope', (r, app) => {
  const sc = r.scope;
  if (TABS.some(([id]) => id === r.tab)) sc.tab = r.tab;
  if (sc.product) { sc.added ??= !S.products.some((p) => p.name === sc.product); keepOpened(sc); } // added: whether this visit put it on the list
  app.innerHTML = scopePage(sc);
  if (sc.tab === 'statistics' ? sc.stat?.rows : sc.summary && sc.summaryKey === query(sc) && (sc.tab !== 'cases' || sc.cases)) paintScope(sc);
  loadScope(sc);
});

// the strip's filters taken off: the drug bar too, as the roles are ticked there
function unfiltered(sc, keys) {
  keys.forEach((key) => clearFilter(sc, key));
  const bar = document.getElementById('oa-drugbar');
  if (bar && sc.product) bar.innerHTML = drugBar(sc);
  refresh(sc);
}

actions({
  unfilter: (el) => unfiltered(scopeNow(), [el.dataset.key]),
  'unfilter-all': () => unfiltered(scopeNow(), [ROLES, ...FILTERS].map((d) => d.key)),
  'roles-ticks': () => document.querySelector('#oa-drugbar .oa-roles [role="checkbox"]')?.focus(),
});
