/* What the page knows: the state `S` every part reads, this browser's kept choices, and each
   scope's own (a product's page, or every case). Page modules add their own fields to `S`. */

import { quarterEnd, quarterStart, sinceWords, store } from './util.js';

function browserTheme() {
  try { return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'; } catch { return 'light'; }
}

// What this browser keeps for its person, read again when a page module has moved older keys into place.
function stored() {
  return {
    side: store.get('side', ''),
    theme: store.get('theme', null) || browserTheme(),
    showTables: store.get('showTables', true),
    // the products this person opened or pinned: [{ name (the drug, as the release names it), title
    // (as the page names it), label (their own name, or ''), opened (ms, or 0), pinned }]; the pinned
    // ones in the side panel's order. A list kept before pins were the side panel's, so it stays pinned.
    products: (store.get('products', null) || store.get('recent', []).map((name) => ({ name, label: '', opened: 0 })))
      .map((p) => ({ ...p, pinned: p.pinned ?? true })),
    // the person's own queries: [{ id, name, terms: [preferred terms] }]
    cmqs: store.get('cmqs', []),
  };
}

export const S = {
  ...stored(),
  drawer: false,
  me: null, // who is asking and what they may see (/api/me)
  release: null,
  scopes: {},
  sql: null,
  schema: null,
  manifest: null,
  downloads: null, // what can be downloaded here, and the limits (/api/downloads)
};

export const applyTheme = () => { document.documentElement.dataset.theme = S.theme; };
export function rereadStored() { Object.assign(S, stored()); applyTheme(); }

// MedDRA's licensed part, as /api/me says this person may see it; WHO's drug classes, as
// /api/release gives them: the index year and WHO's citation, when the release carries them and
// this person may see them
export const meddraOn = () => !!S.me?.tiers?.meddra;
export const whoOn = () => !!S.release?.classes;
export const classLayer = () => S.release.classes;
// WHO's names of the classes /api answers name, so a class reads the same wherever it shows
const classNames = {};
export const learnClasses = (pairs) => pairs.forEach(([code, name]) => { if (name) classNames[code] = name; });
export const className = (code) => classNames[code] || '';
// the MedDRA version reactions are counted in for this person, each under its current PT; null
// where they are FDA's text: the release holds no MedDRA, or the host shows them FDA's (/api/release)
export const ptVersion = () => (S.release?.reactions?.counted_by === 'current_pt' ? S.release.reactions.meddra_version : null);
// the words for that, where reactions are counted
export const ptCounted = () => (ptVersion() ? `by current PT in MedDRA ${ptVersion()}` : '');
// the host's line where reactions are listed, when this person sees FDA's text though the release
// holds MedDRA; empty otherwise
export const ptLine = () => S.release?.reactions?.line || '';

// The release, as /api/release names it: its first and last quarters, the last day it holds, and
// FDA's two systems with the quarters each published (rule era-filter)
// how current the data is, said in one place on every page (frame.js); elsewhere a release names
// only where its quarters start
export const releaseLast = () => S.release.quarters[1].toUpperCase();
export const releaseSince = () => sinceWords(S.release.quarters);
export const releaseEnd = () => quarterEnd(S.release.quarters[1]);
export const releaseEndYear = () => +releaseEnd().slice(0, 4);
export const eras = () => S.release.eras;
// the age bands in order, each with its words, then the words for no age (rule age-bands)
export const ages = () => S.release.ages;
// the notes on a field whose FDA files changed, when the received dates chosen, else the release's
// quarters, take in any of the quarters a note holds for (rule explorer-field-notes)
export const fieldNotes = (field, f) => {
  const lo = f.from || quarterStart(S.release.quarters[0]);
  const hi = f.to || releaseEnd();
  return S.release.field_notes.filter((n) => n.field === field && quarterStart(n.from) <= hi && (!n.to || quarterEnd(n.to) >= lo)).map((n) => n.note);
};
// how long one of the page's short lists is (rule explorer-lists)
export const listLength = (name) => S.release.lists[name];
// the day FDA's files start: the first day of AERS's first quarter
export const filesStart = () => quarterStart(eras().AERS[0]);
const year = (q) => String(q).slice(0, 4);
// FDA's systems in words: 'AERS, 2004Q1 to 2012Q3' and 'FAERS, 2012Q4 onward', or by their years
export const eraSpan = (era, { years = false } = {}) => {
  const [from, to] = eras()[era].map((q) => (years ? year(q) : q.toUpperCase()));
  return to ? `${from} to ${to}` : `${from} onward`;
};

// How a drug counts (rule explorer-drug-counts, as /api/release words it): FDA's role codes with
// their names, the units, and what is chosen when a page opens
export const drugWords = () => S.release.drugs;
export const defaultRoles = () => [...drugWords().default_roles];
// the titles /api answers give the drugs it names, so a drug reads the same wherever it shows
const titles = {};
export const learnTitles = (drugs) => drugs.forEach((d) => { titles[d.name] = d.title; });
export const productLabel = (name) => {
  const kept = S.products.find((p) => p.name === name);
  return kept?.label || titles[name] || kept?.title || name;
};
export function keepProducts() { store.set('products', S.products); }
// the side panel's products, in the person's order; the parts that show them are told as it changes
export const pinned = () => S.products.filter((p) => p.pinned);
const pinWatchers = [];
export const onPins = (redraw) => pinWatchers.push(redraw);
export const pinsChanged = () => pinWatchers.forEach((redraw) => redraw());
export const isPinned = (name) => !!S.products.find((p) => p.name === name)?.pinned;
// pinned, a product goes to the foot of the side panel; one never opened joins the list then
export function setPinned(name, on) {
  const p = S.products.find((x) => x.name === name) || { name, title: titles[name], label: '', opened: 0 };
  p.pinned = on;
  S.products = [...S.products.filter((x) => x !== p), p];
  keepProducts();
  pinsChanged();
}

// a scope: one product's page, or every case, with its filters, its tab and what was last asked for it;
// a product's page counts its drug in `unit` and `roles`, less the spellings in `exclude`, plus FDA's
// spellings with no ingredient in `include`
export function scopeFor(product) {
  const key = product ? `p:${product}` : 'all';
  if (!S.scopes[key]) {
    S.scopes[key] = {
      key, product, tab: 'overview', roles: defaultRoles(), unit: drugWords().default_unit, exclude: [], include: [],
      page: 1, sortCol: null, sortDir: 0,
      f: { pts: [], smqs: [], cmqs: [], ptsOut: [], dprods: [], droles: defaultRoles(), atc: [], atcOut: [], soc: [], aroles: defaultRoles(), could: false, from: '', to: '', efrom: '', eto: '', sex: [], age: [], outcome: [], reporter: [], country: [], sender: '', era: null, dedup: S.release.dedup, label: null },
      summary: null, cases: null, info: null,
    };
  }
  return S.scopes[key];
}
