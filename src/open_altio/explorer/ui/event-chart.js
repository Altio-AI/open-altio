/* The opened event's chart, at the top of its Overview (event-overview.js): the event's cases by
   quarter over the years, placed by the day FDA received them or, with the event's Dates on the day
   the event began, the earlier quarters light and the window's dark under a Window mark. Its title
   says which thresholds were passed and when their current stretch began. Under the bars one strip
   per threshold, named by its first condition (EB05 ≥ 2): a quarter in the warning color where every
   condition held on every case received by its end, deeper the further past, and grey below it,
   darker the closer it came. Hovering a bar, a strip's name or a quarter gives the numbers behind
   it. The strips are the thresholds event-overview.js hands in: the usual ones, the person's own
   and a host's (ctx.screens). No flags, no score lines and no dragging. */

import { WORDS, conditionWords, meets, opOf } from './screens.js';
import { releaseEnd } from './state.js';
import { MONTHS, esc, fig, num, quarterEnd, quarterStart, tip } from './util.js';

// a statistic's short name, by the column a threshold reads first
const NAME = { ebgm: 'EBGM', eb05: 'EB05', prr: 'PRR', ror: 'ROR', ror_lower: 'ROR lower', ic025: 'IC025' };
const SIGN = { at_least: '≥', above: '>', at_most: '≤', below: '<' };
// one order for every strip, whoever set it, so the rows never reshuffle as one is added
const ORDER = ['ebgm', 'eb05', 'prr', 'ror', 'ror_lower', 'ic025'];
// IC and its bound are on a doubling scale: how close a value came reads 2 to the power of the gap
const DOUBLING = new Set(['ic025']);

export const statOf = (t) => t.when[0]?.column;
export const nameOf = (t) => NAME[statOf(t)] || WORDS[statOf(t)] || statOf(t);
const labelOf = (t) => { const c = t.when[0]; const op = opOf(c); return `${nameOf(t)} ${SIGN[op]} ${c[op]}`; };
const place = (t) => { const i = ORDER.indexOf(statOf(t)); return i < 0 ? ORDER.length : i; };

// A threshold: { id, when (the conditions, as a statistic's preset), label, words, own }. The usual
// one of a statistic is its default preset (/api/statistics/about); a host's screen is
// { name, conditions, words }, its name the strip's and its words the tips', both optional.
export const usualThreshold = (statistic, own = false) => {
  const preset = statistic.presets.find((p) => p.default);
  return preset && { id: statistic.id, when: preset.when, label: '', words: preset.label, own };
};
export const hostThreshold = (screen, i) => ({ id: `host-${i}`, when: screen.conditions, label: screen.name || '', words: screen.words || conditionWords(screen.conditions), own: false, host: true });
export const stripName = (t) => t.label || labelOf(t);
export const sortStrips = (ts) => [...ts].sort((a, b) => place(a) - place(b));

// ---- quarters -------------------------------------------------------------------------------------
const keyOf = (day) => `${day.slice(0, 4)}q${Math.ceil(+day.slice(5, 7) / 3)}`;
const nextKey = (k) => { const y = +k.slice(0, 4), n = +k.slice(-1); return n === 4 ? `${y + 1}q1` : `${y}q${n + 1}`; };
export const quarterName = (k) => `${k.slice(0, 4)} Q${k.slice(-1)}`;
export const plainDay = (iso) => { const [y, m, d] = iso.split('-'); return `${+d} ${MONTHS[+m - 1]} ${y}`; };

// The chart's quarters, oldest first, from the first with a case under the filters to the release's
// newest: each with its cases (`n`, from the timeline's months) and the statistics on every case
// FDA had received by its end (`s`, a row of /api/statistics/quarters by its columns; null before
// the pair's first case or where the release cannot give them).
export function quartersOf(months, series) {
  const n = new Map();
  for (const [day, cases] of months) n.set(keyOf(day), (n.get(keyOf(day)) || 0) + cases);
  const s = new Map();
  for (const row of series?.rows || []) {
    const values = Object.fromEntries(series.columns.map((c, i) => [c, row[i]]));
    s.set(`${Math.floor(values.qnum / 10)}q${values.qnum % 10}`, values);
  }
  const held = [...n].filter(([, c]) => c > 0).map(([k]) => k).sort();
  const last = keyOf(releaseEnd());
  const out = [];
  for (let k = held[0]; k && k <= last; k = nextKey(k)) {
    out.push({ key: k, q: quarterName(k), start: quarterStart(k), end: quarterEnd(k), n: n.get(k) || 0, s: s.get(k) || null });
  }
  return out;
}

