/* The opened event's four tiles, beside its chart (event-overview.js), each the window against
   before it: Cases in the window, with the probable duplicates it left out; EB05 and PRR during the
   window, the score on every case received up to the window's start against every case up to its
   end, the change beside it and the before and now mark under it; and the serious and fatal shares
   of the window's cases against those before it. A number is in the warning color only where a
   host's screen (ctx.screens) says so: EB05 or PRR past a host's threshold of that statistic at the
   window's end, a share that rose by at least a host's points and more than chance. */

import { passed, plainDay, ruleWords, statOf } from './event-chart.js';
import { opOf } from './screens.js';
import { releaseEnd } from './state.js';
import { esc, fig, num, tip } from './util.js';

const NAME = { eb05: 'EB05', prr: 'PRR' };
const arrow = (d) => (d >= 0 ? '▲' : '▼');
const pct = (v) => (v == null ? 'Not compared' : v > 0 && v < 0.01 ? 'under 1%' : `${Math.round(100 * v)}%`);
const skeleton = (k, under = '<span class="skeleton oa-ov-msk"></span>') => `<div class="oa-ov-tile">${k}<p class="oa-ov-v"><span class="skeleton oa-ov-vsk"></span></p>${under}</div>`;

// the before and now mark: a hollow dot before, a filled dot now, in the warning color when past a
// host's rule, the before value under the hollow dot
function markSvg(before, now, top, hot, w, label, centered = false) {
  const X = (v) => 5 + ((w - 10) * Math.min(Math.max(v, 0), top)) / top;
  const ink = hot ? 'var(--warn)' : 'var(--ink)';
  const h = label ? 28 : 14;
  const bx = before == null ? null : X(before);
  // a narrow mark (two share a tile) sets its words in its middle, where they cannot run past its ends
  // (with no hollow dot, the words stand at the filled one, on the side that has the room)
  const at = bx ?? X(now);
  const tx = centered ? w / 2 : at < w / 2 ? at - 4 : at + 4;
  const anchor = centered ? 'middle' : at < w / 2 ? 'start' : 'end';
  const text = !label ? '' : `<text x="${tx}" y="25" text-anchor="${anchor}" fill="var(--ink-soft)" stroke="none" class="oa-ov-mtext">${esc(label)}</text>`;
  return `<svg class="oa-ov-mark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
    <line x1="5" x2="${w - 5}" y1="7" y2="7" stroke="var(--line)" stroke-width="2" stroke-linecap="round"/>
    ${bx == null ? '' : `<line x1="${bx}" x2="${X(now)}" y1="7" y2="7" stroke="${ink}" stroke-width="2"/><circle cx="${bx}" cy="7" r="3.5" fill="var(--panel)" stroke="var(--ink-faint)" stroke-width="1.5"/>`}
    <circle cx="${X(now)}" cy="7" r="4" fill="${ink}" stroke="none"/>${text}</svg>`;
}

// the scores at the window's start and end: on every case up to the quarter that ends before the
// window, and up to the last quarter that ends in it (the newest, for a window to the release's end:
// the event's own number; none for a window that ends before the drug's first quarter ends)
function scoresAt(qs, w) {
  const from = w.from || '0000', to = w.to || releaseEnd();
  const held = qs.filter((q) => q.s);
  return { start: held.findLast((q) => q.end < from) || null, end: held.findLast((q) => q.end <= to) || (to >= releaseEnd() ? held.at(-1) : null) || null };
}

