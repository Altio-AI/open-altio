/* The opened event's Overview pane (registered with the frame as 'overview', order 1, through
   registerEventPane, docs/reference/page-extension.md): on top the chart of the event's cases by
   quarter with its threshold strips (event-chart.js) and the four tiles beside it (event-tiles.js);
   under them the pane's sections, in the order they were registered with overviewSection, each
   drawn into a box of its own.

   Every number is a published answer: the cases by month (/api/timeline, by the date the event's
   Dates count, under its filters, every date), the statistics at every quarter's end
   (/api/statistics/quarters, which no filter changes), the cases in the window and before it, all,
   serious and fatal (/api/events/group), and, only where a host asks for a share's alarm, the chance
   test of the serious and fatal shares (/api/breakdowns). The strips are each statistic's usual
   threshold (its default preset, /api/statistics/about): EB05's and PRR's at first, others added from
   Statistics under the strips and kept as the person's view choice; and any screen a host passes
   (ctx.screens), which takes the place of the usual one of its statistic. */

import { chartHtml, hostThreshold, nameOf, quartersOf, sortStrips, statOf, usualThreshold } from './event-chart.js';
import { tilesHtml } from './event-tiles.js';
import { registerEventPane } from './event.js';
import { actions } from './events.js';
import { choice, closedByThisClick, openedBy, place, popMenu, showProblem } from './overlays.js';
import { api } from './server.js';
import { keepView, viewChoice } from './state.js';
import { esc, tip } from './util.js';

// ---- the sections under the chart ---------------------------------------------------------------
// overviewSection(name, { order, draw }): a part of the Overview under the chart and its tiles, such
// as the breakdowns. draw(box, ctx) is called once as the pane is drawn, with a box of its own, and
// may give back { update(ctx), close() }, as a pane does; registered again by the same name, it
// takes that place.
const SECTIONS = new Map();
export function overviewSection(name, { order = 9, draw }) { SECTIONS.set(name, { order, draw }); }
const sections = () => [...SECTIONS].sort(([, a], [, b]) => a.order - b.order);

// ---- the event's questions ------------------------------------------------------------------------
const dates = (ctx) => (ctx.dateField === 'event' ? ['event_from', 'event_to'] : ['received_from', 'received_to']);
const windowOf = (ctx) => { const [f, t] = dates(ctx); return { from: ctx.window?.[f] || '', to: ctx.window?.[t] || '' }; };
const hasBefore = (ctx) => !!(ctx.before?.before_from || ctx.before?.before_to);
const reactions = (ctx, name) => ctx.reaction.map((r) => `${name}=${encodeURIComponent(r)}`).join('&');
// the event's question with `extra` set and the empty values left out
function asked(ctx, extra = {}) {
  const p = new URLSearchParams(ctx.query());
  for (const [k, v] of Object.entries(extra)) p.set(k, v);
  for (const [k, v] of [...p]) if (v === '') p.delete(k);
  return p.toString();
}
// every date: the window's days taken off
const everyDate = (ctx) => asked(ctx, { received_from: '', received_to: '', event_from: '', event_to: '' });
const thresholds = (ctx) => (ctx.screens || []).filter((s) => s.conditions?.length).map(hostThreshold);
const shareScreens = (ctx) => (ctx.screens || []).filter((s) => s.share && s.points != null);

// ---- the strips -----------------------------------------------------------------------------------
// The person's pick: the statistics, by the column their usual threshold reads first, whose usual
// threshold shows as a strip; the tiles' two at first. Kept as a view choice.
const PICKED = 'event.strips';
const picked = () => viewChoice(PICKED, ['eb05', 'prr']);
// a host's strips, then the usual threshold of each picked statistic no host's reads; beside a
// host's, the person's own are drawn lighter
function stripsOf(ctx, about) {
  const host = thresholds(ctx), own = host.length > 0;
  const usual = (about?.statistics || []).map((s) => usualThreshold(s, own)).filter((t) => t && picked().includes(statOf(t)));
  return sortStrips([...host, ...usual.filter((u) => !host.some((h) => statOf(h) === statOf(u)))]);
}
// as many before the usual thresholds' words come, so the chart keeps its height
const stripCount = (ctx) => { const host = thresholds(ctx); return host.length + picked().filter((c) => !host.some((h) => statOf(h) === c)).length; };

