/* The events table's own columns (eventstable.js): those every table draws, and those Columns shows
   or hides. A column has its `head`, its `tip`, the row's `value` it sorts and bounds by, its `cell`,
   its sort's words (`words`, the first sorting `first`), and either a `bound` (the At least box) or
   `ticks` (tick boxes of each value); `menu: false` for a head that opens nothing. */

import { quarterSpan } from './eventthresholds.js';
import { dailymed, labelRules, labelsOn } from './labels.js';
import { S, ptVersion, releaseQuarter } from './state.js';
import { days, esc, fig, num, tip } from './util.js';

const WHOLE = 'Worked out once for the whole release.';
const COUNTS = ['Most first', 'Fewest first'];
const FIGURES = ['Highest first', 'Lowest first'];
const NAMES = ['A to Z', 'Z to A'];

const figure = (id, head, words, about, more = {}) => ({ id, head, menuWords: words, group: 'statistics', tip: `${about}. ${WHOLE}`, value: (r) => r[id] ?? null, cell: (r) => fig(r[id]), cls: 'oa-num', words: FIGURES, first: 'desc', bound: { words: 'At least' }, ...more });
const shareOf = (key, head, about, id = key) => {
  const share = (r) => (r.cases && r[key] != null ? (100 * r[key]) / r.cases : null);
  return { id, head, menuWords: head, group: 'cases', tip: about, value: share, cell: (r) => (share(r) == null ? '' : `${Math.round(share(r))}%`), cls: 'oa-num', words: FIGURES, first: 'desc', bound: { words: 'At least', unit: '% of cases', whole: true, max: 100 } };
};
// the columns Columns shows or hides, in its order: the statistics, then the facts about the cases
const OPTIONAL = [
  figure('expected', 'Expected', 'Expected', 'The cases expected if the drug and the event were unrelated, within age band, sex and year received'),
  figure('eb95', 'EB95', 'EB95', "EBGM's upper 95% bound"),
  figure('prr', 'PRR', 'PRR', "The event's share of the drug's cases, against its share of every other case"),
  figure('chi_square_yates', 'Chi-square', 'Chi-square', "The chi-square with Yates' correction, as PRR's threshold reads it"),
  figure('ror', 'ROR', 'ROR', 'Reporting odds ratio'),
  figure('ror_bounds', 'ROR 95%', 'ROR lower and upper bounds', "The ROR's 95% interval, its lower and upper bound", {
    value: (r) => r.ror_lower ?? null, cell: (r) => (r.ror_lower == null ? '' : `${fig(r.ror_lower)} to ${fig(r.ror_upper)}`), bound: { words: 'Lower bound at least' },
  }),
  figure('ic', 'IC', 'IC', 'Information component, on a doubling scale'),
  figure('ic025', 'IC025', 'IC025', "The lower end of IC's 95% interval"),
  { id: 'cases', head: 'Total cases', menuWords: 'Total cases', group: 'cases', tip: 'Every case naming the drug and the event, in every quarter', value: (r) => r.cases, cell: (r) => num(r.cases), cls: 'oa-num', words: COUNTS, first: 'desc', bound: { words: 'At least', unit: 'cases', whole: true } },
  shareOf('serious', 'Serious', 'The share of its cases with a serious outcome'),
  shareOf('death', 'Fatal', 'The share of its cases that ended in death', 'fatal'),
  { id: 'onset_days', head: 'Onset', menuWords: 'Onset, median days', group: 'cases', stats: true, tip: `The median days from the first dose, day 1, to the event. ${WHOLE}`, value: (r) => r.onset_days ?? null, cell: (r) => (r.onset_days == null ? '' : days(r.onset_days)), cls: 'oa-num', words: FIGURES, first: 'desc', bound: { words: 'At least', unit: 'days' } },
];
export const OPENS_WITH = [];

// an event against today's label, in the words of rule explorer-label-words; a word of no
// comparison (Not compared, Can't tell) is grey
const LABEL_ORDER = ['on_label', 'related', 'not_on_label', 'uncertain', 'forms_differ', 'no_label'];
const labelWord = (r) => labelRules().words[r.label?.answer || 'no_label'];
const labelOrder = () => [...new Set(LABEL_ORDER.map((a) => labelRules().words[a]))];
function labelCell(r, t) {
  const l = r.label, words = labelRules().words, why = l && labelRules().reasons[l.answer];
  if (!l) return `<span class="oa-faint oa-has-tip" ${tip(t.whyNoLabel || 'Not compared with a label')}>${esc(words.no_label)}</span>`;
  if (l.answer === 'forms_differ') return `<button type="button" class="oa-link oa-et-forms" data-act="et-forms" aria-haspopup="menu" ${tip("The labels of the drug's forms do not agree: press to see each")}>${esc(words.forms_differ)}</button>`;
  if (why) return `<span class="oa-faint oa-has-tip" ${tip(`${words[l.answer]}: ${why}`)}>${esc(words[l.answer])}</span>`;
  if (l.answer === 'uncertain' || !l.setid) return `<span class="${l.answer === 'uncertain' ? 'oa-faint' : ''}">${esc(words[l.answer])}</span>`;
  return `<a class="oa-et-label" href="${dailymed({ setid: l.setid, version: l.spl_version })}" target="_blank" rel="noopener" ${tip('Opens the label on DailyMed in a new tab')}>${esc(words[l.answer])}</a>`;
}

