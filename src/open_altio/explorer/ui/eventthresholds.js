/* What the events table says of its thresholds (`thresholds`, rule explorer-event-thresholds), the
   At least values its heads open with: which rows they keep and how many, and the two quarters read. */

import { COMPARE, WORDS, meets, opOf } from './screens.js';
import { MONTHS, esc, fix, num, tip } from './util.js';

// a quarter and its days, as a head's tip says it: "2026 Q2, 1 Apr to 30 Jun"
export const quarterSpan = ({ year, q, words }) => {
  const first = (q - 1) * 3, last = first + 2;
  return `${words}, 1 ${MONTHS[first]} to ${new Date(Date.UTC(year, last + 1, 0)).getUTCDate()} ${MONTHS[last]}`;
};

// "2026 Q2 vs 2026 Q1" in the tools row, each quarter's tip its days
const quarterTip = (quarter) => `${quarter.words}: ${quarterSpan(quarter).slice(quarter.words.length + 2)} ${quarter.year}`;
export const quartersHtml = (now, before) => `<p class="oa-et-count oa-et-quarters"><span class="oa-has-tip" ${tip(quarterTip(now))}>${esc(now.words)}</span> vs <span class="oa-has-tip" ${tip(quarterTip(before))}>${esc(before.words)}</span></p>`;

// Whether a row meets the thresholds: they are filters, so every screen passes, each with all of its
// conditions together, read as screens.js reads them, `cases` being the statistics' own count where
// the row has it. None: it does.
export const meetsThresholds = (row, screens) => {
  const pair = { ...row, cases: row.pair_cases ?? row.cases };
  return screens.every((when) => meets(when, pair));
};

// The head that holds a screen's values: its first condition's column, by the head that shows it.
// Each is held as { column, op, start, at }, `at` empty once a person takes it off. Never kept: a
// visit starts again at `start`.
const HEADS = { ror_lower: 'ror', ror_upper: 'ror' };
export const limitsOf = (screens) => Object.fromEntries((screens || []).filter((when) => when.length).map((when) => [
  HEADS[when[0].column] || when[0].column,
  when.map((c) => ({ column: c.column, op: opOf(c), start: c[opOf(c)], at: c[opOf(c)] })),
]));
// the screen a head's values stand for now, without those taken off
export const screenOfLimits = (limits) => limits.filter((l) => l.at != null).map((l) => ({ column: l.column, [l.op]: l.at }));

// N is this quarter's cases, the head's own word for them
export const limitName = (l) => (l.column === 'newest' ? 'N' : WORDS[l.column] || l.column);
export const opWords = (l) => COMPARE[l.op];
export const wholeLimit = (l) => l.column === 'cases' || l.column === 'newest';
export const limitText = (l, v = l.at) => (v == null ? '' : wholeLimit(l) ? String(v) : fix(v, Number.isInteger(v * 10) ? 1 : 2));
// a head's tip of what it keeps: "EB05 at least 2.0, cases at least 3"
export const limitsWords = (limits) => limits.filter((l) => l.at != null).map((l, i) => {
  const name = limitName(l);
  return `${i && l.column === 'cases' ? 'cases' : name} ${opWords(l)} ${limitText(l)}`;
}).join(', ');

export const countWords = (kept, all) => `<span class="oa-has-tip" ${tip('These events meet every threshold')}><strong>${num(kept)}</strong> of ${num(all)} ${all === 1 ? 'event' : 'events'}</span>`;
export const hiddenWords = (n) => (n > 0 ? `${num(n)} ${n === 1 ? 'event' : 'events'} below the thresholds ${n === 1 ? 'is' : 'are'} hidden.` : '');
