/* The statistics a person adds to the Compared tab beyond EB05 and PRR (event-compared.js): which
   are on, each one's bound (shown only at or above it), and the menus that choose them. Nothing is
   saved: they last while the event stays open. */

import { choice } from './overlays.js';
import { icon } from './icons.js';
import { esc, tip } from './util.js';

// each statistic of the quarterly series a person may add: its head, its words and its sort
export const EXTRA = [
  { id: 'ebgm', title: 'EBGM', about: "EBGM, the empirical Bayes geometric mean" },
  { id: 'eb95', title: 'EB95', about: "EBGM's upper 5% bound" },
  { id: 'ror', title: 'ROR', about: 'Reporting odds ratio' },
  { id: 'ror_lower', title: 'ROR lower', about: "The lower end of ROR's 95% interval" },
  { id: 'ic', title: 'IC', about: 'Information component' },
  { id: 'ic025', title: 'IC025', about: "The lower end of IC's 95% interval" },
  { id: 'rrr', title: 'RRR', about: 'Relative reporting ratio' },
  { id: 'chi_square', title: 'Chi-square', about: "PRR's chi-square" },
];
export const extraOf = (id) => EXTRA.find((x) => x.id === id);

// the Columns menu: a tick box for each statistic
export function columnsHtml(on) {
  return `<p class="menu-heading">Statistics</p><div class="oa-choices">${EXTRA.map((x) => choice(on.includes(x.id), x.title, null, `data-act="cmp-col" data-v="${x.id}" data-tip="${esc(x.about)}"`)).join('')}</div>`;
}

// a head's menu for an added column: its bound, typed in place as Open Altio's head menus do
export function boundHtml(id, bound) {
  const title = extraOf(id).title;
  return `<p class="menu-heading">Show only</p>
    <label class="oa-et-bound"><span>At least</span><input class="oa-et-typeover" type="number" min="0" step="any" inputmode="decimal" data-cmp-bound="${id}" data-changed="${bound != null}" value="${bound ?? ''}" aria-label="${esc(title)} at least"><button type="button" class="icon-btn oa-et-reset" data-act="cmp-unbound" data-v="${id}" data-state="${bound == null ? 'off' : 'on'}" aria-label="Put back ${esc(title)} at least" ${tip('Put it back')}>${icon('reset')}</button></label>`;
}
