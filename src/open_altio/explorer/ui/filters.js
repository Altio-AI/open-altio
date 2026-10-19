/* The filters: which there are, what each says in words, clearing one, and a scope's filters as the
   query string /api reads (src/open_altio/explorer/filters.py reads it the same way). */

import { OUTCOME, REPORTER, SEX, labelOf } from './codes.js';
import { countryName } from './countries.js';
import { labelRules, labelWords, labelsOn } from './labels.js';
import { S, ages, className, defaultRoles, drugWords, eraSpan, meddraOn, productLabel, whoOn } from './state.js';
import { companyName, day, num } from './util.js';

function chosenTerms(f) {
  const terms = new Set(f.pts);
  for (const id of f.cmqs) S.cmqs.find((q) => q.id === id)?.terms.forEach((t) => terms.add(t));
  return [...terms];
}

// roles as a query names them: none when they are the ones a page opens with
const sameRoles = (roles) => roles.join() === defaultRoles().join();
// the roles a count covers, as FDA codes them: 'PS or SS'
export const rolesWords = (roles) => (roles.length === 1 ? roles[0] : `${roles.slice(0, -1).join(', ')} or ${roles.at(-1)}`);
// a product page's roles, on the strip beside the filters while they are not the ones it opens with
export const ROLES = { key: 'roles', label: 'Roles' };
export const rolesChanged = (sc) => (sc.product && !sameRoles(sc.roles) ? rolesWords(sc.roles) : '');

export function query(sc, extra = {}, { noReactions = false } = {}) {
  const p = new URLSearchParams();
  const f = sc.f;
  if (sc.product) {
    p.set('product', sc.product);
    if (sc.unit !== drugWords().default_unit) p.set('unit', sc.unit);
    if (!sameRoles(sc.roles)) sc.roles.forEach((r) => p.append('prole', r));
    sc.exclude.forEach((s) => p.append('exclude', s));
    sc.include.forEach((s) => p.append('include', s));
  }
  if (f.dprods.length) {
    f.dprods.forEach((d) => p.append('dprod', d));
    if (!sameRoles(f.droles)) f.droles.forEach((r) => p.append('drole', r));
  }
  // the class filter's roles count its classes and the Overview's breakdown by class
  f.atc.forEach((c) => p.append('atc', c));
  f.atcOut.forEach((c) => p.append('atc_out', c));
  if (!sameRoles(f.aroles)) f.aroles.forEach((r) => p.append('arole', r));
  if (f.could && f.atc.length) p.set('could', '1');
  if (!noReactions) {
    chosenTerms(f).forEach((t) => p.append('pt', t));
    f.smqs.forEach((s) => p.append('smq', `${s.code}:${s.scope}`));
    f.ptsOut.forEach((t) => p.append('pt_out', t));
    f.soc.forEach((n) => p.append('soc', n));
  }
  if (f.from) p.set('received_from', f.from);
  if (f.to) p.set('received_to', f.to);
  if (f.efrom) p.set('event_from', f.efrom);
  if (f.eto) p.set('event_to', f.eto);
  for (const k of ['sex', 'age', 'outcome', 'reporter', 'country']) f[k].forEach((v) => p.append(k, v));
  if (f.sender) p.set('sender', f.sender);
  if (f.era) { p.set('f', '1'); f.era.forEach((e) => p.append('era', e)); }
  if (f.dedup !== S.release.dedup) p.set('dedup', f.dedup);
  if (f.label) (f.label.length ? f.label : [labelRules().nothing_ticked]).forEach((k) => p.append('label', k));
  for (const [k, v] of Object.entries(extra)) p.set(k, v);
  return p.toString();
}

