/* What the Compared tab counts and keeps (event-compared.js draws it): the event's numbers for its
   drug and for each row compared with it, a drug or one of WHO's classes, every row counted the same
   way, in the same window and filters. Each number is a published question's answer:
     a row's cases, serious and fatal cases in the window: /api/events/group, the drug in the event's
       settings, or the class counted in the same roles, with the line's filters and the window's days;
     a drug's EB05 and PRR at the window's start and at its end: /api/statistics/quarters, every case
       FDA had received by each quarter's end, which no filter changes;
     a class's EB05 and PRR: /api/statistics by class, on every case of the release, where it holds
       them, so they stand only for a window to the release's end, with no start;
     a drug's label answer: its row of /api/events for one reaction, /api/labels/query for a group;
     the classes and drugs inside a class: /api/classes, and /api/product for a drug's own name.
   The rows compared are the person's, kept for each drug as a view choice: the classes ticked and
   left out as the Drug class filter keeps them, and the drugs. With no choice yet a drug starts
   beside its own chemical class. Where ctx.classes is false no class is asked for, started or shown,
   and a class kept earlier stays kept, unread. */

import { learnOwn, learnTree } from './classes.js';
import { api } from './server.js';
import { S, keepView, learnClasses, learnTitles, productLabel, releaseEnd, viewChoice } from './state.js';
import { quarterEnd } from './util.js';
import { EXTRA } from './event-compared-extra.js';

// what is told when numbers come: the tables drawn again
const told = new Set();
export const onNumbers = (fn) => told.add(fn);
export const offNumbers = (fn) => told.delete(fn);
const tell = () => told.forEach((fn) => fn());

// ---- names -------------------------------------------------------------------------------------
// a drug as the page names it: the title an answer gave it, else its name with a capital
export function titleOf(name) {
  const t = productLabel(name);
  return t === name && /^[a-z]/.test(t) ? t[0].toUpperCase() + t.slice(1) : t;
}
export const inSentence = (words) => (/^[A-Z][a-z]/.test(words) ? words[0].toLowerCase() + words.slice(1) : words);

// ---- what is compared, for each drug -----------------------------------------------------------
const KEPT = 'compared';
const blank = () => ({ atc: [], atcOut: [], drugs: [], order: [], names: {} });
const isDrug = (d) => typeof d?.name === 'string' && typeof d?.title === 'string';
const isTicks = (t) => ['atc', 'atcOut', 'drugs', 'order'].every((k) => Array.isArray(t?.[k])) && !!t.names && t.drugs.every(isDrug);
const keptAll = () => { const v = viewChoice(KEPT, {}); return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; };
const kept = (drug) => (isTicks(keptAll()[drug]) ? keptAll()[drug] : null);

// a class's rows and each drug's own codes, as the answers came
const starting = new Map(); // drug -> the ticks it starts with, a promise until known
export const ownCodes = {}; // drug -> its own WHO codes, so the classes on the way to it start open

// the drug's chemical class, from its own full code, the one the drug's name is the class of
function startOf(drug) {
  if (!starting.has(drug)) {
    starting.set(drug, null);
    api(`/api/classes?${new URLSearchParams({ q: drug })}`).then((r) => {
      const word = drug.toLowerCase();
      const own = r.classes.filter((c) => c.level === 5 && c.name.toLowerCase() === word);
      ownCodes[drug] = own.map((c) => c.code);
      learnOwn(r.classes);
      learnClasses(r.classes.map((c) => [c.code, c.name]));
      const cls = own[0] && r.classes.find((c) => c.level === 4 && own[0].code.startsWith(c.code));
      starting.set(drug, !cls ? blank() : { ...blank(), atc: [cls.code], order: [`c:${cls.code}`], names: { [cls.code]: cls.name } });
    }, () => starting.set(drug, blank())).finally(tell);
  }
  return starting.get(drug);
}
// what is ticked for the event's drug: null while its start is being read
export function ticksOf(ctx) {
  const t = kept(ctx.drug);
  if (t) return t;
  return ctx.classes ? startOf(ctx.drug) : blank();
}
// the person's change: from here on the ticks are theirs; new rows go last, rows gone leave the order
export function change(ctx, fn) {
  const t = structuredClone(ticksOf(ctx) || blank());
  fn(t);
  const keys = [...t.atc.map((c) => `c:${c}`), ...t.drugs.map((d) => `d:${d.name}`)];
  t.order = [...t.order.filter((k) => keys.includes(k)), ...keys.filter((k) => !t.order.includes(k))];
  keepView(KEPT, { ...keptAll(), [ctx.drug]: t });
  learnTitles(t.drugs);
  tell();
}
// the rows compared, in the order added: null while the start is being read
export function picksOf(ctx) {
  const t = ticksOf(ctx);
  if (!t) return null;
  const at = (key) => { const i = t.order.indexOf(key); return i < 0 ? Infinity : i; };
  const classes = !ctx.classes ? [] : t.atc.map((code) => ({ kind: 'class', code, title: t.names[code] || code, out: t.atcOut.filter((o) => o !== code && o.startsWith(code)), key: `c:${code}` }));
  const drugs = t.drugs.map((d) => ({ kind: 'drug', name: d.name, title: d.title, key: `d:${d.name}` }));
  return [...classes, ...drugs].sort((a, b) => at(a.key) - at(b.key));
}

