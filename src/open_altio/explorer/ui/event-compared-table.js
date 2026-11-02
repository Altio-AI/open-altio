/* The Compared tab's table (event-compared.js counts and lays it out): the heads, each sorting from
   its menu but Change, and one row: a drug's name that opens its own view, a class as a grey heading
   with guide lines down what it holds, EB05 and PRR each as two marks on one scale per column, the
   two values and the change, in the warning color only past a host's threshold on a drug; the
   serious and fatal shares and a drug's label. */

import { icon } from './icons.js';
import { dailymed, labelRules, labelsOn } from './labels.js';
import { boundHtml, extraOf } from './event-compared-extra.js';
import { choice } from './overlays.js';
import { esc, fix, num, tip } from './util.js';

// the heads a person sorts by: their title, the words of each way, and how the count line says it
export const SORTS = {
  name: { title: (classes) => (classes ? 'Drug or class' : 'Drug'), ways: ['A to Z', 'Z to A'], dirs: ['asc', 'desc'], said: (d) => (d === 'asc' ? 'A to Z' : 'Z to A') },
  cases: { title: () => 'Cases', ways: ['Most first', 'Fewest first'], dirs: ['desc', 'asc'], said: (d) => (d === 'desc' ? 'most cases first' : 'fewest cases first') },
  eb05: { title: () => 'EB05', ways: ['Highest first', 'Lowest first'], dirs: ['desc', 'asc'], said: (d) => `${d === 'desc' ? 'highest' : 'lowest'} EB05 first` },
  prr: { title: () => 'PRR', ways: ['Highest first', 'Lowest first'], dirs: ['desc', 'asc'], said: (d) => `${d === 'desc' ? 'highest' : 'lowest'} PRR first` },
  serious: { title: () => 'Serious', ways: ['Highest first', 'Lowest first'], dirs: ['desc', 'asc'], said: (d) => `${d === 'desc' ? 'most' : 'fewest'} serious first` },
  fatal: { title: () => 'Fatal', ways: ['Highest first', 'Lowest first'], dirs: ['desc', 'asc'], said: (d) => `${d === 'desc' ? 'most' : 'fewest'} fatal first` },
  label: { title: () => 'Label', ways: ['Listed first', 'Not listed first'], dirs: ['desc', 'asc'], said: (d) => (d === 'desc' ? 'listed first' : 'not listed first') },
};
const TIPS = {
  name: (e, classes) => (classes ? 'Each drug and class compared' : 'Each drug compared'),
  cases: (e) => `Its cases with ${e} in the window, under the line's filters`,
  eb05: (e) => `EBGM's lower 5% bound for it and ${e}: every case up to the window's start, then every case up to its end`,
  prr: (e) => `PRR for it and ${e}: every case up to the window's start, then every case up to its end`,
  serious: () => 'The share of its cases in the window with a serious outcome',
  fatal: () => 'The share of its cases in the window that ended in death',
  label: (e) => `Whether today's US prescription label lists ${e}`,
};
// an added statistic sorts and is told like the two beside it
const HIGH = ['Highest first', 'Lowest first'];
export const sortOf = (id) => SORTS[id] || { title: () => extraOf(id).title, ways: HIGH, dirs: ['desc', 'asc'], said: (d) => `${d === 'desc' ? 'highest' : 'lowest'} ${extraOf(id).title} first` };
const tipOf = (id, e, classes) => (TIPS[id] ? TIPS[id](e, classes) : `${extraOf(id).about} for it and ${e}: every case up to the window's start, then every case up to its end`);
const NO_SCORE = 'No score for it with this event: too few cases, or a product of several ingredients.';
const COMBO_TIP = "A combination, counted by WHO's class of the products that hold it";

const share = (part, whole) => (!whole || part == null ? '' : part && (100 * part) / whole < 1 ? '<1%' : `${Math.round((100 * part) / whole)}%`);
const sk = () => '<span class="skeleton oa-cmp-sk"></span>';
const labelWord = (r) => (r.listed ? r.listed : r.label ? labelRules().words[r.label.answer] : r.reported ? labelRules().words.no_label : '');

