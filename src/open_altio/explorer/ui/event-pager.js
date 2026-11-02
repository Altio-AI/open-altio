/* The pager under an opened event's cases: the range shown on the left, the pages around this one
   in the middle, how many cases a page on the right, each person's pick kept as a view choice. */

import { icon } from './icons.js';
import { choice } from './overlays.js';
import { keepView, viewChoice } from './state.js';
import { num } from './util.js';

const KEPT = 'event.casesPerPage';
// the presets in the pager's menu, and the most one may type there
export const PER_PAGE = [25, 50, 100, 200];
export const PER_MOST = 500;
export const perPage = () => { const n = viewChoice(KEPT, 50); return Number.isInteger(n) && n > 0 && n <= PER_MOST ? n : 50; };
export const keepPerPage = (n) => keepView(KEPT, n);
export const pagesOf = (total, per = perPage()) => Math.max(1, Math.ceil((total || 0) / per));

// the pages to show around page `now` of `last`: all of a few, else the ends and this page's neighbours
function pageList(now, last) {
  if (last <= 7) return Array.from({ length: last }, (_, i) => i + 1);
  if (now <= 4) return [1, 2, 3, 4, 5, '…', last];
  if (now >= last - 3) return [1, '…', last - 4, last - 3, last - 2, last - 1, last];
  return [1, '…', now - 1, now, now + 1, '…', last];
}

export function pagerHtml(now, total) {
  const per = perPage(), last = pagesOf(total, per);
  const range = total == null ? '<span class="skeleton oa-ec-range-sk"></span>' : total === 0 ? 'No cases'
    : `Cases <strong>${num((now - 1) * per + 1)} to ${num(Math.min(total, now * per))}</strong> of ${num(total)}`;
  const step = (to, mark, words, off) => `<button type="button" class="icon-btn oa-ec-pstep" data-act="ec-page" data-v="${to}" aria-label="${words}" ${off ? 'aria-disabled="true"' : ''}>${mark}</button>`;
  const pages = total ? pageList(now, last).map((p) => (p === '…' ? '<span class="oa-ec-pgap" aria-hidden="true">…</span>'
    : `<button type="button" class="oa-ec-pnum" data-act="ec-page" data-v="${p}" aria-label="Page ${p}"${p === now ? ' aria-current="page"' : ''}>${p}</button>`)).join('') : '';
  return `<p class="oa-ec-prange">${range}</p>
    <nav class="oa-ec-pages" aria-label="Pages of cases">${step(now - 1, `<span class="oa-ec-back">${icon('chevronRight')}</span>`, 'Previous page', now <= 1 || !total)}${pages}${step(now + 1, icon('chevronRight'), 'Next page', now >= last || !total)}</nav>
    <button type="button" class="btn oa-ec-per" data-act="ec-per" aria-haspopup="menu"><span>${num(per)} a page</span>${icon('chevronDown')}</button>`;
}

// its menu: the presets, or a number of one's own
export function perHtml() {
  const per = perPage(), own = !PER_PAGE.includes(per);
  return `<p class="menu-heading">Cases a page</p>
    <div class="oa-choices">${PER_PAGE.map((n) => choice(per === n, String(n), null, `data-act="ec-perpick" data-v="${n}"`, { radio: true })).join('')}</div>
    <hr class="oa-ec-rule">
    <label class="oa-ec-perown"><span>Your own</span><input class="field-input oa-ec-perinput" type="number" min="1" max="${PER_MOST}" step="1" inputmode="numeric" value="${own ? per : ''}" aria-label="Your own number of cases a page, up to ${PER_MOST}"><span>a page</span></label>`;
}