// each of the newest quarters' cases, as a line ending in a dot on the newest
function spark(r) {
  const ns = r.recent?.length ? r.recent : [0];
  const w = 96, h = 24, max = Math.max(1, ...ns), step = ns.length > 1 ? w / (ns.length - 1) : w;
  const pts = (ns.length > 1 ? ns : [ns[0], ns[0]]).map((n, i) => [(i * step).toFixed(1), (h - 3 - (n / max) * (h - 7)).toFixed(1)]);
  const most = Math.max(...ns);
  const at = releaseQuarter(ns.length - 1 - ns.indexOf(most)).words;
  const words = most ? `${releaseQuarter(ns.length - 1).words} to ${releaseQuarter().words}, most in ${at}: ${num(most)} ${most === 1 ? 'case' : 'cases'}` : `No case in the last ${ns.length} quarters`;
  const [x, y] = pts[pts.length - 1];
  return `<span class="oa-et-trend" ${tip(words)}><svg viewBox="-2 0 ${w + 4} ${h}" aria-label="${esc(words)}" role="img"><polyline points="${pts.map((p) => p.join(',')).join(' ')}"/><circle cx="${x}" cy="${y}" r="2"/></svg></span>`;
}

// the name, then EMA's list it is on, in small words after it
const TAGS = [['dme', 'DME', "On EMA's designated medical event list"], ['ime', 'IME', "On EMA's important medical event list"]];
const nameCell = (r) => `${esc(r.pt)}${TAGS.filter(([k]) => r[k]).slice(0, 1).map(([k, w, said]) => ` <span class="oa-et-tag" data-tag="${k}" ${tip(said)}>${w}</span>`).join('')}`;

// The columns every table draws, in their order: the event's name, then the newest quarter against
// the one before it (each statistic at that quarter's end, quarterly.py).
export function fixedColumns() {
  const ptWords = ptVersion() ? `Each event by its current PT in MedDRA ${ptVersion()}` : 'Each event as FDA wrote it';
  const now = releaseQuarter().words, before = releaseQuarter(1).words;
  const atEnd = (name, q) => `${name} at the end of ${q}, counting every case FDA had received by then`;
  const up = (r) => (r.newest > (r.prior ?? Infinity) ? ` <span class="oa-et-up" ${tip(`Up from ${num(r.prior)} in ${before}`)}>▲</span>` : '');
  const stat = (id, head, about, cell) => ({ id, head, group: 'statistics', tip: about, value: (r) => r[id] ?? null, cell, cls: 'oa-num', words: FIGURES, first: 'desc', bound: { words: 'At least' } });
  const count = (id, head, about, cell) => ({ id, head, tip: about, value: (r) => r[id] ?? null, cell, cls: 'oa-num', words: COUNTS, first: 'desc', bound: { words: 'At least', unit: 'cases', whole: true } });
  return [
    { id: 'event', head: 'Event', tip: ptWords, value: (r) => r.pt.toLowerCase(), cell: nameCell, words: NAMES, first: 'asc', held: true, name: true },
    count('newest', 'N', `The cases FDA first received in ${quarterSpan(releaseQuarter())}`, (r) => `<strong>${num(r.newest)}</strong>${up(r)}`),
    { ...count('prior', 'N prior', `The cases FDA first received in ${quarterSpan(releaseQuarter(1))}`, (r) => num(r.prior)), bound: null },
    stat('ebgm', 'EBGM', atEnd('EBGM', now), (r) => `<strong>${fig(r.ebgm)}</strong>`),
    { ...stat('ebgm_prior', 'EBGM prior', atEnd('EBGM', before), (r, t) => (t.priorDue ? '<span class="skeleton oa-et-due"></span>' : fig(r.ebgm_prior))), bound: null },
    stat('eb05', 'EB05', atEnd("EBGM's lower 5% bound", now), (r) => fig(r.eb05)),
    { id: 'trend', head: 'Trend', tip: `The cases FDA first received in each of the last ${S.release.event_thresholds.trend_quarters} quarters`, cell: spark, menu: false },
  ];
}

// what Columns lists of the table's own: the label's where the release holds labels, then the rest
export const listedColumns = () => [
  ...(labelsOn() ? [{ id: 'label', head: 'Label', menuWords: 'Label', group: 'cases', tip: "Whether today's US prescription label lists the event", value: labelWord, cell: labelCell, ticks: { heading: 'Show events whose label status is', value: labelWord, order: labelOrder(), foot: "Against today's US prescription label." } }] : []),
  ...OPTIONAL,
];