// ---- how each row is counted -------------------------------------------------------------------
// The settings that say how a drug counts; the event's own spellings added or left out are its
// drug's alone, so another drug is counted any product containing it, in the same roles.
const SETTINGS = ['product', 'prole', 'unit', 'include', 'exclude', 'dedup'];
const OWN = ['include', 'exclude'];
function asked(ctx, drug, { settingsOnly = false } = {}) {
  const p = new URLSearchParams(ctx.query());
  if (settingsOnly) [...new Set(p.keys())].filter((k) => !SETTINGS.includes(k)).forEach((k) => p.delete(k));
  if (drug !== ctx.drug) OWN.forEach((k) => p.delete(k));
  p.set('product', drug);
  return p;
}
const reactions = (ctx, name) => ctx.reaction.map((r) => `${name}=${encodeURIComponent(r)}`).join('&');
// the roles and products each drug is counted in, from the event's settings and the line's filter
export function countedAs(ctx) {
  const p = new URLSearchParams(ctx.query());
  const roles = p.getAll('prole').length ? p.getAll('prole') : S.release.drugs.default_roles;
  const unit = p.get('unit') || S.release.drugs.default_unit;
  return { roles, unit };
}
// a class as the Drug class filter counts it: a case where a drug in the class, less the classes left
// out under it, is in the event's roles; the line's other filters and the window as they are
function classAsked(ctx, n) {
  const p = new URLSearchParams(ctx.query());
  const { roles } = countedAs(ctx);
  ['product', 'prole', 'unit', ...OWN].forEach((k) => p.delete(k));
  p.set('atc', n.code);
  (n.out || []).forEach((o) => p.append('atc_out', o));
  roles.forEach((r) => p.append('arole', r));
  return p;
}
// the event's scope for listing classes: their cases counted as a class row counts them, over every
// date, as the tree of a class does not change with the window
function classScope(ctx) {
  const p = new URLSearchParams();
  const dedup = new URLSearchParams(ctx.query()).get('dedup');
  if (dedup) p.set('dedup', dedup);
  countedAs(ctx).roles.forEach((r) => p.append('arole', r));
  return `${p}${p.size ? '&' : ''}${reactions(ctx, 'pt')}`;
}

// ---- each row's numbers, asked once for each question and kept while the page is open -----------
const answers = new Map(); // url -> { done, value, failed }
// the rows inside a class wait behind the others, three at a time: a class can hold many
let asking = 0;
const queue = [];
function nextAsk() { while (asking < 3 && queue.length) { asking += 1; queue.shift()(); } }
const queued = (url) => new Promise((ok, no) => {
  queue.push(() => api(url).then(ok, no).finally(() => { asking -= 1; nextAsk(); }));
  nextAsk();
});
function once(url, ask = api) {
  if (!answers.has(url)) {
    const a = { done: false };
    answers.set(url, a);
    ask(url).then((v) => Object.assign(a, { value: v, done: true }), (err) => Object.assign(a, { failed: err.message || String(err), done: true })).finally(tell);
  }
  return answers.get(url);
}

// the window's days, whichever date counts
export function windowDays(ctx) {
  const w = ctx.window;
  return { from: w.received_from || w.event_from || '', to: w.received_to || w.event_to || '' };
}
// the window is set once the event has read its first day
const ready = (ctx) => !!ctx.kind;

