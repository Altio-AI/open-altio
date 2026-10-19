/* What a host's page modules add: a host's own screens plug in here, each module calling
   extend() once as it loads. On this machine there are none. */

import { actions } from './events.js';
import { onClosing } from './overlays.js';

export const host = {
  improve: false, // whether Improve this is offered: a host that takes the notes says so
  start: null, // async: decides who is here and fills S.me and S.release, in place of the explorer's own
  routes: [], // (address parts) => the route a host's screen draws, or null; asked before the explorer's
  addresses: [], // (address parts) => whether the address is one of a host's screens, for any person
  pages: {}, // a route's page -> draw(route, app)
  after: [], // (route) => anything, once a page is drawn
  noted: [], // () => anything, once an improvement note is kept
  sendNote: null, // async (note) => { said } or { problem }: a module that sends notes elsewhere, in place of POST /api/notes
  // where the person's custom MedDRA queries are kept, when not in this browser (queries.js):
  // { group, save: async (query) => the query as kept, or { problem }, remove: async (query) => {} or { problem } }
  queries: null,
  slots: {}, // a place in the frame -> [(current) => html]
  signedOut: () => {}, // an answer said the person is no longer signed in
  freshLinks: () => false, // true while links on the page must load as a browser loads them
  // (kind, detail): what the person did that the server cannot see: a screen or tab opened, a rule read,
  // a search result picked, Improve this opened. A host that keeps a usage log sends it; on its own the
  // explorer sends nothing.
  report: () => {},
};
export const cardTables = ['.oa-cases']; // lists read row by row, which become cards on phones

export function extend({ acts, pages, slots, routes, addresses, after, noted, closing, cards, ...rest }) {
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
export const slot = (name, current) => (host.slots[name] || []).map((html) => html(current)).join('');

// what the person did, told to the host's report hook; a report never gets in their way
export function report(kind, detail) {
  try { host.report(kind, detail); } catch { /* the person's click goes on */ }
}

// a result picked from a search with words typed in it: an open name as `picked`, MedDRA's licensed
// levels and WHO's classes by `code` and `level`
export function picked(search, words, what) {
  const typed = (words || '').trim();
  if (typed) report('pick', { search, words: typed, ...what });
}
