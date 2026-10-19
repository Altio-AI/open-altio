/* Overview: cases over time at the grain a person picks, and a chart of rows for each of the
   reactions, drugs, drug classes, outcomes, ages, sexes, reporters and countries. Clicking a bar
   filters by it. */

import { NONE, OUTCOME, REPORTER, SEX, labelOf } from './codes.js';
import { countryName } from './countries.js';
import { actions } from './events.js';
import { query, rolesWords } from './filters.js';
import { stepTo, whoLine } from './classes.js';
import { showProblem } from './overlays.js';
import { bodySkeleton, refresh, scopeNow } from './scope.js';
import { api } from './server.js';
import { ages, className, drugWords, fieldNotes, filesStart, learnClasses, listLength, meddraOn, productLabel, ptCounted, ptLine, ptVersion, releaseEnd, releaseEndYear } from './state.js';
import { pressTerm, termOn } from './terms.js';
import { MONTHS, companyName, day, esc, num, tip } from './util.js';

// How many of a chart's cases give its field, in words (rule not-given).
// FDA's own fields say "given", fields Open Altio works out say "found", and outcomes name a serious one,
// since FDA writes outcome rows only for serious outcomes.
const COVERAGE = {
  reaction: ['Reactions', 'given'],
  dprods: ['Ingredient', 'found'],
  atc: ['WHO class', 'found'],
  soc: ['System organ class', 'found'],
  outcome: ['A serious outcome', 'given'],
};
function coverage(key, fallback, [given, cases]) {
  const [word, verb] = COVERAGE[key] || [fallback, 'given'];
  const p = (100 * given) / cases;
  const share = given === cases ? 'all' : !given ? 'none' : p < 1 ? 'under 1%' : p > 99 ? 'over 99%' : `${Math.round(p)}%`;
  return `${word} ${verb} for ${share} of these cases.`;
}

// A field's cases by value, Not given greyed and set apart at the bottom, with how many give the field
// under the title and any note on the field's FDA files under the chart. A row of `more` is no value to
// filter by, such as the cases whose drug could be several classes.
function rowsChart(sc, { key, lead, rest, items, label, chosen, limit, field, word, more = [], note = '' }) {
  const isNone = (k) => k == null || k === NONE;
  const none = items.find(([k]) => isNone(k));
  const shown = items.filter(([k]) => !isNone(k)).slice(0, limit);
  const max = Math.max(1, ...shown.map((i) => i[1]), none ? none[1] : 0, ...more.map((i) => i[1]));
  const row = ([k, n]) => `<li data-state="${chosen.includes(k ?? NONE) ? 'chosen' : ''}">
      <span class="chart-row-label" title="${esc(label(k))}">${esc(label(k))}</span>
      <button type="button" class="chart-track" style="--share:${n / max}" data-act="chart" data-key="${key}" data-v="${esc(k ?? NONE)}" ${tip(`${label(k)}: ${num(n)} cases. Press to filter.`)} aria-label="${esc(label(k))}: ${num(n)} cases. Press to filter.">
        <span class="chart-fill"></span></button>
      <span class="chart-count">${num(n)}</span></li>`;
  const plain = more.map(([words, n, hint]) => `<li data-state="plain"><span class="chart-row-label" ${tip(hint)}>${esc(words)}</span>
      <span class="chart-track" style="--share:${n / max}"><span class="chart-fill"></span></span><span class="chart-count">${num(n)}</span></li>`).join('');
  const given = sc.summary.given?.[key];
  const notes = fieldNotes(field, sc.f);
  return `<section class="oa-chart">
    <p class="chart-sentence"><span class="chart-lead">${lead}</span>${rest ? ` ${rest}` : ''}</p>
    ${given?.[1] ? `<p class="oa-chart-note oa-chart-given">${coverage(key, word || lead, given)}</p>` : ''}
    <ul class="chart-rows">${shown.map(row).join('') || (none || plain ? '' : '<li class="oa-none">None</li>')}${plain}</ul>
    ${none ? `<ul class="chart-rows oa-chart-none">${row(none)}</ul>` : ''}
    ${notes.length ? `<p class="oa-chart-note">${esc(notes.join(' '))}</p>` : ''}${note}
  </section>`;
}