// a quarter end's day from the series' qnum (20262 is 2026 Q2)
const endOf = (qnum) => quarterEnd(`${Math.floor(qnum / 10)}q${qnum % 10}`);
// a statistic at the window's start (every case received before it) and at its end: the last quarter
// that ends in the window, the newest for a window to the release's end, none for a window that ends
// before the drug's first quarter
function scoresAt(got, w) {
  const ev = got?.events?.[0];
  if (!ev) return { start: null, end: null };
  const col = Object.fromEntries(got.columns.map((c, i) => [c, i]));
  const rows = ev.series.map((r) => ({ end: endOf(r[col.qnum]), row: Object.fromEntries(got.columns.map((c, i) => [c, r[i]])) }));
  const start = rows.findLast((q) => q.end < w.from) || null;
  const end = rows.findLast((q) => q.end <= w.to) || (w.to >= releaseEnd() ? rows.at(-1) : null) || null;
  return { start: start?.row || null, end: end?.row || null };
}

const NO_STATISTICS = 'Statistics are not open to you here.';
const NO_CLASS_SCORE = 'No score for the class with this event: the release scores a class only at some of its levels, and not for a group of reactions.';
const ALL_ONLY = "A class's score is worked out on every case of the release, so it stands only for a window to the release's end.";
const LEVEL = { 3: 2, 4: 3, 5: 4 }; // an ATC code's length -> its level, where the release can score it

// One row's numbers: { done, failed, cases, serious, death, eb05, prr ({ before, now } or null), now
// (the scores' row at the window's end, for a host's thresholds), why (no scores), reported (whether
// its cases ever name the event), and for a drug its label, or listed for a group of reactions }.
export function numbersOf(ctx, n) {
  if (!ready(ctx)) return { done: false };
  return n.kind === 'drug' ? drugNumbers(ctx, n) : classNumbers(ctx, n);
}

function drugNumbers(ctx, n) {
  const drug = n.name;
  const w = windowDays(ctx);
  const group = ctx.reaction.length > 1;
  const get = n.lvl ? queued : api;
  const counts = ctx.none ? { done: true, value: { cases: 0, serious: 0, death: 0 } } : once(`/api/events/group?${asked(ctx, drug)}&${reactions(ctx, 'reaction')}`, get);
  const stats = S.me?.statistics === false ? { done: true, failed: NO_STATISTICS }
    : once(`/api/statistics/quarters?product=${encodeURIComponent(drug)}&${reactions(ctx, 'reaction')}`, get);
  const settings = asked(ctx, drug, { settingsOnly: true });
  const label = group ? once(`/api/labels/query?${settings}&${reactions(ctx, 'reaction')}`, get)
    : once(`/api/events?${settings}&${reactions(ctx, 'pt')}`, get);
  if (!(counts.done && stats.done && label.done)) return { done: false };
  if (counts.failed) return { done: true, failed: counts.failed };
  const c = counts.value;
  const s = stats.failed ? { start: null, end: null } : scoresAt(stats.value, w);
  const score = (k) => (s.end?.[k] == null ? null : { before: s.start?.[k] ?? null, now: s.end[k] });
  const out = { done: true, cases: c.cases, serious: c.serious, death: c.death, eb05: score('eb05'), prr: score('prr'), extra: Object.fromEntries(EXTRA.map((x) => [x.id, score(x.id)])), now: s.end, why: stats.failed || '' };
  if (label.failed) return { ...out, reported: true };
  if (group) {
    const l = label.value;
    return { ...out, reported: !!l.reactions?.length, listed: l.reactions ? `${l.listed} of ${ctx.reaction.length} listed` : '' };
  }
  const named = (label.value.rows || []).map((r) => Object.fromEntries(label.value.columns.map((k, i) => [k, r[i]])));
  const row = named.find((r) => r.pt.toLowerCase() === ctx.reaction[0].toLowerCase());
  return { ...out, reported: !!row, label: row?.label || null, whyNoLabel: label.value.not_available?.label || '' };
}

// a class's scores for this event, as the release holds them
function classScores(ctx, n) {
  const level = LEVEL[n.code.length];
  if (n.kind !== 'class' || n.out?.length || !level || !S.release.class_statistics || S.me?.statistics === false || ctx.reaction.length > 1) return { why: NO_CLASS_SCORE };
  if (windowDays(ctx).to < releaseEnd()) return { why: ALL_ONLY };
  const event = ctx.reaction[0];
  const got = once(`/api/statistics?${new URLSearchParams({ by: 'class', level, find: event })}`, n.lvl ? queued : api);
  if (!got.done) return { waiting: true };
  const rows = (got.value?.rows || []).filter((r) => r.class === n.code && String(r.reaction).toLowerCase() === event.toLowerCase());
  return { row: rows[0] || null, why: NO_CLASS_SCORE };
}