// a row's value for a sort; an empty one sorts last whichever way
function sortValue(d, col) {
  const r = d.r;
  if (col === 'name') return d.title.toLowerCase();
  if (!r?.done || r.failed) return null;
  if (col === 'cases') return r.cases;
  if (col === 'eb05' || col === 'prr') return r[col]?.now ?? null;
  if (extraOf(col)) return r.extra?.[col]?.now ?? null;
  if (col === 'serious') return r.cases ? r.serious / r.cases : null;
  if (col === 'fatal') return r.cases ? r.death / r.cases : null;
  if (col === 'label' && d.kind === 'drug') { const w = labelWord(r); return w === labelRules().words.on_label ? 1 : w === labelRules().words.not_on_label ? 0 : null; }
  return null;
}
// rows side by side, sorted once every one has its numbers, so none jumps as numbers come; each level
// sorts on its own, so nothing leaves its class
export function ordered(list, sort) {
  if (sort.col !== 'name' && list.some((d) => !d.r?.done)) return list;
  const sign = sort.dir === 'asc' ? 1 : -1;
  return [...list].sort((a, b) => {
    const va = sortValue(a, sort.col), vb = sortValue(b, sort.col);
    if (va == null || vb == null) return (va == null) - (vb == null);
    return sign * (typeof va === 'string' ? va.localeCompare(vb) : va - vb);
  });
}

// a host's threshold on a statistic, passed at the window's end: each condition holding
const HOLDS = { at_least: (v, x) => v >= x, above: (v, x) => v > x, at_most: (v, x) => v <= x, below: (v, x) => v < x };
const opOf = (c) => Object.keys(c).find((k) => k !== 'column');
const meets = (conditions, row) => conditions.every((c) => row?.[c.column] != null && HOLDS[opOf(c)]?.(row[c.column], c[opOf(c)]));
const hotOf = (ctx, d, stat) => d.kind === 'drug' && !!d.r?.done && !d.r.failed && (ctx.screens || []).some((s) => s.conditions?.some((c) => c.column === stat) && meets(s.conditions, d.r.now));

// ---- the cells -------------------------------------------------------------------------------
// where a score stood at the window's start (hollow) and at its end (filled), on the column's scale
function markHtml(s, top, hot) {
  if (!s || s.now == null) return '';
  const at = (v) => `${(100 * Math.min(Math.max(v, 0), top)) / top}%`;
  const b = s.before;
  const lo = b == null ? s.now : Math.min(b, s.now), hi = b == null ? s.now : Math.max(b, s.now);
  return `<span class="oa-cmp-mark${hot ? ' oa-cmp-hot' : ''}" aria-hidden="true"><span class="oa-cmp-track"></span>
    <span class="oa-cmp-span" style="left:${at(lo)};right:calc(100% - ${at(hi)})"></span>${b == null ? '' : `<span class="oa-cmp-was" style="left:${at(b)}"></span>`}<span class="oa-cmp-now" style="left:${at(s.now)}"></span></span>`;
}
function valuesHtml(s, hot, why) {
  if (!s || s.now == null) return `<span class="oa-faint oa-has-tip" ${tip(why || NO_SCORE)}>Not worked out</span>`;
  const now = `<strong class="oa-cmp-nowv${hot ? ' oa-cmp-hotv' : ''}">${fix(s.now, 2)}</strong>`;
  return s.before == null ? `<span class="oa-has-tip" ${tip(s.noStart || "No score at the window's start: too few cases before it")}>${now}</span>` : `<span class="oa-faint">${fix(s.before, 2)} →</span> ${now}`;
}
function changeHtml(s, hot) {
  if (s?.now == null || s.before == null) return '';
  const d = s.now - s.before;
  const mark = d > 0.004 ? '▲' : d < -0.004 ? '▼' : '';
  // a score the window left where it was says so, never a red "0.00"
  if (!mark) return '<span class="oa-cmp-flat">no change</span>';
  return `<span class="${hot ? 'oa-cmp-hotv' : 'oa-cmp-flat'}">${mark}${fix(Math.abs(d), 2)}</span>`;
}
function statCells(d, stat, tops, hot) {
  const r = d.r;
  if (!r?.done) return `<td class="oa-cmp-mk">${sk()}</td><td class="oa-cmp-v">${sk()}</td><td class="oa-num oa-cmp-chg"></td>`;
  const s = r[stat];
  const why = d.kind === 'combo' ? 'No score for a combination: the release works its statistics out for each ingredient.' : r.why;
  return `<td class="oa-cmp-mk">${markHtml(s, tops[stat], hot)}</td><td class="oa-cmp-v">${r.failed ? '' : valuesHtml(s, hot, why)}</td><td class="oa-num oa-cmp-chg">${changeHtml(s, hot)}</td>`;
}
function extraCell(d, id) {
  const r = d.r;
  if (!r?.done) return `<td class="oa-num">${sk()}</td>`;
  return `<td class="oa-num oa-cmp-xv">${r.failed ? '' : valuesHtml(r.extra?.[id], false, r.why)}</td>`;
}
function labelCell(d) {
  if (!labelsOn()) return '';
  const r = d.r;
  if (d.kind !== 'drug') return '<td></td>';
  if (!r?.done) return `<td>${sk()}</td>`;
  if (r.failed || !r.reported) return '<td></td>';
  if (r.listed) return `<td>${esc(r.listed)}</td>`;
  const l = r.label, words = labelRules().words, why = l && labelRules().reasons?.[l.answer];
  if (!l) return `<td><span class="oa-faint oa-has-tip" ${tip(r.whyNoLabel || 'Not compared with a label')}>${esc(words.no_label)}</span></td>`;
  if (why) return `<td><span class="oa-faint oa-has-tip" ${tip(`${words[l.answer]}: ${why}`)}>${esc(words[l.answer])}</span></td>`;
  if (l.answer === 'uncertain' || l.answer === 'forms_differ' || !l.setid) return `<td><span class="${l.answer === 'uncertain' ? 'oa-faint' : ''}">${esc(words[l.answer])}</span></td>`;
  return `<td><a class="oa-cmp-label" href="${dailymed({ setid: l.setid, version: l.spl_version })}" target="_blank" rel="noopener" ${tip('Opens the label on DailyMed in a new tab')}>${esc(words[l.answer])}</a></td>`;
}