// Cases by drug class, one level under the class chosen (the main groups when none is): each drug in
// the counted roles in its one class, and the drugs that could be several classes in one bar of their
// own, so no drug counts twice.
function classChart(sc) {
  const b = sc.summary.classes;
  if (!b) return '';
  learnClasses(b.rows.map(([code, name]) => [code, name]));
  const more = b.several ? [['Could be several', b.several, "Cases whose drug could be in more than one of these classes: the report does not say which. Each case counts once here."]] : [];
  return rowsChart(sc, {
    key: 'atc',
    lead: b.parent ? `Classes under ${b.parent}` : 'Drug classes',
    rest: b.parent ? esc(b.parent_name || '') : `reported most as ${rolesWords(b.roles)}`,
    items: b.rows.map(([k, , n]) => [k, n]),
    label: (k) => `${k} ${className(k)}`,
    chosen: sc.f.atc,
    more,
    note: `<p class="oa-chart-note">${whoLine()}</p>`,
  });
}

// Cases by MedDRA system organ class, for a viewer who may see MedDRA: a case with reactions in two
// classes counts in both. Titled and cut like the other tiles.
function socChart(sc) {
  const rows = sc.summary.soc;
  if (!rows || !meddraOn()) return '';
  return rowsChart(sc, {
    key: 'soc',
    lead: 'System organ classes',
    rest: `reported most${ptVersion() ? `, in MedDRA ${esc(ptVersion())}` : ''}`,
    items: rows,
    label: (k) => k,
    chosen: sc.f.soc,
    limit: listLength('socs_charted'),
  });
}

// Cases over time, at the grain a person picks; a day is the smallest unit FDA records.
// Clicking a bar keeps only that period's cases and steps down a grain: a year shows its months, a month its days.
const GRAINS = [['year', 'Year'], ['month', 'Month'], ['week', 'Week'], ['day', 'Day']];
const NEXT_GRAIN = { year: 'month', month: 'day', week: 'day', day: 'day' };
const isoDay = (t) => new Date(t).toISOString().slice(0, 10);
const atUtc = (d) => Date.parse(`${d}T00:00:00Z`);
function periodStart(d, grain) {
  const [y, m] = d.split('-');
  if (grain === 'year') return `${y}-01-01`;
  if (grain === 'month') return `${y}-${m}-01`;
  if (grain === 'week') { const t = new Date(atUtc(d)); t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7)); return isoDay(t); }
  return d;
}
function periodEnd(start, grain) {
  const t = new Date(atUtc(start));
  if (grain === 'year') t.setUTCFullYear(t.getUTCFullYear() + 1);
  else if (grain === 'month') t.setUTCMonth(t.getUTCMonth() + 1);
  else if (grain === 'week') t.setUTCDate(t.getUTCDate() + 7);
  else t.setUTCDate(t.getUTCDate() + 1);
  t.setUTCDate(t.getUTCDate() - 1);
  return isoDay(t);
}
const nextPeriod = (start, grain) => isoDay(atUtc(periodEnd(start, grain)) + 864e5);
function periodWords(start, grain) {
  const [y, m] = start.split('-');
  if (grain === 'year') return y;
  if (grain === 'month') return `${MONTHS[+m - 1]} ${y}`;
  if (grain === 'week') return `the week of ${day(start)}`;
  return day(start);
}
function periodLabel(start, grain, n) {
  const [y, m, d] = start.split('-').map(Number);
  const monthOrYear = () => (m === 1 ? String(y) : MONTHS[m - 1]);
  if (grain === 'year') return n > 12 && (releaseEndYear() - y) % 2 ? '' : String(y);
  if (grain === 'month') return n <= 18 ? (m === 1 ? `Jan ${y}` : MONTHS[m - 1]) : (m === 1 ? String(y) : '');
  // weeks and days name each month where it starts (each quarter's for long runs of weeks), and January by its year
  if (grain === 'week') return n <= 26 ? `${d} ${MONTHS[m - 1]}` : d <= 7 && (n <= 120 || m % 3 === 1) ? monthOrYear() : '';
  if (n <= 7) return `${d} ${MONTHS[m - 1]}`;
  return n <= 45 ? ((d - 1) % 7 === 0 ? `${d} ${MONTHS[m - 1]}` : '') : d === 1 ? monthOrYear() : '';
}

