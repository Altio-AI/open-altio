/* What a host's page modules add: a host's own screens plug in here, each module calling
   extend() once as it loads. On this machine there are none. The keys extend() takes and the places
   a host draws in are closed lists, part of Open Altio's written contract
   (docs/reference/page-extension.md): an unknown key or place throws, so a host finds out at once. */

import { actions } from './events.js';
import { onClosing } from './overlays.js';

export const host = {
  brand: 'Open Altio', // the product's name, at the top of the frame and in the page's title
  improve: false, // whether Improve this is offered: a host that takes the notes says so
  start: null, // async: decides who is here and fills S.me and S.release, in place of the explorer's own
  routes: [], // (address parts) => the route a host's screen draws, or null; asked before the explorer's
  addresses: [], // (address parts) => whether the address is one of a host's screens, for any person
  pages: {}, // a route's page -> draw(route, app)
  after: [], // (route) => anything, once a page is drawn
  noted: [], // () => anything, once an improvement note is kept
  sendNote: null, // async (note) => { said } or { problem }: a module that sends notes elsewhere, in place of POST /api/notes
  // where the person's custom MedDRA queries are kept, when not in this browser (queries.js):
  // { group, save: async (query) => the query as kept, or { problem }, remove: async (query) => {} or { problem },
  // words?: { intro, save, saved: (query) => line } } where the builder should say something else
  queries: null,
  // where the person's view choices are kept, when not in this browser (state.js viewChoice):
  // { load: async () => { [choice]: value }, save: async (choice, value) => anything }
  kept: null,
  slots: {}, // a place in the frame -> [(current) => html]
  signedOut: () => {}, // an answer said the person is no longer signed in
  hideAsOf: () => false, // (here) => true where the corner and the top bar leave out how current the data is
  freshLinks: () => false, // true while links on the page must load as a browser loads them
  // (kind, detail): what the person did that the server cannot see, one of REPORTED. A host that keeps
  // a usage log sends it; on its own the explorer sends nothing.
  report: () => {},
};
export const cardTables = ['.oa-cases']; // lists read row by row, which become cards on phones

// Every key extend() takes: acts, pages, slots, routes, addresses, after, noted, closing and cards add
// to what is there; the others take the host's place.
export const EXTEND_KEYS = [
  'acts', 'pages', 'slots', 'routes', 'addresses', 'after', 'noted', 'closing', 'cards',
  'brand', 'improve', 'start', 'sendNote', 'queries', 'kept', 'signedOut', 'freshLinks', 'hideAsOf', 'report',
];
// Every place a host draws in, named for where it sits: the side panel and its folded rail, the
// export and SQL download dialogs, Improve this, Settings, the top right of every page, and an
// opened event's bar, Dates menu, line, the line under its bar and a drug's name in its tables.
export const SLOTS = [
  'side-places', 'side-you', 'side-you-end', 'rail-places', 'rail-you', 'rail-you-end',
  'export-note', 'sql-download-note', 'note-head', 'note-fields', 'settings', 'corner-end',
  'event-bar-end', 'event-window', 'event-under-bar', 'event-line-note', 'event-drug-mark',
  'event-after-evidence',
];

export function extend(given) {
  const unknown = Object.keys(given).find((key) => !EXTEND_KEYS.includes(key));
  if (unknown) throw new Error(`extend() takes no key "${unknown}"`);
  const { acts, pages, slots, routes, addresses, after, noted, closing, cards, ...rest } = given;
  const place = Object.keys(slots || {}).find((name) => !SLOTS.includes(name));
  if (place) throw new Error(`extend() takes no slot "${place}"`);
  actions(acts || {});
  Object.assign(host.pages, pages);
  for (const [name, html] of Object.entries(slots || {})) (host.slots[name] ||= []).push(html);
  host.routes.push(...(routes || []));
  host.addresses.push(...(addresses || []));
  host.after.push(...(after || []));
  host.noted.push(...(noted || []));
  (closing || []).forEach(onClosing);
  cardTables.push(...(cards || []));
  Object.assign(host, rest);
}

// what a host draws in one place of the frame
export function slot(name, current) {
  if (!SLOTS.includes(name)) throw new Error(`slot() takes no slot "${name}"`);
  return (host.slots[name] || []).map((html) => html(current)).join('');
}

// What the page reports, each with its detail (src/open_altio/explorer/access.py REPORTED): a screen
// or tab opened { screen, tab, product }, a rule read { rule }, a search's result picked { search,
// words, picked or level and code }, Improve this opened { page }.
export const REPORTED = ['screen', 'rule', 'pick', 'improve_opened'];

// what the person did, told to the host's report hook; a report never gets in their way, and a kind
// not in REPORTED is never sent
export function report(kind, detail) {
  if (!REPORTED.includes(kind)) return;
  try { host.report(kind, detail); } catch { /* the person's click goes on */ }
}

// a result picked from a search with words typed in it: an open name as `picked`, MedDRA's licensed
// levels and WHO's classes by `code` and `level`
export function picked(search, words, what) {
  const typed = (words || '').trim();
  if (typed) report('pick', { search, words: typed, ...what });
}
