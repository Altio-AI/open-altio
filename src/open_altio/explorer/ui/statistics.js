/* A product's Statistics tab, or All cases': EBGM, PRR, ROR, RRR, IC and the time to onset for each
   ingredient and reaction pair, from the release's statistics (/api/statistics), read with the
   screens the person chose (screens.js); and, under the cases a pair's row opens, its ROR within
   each age band and each sex (/api/statistics/strata). Where the release holds the statistics of
   each WHO class, All cases' list may be by class, and a drug's rows show its class's EB05
   (classstats.js). The filters do not change these numbers: every release works them out once, on
   its own cases. */

import { byClass, classButton, classCell, classLevel, classParams, classTip, classesHeld, useClasses } from './classstats.js';
import { NO_ONSET, SEX } from './codes.js';
import { actions } from './events.js';
import { icon } from './icons.js';
import { labelButton, labelColumn, labelLead, labelParams, labelStrip, labelsPainted, onLabelChange } from './labelstats.js';
import { showProblem } from './overlays.js';
import { addressParts, current, go, pageAt, productPath } from './router.js';
import { listWords, passParam, passes, screenOf, useScreens } from './screens.js';
import { api } from './server.js';
import { S, ages, defaultRoles, learnClasses, scopeFor } from './state.js';
import { esc, fix, num, ruleTag, skeletonRows, sortMark, tip } from './util.js';

const scopeHere = () => current()?.scope;
// a ratio as a person reads it: three figures or so, an empty value left empty
const fig = (v) => (v == null ? '' : Math.abs(v) >= 100 ? num(Math.round(v)) : fix(v, Math.abs(v) >= 10 ? 1 : 2));
const faint = (text, words) => `<span class="oa-faint oa-has-tip" ${tip(words)}>${text}</span>`;
// a median in days with its unit: 1 day, 238 days, 12.5 days
const days = (v) => `${Number.isInteger(v) ? num(v) : fix(v, 1)} ${v === 1 ? 'day' : 'days'}`;
const ror = (r) => (r.ror == null ? '' : `${fig(r.ror)} ${faint(`${fig(r.ror_lower)} to ${fig(r.ror_upper)}`, '95% interval of the ROR')}`);

// a pair's time to onset: the median days, and in grey the drugs it is based on of the pair's
// drugs, whose tip says why the others have none (rule time-to-onset)
const REASONS = Object.keys(NO_ONSET);
function onset(r) {
  if (r.onset_drugs == null) return '';
  const none = REASONS.map((k) => [k, r[`no_onset_${k}`]]).filter(([, n]) => n);
  const all = r.onset_drugs + none.reduce((sum, [, n]) => sum + n, 0);
  const why = none.length ? ` ${num(all - r.onset_drugs)} have none: ${none.map(([k, n]) => `${num(n)} ${NO_ONSET[k][0].toLowerCase()}`).join(', ')}.` : '';
  const words = `${num(r.onset_drugs)} of the pair's ${num(all)} suspect drugs give a time to onset.${why}`;
  return `${r.onset_days == null ? '' : days(r.onset_days)} ${faint(`${num(r.onset_drugs)} of ${num(all)} drugs`, words)}`;
}

