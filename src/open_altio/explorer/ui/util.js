/* Small helpers every part of the page uses: escaping, numbers and dates as a person reads them,
   this browser's kept choices, the tip a grey value carries and the link to a value's rule. */

export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const num = (n) => (n == null ? '' : Number(n).toLocaleString('en-GB'));
export const fix = (n, d = 2) => (n == null || !isFinite(n) ? '' : Number(n).toFixed(d));
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const day = (iso) => {
  if (!iso) return '';
  const [y, m, d] = String(iso).slice(0, 10).split('-');
  return d ? `${d}-${MONTHS[+m - 1]}-${y}` : String(iso);
};
export const fdaDay = (raw) => {
  // FDA's yyyymmdd, yyyymm or yyyy, as a person reads it
  const s = String(raw || '');
  if (/^\d{8}$/.test(s)) return `${s.slice(6, 8)}-${MONTHS[+s.slice(4, 6) - 1] || '?'}-${s.slice(0, 4)}`;
  if (/^\d{6}$/.test(s)) return `${MONTHS[+s.slice(4, 6) - 1] || '?'}-${s.slice(0, 4)}`;
  return s;
};
// a company as the release names it (company_T); _direct, the reports sent straight to FDA by no
// company; or Not given (rule company-names)
export const companyName = (name) => (name == null || name === '_none' ? 'Not given' : name === '_direct' ? 'Sent straight to FDA' : name);
// a company typed: the words shown for the direct reports choose them, as the server reads them
export const typedCompany = (text) => (text.trim().toUpperCase() === companyName('_direct').toUpperCase() ? '_direct' : text.trim());

// a release's quarters in words, from where they start: the last is said once, on every page
export const sinceWords = ([from, to]) => (from === to ? 'one FDA quarter' : `FDA's quarters since ${from.toUpperCase()}`);

// A touch screen: nothing hovers there, so a hover that changes the page would cost the first tap
// (iOS takes it for the hover), and a text box takes focus only when pressed, so neither the
// keyboard nor a zoom opens on its own.
export const touchScreen = () => matchMedia('(pointer: coarse)').matches;
export const hovered = (e) => e.pointerType !== 'touch';
export const focusBox = (el, how) => { if (el && !touchScreen()) el.focus(how); };

// one prefix, so this app's keys never meet another page's on the same address
export const store = {
  get(k, d) { try { const v = localStorage.getItem(`open-altio.${k}`); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`open-altio.${k}`, JSON.stringify(v)); } catch { /* private window */ } },
};
export const tip = (text) => `data-tip="${esc(text)}"`;
// where a cleaned value came from, linked to its rule on the methods page
export const ruleTag = (rule, words) => `<a class="oa-rule-tag" href="/methods?open=${encodeURIComponent(rule)}">${esc(words)}</a>`;
// rows that stand in for what is still loading
export const skeletonRows = (n) => '<span class="skeleton skeleton-row"></span>'.repeat(n);
// up and down chevrons on every header that sorts: the lit one says which way it is sorted now
export const sortMark = (state) => `<svg class="oa-sort" data-sort="${state}" viewBox="0 0 10 16" aria-hidden="true"><path class="oa-sort-up" d="M2 6.5 5 3.5 8 6.5"/><path class="oa-sort-down" d="M2 9.5 5 12.5 8 9.5"/></svg>`;
// an FDA quarter, '2026q2' or '2026Q2': its first and its last day, as ISO dates
export const quarterStart = (q) => `${String(q).slice(0, 4)}-${String(3 * +String(q).slice(-1) - 2).padStart(2, '0')}-01`;
export const quarterEnd = (q) => {
  const y = +String(q).slice(0, 4), n = +String(q).slice(-1);
  return new Date(Date.UTC(y, 3 * n, 0)).toISOString().slice(0, 10);
};
// Where a search's find comes in its list (rule explorer-lists): 0 when one of its names is what
// was typed (`q`, in lower case), 1 when one starts with it, 2 when one holds it, -1 when none does
export const foundOrder = (q, ...names) => {
  const held = names.filter(Boolean).map((n) => String(n).toLowerCase());
  if (held.includes(q)) return 0;
  if (held.some((n) => n.startsWith(q))) return 1;
  return held.some((n) => n.includes(q)) ? 2 : -1;
};
// the items `order` finds by `q` (foundOrder of each): those named so first, then those starting
// so, then the rest, each in the list's own order; every item, as listed, while nothing is typed
export const foundFirst = (items, q, order) => (q
  ? items.map((x, i) => [order(x), i, x]).filter(([o]) => o >= 0).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([, , x]) => x)
  : items);
export const trim = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
export const size = (b) => (b == null ? '' : b > 1e9 ? `${fix(b / 1e9, 1)} GB` : b >= 1e6 ? `${fix(b / 1e6, 0)} MB` : `${fix(Math.max(b, 1e3) / 1e3, 0)} kB`);