function timeChart(sc) {
  const t = sc.timeline;
  const grain = sc.grain || 'year';
  const tabs = `<div class="tabs-line oa-grains" role="tablist" aria-label="Count by">${GRAINS.map(([v, w]) => `<button type="button" class="tabs-line-tab" role="tab" aria-selected="${grain === v}" data-act="grain" data-v="${v}">${w}</button>`).join('')}</div>`;
  const head = `<div class="oa-chart-head"><p class="chart-sentence"><span class="chart-lead">Cases</span> by the ${grain} FDA first received them</p>${tabs}</div>`;
  if (!t || t.grain !== grain) return `<section class="oa-chart oa-chart-wide" id="oa-timechart">${head}<div class="oa-cols-scroll"><span class="skeleton oa-chart-skeleton"></span></div></section>`;
  // a period counts as before FDA's files only when it ends before their first day (the week of
  // 29-Dec-2003 holds 1 to 4 January 2004)
  const start = filesStart();
  const end = releaseEnd();
  const early = t.rows.filter(([k]) => periodEnd(k, grain) < start);
  const rowsShown = t.rows.filter(([k]) => periodEnd(k, grain) >= start || (sc.f.from && sc.f.from < start));
  const by = Object.fromEntries(rowsShown);
  const f = sc.f;
  // the axis runs from the first period to the last, with the chosen days' edges and the release's years when nothing narrows it
  const starts = rowsShown.map(([k]) => k);
  let lo = starts[0] || periodStart(f.from || start, grain);
  let hi = starts[starts.length - 1] || periodStart(f.to && f.to < end ? f.to : end, grain);
  if (f.from && periodStart(f.from, grain) < lo) lo = periodStart(f.from, grain);
  if (f.to && periodStart(f.to < end ? f.to : end, grain) > hi) hi = periodStart(f.to < end ? f.to : end, grain);
  if (!f.from && !f.to && !sc.product && grain === 'year') { lo = periodStart(start, 'year'); hi = periodStart(end, 'year'); }
  const periods = [];
  for (let k = lo; k <= hi && periods.length < 12000; k = nextPeriod(k, grain)) periods.push(k);
  const max = Math.max(1, ...rowsShown.map(([, n]) => n));
  // a bar is lit when the chosen days take it in, and do not take in the whole chart
  const whole = f.from && f.to && f.from <= lo && f.to >= periodEnd(hi, grain);
  const lit = (a, b) => (f.from || f.to) && !whole && (!f.from || f.from <= a) && (!f.to || f.to >= b);
  const n = periods.length;
  const cols = periods.map((k) => {
    const v = by[k] || 0;
    const end = periodEnd(k, grain);
    return `<div class="oa-col-slot">
      ${v ? `<button type="button" class="oa-col-bar${lit(k, end) ? ' oa-bar-chosen' : ''}" style="--share:${v / max}" data-act="period" data-from="${k}" data-to="${end}" data-grain="${grain}" ${tip(`${periodWords(k, grain)}: ${num(v)} cases`)} aria-label="${periodWords(k, grain)}: ${num(v)} cases. Press to keep only these."></button>` : '<span class="oa-col-empty"></span>'}
      <span class="oa-col-label">${periodLabel(k, grain, n)}</span></div>`;
  });
  const before = rowsShown.length === t.rows.length ? 0 : early.reduce((a, [, n]) => a + n, 0);
  const notes = [
    before ? `${num(before)} ${before === 1 ? 'case' : 'cases'} FDA first received before ${start.slice(0, 4)}, in reports it published later, ${before === 1 ? 'is' : 'are'} not drawn; FDA's files start in ${start.slice(0, 4)}.` : '',
    t.undated ? `${num(t.undated)} ${t.undated === 1 ? 'case has' : 'cases have'} no full date from FDA, only a month or a year, so ${t.undated === 1 ? 'it is' : 'they are'} not in this chart.` : '',
  ].filter(Boolean);
  const note = notes.length ? `<p class="oa-chart-note">${notes.join(' ')}</p>` : '';
  return `<section class="oa-chart oa-chart-wide" id="oa-timechart">${head}
    <div class="oa-cols-scroll"><div class="oa-cols" data-grain="${grain}" style="--cols:${n}; min-width: calc(${n} * ${grain === 'year' ? 0 : 7}px)">${cols.join('')}</div></div>${note}
  </section>`;
}
export const scrollChartsToEnd = () => requestAnimationFrame(() => document.querySelectorAll('.oa-cols-scroll').forEach((e) => { e.scrollLeft = e.scrollWidth; }));

