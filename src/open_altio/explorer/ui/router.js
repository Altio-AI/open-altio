/* Addresses and routing. Every page has a plain address with no "#": "/" is Home,
   /product/ADALIMUMAB/overview a product, /admin/requests a host's Administration. The server serves
   this page at each of them (src/open_altio/explorer/pages.py), so a reload or a link opens the page it
   names. An address that is not a page this view may see goes home, put in its place so Back does not
   return to it; there is no error page. A host's routes are asked first; signed out, a host may show
   its sign-in page at a page's address and go on to that page once signed in. */

import { host, report } from './host.js';
import { closeMenus, hideTip } from './overlays.js';
import { S, scopeFor } from './state.js';

// a product's and All cases' tabs, as their addresses name them
export const TABS = [['overview', 'Overview'], ['cases', 'Cases'], ['statistics', 'Statistics']];
const TAB_IDS = TABS.map(([id]) => id);

let currentRoute = null;
export const current = () => currentRoute;
export const here = () => location.pathname + location.search;

// open another page here: its address goes into the history, so Back and Forward work, then it is drawn
export const go = (path) => { if (path !== here()) history.pushState(null, '', path); render(); };
// put an address in place of the one shown, adding no step to the history
export const putAddress = (path) => { if (path !== here()) history.replaceState(null, '', path); };

export const productPath = (name, tab = 'overview') => `/product/${encodeURIComponent(name)}/${tab}`;

// the address's parts, decoded; null for an address that cannot be read
export function addressParts(path = location.pathname) {
  try { return path.split('/').filter(Boolean).map(decodeURIComponent); } catch { return null; }
}

// The explorer's own page an address names, or null.
export function pageAt(parts) {
  const [first, second, third, ...more] = parts;
  const tabOk = (t) => !t || TAB_IDS.includes(t);
  if (more.length) return null;
  if (!first) return { page: 'home' };
  if (first === 'product') return second && tabOk(third) ? { page: 'scope', product: second, tab: third || 'overview' } : null;
  if (first === 'all') return !third && tabOk(second) ? { page: 'scope', product: null, tab: second || 'overview' } : null;
  if (second) return null;
  if (first === 'release') return { page: 'release' };
  if (first === 'sql') return { page: 'release', tab: 'sql', address: '/release' };
  if (first === 'downloads') return { page: 'release', tab: 'tables', address: '/release' };
  if (first === 'methods') return { page: 'methods' };
  if (first === 'rules') return { page: 'methods', address: '/methods' }; // its old address
  return null;
}

// a page of these, so a click on a link to it opens it here (any other page loads as a browser loads it)
function isPageAddress(path) {
  const parts = addressParts(path);
  return !!parts && (!!pageAt(parts) || host.addresses.some((is) => is(parts)));
}

// the route of the address shown: a host's screen first, where it draws one, else the explorer's own page
function parseRoute() {
  const parts = addressParts();
  for (const route of host.routes) {
    const r = route(parts);
    if (r) return r;
  }
  const at = parts && pageAt(parts);
  if (!at) return { page: 'home', away: true };
  return at.page === 'scope' ? { ...at, scope: scopeFor(at.product) } : at;
}

// the explorer's own pages: a route's page -> draw(route, app), each added by the part that draws it
const PAGES = {};
export const drawn = (page, draw) => { PAGES[page] = draw; };

// a screen or tab opened, once each time it is: a page drawn again for its data is not opened again.
// Arriving on How we clean FAERS with rules named in the address (?open=), each is a rule read.
let seen = '';
function opened(r) {
  const screen = { screen: r.page, tab: r.tab || '', product: r.product || '' };
  const key = JSON.stringify(screen);
  if (key === seen) return;
  seen = key;
  report('screen', screen);
  if (r.page !== 'methods') return;
  const named = new URLSearchParams(location.search).get('open') || '';
  named.split(',').filter(Boolean).forEach((rule) => report('rule', { rule }));
}

export function render() {
  closeMenus();
  S.drawer = false;
  const r = parseRoute();
  if (r.away) putAddress('/'); // not a page this view may see: home, in its place, so Back does not return to it
  else if (r.address && r.address !== location.pathname) putAddress(r.address + location.search); // an old address of this page
  currentRoute = r;
  const app = document.getElementById('app');
  document.body.dataset.page = r.page;
  (host.pages[r.page] || PAGES[r.page])?.(r, app);
  hideTip();
  host.after.forEach((done) => done(r));
  opened(r);
}

// Back and Forward draw the page of the address they bring back.
window.addEventListener('popstate', render);
// A click on a link to one of these pages opens it here, without loading everything again. Links to
// other pages, clicks that open a new tab or window, and a host screen whose links start afresh load
// as a browser does.
document.addEventListener('click', (e) => {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || host.freshLinks()) return;
  const a = e.target.closest?.('a[href]');
  if (!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return;
  const url = new URL(a.getAttribute('href'), location.href);
  if (url.origin !== location.origin || !isPageAddress(url.pathname)) return;
  e.preventDefault();
  go(url.pathname + url.search);
});