// The table's columns after the reaction, in order, each reading fields of the pair /api/statistics
// gives. Further columns join this list. A column may name its class (`cls`, a number's otherwise),
// where it shows (`when`, everywhere otherwise), its tip as the tab's scope gives it, and that it
// does not sort (`still`).
export const statisticsColumns = [
  labelColumn,
  { id: 'cases', head: 'Cases', reads: ['cases'], tip: 'Cases naming both the ingredient, as a suspect, and the reaction', cell: (r) => num(r.cases) },
  { id: 'expected', head: 'Exp. count', reads: ['expected'], tip: 'Expected count: the cases expected if the two were unrelated, worked out within age band, sex and year received', cell: (r) => fig(r.expected) },
  { id: 'ebgm', head: 'EBGM', reads: ['ebgm'], tip: 'How many times more often than expected, small counts pulled towards the usual ratio', cell: (r) => fig(r.ebgm) },
  { id: 'eb05', head: 'EB05', reads: ['eb05'], tip: "EBGM's lower 5% bound: at least this, allowing for chance", cell: (r) => fig(r.eb05) },
  { id: 'class_eb05', head: 'Class EB05', reads: [], tip: classTip, still: true, when: (sc) => !!sc.product && classesHeld(), cell: (r) => fig(r.class_eb05) },
  { id: 'eb95', head: 'EB95', reads: ['eb95'], tip: "EBGM's upper 95% bound", cell: (r) => fig(r.eb95) },
  { id: 'prr', head: 'PRR', reads: ['prr'], tip: "The reaction's share of the ingredient's cases, against its share of every other case", cell: (r) => fig(r.prr) },
  { id: 'chi_square', head: 'Chi²', reads: ['chi_square'], tip: "Pearson's chi-square of the table", cell: (r) => fig(r.chi_square) },
  { id: 'chi_square_yates', head: 'Yates', reads: ['chi_square_yates'], tip: "Chi² Yates: the chi-square with Yates' correction", cell: (r) => fig(r.chi_square_yates) },
  { id: 'ror', head: 'ROR', reads: ['ror', 'ror_lower', 'ror_upper'], tip: 'Reporting odds ratio. In grey, its 95% interval', cell: ror },
  { id: 'rrr', head: 'RRR', reads: ['rrr'], tip: 'Cases over the cases expected over the whole table', cell: (r) => fig(r.rrr) },
  { id: 'ic', head: 'IC', reads: ['ic', 'ic025'], tip: 'Information component, on a doubling scale. In grey, IC025: the lower end of its 95% interval', cell: (r) => `${fix(r.ic)} ${faint(fix(r.ic025), 'IC025')}` },
  { id: 'onset_days', head: 'Onset', reads: ['onset_days', 'onset_drugs'], tip: 'Onset: the median days from the first dose, day 1, to the reaction, over the suspect drugs that give both dates to the day. In grey, how many drugs that is', when: (sc) => !byClass(sc), cell: onset },
];

let about = null; // /api/statistics/about for the release shown
let aboutFor = '';
let painted = null; // the scope the tab is drawn for

// a new list a moment after the last key: the table says it is coming at once
function later(sc) {
  document.getElementById('oa-body')?.setAttribute('aria-busy', 'true');
  clearTimeout(state(sc).wait);
  state(sc).wait = setTimeout(() => reload(sc), 250);
}

function screened(sc, listChanges) {
  if (scopeHere() !== sc || sc.tab !== 'statistics') return;
  if (listChanges) { later(sc); return; }
  paintStatistics(sc);
}

async function aboutRelease() {
  const name = S.release?.release || '';
  if (!about || aboutFor !== name) {
    about = await api('/api/statistics/about');
    aboutFor = name;
  }
  useScreens(about, (listChanges) => painted && screened(painted, listChanges));
  useClasses(about, (sc) => reload(sc));
  return about;
}

// sort null: the table's own order, which /api/statistics gives when asked for none
const state = (sc) => (sc.stat ??= { find: '', sort: null, dir: null, rows: null, matched: 0, key: '' });

function askFor(sc, offset = 0) {
  const st = state(sc);
  const p = new URLSearchParams({ find: st.find.trim(), ...(st.sort && { sort: st.sort, dir: st.dir }), offset: String(offset), pass: passParam() });
  if (sc.product) p.set('ingredient', sc.product);
  labelParams(sc, p);
  classParams(sc, p);
  return `/api/statistics?${p}`;
}

// the tab's data: the release's statistics, then the first page of pairs (or the next one)
export async function loadStatistics(sc, { more = false } = {}) {
  const st = state(sc);
  if (S.me?.statistics === false) { st.closed = true; return; }
  const found = await aboutRelease();
  if (!found.present) return;
  const asked = askFor(sc, more ? st.rows.length : 0);
  const got = await api(asked);
  st.rows = more ? [...st.rows, ...got.rows] : got.rows;
  st.matched = got.matched;
  st.label = got.label;
  st.cls = got.class;
  st.key = asked;
  // the classes named here, so a filter by one says its name
  learnClasses(got.by === 'class' ? got.rows.map((r) => [r.class, r.class_name]) : got.class ? [[got.class.code, got.class.name]] : []);
}