export function overview(sc) {
  const s = sc.summary;
  if (!s) return bodySkeleton(sc);
  if (!s.cases) return '<p class="oa-empty">No cases match these filters.</p>';
  const ordered = (list, order) => (order ? [...list].sort((a, b) => order.indexOf(a[0] ?? NONE) - order.indexOf(b[0] ?? NONE)) : list);
  return `<div class="oa-charts">
    ${timeChart(sc)}
    ${rowsChart(sc, { key: 'reaction', lead: 'Reactions', rest: ['reported most', ptCounted()].filter(Boolean).join(', '), items: s.reactions, label: (k) => k, chosen: s.reactions.map(([t]) => t).filter((t) => termOn(sc.f, t)), note: ptLine() ? `<p class="oa-chart-note oa-pt-line">${esc(ptLine())}</p>` : '' })}
    ${sc.product ? '' : rowsChart(sc, { key: 'dprods', lead: 'Ingredients', rest: `reported most as ${rolesWords(drugWords().default_roles)}`, items: s.drugs || [], label: productLabel, chosen: sc.f.dprods })}
    ${sc.product ? '' : classChart(sc)}
    ${socChart(sc)}
    ${rowsChart(sc, { key: 'outcome', lead: 'Outcomes', rest: 'a case can have several', items: ordered(s.outcome, Object.keys(OUTCOME)), label: (k) => labelOf(OUTCOME, k), chosen: sc.f.outcome })}
    ${rowsChart(sc, { key: 'age', lead: 'Age', rest: 'at the event', items: ordered(s.age, Object.keys(ages())), label: (k) => labelOf(ages(), k), chosen: sc.f.age, field: 'age' })}
    ${rowsChart(sc, { key: 'sex', lead: 'Sex', rest: '', items: s.sex, label: (k) => labelOf(SEX, k), chosen: sc.f.sex, field: 'sex' })}
    ${rowsChart(sc, { key: 'reporter', lead: 'Who reported', rest: '', items: s.reporter, label: (k) => labelOf(REPORTER, k), chosen: sc.f.reporter, field: 'occp_cod', word: 'Reporter' })}
    ${rowsChart(sc, { key: 'country', lead: 'Countries', rest: 'where the event happened', items: s.country, limit: listLength('countries_charted'), label: countryName, chosen: sc.f.country, word: 'Country' })}
    ${rowsChart(sc, { key: 'sender', lead: 'Companies', rest: 'that sent the reports', items: s.sender, label: companyName, chosen: [sc.f.sender], word: 'Company' })}
  </div>`;
}

actions({
  chart: (el) => {
    const sc = scopeNow();
    const { key, v } = el.dataset;
    if (key === 'year') { const same = sc.f.from === `${v}-01-01` && sc.f.to === `${v}-12-31`; sc.f.from = same ? '' : `${v}-01-01`; sc.f.to = same ? '' : `${v}-12-31`; }
    else if (key === 'reaction') pressTerm(sc.f, v);
    else if (key === 'sender') sc.f.sender = sc.f.sender === v ? '' : v;
    else if (key === 'dprods') sc.f.dprods = sc.f.dprods.includes(v) ? sc.f.dprods.filter((x) => x !== v) : [...sc.f.dprods, v];
    else if (key === 'atc') stepTo(sc.f, v);
    else { const list = sc.f[key]; sc.f[key] = list.includes(v) ? list.filter((x) => x !== v) : [...list, v]; }
    refresh(sc);
  },
  grain: async (el) => {
    const sc = scopeNow();
    sc.grain = el.dataset.v;
    const box = document.getElementById('oa-timechart');
    if (box) box.outerHTML = timeChart(sc);
    try { sc.timeline = await api(`/api/timeline?grain=${sc.grain}&${query(sc)}`); } catch (err) { showProblem(err); return; }
    const again = document.getElementById('oa-timechart');
    if (again && sc.timeline.grain === sc.grain) { again.outerHTML = timeChart(sc); scrollChartsToEnd(); }
  },
  period: (el) => {
    const sc = scopeNow();
    const { from, to, grain } = el.dataset;
    if (sc.f.from === from && sc.f.to === to) { sc.f.from = ''; sc.f.to = ''; }
    else { sc.f.from = from; sc.f.to = to; sc.grain = NEXT_GRAIN[grain]; }
    refresh(sc);
  },
});