export const FILTERS = [
  { key: 'spellings', label: 'Spellings', kind: 'spellings', productOnly: true },
  { key: 'reactions', label: 'Reactions', kind: 'reactions' },
  { key: 'label', label: 'Label status', kind: 'label', productOnly: true, labels: true },
  { key: 'drugs', label: 'Drugs', kind: 'drugs', allOnly: true },
  { key: 'soc', label: 'System organ class', kind: 'codes', map: {}, meddra: true, note: 'A case counts when any of its reactions is in a ticked class. Each reaction is placed by the primary class of its current PT.' },
  { key: 'atc', label: 'Drug class (ATC)', kind: 'atc', allOnly: true, who: true },
  { key: 'received', label: 'Received by FDA', kind: 'days', lo: 'from', hi: 'to', what: 'FDA first received the case' },
  { key: 'event', label: 'Event date', kind: 'days', lo: 'efrom', hi: 'eto', what: 'the event happened' },
  { key: 'sex', label: 'Sex', kind: 'codes', map: SEX, field: 'sex', note: 'Not given means the report gives neither female nor male: FDA\'s field is empty or holds another code, such as NS (not specified) or UNK.' },
  // the bands come with the release's answer, after this list is made
  { key: 'age', label: 'Age', kind: 'codes', field: 'age', get map() { return ages(); }, get order() { return Object.keys(ages()); }, get note() { return ageNote(); } },
  { key: 'outcome', label: 'Outcome', kind: 'codes', map: OUTCOME, order: Object.keys(OUTCOME) },
  { key: 'reporter', label: 'Who reported', kind: 'codes', map: REPORTER, field: 'occp_cod' },
  { key: 'country', label: 'Country', kind: 'codes', country: true },
  { key: 'sender', label: 'Company', kind: 'sender' },
  { key: 'era', label: 'FDA system', kind: 'era' },
  { key: 'dedup', label: 'Duplicates', kind: 'dedup' },
];
// what the youngest bands hold and why one has no range (rule age-bands); a negative or impossible
// age is no age (rule age-in-years)
function ageNote() {
  const a = ages();
  return `${a['0-27d']}, ${a['28d-1']} and ${a['under-1']}, ticked together, are every case under 2. ${a['under-1']} holds the children whose age was written as 0 years, with no age group from the sender placing them as a newborn or an infant. ${a._none} means the report gives no age, or one that cannot be, such as a negative age.`;
}
export const filtersFor = (sc) => FILTERS.filter((d) => !(d.allOnly && sc.product) && !(d.productOnly && !sc.product) && !(d.who && !whoOn()) && !(d.meddra && !meddraOn())
  && !(d.labels && !labelsOn()));

// chosen classes in words: their codes, and WHO's name of a single one
export const classesWords = (codes) => (codes.length === 1 && className(codes[0]) ? `${codes[0]} ${className(codes[0])}` : codes.join(', '));
// what a tree filter leaves out of the groups chosen in it
const leftOut = (list, words = (x) => x.join(', ')) => (list.length ? `, leaving out ${words(list)}` : '');

function reactionWords(f) {
  return [
    ...f.pts,
    ...f.smqs.map((s) => `${s.name}, ${s.scope}`),
    ...f.cmqs.map((id) => S.cmqs.find((q) => q.id === id)?.name).filter(Boolean),
  ].join('; ') + leftOut(f.ptsOut);
}

export function filterWords(sc, def) {
  const f = sc.f;
  switch (def.kind) {
    case 'reactions': return reactionWords(f);
    case 'spellings': return [
      sc.exclude.length ? `${num(sc.exclude.length)} left out` : '',
      sc.include.length ? `${num(sc.include.length)} with no ingredient added` : '',
    ].filter(Boolean).join(', ');
    case 'label': return f.label ? labelWords(f.label) : '';
    case 'drugs': return f.dprods.length ? `${f.dprods.map(productLabel).join(', ')}, as ${rolesWords(f.droles)}` : '';
    case 'atc': return f.atc.length ? `${classesWords(f.atc)}${leftOut(f.atcOut, classesWords)}, as ${rolesWords(f.aroles)}${f.could ? ', and the drugs that could be in it' : ''}` : '';
    case 'days': {
      const a = f[def.lo], b = f[def.hi];
      if (a && b) return a === b ? `${day(a)}` : `${day(a)} to ${day(b)}, both included`;
      if (a) return `On or after ${day(a)}`;
      if (b) return `On or before ${day(b)}`;
      return '';
    }
    case 'codes': return f[def.key].map((c) => (def.country ? countryName(c) : labelOf(def.map, c))).join(', ');
    case 'sender': return f.sender ? companyName(f.sender) : '';
    case 'era': return f.era ? (f.era.length ? f.era.map((e) => `${e} (${eraSpan(e, { years: true })})`).join(', ') : 'None') : '';
    case 'dedup': return f.dedup === S.release.dedup ? '' : f.dedup === 'all' ? 'Probable duplicates included' : 'Probable duplicates left out';
    default: return '';
  }
}

export function clearFilter(sc, key) {
  const f = sc.f;
  if (key === 'roles') { if (sc.product) sc.roles = defaultRoles(); } else if (key === 'spellings') { sc.exclude = []; sc.include = []; } else if (key === 'reactions') { f.pts = []; f.smqs = []; f.cmqs = []; f.ptsOut = []; } else if (key === 'drugs') { f.dprods = []; f.droles = defaultRoles(); } else if (key === 'atc') { f.atc = []; f.atcOut = []; f.aroles = defaultRoles(); f.could = false; } else if (key === 'received') { f.from = ''; f.to = ''; } else if (key === 'event') { f.efrom = ''; f.eto = ''; }
  else if (key === 'era') f.era = null;
  else if (key === 'dedup') f.dedup = S.release.dedup;
  else if (key === 'label') f.label = null; // every tick on, as the list opens
  else if (Array.isArray(f[key])) f[key] = [];
  else if (key in f) f[key] = '';
}