// ---- loading --------------------------------------------------------------------------------------
async function countsOf(ctx) {
  if (ctx.none) return { cases: 0, serious: 0, death: 0, before: null, duplicates: 0, rose: null };
  const [f, t] = dates(ctx);
  const group = (q) => api(`/api/events/group?${q}&${reactions(ctx, 'reaction')}`);
  const counted = new URLSearchParams(ctx.query()).get('dedup') === 'all';
  const before = hasBefore(ctx) ? { [f]: ctx.before.before_from, [t]: ctx.before.before_to } : null;
  // the breakdowns place a case by the day FDA received it, so the chance test reads that date only
  const tested = shareScreens(ctx).length > 0 && !!before && ctx.dateField !== 'event';
  const [now, then, all, lines] = await Promise.all([
    group(asked(ctx)),
    before ? group(asked(ctx, before)) : null,
    counted ? null : group(asked(ctx, { dedup: 'all' })),
    tested ? api(`/api/breakdowns?${asked(ctx, ctx.before)}&${reactions(ctx, 'reaction')}`) : null,
  ]);
  const values = lines?.lines?.find((l) => l.field === 'seriousness')?.values || [];
  const rose = (v) => values.find((x) => x.value === v)?.rose ?? null;
  return {
    cases: now.cases, serious: now.serious, death: now.death,
    before: then && { cases: then.cases, serious: then.serious, death: then.death },
    duplicates: all ? all.cases - now.cases : null,
    rose: lines ? { serious: rose('serious'), death: rose('DE') } : null,
  };
}

// each part asked again only when what it reads changed, and painted as its answer comes; where the
// release cannot give the statistics, its reason stands in for them
function load(o) {
  const ctx = o.ctx;
  const ask = (part, key, how) => {
    if (o.keys[part] === key) return;
    o.keys[part] = key;
    o.waiting.add(part);
    const seq = (o.seq[part] = (o.seq[part] || 0) + 1);
    const live = () => o.seq[part] === seq;
    how().then((got) => { if (live()) o[part] = got; }, (err) => {
      if (!live()) return;
      if (part === 'series') o.series = { why: err.message || String(err) }; else showProblem(err);
    }).finally(() => { if (live()) { o.waiting.delete(part); paint(o); } });
  };
  ask('about', 'about', () => api('/api/statistics/about'));
  ask('series', `${ctx.drug}|${ctx.reaction.join('|')}`, () => api(`/api/statistics/quarters?product=${encodeURIComponent(ctx.drug)}&${reactions(ctx, 'reaction')}`));
  ask('months', `${everyDate(ctx)}|${ctx.dateField}|${ctx.none}`, () => (ctx.none ? Promise.resolve({ rows: [], undated: 0 })
    : api(`/api/timeline?grain=month&by=${ctx.dateField === 'event' ? 'event' : 'received'}&${everyDate(ctx)}&${reactions(ctx, 'pt')}`)));
  ask('counts', `${asked(ctx)}|${JSON.stringify(ctx.before)}|${ctx.dateField}|${ctx.none}|${JSON.stringify(shareScreens(ctx))}`, () => countsOf(ctx));
}