const COLS = (extras) => ['name', 'n', 'mk', 'v', 'chg', 'mk', 'v', 'chg', ...extras.map(() => 'xv'), 'pct', 'pct', ...(labelsOn() ? ['l'] : []), 'x'];
export const colgroup = (extras = []) => `<colgroup>${COLS(extras).map((c) => `<col class="oa-cmp-c-${c}">`).join('')}</colgroup>`;

// the arrow of the sort chosen, up for the first way (highest or A to Z first), down for the other; a head
// not sorted by keeps the arrow's room empty, so nothing moves when the sort does
const arrow = (sort, id) => `<span class="oa-cmp-arrow" aria-hidden="true">${sort.col === id ? icon(sort.dir === sortOf(id).dirs[0] ? 'arrowUp' : 'arrowDown') : ''}</span>`;

export function headHtml(sort, e, classes, extras = []) {
  const t = (id, cls = '', span = 1) => `<th scope="col" class="${cls}"${span > 1 ? ` colspan="${span}"` : ''}><button type="button" class="oa-cmp-head${sort.col === id ? ' oa-cmp-head-on' : ''}" data-act="cmp-head" data-v="${id}" aria-haspopup="menu" ${tip(tipOf(id, e, classes))}>${sortOf(id).title(classes)}${arrow(sort, id)}</button></th>`;
  const chg = '<th scope="col" class="oa-num"><span class="oa-cmp-head-plain">Change</span></th>';
  return `<tr>${t('name', 'oa-cmp-name')}${t('cases', 'oa-num')}${t('eb05', 'oa-cmp-mkh', 2)}${chg}${t('prr', 'oa-cmp-mkh', 2)}${chg}${extras.map((x) => t(x, 'oa-num')).join('')}${t('serious', 'oa-num')}${t('fatal', 'oa-num')}${labelsOn() ? t('label') : ''}<th class="oa-cmp-x" aria-label="Take out"></th></tr>`;
}

// a head's menu: Sort, its two ways, and the event's drug staying on top
export function sortMenu(sort, id, own, classes, bounds = {}) {
  const s = sortOf(id);
  const ways = s.ways.map((w, i) => choice(sort.col === id && sort.dir === s.dirs[i], w, null, `data-act="cmp-sort" data-v="${id}" data-dir="${s.dirs[i]}"`, { radio: true })).join('');
  return `<p class="menu-heading">Sort</p>${ways}${extraOf(id) ? boundHtml(id, bounds[id]) : ''}`;
}

// ---- a row -------------------------------------------------------------------------------------
const STEP = 18; // each level's step in, in pixels
// thin guide lines down what an open class holds, one for each level above the row
function guides(lvl) {
  if (!lvl) return '';
  const at = Array.from({ length: lvl }, (_, i) => `calc(var(--cmp-pad) + 5px + ${STEP * i}px) 0`);
  return ` style="background-image:${at.map(() => 'linear-gradient(var(--cmp-guide), var(--cmp-guide))').join(',')};background-size:${at.map(() => '1px 100%').join(',')};background-position:${at.join(',')};background-repeat:no-repeat"`;
}