// ---- a quarter against a threshold ----------------------------------------------------------------
export const passed = (q, t) => !!q?.s && meets(t.when, q.s);
// one condition: its value over its limit, 0 to 1
function part(v, c) {
  const op = opOf(c), limit = c[op];
  if (v == null || !Number.isFinite(v)) return 0;
  if (op === 'at_most' || op === 'below') return meets([c], { [c.column]: v }) ? 1 : 0;
  const r = DOUBLING.has(c.column) ? 2 ** (v - limit) : limit > 0 ? v / limit : v >= limit ? 1 : 0;
  return Math.max(0, Math.min(1, r));
}
// how close quarter q came, 0 to 1 (1: past it): the lowest of its conditions, so a quarter is only
// as close as its weakest part
export function closeness(q, t) {
  if (!q?.s) return 0;
  if (passed(q, t)) return 1;
  return Math.min(1 - Number.EPSILON, ...t.when.map((c) => part(q.s[c.column], c)));
}
// how far past it a quarter is, 0 to 1: its first value over its limit on a log scale, full at ten
// times (a doubling scale's read as 2 to the power of the gap)
function depthOf(q, t) {
  const c = t.when[0], v = q.s[c.column], limit = c[opOf(c)];
  if (v == null || !Number.isFinite(v)) return 1;
  const r = DOUBLING.has(c.column) || !(limit > 0) ? 2 ** (v - limit) : v / limit;
  return Math.max(0, Math.min(1, Math.log(Math.max(r, 1)) / Math.log(10)));
}
const greyOf = (c) => `${Math.round(6 + 52 * c * c)}%`;
const redOf = (d) => `${Math.round(30 + 70 * d)}%`;
const cases = (n) => `${num(n)} ${n === 1 ? 'case' : 'cases'}`;
// the threshold in words, then quarter q's values: "PRR at least 2, chi-square at least 4, at least
// 3 cases. Passed in 2025 Q3: PRR 2.40, Chi-square, Yates 9.10, 41 cases."
export function ruleWords(t, q) {
  if (!q) return `${t.words}.`;
  if (!q.s) return `${t.words}. Not worked out in ${q.q}: no case of the pair had been received.`;
  const got = t.when.map(({ column }) => (column === 'cases' ? cases(q.s.cases ?? 0) : `${WORDS[column] || column} ${q.s[column] == null ? 'not worked out' : fig(q.s[column])}`));
  return `${t.words}. ${passed(q, t) ? 'Passed' : 'Not passed'} in ${q.q}: ${got.join(', ')}.`;
}