// EB05 or PRR during the window: `qs` the chart's quarters (null while they come), `ts` the strips,
// a host's among them; `why` the reason where the release cannot give the statistics
function scoreTile({ qs, ts, w, why }, stat) {
  const name = NAME[stat], k = `<p class="oa-ov-k">${name} during the window</p>`;
  if (why) return `<div class="oa-ov-tile" ${tip(why)}>${k}<p class="oa-ov-v oa-ov-none">Not worked out</p><p class="oa-ov-s">${esc(why)}</p></div>`;
  if (!qs) return skeleton(k);
  const { start, end } = scoresAt(qs, w);
  const now = end?.s[stat], before = start?.s[stat] ?? null;
  if (now == null) return `<div class="oa-ov-tile">${k}<p class="oa-ov-v oa-ov-none">Not worked out</p><p class="oa-ov-s">Too few cases</p></div>`;
  const host = ts.find((t) => t.host && statOf(t) === stat);
  const hot = !!host && passed(end, host);
  const top = Math.max(now, before || 0, host ? host.when[0][opOf(host.when[0])] : 0) * 1.15;
  // a score the window left where it was (no new case moved it) says so, never "▲0.00"
  const still = before != null && Number(fig(Math.abs(now - before))) === 0;
  const change = before == null ? '' : still ? '<span class="oa-ov-ch oa-ov-still">no change</span>' : `<span class="oa-ov-ch"${hot ? ' data-hot="true"' : ''}>${arrow(now - before)}${fig(Math.abs(now - before))}</span>`;
  const said = `${name} on every case up to ${plainDay(end.end)}: ${fig(now)}${before == null ? '' : `; up to the window's start, ${plainDay(start.end)}: ${fig(before)}`}.${host ? ` ${ruleWords(host)}` : ''}`;
  return `<div class="oa-ov-tile" ${tip(said)}>${k}<p class="oa-ov-v"><span${hot ? ' data-hot="true"' : ''}>${fig(now)}</span> ${change}</p>
    ${markSvg(before, now, top, hot, 150, before == null ? 'none at its start' : `${fig(before)} at its start`)}</div>`;
}

// `counts`: { cases, serious, death, before: { cases, serious, death } or null, duplicates (null
// where they are counted), rose: { serious, death } from the chance test where a host asks }
function casesTile({ counts: c, by }) {
  const k = '<p class="oa-ov-k">Cases in the window</p>';
  if (!c) return skeleton(k, '<p class="oa-ov-s"><span class="skeleton oa-ov-ssk"></span></p>');
  const dups = c.duplicates == null ? 'Probable duplicates counted' : `${num(c.duplicates)} ${c.duplicates === 1 ? 'duplicate' : 'duplicates'} left out`;
  const under = c.cases || c.duplicates ? dups : by === 'event' ? 'None started in the window' : 'None received in the window';
  return `<div class="oa-ov-tile">${k}<p class="oa-ov-v">${num(c.cases)}</p><p class="oa-ov-s">${under}</p></div>`;
}

function seriousTile({ counts: c, shares, by }) {
  const k = '<p class="oa-ov-k">Serious · fatal</p>';
  if (!c) return skeleton(k);
  if (!c.cases) return `<div class="oa-ov-tile">${k}<p class="oa-ov-v oa-ov-none">No cases</p><p class="oa-ov-s">${by === 'event' ? 'None started in the window' : 'None received in the window'}</p></div>`;
  const part = (key) => {
    const now = c[key] / c.cases, before = c.before?.cases ? c.before[key] / c.before.cases : null;
    const change = before == null ? null : Math.round(100 * now) - Math.round(100 * before);
    const host = shares.find((s) => s.share === key);
    const hot = !!host && change != null && change >= host.points && c.rose?.[key] === true;
    return { now, before, change, hot };
  };
  const s = part('serious'), f = part('death');
  const v = (x) => `<span${x.hot ? ' data-hot="true"' : ''}>${pct(x.now)}</span>${x.change == null ? '' : `<span class="oa-ov-ch"${x.hot ? ' data-hot="true"' : ''}>${arrow(x.change)}${Math.abs(x.change)}</span>`}`;
  const m = (x) => markSvg(x.before == null ? null : 100 * x.before, 100 * x.now, 100, x.hot, 68, x.before == null ? '' : `${pct(x.before)} before`, true);
  const said = `Serious: ${pct(s.now)} of the window's cases${s.before == null ? '' : `, ${pct(s.before)} before it`}. Fatal: ${pct(f.now)}${f.before == null ? '' : `, ${pct(f.before)} before`}.`;
  return `<div class="oa-ov-tile" ${tip(said)}>${k}<p class="oa-ov-v oa-ov-v2">${v(s)}<span class="oa-ov-dot">·</span>${v(f)}</p><div class="oa-ov-marks">${m(s)}${m(f)}</div></div>`;
}

// The four tiles, 2 x 2, from what has come: { qs, ts, w, why, counts, shares, by }
export const tilesHtml = (o) => `${casesTile(o)}${scoreTile(o, 'eb05')}${scoreTile(o, 'prr')}${seriousTile(o)}`;