function nameHtml(ctx, d, e) {
  const r = d.r, pad = STEP * (d.lvl || 0), qual = (words) => `<span class="oa-cmp-qual">${esc(words)}</span>`;
  if (d.kind === 'class') {
    const words = d.code + (d.out?.length ? ` without ${d.out.join(', ')}` : '');
    return `<span class="oa-cmp-namebox" style="padding-left:${pad}px"><button type="button" class="oa-cmp-open" data-act="cmp-toggle" data-code="${esc(d.code)}" aria-expanded="${!!d.open}" ${tip(d.open ? 'Hide what is in it' : 'Show what is in it')}><span class="oa-cmp-chev" aria-hidden="true">${icon('chevronDown')}</span><span class="oa-cmp-words" ${tip(`${d.title}, WHO class ${words}`)}>${esc(d.title)}</span> ${qual(words)}</button></span>`;
  }
  const indent = pad + (d.lvl ? 14 : 0);
  if (d.kind === 'combo') return `<span class="oa-cmp-namebox" style="padding-left:${indent}px"><span class="oa-cmp-words oa-has-tip" ${tip(COMBO_TIP)}>${esc(d.title)}</span> ${qual(d.code)}</span>`;
  const mark = ctx.drugMark(d.name);
  // a drug opens its own view of the event, where its cases name the event, from the first drug's
  const goes = !d.own && !ctx.from && r?.done && !r.failed && r.reported;
  const says = `Open ${d.title}'s ${e}, read only, in this window and these filters`;
  const name = goes ? `<button type="button" class="oa-link oa-cmp-drug" data-act="cmp-go" data-name="${esc(d.name)}" ${tip(says)}>${esc(d.title)}</button>`
    : `<span class="oa-cmp-drug${d.own ? ' oa-cmp-own' : ''}"${!d.own && r?.done && !r.reported ? ` ${tip(`No case names ${d.title} with ${e}`)}` : ''}>${esc(d.title)}</span>`;
  return `<span class="oa-cmp-namebox" style="padding-left:${indent}px">${name}${mark ? ` <span class="oa-cmp-mark-host">${mark}</span>` : ''}</span>`;
}

export function rowHtml(ctx, d, tops, e, extras = []) {
  const r = d.r;
  const hot = { eb05: hotOf(ctx, d, 'eb05'), prr: hotOf(ctx, d, 'prr') };
  const counts = !r?.done ? `<td class="oa-num">${sk()}</td>` : `<td class="oa-num">${r.failed ? '' : num(r.cases)}</td>`;
  const shares = !r?.done ? `<td class="oa-num">${sk()}</td><td class="oa-num">${sk()}</td>` : `<td class="oa-num">${share(r.serious, r.cases)}</td><td class="oa-num">${share(r.death, r.cases)}</td>`;
  const x = d.top && !d.pinned ? `<button type="button" class="oa-cmp-remove" data-act="cmp-remove" data-key="${esc(d.key)}" aria-label="Take ${esc(d.title)} out" ${tip('Take it out of the comparison')}>${icon('close')}</button>` : '';
  const cls = ['oa-cmp-row', d.pinned && 'oa-cmp-ref', d.kind === 'class' && 'oa-cmp-class', d.kind === 'combo' && 'oa-cmp-combo', d.stale && 'oa-cmp-stale'].filter(Boolean).join(' ');
  return `<tr class="${cls}" data-row="${esc(d.key)}"><th scope="row" class="oa-cmp-name"${guides(d.lvl)}>${nameHtml(ctx, d, e)}</th>${counts}
    ${statCells(d, 'eb05', tops, hot.eb05)}${statCells(d, 'prr', tops, hot.prr)}${extras.map((x) => extraCell(d, x)).join('')}${shares}${labelCell(d)}<td class="oa-cmp-x">${x}</td></tr>`;
}

// a row's place while what a class holds is read
export const waitRow = (lvl) => `<tr class="oa-cmp-row oa-cmp-wait"><th scope="row" class="oa-cmp-name"${guides(lvl)}><span class="oa-cmp-namebox" style="padding-left:${STEP * lvl + 14}px">${sk()}</span></th><td class="oa-num">${sk()}</td><td class="oa-cmp-mk"></td><td class="oa-cmp-v">${sk()}</td><td></td><td class="oa-cmp-mk"></td><td class="oa-cmp-v">${sk()}</td><td></td><td class="oa-num">${sk()}</td><td class="oa-num">${sk()}</td>${labelsOn() ? '<td></td>' : ''}<td></td></tr>`;