async function reload(sc, more = false) {
  document.getElementById('oa-body')?.setAttribute('data-state', 'loading');
  try { await loadStatistics(sc, { more }); } catch (err) { showProblem(err); return; }
  if (scopeHere() === sc && sc.tab === 'statistics') paintStatistics(sc);
}

onLabelChange((sc) => reload(sc));

const findWords = (sc) => (sc.product ? 'Find a reaction' : byClass(sc) ? 'Find a class or a reaction' : 'Find an ingredient or a reaction');

export function statisticsToolbar(sc) {
  const st = state(sc);
  return `<div class="search-bar oa-stat-find">
      <span class="search-icon">${icon('search')}</span>
      <input class="search-input" id="oa-stat-find" type="search" autocomplete="off" aria-label="Find" placeholder="${findWords(sc)}" value="${esc(st.find)}">
    </div>
    <p class="oa-countline" id="oa-countline">${countLine(sc)}</p>
    ${labelButton(sc)}${classButton(sc)}<button type="button" class="btn oa-screens-btn" data-act="screens" aria-haspopup="menu" aria-label="Thresholds">${icon('filter')}<span class="oa-btn-words">Thresholds</span></button>`;
}

// a combination's statistics are its ingredients' own (rule statistics-cases): each one's tab, its
// address alone, so nothing of this page's choices goes with it
const combined = (sc) => (sc.info?.ingredients?.length ?? 0) > 1;
function eachIngredient(sc) {
  const links = sc.info.ingredients.map((name) => `<a class="oa-link" href="${productPath(name, 'statistics')}">${esc(name)}</a>`);
  return `<p class="oa-empty">Statistics are worked out for each ingredient: ${links.slice(0, -1).join(', ')} and ${links.at(-1)}.</p>`;
}

function countLine(sc) {
  const st = state(sc);
  if (!about?.present || !st.rows) return '<span class="skeleton oa-count-skeleton"></span>';
  if (combined(sc)) return '';
  return `<strong>${num(st.matched)}</strong> ${st.matched === 1 ? 'pair' : 'pairs'}<span class="oa-dot">·</span>${esc(listWords())}`;
}

// the strip's one line under the toolbar: where the method is, and that the filters do not apply
// one sentence, not filter items: on a phone it wraps rather than fading out at the edge
export const statisticsLead = () => `<span class="oa-strip-lead"><a class="oa-link" href="/methods?open=ebgm">How these are worked out</a><span class="oa-dot">·</span><span class="oa-faint">The filters do not change them</span></span>`;

// what the numbers are, in plain words, above the table
function lead(sc) {
  const level = byClass(sc) ? classLevel() : null;
  const fit = level ? { fitted: level.fitted, reason: level.reason } : about.ebgm;
  const unfit = fit.fitted ? '' : ` EBGM could not be fitted on ${level ? 'this level' : 'this release'}, so its columns are empty: ${esc(fit.reason)}.`;
  const byPt = about.reaction_key === 'meddra_pt' ? ` Reactions under today's MedDRA ${esc(about.meddra_version)} terms.` : about.line ? ` ${esc(about.line)}` : '';
  const row = level
    ? `one WHO class, its ${esc(level.name.toLowerCase())} (ATC level ${level.level}), and one reaction, every drug of the class in a case counted once for it`
    : 'one ingredient and one reaction';
  return `<p class="oa-stat-lead">Each row is ${row}, counted once for the whole release, so your filters don't change it. A high number is not a signal on its own.${byPt}${unfit}</p>`;
}