// the quarter a threshold's current stretch began: passed in every quarter from it to the newest;
// null if the newest did not pass (an earlier pass that fell back does not count)
function stretchOf(qs, t) {
  let i = qs.length - 1;
  if (i < 0 || !passed(qs[i], t)) return null;
  while (i > 0 && passed(qs[i - 1], t)) i -= 1;
  return i;
}
const andList = (xs) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`);
// The title states what the strips show: which thresholds passed and when their stretch began
export function claim(qs, ts) {
  if (!qs.length || !ts.length || !qs.some((q) => q.s)) return 'Cases by quarter';
  const names = [...new Set(ts.map(nameOf))];
  const starts = [];
  for (const t of ts) { const i = stretchOf(qs, t); if (i != null && !starts.some(([n]) => n === nameOf(t))) starts.push([nameOf(t), i]); }
  if (!starts.length) return `${andList(names)} ${names.length > 1 ? 'are below their thresholds' : 'is below its threshold'} in ${qs.at(-1).q}`;
  const at = [...new Set(starts.map(([, i]) => i))];
  if (at.length === 1) {
    const who = starts.map(([n]) => n);
    return `${andList(who)} passed ${who.length > 1 ? 'their thresholds' : 'its threshold'} in ${qs[at[0]].q}`;
  }
  starts.sort((a, b) => a[1] - b[1]);
  return `${starts[0][0]} passed its threshold in ${qs[starts[0][1]].q}, ${starts.slice(1).map(([n, i]) => `${n} in ${qs[i].q}`).join(', ')}`;
}
// round steps for the cases' axis: three or four lines
function ticksFor(max) {
  const raw = Math.max(1, max) / 3;
  const p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= raw) || 10 * p;
  const top = Math.max(step, Math.ceil(max / step) * step);
  const out = [];
  for (let v = 0; v <= top + 1e-9; v += step) out.push(Math.round(v));
  return { top, ticks: out };
}

// ---- drawing --------------------------------------------------------------------------------------
const LEGEND = '<span class="oa-ov-legend"><span class="oa-ov-key" data-k="grey"><span class="oa-ov-light">Darker grey, closer to it</span><span class="oa-ov-dark">Lighter grey, closer to it</span></span><span class="oa-ov-key" data-k="past"><span class="oa-ov-light">Darker red, further past it</span><span class="oa-ov-dark">Brighter red, further past it</span></span></span>';
const head = (title, sub) => `<div class="oa-ov-head"><p class="chart-sentence"><span class="chart-lead">${esc(title)}</span> <span class="oa-ov-sub">${esc(sub)}</span></p>${LEGEND}</div>`;
// the names' column as wide as its longest name, so no name is squeezed
const nameWidth = (ts) => Math.max(44, Math.round(Math.max('Statistics'.length, ...ts.map((t) => stripName(t).length)) * 6.6 + 14));
const more = (row) => `<button type="button" class="oa-ov-more" style="grid-row:${row}" data-act="ev-ov-strips" aria-haspopup="menu" ${tip('Add a strip for another statistic, for yourself')}>Statistics</button>`;

// The chart: `qs` its quarters (null while they come), `ts` its strips in order (`rows` of them
// while their words come), `w` the window ({ from, to }, either empty for no bound), `by`
// 'received' or 'event', `undated` the cases with no date to place them by, `why` the reason the
// strips have no values where the release cannot give them, `absent` the words in place of the bars
// where there is nothing to draw
export function chartHtml({ qs, ts, rows: waiting = 0, w, by, undated = 0, why = '', absent = '' }) {
  const sub = `cases by quarter ${by === 'event' ? 'the reaction started' : 'received'}${undated ? `, ${cases(undated)} with no date not shown` : ''}`;
  const rows = ts.length || waiting;
  const frame = (inner, n = 1) => `<div class="oa-ov-plot" style="--cols:${n}; --strips:${rows}; --yw:${nameWidth(ts)}px">${inner}</div>`;
  if (!qs) return `${head('Cases by quarter', sub)}${frame('<span class="skeleton oa-ov-skeleton"></span>')}`;
  if (!qs.length) return `${head('Cases by quarter', sub)}${frame(`<p class="oa-ov-absent">${esc(absent)}</p>`)}`;
  const shown = ts.filter((t) => !t.own);
  const n = qs.length;
  const { top, ticks } = ticksFor(Math.max(0, ...qs.map((q) => q.n)));
  const valueWords = (q) => [...new Set(shown.map(statOf))].map((c) => `${NAME[c] || WORDS[c] || c} ${q.s?.[c] == null ? 'not worked out' : fig(q.s[c])}`).join(', ');
  const from = w.from || '0000', to = w.to || releaseEnd();
  const inWindow = (q) => q.end >= from && q.start <= to;
  const bars = qs.map((q, i) => {
    const said = `${q.q}: ${cases(q.n)} ${by === 'event' ? 'whose reaction started in it' : 'received'}.${shown.length ? ` On every case up to ${plainDay(q.end)}: ${valueWords(q)}.` : ''}`;
    return `<span class="oa-ov-slot" style="grid-column:${i + 2}" role="img" aria-label="${esc(said)}" ${tip(said)}><span class="oa-ov-bar"${inWindow(q) ? ' data-in="window"' : ''} style="--h:${q.n / top}"></span></span>`;
  }).join('');
  const first = qs.findIndex(inWindow), last = qs.findLastIndex(inWindow);
  const mark = first < 0 ? '' : `<span class="oa-ov-wmark" style="grid-column:${first + 2} / ${last + 3}" ${tip(`The window: ${plainDay(w.from || qs[0].start)} to ${plainDay(w.to || releaseEnd())}`)}><span>Window</span></span>`;
  const grid = ticks.map((v) => `<span class="oa-ov-gl" style="--at:${v / top}"><span class="oa-ov-yl">${num(v)}</span></span>`).join('');
  const strips = ts.map((t, k) => {
    const name = `<span class="oa-ov-sname${t.own ? ' oa-ov-own' : ''}" style="grid-row:${k + 3}" ${tip(ruleWords(t, qs.at(-1)))}>${esc(stripName(t))}</span>`;
    if (why) return `${name}<span class="oa-ov-why" style="grid-row:${k + 3}">${k ? '' : esc(why)}</span>`;
    return name + qs.map((q, i) => {
      const past = passed(q, t);
      return `<span class="oa-ov-cell" style="grid-row:${k + 3};grid-column:${i + 2};${past ? `--r:${redOf(depthOf(q, t))}` : `--g:${greyOf(closeness(q, t))}`}"${past ? ' data-past="true"' : ''}${t.own ? ' data-own="true"' : ''} ${tip(ruleWords(t, q))}></span>`;
    }).join('');
  }).join('');
  // a year under its first quarter, as many years apart as keeps them from running into each other
  const years = Math.ceil(n / 4), every = Math.max(1, Math.ceil(years / 6));
  const axis = qs.map((q, i) => (q.q.endsWith('Q1') && (+q.q.slice(0, 4) - +qs[0].q.slice(0, 4)) % every === 0 && i < n - 4 ? `<span class="oa-ov-x" style="grid-row:${rows + 3};grid-column:${i + 2}">${q.q.slice(0, 4)}</span>` : '')).join('');
  return `${head(claim(qs, shown), sub)}${frame(`${mark}<div class="oa-ov-bars">${grid}</div>${bars}${strips}${more(rows + 3)}${axis}`, n)}`;
}