// ---- painting -------------------------------------------------------------------------------------
const drawn = new Set(); // every Overview drawn and not closed
function paint(o) {
  const ctx = o.ctx;
  const why = o.about && !o.about.present ? o.about.reason : o.series?.why || '';
  const series = o.series?.why ? null : o.series?.events?.[0]?.series && { columns: o.series.columns, rows: o.series.events[0].series };
  const qs = o.about && o.months && (o.series || why) ? quartersOf(o.months.rows, series) : null;
  const shown = {
    qs, ts: o.about ? stripsOf(ctx, o.about) : [], rows: stripCount(ctx), w: windowOf(ctx), by: ctx.dateField,
    undated: o.months?.undated || 0, why, counts: o.counts, shares: shareScreens(ctx), absent: 'No case of this event under these filters.',
  };
  const chart = o.pane.querySelector('.oa-ov-chart'), tiles = o.pane.querySelector('.oa-ov-tiles');
  chart.innerHTML = chartHtml(shown);
  tiles.innerHTML = tilesHtml(shown);
  // a part asked again keeps what it showed, quieter, until its answer comes
  const quiet = (el, on) => (on ? el.setAttribute('data-state', 'loading') : el.removeAttribute('data-state'));
  quiet(chart, !!qs && (o.waiting.has('months') || o.waiting.has('series')));
  quiet(tiles, !!o.counts && o.waiting.has('counts'));
}

function draw(pane, ctx) {
  const o = { pane, ctx, keys: {}, seq: {}, waiting: new Set(), about: null, series: null, months: null, counts: null };
  pane.innerHTML = `<div class="oa-ov">
    <div class="oa-ov-top"><section class="oa-ov-chart"></section><div class="oa-ov-tiles"></div></div>
    <div class="oa-ov-sections">${sections().map(([name]) => `<div class="oa-ov-section" data-section="${esc(name)}"></div>`).join('')}</div>
    <div class="oa-ov-after">${ctx.slot('event-after-evidence')}</div></div>`;
  pane.querySelector('.oa-ov').overview = o;
  drawn.add(o);
  load(o);
  paint(o);
  const parts = sections().map(([name, s]) => s.draw(pane.querySelector(`.oa-ov-section[data-section="${CSS.escape(name)}"]`), ctx) || {});
  return {
    update(next) { o.ctx = next; load(o); paint(o); parts.forEach((p) => p.update?.(next)); },
    close() { drawn.delete(o); parts.forEach((p) => p.close?.()); },
  };
}

export const overviewPane = { label: 'Overview', order: 1, draw };

// ---- Statistics, under the strips: a strip for another statistic, for the person ---------------
let menuOf = null; // the Overview whose Statistics menu is open
function menuHtml(o) {
  const host = thresholds(o.ctx);
  const offered = sortStrips(o.about.statistics.map((s) => usualThreshold(s)).filter(Boolean));
  const name = (t) => nameOf(t).replace(' lower', '');
  const rows = offered.map((t) => (host.some((h) => statOf(h) === statOf(t))
    ? choice(true, name(t), null, `aria-disabled="true" data-locked="true" ${tip('Always shown here')}`)
    : choice(picked().includes(statOf(t)), name(t), null, `data-act="ev-ov-strip" data-v="${esc(statOf(t))}" ${tip(t.words)}`))).join('');
  const foot = host.length ? 'Yours are drawn lighter, each against its statistic’s usual threshold.' : 'Each against its statistic’s usual threshold, as the methods page gives it.';
  return `<p class="menu-heading">Show as strips</p><div class="oa-choices">${rows}</div><p class="menu-footnote">${foot}</p>`;
}
actions({
  'ev-ov-strips': (el) => {
    if (closedByThisClick()) return;
    const o = el.closest('.oa-ov')?.overview;
    if (!o?.about?.present) return;
    menuOf = o;
    const menu = popMenu(el, menuHtml(o), 'oa-ov-strips-menu');
    place(menu, el, { fit: true });
    openedBy(el);
  },
  'ev-ov-strip': (el) => {
    const v = el.dataset.v, on = picked();
    keepView(PICKED, on.includes(v) ? on.filter((x) => x !== v) : [...on, v]);
    if (menuOf) el.closest('.menu').innerHTML = menuHtml(menuOf);
    drawn.forEach(paint);
  },
});

registerEventPane('overview', overviewPane);