function classNumbers(ctx, n) {
  const counts = ctx.none ? { done: true, value: { cases: 0, serious: 0, death: 0 } } : once(`/api/events/group?${classAsked(ctx, n)}&${reactions(ctx, 'reaction')}`, n.lvl ? queued : api);
  const scores = classScores(ctx, n);
  if (!counts.done || scores.waiting) return { done: false };
  if (counts.failed) return { done: true, failed: counts.failed };
  const c = counts.value;
  const score = (k) => (scores.row?.[k] == null ? null : { before: null, now: scores.row[k], noStart: ALL_ONLY });
  return { done: true, cases: c.cases, serious: c.serious, death: c.death, eb05: score('eb05'), prr: score('prr'), extra: Object.fromEntries(EXTRA.map((x) => [x.id, score(x.id)])), why: scores.why, reported: true };
}

// ---- what is inside a class ---------------------------------------------------------------------
const COMBINED = /\sand\s|,/; // WHO's combinations ("valsartan and diuretics"), counted by their class
const listed = new Map(); // url -> the answer, once read
const reading = new Map();
export function classesIn(ctx, what = {}) {
  const url = `/api/classes?${classScope(ctx)}&${new URLSearchParams(what)}`;
  if (!reading.has(url)) {
    reading.set(url, api(url).then((r) => {
      learnOwn(r.classes);
      learnClasses(r.classes.map((c) => [c.code, c.name]));
      if (what.parent) learnTree(what.parent, r.classes);
      listed.set(url, r);
      return r;
    }).catch((err) => { reading.delete(url); throw err; }));
  }
  return reading.get(url);
}
export const classesKnown = (ctx, what = {}) => listed.get(`/api/classes?${classScope(ctx)}&${new URLSearchParams(what)}`);

const named = new Map(); // WHO's name of a full code -> what the release opens for it, or null
function namedAs(name) {
  if (!named.has(name)) {
    named.set(name, undefined);
    queued(`/api/product?${new URLSearchParams({ product: name })}`).catch(() => null).then((f) => { named.set(name, f); tell(); });
  }
  return named.get(name);
}

const unread = new Set(); // classes whose members could not be read: drawn closed up, not asked again
// The classes, drugs and combinations in a class that name the event, each a row; null while they are
// read. A full code the release cannot open as one ingredient stays in view, counted by its class.
export function membersOf(ctx, n) {
  if (unread.has(n.code)) return [];
  const r = classesKnown(ctx, { parent: n.code });
  if (!r) {
    classesIn(ctx, { parent: n.code }).catch(() => unread.add(n.code)).finally(tell);
    return null;
  }
  const out = n.out || [];
  const kids = r.classes.filter((k) => k.cases > 0 && !out.some((o) => k.code.startsWith(o)));
  const singles = kids.filter((k) => k.level >= 5 && !COMBINED.test(k.name));
  if (singles.map((k) => namedAs(k.name)).some((f) => f === undefined)) return null;
  const lvl = n.lvl + 1;
  const seen = new Set();
  return kids.flatMap((k) => {
    if (k.level < 5) return [{ kind: 'class', code: k.code, title: k.name, out: out.filter((o) => o.startsWith(k.code) && o !== k.code), lvl, key: `c:${k.code}` }];
    const f = !COMBINED.test(k.name) && named.get(k.name);
    if (f?.kind !== 'ingredient' || f.name.includes(';')) return [{ kind: 'combo', code: k.code, title: k.name, lvl, key: `c:${k.code}` }];
    if (seen.has(f.name)) return [];
    seen.add(f.name);
    learnTitles([{ name: f.name, title: f.title || titleOf(f.name) }]);
    return [{ kind: 'drug', name: f.name, title: f.title || titleOf(f.name), own: f.name === ctx.drug, lvl, key: `d:${f.name}` }];
  });
}

// drugs found by what is typed, the event's own left out
export async function found(q, drug) {
  const got = await api(`/api/products?${new URLSearchParams({ q })}`);
  const drugs = (got.drugs || []).filter((d) => d.name !== drug).slice(0, 8).map((d) => ({ name: d.name, title: d.title || titleOf(d.name), cases: d.cases }));
  learnTitles(drugs);
  return drugs;
}