export function statisticsBody(sc) {
  const st = state(sc);
  if (st.closed) return '<p class="oa-empty">Statistics are not open to you here.</p>';
  if (about && !about.present) return `<p class="oa-empty">${esc(about.reason)}</p>`;
  if (!st.rows) return `<div class="oa-table-skeleton">${skeletonRows(4)}</div>`;
  if (combined(sc)) return eachIngredient(sc);
  const columns = statisticsColumns.filter((c) => !c.when || c.when(sc));
  const head = (id, label, words, cls = 'oa-num', still = false) => {
    const mark = st.sort === id ? (st.dir === 'desc' ? 'desc' : 'asc') : 'none';
    // data-col: the column's slot (statistics.css), so sorting or a screen moves nothing
    const inside = still ? `<span class="oa-still-head" ${tip(words)}>${label}</span>` : `<button type="button" class="dashboard-sort oa-sortable" data-act="stat-sort" data-v="${id}" ${tip(words)}>${label}${sortMark(mark)}</button>`;
    return `<th scope="col" data-col="${id}"${cls ? ` class="${cls}"` : ''}>${inside}</th>`;
  };
  const words = (c) => (typeof c.tip === 'function' ? c.tip(sc) : c.tip);
  const classes = byClass(sc);
  const first = (r) => (sc.product ? '' : `<td>${classes ? classCell(r) : esc(r.ingredient)}</td>`);
  // a cell is marked where it shows a number its statistic's screen reads, and the screen holds
  const reads = about.statistics.map((s) => [s.id, screenOf(s.id).when.map((c) => c.column).filter((c) => s.columns.includes(c))]);
  const marked = (col, r) => reads.some(([id, cols]) => col.reads.some((f) => cols.includes(f)) && passes(id, r));
  const rows = st.rows.map((r) => `<tr data-act="stat-row" ${classes ? `data-class="${esc(r.class)}"` : `data-ingredient="${esc(r.ingredient)}"`} data-term="${esc(r.term)}" tabindex="0">
      ${first(r)}<th scope="row">${esc(r.reaction)}</th>
      ${columns.map((c) => `<td class="${c.cls || 'oa-num'}" data-state="${marked(c, r) ? 'pass' : ''}">${c.cell(r)}</td>`).join('')}
    </tr>`).join('');
  const width = columns.length + (sc.product ? 1 : 2);
  const none = st.find.trim() ? `Nothing matches "${esc(st.find.trim())}".` : 'No pair passes this threshold. Choose another in Thresholds.';
  const firstHead = classes ? head('class', 'Class', `WHO's class at this level, with its ATC code`, false) : head('ingredient', 'Ingredient', 'The ingredient, in any product containing it', false);
  return `${lead(sc)}${labelLead(sc, st.label)}<div class="dashboard-frame"><table class="dashboard-table oa-stats oa-freeze">
      <thead><tr>${sc.product ? '' : firstHead}${head('reaction', 'Reaction', about.reaction_key === 'meddra_pt' ? `The reaction's current PT in MedDRA ${about.meddra_version}` : 'The reaction as FDA published it', false)}${columns.map((c) => head(c.id, c.head, words(c), c.cls, c.still)).join('')}</tr></thead>
      <tbody>${rows || `<tr><td colspan="${width}" class="oa-faint">${none}</td></tr>`}</tbody></table></div>
    <div class="oa-stat-foot"><span>${num(st.rows.length)} of ${num(st.matched)} shown</span>${st.rows.length < st.matched ? `<button type="button" class="btn" data-act="stat-more">Show ${num(about.shown)} more</button>` : ''}</div>
    <p class="oa-note">Marked numbers pass their statistic's threshold. Press a row to see its cases, and its ROR by age band and by sex under them.</p>`;
}

export function paintStatistics(sc) {
  painted = sc;
  const body = document.getElementById('oa-body');
  if (!body) return;
  body.removeAttribute('data-state');
  body.removeAttribute('aria-busy');
  body.innerHTML = statisticsBody(sc);
  const line = document.getElementById('oa-countline');
  if (line) line.innerHTML = countLine(sc);
  // the list's kind, in the button's words and what Find looks for
  const kind = document.querySelector('#oa-toolbar [data-act="stat-classes"]');
  if (kind) kind.outerHTML = classButton(sc);
  document.getElementById('oa-stat-find')?.setAttribute('placeholder', findWords(sc));
  const strip = document.getElementById('oa-strip');
  if (strip) strip.innerHTML = labelStrip(sc) + statisticsLead();
  labelsPainted(sc);
}

actions({
  'stat-sort': (el) => {
    const sc = scopeHere(); const st = state(sc); const v = el.dataset.v;
    // highest first (a name A to Z), then lowest first, then the table's own order again
    const first = ['ingredient', 'class', 'reaction'].includes(v) ? 'asc' : 'desc';
    if (st.sort !== v) { st.sort = v; st.dir = first; } else if (st.dir === first) st.dir = first === 'desc' ? 'asc' : 'desc';
    else { st.sort = null; st.dir = null; }
    reload(sc);
  },
  'stat-more': () => reload(scopeHere(), true),
  // a pair's cases: this product's Cases tab, or the ingredient's, filtered to the reaction; a class's,
  // every case's Cases tab filtered to the class, in the roles a page opens with, and the reaction
  'stat-row': (el) => {
    if (el.dataset.class) {
      Object.assign(scopeFor(null).f, { atc: [el.dataset.class], atcOut: [], aroles: defaultRoles(), could: false, pts: [el.dataset.term] });
      go('/all/cases');
      return;
    }
    const path = productPath(scopeHere().product || el.dataset.ingredient, 'cases');
    scopeFor(pageAt(addressParts(path)).product).f.pts = [el.dataset.term];
    go(path);
  },
});

document.addEventListener('input', (e) => {
  if (e.target.id !== 'oa-stat-find') return;
  const sc = scopeHere();
  state(sc).find = e.target.value;
  later(sc);
});

// The ROR by age band and by sex of the pair a product's case list is narrowed to, one reaction,
// for the list to show under its cases: fetched once a pair, none where the statistics name no
// such pair (rule ror-strata).
const strataFor = (sc) => (sc.product && !combined(sc) && sc.f.pts?.length === 1 && S.me?.statistics !== false ? `${sc.product}\n${sc.f.pts[0]}` : '');

export async function loadStrata(sc) {
  const key = strataFor(sc);
  if (key === (sc.strata?.key ?? '')) return;
  if (!key) { sc.strata = null; return; }
  const [ingredient, reaction] = key.split('\n');
  const got = await api(`/api/statistics/strata?${new URLSearchParams({ ingredient, reaction })}`).catch(() => null);
  sc.strata = { key, got };
}

const STRATA_HEAD = { age_band: 'Age band', sex: 'Sex' };
const strataName = (by, v) => esc((by === 'age_band' ? ages()[v] : SEX[v]) ?? v);

export function strataBlock(sc) {
  const got = sc.strata?.key === strataFor(sc) ? sc.strata.got : null;
  if (!got) return '';
  const tables = got.parts.map((p) => `<table class="case-table oa-strata-table"><thead><tr><th>${STRATA_HEAD[p.by] ?? esc(p.by)}</th><th class="oa-num">Cases</th><th class="oa-num" ${tip('Reporting odds ratio within this group alone. In grey, its 95% interval; empty where a cell of its table is 0')}>ROR</th></tr></thead>
      <tbody>${p.strata.map((s) => `<tr><td>${strataName(p.by, s.stratum)}</td><td class="oa-num">${num(s.cases)}</td><td class="oa-num">${ror(s)}</td></tr>`).join('')}</tbody></table>`).join('');
  return `<section class="oa-strata" aria-label="ROR by age band and by sex">
      <h3 class="case-section">ROR by age band and by sex</h3>
      <p class="oa-note">For ${esc(got.ingredient)} and ${esc(got.reaction)}, on the ${num(got.cases)} cases the statistics count for them; the filters do not change it. ${ruleTag('ror-strata', 'fixed rule: ror-strata')}</p>
      <div class="oa-case-cols">${tables}</div></section>`;
}
